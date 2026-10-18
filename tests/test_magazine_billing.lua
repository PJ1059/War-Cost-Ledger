local create = assert(loadfile(assert(arg[1])))()
local prices = {FUEL={id='EQ-054',unit_cents=30}, CLIP={id='EQ-001',unit_cents=10}}
local meter, checks = create(prices), 0
local function sample(resource, rounds, spares, options)
    options = options or {}
    return {world=1,mission=1,player=2,peer='peer',avatar=3,life=1,time=options.time or 0,
        reading={entity=options.entity or 4,resource=resource,
            reserve_mode=resource=='FUEL' and 'fuel' or 'magazine',
            state={rounds=rounds,working=options.working or rounds,spares=spares,
                capacity=options.capacity or 100,from=options.from or 'copy',
                chambered=options.chambered or 1,chamber_empty=options.empty or 0}}}
end
local function check(s, units, status)
    local result=meter:observe(s); checks=checks+1
    assert(result.units==units, checks..': '..result.units..' expected '..units)
    assert(not status or result.status==status, checks..': '..result.status)
    assert(result.cents==units*(s and s.reading and prices[s.reading.resource] and prices[s.reading.resource].unit_cents or 0))
    return result
end
check(sample('CLIP',100,3),0,'baseline')
check(sample('CLIP',80,3),20,'consumed') -- actual fired cartridges
check(sample('CLIP',100,2),80,'consumed') -- tactical reload discards 80, chamber retained
check(sample('CLIP',100,2),0,'unchanged')
check(sample('CLIP',0,2,{empty=1}),101,'consumed') -- full 100 + one in chamber
check(sample('CLIP',99,1),0,'unchanged') -- dry reload moves one cartridge into chamber
check(sample('CLIP',100,4),0,'refilled')
meter:reset()
check(sample('FUEL',100,3),0,'baseline')
check(sample('FUEL',92,3),8,'consumed')
check(sample('FUEL',100,2),92,'consumed') -- no +1 fuel chamber
check(sample('FUEL',0,2),100,'consumed')
check(sample('FUEL',100,1),0,'unchanged')
meter:reset()
check(sample('CLIP',20,3),0,'baseline')
check(sample('CLIP',0,2,{empty=1,time=100}),0,'unsettled') -- reserve removed before fill
check(sample('CLIP',100,2,{time=200}),20,'consumed')
meter:reset()
check(sample('CLIP',92,3),0,'baseline')
check(sample('CLIP',92,2,{time=100}),0,'unsettled') -- reserve decremented before old magazine removed
check(sample('CLIP',0,2,{time=200}),0,'unsettled') -- the existing chambered round is retained
check(sample('CLIP',100,2,{time=300}),92,'consumed')
meter:reset()
check(sample('CLIP',20,3),0,'baseline')
check(sample('CLIP',100,3,{time=100}),0,'unsettled') -- fill before reserve decrement
check(sample('CLIP',100,2,{time=200}),20,'consumed')
meter:reset()
check(sample('FUEL',20,3),0,'baseline')
check(sample('FUEL',0,3,{working=20,time=100}),0,'unsettled')
check(sample('FUEL',100,2,{time=200}),20,'consumed')
check(sample('FUEL',95,2,{entity=5,time=300}),0,'baseline') -- switch/new generation
check(nil,0,'missing')
check(sample('FUEL',80,2),0,'baseline') -- no back-charge across an unreadable gap
local dead=sample('FUEL',50,2); dead.life=2; check(dead,0,'baseline')
check(sample('FUEL',30,2,{capacity=200}),0,'baseline')
meter:reset()
check(sample('FUEL',50,3),0,'baseline')
check(sample('FUEL',0,2,{working=50,time=100}),0,'unsettled')
check(sample('FUEL',0,2,{working=50,time=2201}),0,'unsettled')
check(sample('FUEL',100,2,{time=2300}),0,'baseline') -- do not retain stale reload indefinitely
local ally=sample('FUEL',90,2); ally.peer='other'; check(ally,0,'baseline')
local invalid=sample('FUEL',110,2); check(invalid,0,'invalid')
check(sample('FUEL',80,2),0,'baseline')
print('PASS: '..checks..' magazine/fuel billing cases; shots+discard, chamber, refill, both reload phases, gaps, identity and stale samples.')
