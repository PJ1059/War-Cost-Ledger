-- Manual, read-only research material collector, NOT a successful-status counter.
-- Target active/instigator/timer layout remains unproven. Never emits effective/ended.
-- Requires the verified world from HD2Runtime 0.30.3 event_world.open(). No hooks.
local DLL_SHA = '2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E'
local WINDOWS = {
    {label = 'receive_condition_candidate', rva = 0x6994F0, size = 0x950},
    {label = 'apply_buildup_and_refresh_candidate', rva = 0x699E40, size = 0x1080},
    {label = 'unknown_status_callee', rva = 0x69AEC0, size = 0x330},
    {label = 'has_status_query_candidate', rva = 0x69B1F0, size = 0x700},
    {label = 'queue_request_and_target_lookup', rva = 0x129F170, size = 0x130},
    {label = 'request_router_and_instigator_arguments', rva = 0x129F2A0, size = 0x300},
}
local function u32(bytes, offset)
    local a, b, c, d = bytes:byte(offset + 1, offset + 4)
    return a + b * 256 + c * 65536 + d * 16777216
end
local function hex(bytes)
    return (bytes:gsub('.', function(c) return string.format('%02x', c:byte()) end))
end
local function pointer(value)
    return type(value) == 'number' and value >= 65536 and value < 140737488355328 and value % 1 == 0
end
local function identity(id)
    if type(id) ~= 'number' or id <= 0 or id >= 4294967296 or id % 1 ~= 0 then return nil end
    -- Exact engine identity convention proved in research_event_state.py / entity_exists.
    return {id = id, index = id % 4194304, generation = math.floor(id / 4194304) % 256}
end

return function(world_api, natives)
    local source, status = natives and natives.source, natives and natives.status
    local profile_ok = source and source.gameDllSha256 == DLL_SHA and source.imageSize == 0x4744000
        and status and status.manager == 0x3326620 and status.rva == 0x129F170
        and type(status.prologue) == 'string' and #status.prologue > 0
    local api = {version = 1, layout_ready = false, success_count_available = false,
        enabled_by_default = false, capture_kind = 'manual_status_layout_material',
        max_targets = 8, code_window_count = #WINDOWS, code_bytes = 10288,
        manager_header_bytes = 512, identity = identity}
    function api:capture(world, request)
        if type(request) ~= 'table' or request.manual ~= true then return nil, 'MANUAL_CAPTURE_ONLY' end
        if not profile_ok then return nil, 'STATUS_BUILD_PROFILE_UNPROVEN' end
        if type(world) ~= 'table' or not pointer(world.game) or type(world.view) ~= 'table'
            or type(world.view.read) ~= 'function' or type(world.view.pointer) ~= 'function'
            or type(world.view.proves) ~= 'function' then return nil, 'VERIFIED_WORLD_REQUIRED' end
        local targets = request.targets or {}
        if type(targets) ~= 'table' or #targets > self.max_targets then return nil, 'TARGET_LIMIT' end
        local descriptor = natives.health and natives.health.descriptor
        if #targets > 0 and (not descriptor or descriptor.size ~= 24 or descriptor.entity ~= 8
            or descriptor.unit ~= 12 or descriptor.goid ~= 16 or descriptor.type ~= 0
            or type(world_api.entity_exists) ~= 'function') then return nil, 'ENTITY_IDENTITY_CHAIN_UNPROVEN' end
        for _, target in ipairs(targets) do
            if type(target) ~= 'table' or not identity(target.entity) or not pointer(target.pointer) then
                return nil, 'INVALID_TARGET_DESCRIPTOR'
            end
        end
        if not world.view.proves(world.game + status.rva, status.prologue) then
            return nil, 'STATUS_REQUEST_CODE_CHANGED'
        end
        local manager = world.view.pointer(world.game + status.manager)
        if not pointer(manager) then return nil, 'STATUS_MANAGER_UNAVAILABLE' end
        local report = {schema = 1, purpose = self.capture_kind, layout_ready = false,
            success_count_available = false, atomic = false, game_dll_sha256 = DLL_SHA,
            game_base = world.game, code_windows = {}, targets = {},
            manager = {pointer = manager, bytes = self.manager_header_bytes, interpreted = false}}
        for _, window in ipairs(WINDOWS) do
            local bytes = world.view.read(world.game + window.rva, window.size)
            if type(bytes) ~= 'string' or #bytes ~= window.size then
                return nil, 'STATUS_CODE_WINDOW_UNREADABLE:' .. window.label
            end
            report.code_windows[#report.code_windows + 1] = {label = window.label,
                rva = window.rva, bytes = window.size, hex = hex(bytes), exact_function_extent = false}
        end
        local header = world.view.read(manager, self.manager_header_bytes)
        if type(header) ~= 'string' or #header ~= self.manager_header_bytes then
            return nil, 'STATUS_MANAGER_HEADER_UNREADABLE'
        end
        report.manager.hex = hex(header)
        for _, target in ipairs(targets) do
            if world_api.entity_exists(world, target.entity) ~= true then
                return nil, 'TARGET_IDENTITY_UNREADABLE_OR_STALE'
            end
            local bytes = world.view.read(target.pointer, descriptor.size)
            if type(bytes) ~= 'string' or #bytes ~= descriptor.size or u32(bytes, descriptor.entity) ~= target.entity
                or world_api.entity_exists(world, target.entity) ~= true then
                return nil, 'TARGET_DESCRIPTOR_CHANGED'
            end
            local record = identity(target.entity)
            record.type = string.format('%08X%08X', u32(bytes, 4), u32(bytes, 0))
            record.unit, record.goid = u32(bytes, descriptor.unit), u32(bytes, descriptor.goid)
            record.descriptor_pointer, record.descriptor_hex = target.pointer, hex(bytes)
            record.status_active_verified = false
            report.targets[#report.targets + 1] = record
        end
        -- No queue entries, whole-world scans, native calls, writes or derived counts.
        return report
    end
    return api
end
