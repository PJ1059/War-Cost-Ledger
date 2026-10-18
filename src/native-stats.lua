-- Read-only statistics for the already-proven HD2Runtime 0.30.3 world.
-- Layout/provenance: HD2Runtime scripts/research_event_state.py and
-- scripts/generate_event_natives.py (Steam build 25480438). No guessed keys.
-- This file can be embedded as: local NATIVE_STATS = (function() ... end)().
local b = require('hd2runtime/core/bytes')
local T = require('hd2runtime/domains/event_natives').stats
local M = {limits = {main_capacity = 4096, index_capacity = 65536,
    source_blocks = 64, source_entries = 16, specs = 64}}
local U32, I32 = 4294967296, 2147483648

local function uint(value)
    return type(value) == 'number' and value >= 0 and value < U32 and value % 1 == 0
end
local function capacity(value, limit, allow_empty)
    if not uint(value) or value > limit then return false end
    if value == 0 then return allow_empty end
    while value > 1 do
        if value % 2 ~= 0 then return false end
        value = value / 2
    end
    return true
end
local function pointer(bytes, offset)
    local lo, hi = b.u32(bytes, offset), b.u32(bytes, offset + 4)
    if hi > 32767 then return nil end
    local value = lo + hi * U32
    if value == 0 or value >= 65536 then return value end
end
local function read(world, address, size)
    if type(address) ~= 'number' or address < 65536 then return nil end
    local bytes = world.view.read(address, size)
    if type(bytes) ~= 'string' or #bytes ~= size then return nil end
    return bytes
end
local function mul32(a, c)
    -- Avoid losing low bits in a double when multiplying two full u32 values.
    local al, cl = a % 65536, c % 65536
    return (al * cl + ((a - al) * cl + (c - cl) * al) % U32) % U32
end
local function zero(kind)
    if kind == 'bool' then return false end
    return 0
end
local function locate(world, entity)
    if type(world) ~= 'table' or type(world.view) ~= 'table'
        or type(world.view.read) ~= 'function' or type(world.view.pointer) ~= 'function'
        or type(world.game) ~= 'number' or not uint(entity) then
        return nil, 'INVALID_TARGET'
    end
    local score = world.view.pointer(world.game + T.score)
    local header = score and read(world, score + T.indexSlots, 20)
    if not header then return nil, 'SCORE_UNREADABLE' end
    local slots, count = pointer(header, 0), b.u32(header, 8)
    if not capacity(count, M.limits.index_capacity, false) then
        return nil, 'INDEX_CAPACITY_LIMIT_OR_INVALID'
    end
    if not slots or slots == 0 then return nil, 'INDEX_UNREADABLE' end
    local empty, start = b.u32(header, 12), mul32(entity, b.u32(header, 16))
    local index
    for probe = 0, count - 1 do
        local entry = read(world, slots + ((start + probe) % count) * 8, 8)
        if not entry then return nil, 'INDEX_UNREADABLE' end
        local key = b.u32(entry, 0)
        if key == empty then break end
        if key == entity then index = b.u32(entry, 4); break end
    end
    if not index or index >= T.maxPlayers then return nil, 'PLAYER_NOT_FOUND' end
    local record = read(world, score + T.recordBase + index * T.recordStride, T.recordStride)
    if not record then return nil, 'RECORD_UNREADABLE' end
    local main_capacity = b.u32(record, T.tableCapacity)
    if not capacity(main_capacity, M.limits.main_capacity, true) then
        return nil, 'MAIN_CAPACITY_LIMIT_OR_INVALID'
    end
    local main, sources = pointer(record, T.tableEntries), pointer(record, T.sources)
    if not main or (main_capacity > 0 and main == 0) or not sources then
        return nil, 'RECORD_POINTER_INVALID'
    end
    return {index = index, main = main, capacity = main_capacity,
        empty = b.u32(record, T.tableEmpty), multiplier = b.u32(record, T.tableMultiplier), sources = sources}
