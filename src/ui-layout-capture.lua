-- Explicit, bounded UI evidence capture. Never enabled or started automatically.
-- Reads at most 64 KiB per step; its binary plus metadata is capped at 8 MiB.
-- No process dump, target scan, game call, memory write or task-node guess.
local json = require('hd2runtime/runtime/mod_store')
local M = {limits = {read_per_step = 65536, payload_per_step = 65280,
    output = 8388608, hud = 0x480000},
    code_windows = {{name = 'mission_hud_code', rva = 0x12E8000, size = 0x10000},
        {name = 'widget_layout_code', rva = 0x143A000, size = 0x18000}}}
local Capture = {}
Capture.__index = Capture

local function hex(bytes)
    return bytes and (bytes:gsub('.', function(c) return string.format('%02X', c:byte()) end)) or nil
end
local function sample(state)
    return state and {hud = state.hud, mission = state.mission, map_open = state.map_open} or nil
end
local function region(world, at)
    local runtime = type(world) == 'table' and world.runtime
    if type(runtime) ~= 'table' or type(runtime.query) ~= 'function' then return nil end
    local r = runtime.query(at)
    if not r or type(r.base) ~= 'number' or type(r.size) ~= 'number' or r.size <= 0
        or r.base > at or r.base + r.size <= at or r.state ~= 0x1000
        or r.protect == 0 or r.protect % 512 >= 256 then return nil end
    return r
end
local function exists(path)
    local f = io.open(path, 'rb')
    if f then f:close(); return true end
    return false
end
local function read(world, at, length)
    local bytes = world.view.read(at, length)
    if type(bytes) ~= 'string' or #bytes ~= length then return nil end
    return bytes
end
local function boundaries(world, hud)
    -- Small sentinels document (not prove) whether the object's ends stayed still.
    return {head = hex(read(world, hud, 16)),
        tail = hex(read(world, hud + M.limits.hud - 16, 16))}
end

function M.new(options)
    options = options or {}
    local directory = options.directory
    if not directory then
        local base = os.getenv('LOCALAPPDATA')
        directory = base and (base .. '/HD2Runtime/mod_data')
    end
    return setmetatable({bridge = options.bridge, directory = directory,
        log = options.log or function() end, status = 'disabled', captured = {}, sequence = 0}, Capture)
end

function Capture:_finish(world, reason)
    local active = self.active
    if not active then return nil, 'UI_CAPTURE_NOT_RUNNING' end
    local meta = active.meta
    if world and world.game == meta.game_base then
        local ui = self.bridge:poll(world)
        meta.end_state = sample(ui)
        if ui and ui.hud == meta.hud then meta.end_boundaries = boundaries(world, meta.hud) end
    end
    meta.identity_consistent = meta.end_state ~= nil and meta.start_state.hud == meta.end_state.hud
        and meta.start_state.mission == meta.end_state.mission
        and meta.start_state.map_open == meta.end_state.map_open
    local last = meta.end_boundaries or {}
    meta.boundaries_consistent = meta.start_boundaries.head ~= nil and meta.start_boundaries.tail ~= nil
        and meta.start_boundaries.head == last.head and meta.start_boundaries.tail == last.tail
    meta.complete = reason == nil and meta.bytes_written == meta.bytes_planned and meta.identity_consistent
    meta.error = reason or (not meta.complete and 'UI_CAPTURE_FINAL_STATE_CHANGED' or nil)
    meta.finished_at = os.time()
    local closed, close_error = active.file:close()
    if not closed then meta.complete, meta.error = false, 'UI_CAPTURE_BINARY_CLOSE:' .. tostring(close_error) end
    local encoded = json.encode(meta)
    if meta.bytes_written + #encoded > M.limits.output then
        meta.complete, meta.error = false, 'UI_CAPTURE_OUTPUT_LIMIT'
        encoded = json.encode(meta)
    end
    local sidecar, sidecar_error = io.open(meta.json_path, 'wb')
    if sidecar then
        local written, why = sidecar:write(encoded)
        local finished = sidecar:close()
        if not written or not finished then meta.complete, meta.error = false, 'UI_CAPTURE_METADATA_WRITE:' .. tostring(why) end
    else meta.complete, meta.error = false, 'UI_CAPTURE_METADATA_OPEN:' .. tostring(sidecar_error) end
    self.active, self.last = nil, meta
    self.status = meta.complete and 'complete' or 'incomplete'
    if meta.complete then self.captured[meta.mode] = true end
    self.log('UI定位采集 ' .. self.status .. '：' .. meta.json_path)
    return meta
end

