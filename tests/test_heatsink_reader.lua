-- Real Runtime domains and bounded native memory fixture; no game process.
local source,fixture,runtime,billing=assert(arg[1]),assert(arg[2]),assert(arg[3]),assert(arg[4])
local old=arg;HD2_CONSUMABLE_FIXTURE_ONLY=true;arg={source,runtime}
local f=dofile(fixture);arg=old;HD2_CONSUMABLE_FIXTURE_ONLY=nil
local b=require('hd2runtime/core/bytes')
local resource='8645F167B3C813A2'
local price={id='EQ-044-HEATSINK',unit_cents=7500,inventory_mode='heatsink'}
local function memory(index)
    index=index or 0
    local m=f.memory(false,resource)
    local heat,states,descs,desc=0x430000000,0x431000000,0x432000000,0x433000000
    m:put(m.game+0x3326D48,f.ptr(heat));m:put(heat+20,f.u32(1))
    m:hash(heat,40,m.entity,index)
    m:put(heat+64,f.ptr(descs));m:put(descs+index*8,f.ptr(desc))
    m:put(desc,b.unhex(resource):reverse()..f.u32(m.entity)..f.u32(29)..f.u32(40)..f.u32(1))
    m:put(heat+88,f.ptr(states))
    local file=assert(io.open(source,'rb'));local text=file:read('*a');file:close()
    for rva,hex in text:gmatch("{rva=(%d+),hex='([%x]+)'}")do m:put(m.game+tonumber(rva),b.unhex(hex))end
    function m:stock(n,heat_value)
        self:put(states+index*12,f.u32(n)..b.encode(heat_value or 0,'f32')..f.u32(0))
    end
    m:stock(3,0)
    m.heat_desc,m.heat_states=desc,states+index*12
    m.bill=dofile(billing)({[resource]=price})
    m.reader=m:reader(nil,{[resource]=price})
    function m:observe(t)
        local reading,why=self.reader:read(self.world,self.player);assert(reading,why)
        local out=self.bill:observe({world='world',mission=1,player=10,peer='peer',avatar=self.avatar,
            life=1,time=t,reading=reading})
        return out,reading
    end
    return m
end
local checks=0
local function check(fn)fn();checks=checks+1 end
check(function()
    local m=memory();local out,r=m:observe(0)
    assert(out.status=='baseline' and out.cents==0 and r.state.spares==3 and r.state.from=='heat')
    assert(r.reserve_mode=='heatsink' and r.state.rounds==nil)
    m:stock(3,85);out=m:observe(100);assert(out.units==0)
    m:stock(3,0);out=m:observe(200);assert(out.units==0) -- normal cooling is free
    m:stock(2,0);out=m:observe(300);assert(out.units==1 and out.cents==7500)
    m:stock(3,0);out=m:observe(400);assert(out.status=='refilled' and out.units==0)
    m:stock(2,0);out=m:observe(500);assert(out.units==1 and out.cents==7500)
    assert(m.writes==0 and m.reader.diagnostics.operations_peak<=48)
    print('heat proof/steady <= '..m.reader.diagnostics.operations_peak..' reads / '..m.reader.diagnostics.read_peak..' bytes')
end)
check(function()
    local m=memory();m:observe(0)
    m:put(m.heat_desc,b.unhex(resource):reverse()..f.u32(m.entity)..f.u32(29)..f.u32(40)..f.u32(0))
    local r,why=m.reader:read(m.world,m.player);assert(not r and why=='HEAT_OWNERSHIP')
end)
check(function()
    local m=memory();m:put(m.game+7616912,string.rep('x',256))
    local r,why=m.reader:read(m.world,m.player);assert(not r and why=='HEAT_CODE_PIN_CHANGED')
end)
check(function()
    local m=memory();m:stock(10001,0)
    local r,why=m.reader:read(m.world,m.player);assert(not r and why=='HEAT_INVALID_RESERVE')
end)
check(function()
    local m=memory();local n=0
    m.fault=function(at)if at==m.heat_states then n=n+1;if n==2 then return f.u32(2)end end end
    local r,why=m.reader:read(m.world,m.player);assert(not r and why=='HEAT_CHANGED')
end)
check(function()local m=memory(3);local out=m:observe(0);assert(out.status=='baseline')end)
print('PASS: '..checks..' heatsink replacement/refill/cooling/ownership/pin/race checks; no native calls/writes')

