-- Standalone: run tools/test.py run_lua with args = module path, Runtime cache root.
local module_path, runtime_path = assert(arg[1]), assert(arg[2])
package.preload['hd2runtime/core/bytes'] = function() return dofile(runtime_path .. '/core/bytes.lua') end
package.preload['hd2runtime/domains/event_natives'] = function()
    return dofile(runtime_path .. '/domains/event_natives.lua')
end
local b = require('hd2runtime/core/bytes')
local T = require('hd2runtime/domains/event_natives').stats
local view_api = dofile(runtime_path .. '/runtime/native_view.lua')
local api = dofile(module_path)
local SHOTS, KILLS, HITS = T.keys.projectiles_fired, T.keys.dealt_kills, T.keys.projectiles_hit
local FLOAT, FLAG, ABSENT = 701, 702, 703 -- Synthetic keys, not claimed game keys.
local EMPTY, SOURCE = 4294967295, '0000000212345678'
local tests = 0
local function check(name, fn)
    local ok, message = pcall(fn)
    assert(ok, name .. ': ' .. tostring(message))
    tests = tests + 1; print('PASS ' .. name)
end
local function patch(bytes, offset, insert)
    return bytes:sub(1, offset) .. insert .. bytes:sub(offset + #insert + 1)
end
local function u32(n) return b.encode(n, 'u32') end
local function ptr(n) return u32(n % 4294967296) .. u32(math.floor(n / 4294967296)) end
local function entry(key, int, real, flag)
    return u32(key) .. b.encode(int or 0, 'i32') .. b.encode(real or 0, 'f32')
        .. string.char(flag or 0) .. string.rep('\0', 7)
end
local function mul32(a, c)
    -- Independent exact low-word multiplication for test table construction.
    local bit = require('bit')
    local al, ah, cl, ch = a % 65536, math.floor(a / 65536), c % 65536, math.floor(c / 65536)
    local n = al * cl + ((ah * cl + al * ch) % 65536) * 65536
    return tonumber(bit.band(n % 4294967296, 0xffffffff)) % 4294967296
end
local function fixture(rows, source_rows, opts)
    opts = opts or {}
    local f = {game = 0x10000000, score = 0x30000000, index_slots = 0x40000000,
        main = 0x50000000, sources = 0x60000000, entity = opts.entity or 42,
        capacity = opts.capacity or 8, multiplier = opts.multiplier or 2654435761, calls = {}, fills = 0}
    f.index_header = ptr(f.index_slots) .. u32(8) .. u32(EMPTY) .. u32(f.multiplier)
    f.index_bytes = string.rep(u32(EMPTY) .. u32(EMPTY), 8)
    f.index_bytes = patch(f.index_bytes, (mul32(f.entity, f.multiplier) % 8) * 8,
        u32(f.entity) .. u32(opts.index or 0))
    f.record = ptr(f.main) .. u32(f.capacity) .. u32(EMPTY) .. u32(f.multiplier) .. string.rep('\0', 4)
        .. ptr(opts.no_sources and 0 or f.sources) .. string.rep('\0', 8)
    f.main_bytes = string.rep(entry(EMPTY), f.capacity)
    for _, row in ipairs(rows or {}) do
        local slot = mul32(row[1], f.multiplier) % f.capacity
        while b.u32(f.main_bytes, slot * 20) ~= EMPTY do slot = (slot + 1) % f.capacity end
        f.main_bytes = patch(f.main_bytes, slot * 20, entry(unpack(row)))
    end
    f.source_bytes = string.rep('\0', T.sourceBlocks * T.sourceStride)
    for i, rows_in_block in ipairs(source_rows or {}) do
        local base = (i - 1) * T.sourceStride
        f.source_bytes = patch(f.source_bytes, base, u32(0x12345678) .. u32(2))
        for j, row in ipairs(rows_in_block) do
            f.source_bytes = patch(f.source_bytes, base + T.sourceEntries + (j - 1) * 20, entry(unpack(row)))
        end
    end
    local function raw_read(address, size)
        f.calls[#f.calls + 1] = {address = address, size = size}
        if address == f.sources then f.fills = f.fills + 1 end
        if f.fail and address <= f.fail and f.fail < address + size then return nil end
        local segments = {
            {f.game + T.score, ptr(f.score)}, {f.score + T.indexSlots, f.index_header},
            {f.index_slots, f.index_bytes}, {f.score + T.recordBase, f.record},
            {f.main, f.main_bytes}, {f.sources, f.source_bytes}}
        for _, segment in ipairs(segments) do
            local offset = address - segment[1]
            if offset >= 0 and offset + size <= #segment[2] then
                local bytes = segment[2]:sub(offset + 1, offset + size)
                return f.short and bytes:sub(1, #bytes - 1) or bytes
            end
        end
    end
    f.view = view_api.new({read = raw_read})
    f.block = f.view.slot()
    f.world = {game = f.game, view = f.view}
    return f
end
local function refused(f, specs, reason, snapshot)
    local result, why
    if snapshot then result, why = api.snapshot(f.world, f.entity, f.block)
    else result, why = api.read(f.world, f.entity, specs, f.block) end
    assert(result == nil and why == reason, 'expected ' .. reason .. ', got ' .. tostring(why))
end
check('integer compatibility; source blocks summed once; duplicate specs deduplicated', function()
    local f = fixture({{SHOTS, 4, 99}, {KILLS, 2, 88}},
        {{{SHOTS, 3, 100}, {KILLS, 5, 200}}, {{SHOTS, 7, 300}}})
    local x = assert(api.read(f.world, f.entity, {SHOTS, KILLS, SHOTS}, f.block))
    assert(x.main[SHOTS] == 4 and x.totals[SHOTS] == 14 and x.totals[KILLS] == 7)
    assert(x.sources[SOURCE][SHOTS] == 10 and x.sources[SOURCE][KILLS] == 5)
    assert(f.fills == 1)
    for _, call in ipairs(f.calls) do
        if call.address >= f.main and call.address < f.main + #f.main_bytes then assert(call.size == 20) end
    end
end)
check('mixed typed slots; float is +8 rather than integer +4; boolean OR', function()
    local f = fixture({{FLOAT, 9000, 12.5}, {FLAG, 42, 5.5, 0}},
        {{{FLOAT, 8000, 2.25}, {FLAG, 3, 66, 1}}, {{FLOAT, 7000, 0.25}, {FLAG, 2, 9, 0}}})
    local x = assert(api.read(f.world, f.entity,
        {{key = FLOAT, kind = 'f32'}, {key = FLAG, kind = 'bool'}}, f.block))
    assert(x.main[FLOAT] == 12.5 and x.totals[FLOAT] == 15 and x.sources[SOURCE][FLOAT] == 2.5)
    assert(x.main[FLAG] == false and x.totals[FLAG] == true and x.sources[SOURCE][FLAG] == true)
    assert(f.fills == 1)
end)
check('known projectile-hit key shares the existing source bulk read and preserves attribution', function()
    assert(HITS == 0x897A5551)
    local f = fixture({{SHOTS, 8}, {KILLS, 1}, {HITS, 2}},
        {{{SHOTS, 12}, {KILLS, 3}, {HITS, 7}}, {{HITS, 4}}})
    local x = assert(api.read(f.world, f.entity, {SHOTS, KILLS, HITS}, f.block))
    assert(x.totals[HITS] == 13 and x.main[HITS] == 2 and x.sources[SOURCE][HITS] == 11)
    assert(x.totals[SHOTS] == 20 and x.totals[KILLS] == 4 and f.fills == 1)
    local source_reads = 0
    for _, call in ipairs(f.calls) do if call.address == f.sources then source_reads = source_reads + 1 end end
    assert(source_reads == 1)
end)
check('missing keys return numeric zero or boolean false', function()
    local f = fixture({}, nil, {no_sources = true})
    local x = assert(api.read(f.world, f.entity, {ABSENT, {key = FLOAT, kind = 'f32'},
        {key = FLAG, kind = 'bool'}}, f.block))
    assert(x.totals[ABSENT] == 0 and x.totals[FLOAT] == 0 and x.totals[FLAG] == false)
    assert(next(x.sources) == nil and f.fills == 0)
end)
check('empty spec list does not access memory or validate unrelated target', function()
    local x = assert(api.read(nil, nil, {}, nil))
    assert(next(x.totals) == nil and next(x.main) == nil and next(x.sources) == nil)
end)
check('signed integer slots and hash collision handling', function()
    local f = fixture({{1, -17, 9}, {9, 20, 10}}, {{{1, -3, 12}}})
    local x = assert(api.read(f.world, f.entity, {1, 9}, f.block))
    assert(x.main[1] == -17 and x.totals[1] == -20 and x.totals[9] == 20)
end)
check('raw snapshots preserve slots, all types and duplicate source blocks', function()
    local f = fixture({{FLOAT, 9000, 12.5, 7}}, {{{FLOAT, 8000, 2.25, 0}}, {{FLOAT, 7000, 0.25, 1}}})
    local x = assert(api.snapshot(f.world, f.entity, f.block))
    assert(#x.main == 1 and #x.sources == 2 and x.capacity == 8 and x.score_index == 0)
    assert(x.main[1].key == FLOAT and x.main[1].i32 == 9000 and x.main[1].f32 == 12.5)
    assert(x.main[1].bool == true and x.main[1].bool_byte == 7 and x.main[1].f32_valid == true)
    assert(x.sources[1].block == 0 and x.sources[2].block == 1)
    assert(x.sources[1].type == SOURCE and x.sources[2].type == SOURCE)
    assert(x.sources[1].entries[1].i32 == 8000 and x.sources[2].entries[1].f32 == 0.25)
    assert(f.fills == 1)
end)
check('binary raw capture preserves complete buffers and unused float bits without entry allocation', function()
    local f = fixture({{FLOAT, -17, 12.5, 7}}, {{{FLOAT, 9, 2.25, 0}}, {{FLOAT, 8, 0.25, 1}}})
    local slot = mul32(FLOAT, f.multiplier) % f.capacity
    f.main_bytes = patch(f.main_bytes, slot * 20 + 8, u32(0x7FC01234))
    local x = assert(api.raw(f.world, f.entity))
    assert(x.capacity == 8 and x.empty == EMPTY and x.score_index == 0)
    assert(x.main_bytes == f.main_bytes and x.sources_bytes == f.source_bytes)
    assert(x.main == nil and x.sources == nil and f.fills == 1)
    local main_reads, source_reads = 0, 0
    for _, call in ipairs(f.calls) do
        if call.address == f.main then main_reads = main_reads + 1; assert(call.size == 8 * 20) end
        if call.address == f.sources then source_reads = source_reads + 1; assert(call.size == 64 * 328) end
    end
    assert(main_reads == 1 and source_reads == 1)
end)
check('binary raw empty and maximum tables respect bounded lengths without a scratch buffer', function()
    local f = fixture(nil, nil, {no_sources = true})
    f.record = patch(f.record, 0, ptr(0)); f.record = patch(f.record, 8, u32(0))
    local x = assert(api.raw(f.world, f.entity))
    assert(x.capacity == 0 and x.main_bytes == '' and x.sources_bytes == '' and f.fills == 0)
    f = fixture({{SHOTS, 4}}, {{{SHOTS, 5}}}, {capacity = 4096})
    x = assert(api.raw(f.world, f.entity))
    assert(#x.main_bytes == 4096 * 20 and #x.sources_bytes == 64 * 328 and f.fills == 1)
    f.record = patch(f.record, 8, u32(8192))
    local result, reason = api.raw(f.world, f.entity)
    assert(result == nil and reason == 'MAIN_CAPACITY_LIMIT_OR_INVALID')
end)
check('binary raw unreadable main or sources fails atomically', function()
    local f = fixture({{SHOTS, 2}})
    f.fail = f.main
    local x, why = api.raw(f.world, f.entity)
    assert(x == nil and why == 'MAIN_UNREADABLE')
    f.fail = f.sources
    x, why = api.raw(f.world, f.entity)
    assert(x == nil and why == 'SOURCES_UNREADABLE')
end)
check('nonfinite raw float retains bits; typed float refuses entire reading', function()
    local f = fixture({{FLOAT, 23, 0}})
    local slot = mul32(FLOAT, f.multiplier) % f.capacity
    f.main_bytes = patch(f.main_bytes, slot * 20 + 8, u32(0x7FC01234))
    local x = assert(api.snapshot(f.world, f.entity, f.block))
    assert(x.main[1].f32 == nil and x.main[1].f32_valid == false and x.main[1].float_bits == 0x7FC01234)
    refused(f, {{key = FLOAT, kind = 'f32'}}, 'NONFINITE_MAIN_FLOAT')
    assert(api.read(f.world, f.entity, {FLOAT}, f.block).totals[FLOAT] == 23)
    f = fixture({}, {{{FLOAT, 5, 0}}})
    f.source_bytes = patch(f.source_bytes, 8 + 8, u32(0x7F800000))
    refused(f, {{key = FLOAT, kind = 'f32'}}, 'NONFINITE_SOURCE_FLOAT')
    x = assert(api.snapshot(f.world, f.entity, f.block))
    assert(x.sources[1].entries[1].f32_valid == false)
end)
check('mapping missing player and invalid score index do not read statistics', function()
    local f = fixture()
    f.index_bytes = string.rep(u32(EMPTY) .. u32(EMPTY), 8)
    refused(f, {SHOTS}, 'PLAYER_NOT_FOUND')
    assert(f.fills == 0)
    f = fixture(nil, nil, {index = 4})
    refused(f, {SHOTS}, 'PLAYER_NOT_FOUND')
end)
check('main capacity over 4096 or non power of two refuses before enumeration', function()
    local f = fixture()
    f.record = patch(f.record, 8, u32(8192))
    refused(f, nil, 'MAIN_CAPACITY_LIMIT_OR_INVALID', true)
    f.record = patch(f.record, 8, u32(6))
    refused(f, {SHOTS}, 'MAIN_CAPACITY_LIMIT_OR_INVALID')
    assert(f.fills == 0)
end)
check('zero-capacity table and absent sources are a valid empty snapshot', function()
    local f = fixture(nil, nil, {no_sources = true})
    f.record = patch(f.record, 0, ptr(0)); f.record = patch(f.record, 8, u32(0))
    local x = assert(api.snapshot(f.world, f.entity, f.block))
    assert(#x.main == 0 and #x.sources == 0 and x.capacity == 0)
    assert(api.read(f.world, f.entity, {SHOTS}, f.block).totals[SHOTS] == 0)
end)
check('bounded maximum capture and all 64 sources with 16 entries each', function()
    local blocks = {}
    for i = 1, 64 do
        blocks[i] = {}
        for j = 1, 16 do blocks[i][j] = {SHOTS, 1, j, 0} end
    end
    local f = fixture({{SHOTS, 4}}, blocks,
        {capacity = 4096, entity = 4294906420, multiplier = 4063530223})
    local x = assert(api.snapshot(f.world, f.entity, f.block))
    assert(x.capacity == 4096 and #x.main == 1 and #x.sources == 64)
    assert(#x.sources[64].entries == 16 and x.sources[64].entries[16].f32 == 16)
    assert(f.fills == 1)
    f.fills = 0
    x = assert(api.read(f.world, f.entity, {SHOTS}, f.block))
    assert(x.totals[SHOTS] == 1028 and x.sources[SOURCE][SHOTS] == 1024 and f.fills == 1)
end)
check('index capacity, unreadable record and unsafe pointer failures are explicit', function()
    local f = fixture()
    f.index_header = patch(f.index_header, 8, u32(131072))
    refused(f, {SHOTS}, 'INDEX_CAPACITY_LIMIT_OR_INVALID')
    f = fixture(); f.fail = f.index_slots + (mul32(f.entity, f.multiplier) % 8) * 8
    refused(f, {SHOTS}, 'INDEX_UNREADABLE')
    f = fixture(); f.fail = f.score + T.recordBase
    refused(f, {SHOTS}, 'RECORD_UNREADABLE')
    f = fixture(); f.record = patch(f.record, 4, u32(0xFFFF))
    refused(f, {SHOTS}, 'RECORD_POINTER_INVALID')
end)
check('unreadable/short reads and missing source buffer never return partial data', function()
    local f = fixture({{SHOTS, 2}})
    f.fail = f.score + T.indexSlots; refused(f, {SHOTS}, 'SCORE_UNREADABLE')
    f.fail = f.main + (mul32(SHOTS, f.multiplier) % f.capacity) * 20
    refused(f, {SHOTS}, 'MAIN_UNREADABLE')
    f.fail = f.sources; refused(f, {SHOTS}, 'SOURCES_UNREADABLE')
    f.fail = nil
    local x, why = api.read(f.world, f.entity, {SHOTS}, nil)
    assert(x == nil and why == 'SOURCE_BUFFER_REQUIRED')
    f.short = true; refused(f, {SHOTS}, 'SCORE_UNREADABLE')
end)
check('spec limits, invalid kind, holes, conflicting duplicate and invalid target', function()
    local f = fixture()
    refused(f, {{key = SHOTS, kind = 'string'}}, 'INVALID_SPECS')
    refused(f, {SHOTS, {key = SHOTS, kind = 'f32'}}, 'CONFLICTING_SPEC')
    refused(f, {[1] = SHOTS, [3] = KILLS}, 'INVALID_SPECS')
    local specs = {}; for i = 1, 65 do specs[i] = SHOTS end
    refused(f, specs, 'INVALID_SPECS')
    local x, why = api.read(f.world, -1, {SHOTS}, f.block)
    assert(x == nil and why == 'INVALID_TARGET')
    assert(#f.calls == 0)
end)
print('native-stats: ' .. tests .. ' checks passed; actual HD2 Lua 5.1; no live game access.')