function Capture:start(world, label)
    if self.active then return nil, 'UI_CAPTURE_ALREADY_RUNNING' end
    if not self.bridge or type(self.bridge.poll) ~= 'function' then return nil, 'UI_CAPTURE_BRIDGE_UNAVAILABLE' end
    if not self.directory then return nil, 'UI_CAPTURE_DIRECTORY_UNAVAILABLE' end
    if label ~= nil and (type(label) ~= 'string' or #label > 160) then return nil, 'UI_CAPTURE_INVALID_LABEL' end
    local ui, why = self.bridge:poll(world)
    if not ui then return nil, why end
    if not ui.mission then return nil, 'UI_CAPTURE_NOT_IN_MISSION' end
    local mode = ui.map_open and 'map_open' or 'map_closed'
    if self.captured[mode] then return nil, 'UI_CAPTURE_MODE_ALREADY_SAVED' end
    local owner = region(world, ui.hud)
    if not owner or owner.type ~= 0x20000 or owner.protect ~= 4 then return nil, 'UI_CAPTURE_HUD_OWNER_UNAVAILABLE' end
    local first = boundaries(world, ui.hud)
    local stem
    for i = 1, 100 do
        self.sequence = self.sequence + 1
        local name = 'ledger_ui_' .. os.date('!%Y%m%dT%H%M%SZ') .. '_' .. mode .. '_' .. tostring(self.sequence)
        local candidate = self.directory .. '/' .. name
        if not exists(candidate .. '.bin') and not exists(candidate .. '.json') then stem = candidate; break end
    end
    if not stem then return nil, 'UI_CAPTURE_NAME_UNAVAILABLE' end
    local file, open_error = io.open(stem .. '.bin', 'wb')
    if not file then return nil, 'UI_CAPTURE_BINARY_OPEN:' .. tostring(open_error) end
    local source = self.bridge.source
    local meta = {format = 'HD2-UI-LAYOUT-1', build = 25480438,
        exe_sha = source and source.exe_sha,
        dll_sha = source and source.dll_sha,
        label = label or mode, mode = mode, started_at = os.time(),
        game_base = world.game, exe_base = world.exe, hud = ui.hud,
        hud_owner = {allocation_base = owner.allocation_base, base = owner.base, size = owner.size,
            type = owner.type, protect = owner.protect},
        start_state = sample(ui), start_boundaries = first, complete = false,
        atomic = false, read_budget = M.limits.read_per_step, output_limit = M.limits.output,
        binary_path = stem .. '.bin', json_path = stem .. '.json', bytes_written = 0,
        bytes_planned = M.limits.hud, ranges = {}, chunks = {}}
    meta.ranges[1] = {name = 'hud_object', base = ui.hud, length = M.limits.hud,
        binary_offset = 0, allocation_base = owner.allocation_base}
    local offset = M.limits.hud
    for _, window in ipairs(M.code_windows) do
        meta.ranges[#meta.ranges + 1] = {name = window.name, base = world.game + window.rva,
            rva = window.rva, length = window.size, binary_offset = offset}
        offset = offset + window.size
    end
    meta.bytes_planned = offset
    assert(meta.bytes_planned + 131072 <= M.limits.output, 'UI capture exceeds output ceiling')
    self.active = {file = file, meta = meta, range = 1, offset = 0}
    self.status = 'capturing'
    self.log('UI定位采集开始：' .. mode .. '；每次≤64KiB，输出 ' .. meta.binary_path)
    return meta
end

function Capture:step(world)
    local active = self.active
    if not active then return nil, 'UI_CAPTURE_NOT_RUNNING' end
    local meta = active.meta
    if type(world) ~= 'table' or world.game ~= meta.game_base or world.exe ~= meta.exe_base then
        return self:_finish(nil, 'UI_CAPTURE_WORLD_CHANGED')
    end
    local ui, why = self.bridge:poll(world)
    if not ui or ui.hud ~= meta.hud or not ui.mission or ui.map_open ~= meta.start_state.map_open then
        return self:_finish(world, why or 'UI_CAPTURE_UI_CHANGED')
    end
    local range = meta.ranges[active.range]
    if not range then return self:_finish(world) end
    local at = range.base + active.offset
    local mapped = region(world, at)
    if not mapped or (range.name == 'hud_object' and
        (mapped.allocation_base ~= range.allocation_base or mapped.type ~= 0x20000 or mapped.protect ~= 4)) then
        meta.chunks[#meta.chunks + 1] = {range = range.name, address = at, requested = 0,
            success = false, error = 'UI_CAPTURE_REGION_CHANGED'}
        return self:_finish(world, 'UI_CAPTURE_REGION_CHANGED')
    end
    local length = math.min(M.limits.payload_per_step, range.length - active.offset, mapped.base + mapped.size - at)
    local data = read(world, at, length)
    local chunk = {range = range.name, address = at, requested = length,
        binary_offset = meta.bytes_written, success = data ~= nil, length = data and #data or 0,
        region = {base = mapped.base, size = mapped.size, protect = mapped.protect, type = mapped.type}}
    meta.chunks[#meta.chunks + 1] = chunk
    if not data then return self:_finish(world, 'UI_CAPTURE_READ_FAILED') end
    local wrote, write_error = active.file:write(data)
    if not wrote then return self:_finish(world, 'UI_CAPTURE_BINARY_WRITE:' .. tostring(write_error)) end
    meta.bytes_written = meta.bytes_written + #data
    active.offset = active.offset + length
    if active.offset == range.length then active.range, active.offset = active.range + 1, 0 end
    if active.range > #meta.ranges then return self:_finish(world) end
    return meta
end

function Capture:cancel()
    if not self.active then return true end
    return self:_finish(nil, 'UI_CAPTURE_CANCELLED')
end

return M
