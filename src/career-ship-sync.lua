-- One bounded read-only synchronization attempt per Ship lifetime.
-- Native reads are injected; successful totals become the same KD anchor as
-- the independent visible-page synchronization. No UI action or native write.
local SOURCE = 'personal_career_native_counters'
local IDENTITY = {'game', 'state_context', 'local_user', 'local_peer', 'counter_pointer'}
local ANCHOR = {'version', 'kills', 'deaths', 'anchor_mod_kills', 'anchor_mod_deaths',
    'anchor_mission_sequence', 'local_peer', 'source'}
local function count(value)
    return type(value) == 'number' and value >= 0 and value < 2147483648 and value % 1 == 0
end
local function peer(value)
    return type(value) == 'string' and #value == 16 and not value:find('[^%x]')
        and value ~= '0000000000000000'
end
local function stamp(value)
    local out = {}
    if type(value) == 'table' then
        for _, field in ipairs(ANCHOR) do out[field] = value[field] end
    end
    return out
end
local function same_fields(a, b, fields)
    if not a or not b then return false end
    for _, field in ipairs(fields) do if a[field] ~= b[field] then return false end end
    return true
end
local function baseline_valid(value, local_peer)
    return type(value) == 'table' and value.version == 1 and count(value.kills)
        and count(value.deaths) and count(value.anchor_mod_kills) and count(value.anchor_mod_deaths)
        and (value.local_peer == nil or value.local_peer == local_peer)
