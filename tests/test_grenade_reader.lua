-- Actual Runtime domain and native-view fixture; never connects to a game process.
local source,fixture,runtime=assert(arg[1]),assert(arg[2]),assert(arg[3])
local old=arg;HD2_CONSUMABLE_FIXTURE_ONLY=true
arg={fixture:gsub('tests/test_consumable_reader.lua$','src/consumable-reader.lua'),runtime}
local f=dofile(fixture);arg=old;HD2_CONSUMABLE_FIXTURE_ONLY=nil
local D=require('hd2runtime/domains/player_equipment');local I=D.inventory
local factory=dofile(source)
local GAS='0416984F4922757B'
local function memory(resource,count)
    local m=f.memory(false)
    local manager,records,counts,descs,desc=0x410000000,0x411000000,0x412000000,0x413000000,0x414000000
    m.inventory,m.inv_records,m.inv_counts,m.inv_desc=manager,records,counts,desc
    m:put(m.game+I.global,f.ptr(manager));m:hash(manager,I.hash,m.avatar,0)
    m:put(manager+I.records,f.ptr(records));m:put(manager+I.counts,f.ptr(counts))
    m:put(manager+I.descriptors,f.ptr(descs));m:put(descs,f.ptr(desc))
    m:put(desc,string.rep('\0',8)..f.u32(m.avatar)..string.rep('\0',8)..f.u32(1))
    for _,pin in ipairs(D.pins)do m:put(m.game+pin.rva,require('hd2runtime/core/bytes').unhex(pin.hex))end
    function m:grenades(kind,n)
        self:put(records+I.throwable,require('hd2runtime/core/bytes').unhex(kind):reverse())
        self:put(counts,f.u32(n))
    end
    m:put(records+I.slots.held,f.u32(0))
    m:grenades(resource or GAS,count or 4)
    function m:grenade_reader(options)
        options=options or {};options.clock=options.clock or function()return 0 end
        return factory(f.world_api,options)
    end
    return m
end
local function hand(m,kind)
    local N=f.N.wielder
    m:put(m.inv_records+I.slots.held,f.u32(m.entity))
    m:put(m.entity_manager+N.descriptors,require('hd2runtime/core/bytes').unhex(kind):reverse()
        ..f.u32(m.entity)..f.u32(29)..f.u32(40)..f.u32(1))
