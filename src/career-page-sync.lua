-- A visible personal Career page establishes a new lifetime anchor.
-- The reader is injected; this module performs no native writes or UI actions.
local function count(value)
    return type(value) == 'number' and value >= 0 and value < 2147483648 and value % 1 == 0
end
local function peer(value)
    return type(value) == 'string' and #value == 16 and not value:find('[^%x]')
        and value ~= '0000000000000000'
end
local function same(a, b)
    return a and b and a.game == b.game and a.controller == b.controller
        and a.gui_context == b.gui_context and a.local_peer == b.local_peer
        and a.kills == b.kills and a.deaths == b.deaths
end
return function(options)
    local saved = options.store:get('career_kd', nil)
    local api = {status = 'waiting_page', reason = nil, reads = 0, last = nil}
    if type(saved) == 'table' and saved.source == 'personal_career_visible_page'
        and count(saved.kills) and count(saved.deaths) then
        api.last = {kills = saved.kills, deaths = saved.deaths, synced_at = saved.synced_at,
            local_peer = saved.local_peer}
    end
    local reader, candidate, next_read = nil, nil, 0
    local function clear(status, reason)
        candidate, api.status, api.reason = nil, status, reason
        if reader then reader:reset() end
    end
    function api:step(now, world, game, players, history, sequence, enabled)
        if enabled == false then clear('disabled'); return end
        if not world or not game or game.state ~= 3 or game.mission then
            clear('waiting_ship'); return
        end
        if now + 1e-9 < next_read then return end
        next_read = now + 1
        local local_peer
        for _, player in ipairs(players or {}) do
            if player['local'] == true then
                if local_peer then clear('unavailable', 'CAREER_AMBIGUOUS_LOCAL_PLAYER'); return end
                local_peer = player.peer
            end
        end
        if not peer(local_peer) then clear('waiting_page', 'CAREER_LOCAL_PEER_UNAVAILABLE'); return end
        local_peer = local_peer:upper()
        if not reader then
            local ok, result = pcall(options.reader, world)
            if not ok then clear('unavailable', tostring(result)); return end
            reader = result
        end
        self.reads = self.reads + 1
        local ok, snapshot, reason = pcall(reader.read, reader, world, local_peer)
        self.reader_diagnostics = reader.diagnostics
        if not ok then clear('unavailable', tostring(snapshot)); return end
        if not snapshot or snapshot.page_visible ~= true or reason ~= 'page_visible'
            or snapshot.local_peer ~= local_peer then
            local waiting = reason == 'CAREER_CONTROLLER_UNAVAILABLE'
                or reason == 'CAREER_PAGE_NOT_VISIBLE' or reason == 'CAREER_UI_CACHE_NOT_ESTABLISHED'
            clear(waiting and 'waiting_page' or 'unavailable', reason); return
        end
        if not count(snapshot.kills) or not count(snapshot.deaths) or not snapshot.identity
            or not count(history.kills) or not count(history.deaths) then
            clear('unavailable', 'CAREER_ANCHOR_INVALID'); return
        end
        local observed = {game = snapshot.identity.game, controller = snapshot.identity.controller,
            gui_context = snapshot.identity.gui_context, local_peer = local_peer,
            kills = snapshot.kills, deaths = snapshot.deaths}
        -- Two low-frequency visible observations settle page opening/fill animation.
        -- This is the displayed value, not a promise of server refresh completion.
        if not same(candidate, observed) then
            candidate, self.status, self.reason = observed, 'reading_page', nil; return
        end
        local baseline = options.store:get('career_kd', nil)
        if type(baseline) == 'table' and baseline.source == 'personal_career_visible_page'
            and baseline.local_peer == local_peer and baseline.kills == observed.kills
            and baseline.deaths == observed.deaths and baseline.anchor_mod_kills == history.kills
            and baseline.anchor_mod_deaths == history.deaths then
            self.status, self.reason = 'synced', nil; return
        end
        baseline = {version = 1, kills = observed.kills, deaths = observed.deaths,
            anchor_mod_kills = history.kills, anchor_mod_deaths = history.deaths,
            anchor_mission_sequence = sequence, local_peer = local_peer,
            source = 'personal_career_visible_page',
            synced_at = os.date('!%Y-%m-%dT%H:%M:%SZ'), policy = 'visible_page_plus_observed_deltas'}
        options.store:set('combat_history', history)
        options.store:set('career_kd', baseline)
        options.store:save()
        self.last = {kills = baseline.kills, deaths = baseline.deaths, synced_at = baseline.synced_at,
            local_peer = local_peer}
        self.status, self.reason = 'synced', nil
        options.accepted(baseline)
        options.log(string.format('生涯同步成功：敌方击杀 %d；阵亡 %d；历史KD %s。',
            baseline.kills, baseline.deaths, baseline.deaths > 0
                and string.format('%.2f', baseline.kills / baseline.deaths) or '--'))
        return true
    end
    function api:description()
        local message = self.status == 'disabled' and '生涯同步已关闭。'
            or self.status == 'reading_page' and '正在读取完整生涯页。'
            or self.status == 'unavailable' and '暂未读到完整数据，保留上次结果。'
            or '在飞船打开自己的完整生涯统计页，保持约3秒，即可同步。'
        if self.last then
            message = message .. string.format(' 最近同步：%d杀 / %d阵亡，KD %s；%s。',
                self.last.kills, self.last.deaths, self.last.deaths > 0
                    and string.format('%.2f', self.last.kills / self.last.deaths) or '--', self.last.synced_at or '')
        end
        return message
    end
    return api
end
