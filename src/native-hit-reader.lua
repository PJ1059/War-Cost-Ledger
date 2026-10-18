-- Read-only native damage-queue samples for interface research, NOT hit counts.
-- The 0x70 queue record omits effective AP, its selected angle lane and the
-- armour comparison. It must never be passed to hit-feedback.accept() as a
-- verified direct contact. See docs/native-hit-reader-research.md.
local M = {}
M.source = {
    commit = 'dcd996daca2573443956c07252c55c2d86dd0320',
    exe_sha256 = 'F5FEE03DCFDB2E553A4752C283590950AC13316B376D8196AA556FF0400D5F06',
    game_sha256 = '2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E',
}
M.layout = {system_global = 0x347CF38, queue = 0x1120, queue_count = 0x201120,
    stride = 0x70, capacity = 4096, local_user_global = 0x347CEF0,
    local_peer = 0xB398, default_limit = 16, max_limit = 64}
-- Exact upstream instruction pins, not guesses from an on-disk packed image.
-- runtime/event_world.open() separately validates the build and public pins.
M.pins = {
    {0x129DD77, '4c8b35baf11d02'}, -- producer: damage system global
    {0x129E41D, '81f900100000'}, -- producer: queue capacity 4096
    {0x129E430, '4c6be970'}, -- producer: entry stride 0x70
    {0x129E440, '4389842e20110000'}, -- target entity -> queue +0
    {0x129E44B, '4389842e24110000'}, -- source kind -> queue +4
    {0x129E457, '4389842e28110000'}, -- element -> queue +8
    {0x129E472, '4389842e30110000'}, -- dealer GOID -> queue +0x10
    {0x129E481, '4389842e34110000'}, -- owner GOID -> queue +0x14
    {0x129E490, '4b89842e38110000'}, -- creditor -> queue +0x18
    {0x129E49C, '4389842e40110000'}, -- unknown key -> queue +0x20
    {0x129E4B9, '4389842e4c110000'}, -- damage -> queue +0x2C
    {0x129E4F9, '4389842e60110000'}, -- unknown hit member -> queue +0x60
    {0x12A6F17, '8b8120112000'}, -- drain: queue count
    {0x12A6FA8, '4883c770'}, -- drain: entry stride
    {0x12A8751, '483b8898b30000'}, -- creditor == local user's peer
}

local L = M.layout
local function uint(n)
    return type(n) == 'number' and n >= 0 and n < 4294967296 and n % 1 == 0
end
local function finite(n)
    return type(n) == 'number' and n == n and n > -math.huge and n < math.huge
end
local function block_float(block, at)
    -- The string fallback's bytes.value throws for NaN/Inf, while the FFI
    -- block returns a float. Reject either representation before decoding.
    if math.floor(block:u32(at) / 8388608) % 256 == 255 then return nil end
    local value = block:f32(at)
    return finite(value) and value or nil
end

-- The returned object and its slots are reused. Consume/copy before the next
-- sample. Iterate 1..sampled_count, never #records. No scheduler is installed.
function M.create(world_api, native_schema)
    world_api = world_api or require('hd2runtime/runtime/event_world')
    native_schema = native_schema or require('hd2runtime/domains/event_natives')
    local cached_world, block
    local out = {kind = 'damage_queue_sample', records = {}, sampled_count = 0,
        observed_queue_count = 0, truncated = false, classification_verified = false,
        complete_stream = false}
    for i = 1, L.max_limit do
        out.records[i] = {verified = false, direct = nil, result = nil}
    end
    local api = {}
    local function prove(world)
        local source = native_schema.source or {}
        -- event_natives names gameDllSha256; event_world.open() proves both
        -- disk fingerprints. That schema does not have an exeSha256 field.
        if source.gameDllSha256 ~= M.source.game_sha256 then
            return nil, 'BUILD_PROFILE_MISMATCH'
        end
        if cached_world == world then return true end
        for _, pin in ipairs(M.pins) do
            if not world.view.proves(world.game + pin[1], pin[2]) then
                return nil, 'NATIVE_CODE_MISMATCH_' .. string.format('%X', pin[1])
            end
        end
        block = world.view.slot()
        cached_world = world
        return true
    end
    function api.sample(limit)
        out.sampled_count, out.observed_queue_count, out.truncated = 0, 0, false
        limit = limit or L.default_limit
        if not uint(limit) or limit < 1 or limit > L.max_limit then return nil, 'INVALID_LIMIT' end
        local world, why = world_api.open()
        if not world then return nil, why or 'WORLD_UNAVAILABLE' end
        local ok
        ok, why = prove(world)
        if not ok then return nil, why end
        local view, game = world.view, world.game
        -- Addresses never survive a sample: managers may disappear or change.
        local system = view.pointer(game + L.system_global)
        local user = view.pointer(game + L.local_user_global)
        if not system or not user then return nil, 'MANAGER_UNREADABLE' end
        local count = view.u32(system + L.queue_count)
        if not uint(count) or count > L.capacity then return nil, 'QUEUE_COUNT_INVALID' end
        local peer_lo, peer_hi = view.u32(user + L.local_peer), view.u32(user + L.local_peer + 4)
        if not uint(peer_lo) or not uint(peer_hi) or (peer_lo == 0 and peer_hi == 0) then
            return nil, 'LOCAL_PEER_UNREADABLE'
        end
        local size = math.min(count, limit)
        if size > 0 and not view.fill(block, system + L.queue, size * L.stride) then
            return nil, 'QUEUE_UNREADABLE'
        end
        -- These checks reject an obviously changed sample, not prove atomicity.
        -- A compaction replacing entries without changing count cannot be detected.
        if view.u32(system + L.queue_count) ~= count
            or view.pointer(game + L.system_global) ~= system
            or view.pointer(game + L.local_user_global) ~= user
            or view.u32(user + L.local_peer) ~= peer_lo
            or view.u32(user + L.local_peer + 4) ~= peer_hi then
            return nil, 'SAMPLE_CHANGED'
        end
        for i = 1, size do
            local at, record = (i - 1) * L.stride, out.records[i]
            record.target = block:u32(at)
            record.source_kind = block:u32(at + 4)
            record.element = block:u32(at + 8)
            record.hit_actor = block:u32(at + 0x0C)
            record.dealer_goid = block:u32(at + 0x10)
            record.owner_goid = block:u32(at + 0x14)
            record.creditor_lo, record.creditor_hi = block:u32(at + 0x18), block:u32(at + 0x1C)
            record.local_player = record.creditor_lo == peer_lo and record.creditor_hi == peer_hi
            record.unknown_key = block:u32(at + 0x20)
            record.damage = block:i32(at + 0x2C) -- -1 is the native kill sentinel
            record.telemetry_distance = block_float(block, at + 0x3C)
            record.telemetry_height = block_float(block, at + 0x40)
            record.unknown_60 = block:u32(at + 0x60)
            -- Reassert diagnostic status, even if a caller mutated a reused slot.
            record.verified, record.direct, record.result = false, nil, nil
            record.ricochet, record.through, record.part_destroyed, record.weakpoint = nil, nil, nil, nil
            record.attack, record.count = nil, nil
        end
        out.sampled_count, out.observed_queue_count, out.truncated = size, count, count > size
        out.local_peer_lo, out.local_peer_hi = peer_lo, peer_hi
        out.classification_verified, out.complete_stream = false, false
        return out
    end
    return api
end
return M
