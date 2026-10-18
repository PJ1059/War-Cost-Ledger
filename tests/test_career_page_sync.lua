-- Injected reader/store only. The real career-kd module is pure Lua.
-- No game memory, UI action, native callback, or external account is used.
local create = dofile(assert(arg[1], 'career-page-sync source required'))
local create_kd = dofile(assert(arg[2], 'career-kd source required'))
local PEER, OTHER = 'ABCDEF0123456789', '1122334455667788'
local cases = 0
local function test(name, fn)
    local ok, why = pcall(fn)
    assert(ok, name .. ': ' .. tostring(why))
    cases = cases + 1
end
local function copy(value)
    if type(value) ~= 'table' then return value end
    local out = {}; for key, item in pairs(value) do out[key] = copy(item) end
    return out
end
local function environment(saved)
    local e = {world = {}, game = {state = 3, mission = false},
        players = {{['local'] = false, peer = OTHER}, {['local'] = true, peer = PEER:lower()}},
        history = {kills = 449, deaths = 2, medals = {fragrant = true, democracy_undying = true},
            other_observed = {value = 37}}, sequence = 18,
        accepted = {}, logs = {}, factories = 0}
    e.store = {data = {career_kd = saved}, sets = {}, saves = 0}
    function e.store:get(key, fallback) local v = self.data[key]; if v == nil then return fallback end; return v end
    function e.store:set(key, value) self.sets[#self.sets + 1] = {key, value}; self.data[key] = value end
    function e.store:save() self.saves = self.saves + 1 end
    e.reader = {calls = 0, resets = 0, diagnostics = {}, mode = 'visible',
        kills = 351849, deaths = 4633,
        identity = {game = 0x180000000, controller = 0x300000000, gui_context = 0x400000000}}
    function e.reader:reset() self.resets = self.resets + 1 end
    function e.reader:read(world, requested_peer)
        assert(world == e.world and requested_peer == PEER, 'reader must receive current local peer, normalized')
        self.calls = self.calls + 1
        if self.mode == 'throw' then error('owned reader failure') end
        if self.mode == 'missing' then return nil, 'CAREER_CONTROLLER_UNAVAILABLE' end
        if self.mode == 'error' then return nil, 'CAREER_READ_FAILED' end
        local snapshot = {kills = self.kills, deaths = self.deaths,
            local_peer = self.mode == 'foreign' and OTHER or PEER,
            page_visible = self.mode ~= 'hidden', identity = copy(self.identity)}
        if self.edit then self.edit(snapshot) end
        return snapshot, self.mode == 'hidden' and 'ui_cache_observed' or 'page_visible'
    end
    e.kd = create_kd(saved)
    e.api = create({store = e.store,
        reader = function() e.factories = e.factories + 1; return e.reader end,
        accepted = function(baseline)
            e.accepted[#e.accepted + 1] = copy(baseline)
            e.kd = create_kd(baseline)
        end,
        log = function(message) e.logs[#e.logs + 1] = message end})
    function e:step(now, enabled)
        return self.api:step(now, self.world, self.game, self.players, self.history, self.sequence, enabled)
    end
    function e:totals() return assert(self.kd:totals(self.history)) end
    return e
end

test('only two consecutive visible personal observations commit one anchor', function()
    local e = environment(); assert(not e:step(0))
    assert(e.api.status == 'reading_page' and e.store.saves == 0 and #e.accepted == 0)
    assert(not e:step(.05)); assert(e.reader.calls == 1, 'main ticker must not force full reads every tick')
    assert(e:step(1) == true)
    local baseline = e.store.data.career_kd
    assert(baseline.version == 1 and baseline.source == 'personal_career_visible_page')
    assert(baseline.local_peer == PEER and baseline.kills == 351849 and baseline.deaths == 4633)
    assert(baseline.anchor_mod_kills == 449 and baseline.anchor_mod_deaths == 2)
    assert(baseline.anchor_mission_sequence == 18 and baseline.synced_at:match('^%d%d%d%d%-%d%d%-%d%dT'))
    assert(e.store.saves == 1 and #e.store.sets == 2 and #e.accepted == 1 and #e.logs == 1)
    assert(e.api.last.kills == 351849 and e.api.status == 'synced')
    assert(e:totals().kills == 351849 and e:totals().deaths == 4633)
end)

test('nonShip missing world and mission never construct or poll the reader', function()
    for _, change in ipairs({function(e) e.world = nil end, function(e) e.game = nil end,
        function(e) e.game.state = 4 end, function(e) e.game.mission = true end}) do
        local e = environment(); change(e); assert(not e:step(0)); assert(not e:step(2))
        assert(e.api.status == 'waiting_ship' and e.factories == 0 and e.reader.calls == 0)
        assert(e.store.saves == 0 and #e.store.sets == 0)
    end
end)

test('hidden unavailable error and foreign snapshots cannot replace a prior anchor', function()
    for _, mode in ipairs({'hidden', 'missing', 'error', 'throw', 'foreign'}) do
        local previous = {version = 1, source = 'personal_career_visible_page', local_peer = PEER,
            kills = 351000, deaths = 4600, anchor_mod_kills = 10, anchor_mod_deaths = 1}
        local e = environment(previous); e:step(0); e.reader.mode = mode; assert(not e:step(1))
        assert(e.store.data.career_kd == previous and e.store.saves == 0 and #e.accepted == 0)
        assert(e.api.last.kills == 351000 and e.reader.resets >= 1)
        e.reader.mode = 'visible'; assert(not e:step(2))
        assert(e.api.status == 'reading_page' and e.store.saves == 0, 'a failure must break stability')
        assert(e:step(3) == true and e.store.saves == 1)
    end
end)

test('no local player malformed peer and ambiguous local players do not read', function()
    for _, players in ipairs({{{['local'] = false, peer = OTHER}},
        {{['local'] = true, peer = 'bad'}},
        {{['local'] = true, peer = '0000000000000000'}},
        {{['local'] = true, peer = PEER}, {['local'] = true, peer = OTHER}}}) do
        local e = environment(); e.players = players; assert(not e:step(0))
        assert(e.reader.calls == 0 and e.factories == 0 and e.store.saves == 0)
    end
end)

test('changes to identity or displayed value restart the two-observation requirement', function()
    for _, field in ipairs({'game', 'controller', 'gui_context', 'kills', 'deaths'}) do
        local e = environment(); e:step(0)
        if e.reader.identity[field] then e.reader.identity[field] = e.reader.identity[field] + 8
        else e.reader[field] = e.reader[field] + 1 end
        assert(not e:step(1)); assert(e.api.status == 'reading_page' and e.store.saves == 0)
        assert(e:step(2) == true and e.store.saves == 1)
        assert(e.store.data.career_kd.kills == e.reader.kills and e.store.data.career_kd.deaths == e.reader.deaths)
    end
end)

test('same visible values and same local anchor never repeat save accepted or log', function()
    local e = environment(); e:step(0); e:step(1)
    local old_baseline = e.store.data.career_kd
    for now = 2, 8 do assert(not e:step(now)) end
    assert(e.store.data.career_kd == old_baseline and e.store.saves == 1)
    assert(#e.accepted == 1 and #e.logs == 1 and #e.store.sets == 2)
    local restored = environment(copy(old_baseline))
    assert(restored.api.last.kills == 351849 and restored.api.last.deaths == 4633)
    restored:step(0); assert(not restored:step(1))
    assert(restored.api.status == 'synced' and restored.store.saves == 0 and #restored.logs == 0)
end)

test('reopened real totals replace the anchor without counting old local history twice', function()
    local e = environment(); e:step(0); e:step(1)
    local original = e.store.data.career_kd
    e.game = {state = 4, mission = true}; e.history.kills = 549; e.history.deaths = 3
    assert(not e:step(2)); assert(e:totals().kills == 351949 and e:totals().deaths == 4634)
    e.game = {state = 3, mission = false}; e.sequence = 19
    e.reader.kills, e.reader.deaths = 351999, 4635
    assert(not e:step(3)); assert(e:step(4) == true)
    assert(e.store.saves == 2 and e:totals().kills == 351999 and e:totals().deaths == 4635)
    assert(e.store.data.career_kd.anchor_mod_kills == 549 and e.store.data.career_kd.anchor_mod_deaths == 3)
    assert(e.store.data.career_kd.anchor_mission_sequence == 19)
    assert(original.kills == 351849 and original.anchor_mod_kills == 449)
    e.history.kills, e.history.deaths = 559, 4
    assert(e:totals().kills == 352009 and e:totals().deaths == 4636)
end)

test('changed nonmission local counters reanchor once while preserving medals and other history', function()
    local e = environment(); local medals, extra = e.history.medals, e.history.other_observed
    e:step(0); e:step(1); e.reader.mode = 'hidden'; assert(not e:step(2))
    e.history.kills, e.history.deaths = 700, 6
    e.reader.mode = 'visible'; assert(not e:step(3)); assert(e:step(4) == true)
    local baseline = e.store.data.career_kd
    assert(baseline.kills == 351849 and baseline.anchor_mod_kills == 700 and baseline.anchor_mod_deaths == 6)
    assert(e:totals().kills == 351849 and e:totals().deaths == 4633)
    assert(e.store.data.combat_history == e.history and e.history.medals == medals)
    assert(medals.fragrant and medals.democracy_undying and e.history.other_observed == extra and extra.value == 37)
    assert(not e:step(5)); assert(e.store.saves == 2)
end)

test('genuine zero totals are legal and zero death display has no division error', function()
    local e = environment(); e.reader.kills, e.reader.deaths = 0, 0
    e.history.kills, e.history.deaths = 0, 0
    e:step(0); assert(e:step(1) == true)
    assert(e:totals().kills == 0 and e:totals().deaths == 0 and e.store.saves == 1)
    assert(e.logs[1]:find('--', 1, true) and e.api:description():find('--', 1, true))
end)

test('invalid displayed counts and invalid local anchors refuse all writes', function()
    for _, value in ipairs({-1, .5, math.huge, 2147483648}) do
        local e = environment(); e.reader.kills = value; e:step(0); e:step(1)
        assert(e.api.reason == 'CAREER_ANCHOR_INVALID' and e.store.saves == 0 and #e.store.sets == 0)
        e = environment(); e.history.deaths = value; e:step(0); e:step(1)
        assert(e.api.reason == 'CAREER_ANCHOR_INVALID' and e.store.saves == 0)
    end
    local e = environment(); e.reader.kills = 0/0; e:step(0); e:step(1)
    assert(e.api.reason == 'CAREER_ANCHOR_INVALID' and e.store.saves == 0)
    e = environment(); e.reader.edit = function(snapshot) snapshot.identity = nil end
    e:step(0); e:step(1); assert(e.api.reason == 'CAREER_ANCHOR_INVALID' and e.store.saves == 0)
end)

test('disabled clears the pending observation and can recover without discarding prior results', function()
    local e = environment(); e:step(0); assert(not e:step(.1, false))
    assert(e.api.status == 'disabled' and e.store.saves == 0 and e.reader.resets >= 1)
    assert(not e:step(1, true) and e.store.saves == 0, 'pre-disable observation must not count')
    assert(e:step(2, true) == true)
    local last, baseline, calls = e.api.last, e.store.data.career_kd, e.reader.calls
    for now = 3, 5 do assert(not e:step(now, false)) end
    assert(e.reader.calls == calls and e.api.last == last and e.store.data.career_kd == baseline)
    assert(not e:step(6, true)); assert(not e:step(7, true))
    assert(e.api.status == 'synced' and e.store.saves == 1 and #e.accepted == 1)
end)

print('career-page-sync: ' .. cases .. ' owned cases PASS; visible personal Ship stability, dedupe, reanchor, medals, zero, disabled recovery; no game reads/writes')
