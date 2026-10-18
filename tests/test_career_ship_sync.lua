-- Only injected stable/late/error counter observations and an owned store.
-- Run in the installed LuaJIT library; no Game process/UI/native reads/writes.
local create = dofile(assert(arg[1], 'career-ship-sync source required'))
local create_kd = dofile(assert(arg[2], 'career-kd source required'))
local PEER, OTHER = 'ABCDEF0123456789', '1122334455667788'
local cases = 0
local function test(name, fn)
    local ok, why = pcall(fn); assert(ok, name .. ': ' .. tostring(why)); cases = cases + 1
end
local function copy(v)
    if type(v) ~= 'table' then return v end
    local out = {}; for k, value in pairs(v) do out[k] = copy(value) end; return out
end
local function baseline(source)
    return {version = 1, source = source or 'personal_career_native_counters', local_peer = PEER,
        kills = 1000, deaths = 20, anchor_mod_kills = 50, anchor_mod_deaths = 5,
        anchor_mission_sequence = 19, synced_at = 'owned-previous'}
end
local function environment(saved)
    local e = {world = {game = 0x180000000, exe = 0x140000000},
        game = {state = 3, mission = false}, players = {{['local'] = true, peer = PEER:lower()}},
        history = {kills = 50, deaths = 5, medals = {kept = true}, other = {kept = 42}},
        sequence = 20, factories = 0, accepted = {}, logs = {}}
    e.store = {data = {career_kd = saved}, saves = 0, sets = {}}
    function e.store:get(key, fallback) local v = self.data[key]; if v == nil then return fallback end; return v end
    function e.store:set(key, value) self.sets[#self.sets + 1] = key; self.data[key] = value end
    function e.store:save() self.saves = self.saves + 1 end
    e.reader = {calls = 0, resets = 0, kills = 1000, deaths = 20, diagnostics = {},
        identity = {game = e.world.game, state_context = 0x400000000, local_user = 0x500000000,
            local_peer = PEER, counter_pointer = 0x600000000}}
    function e.reader:reset() self.resets = self.resets + 1 end
    function e.reader:read(world, requested_peer)
        assert(world == e.world and requested_peer == e.players[1].peer:upper())
        self.calls = self.calls + 1
        if self.mode == 'throw' then error('owned counter reader failure') end
        if self.mode == 'missing' then return nil, 'CAREER_COUNTERS_UNAVAILABLE' end
        local sample = {kills = self.kills, deaths = self.deaths, local_peer = requested_peer,
            identity = copy(self.identity), source = 'personal_career_native_counters'}
        if self.edit then self.edit(sample) end
        return sample, 'native_career_counters'
    end
    e.kd = create_kd(saved)
    e.api = create({store = e.store,
        reader = function()
            e.factories = e.factories + 1
            if e.factory_error then error('owned factory failure') end
            return e.reader
        end,
        accepted = function(value) e.accepted[#e.accepted + 1] = value; e.kd = create_kd(value) end,
        log = function(value) e.logs[#e.logs + 1] = value end})
    function e:step(now, enabled)
        return self.api:step(now, self.world, self.game, self.players, self.history, self.sequence, enabled)
    end
    return e
end

test('five-second delay two one-Hz observations then no more polling this Ship', function()
    local e = environment(); local medals, other = e.history.medals, e.history.other
    assert(not e:step(0)); assert(not e:step(4.999)); assert(e.reader.calls == 0 and e.factories == 0)
    assert(not e:step(5) and e.api.status == 'reading_counters')
    assert(not e:step(5.2)); assert(e.reader.calls == 1)
    assert(e:step(6) == true and e.api.status == 'synced')
    for _, now in ipairs({6.1, 7, 30, 100}) do assert(not e:step(now)) end
    assert(e.reader.calls == 2 and e.factories == 1 and e.store.saves == 1 and #e.accepted == 1)
    local value = e.store.data.career_kd
    assert(value.version == 1 and value.source == 'personal_career_native_counters')
    assert(value.policy == 'native_career_counters_plus_observed_deltas' and value.local_peer == PEER)
    assert(value.anchor_mod_kills == 50 and value.anchor_mod_deaths == 5 and value.anchor_mission_sequence == 20)
    assert(e.store.data.combat_history == e.history and e.history.medals == medals and e.history.other == other)
    assert(e.kd:totals(e.history).kills == 1000 and #e.logs == 1 and #e.store.sets == 2)
end)

test('SDK game-state wrapper recreated every tick does not restart initialization', function()
    local e = environment(); e:step(0)
    for now = 1, 5 do e.game = {state = 3, mission = false}; e:step(now) end
    e.game = {state = 3, mission = false}; assert(e:step(6) == true)
    assert(e.reader.calls == 2 and e.store.saves == 1)
end)

test('Title mission missing World and return Ship reset the lifetime', function()
    for _, depart in ipairs({function(e) e.game = {state = 2, mission = false} end,
        function(e) e.game = {state = 4, mission = true} end,
        function(e) e.world = nil end, function(e) e.game = nil end}) do
        local e = environment(); e:step(0); e:step(5); assert(e.reader.calls == 1)
        local world = e.world; depart(e); e:step(5.5); assert(e.api.status == 'waiting_ship')
        e.world, e.game = world, {state = 3, mission = false}; e:step(10)
        assert(not e:step(14.9)); assert(e.reader.calls == 1)
        assert(not e:step(15)); assert(e:step(16) == true and e.reader.calls == 3)
    end
end)

test('next Ship polls again but duplicate anchored totals do not save again', function()
    local e = environment(); e:step(0); e:step(5); e:step(6)
    e.game = {state = 4, mission = true}; e:step(7)
    e.game = {state = 3, mission = false}; e:step(10); e:step(15); assert(not e:step(16))
    assert(e.api.status == 'synced' and e.reader.calls == 4 and e.factories == 2)
    assert(e.store.saves == 1 and #e.accepted == 1 and #e.logs == 2)
    assert(e.logs[2]:find('与当前基准一致', 1, true))
end)

test('module and local-peer changes require a new Ship initialization and stable identity', function()
    for _, change in ipairs({function(e)
        e.world.game = e.world.game + 0x100000; e.reader.identity.game = e.world.game
    end, function(e)
        e.players[1].peer = OTHER; e.reader.identity.local_peer = OTHER
    end}) do
        local e = environment(); e:step(0); e:step(5); e:step(6); change(e); e:step(10)
        assert(not e:step(14.9)); assert(e.reader.calls == 2)
        e:step(15); e:step(16); assert(e.api.status == 'synced' and e.reader.calls == 4)
    end
end)

test('changed count or native object identity breaks sample stability', function()
    for _, change in ipairs({function(e) e.reader.kills = 1001 end,
        function(e) e.reader.identity.counter_pointer = e.reader.identity.counter_pointer + 8 end,
        function(e) e.reader.identity.state_context = e.reader.identity.state_context + 8 end}) do
        local e = environment(); e:step(0); e:step(5); change(e)
        assert(not e:step(6) and e.store.saves == 0)
        assert(e:step(7) == true and e.reader.calls == 3)
    end
end)

test('unsettled old counters never erase observed deltas and catch up before reanchoring', function()
    local previous = baseline(); local e = environment(previous)
    e.history.kills, e.history.deaths = 70, 6
    assert(e.kd:totals(e.history).kills == 1020 and e.kd:totals(e.history).deaths == 21)
    e:step(0); e:step(5); e:step(6); assert(e.api.status == 'waiting_settlement')
    assert(e.store.data.career_kd == previous and e.store.saves == 0)
    e.reader.kills, e.reader.deaths = 1020, 21; e:step(7); assert(e:step(8) == true)
    assert(e.store.data.career_kd.anchor_mod_kills == 70 and e.store.data.career_kd.anchor_mod_deaths == 6)
    assert(e.kd:totals(e.history).kills == 1020 and e.kd:totals(e.history).deaths == 21)
end)

test('prior baseline rejects all-zero fallback then expires and stays stopped until next Ship', function()
    local previous = baseline(); local e = environment(previous)
    e.reader.kills, e.reader.deaths = 0, 0; e:step(0)
    for now = 5, 29 do e:step(now) end
    assert(e.api.status == 'waiting_settlement' and e.reader.calls == 25)
    e:step(30); assert(e.api.status == 'expired' and e.store.data.career_kd == previous)
    e:step(31); e:step(50); assert(e.reader.calls == 25 and e.store.saves == 0)
    e.game = {state = 2, mission = false}; e:step(51)
    e.game = {state = 3, mission = false}; e.reader.kills, e.reader.deaths = 1000, 20
    e:step(52); e:step(57); e:step(58)
    assert(e.api.status == 'synced' and e.reader.calls == 27 and e.store.saves == 0)
end)

test('first-time player zero totals are valid', function()
    local e = environment(); e.reader.kills, e.reader.deaths = 0, 0
    e.history.kills, e.history.deaths = 0, 0
    e:step(0); e:step(5); assert(e:step(6) == true)
    assert(e.kd:totals(e.history).kills == 0 and e.store.saves == 1)
    assert(e.api:description():find('--', 1, true))
end)

test('invalid counts identity reader/factory errors and ambiguous peer preserve account', function()
    local changes = {
        function(e) e.reader.kills = -1 end, function(e) e.reader.deaths = .5 end,
        function(e) e.reader.kills = math.huge end, function(e) e.reader.kills = 0/0 end,
        function(e) e.reader.deaths = 2147483648 end, function(e) e.history.kills = -1 end,
        function(e) e.reader.mode = 'throw' end, function(e) e.reader.mode = 'missing' end,
        function(e) e.factory_error = true end,
        function(e) e.reader.edit = function(s) s.local_peer = OTHER end end,
        function(e) e.reader.edit = function(s) s.identity.local_peer = OTHER end end,
        function(e) e.reader.edit = function(s) s.identity.counter_pointer = nil end end,
        function(e) e.reader.edit = function(s) s.source = 'unknown' end end,
        function(e) e.reader.edit = function(s) s.identity.game = 0 end end,
        function(e) e.players[2] = {['local'] = true, peer = OTHER} end,
        function(e) e.players[1].peer = 'bad' end,
    }
    for _, change in ipairs(changes) do
        local previous = baseline(); local e = environment(previous); change(e)
        e:step(0); e:step(5); e:step(6)
        assert(e.store.data.career_kd == previous and e.store.saves == 0 and #e.store.sets == 0)
        assert(#e.accepted == 0 and e.api.last.kills == 1000)
    end
end)

test('disabled stops reader and discards incomplete sample before a new enabled lifetime', function()
    local e = environment(); e:step(0); e:step(5); e:step(5.1, false)
    assert(e.api.status == 'disabled' and e.reader.calls == 1 and e.store.saves == 0)
    e:step(6, false); e:step(9, false); assert(e.reader.calls == 1)
    e:step(10, true); e:step(15, true); assert(e:step(16, true) == true)
    local last, previous = e.api.last, e.store.data.career_kd
    e:step(17, false); e:step(30, false)
    assert(e.api.last == last and e.store.data.career_kd == previous and e.reader.calls == 3)
end)

test('manual/native saved totals display and manual reanchor restarts same-Ship confirmation without duplicate save', function()
    for _, source in ipairs({'personal_career_visible_page', 'personal_career_native_counters'}) do
        local previous = baseline(source); local e = environment(previous)
        assert(e.api.last.kills == 1000 and e.api.last.source == source)
        e:step(0); e:step(5); assert(not e:step(6))
        assert(e.api.status == 'synced' and e.store.saves == 0 and #e.accepted == 0)
        assert(#e.logs == 1 and e.logs[1]:find('与当前基准一致', 1, true))
        local manual = baseline('personal_career_visible_page'); manual.kills = 1002
        e.store.data.career_kd, e.reader.kills = manual, 1002; e:step(10)
        e:step(15); e:step(16)
        assert(e.reader.calls == 4 and e.api.last.kills == 1002 and e.api.status == 'synced')
        assert(e.store.data.career_kd == manual and e.store.saves == 0 and #e.accepted == 0)
        e:step(17); e:step(40); assert(#e.logs == 2 and e.reader.calls == 4)
    end
end)

test('reset observed history cannot silently replace a valid historical anchor', function()
    local previous = baseline(); local e = environment(previous); e.history.deaths = 4
    e:step(0); e:step(5); e:step(6)
    assert(e.api.reason == 'CAREER_LOCAL_HISTORY_RESET' and e.store.data.career_kd == previous)
    assert(e.store.saves == 0 and #e.accepted == 0)
end)

print('career-ship-sync: ' .. cases .. ' owned cases PASS; Ship delay/stability, bounded stop/reentry, personal identity, stale settlement, manual/native dedupe, disabled, zero; no Game reads/writes')
