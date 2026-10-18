local capture_path, bridge_path, runtime_path = assert(arg[1]), assert(arg[2]), assert(arg[3])
package.preload['hd2runtime/schemas/current'] = function() return dofile(runtime_path .. '/schemas/current.lua') end
package.preload['hd2runtime/runtime/log'] = function() return {emit = function() end} end
package.preload['hd2runtime/runtime/events'] = function() return {} end
package.preload['hd2runtime/runtime/mod_store'] = function() return dofile(runtime_path .. '/runtime/mod_store.lua') end
local json = require('hd2runtime/runtime/mod_store')
local api, native = dofile(capture_path), dofile(bridge_path)
local files, original_open, tests = {}, io.open, 0
local function check(name, action)
    local ok, why = pcall(action)
    assert(ok, name .. ': ' .. tostring(why))
    tests = tests + 1; print('PASS ' .. name)
end
io.open = function(path, mode)
    if mode == 'rb' then
        if not files[path] then return nil, 'missing' end
        return {close = function() return true end}
    end
    assert(mode == 'wb' and not files[path], 'an existing artifact was overwritten')
    local file = {parts = {}, size = 0, closed = false}
    function file:write(data)
        assert(not self.closed and type(data) == 'string')
        self.parts[#self.parts + 1] = data; self.size = self.size + #data; return self
    end
    function file:close() self.closed = true; return true end
    files[path] = file; return file
end
local sequence = 0
local function fixture()
    sequence = sequence + 1
    local f = {game = 0x10000000, exe = 0x8000000, hud = 0x30000000,
        shown = 1, ready = 1, map = 0, bytes = 0, writes = 0, calls = {}, payload_calls = 0}
    local function raw(at, size)
        f.bytes = f.bytes + size; f.calls[#f.calls + 1] = {at = at, size = size}
        if f.fail and at <= f.fail and f.fail < at + size then return nil end
        if at == f.hud + native.source.mission_hud + native.source.mission_shown and size == 1 then return string.char(f.shown) end
        if at == f.hud + native.source.mission_hud + native.source.mission_ready and size == 1 then return string.char(f.ready) end
        if at == f.hud + native.source.map_open and size == 1 then return string.char(f.map) end
        if at >= f.hud and at + size <= f.hud + api.limits.hud then
            if size > 16 then f.payload_calls = f.payload_calls + 1 end
            return string.rep(at == f.hud and f.head_change and 'Y' or 'H', size)
        end
        for _, window in ipairs(api.code_windows) do
            if at >= f.game + window.rva and at + size <= f.game + window.rva + window.size then
                if size > 16 then f.payload_calls = f.payload_calls + 1 end
                return string.rep('C', size)
            end
        end
        error('capture read outside its explicit UI ranges')
    end
    f.world = {game = f.game, exe = f.exe, view = {
        pointer = function(at)
            f.bytes = f.bytes + 8
            assert(at == f.game + native.source.hud_global, 'only proven HUD root permitted')
            return f.hud
        end,
        read = raw,
        write = function() f.writes = f.writes + 1; error('game writes forbidden') end,
    }, runtime = {query = function(at)
        if at >= f.hud and at < f.hud + api.limits.hud then
            return {base = f.hud, size = api.limits.hud, allocation_base = f.hud,
                state = 0x1000, protect = f.bad_protect and 1 or 4, type = 0x20000}
        end
        return {base = f.game, size = 74727424, allocation_base = f.game,
            state = 0x1000, protect = 0x20, type = 0x1000000}
    end}}
    f.capture = api.new({bridge = native.new(), directory = 'fixture' .. sequence})
    return f
end
local function run(f)
    local steps = 0
    while f.capture.active do
        f.bytes = 0
        local result = assert(f.capture:step(f.world))
        assert(f.bytes <= api.limits.read_per_step, '64KiB per-step budget exceeded: ' .. f.bytes)
        steps = steps + 1; assert(steps <= 100)
    end
    return assert(f.capture.last), steps
end
check('disabled by default; no read, scan, file or game write without start', function()
    local f = fixture(); assert(f.capture.status == 'disabled' and f.bytes == 0)
    assert(f.capture:step(f.world) == nil and f.bytes == 0 and f.writes == 0)
end)
check('actual UI ranges stream once within 64KiB and binary+JSON 8MiB budget', function()
    local f = fixture(); local first = assert(f.capture:start(f.world, 'map closed tasks'))
    assert(f.bytes <= 65536 and f.payload_calls == 0)
    local meta, steps = run(f)
    assert(meta.complete and meta.identity_consistent and meta.boundaries_consistent and not meta.atomic)
    assert(steps > 70 and f.writes == 0 and #meta.ranges == 3)
    assert(meta.bytes_written == 4882432 and meta.bytes_written == meta.bytes_planned)
    assert(files[meta.binary_path].size == meta.bytes_written)
    assert(files[meta.binary_path].size + files[meta.json_path].size < api.limits.output)
    local decoded = json.decode(table.concat(files[meta.json_path].parts))
    assert(decoded.complete and decoded.mode == 'map_closed' and decoded.exe_sha == native.source.exe_sha)
    assert(#decoded.chunks > 70 and decoded.ranges[2].rva == 0x12E8000)
    for _, chunk in ipairs(decoded.chunks) do assert(chunk.success and chunk.requested <= 65280) end
end)
check('map open and closed each save once with separate labels and paths', function()
    local f = fixture(); assert(f.capture:start(f.world)); local closed = run(f)
    local result, why = f.capture:start(f.world); assert(not result and why == 'UI_CAPTURE_MODE_ALREADY_SAVED')
    f.map = 1; assert(f.capture:start(f.world, 'map open tasks')); local opened = run(f)
    assert(opened.mode == 'map_open' and opened.binary_path ~= closed.binary_path)
    assert(f.capture:start(f.world) == nil)
end)
check('failed native read produces partial binary plus incomplete JSON with failed extent', function()
    local f = fixture(); assert(f.capture:start(f.world)); assert(f.capture:step(f.world))
    f.fail = f.hud + api.limits.payload_per_step
    local result = assert(f.capture:step(f.world))
    assert(not result.complete and result.error == 'UI_CAPTURE_READ_FAILED')
    assert(result.bytes_written == 65280 and not result.chunks[#result.chunks].success)
    assert(files[result.binary_path].closed)
    assert(not json.decode(table.concat(files[result.json_path].parts)).complete)
    f.fail = nil; assert(f.capture:start(f.world)); assert(f.capture:cancel())
end)
check('map or world changes cancel identity, never mixed into a complete sample', function()
    local f = fixture(); assert(f.capture:start(f.world)); f.map = 1
    local result = assert(f.capture:step(f.world)); assert(not result.complete and result.error == 'UI_CAPTURE_UI_CHANGED')
    assert(result.bytes_written == 0)
    assert(f.capture:start(f.world)); result = assert(f.capture:step(nil))
    assert(not result.complete and result.error == 'UI_CAPTURE_WORLD_CHANGED')
end)
check('unstable boundary is reported separately from full read and stable UI identity', function()
    local f = fixture(); assert(f.capture:start(f.world)); f.head_change = true
    local meta = run(f); assert(meta.complete and not meta.boundaries_consistent and not meta.atomic)
end)
check('HUD allocation protection or no mission prevents capture startup', function()
    local f = fixture(); f.bad_protect = true; local result, why = f.capture:start(f.world)
    assert(not result and why == 'UI_CAPTURE_HUD_OWNER_UNAVAILABLE' and f.payload_calls == 0)
    f.bad_protect, f.shown = false, 0; result, why = f.capture:start(f.world)
    assert(not result and why == 'UI_CAPTURE_NOT_IN_MISSION')
end)
check('explicit cancellation closes evidence as incomplete without advancing payload', function()
    local f = fixture(); assert(f.capture:start(f.world)); local before = f.bytes
    local meta = assert(f.capture:cancel()); assert(not meta.complete and meta.error == 'UI_CAPTURE_CANCELLED')
    assert(f.bytes == before and files[meta.binary_path].closed)
end)
io.open = original_open
print('UI layout capture tests: ' .. tests .. ' passed; real game task parent still awaits samples.')
