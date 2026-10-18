local module_path, runtime_path = assert(arg[1]), assert(arg[2])
package.preload['hd2runtime/schemas/current'] = function()
    return dofile(runtime_path .. '/schemas/current.lua')
end
local api = dofile(module_path)
local profile = require('hd2runtime/schemas/current')
local tests = 0
local function check(name, action)
    local ok, why = pcall(action)
    assert(ok, name .. ': ' .. tostring(why))
    tests = tests + 1; print('PASS ' .. name)
end
local function fixture()
    local f = {game = 0x10000000, hud = 0x20000000, shown = 1, ready = 1, map = 0, calls = {}, writes = 0}
    local function call(at, size) f.calls[#f.calls + 1] = {at, size} end
    f.world = {game = f.game, view = {
        pointer = function(at)
            call(at, 8)
            assert(at == f.game + api.source.hud_global, 'read outside HUD global')
            return f.hud
        end,
        read = function(at, size)
            call(at, size); assert(size == 1, 'only boolean reads allowed')
            if at == f.fail then return nil end
            if at == f.hud + api.source.mission_hud + api.source.mission_shown then return string.char(f.shown) end
            if at == f.hud + api.source.mission_hud + api.source.mission_ready then return string.char(f.ready) end
            if at == f.hud + api.source.map_open then return string.char(f.map) end
            error('read outside proven UI fields')
        end,
        write = function() f.writes = f.writes + 1; error('no native write permitted') end,
    }}
    return f
end
check('real source route: map open and close, no key state; four reads eleven bytes', function()
    local f, bridge = fixture(), api.new()
    local state = assert(bridge:poll(f.world)); assert(state.mission and not state.map_open)
    local bytes = 0; for _, call in ipairs(f.calls) do bytes = bytes + call[2] end
    assert(#f.calls == 4 and bytes == 11 and f.writes == 0)
    f.map = 1; assert(bridge:poll(f.world).map_open)
    f.map = 0; assert(not bridge:poll(f.world).map_open)
end)
check('native mission gates suppress a leftover map bit outside mission', function()
    local f, bridge = fixture(), api.new(); f.map = 1
    f.shown = 0; local state = assert(bridge:poll(f.world)); assert(not state.mission and not state.map_open)
    f.shown, f.ready = 1, 0; state = assert(bridge:poll(f.world)); assert(not state.map_open)
end)
check('HUD replacement follows the current pointer', function()
    local f, bridge = fixture(), api.new(); assert(bridge:poll(f.world).hud == f.hud)
    f.hud, f.map = f.hud + 0x800000, 1; assert(bridge:poll(f.world).hud == f.hud)
end)
check('lost/invalid boolean clears previously open state', function()
    local f, bridge = fixture(), api.new(); f.map = 1; assert(bridge:poll(f.world).map_open)
    f.fail = f.hud + api.source.map_open
    local state, why = bridge:poll(f.world); assert(not state and why == 'NATIVE_UI_MAP_UNREADABLE')
    assert(bridge.state == nil and bridge.world == nil)
    f.fail, f.map = nil, 2; assert(bridge:poll(f.world) == nil)
end)
check('unreadable mission is unavailable, not a stale map value', function()
    local f, bridge = fixture(), api.new(); f.fail = f.hud + api.source.mission_hud + api.source.mission_ready
    local state, why = bridge:poll(f.world); assert(not state and why == 'NATIVE_UI_MISSION_UNREADABLE')
end)
check('missing/noncanonical HUD or world cannot read native fields', function()
    local f, bridge = fixture(), api.new()
    for _, hud in ipairs({0, 1, 65537, 140737488355328}) do
        f.hud = hud; local state, why = bridge:poll(f.world)
        assert(not state and why == 'NATIVE_UI_HUD_UNAVAILABLE')
    end
    assert(bridge:poll(nil) == nil)
end)
check('different pinned schema rejects every native read', function()
    local f, bridge = fixture(), api.new(); local keep = profile.dll_sha
    profile.dll_sha = 'other_build'; local state, why = bridge:poll(f.world); profile.dll_sha = keep
    assert(not state and why == 'NATIVE_UI_BUILD_MISMATCH' and #f.calls == 0)
end)
check('bridge without the task module does not attempt layout writes', function()
    local f, bridge = fixture(), api.new(); assert(bridge:poll(f.world))
    local ok, why = bridge:reserve({visible = true, reserved_height = 150, task_gap = 12})
    assert(api.source.tasks.list == 0x29B180 and api.source.tasks.focused == 0x38CA10)
    assert(not ok and why == 'TASK_LAYOUT_MODULE_UNAVAILABLE' and f.writes == 0)
    assert(not bridge:restore())
end)
print('Native UI bridge tests: ' .. tests .. ' passed; task movement is exercised in separate real-fixture tests.')
