local factory=dofile(assert(arg[1]))
local GAS,HE,KNIFE='0416984F4922757B','6B11FC757618C57E','F7B35A9C5AE340B6'
local prices={[GAS]={id='EQ-127',unit_cents=18000},[HE]={id='EQ-116',unit_cents=4500}}
local checks=0
local function sample(n,kind,t)
    return {world='game:exe',mission=2,player=5,peer='FEDCBA9876543210',avatar=17,life=1,
        time=t or 0,reading={resource=kind or GAS,count=n}}
end
local bill=factory(prices)
local function expect(s,units,status)
    local out=bill:observe(s);checks=checks+1
    assert(out.units==units and (not status or out.status==status),checks..':'..out.status..'/'..out.units)
    assert(out.cents==units*(s and s.reading and prices[s.reading.resource] or {unit_cents=0}).unit_cents)
    return out
end
expect(sample(4),0,'baseline');expect(sample(3,GAS,100),1,'consumed')
expect(sample(3,GAS,200),0,'unchanged');expect(sample(0,GAS,300),3,'consumed')
expect(sample(6,GAS,400),0,'refilled');expect(sample(5,GAS,500),1,'consumed')
expect(sample(2,HE,600),0,'baseline');expect(sample(1,HE,700),1,'consumed')
expect(sample(3,KNIFE,800),0,'missing');expect(sample(2,KNIFE,900),0,'missing')
expect(sample(4,GAS,1000),0,'baseline');expect(nil,0,'missing');expect(sample(3,GAS,1100),0,'baseline')
for _,key in ipairs({'world','mission','player','peer','avatar','life'})do
    bill:reset();expect(sample(4),0,'baseline')
    local s=sample(3,GAS,100);s[key]=type(s[key])=='number' and s[key]+1 or s[key]..'-new'
    expect(s,0,'baseline')
end
bill:reset();expect(sample(4),0);expect(sample(1,GAS,501),0,'baseline')
expect(sample(0,GAS,400),0,'baseline')
bill:reset();expect(sample(4),0);local bad=sample(-1,GAS,100);expect(bad,0,'missing')
expect(sample(2,GAS,200),0,'baseline');bill:reset();expect(sample(1,GAS,300),0,'baseline')
print('PASS: '..checks..' grenade billing checks: exact decrements, zero/refill, type/life/peer/gap reset, knife excluded')
