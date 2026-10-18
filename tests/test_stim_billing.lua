local create = dofile(assert(arg[1]))
local KEY, checks = 0xC8256789, 0
local function sample(n)
    return {world = 'world:exe', mission = 17, player = 0x10001,
        peer = '06464E240E0D372A', stats = {totals = {[KEY] = n}, main = {}, sources = {}}}
end
local function test(name, fn)
    local ok, why = pcall(fn); assert(ok, name .. ': ' .. tostring(why))
    checks = checks + 1
end
local function expect(observer, value, units, status)
    local result = observer:observe(value)
    assert(result.units == units and result.cents == units * 2500)
    if status then assert(result.status == status, result.status .. ' ~= ' .. status) end
    return result
end
local function observer() return create({key = KEY, unit_cents = 2500}) end

test('native baseline then 0 to 1 to 3; duplicates do not charge', function()
    local o = observer(); expect(o, sample(0), 0, 'baseline')
    expect(o, sample(1), 1, 'consumed'); expect(o, sample(3), 2, 'consumed')
    for i = 1, 100 do expect(o, sample(3), 0, 'unchanged') end
end)
test('late join displays first native value without back charging', function()
    local o = observer(); assert(expect(o, sample(6), 0, 'baseline').current == 6)
    expect(o, sample(7), 1, 'consumed')
end)
test('death or avatar replacement does not break this player mission counter', function()
    local o = observer(); local s = sample(1); s.avatar, s.life = 99, 1
    expect(o, s, 0, 'baseline')
    s = sample(2); s.avatar, s.life = nil, 2; expect(o, s, 1, 'consumed')
    s = sample(3); s.avatar, s.life = 222, 3; expect(o, s, 1, 'consumed')
end)
test('world mission player and peer changes each force a fresh baseline', function()
    for field, value in pairs({world = 'new', mission = 18, player = 0x10002, peer = '0123456789ABCDEF'}) do
        local o = observer(); expect(o, sample(2), 0)
        local s = sample(9); s[field] = value; expect(o, s, 0, 'baseline')
        s.stats.totals[KEY] = 10; expect(o, s, 1, 'consumed')
    end
end)
test('full peer uses exact string with hex case normalization', function()
    local o = observer(); expect(o, sample(1), 0)
    local s = sample(2); s.peer = s.peer:lower(); expect(o, s, 1)
    for _, peer in ipairs({'', '0', '06464E240E0D372X', '0000000000000000', 12345}) do
        s = sample(99); s.peer = peer; expect(o, s, 0, 'identity')
        expect(o, sample(100), 0, 'baseline')
    end
end)
test('exact totals only, no second main or source addition', function()
    local o = observer(); local s = sample(3)
    s.stats.main[KEY] = 1; s.stats.sources.weapon = {[KEY] = 2}; expect(o, s, 0)
    s.stats.totals[KEY], s.stats.main[KEY] = 4, 2; expect(o, s, 1)
end)
test('healing and received P11 or resupply alone do not charge a stim', function()
    local o = observer(); expect(o, sample(0), 0)
    local s = sample(0); s.health_gain, s.stock, s.received_p11 = 420, 6, true
    s.stats.sources.D6B1FB05B9109353 = {[1448579290] = 7}
    expect(o, s, 0, 'unchanged')
end)
test('unreadable missing invalid values clear only this observer baseline', function()
    for _, bad in ipairs({false, -1, 0.5, math.huge, 0 / 0, 2147483648}) do
        local o = observer(); expect(o, sample(3), 0)
        expect(o, sample(bad), 0, 'invalid'); expect(o, sample(9), 0, 'baseline')
        expect(o, sample(10), 1, 'consumed')
    end
    for _, variant in ipairs({'sample', 'stats', 'totals', 'key'}) do
        local o = observer(); expect(o, sample(3), 0)
        local s = sample(4)
        if variant == 'sample' then s = nil elseif variant == 'stats' then s.stats = nil
        elseif variant == 'totals' then s.stats.totals = nil else s.stats.totals[KEY] = nil end
        expect(o, s, 0, 'missing'); expect(o, sample(9), 0, 'baseline')
    end
end)
test('rollback reset and nil identity never refund or reuse stale baseline', function()
    local o = observer(); expect(o, sample(3), 0); expect(o, sample(5), 2)
    expect(o, sample(0), 0, 'reset'); expect(o, sample(1), 1)
    o:reset(); expect(o, sample(9), 0, 'baseline')
    for _, field in ipairs({'world', 'mission', 'player', 'peer'}) do
        local s = sample(99); s[field] = nil; expect(o, s, 0, 'identity')
        expect(o, sample(100), 0, 'baseline')
    end
end)
test('independent configured price and copied identity', function()
    local o = create({unit_cents = 100}); local s = sample(2); o:observe(s)
    s.mission = 100; assert(o:observe(s).units == 0)
    s.stats.totals[KEY] = 3; local r = o:observe(s); assert(r.units == 1 and r.cents == 100)
    for _, price in ipairs({-1, 0.5, math.huge}) do assert(not pcall(create, {unit_cents = price})) end
end)
print('PASS: ' .. checks .. ' stim billing groups; standard native stat, no healing inference, lifecycle and duplicate guards; no process IO.')
