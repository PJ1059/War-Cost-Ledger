-- Actual Runtime bytes/schema and LuaJIT, owned sparse bytes only; no Game.
local runtime_root = assert(arg[2], 'Runtime source root required')
table.insert(package.loaders, 1, function(name)
    if name:sub(1, 11) ~= 'hd2runtime/' then return '\nnot a Runtime module' end
    local fn, why = loadfile(runtime_root .. '/' .. name:sub(12) .. '.lua')
    return fn or ('\n' .. tostring(why))
end)
local b = require('hd2runtime/core/bytes')
local profile = require('hd2runtime/schemas/current')
local M = assert(loadfile(arg[1]))()
local PEER, U32 = '06464E240E0D372A', 4294967296
local function ptr(v) return b.encode(v % U32, 'u32') .. b.encode(math.floor(v / U32), 'u32') end
local function memory()
    local m = {game = 0x180000000, context = 0x300000000, user = 0x301000000,
        counter = 0x302000000, other_counter = 0x302100000, names = {0x303000003, 0x303000083},
        bytes = {}, reads = {}, writes = 0}
    function m:put(at, raw) for i = 1, #raw do self.bytes[at + i - 1] = raw:sub(i, i) end end
    m:put(m.game + M.source.state, ptr(m.context))
    m:put(m.context + M.source.state_offset, b.encode(3, 'u32'))
    m:put(m.game + M.source.local_user, ptr(m.user))
    m:put(m.user + M.source.local_peer, b.unhex(PEER):reverse())
    m:put(m.game + M.source.counters, ptr(m.counter))
    for _, at in ipairs({m.counter, m.other_counter}) do
        m:put(at + M.source.kills, b.encode(351885, 'u32'))
        m:put(at + M.source.deaths, b.encode(4633, 'u32'))
    end
    for _, pin in ipairs(M.pins) do m:put(m.game + pin.rva, b.unhex(pin.hex)) end
    for i, name in ipairs(M.names) do
        m:put(m.game + M.source.names + name.slot * 8, ptr(m.names[i]))
        -- Packed rodata may contain following bytes after the first NUL.
        m:put(m.names[i], name.text .. '\0' .. string.rep('x', 63 - #name.text))
    end
    m.world = {game = m.game, runtime = {mode = 'live', write = function()
        m.writes = m.writes + 1; error('must not write') end}, view = {}}
    m.world.view.pointer = function() error('unbudgeted pointer') end
    m.world.view.u32 = function() error('unbudgeted u32') end
    m.world.view.read = function(at, size)
        m.reads[#m.reads + 1] = {at, size}
        if m.on_read then m.on_read(at, size) end
        if m.short == at then return '' end
        local raw = {}
        for i = 0, size - 1 do raw[#raw + 1] = assert(m.bytes[at + i], 'read outside owned fields') end
        return table.concat(raw)
    end
    return m
end
local function reader(options)
    options = options or {}; options.clock = options.clock or function() return 0 end
    return M.new(options)
end
local cases = 0
local function test(name, fn) fn(); cases = cases + 1 end
local function reject(m, r, why)
    local value, reason = r:read(m.world, PEER)
    assert(not value and reason == why, tostring(reason))
    assert(not r.diagnostics.ready and not r.diagnostics.source_cached and m.writes == 0)
end

test('cold Ship exact two offsets, identity and first/cached read costs', function()
    local m, r = memory(), reader()
    local value, why = r:read(m.world, PEER)
    assert(value and value.kills == 351885 and value.deaths == 4633)
    assert(why == 'native_career_counters' and value.status == why)
    assert(value.source == 'personal_career_native_counters')
    assert(value.identity.game == m.game and value.identity.state_context == m.context)
    assert(value.identity.local_user == m.user and value.identity.local_peer == PEER)
    assert(value.identity.counter_pointer == m.counter and value.local_peer == PEER)
    assert(value.page_required == false and not value.backend_ready and not value.server_ready)
    assert(not value.backend_refresh_verified and not value.atomic)
    assert(r.diagnostics.reads == 22 and r.diagnostics.bytes == 254 and #m.reads == 22)
    for _, call in ipairs(m.reads) do assert(call[1] ~= m.counter, 'uninterpreted header must not be read') end
    local n = #m.reads
    assert(r:read(m.world, PEER))
    assert(#m.reads - n == 14 and r.diagnostics.reads == 14 and r.diagnostics.bytes == 88)
    assert(m.writes == 0)
end)

test('reset and changed view/read identity revalidate names and PINs', function()
    local m, r = memory(), reader(); assert(r:read(m.world, PEER))
    local n = #m.reads; r:reset(); assert(r:read(m.world, PEER)); assert(#m.reads - n == 22)
    local read = m.world.view.read
    m.world.view = {read = read}; n = #m.reads
    assert(r:read(m.world, PEER)); assert(#m.reads - n == 22)
    m.world.view.read = function(at, size) return read(at, size) end
    m:put(m.game + M.pins[1].rva, '\0')
    reject(m, r, 'CAREER_COUNTER_CODE_MISMATCH')
end)

test('wrong build, nonlive world and malformed peer refuse zero IO', function()
    local m, r = memory(), reader(); local old = profile.dll_sha
    profile.dll_sha = 'wrong'; reject(m, r, 'CAREER_COUNTER_BUILD_MISMATCH'); profile.dll_sha = old
    assert(#m.reads == 0)
    m.world.runtime.mode = 'offline'; reject(m, r, 'CAREER_COUNTER_WORLD_UNAVAILABLE'); assert(#m.reads == 0)
    m.world.runtime.mode = 'live'
    for _, peer in ipairs({'bad', '0000000000000000', '06464E240E0D372Z'}) do
        local value, why = r:read(m.world, peer)
        assert(not value and why == 'CAREER_COUNTER_LOCAL_PEER_UNAVAILABLE' and #m.reads == 0)
    end
end)

test('nonShip performs only state reads and no peer/count/source work', function()
    for _, state in ipairs({0, 1, 2, 4, 5, 6}) do
        local m, r = memory(), reader()
        m:put(m.context + M.source.state_offset, b.encode(state, 'u32'))
        reject(m, r, 'CAREER_COUNTER_WAITING_FOR_SHIP')
        assert(#m.reads == 2 and r.diagnostics.bytes == 12)
    end
end)

test('nonlocal or changing peer withholds without touching other users', function()
    local m, r = memory(), reader(); m:put(m.user + M.source.local_peer, b.unhex('06464E240E0D372B'):reverse())
    reject(m, r, 'CAREER_COUNTER_LOCAL_PEER_CHANGED'); assert(#m.reads == 4)
    m, r = memory(), reader(); local n = 0
    m.on_read = function(at)
        if at == m.user + M.source.local_peer then
            n = n + 1; if n == 2 then m:put(at, b.unhex('06464E240E0D372B'):reverse()) end
        end
    end
    reject(m, r, 'CAREER_COUNTER_LOCAL_PEER_CHANGED')
end)

test('second state/context/pointer or value changes are withheld', function()
    for _, change in ipairs({'state', 'context', 'pointer', 'kills', 'deaths'}) do
        local m, r = memory(), reader(); local n = 0
        local at = change == 'state' and m.context + M.source.state_offset
            or change == 'context' and m.game + M.source.state
            or change == 'pointer' and m.game + M.source.counters
            or m.counter + (change == 'kills' and M.source.kills or M.source.deaths)
        m.on_read = function(address)
            if address == at then
                n = n + 1
                if n == 2 then
                    if change == 'state' then m:put(at, b.encode(4, 'u32'))
                    elseif change == 'context' then
                        m:put(at, ptr(m.context + 0x100000)); m:put(m.context + 0x100000 + M.source.state_offset, b.encode(3, 'u32'))
                    elseif change == 'pointer' then m:put(at, ptr(m.other_counter))
                    else m:put(at, b.encode(9, 'u32')) end
                end
            end
        end
        local expected = change == 'state' and 'CAREER_COUNTER_WAITING_FOR_SHIP'
            or (change == 'kills' or change == 'deaths') and 'CAREER_COUNTER_VALUES_CHANGED'
            or 'CAREER_COUNTER_IDENTITY_CHANGED'
        reject(m, r, expected)
    end
end)

test('exact true names and NUL required; unaligned string addresses permitted', function()
    for _, invalid in ipairs({'wrong', 'unterminated', 'zero_pointer'}) do
        local m, r = memory(), reader()
        if invalid == 'wrong' then m:put(m.names[1], 'x')
        elseif invalid == 'unterminated' then m:put(m.names[1], string.rep('x', 64))
        else m:put(m.game + M.source.names, ptr(0)) end
        reject(m, r, invalid == 'zero_pointer' and 'CAREER_COUNTER_NAME_POINTER' or 'CAREER_COUNTER_NAME_MISMATCH')
        for _, call in ipairs(m.reads) do assert(call[1] ~= m.counter + M.source.kills) end
    end
    local m, r = memory(), reader(); assert(m.names[1] % 8 ~= 0 and r:read(m.world, PEER))
    m:put(m.names[2], 'x'); r:reset(); reject(m, r, 'CAREER_COUNTER_NAME_MISMATCH')
end)

test('zero legal; high signed bit, null/unsafe pointer and short read are never values', function()
    local m, r = memory(), reader()
    m:put(m.counter + M.source.kills, b.encode(0, 'u32')); m:put(m.counter + M.source.deaths, b.encode(0, 'u32'))
    local value = assert(r:read(m.world, PEER)); assert(value.kills == 0 and value.deaths == 0)
    m, r = memory(), reader(); m:put(m.counter + M.source.deaths, b.encode(2147483648, 'u32'))
    reject(m, r, 'CAREER_COUNTER_VALUE_RANGE')
    m, r = memory(), reader(); m:put(m.game + M.source.counters, ptr(0)); reject(m, r, 'CAREER_COUNTER_UNAVAILABLE')
    m, r = memory(), reader(); m:put(m.game + M.source.counters, ptr(0x800000000000)); reject(m, r, 'CAREER_COUNTER_POINTER')
    m, r = memory(), reader(); m.short = m.counter + M.source.kills; reject(m, r, 'CAREER_COUNTER_READ_FAILED')
end)

test('byte/read/soft-time budgets checked before IO and final time included', function()
    local m, r = memory(), reader({max_bytes = 1}); reject(m, r, 'CAREER_COUNTER_READ_BUDGET'); assert(#m.reads == 0)
    m, r = memory(), reader({max_reads = 21}); reject(m, r, 'CAREER_COUNTER_READ_BUDGET'); assert(#m.reads == 21)
    local n = 0
    m, r = memory(), reader({clock = function() n = n + 1; return n == 1 and 0 or .003 end})
    reject(m, r, 'CAREER_COUNTER_TIME_BUDGET'); assert(#m.reads == 0)
    local now = 0; m, r = memory(), reader({clock = function() return now end})
    m.on_read = function() now = .003 end
    reject(m, r, 'CAREER_COUNTER_TIME_BUDGET'); assert(#m.reads == 1)
    assert(not pcall(M.new, {max_reads = 33}))
    assert(not pcall(M.new, {max_bytes = 513}))
    assert(not pcall(M.new, {seconds = .003}))
end)

test('clock invalid/throwing never escapes read or marks ready', function()
    for _, clock in ipairs({function() return 0/0 end, function() error('owned clock') end}) do
        local m, r = memory(), reader({clock = clock})
        reject(m, r, 'CAREER_COUNTER_CLOCK'); assert(#m.reads == 0)
    end
end)

print('native-career-counters: ' .. cases .. ' cases PASS; first22/254B cached14/88B; owned only, no Game/UI/write')
