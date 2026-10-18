-- Same-build SDK ownership and actual Runtime Inventory/Deposit layouts, no game IO.
local source,fixture,runtime,billing=assert(arg[1]),assert(arg[2]),assert(arg[3]),assert(arg[4])
local old=arg;HD2_CONSUMABLE_FIXTURE_ONLY=true;arg={source,runtime}
local f=dofile(fixture);arg=old;HD2_CONSUMABLE_FIXTURE_ONLY=nil
local D=require('hd2runtime/domains/player_equipment');local I,P=D.inventory,D.deposit
local b=require('hd2runtime/core/bytes')
local MODERN,LEGACY,PACK='78A8185F63A70795','0736BEE2D6328726','43EB1C3C1A1860E0'
local price={id='EQ-113',unit_cents=30,inventory_mode='fuel',inventory_storage='paired_deposit'}
local function memory()
    local m=f.memory(false,MODERN)
    local inv,ids,who,rows=0x440000000,0x441000000,0x442000000,0x443000000
    local dep,descs,desc,states=0x450000000,0x451000000,0x452000000,0x453000000
    m:put(m.game+I.global,f.ptr(inv));m:hash(inv,I.hash,m.avatar,2)
    m:put(inv+I.descriptors,f.ptr(ids));m:put(ids+16,f.ptr(who))
    m:put(who,string.rep('\0',8)..f.u32(m.avatar)..f.u32(29)..f.u32(40)..f.u32(1))
    m:put(inv+I.records,f.ptr(rows));m.pack_at=rows+2*I.stride+I.slots.backpack
    m:put(m.pack_at,f.u32(88))
    m:put(m.game+P.global,f.ptr(dep));m:hash(dep,P.hash,88,3)
    m:put(dep+P.descriptors,f.ptr(descs));m:put(descs+24,f.ptr(desc))
    m:put(desc,b.unhex(PACK):reverse()..f.u32(88)..f.u32(29)..f.u32(40)..f.u32(1))
    m:put(dep+P.live,f.ptr(states));m.pack_remaining=states+3*P.liveStride+P.amount
    m.pack_desc=desc
    local file=assert(io.open(source,'rb'));local text=file:read('*a');file:close()
    for rva,hex in text:gmatch("{rva=(%d+),hex='([%x]+)'}")do m:put(m.game+tonumber(rva),b.unhex(hex))end
    function m:stock(n)self:put(self.pack_remaining,f.u32(n))end
    m:stock(500)
    m.bill=dofile(billing)({[MODERN]=price});m.reader=m:reader(nil,{[MODERN]=price})
    function m:observe(t)
        local reading,why=self.reader:read(self.world,self.player);assert(reading,why)
        return self.bill:observe({world='world',mission=1,player=10,peer='peer',avatar=self.avatar,
            life=1,time=t,reading=reading}),reading
    end
    return m
end
local checks=0
local function check(fn)fn();checks=checks+1 end
check(function()
    local m=memory();local out,r=m:observe(0)
    assert(out.status=='baseline' and out.cents==0 and r.state.remaining==500)
    assert(r.reserve_mode=='backpack_fuel' and r.state.pack_entity==88)
    m:stock(490);out=m:observe(100);assert(out.units==10 and out.cents==300)
    m:stock(500);out=m:observe(200);assert(out.status=='refilled' and out.units==0)
    m:stock(498);out=m:observe(300);assert(out.units==2 and out.cents==60)
    m:stock(0);out=m:observe(400);assert(out.units==498 and out.cents==14940)
    assert(m.writes==0 and m.reader.diagnostics.operations_peak<=64)
    print('backpack proof/steady <= '..m.reader.diagnostics.operations_peak..' reads / '..m.reader.diagnostics.read_peak..' bytes')
end)
check(function()
    local m=memory();m:put(m.pack_at,f.u32(0))
    local r,why=m.reader:read(m.world,m.player);assert(not r and why=='PACK_NOT_EQUIPPED')
end)
check(function()
    local m=memory();m:put(m.pack_desc,b.unhex('1122334455667788'):reverse()..f.u32(88)..string.rep('\0',12))
    local r,why=m.reader:read(m.world,m.player);assert(not r and why=='PACK_DEPOSIT_TYPE')
end)
check(function()
    local m=memory();local n=0
    m.fault=function(at)if at==m.pack_remaining then n=n+1;if n==2 then return f.u32(499)end end end
    local r,why=m.reader:read(m.world,m.player);assert(not r and why=='PACK_CHANGED')
end)
check(function()
    local m=memory();m:put(m.game+5456206,string.rep('x',128))
    local r,why=m.reader:read(m.world,m.player);assert(not r and why=='PACK_CODE_PIN_CHANGED')
end)
check(function()
    local m=f.memory(false,LEGACY)
    local r,why=m:reader(nil,{[LEGACY]=price}):read(m.world,m.player)
    assert(r,why);assert(r.reserve_mode=='fuel' and r.state.capacity==100)
    assert(r.state.spares==3 and r.state.rounds==60 and m.writes==0)
end)
print('PASS: '..checks..' B/FLAM-80 paired-deposit/legacy-magazine consume/refill/zero/sparse-row/type/race/pin checks')
