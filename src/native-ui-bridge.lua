-- Native UI state for the same Steam build as HD2Runtime 0.30.3.
-- Input MUST be the fingerprint/pin-proven world returned by event_world.open().
-- Provenance: installed Enemy Reinforcement HUD 0.5.2, ui_snapshot (527-535)
-- and fast_map (648-652); existing local 2026-10-10 probe/HUD logs show map edges.
local profile = require('hd2runtime/schemas/current')
local M = {source = {
    exe_sha = 'F5FEE03DCFDB2E553A4752C283590950AC13316B376D8196AA556FF0400D5F06',
    dll_sha = '2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E',
    hud_global = 0x346D538, mission_hud = 0x24E340,
    mission_shown = 0x58, mission_ready = 0x21F5B0, map_open = 0x3EF2FD,
    tasks = {list = 0x29B180, focused = 0x38CA10, slots = 16,
        complete_sample_sha256 = 'ee338b1688205b060d545a99659a36005fb3c9d370f52314df3acef92eab9648',
        position_update_verified = true, layout = 0x392328, gap_down = 0x2C},
}}
local Bridge = {}
Bridge.__index = Bridge

local function address(value)
    return type(value) == 'number' and value >= 65536 and value < 140737488355328
        and value % 8 == 0
end
local function byte(world, at)
    local data = world.view.read(at, 1)
    if type(data) ~= 'string' or #data ~= 1 then return nil end
    local value = data:byte()
    if value == 0 or value == 1 then return value end
end
local function unavailable(self, reason)
    self.world, self.state = nil, nil
    self.status = reason
    return nil, reason
end

function M.new(options)
    options=options or {}
    local task=options.task_module and options.task_module.new({log=options.log,place_factory=options.place_factory})
    return setmetatable({source = M.source, task=task, status = 'WAITING_FOR_NATIVE_UI',
        task_status = 'WAITING_FOR_TASK_LAYOUT'}, Bridge)
end

-- At most four reads / eleven bytes; no scan, native call or write.
-- A lost read invalidates the sample instead of retaining a stale open-map state.
function Bridge:poll(world)
    if profile.exe_sha ~= M.source.exe_sha or profile.dll_sha ~= M.source.dll_sha then
        return unavailable(self, 'NATIVE_UI_BUILD_MISMATCH')
    end
    if type(world) ~= 'table' or not address(world.game) or type(world.view) ~= 'table'
        or type(world.view.pointer) ~= 'function' or type(world.view.read) ~= 'function' then
        return unavailable(self, 'NATIVE_UI_WORLD_UNAVAILABLE')
    end
    local hud = world.view.pointer(world.game + M.source.hud_global)
    if not address(hud) then return unavailable(self, 'NATIVE_UI_HUD_UNAVAILABLE') end
    local shown = byte(world, hud + M.source.mission_hud + M.source.mission_shown)
    local ready = byte(world, hud + M.source.mission_hud + M.source.mission_ready)
    if shown == nil or ready == nil then return unavailable(self, 'NATIVE_UI_MISSION_UNREADABLE') end
    local mission = shown == 1 and ready == 1
    local map = byte(world, hud + M.source.map_open)
    if map == nil then return unavailable(self, 'NATIVE_UI_MAP_UNREADABLE') end
    self.world, self.status = world, 'NATIVE_UI_READ'
    self.state = {mission = mission, map_open = mission and map == 1, hud = hud}
    return self.state
end

function Bridge:reserve(options)
    if type(options) ~= 'table' then return nil, 'NATIVE_UI_INVALID_RESERVATION' end
    if not self.task then self.task_status='TASK_LAYOUT_MODULE_UNAVAILABLE';return nil,self.task_status end
    local ok,why=self.task:reserve(self.world,self.state,options)
    self.task_status=why
    return ok,why
end
function Bridge:restore()
    return self:reserve({visible=false})
end

return M
