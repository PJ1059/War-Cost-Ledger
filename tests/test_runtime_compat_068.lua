-- Capability contracts are independent from Runtime release labels. These tests
-- deliberately do not call any supplied native/read/write function.
local module_path = assert(arg[1], 'runtime-compat.lua required')
local compat = dofile(module_path)
assert(type(compat) == 'table' and type(compat.check) == 'function'
    and type(compat.load) == 'function' and type(compat.check_objects) == 'function')
local function fn() error('capability validation must not execute Runtime APIs') end
local function fixture(version)
    return {mod = fn, ui = {overlay = fn}},
        {open = fn, game_state = fn, players = fn, entity_state = fn, stat_breakdown = fn},
        {prove = fn, beacons = fn, clock = fn}, {prove = fn, id_of = fn},
        {stats = {keys = {projectiles_fired = 1, dealt_kills = 2, received_deaths = 3, projectiles_hit = 4}}},
        {version = version, api_version = 1}
end
local function unpacked(values) return unpack(values, 1, 6) end
for _, version in ipairs({'0.30.3', '0.30.4', '0.40.1', '99.99.99', 'custom-build'}) do
    assert(compat.check(fixture(version)), 'API-identical label incorrectly rejected: ' .. version)
end
do
    local parts = {fixture('0.30.3')}; parts[6].api_version = nil
    assert(compat.check(unpacked(parts)), 'legacy metadata requires shape validation')
end
local cases = {
    {1, {'mod'}, 'hd2.mod'}, {1, {'ui', 'overlay'}, 'hd2.ui.overlay'},
    {2, {'open'}, 'event_world.open'}, {2, {'game_state'}, 'event_world.game_state'},
    {2, {'players'}, 'event_world.players'}, {2, {'entity_state'}, 'event_world.entity_state'},
    {2, {'stat_breakdown'}, 'event_world.stat_breakdown'},
    {3, {'prove'}, 'beacon_redirect.prove'}, {3, {'beacons'}, 'beacon_redirect.beacons'},
    {3, {'clock'}, 'beacon_redirect.clock'},
    {4, {'prove'}, 'stratagem_loadout.prove'}, {4, {'id_of'}, 'stratagem_loadout.id_of'},
    {5, {'stats', 'keys', 'projectiles_fired'}, 'projectiles_fired'},
    {5, {'stats', 'keys', 'dealt_kills'}, 'dealt_kills'},
    {5, {'stats', 'keys', 'received_deaths'}, 'received_deaths'},
    {5, {'stats', 'keys', 'projectiles_hit'}, 'projectiles_hit'},
}
for _, case in ipairs(cases) do
    local parts = {fixture('0.30.4')}; local owner = parts[case[1]]
    for index = 1, #case[2] - 1 do owner = owner[case[2][index]] end
    owner[case[2][#case[2]]] = nil
    local ok, why = compat.check(unpacked(parts))
    assert(not ok and type(why) == 'string' and why:find(case[3], 1, true),
        'missing capability needs exact field diagnostic: ' .. case[3] .. ': ' .. tostring(why))
end
for _, value in ipairs({-1, 1.5, math.huge, '2', 4294967296}) do
    local parts = {fixture('0.30.4')}; parts[5].stats.keys.dealt_kills = value
    local ok, why = compat.check(unpacked(parts))
    assert(not ok and tostring(why):find('dealt_kills', 1, true), 'invalid native counter key accepted')
end
do
    local parts = {fixture('0.30.4')}; parts[5].stats.keys.dealt_kills = 0/0
    assert(not compat.check(unpacked(parts)), 'NaN native counter key accepted')
    parts = {fixture('0.30.4')}; parts[6].api_version = 2
    local ok, why = compat.check(unpacked(parts))
    assert(not ok and tostring(why):find('api_version', 1, true), 'declared unsupported API was ignored')
end
print('PASS Runtime labels do not gate identical capabilities; missing functions, invalid uint counters, unsupported declared API are diagnosed')
local function objects()
    return {log = fn, store = fn, bind = fn, on_frame = fn},
        {get = fn, set = fn, save = fn}, {draw = fn, show = fn, hide = fn}
end
assert(compat.check_objects(objects()))
for index, keys in ipairs({{'log','store','bind','on_frame'}, {'get','set','save'}, {'draw','show','hide'}}) do
    for _, key in ipairs(keys) do
        local parts = {objects()}; parts[index][key] = nil
        local ok, why = compat.check_objects(unpack(parts))
        assert(not ok and tostring(why):find(key, 1, true), 'missing object method not diagnosed: ' .. key)
    end
end
local parts = {fixture('0.30.4')}
local names = {'mods/skyeshade/hd2runtime', 'hd2runtime/domains/metadata',
    'hd2runtime/runtime/event_world', 'hd2runtime/runtime/beacon_redirect',
    'hd2runtime/runtime/stratagem_loadout', 'hd2runtime/domains/event_natives'}
local loaded = {[names[1]] = parts[1], [names[2]] = parts[6], [names[3]] = parts[2],
    [names[4]] = parts[3], [names[5]] = parts[4], [names[6]] = parts[5]}
local hd2, metadata, world, beacons, loadout, keys = compat.load(function(name) return assert(loaded[name], name) end)
assert(hd2 == parts[1] and metadata == parts[6] and world == parts[2]
    and beacons == parts[3] and loadout == parts[4] and keys == parts[5].stats.keys)
for _, absent in ipairs(names) do
    local ok, why = compat.load(function(name)
        if name == absent then error('fixture module absent') end
        return assert(loaded[name], name)
    end)
    assert(not ok and tostring(why):find(absent, 1, true), 'import failure loses module name: ' .. absent)
end
print('PASS require failures and unavailable Mod/Store/Overlay methods diagnosed without invoking Runtime methods')
if arg[2] and arg[3] then
    -- Test the real Runtime resolver fingerprint, and the ledger native UI
    -- schema guard. A Runtime version change must never bypass either proof.
    local bridge_path, runtime_root = arg[2], arg[3]
    local event_world = dofile(runtime_root .. '/runtime/event_world.lua')
    local read_calls, hash_calls = 0, 0
    event_world.set_runtime({mode = 'fixture', module = function(name) return name or 'exe' end,
        address = function(handle) return handle == 'exe' and 0x10000000 or 0x20000000 end,
        module_hash = function() hash_calls = hash_calls + 1; return 'wrong-build-sha' end,
        read = function() read_calls = read_calls + 1; error('wrong build cannot read memory') end})
    local world_value, why = event_world.open()
    assert(not world_value and tostring(why):find('unsupported build fingerprint', 1, true)
        and read_calls == 0 and hash_calls == 2, 'Runtime native fingerprint proof was bypassed')
    local bridge = dofile(bridge_path)
    local profile = require('hd2runtime/schemas/current')
    local old_sha = profile.dll_sha; profile.dll_sha = 'other-build'
    local state, reason = bridge.new():poll({game = 0x10000000, view = {
        pointer = function() read_calls = read_calls + 1 end,
        read = function() read_calls = read_calls + 1 end}})
    profile.dll_sha = old_sha
    assert(not state and reason == 'NATIVE_UI_BUILD_MISMATCH' and read_calls == 0,
        'Ledger native UI fingerprint proof was bypassed')
    print('PASS real Runtime event_world and ledger native UI both reject wrong game build before any memory read')
end