end
if HD2_GRENADE_FIXTURE_ONLY then return {memory=memory,source_fixture=f,D=D,GAS=GAS}end
local passed=0
local function check(fn)fn();passed=passed+1 end
check(function()
    local m=memory();local reader=m:grenade_reader()
    local got,why=reader:read(m.world,m.player);assert(got,why)
    assert(got.resource==GAS and got.count==4 and got.avatar==m.avatar)
    assert(reader.diagnostics.operations<=64 and reader.diagnostics.bytes<=4096 and m.writes==0)
    print('grenade first proof/read: '..reader.diagnostics.operations..' operations / '..reader.diagnostics.bytes..' bytes')
    m.reads={};m:grenades(GAS,3);got=assert(reader:read(m.world,m.player));assert(got.count==3)
    assert(reader.diagnostics.operations==#m.reads and #m.reads<30)
    print('grenade steady read: '..reader.diagnostics.operations..' operations / '..reader.diagnostics.bytes..' bytes')
end)
check(function()
    local m=memory(GAS,0);local got=assert(m:grenade_reader():read(m.world,m.player));assert(got.count==0)
    m:grenades('6B11FC757618C57E',6);got=assert(m:grenade_reader():read(m.world,m.player));assert(got.count==6)
end)
check(function()
    local m=memory();m.player['local']=false;local got,why=m:grenade_reader():read(m.world,m.player)
    assert(not got and why=='NOT_LOCAL_AVATAR' and #m.reads==0)
end)
check(function()
    for _,value in ipairs({0,2})do local m=memory();m:put(m.inv_desc,string.rep('\0',8)..f.u32(m.avatar)..string.rep('\0',8)..f.u32(value))
        local got,why=m:grenade_reader():read(m.world,m.player);assert(not got and why=='GRENADE_AVATAR_OWNERSHIP')end
end)
check(function()
    local m=memory();m:put(m.inv_desc,string.rep('\0',8)..f.u32(m.avatar+1)..string.rep('\0',8)..f.u32(1))
    local got,why=m:grenade_reader():read(m.world,m.player);assert(not got and why=='GRENADE_AVATAR_OWNERSHIP')
end)
check(function()
    local m=memory();m:put(m.game+D.pins[99].rva,string.rep('\0',#D.pins[99].hex/2))
    local got,why=m:grenade_reader():read(m.world,m.player);assert(not got and why=='GRENADE_CODE_PIN_CHANGED')
end)
check(function()
    local m=memory(GAS,10001);local got,why=m:grenade_reader():read(m.world,m.player)
    assert(not got and why=='GRENADE_INVALID_COUNT')
end)
check(function()
    local m=memory();local n=0
    m.fault=function(at)if at==m.inv_counts then n=n+1;if n==2 then return f.u32(3)end end end
    local got,why=m:grenade_reader():read(m.world,m.player);assert(not got and why=='GRENADE_INVENTORY_CHANGED')
end)
check(function()
    local m=memory();m.fault=function(at)if at==m.inv_records+I.throwable then return false end end
    local got,why=m:grenade_reader():read(m.world,m.player);assert(not got and why=='GRENADE_READ_FAILED')
end)
check(function()
    local m=memory();local now=0
    local reader=m:grenade_reader({clock=function()now=now+.0006;return now end})
    local got,why=reader:read(m.world,m.player);assert(not got and why=='GRENADE_TIME_BUDGET')
end)
check(function()
    local m=memory(GAS,3);hand(m,GAS)
    local got,why=m:grenade_reader():read(m.world,m.player);assert(got,why)
    assert(got.count==4 and got.reserve==3 and got.held_count==1 and got.held_entity==m.entity)
    assert(m.writes==0)
    m:put(m.inv_records+I.slots.held,f.u32(0))
    got=assert(m:grenade_reader():read(m.world,m.player));assert(got.count==3 and got.held_count==0)
end)
check(function()
    local m=memory(GAS,3);hand(m,'1122334455667788')
    local got,why=m:grenade_reader():read(m.world,m.player);assert(got,why)
    assert(got.count==3 and got.held_count==0)
end)
check(function()
    local m=memory(GAS,3);hand(m,GAS);local n=0
    m.fault=function(at)if at==m.inv_records+I.slots.held then n=n+1;if n==2 then return f.u32(0)end end end
    local got,why=m:grenade_reader():read(m.world,m.player);assert(not got and why=='GRENADE_INVENTORY_CHANGED')
end)
check(function()
    local bill_path=source:gsub('grenade%-reader.lua$','grenade-billing.lua')
    local bill=dofile(bill_path)({[GAS]={id='EQ-127',unit_cents=18000}})
    local m=memory(GAS,4);local reader=m:grenade_reader()
    local function observe(t,expected)
        local reading,why=reader:read(m.world,m.player);assert(reading,why)
        local result=bill:observe({world='world',mission=1,player=10,peer='peer',avatar=m.avatar,
            life=1,time=t,reading=reading})
        assert(result.units==expected,result.status..':'..result.units)
    end
    observe(0,0)
    -- Pull out: reserve 4 -> 3, exact matching in-hand grenade 0 -> 1.
    m:grenades(GAS,3);hand(m,GAS);observe(100,0);observe(200,0)
    -- Cancel without throwing, return that grenade to reserve.
    m:grenades(GAS,4);m:put(m.inv_records+I.slots.held,f.u32(0));observe(300,0)
    -- Pull out again, then actually release. Only the release costs 180 MC.
    m:grenades(GAS,3);hand(m,GAS);observe(400,0)
    m:put(m.inv_records+I.slots.held,f.u32(0));observe(500,1);observe(600,0)
end)
print('PASS: '..passed..' actual Runtime grenade resource/count/ownership/pin/race/budget checks; no native calls/writes')