end
local function finite_bits(bits) return math.floor(bits / 8388608) % 256 ~= 255 end
local function value(bytes, offset, kind)
    if kind == 'bool' then return bytes:byte(offset + 13) ~= 0 end
    if kind == 'i32' then return b.value(bytes, offset + 4, 'i32') end
    if not finite_bits(b.u32(bytes, offset + 8)) then return nil end
    return b.value(bytes, offset + 8, 'f32')
end
local function block_value(block, offset, kind)
    if kind == 'bool' then return block:u8(offset + 12) ~= 0 end
    if kind == 'i32' then return block:i32(offset + 4) end
    if not finite_bits(block:u32(offset + 8)) then return nil end
    return block:f32(offset + 8)
end
local function add(a, c, kind)
    if kind == 'bool' then return a or c end
    return a + c
end
local function specs_list(specs)
    if type(specs) ~= 'table' then return nil, 'INVALID_SPECS' end
    local count = 0
    for index in pairs(specs) do
        if not uint(index) or index < 1 or index > M.limits.specs then return nil, 'INVALID_SPECS' end
        count = count + 1
    end
    if count ~= #specs then return nil, 'INVALID_SPECS' end
    local keys, list = {}, {}
    for _, spec in ipairs(specs) do
        local key, kind = spec, 'i32'
        if type(spec) == 'table' then key, kind = spec.key, spec.kind or 'i32' end
        if not uint(key) or (kind ~= 'i32' and kind ~= 'f32' and kind ~= 'bool') then
            return nil, 'INVALID_SPECS'
        end
        if keys[key] and keys[key] ~= kind then return nil, 'CONFLICTING_SPEC' end
        if not keys[key] then list[#list + 1] = {key = key, kind = kind}; keys[key] = kind end
    end
    return list, keys
end
local function source_block(world, located, block)
    if located.sources == 0 then return false end
    if not block or type(world.view.fill) ~= 'function' then return nil, 'SOURCE_BUFFER_REQUIRED' end
    local filled = world.view.fill(block, located.sources, T.sourceBlocks * T.sourceStride)
    if not filled then return nil, 'SOURCES_UNREADABLE' end
    return filled
end

-- specs = {key, {key = key, kind = 'i32'|'f32'|'bool'}, ...}; integers default to i32.
-- Missing keys are 0/false. Duplicate specs are read once; conflicting kinds fail.
-- Counts/floats sum main + all source entries; bool uses OR (a reporting convention).
-- A nil result + reason means no partial reading should be consumed. Empty specs
-- return empty tables without touching memory. One source fill at most per call.
function M.read(world, entity, specs, block)
    local list, wanted = specs_list(specs)
    if not list then return nil, wanted end
    local result = {totals = {}, main = {}, sources = {}}
    if #list == 0 then return result end
    local located, reason = locate(world, entity)
    if not located then return nil, reason end
    for _, spec in ipairs(list) do
        local current = zero(spec.kind)
        local start = mul32(spec.key, located.multiplier)
        for probe = 0, located.capacity - 1 do
            local entry = read(world, located.main + ((start + probe) % located.capacity) * T.entryStride,
                T.entryStride)
            if not entry then return nil, 'MAIN_UNREADABLE' end
            local key = b.u32(entry, 0)
            if key == located.empty then break end
            if key == spec.key then
                current = value(entry, 0, spec.kind)
                if current == nil then return nil, 'NONFINITE_MAIN_FLOAT' end
                break
            end
        end
        result.main[spec.key], result.totals[spec.key] = current, current
    end
    local filled, why = source_block(world, located, block)
    if filled == nil then return nil, why end
    if filled then
        for index = 0, T.sourceBlocks - 1 do
            local base = index * T.sourceStride
            local lo, hi = filled:u32(base), filled:u32(base + 4)
            if lo ~= 0 or hi ~= 0 then
                local source
                for slot = 0, T.sourceEntryCount - 1 do
                    local at = base + T.sourceEntries + slot * T.entryStride
                    local key = filled:u32(at)
                    if key == 0 then break end
                    local kind = wanted[key]
                    if kind then
                        local current = block_value(filled, at, kind)
                        if current == nil then return nil, 'NONFINITE_SOURCE_FLOAT' end
                        if not source then
                            local name = string.format('%08X%08X', hi, lo)
                            source = result.sources[name] or {}; result.sources[name] = source
                        end
                        local previous = source[key]
                        if previous == nil then previous = zero(kind) end
                        source[key] = add(previous, current, kind)
                        result.totals[key] = add(result.totals[key], current, kind)
                    end
                end
            end
        end
    end
    return result
end

local function raw_entry(bytes, offset, slot)
    local bits, byte = b.u32(bytes, offset + 8), bytes:byte(offset + 13)
    local valid = finite_bits(bits)
    return {slot = slot, key = b.u32(bytes, offset), i32 = b.value(bytes, offset + 4, 'i32'),
        f32 = valid and b.value(bytes, offset + 8, 'f32') or nil, f32_valid = valid,
        float_bits = bits, bool = byte ~= 0, bool_byte = byte}
end
-- Preserve the bounded native buffers without constructing an entry table.
-- Decoding/JSON conversion can run in an external process after the capture.
-- Empty main/source tables produce empty strings; unreadable data fails atomically.
function M.raw(world, entity)
    local located, reason = locate(world, entity)
    if not located then return nil, reason end
    local main, sources = '', ''
    if located.capacity > 0 then
        main = read(world, located.main, located.capacity * T.entryStride)
        if not main then return nil, 'MAIN_UNREADABLE' end
    end
    if located.sources ~= 0 then
        sources = read(world, located.sources, T.sourceBlocks * T.sourceStride)
        if not sources then return nil, 'SOURCES_UNREADABLE' end
    end
    return {capacity = located.capacity, empty = located.empty, score_index = located.index,
        main_bytes = main, sources_bytes = sources}
end
-- Bounded raw capture, without merging independently stored int/float/bool slots.
-- main is a physical-slot entry array; sources is an array of {block,type,entries}
-- preserving duplicate source blocks and entries. Slots/block indexes are zero-based.
-- Nonfinite *unused* float slots keep float_bits with f32_valid=false, f32 omitted.
function M.snapshot(world, entity, block)
    local located, reason = locate(world, entity)
    if not located then return nil, reason end
    local result = {player_entity = entity, score_index = located.index, capacity = located.capacity,
        main = {}, sources = {}}
    if located.capacity > 0 then
        local bytes = read(world, located.main, located.capacity * T.entryStride)
        if not bytes then return nil, 'MAIN_UNREADABLE' end
        for slot = 0, located.capacity - 1 do
            local at = slot * T.entryStride
            if b.u32(bytes, at) ~= located.empty then result.main[#result.main + 1] = raw_entry(bytes, at, slot) end
        end
    end
    local filled, why = source_block(world, located, block)
    if filled == nil then return nil, why end
    if filled then
        for index = 0, T.sourceBlocks - 1 do
            local base = index * T.sourceStride
            local lo, hi = filled:u32(base), filled:u32(base + 4)
            if lo ~= 0 or hi ~= 0 then
                local source = {block = index, type = string.format('%08X%08X', hi, lo), entries = {}}
                for slot = 0, T.sourceEntryCount - 1 do
                    local at = base + T.sourceEntries + slot * T.entryStride
                    local key = filled:u32(at)
                    if key == 0 then break end
                    local bits, byte = filled:u32(at + 8), filled:u8(at + 12)
                    local valid = finite_bits(bits)
                    source.entries[#source.entries + 1] = {slot = slot, key = key, i32 = filled:i32(at + 4),
                        f32 = valid and filled:f32(at + 8) or nil, f32_valid = valid,
                        float_bits = bits, bool = byte ~= 0, bool_byte = byte}
                end
                result.sources[#result.sources + 1] = source
            end
        end
    end
    return result
end
return M
