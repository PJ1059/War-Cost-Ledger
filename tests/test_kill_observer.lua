-- Production observer with the existing native-memory boundary fixture.
local observer_path,runtime_root,fixture=assert(arg[1]),assert(arg[2]),assert(arg[3])
local input=assert(io.open(fixture,'rb'));local source=input:read('*a'):gsub('\r\n','\n');input:close()
local start=assert(source:find('state=dofile(path).state',1,true))
local scenario=[[
local create=dofile(path)
local api=require('hd2runtime/runtime/event_world')
local TYPE,OTHER,ASSET='D1E990BAF22D5A52','F540CA9D9D4A422E','74E2285C01DA4F71'
local catalog={[TYPE]={kill=true,asset=false},[OTHER]={kill=true,asset=false},[ASSET]={kill=false,asset=true}}
local deaths,corpses,local_total,epoch,readable={}, {}, 0, 1, true
local native_cause,cause_pin_ok=false,true
local cause_pins={{0x925E38,'f6411401'},{0x925E42,'488b8360100000'},
    {0x925E49,'486bfe1c'},{0x925E58,'448974070c'},
    {0x925E99,'89040f'},{0x925EC9,'89440f04'}}
local old_read,old_fill,old_pointer=view.read,view.fill,view.pointer
function view.pointer(address)
    if native_cause and address>=3 and(address-3)%8==0 then
        local a=actors[(address-3)/8+1];if a then return a.pointer end
    end
    for _,row in pairs(corpses)do if address==900000+row.index*8 then return row.pointer end end
    return old_pointer(address)
end
function view.read(pointer,size)
    if native_cause then
        for _,pin in ipairs(cause_pins)do if pointer==world.game+pin[1]then
            return cause_pin_ok and b.unhex(pin[2])or string.rep('\0',#pin[2]/2)
        end end
        if pointer>=700000 and(pointer-700000)%H.extStride==0 then
            local a=actors[(pointer-700000)/H.extStride+1]
            if a and a.cause then
                a.cause_reads=(a.cause_reads or 0)+1
                local c=a.cause
                local element=a.cause_race and a.cause_reads>1 and 5 or c.element
                return b.encode(c.kind,'u32')..b.encode(element,'u32')..b.encode(0,'u32')
                    ..b.encode(c.life or 2,'u32')..string.rep('\0',12)
            end
        end
    end
    local raw=old_read(pointer,size)
    if raw then for _,a in ipairs(actors)do if a.pointer==pointer then
        local value=a.unit or a.id*7
        raw=raw:sub(1,H.descriptor.unit)..b.encode(value,'u32')..raw:sub(H.descriptor.unit+5)
        raw=raw:sub(1,H.descriptor.flags)..b.encode(a.owned and 1 or 0,'u32')..raw:sub(H.descriptor.flags+5)
    end end end
    if not raw then for _,row in pairs(corpses)do if pointer==row.pointer then
        raw=string.rep('\0',size)
        local function set(offset,value)raw=raw:sub(1,offset)..b.encode(value,'u32')..raw:sub(offset+5)end
        local kind=row.kind or '0000000000000001'
        set(H.descriptor.type,tonumber(kind:sub(9),16));set(H.descriptor.type+4,tonumber(kind:sub(1,8),16))
        set(H.descriptor.entity,row.id);set(H.descriptor.unit,row.unit)
    end end end
    return raw
end
local old_header=api.health_header
api.health_header=function(...)
    local h=old_header(...);if h and native_cause then h.ext=700000 end;return h
end
function view.fill(block,address,size)
    local result=old_fill(block,address,size)
    if result and address==2 then
        local prior=result.u32
        result.u32=function(self,offset)
            if offset%H.stride==H.record.health then local a=actors[math.floor(offset/H.stride)+1];return a and a.health or 100 end
            return prior(self,offset)
        end
    end
    return result
end
api.corpses=function()
    if not readable then return nil end
    local origins={};for id,row in pairs(corpses)do origins[id]=row.index end
    return {origins=origins,descriptors=900000}
end
api.corpse_entity=function(_,_,index,unit)
    for _,row in pairs(corpses)do if row.index==index and row.unit==unit then return row.id end end
end
local observer=create(api,native,catalog,function(event)deaths[#deaths+1]=event end,{local_kills=function()return local_total end})
local players={{['local']=true,peer='0000000000000011'}}
local function tick(n,dt)for _=1,n or 1 do observer:poll(world,players,dt or .1,epoch)end end
local function actor(kind)
    next_id=next_id+1
    local a={id=next_id,pointer=100000+next_id*256,kind=kind or TYPE,life=0,health=100,credit=0}
    actors[#actors+1]=a;return a
end
local function corpse(a,unit)
    for i,row in ipairs(actors)do if row==a then table.remove(actors,i);break end end
    corpses[a.id]={index=a.id,unit=unit or a.id*7,id=a.id+10000,pointer=800000+a.id*64}
end
local function reset()
    observer:reset();actors,corpses,deaths={}, {}, {};local_total,epoch,health_readable,readable=0,1,true,true
    native_cause,cause_pin_ok=false,true;world.game=1;tick()
end
local function locals()local n=0;for _,event in ipairs(deaths)do if event.local_killer then n=n+1 end end;return n end
reset()
local a=actor();tick();a.life,a.credit,local_total=2,0x11,1;tick()
assert(#deaths==1 and deaths[1].native_creditor_verified==true and not deaths[1].inferred)
local missing=actor();tick();missing.life=2;tick(10)
assert(locals()==1,'direct local creditor must consume its native quota; no second missing-peer kill')
reset()
local other,missing=actor(),actor();tick();other.life,other.credit,missing.life,local_total=2,0x22,2,1;tick(4)
assert(#deaths==2 and deaths[1].entity_id==other.id and deaths[1].local_killer==false)
assert(deaths[1].killer_peer=='0000000000000022' and deaths[2].entity_id==missing.id)
assert(deaths[2].inferred==true and deaths[2].native_creditor_verified==false and deaths[2].killer_peer==nil)
assert(deaths[2].observed=='dead_state' and locals()==1,'never relabel an explicit other-peer kill')
reset()
local missing=actor();tick();missing.life=2;tick();assert(#deaths==0)
local_total=1;tick(4)
assert(locals()==1,'a slightly later native counter can fund an observed missing-peer death')
reset()
local direct_actor,missing=actor(),actor();tick();direct_actor.life,direct_actor.credit=2,0x11;tick()
missing.life,local_total=2,1;tick(10)
assert(locals()==1,'later native growth first pays an earlier direct-credit death')
reset()
local a=actor();tick();corpse(a);local_total=1;tick(4)
assert(#deaths==1 and deaths[1].observed=='corpse' and deaths[1].entity_id==a.id)
assert(deaths[1].type==TYPE and deaths[1].corpse_entity_id==a.id+10000 and deaths[1].life_epoch==1)
assert(deaths[1].inferred and not deaths[1].native_creditor_verified and deaths[1].killer_peer==nil)
tick(10);assert(#deaths==1,'a retained corpse cannot replay')
reset()
local disappeared,mismatch=actor(),actor();tick()
table.remove(actors,1);corpse(mismatch,99);local_total=2;tick(10)
assert(#deaths==0,'despawn and corpse origin with a different unit are not deaths')
reset()
local a=actor();a.life=2;corpses[123]={index=0,unit=123,id=999,pointer=888888};local_total=20;observer:reset();tick(10)
assert(#deaths==0,'existing dead actors, corpses, and native totals are a baseline')
reset()
for _=1,128 do local a=actor();a.life=2 end
observer:reset();tick();local_total=1;tick(6)
assert(#deaths==0,'warm-up descriptor overflow cannot turn old dead baseline rows into fresh kills')
reset()
local a=actor();a.life,local_total=2,1;tick(4)
assert(locals()==1 and deaths[1].inferred and deaths[1].observed=='dead_state',
    'a newly appearing exact enemy death after baseline covers a sub-poll instant kill')
reset()
corpses[123]={index=0,unit=123,id=999,pointer=888888,kind=TYPE};local_total=1;tick(4)
assert(locals()==1 and deaths[1].type==TYPE and deaths[1].observed=='corpse' and deaths[1].entity_id==123,
    'a fresh corpse with its own exact enemy type needs no prior live health record')
tick(10);assert(locals()==1,'an origin retained in the corpse table never replays')
reset()
corpses[123]={index=0,unit=123,id=999,pointer=888888};local_total=1;tick(10)
assert(#deaths==0,'a generic corpse type cannot be guessed into an enemy identity')
reset()
local a=actor();tick();a.health,a.credit=50,0x22;tick();corpse(a);local_total=1;tick(10)
assert(#deaths==0,'cached explicit teammate hit is not stolen for corpse inference')
reset()
local a=actor(ASSET);tick();corpse(a);local_total=1;tick(10)
assert(#deaths==0,'asset deaths cannot consume enemy KILLS inference')
reset()
local a=actor();tick();a.life,local_total=2,1;tick();observer:gap();tick(10)
assert(#deaths==0,'read gaps discard pending candidates and native quotas')
reset()
local a=actor();tick();a.life,local_total=2,1;tick();world.game=2;tick(10)
assert(#deaths==0,'world changes discard pending candidates and native quotas')
reset()
local a=actor();tick();a.life,local_total=2,1;tick();epoch=2;tick(10)
assert(#deaths==0,'reinforcement/life changes cannot fund an old inferred kill')
reset()
local a=actor();tick();a.life=2;tick(9);local_total=1;tick(4)
assert(#deaths==0,'expired candidates cannot consume later native kills')
reset()
local a=actor();tick();corpse(a);readable=false;local_total=1;tick(4)
assert(#deaths==0,'unreadable corpse table cannot prove an origin/unit transition')
reset()
local a=actor();tick();a.pointer=a.pointer+64;a.life,local_total=2,1;tick(5)
assert(#deaths==0,'descriptor reuse is a new identity, never an old live-to-dead edge')
for _,element in ipairs({1,5})do
    reset();native_cause=true
    local a=actor();a.owned=true;a.cause={kind=2,element=element};tick()
    a.life,a.credit,local_total=2,0x11,1;tick()
    local c=assert(deaths[1].damage_cause)
    assert(c.kind==2 and c.element==element and c.life==2 and c.owned and c.current)
    assert(c.source=='native_health_extension' and locals()==1)
end
for _,case in ipairs({'remote','mismatch','pin','race'})do
    reset();native_cause=true;cause_pin_ok=case~='pin'
    local a=actor();a.owned=case~='remote';a.cause={kind=2,element=1,life=case=='mismatch'and 1 or 2}
    a.cause_race=case=='race';tick();a.life,a.credit,local_total=2,0x11,1;tick()
    assert(locals()==1 and not deaths[1].damage_cause,'failed optional cause must not lose or relabel a kill: '..case)
end
reset();native_cause=true
for _=1,12 do local a=actor();a.owned=true;a.cause={kind=2,element=1}end
tick();for _,a in ipairs(actors)do a.life,a.credit=2,0x11 end;local_total=12;tick()
local sampled=0;for _,event in ipairs(deaths)do if event.damage_cause then sampled=sampled+1 end end
assert(locals()==12 and sampled<=8,'optional cause reads must stay bounded without dropping kills')
reset()
local old_clock=os.clock;os.clock=function()return 0 end
for id=1001,1128 do
    corpses[id]={index=id-1001,unit=id*7,id=id+10000,pointer=1800000+id*64,kind=TYPE}
end
local_total=128;tick(5)
assert(locals()==128,'all 128 fresh exact-type corpses survive the 64-per-poll read budget')
tick(10);assert(locals()==128,'drained corpse backlog must not replay')
reset()
local burst={};for _=1,128 do burst[#burst+1]=actor()end
tick(3)
for _,target in ipairs(burst)do corpse(target)end
local_total=128;tick(5)
assert(locals()==128,'all 128 previously tracked targets survive conversion to generic corpses under the read budget')
tick(10);assert(locals()==128,'tracked corpse backlog must not replay')
reset()
corpses[123]={index=0,unit=123,id=999,pointer=1888888,kind=TYPE};local_total=1
local calls=0
os.clock=function()calls=calls+1;return calls==1 and 0 or .003 end
tick();assert(#deaths==0,'the time budget really defers a fresh corpse')
os.clock=function()return 0 end;tick(4)
assert(locals()==1,'an unvisited corpse survives one CPU-budget interruption')
reset()
corpses[123]={index=0,unit=123,id=999,pointer=1888888,kind=TYPE};local_total=1
for _=1,9 do
    calls=0;os.clock=function()calls=calls+1;return calls==1 and 0 or .003 end;tick()
end
os.clock=function()return 0 end;local_total=2;tick(4)
assert(#deaths==0,'expired unvisited corpse cannot consume unrelated later kill growth')
reset()
for id=1001,1128 do corpses[id]={index=id-1001,unit=id*7,id=id+10000,pointer=1800000+id*64,kind=TYPE}end
observer:reset();tick();local_total=128;tick(6)
assert(#deaths==0,'large pre-existing corpse sets remain a baseline even when descriptor reads are bounded')
print('PASS 128-target fresh/tracked corpse bursts, CPU defer/expiry, initial baseline and no replay')
os.clock=old_clock
reset()
local scans=observer.diagnostics.scans;tick(600,1/60)
assert(observer.diagnostics.scans-scans==100,'10 Hz schedule across 600 frames at 60 fps')
local scans=observer.diagnostics.scans;tick(1,3);assert(observer.diagnostics.scans==scans+1,'no catch-up scans')
print('PASS: exact creditor and native-quota corpse attribution; optional owned current death kind/element with PIN, life, identity, race and 8-per-poll bounds; no replay; 10 Hz schedule.')
]]
arg={observer_path,runtime_root}
assert(loadstring(source:sub(1,start-1)..scenario,'@kill-observer-native-credit'))()
