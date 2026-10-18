-- Synthetic bounded-read tests only; this does not prove a live status layout.
local create = dofile(assert(arg[1], 'native-status-reader.lua required'))
local runtime = assert(arg[2], 'pinned Runtime source directory required')
package.path = runtime .. '/?.lua;' .. package.path
local natives = dofile(runtime .. '/domains/event_natives.lua')
local calls, bytes_read, native_calls, writes = 0, 0, 0, 0
local game, manager, target_pointer = 0x180000000, 0x200000000, 0x210000000
local entity = 7 * 4194304 + 1234
local fail_code, stale, bad_descriptor, generation_checks = false, false, false, 0
local function pack32(value)
    local result = {}
    for i = 1, 4 do result[i] = string.char(value % 256); value = math.floor(value / 256) end
    return table.concat(result)
end
local descriptor = pack32(0x12345678) .. pack32(0x89ABCDEF) .. pack32(entity) .. pack32(44) .. pack32(55) .. pack32(1)
local view = {}
function view.proves(address, expected)
    calls = calls + 1; bytes_read = bytes_read + #expected / 2
    assert(address == game + 0x129F170 and expected == natives.status.prologue)
    return not fail_code
end
function view.pointer(address)
    calls = calls + 1; bytes_read = bytes_read + 8
    assert(address == game + 0x3326620)
    return manager
end
function view.read(address, size)
    calls = calls + 1; bytes_read = bytes_read + size
    if address == target_pointer then
        assert(size == 24)
        return bad_descriptor and descriptor:sub(1, 8) .. pack32(entity + 1) .. descriptor:sub(13) or descriptor
    end
    if address == manager then assert(size == 512); return string.rep('\0', size) end
    assert(size <= 4224 and address >= game + 0x6994F0 and address < game + 0x12A0000)
    return string.rep(string.char(144), size)
end
local world = {game = game, view = view}
local world_api = {entity_exists = function(w, id)
    generation_checks = generation_checks + 1
    assert(w == world and id == entity)
    return not stale
end, native_status = function() native_calls = native_calls + 1 end,
    write = function() writes = writes + 1 end}
local reader = create(world_api, natives)
assert(calls == 0 and not reader.enabled_by_default and not reader.layout_ready and not reader.success_count_available)
local value, why = reader:capture(world, {})
assert(value == nil and why == 'MANUAL_CAPTURE_ONLY' and calls == 0)
assert(reader.identity(entity).index == 1234 and reader.identity(entity).generation == 7)
assert(reader.identity(255 * 4194304 + 42).generation == 255)
assert(reader.identity(256 * 4194304 + 42).generation == 0, 'generation is an eight-bit value, not an unbounded lifetime ID')
for _, invalid in ipairs({0, -1, 1.5, 4294967296, '123'}) do assert(reader.identity(invalid) == nil) end
local too_many = {}
for i = 1, 9 do too_many[i] = {entity = entity, pointer = target_pointer} end
value, why = reader:capture(world, {manual = true, targets = too_many})
assert(value == nil and why == 'TARGET_LIMIT' and calls == 0)
value, why = reader:capture(world, {manual = true, targets = {{entity = entity, pointer = 1}}})
assert(value == nil and why == 'INVALID_TARGET_DESCRIPTOR' and calls == 0)
fail_code = true
value, why = reader:capture(world, {manual = true})
assert(value == nil and why == 'STATUS_REQUEST_CODE_CHANGED' and calls == 1)
fail_code, calls, bytes_read = false, 0, 0
local captured = assert(reader:capture(world, {manual = true, targets = {{entity = entity, pointer = target_pointer}}}))
assert(calls == 10 and bytes_read == 10288 + 512 + 24 + 8 + #natives.status.prologue / 2)
assert(#captured.code_windows == 6 and #captured.targets == 1 and generation_checks == 2)
assert(captured.atomic == false and captured.layout_ready == false and captured.success_count_available == false)
assert(captured.events == nil and captured.cumulative == nil and captured.statuses == nil,
    'raw research capture must never masquerade as effective status events')
local target = captured.targets[1]
assert(target.id == entity and target.index == 1234 and target.generation == 7)
assert(target.type == '89ABCDEF12345678' and target.goid == 55 and target.goid ~= target.generation)
assert(target.status_active_verified == false and captured.manager.interpreted == false)
local sum = 0
for _, window in ipairs(captured.code_windows) do
    sum = sum + window.bytes
    assert(#window.hex == window.bytes * 2 and window.exact_function_extent == false)
end
assert(sum == reader.code_bytes and #captured.manager.hex == 1024)
stale = true
value, why = reader:capture(world, {manual = true, targets = {{entity = entity, pointer = target_pointer}}})
assert(value == nil and why == 'TARGET_IDENTITY_UNREADABLE_OR_STALE')
stale, bad_descriptor = false, true
value, why = reader:capture(world, {manual = true, targets = {{entity = entity, pointer = target_pointer}}})
assert(value == nil and why == 'TARGET_DESCRIPTOR_CHANGED')
assert(native_calls == 0 and writes == 0 and reader.layout_ready == false)
print('PASS: synthetic manual-only status research capture; bounded six code windows/512-byte header/eight targets, exact engine generation identity, stale descriptor rejection, no native calls/writes/counts. Live target active/instigator layout is NOT verified.')
