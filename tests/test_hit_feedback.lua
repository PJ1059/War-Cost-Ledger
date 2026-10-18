local create = dofile(assert(arg[1]))
local tests = 0
local function check(name, fn)
    local ok, why = pcall(fn); assert(ok, name .. ': ' .. tostring(why))
    tests = tests + 1; print('PASS ' .. name)
end
local function contact(result, n)
    return {verified = true, local_player = true, direct = true, attack = 'projectile', result = result, count = n or 1}
end
check('rapid same-type hits keep one stable numeric slot', function()
    local f = create(); local recent, cumulative = f.recent, f.cumulative
    for i = 1, 1000 do assert(f:accept(contact('ricochet'), i / 1000)) end
    assert(f.recent == recent and f.cumulative == cumulative)
    assert(f.recent.ricochet == 1000 and f.cumulative.total == 1000)
    local slots = 0; for _ in pairs(f.recent) do slots = slots + 1 end; assert(slots == 9)
end)
check('exact two-second collection; a new hit refreshes the deadline', function()
    local f = create(); assert(f:accept(contact('penetration', 2), 1))
    assert(f:visible(2.999, false, true).penetration == 2)
    assert(f:accept(contact('blocked', 4), 2.999))
    assert(f:visible(4.998, false, true).total == 6)
    assert(f:visible(5, false, true) == nil and f.cumulative.total == 6)
    assert(f:accept(contact('ricochet'), 5.1)); assert(f.recent.total == 1)
    assert(f.cumulative.total == 7 and f.recent.blocked == 0)
end)
check('map and HUD visibility keep match totals; reset starts a new match', function()
    local f = create(); f:accept(contact(nil, 3), 1)
    assert(f:visible(1.1, false, false) == nil)
    f:accept(contact('full_penetration', 2), 1.2)
    assert(f:visible(10, true, true).total == 5)
    assert(f:visible(10, false, true) == nil)
    f:reset(); assert(f.cumulative.total == 0 and f.last_hit == nil)
end)
check('overlapping head, part and penetration information count one contact once', function()
    local f = create(); local c = contact('penetration')
    c.weakpoint, c.part_destroyed, c.through = true, true, true
    assert(f:accept(c, 1)); assert(f.cumulative.total == 1)
    assert(f.cumulative.penetration == 1 and f.cumulative.weakpoint == 1
        and f.cumulative.part_destroyed == 1 and f.cumulative.through == 1)
end)
check('unclassified projectile growth stays total-only; melee does not imply a kill', function()
    local f = create(); f:accept(contact(nil, 7), 1)
    local c = contact(); c.attack = 'melee'; assert(f:accept(c, 1.1))
    assert(f.cumulative.total == 8 and f.cumulative.melee == 1)
    assert(f.cumulative.penetration == 0 and f.cumulative.ricochet == 0)
end)
check('armor blocking and physical ricochet overlap without counting the contact twice', function()
    local f = create(); local c = contact('blocked'); c.ricochet = true
    f:accept(c, 1); assert(f.cumulative.total == 1 and f.cumulative.blocked == 1 and f.cumulative.ricochet == 1)
    c = contact('ricochet'); c.ricochet = true
    f:accept(c, 1.1); assert(f.cumulative.total == 2 and f.cumulative.ricochet == 2)
end)
check('spray, burning, ground fire and area blasts do not extend the timer', function()
    local f = create(); f:accept(contact(), 1)
    for _, mode in ipairs({'spray', 'burning', 'ground_fire', 'explosion_area'}) do
        local c = contact(); c.mode = mode; assert(not f:accept(c, 2.9))
    end
    assert(f.last_hit == 1 and f:visible(3, false, true) == nil and f.cumulative.total == 1)
end)
check('unverified, remote, indirect and invalid samples cannot create feedback', function()
    local f = create()
    for _, key in ipairs({'verified', 'local_player', 'direct'}) do
        local c = contact(); c[key] = false; assert(not f:accept(c, 1))
    end
    assert(not f:accept(contact('guessed_class'), 1))
    assert(not f:accept(contact(nil, -1), 1)); assert(not f:accept(contact(nil, 1.5), 1))
    assert(not f:accept(contact(), 0/0)); assert(not f:accept(contact(), math.huge))
    assert(f.cumulative.total == 0)
end)
print('Hit-feedback prototype: ' .. tests .. ' checks passed; synthetic contacts only')