end
return function(options)
    local api = {status = 'waiting_ship', reason = nil, reads = 0, last = nil}
    local reader, candidate, lifetime, anchor_stamp
    local started, next_read, done
    local function remember(baseline)
        if type(baseline) == 'table' and count(baseline.kills) and count(baseline.deaths)
            and (baseline.source == SOURCE or baseline.source == 'personal_career_visible_page') then
            api.last = {kills = baseline.kills, deaths = baseline.deaths,
                synced_at = baseline.synced_at, local_peer = baseline.local_peer, source = baseline.source}
        end
    end
    remember(options.store:get('career_kd', nil))
    local function reset_reader()
        if reader and type(reader.reset) == 'function' then pcall(reader.reset, reader) end
        reader, candidate = nil, nil
    end
    local function leave(status, reason)
        if lifetime or reader or candidate then reset_reader() end
        lifetime, anchor_stamp, started, next_read, done = nil, nil, nil, nil, nil
        api.status, api.reason = status, reason
    end
    local function begin(now, world, local_peer, baseline)
        reset_reader()
        lifetime = {game = world.game, exe = world.exe, local_peer = local_peer}
        anchor_stamp, started, next_read, done = stamp(baseline), now, now + 5, false
        api.status, api.reason = 'waiting_initialization', nil
    end
    local function unavailable(reason)
        candidate, api.status, api.reason = nil, 'unavailable', reason
        if reader and type(reader.reset) == 'function' then pcall(reader.reset, reader) end
    end
    function api:step(now, world, game, players, history, sequence, enabled)
        if enabled == false then leave('disabled'); return end
        if not world or not game or game.state ~= 3 or game.mission then
            leave('waiting_ship'); return
        end
        if type(now) ~= 'number' or now ~= now or now == math.huge or now == -math.huge then
            leave('unavailable', 'CAREER_CLOCK_INVALID'); return
        end
        local local_peer
        for _, player in ipairs(players or {}) do
            if player['local'] == true then
                if local_peer then leave('unavailable', 'CAREER_AMBIGUOUS_LOCAL_PLAYER'); return end
                local_peer = player.peer
            end
        end
        if not peer(local_peer) then leave('waiting_ship', 'CAREER_LOCAL_PEER_UNAVAILABLE'); return end
        local_peer = local_peer:upper()
        local baseline = options.store:get('career_kd', nil)
        if not lifetime or lifetime.game ~= world.game or lifetime.exe ~= world.exe
            or lifetime.local_peer ~= local_peer
            or not same_fields(anchor_stamp, stamp(baseline), ANCHOR) or now < started then
            begin(now, world, local_peer, baseline)
            remember(baseline)
        end
        if done then return end
        if now >= started + 30 then
            reset_reader(); done = true
            self.status, self.reason = 'expired', 'CAREER_SHIP_WINDOW_ENDED'; return
        end
        if now + 1e-9 < next_read then return end
        next_read = now + 1
        if not reader then
            local ok, result = pcall(options.reader, world)
            if not ok or type(result) ~= 'table' or type(result.read) ~= 'function' then
                unavailable(ok and 'CAREER_READER_UNAVAILABLE' or tostring(result)); return
            end
            reader = result
        end
        self.reads = self.reads + 1
        local ok, snapshot, reason = pcall(reader.read, reader, world, local_peer)
        self.reader_diagnostics = reader.diagnostics
        if not ok then unavailable(tostring(snapshot)); return end
        if type(snapshot) ~= 'table' or reason ~= 'native_career_counters'
            or snapshot.source ~= SOURCE or snapshot.local_peer ~= local_peer then
            unavailable(reason or 'CAREER_PERSONAL_COUNTERS_UNAVAILABLE'); return
        end
        if not count(snapshot.kills) or not count(snapshot.deaths) or type(snapshot.identity) ~= 'table'
            or snapshot.identity.game ~= world.game or snapshot.identity.local_peer ~= local_peer
            or type(history) ~= 'table' or not count(history.kills) or not count(history.deaths)
            or not count(sequence) then
            unavailable('CAREER_ANCHOR_INVALID'); return
        end
        for _, field in ipairs(IDENTITY) do
            if snapshot.identity[field] == nil then unavailable('CAREER_COUNTER_IDENTITY_INVALID'); return end
        end
        if baseline_valid(baseline, local_peer) then
            if history.kills < baseline.anchor_mod_kills or history.deaths < baseline.anchor_mod_deaths then
                unavailable('CAREER_LOCAL_HISTORY_RESET'); return
            end
            if snapshot.kills < baseline.kills + history.kills - baseline.anchor_mod_kills
                or snapshot.deaths < baseline.deaths + history.deaths - baseline.anchor_mod_deaths then
                candidate, self.status, self.reason = nil, 'waiting_settlement', 'CAREER_COUNTERS_BEHIND_ANCHOR'
                return
            end
        end
        local observed = {kills = snapshot.kills, deaths = snapshot.deaths, identity = {}}
        for _, field in ipairs(IDENTITY) do observed.identity[field] = snapshot.identity[field] end
        if not candidate or candidate.kills ~= observed.kills or candidate.deaths ~= observed.deaths
            or not same_fields(candidate.identity, observed.identity, IDENTITY) then
            candidate, self.status, self.reason = observed, 'reading_counters', nil; return
        end
        done, candidate, self.status, self.reason = true, nil, 'synced', nil
        if baseline_valid(baseline, local_peer) and baseline.kills == observed.kills
            and baseline.deaths == observed.deaths and baseline.anchor_mod_kills == history.kills
            and baseline.anchor_mod_deaths == history.deaths then
            remember(baseline); reset_reader()
            options.log(string.format('上舰生涯核对成功：敌方击杀 %d；阵亡 %d；与当前基准一致。',
                observed.kills, observed.deaths))
            return
        end
        baseline = {version = 1, kills = observed.kills, deaths = observed.deaths,
            anchor_mod_kills = history.kills, anchor_mod_deaths = history.deaths,
            anchor_mission_sequence = sequence, local_peer = local_peer, source = SOURCE,
            synced_at = os.date('!%Y-%m-%dT%H:%M:%SZ'),
            policy = 'native_career_counters_plus_observed_deltas'}
        options.store:set('combat_history', history)
        options.store:set('career_kd', baseline)
        options.store:save()
        anchor_stamp = stamp(baseline)
        remember(baseline); reset_reader()
        options.accepted(baseline)
        options.log(string.format('上舰生涯同步成功：敌方击杀 %d；阵亡 %d；历史KD %s。',
            baseline.kills, baseline.deaths, baseline.deaths > 0
                and string.format('%.2f', baseline.kills / baseline.deaths) or '--'))
        return true
    end
    function api:description()
        local message = self.status == 'disabled' and '上舰生涯同步已关闭。'
            or self.status == 'waiting_initialization' and '上舰后等待生涯数据初始化。'
            or self.status == 'reading_counters' and '正在确认本人生涯数据。'
            or self.status == 'waiting_settlement' and '等待生涯数据结算，保留现有历史KD。'
            or self.status == 'synced' and '本次上舰生涯同步完成。'
            or self.status == 'expired' and '本次上舰未完成同步；下次上舰再试，可手动打开生涯页同步。'
            or self.status == 'unavailable' and '暂未读到完整生涯数据，保留上次结果。'
            or '上舰后自动同步本人生涯数据。'
        if self.last then
            message = message .. string.format(' 最近同步：%d杀 / %d阵亡，KD %s；%s。',
                self.last.kills, self.last.deaths, self.last.deaths > 0
                    and string.format('%.2f', self.last.kills / self.last.deaths) or '--', self.last.synced_at or '')
        end
        return message
    end
    return api
end
