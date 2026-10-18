-- Actual Runtime bytes/schema with owned saved Career rows; no live process.
local runtime_root = assert(arg[2], 'Runtime source root required')
table.insert(package.loaders, 1, function(name)
    if name:sub(1, 11) ~= 'hd2runtime/' then return '\nnot a Runtime module' end
    local fn, why = loadfile(runtime_root .. '/' .. name:sub(12) .. '.lua')
    return fn or ('\n' .. tostring(why))
end)
local b = require('hd2runtime/core/bytes')
local profile = require('hd2runtime/schemas/current')
local M = assert(loadfile(arg[1]))()
local fixture = assert(loadfile(arg[3]))()
local PEER = '0102030405060708'
local U32 = 4294967296
local function ptr(value) return b.encode(value % U32, 'u32') .. b.encode(math.floor(value / U32), 'u32') end
local function memory()
    local m = {records = {}, reads = {}, writes = 0, local_user = 0x300000000}
    for _, record in ipairs(fixture.records) do m.records[#m.records + 1] = {record[1], b.unhex(record[2])} end
    m.records[#m.records + 1] = {fixture.game + M.source.local_user, ptr(m.local_user)}
    -- Peer storage is an owned synthetic addition from the Runtime schema,
    -- not bytes claimed to have been present in the original Career capture.
    m.records[#m.records + 1] = {m.local_user + M.source.local_peer, b.unhex(PEER):reverse()}
    function m:patch(at, raw)
        for _, record in ipairs(self.records) do
            if at >= record[1] and at + #raw <= record[1] + #record[2] then
                local offset = at - record[1]
                record[2] = record[2]:sub(1, offset) .. raw .. record[2]:sub(offset + #raw + 1)
                return
            end
        end
        error('patch outside owned fixture')
    end
    m.world = {game = fixture.game, runtime = {mode = 'live',
        write = function() m.writes = m.writes + 1; error('must never write') end}, view = {}}
    m.world.view.pointer = function() error('unbudgeted pointer') end
    m.world.view.u32 = function() error('unbudgeted u32') end
    m.world.view.fill = function() error('unbudgeted fill') end
    m.world.view.read = function(at, n)
        m.reads[#m.reads + 1] = {at, n}
        if m.on_read then m.on_read(at, n) end
        if m.short == at then return '' end
        for _, record in ipairs(m.records) do
            if at >= record[1] and at + n <= record[1] + #record[2] then
                return record[2]:sub(at - record[1] + 1, at - record[1] + n)
            end
        end
        error(('read outside owned fixture %x/%d'):format(at, n))
    end
    function m:alpha(value)
        self:patch(fixture.controller + M.source.panel + M.source.track_alpha, b.encode(value, 'f32'))
    end
    return m
end
local cases = 0
local function test(name, fn) fn(); cases = cases + 1 end
local function reader(options)
    options = options or {}; options.clock = options.clock or function() return 0 end
    return M.new(options)
end
if HD2_CAREER_FIXTURE_ONLY then
    return {memory=memory,fixture=fixture,M=M,peer=PEER,b=b,ptr=ptr}
end

test('actual two rows and current peer before/after', function()
    local m, r = memory(), reader()
    local s, why = r:read(m.world, PEER)
    assert(s and s.kills == 351849 and s.deaths == 4633 and why == 'page_visible')
    assert(s.local_peer == PEER and s.identity.local_user == m.local_user)
    assert(s.ui_cache_loaded and not s.backend_ready and not s.server_ready)
    assert(not s.ui_cache_refresh_verified and not s.generic_numeric_enum_verified)
    assert(r.diagnostics.reads == 58 and r.diagnostics.bytes == 6761)
    assert(m.writes == 0 and #m.reads == 58)
end)
test('production visible-only stops before rows after closing', function()
    local m, r = memory(), reader({visible_only=true})
    assert(r:read(m.world, PEER))
    m:alpha(0)
    local n = #m.reads
    local s, why = r:read(m.world, PEER)
    assert(not s and why == 'CAREER_PAGE_NOT_VISIBLE' and #m.reads - n == 9)
end)

test('PINs once for same native world, reproved for new view', function()
    local m, r = memory(), reader(); assert(r:read(m.world, PEER))
    local before = #m.reads; assert(r:read(m.world, PEER))
    assert(#m.reads - before == 54 and r.diagnostics.bytes == 6720)
    local old = m.world.view
    m.world.view = {read = old.read}
    before = #m.reads; assert(r:read(m.world, PEER)); assert(#m.reads - before == 58)
end)

test('nonShip checks only twelve bytes and no Career or peer', function()
    for _, state in ipairs({0, 1, 2, 4, 5, 6}) do
        local m, r = memory(), reader()
        m:patch(fixture.state_context + M.source.state_offset, b.encode(state, 'u32'))
        local s, why = r:read(m.world, PEER)
        assert(not s and why == 'CAREER_WAITING_FOR_SHIP')
        assert(#m.reads == 2 and r.diagnostics.bytes == 12)
    end
end)

test('malformed/nonlocal peer refuses before IO', function()
    for _, peer in ipairs({'bad', '0000000000000000', '010203040506070Z'}) do
        local m, r = memory(), reader(); local s, why = r:read(m.world, peer)
        assert(not s and why == 'CAREER_LOCAL_PEER_UNAVAILABLE' and #m.reads == 0)
    end
    local m, r = memory(), reader(); local s, why = r:read(m.world, '0102030405060709')
    assert(not s and why == 'CAREER_LOCAL_PEER_CHANGED' and #m.reads == 9)
end)

test('peer change after snapshot prevents result', function()
    local m, r, calls = memory(), reader(), 0
    m.on_read = function(at)
        if at == m.local_user + M.source.local_peer then
            calls = calls + 1
            if calls == 2 then m:patch(at, b.unhex('0102030405060709'):reverse()) end
        end
    end
    local s, why = r:read(m.world, PEER)
    assert(not s and why == 'CAREER_LOCAL_PEER_CHANGED' and not r.diagnostics.ui_cache_loaded)
end)

test('hidden cache requires one genuine visible read and remains freshness unknown', function()
    local m, r = memory(), reader(); m:alpha(0)
    local s, why = r:read(m.world, PEER)
    assert(not s and why == 'CAREER_UI_CACHE_NOT_ESTABLISHED')
    assert(#m.reads == 9 and not r.diagnostics.ui_cache_loaded)
    m:alpha(1); assert(r:read(m.world, PEER)); m:alpha(0)
    s, why = r:read(m.world, PEER)
    assert(s and why == 'ui_cache_observed' and s.ui_cache_loaded and not s.page_visible)
    assert(s.kills == 351849 and not s.server_ready and not s.ui_cache_refresh_verified)
    r:reset(); assert(not r:read(m.world, PEER))
end)

test('mission does not read cached Career; returnShip cache is observed, not refreshed', function()
    local m, r = memory(), reader(); assert(r:read(m.world, PEER)); m:alpha(0)
    m:patch(fixture.state_context + M.source.state_offset, b.encode(4, 'u32'))
    assert(not r:read(m.world, PEER)); assert(r.diagnostics.reads == 2)
    m:patch(fixture.state_context + M.source.state_offset, b.encode(3, 'u32'))
    local s = assert(r:read(m.world, PEER))
    assert(s.status == 'ui_cache_observed' and not s.ui_cache_refresh_verified)
end)

test('same-context list rebuild in final gate is rejected', function()
    local m, r, calls = memory(), reader(), 0
    m.on_read = function(at)
        if at == fixture.list then
            calls = calls + 1
            if calls == 2 then m:patch(at + 0xE0, ptr(fixture.rows[2])) end
        end
    end
    local s, why = r:read(m.world, PEER)
    assert(not s and why == 'CAREER_PAGE_CHANGED')
end)

test('type4 zero high32 and nonnegative32 supported subset only', function()
    local at = fixture.rows[2] + M.source.value + 272
    for _, failure in ipairs({'key', 'type', 'high', 'negative', 'count', 'tag'}) do
        local m, r = memory(), reader()
        if failure == 'key' then m:patch(at + 8, b.encode(0, 'u32')) end
        if failure == 'type' then m:patch(at + 12, b.encode(1, 'u32')) end
        if failure == 'high' then m:patch(at + 20, b.encode(1, 'u32')) end
        if failure == 'negative' then m:patch(at + 16, b.encode(2147483648, 'u32')) end
        if failure == 'count' then m:patch(at + 344, '\2') end
        if failure == 'tag' then m:patch(fixture.rows[2] + M.source.tag + 272, b.encode(0, 'u32')) end
        local s, why = r:read(m.world, PEER)
        assert(not s and (why == 'CAREER_VALUE_FORMAT' or why == 'CAREER_LABEL_BINDING'))
    end
end)

test('zero values are permitted genuine values but read failure is never zero', function()
    local m, r = memory(), reader()
    m:patch(fixture.rows[2] + M.source.value + 288, ptr(0))
    local s = assert(r:read(m.world, PEER)); assert(s.deaths == 0)
    m = memory(); r = reader(); m.short = fixture.rows[2] + M.source.value + 272
    s = r:read(m.world, PEER); assert(not s and r.diagnostics.reason == 'CAREER_READ_FAILED')
end)

test('code PIN mismatch rejects before row traversal', function()
    local m, r = memory(), reader()
    m:patch(fixture.game + M.pins[1].rva, '\0')
    local s, why = r:read(m.world, PEER)
    assert(not s and why == 'CAREER_CODE_MISMATCH')
    for _, call in ipairs(m.reads) do assert(call[1] ~= fixture.rows[1]) end
end)

test('value change and cycle prevent snapshot', function()
    local m, r, calls = memory(), reader(), 0
    local at = fixture.rows[2] + M.source.value + 272
    m.on_read = function(address)
        if address == at then calls = calls + 1; if calls == 2 then m:patch(at + 16, b.encode(4634, 'u32')) end end
    end
    local s, why = r:read(m.world, PEER); assert(not s and why == 'CAREER_VALUE_CHANGED')
    m = memory(); r = reader(); m:patch(fixture.rows[1] + 0xE8, ptr(fixture.rows[1]))
    s, why = r:read(m.world, PEER); assert(not s and why == 'CAREER_ROW_CHAIN')
end)

test('all read and byte limits check before first native operation', function()
    local m, r = memory(), reader({max_bytes = 1})
    local s, why = r:read(m.world, PEER)
    assert(not s and why == 'CAREER_READ_BUDGET' and #m.reads == 0)
    m = memory(); r = reader({max_reads = 1})
    s, why = r:read(m.world, PEER)
    assert(not s and why == 'CAREER_READ_BUDGET' and #m.reads == 1)
    local calls = 0
    m = memory(); r = reader({clock = function() calls = calls + 1; return calls == 1 and 0 or .003 end})
    s, why = r:read(m.world, PEER)
    assert(not s and why == 'CAREER_TIME_BUDGET' and #m.reads == 0)
    assert(not pcall(M.new, {max_reads = 65}))
    assert(not pcall(M.new, {max_bytes = 8193}))
    assert(not pcall(M.new, {seconds = .003}))
end)

test('changed schema and nonlive world refuse zero IO', function()
    local m, r = memory(), reader(); local original = profile.dll_sha
    profile.dll_sha = 'wrong'; local s, why = r:read(m.world, PEER); profile.dll_sha = original
    assert(not s and why == 'CAREER_BUILD_MISMATCH' and #m.reads == 0)
    m.world.runtime.mode = 'offline'; s, why = r:read(m.world, PEER)
    assert(not s and why == 'CAREER_WORLD_UNAVAILABLE' and #m.reads == 0)
end)

test('actual Runtime f32 decoder rejects NaN and infinity before cache status', function()
    for _, bits in ipairs({0x7FC00000, 0x7F800000, 0xFF800000}) do
        local m, r = memory(), reader(); assert(r:read(m.world, PEER))
        m:patch(fixture.controller + M.source.panel + M.source.track_alpha, b.encode(bits, 'u32'))
        local s, why = r:read(m.world, PEER)
        assert(not s and why:find('nonfinite field value', 1, true))
        assert(not r.diagnostics.ready)
    end
end)

assert(not fixture.source_complete, 'owned partial fixture mislabelled complete')
print('native-career-reader: ' .. cases .. ' cases PASS; type4 two rows; no live reads/writes')
