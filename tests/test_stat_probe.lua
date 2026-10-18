-- Exercise the real probe module with real JSON/files, a bounded synthetic reader, and no game process.
local probe_path, runtime, temp = assert(arg[1]), assert(arg[2]), assert(arg[3])
package.preload['hd2runtime/runtime/log'] = function() return {emit = function() end} end
package.preload['hd2runtime/runtime/events'] = function() return {} end
package.preload['hd2runtime/runtime/windows_readonly'] = function() return function() return {} end end
package.preload['hd2runtime/runtime/mod_store'] = function() return dofile(runtime .. '/runtime/mod_store.lua') end
local json = require('hd2runtime/runtime/mod_store')
local create = dofile(probe_path)
local getenv = os.getenv
os.getenv = function(name) if name == 'LOCALAPPDATA' then return temp end; return getenv(name) end
local folder = temp .. '/HD2Runtime/mod_data/'
local request_path = folder .. 'ledger_probe_request.json'
local opened, loaded, snapshots, code_reads, raw_reads = 0, 0, 0, 0, 0
local open = io.open
io.open = function(...) opened = opened + 1; return open(...) end
local enabled, logs = false, {}
local store = {get = function(_, _, default) return enabled or default end}
local mod = {log = function(_, text) logs[#logs + 1] = text end}
local reason
local b = dofile(runtime .. '/core/bytes.lua')
local raw_data = {capacity = 8, empty = 4294967295, score_index = 0,
    main_bytes = b.encode(123, 'u32') .. b.encode(-17, 'i32') .. b.encode(37.5, 'f32')
        .. string.char(7) .. string.rep('\0', 7) .. string.rep(b.encode(4294967295, 'u32') .. string.rep('\0', 16), 7),
    sources_bytes = string.rep('\0', 64 * 328)}
local loader = function()
    loaded = loaded + 1
    return {snapshot = function(_, entity)
        assert(entity == 42); snapshots = snapshots + 1
        if reason then return nil, reason end
        return {main = {{key = 123, i32 = 0, f32 = 37.5, bool = false}}, sources = {}}
    end, raw = function(_, entity)
        assert(entity == 42); raw_reads = raw_reads + 1
        if reason then return nil, reason end
        return raw_data
    end}
end
local unreadable_code = false
local world = {game = 0x100000, view = {slot = function() return {} end,
    read = function(address, size)
        code_reads = code_reads + 1
        if unreadable_code and address == 0x100000 + 0x630130 then return nil end
        return string.rep('a', size)
    end}}
local position_reads, avatar_reads, available_avatar = 0, 0, true
package.preload['hd2runtime/runtime/event_world'] = function()
    return {players = function(_, with_avatars)
        assert(with_avatars == true); avatar_reads = avatar_reads + 1
        return {{entity = 42, ['local'] = true, lifecycle = 3, avatar = available_avatar and 1234 or nil}}
    end, unit_position = function(_, avatar)
        assert(avatar == 1234); position_reads = position_reads + 1
        return {x = 12.5, y = -17, z = 100}
    end}
end
local players, game = {{entity = 42, ['local'] = true, lifecycle = 2}},
    {mission = true, state = 4, mode = 'Mission', host = false}
local probe = create(mod, store, loader)
for i = 1, 600 do probe:poll(world, players, game, 1/60) end
assert(opened == 0 and loaded == 0 and snapshots == 0, 'disabled probe must perform no IO/native reads')
enabled = true; probe = create(mod, store, loader)
for i = 1, 60 do probe:poll(world, players, game, 1/60) end
assert(opened == 1 and snapshots == 0, 'enabled idle probe checks at most once per second')
local function request(id, label, include_code, format)
    local f = assert(open(request_path, 'wb'))
    f:write(json.encode({id = id, label = label, include_code = include_code, format = format})); f:close()
end
local id = string.rep('1', 32)
request(id, 'baseline', true)
probe:poll(world, players, game, 1)
assert(snapshots == 1 and loaded == 1 and code_reads == 2)
assert(avatar_reads == 0 and position_reads == 0, 'legacy JSON did not request position capture')
local result_path = folder .. 'ledger_probe_' .. id .. '.json'
local f = assert(open(result_path, 'rb')); local result = json.decode(f:read('*a')); f:close()
assert(result.stats.main[1].f32 == 37.5 and result.label == 'baseline')
assert(result.code[1].size == 0x7C0 and #result.code[1].hex == 0x7C0 * 2)
assert(not open(request_path, 'rb'), 'command consumed after capture')
-- A repeated request cannot overwrite a result or trigger another expensive snapshot.
request(id, 'duplicate', false); probe:poll(world, players, game, 1); assert(snapshots == 1)
request('../outside', 'invalid', false); probe:poll(world, players, game, 1); assert(snapshots == 1)
reason = 'bounded test failure'
local second = string.rep('2', 32)
request(second, 'failed', false); probe:poll(world, players, game, 1)
f = assert(open(folder .. 'ledger_probe_' .. second .. '.json', 'rb'))
result = json.decode(f:read('*a')); f:close()
assert(result.error == reason and result.stats == nil and loaded == 1)
reason = nil
local function binary_capture(id, code)
    request(id, 'binary\0label', code, 'binary'); probe:poll(world, players, game, 1)
    local file = assert(open(folder .. 'ledger_probe_' .. id .. '.bin', 'rb'))
    local body = file:read('*a'); assert(file:close())
    assert(body:sub(1, 8) == 'HD2STAT1')
    local lengths, parts, offset = {}, {}, 28
    for i = 1, 5 do lengths[i] = b.u32(body, 8 + (i - 1) * 4) end
    for i = 1, 5 do parts[i] = body:sub(offset + 1, offset + lengths[i]); offset = offset + lengths[i] end
    assert(offset == #body and #body <= 1048576)
    local metadata = json.decode(parts[1])
    assert(metadata.version == '0.3.3' and metadata.id == id and metadata.label == 'binary\0label')
    assert(metadata.capacity == 8 and metadata.empty == 4294967295 and metadata.score_index == 0)
    assert(metadata.player_entity == 42 and metadata.stats == nil)
    assert(parts[2] == raw_data.main_bytes and parts[3] == raw_data.sources_bytes)
    assert(not open(request_path, 'rb'))
    return metadata, lengths, parts
end
local third = string.rep('3', 32)
local metadata, lengths, parts = binary_capture(third, true)
assert(raw_reads == 1 and snapshots == 2 and code_reads == 4)
assert(lengths[4] == 0x7C0 and lengths[5] == 0x50E)
assert(parts[4] == string.rep('a', 0x7C0) and metadata.code_ranges[2].rva == 0xBF9810)
assert(metadata.code_ranges[1].error == nil)
assert(metadata.game_state == 4 and metadata.game_mode == 'Mission' and metadata.host == false)
assert(metadata.player_lifecycle == 3 and metadata.avatar == 1234)
assert(metadata.position.x == 12.5 and metadata.position.y == -17 and position_reads == 1 and avatar_reads == 1)
request(third, 'duplicate-bin', false, 'binary'); probe:poll(world, players, game, 1)
assert(raw_reads == 1, 'existing bin must block all repeat captures')
request(id, 'duplicate-json', false, 'binary'); probe:poll(world, players, game, 1)
assert(raw_reads == 1, 'converted/original JSON must block repeat binary captures')
unreadable_code = true
metadata, lengths = binary_capture(string.rep('4', 32), true)
assert(lengths[4] == 0 and lengths[5] == 0x50E and metadata.code_ranges[1].error == 'unreadable')
available_avatar = false
metadata, lengths = binary_capture(string.rep('5', 32), false)
assert(lengths[4] == 0 and lengths[5] == 0 and metadata.code_ranges == nil)
assert(metadata.avatar == nil and metadata.position == nil and metadata.player_lifecycle == 3)
assert(position_reads == 2 and avatar_reads == 3, 'position is attempted only on an explicit binary capture')
reason = 'binary unavailable'
local failed = string.rep('6', 32)
request(failed, 'failed-binary', false, 'binary'); probe:poll(world, players, game, 1)
f = assert(open(folder .. 'ledger_probe_' .. failed .. '.json', 'rb'))
result = json.decode(f:read('*a')); assert(f:close())
assert(result.error == reason and result.stats == nil and not open(folder .. 'ledger_probe_' .. failed .. '.bin', 'rb'))
local before = raw_reads
request(string.rep('7', 32), 'invalid-format', false, 'other'); probe:poll(world, players, game, 1)
assert(raw_reads == before and not open(request_path, 'rb'))
print('PASS: probe disabled zero IO, idle 1Hz, JSON compatibility, bounded binary buffers, real file roundtrip, code unreadable metadata, bin/JSON duplicate rejection, explicit failure JSON.')
