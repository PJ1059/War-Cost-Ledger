-- Same native Health/entity-map fields used in production, replaced by owned
-- byte buffers. No runtime events or global weapon batches enter attribution.
local observer_path,runtime_root,fixture,trace_path=assert(arg[1]),assert(arg[2]),assert(arg[3]),assert(arg[4])
local resolver_path=arg[5]
local f=assert(io.open(fixture,'rb'));local source=f:read('*a'):gsub('\r\n','\n');f:close()
local start=assert(source:find('state=dofile(path).state',1,true))
local scenario=[[
local create=dofile(path)
local trace=dofile(_TRACE_PATH)()
local observed_trace_rows={}
local trace_observe=trace.observe
function trace:observe(previous,row)
    observed_trace_rows[#observed_trace_rows+1]=row
    return trace_observe(self,previous,row)
end
local WI,E=native.wielder,native.engine
-- Logical replay fixes CPU time; a separate real ReadProcessMemory benchmark
-- measures the production soft budget without JIT/cold-load test flakiness.
local real_cpu_clock=os.clock
os.clock=function()return 0 end
world.exe=1
local R36,ALPHA='B6AFF2195568767F','F79CD8BB654397DF'
local TYPE,AC,LOW,GAS,G6='D1E990BAF22D5A52','A8CFFB316F0B5C5F','968211C0033DCE64','0416984F4922757B','4CE9EAB785A79B7B'
local pins={{0x925E38,'f6411401'},{0x925E42,'488b8360100000'},
    {0x925E49,'486bfe1c'},{0x925E58,'448974070c'},
    {0x925E99,'89040f'},{0x925EC9,'89440f04'},
    {0x923C24,'45896740'},{0x920D5F,'8b4640'}}
local function blob(size,fields)
    local raw=string.rep('\0',size)
    for at,value in pairs(fields)do raw=raw:sub(1,at)..b.encode(value,'u32')..raw:sub(at+5)end
    return raw
end
local function ptr(value)return b.encode(value,'u32')..b.encode(0,'u32')end
local target_records,target_pointers,ext=5000000,7000000,8000000
local manager,generation_manager,generations,buckets=800000,810000,820000,830000
local owners={[42]='4D1C334D294DFA97',[201]=AC,[202]=LOW,[203]='FFFFFFFFFFFFFFFF',[204]=GAS,[205]=TYPE,[206]=R36}
local unreadable,owner_generation,bad_pin,source_race=false,false,false,false
local all_reads,all_bytes=0,0
local old_read,old_fill=view.read,view.fill
local function record(a)
    return blob(H.stride,{[H.record.life]=a.life,[H.record.health]=a.health,
        [H.record.lastOwner]=a.owner or 0,[H.record.lastCreditor]=a.credit or 0,[0x40]=a.token or 0})
end
function view.read(at,size)
    all_reads,all_bytes=all_reads+1,all_bytes+size
    for _,pin in ipairs(pins)do if at==world.game+pin[1]then return bad_pin and string.rep('\0',size)or b.unhex(pin[2])end end
    if at==world.exe+E.entities then return ptr(generation_manager)end
    if at==generation_manager+E.generationSize then return b.encode(1024,'u32')end
    if at==generation_manager+E.generations then return ptr(generations)end
    if at>=generations and at<generations+1024 then return string.char(owner_generation and 1 or 0)end
    if at==world.game+WI.entities then return ptr(manager)end
    if at==manager+WI.entityMap then return ptr(buckets)..b.encode(1024,'u32')..b.encode(0xFFFFFFFF,'u32')..b.encode(1,'u32')end
    if at>=buckets and at<buckets+1024*8 then
        local id=(at-buckets)/8
        return blob(8,{[0]=owners[id]and id or 0xFFFFFFFF,[4]=id})
    end
    for id,kind in pairs(owners)do
        if at==manager+WI.descriptors+id*WI.descriptorStride then
            if unreadable then return nil end
            local actual=source_race and LOW or kind
            return blob(WI.descriptorStride,{[0]=tonumber(actual:sub(9),16),[4]=tonumber(actual:sub(1,8),16),[WI.descriptorEntity]=id})
        end
    end
    for index,a in ipairs(actors)do
        if at==target_records+(index-1)*H.stride then return record(a)end
        if at==target_pointers+(index-1)*8 then return ptr(a.pointer)end
        if at==ext+(index-1)*H.extStride then
            return blob(H.extStride,{[0]=a.damage_kind or 2,[4]=a.element or 0,[12]=a.life})
        end
        if at==a.pointer then
            if a.unreadable then return nil end
            local raw=old_read(at,size)
            raw=raw:sub(1,H.descriptor.unit)..b.encode(a.id*7,'u32')..raw:sub(H.descriptor.unit+5)
            raw=raw:sub(1,H.descriptor.flags)..b.encode(a.remote and 0 or 1,'u32')..raw:sub(H.descriptor.flags+5)
            return raw
        end
    end
end
function view.pointer(at)local raw=view.read(at,8);return raw and b.u32(raw,0)end
function view.fill(block,at,size)
    if at==target_records then return {u32=function(_,offset)
        local a=actors[math.floor(offset/H.stride)+1]
        return a and b.u32(record(a),offset%H.stride)
    end}end
    if at==target_pointers then return {ptr=function(_,offset)return actors[offset/8+1].pointer end}end
    return old_fill(block,at,size)
end
local api=require('hd2runtime/runtime/event_world')
api.health_header=function()return {live=#actors,hash_capacity=bucket_capacity(),hash_empty=0xFFFFFFFF,
    buckets=1,records=target_records,descriptors=target_pointers,ext=ext}end
api.mul32=function(a,c)return(a*(c%65536)+((a*math.floor(c/65536))%65536)*65536)%4294967296 end
local deaths,total,epoch={},0,1
local position_calls=0
local resolver=_RESOLVER_PATH and dofile(_RESOLVER_PATH)({damage_info={
    ['202']={candidates={AC}},['189']={candidates={AC,'4CE9EAB785A79B7B'},shared=true,unresolved=true},
    ['370']={candidates={AC},shared=true,unresolved=true}}})
local observer=create(api,native,{[TYPE]={kill=true},[ALPHA]={kill=true}},function(event)deaths[#deaths+1]=event end,
    {local_kills=function()return total end,damage_attribution=trace,source_types={[AC]={},[LOW]={},[GAS]={},[G6]={},[R36]={}},
        damage_resolver=resolver,unit_position=function()position_calls=position_calls+1;return{x=0,y=0,z=0}end})
local players={{['local']=true,peer='0000000000000011'}}
local function tick(n)for _=1,n or 1 do observer:poll(world,players,.1,epoch)end end
local function reset()
    observer:reset();actors,deaths={},{};total,epoch,position_calls=0,1,0
    observed_trace_rows={}
    unreadable,owner_generation,bad_pin,source_race=false,false,false,false;tick()
end
local function actor(kind)
    next_id=next_id+1
    local a={id=next_id,pointer=100000+next_id*256,kind=kind or TYPE,life=0,health=100,credit=0x11}
    actors[#actors+1]=a;tick();return a
end
local function hit(a,health,owner,element,life)
    a.health,a.owner,a.element,a.life=health,owner,element or 0,life or 0;tick()
end
reset()
local a=actor();hit(a,75,201);hit(a,50,0);hit(a,25,0);total=1;hit(a,0,0,0,2)
assert(#deaths==1 and deaths[1].damage_source.type==AC and deaths[1].damage_source.inferred)
assert(deaths[1].damage_source.target_bound and not deaths[1].damage_source.barrier)
assert(#observed_trace_rows==4 and type(observed_trace_rows[1].now)=='number',
    'source observations carry the real poll clock, not a source-token clock')
for _,row in ipairs(observed_trace_rows)do assert(row.damage_observed==true,'actual HP decrease is marked as damage')end
reset()
a=actor();hit(a,75,201);hit(a,50,203);hit(a,25,0);total=1;hit(a,0,0,0,2)
assert(#deaths==1 and deaths[1].damage_source.type==AC and not deaths[1].damage_source.barrier,
    'different unknown sources within one continuous damage chain retain the latest known AC8')
reset()
a=actor();hit(a,75,201);a.token=5;hit(a,50,0,1);a.token=7;hit(a,25,0,5);total=1;hit(a,0,0,5,2)
assert(deaths[1].damage_source.type==AC and not deaths[1].damage_source.barrier,
    'owner, opaque token and element changes do not split a continuous HP-loss chain')
assert(deaths[1].damage_cause.element==5)
reset()
a=actor();observer:contact({verified=true,local_player=true,direct=true,attack='projectile',result='penetration',target=a.id,source=201,owner=42})
hit(a,75,42);hit(a,50,42);total=1;hit(a,0,42,4,2)
assert(deaths[1].damage_source.type==AC and deaths[1].damage_source.inferred,
    'existing native contact supplies the weapon when Health.lastOwner is an avatar')
assert(observed_trace_rows[1].now==observed_trace_rows[2].now
    and observed_trace_rows[1].damage_observed==true and observed_trace_rows[2].damage_observed==true
    and observed_trace_rows[1].health==75 and observed_trace_rows[2].health==75,
    'contact and final rows share current HP and one real-damage observation time')
reset()
a=actor();observer:contact({verified=true,local_player=true,direct=true,attack='projectile',result='penetration',target=a.id,source=201,owner=42})
hit(a,75,42)
observer:contact({verified=true,local_player=true,direct=true,attack='projectile',result='penetration',target=a.id,source=203,owner=42})
hit(a,50,42);total=1;hit(a,0,42,4,2)
assert(deaths[1].damage_source.type==AC and not deaths[1].damage_source.barrier,
    'an unknown contact with real HP loss remains within the AC8 continuous chain')
reset()
a=actor();observer:contact({verified=true,local_player=true,direct=true,attack='projectile',result='blocked',target=a.id,source=201,owner=42})
total=1;hit(a,0,42,4,2)
assert(not deaths[1].damage_source.type,'blocked contact is not a prior damage source')
reset()
a=actor();a.remote=true;total=1;hit(a,0,202,0,2)
assert(deaths[1].damage_source.type==LOW and not deaths[1].damage_cause,
    'direct source works on remote-owned target without borrowing owned extension')
reset()
a=actor();hit(a,60,42);a.token=8;total=1;hit(a,0,42,4,2)
assert(not deaths[1].damage_source.type and not deaths[1].damage_source.barrier
    and deaths[1].damage_source.history_complete,
    'avatar-only history without an actual prior weapon is not a veto of this kill native source')
reset()
a=actor();hit(a,60,204);total=1;hit(a,0,204,5,2)
assert(deaths[1].damage_source.type==GAS and not deaths[1].damage_source.inferred,
    'the exact existing G4 resource remains a known direct source')
reset()
a=actor();hit(a,60,42);total=1;hit(a,0,42,5,2)
assert(not deaths[1].damage_source.type and not deaths[1].damage_source.barrier
    and deaths[1].damage_cause.element==5,
    'unknown-only gas owner can still consume this kill credited native G4 batch')
if resolver then
    reset();a=actor()
    assert(observer:explosion({local_player=true,source_type=GAS,owner=42,radius=7,
        position={x=0,y=0,z=0},status='poison',status_duration=6}))
    tick(20);hit(a,70,0)
    assert(position_calls==1,'unknown gas damage seeds from actual target position after the ordinary .8s blast window')
    tick(5);a.damage_kind=2;total=1;hit(a,0,0,5,2)
    assert(deaths[1].damage_source.type==GAS and deaths[1].local_killer,
        'G4 status area establishes the previously missing first weapon anchor and keeps native credit gate')
    reset();a=actor()
    assert(observer:explosion({local_player=true,source_type=GAS,owner=42,radius=7,
        position={x=0,y=0,z=0},status='poison',status_duration=6}))
    tick(20);a.damage_kind=10;total=1;hit(a,0,0,0,2)
    assert(deaths[1].damage_source.type==GAS,'native kind10 none is not a false non-poison veto on the first gas death')
    reset();a=actor()
    assert(observer:explosion({local_player=true,source_type=GAS,owner=42,radius=7,
        position={x=0,y=0,z=0},status='poison',status_duration=6}))
    observer:contact({verified=true,local_player=true,direct=true,attack='projectile',result='penetration',
        target=a.id,source=42,owner=42,count=0})
    tick();tick(61);total=1;a.damage_kind=2;hit(a,0,0,5,2)
    assert(not deaths[1].damage_source.type,'no-HP gas contact and expired status do not establish a source')
    reset();a=actor();hit(a,60,205);a.damage_kind=4;total=1;hit(a,0,205,0,2)
    assert(deaths[1].damage_source.type==TYPE and deaths[1].damage_source.mechanism=='enemy_damage',
        'a real other enemy owner is named without pretending it is a player weapon')
    reset();a=actor();owners[a.id]=TYPE;a.damage_kind=4;total=1;hit(a,0,a.id,0,2);owners[a.id]=nil
    assert(deaths[1].damage_source.type==TYPE and deaths[1].damage_source.mechanism=='self_explosion',
        'verified explosion death whose lastOwner is this target carries a self-explosion mechanism')
    reset();a=actor();a.credit=0x22;a.damage_kind=4;hit(a,0,205,0,2)
    assert(#deaths==1 and not deaths[1].local_killer,'enemy damage does not grant player credit by itself')
    reset();a=actor()
    observer:contact({verified=true,local_player=true,direct=true,attack='projectile',result='penetration',
        target=a.id,source=42,owner=42,damage_info_id=202,count=0,attribution_only=true})
    total=1;hit(a,0,42,0,2)
    assert(deaths[1].damage_source.type==AC and deaths[1].damage_source.inferred,
        'typed AC8 flak direct DamageInfo maps an avatar-only attribution contact without creating hits')
    reset();a=actor()
    observer:contact({verified=true,local_player=true,direct=true,attack='projectile',result='penetration',
        target=a.id,source=42,owner=42,damage_info_id=189,count=0})
    total=1;hit(a,0,42,0,2)
    assert(not deaths[1].damage_source.type,'shared shrapnel without context remains unknown')
    reset();a=actor();hit(a,70,201)
    observer:contact({verified=true,local_player=true,direct=true,attack='projectile',result='penetration',
        target=a.id,source=42,owner=42,damage_info_id=189,count=0})
    total=1;hit(a,0,42,0,2)
    assert(deaths[1].damage_source.type==AC,'shared fragment uses this target immediately named parent')
    reset();a=actor()
    observer:contact({verified=true,local_player=true,direct=true,attack='projectile',result='penetration',
        target=a.id,source=201,owner=42,damage_info_id=213})
    hit(a,70,42)
    observer:contact({verified=true,local_player=true,direct=true,attack='projectile',result='penetration',
        target=a.id,source=42,owner=42,damage_info_id=189,count=0})
    total=1;hit(a,0,42,0,2)
    assert(deaths[1].damage_source.type==AC,
        'same owner and Health run after a known native contact retains the fragment parent')
    reset();a=actor()
    assert(observer:explosion({local_player=true,source_type=AC,owner=42,radius=6,position={x=0,y=0,z=0}}))
    observer:contact({verified=true,local_player=true,direct=true,attack='projectile',result='penetration',
        target=a.id,source=42,owner=42,damage_info_id=189,count=0})
    a.damage_kind=0
    total=1;hit(a,0,42,0,2)
    assert(deaths[1].damage_source.type==AC and position_calls==1,
        'first shared fragment with gunfire death reads target position once and uses the current local AC8 blast')
    reset();a=actor()
    assert(observer:explosion({local_player=true,source_type=G6,owner=42,radius=6,position={x=0,y=0,z=0}}))
    observer:contact({verified=true,local_player=true,direct=true,attack='projectile',result='penetration',
        target=a.id,source=42,owner=42,damage_info_id=189,count=0})
    a.damage_kind=0;total=1;hit(a,0,42,0,2)
    assert(deaths[1].damage_source.type==G6 and position_calls==1,'the same shared fragment belongs to G6 with a G6 blast parent')
    reset();a=actor()
    assert(observer:explosion({local_player=true,source_type=AC,owner=42,radius=6,position={x=0,y=0,z=0}}))
    a.damage_kind=4;total=1;hit(a,0,42,0,2)
    assert(deaths[1].damage_source.type==AC,'verified explosion death can use this target position and local blast')
    reset();a=actor()
    assert(observer:explosion({local_player=true,source_type=AC,owner=42,radius=6,position={x=0,y=0,z=0}}))
    a.damage_kind=2;total=1;hit(a,0,42,5,2)
    assert(not deaths[1].damage_source.type,'nearby blast does not claim poison DOT')
    reset();a=actor();hit(a,75,201);a.token=5;hit(a,50,203);a.token=7;hit(a,25,0)
    assert(observer:explosion({local_player=true,source_type=AC,owner=42,radius=6,position={x=0,y=0,z=0}}))
    observer:contact({verified=true,local_player=true,direct=true,attack='projectile',result='penetration',
        target=a.id,source=42,owner=42,damage_info_id=189,count=0,position={x=0,y=0,z=0}})
    total=1;hit(a,0,42,0,2)
    assert(deaths[1].damage_source.type==AC and not deaths[1].damage_source.barrier,
        'a shared ID may use the current AC8 chain through different continuous unknown damage')
    reset();next_id=next_id+1
    a={id=next_id,pointer=100000+next_id*256,kind=TYPE,life=2,health=0,credit=0x11,owner=42}
    actors[#actors+1]=a;total=1
    observer:contact({verified=true,local_player=true,direct=true,attack='projectile',result='penetration',
        target=a.id,source=42,owner=42,damage_info_id=202,count=0})
    tick(3)
    assert(#deaths==1 and deaths[1].damage_source.type==AC
        and deaths[1].damage_source.last_damage_at==nil and deaths[1].damage_source.chain_source==nil,
        'a first-seen-dead typed source supplies this death only, never a live continuous damage anchor')
    for _,row in ipairs(observed_trace_rows)do
        assert(row.first_seen_dead==true and row.damage_observed==false,
            'first-seen-dead contact and final rows share no fabricated alive damage observation')
    end
    print('PASS typed DamageInfo native contacts, current shared parent, local blast death, poison exclusion and continuous unknown chain')
end
for _,failure in ipairs({'target_read','epoch','gap'})do
    reset();a=actor();hit(a,75,201)
    if failure=='target_read'then a.unreadable=true;hit(a,60,201);a.unreadable=false
    elseif failure=='epoch'then epoch=2
    elseif failure=='gap'then observer:gap();tick()end
    total=1;hit(a,0,0,0,2);tick(4)
    assert(#deaths==1 and not deaths[1].damage_source.type,'failure must not borrow source: '..failure)
end
for _,failure in ipairs({'source_generation','source_read'})do
    reset();a=actor();hit(a,75,201)
    if failure=='source_generation'then owner_generation=true
    else unreadable=true end
    hit(a,60,201);unreadable=false;total=1;hit(a,0,0,0,2)
    assert(#deaths==1 and deaths[1].damage_source.type==AC,
        'unreadable current source is continuous unknown damage, not a target identity gap: '..failure)
end
reset();a=actor();bad_pin=true;hit(a,75,201);total=1;hit(a,0,0,0,2)
assert(deaths[1].damage_source.type==AC,
    'unavailable opaque-token pins do not disable a source/HP/time chain that no longer depends on token identity')
reset();a=actor(ALPHA);hit(a,75,206);tick(39);total=1;hit(a,0,0,4,2)
assert(deaths[1].damage_source.type==R36 and deaths[1].damage_source.inferred,
    'Eruptor headshot followed four seconds later by unknown bleeding death retains Eruptor')
reset();a=actor();hit(a,75,201);tick(49);total=1;hit(a,0,0,0,2)
assert(deaths[1].damage_source.type==AC,
    'an observed damage interval of exactly 5 seconds is continuous')
reset();a=actor();hit(a,75,201);tick(50);total=1;hit(a,0,0,0,2)
assert(not deaths[1].damage_source.type and deaths[1].damage_source.chain_expired,
    'more than 5 seconds without HP loss expires the old known source')
reset();a=actor();hit(a,90,201)
for i=1,3 do tick(39);a.token=i;hit(a,90-i*20,i%2==0 and 203 or 0)end
tick(39);total=1;hit(a,0,0,0,2)
assert(deaths[1].damage_source.type==AC,
    'continuous unknown HP loss refreshes the interval even long after the initial known hit')
reset();a=actor();hit(a,75,201)
tick(40);a.owner,a.token=203,11;tick();tick(9);total=1;hit(a,0,0,0,2)
assert(not deaths[1].damage_source.type,
    'polling and owner/token metadata changes do not refresh the damage interval')
local non_damage=false
for _,row in ipairs(observed_trace_rows)do if row.health==75 and row.owner==203 then
    assert(row.damage_observed==false);non_damage=true
end end
assert(non_damage,'the source metadata-only sample was actually exercised')
reset();a=actor();hit(a,75,201);tick(40);hit(a,90,202);tick(9);total=1;hit(a,0,0,0,2)
assert(not deaths[1].damage_source.type,'healing plus a newly named owner cannot renew or replace an expired damage anchor')
reset();a=actor();hit(a,75,201);a.owner=202;tick();hit(a,50,0);total=1;hit(a,0,0,0,2)
assert(deaths[1].damage_source.type==AC,'a known owner seen without HP loss cannot replace the last actually damaging weapon')
reset();a=actor()
observer:contact({verified=true,local_player=true,direct=true,attack='projectile',result='penetration',target=a.id,source=201,owner=42})
a.owner=42;tick();tick(3);total=1;hit(a,0,0,0,2)
assert(not deaths[1].damage_source.type,'a direct native contact with no observed HP loss cannot create an anchor')
assert(observed_trace_rows[1].damage_observed==false and observed_trace_rows[2].damage_observed==false
    and observed_trace_rows[1].now==observed_trace_rows[2].now,
    'contact and final samples carry one observation time and the same non-damage flag')
reset();a=actor();hit(a,75,201);hit(a,60,202);hit(a,40,203);total=1;hit(a,0,0,0,2)
assert(deaths[1].damage_source.type==LOW,'a new known damaging weapon replaces the older AC8 anchor within a chain')
reset();a=actor();hit(a,75,201);a.owner,a.life=0,2;total=1;tick()
assert(deaths[1].damage_source.type==AC and observed_trace_rows[#observed_trace_rows].damage_observed==true,
    'an alive-to-dead transition is real damage evidence even when sampled HP has not dropped further')
if resolver then
    reset()
    local targets={};for _=1,16 do targets[#targets+1]=actor()end
    for _,target in ipairs(targets)do
        observer:contact({verified=true,local_player=true,direct=true,attack='projectile',result='penetration',
            target=target.id,source=42,owner=42,damage_info_id=202})
        target.health,target.life,target.owner=0,2,42
    end
    total=16;tick()
    assert(#deaths==16,'a typed burst must preserve the original local kill gate and total')
    for _,event in ipairs(deaths)do
        assert(event.damage_source.type==AC,'all typed contacts survive the eight-target native enrichment budget')
    end
    assert(observer.diagnostics.source_reads<=512 and observer.diagnostics.source_bytes<=32768)
    tick(3);assert(#deaths==16,'pure Lua typed enrichment never produces duplicate deaths')

    reset()
    targets={};for _=1,16 do targets[#targets+1]=actor()end
    for index,target in ipairs(targets)do
        observer:contact({verified=true,local_player=true,direct=true,attack='projectile',result='penetration',
            target=target.id,source=42,owner=42,damage_info_id=202})
        target.owner=42;target.health=index%2==0 and 110 or 100
    end
    tick()
    for _,target in ipairs(targets)do target.health,target.life=0,2 end
    total=16;tick()
    assert(#deaths==16)
    for _,event in ipairs(deaths)do
        assert(not event.damage_source.type,'no-HP contact metadata and healing cannot create a typed burst anchor')
    end
    print('PASS 16-target typed burst retains every source with unchanged native budgets; metadata/healing stay unanchored')
    reset();local target=actor()
    observer:contact({verified=true,local_player=true,direct=true,attack='projectile',result='penetration',
        target=target.id,source=42,owner=42,damage_info_id=202})
    target.health,target.life,target.owner=0,2,42;total=1
    local cpu_calls=0
    os.clock=function()cpu_calls=cpu_calls+1;return cpu_calls==1 and 0 or .003 end
    tick();os.clock=function()return 0 end
    assert(#deaths==0,'the forced outer native scan budget really deferred the target')
    tick()
    assert(#deaths==1 and deaths[1].damage_source.type==AC,
        'an unvisited target retains its typed contact across a native scan budget break')

    reset();target=actor()
    observer:contact({verified=true,local_player=true,direct=true,attack='projectile',result='penetration',
        target=target.id,source=42,owner=42,damage_info_id=202})
    target.health,target.life,target.owner=0,2,42;total=1
    cpu_calls=0
    os.clock=function()cpu_calls=cpu_calls+1;return cpu_calls==1 and 0 or .003 end
    tick();os.clock=function()return 0 end
    observer:poll(world,players,.8,epoch)
    assert(#deaths==1 and not deaths[1].damage_source.type,
        'an unvisited contact expires after the bounded 0.75s retention window')

    reset();target=actor()
    observer:contact({verified=true,local_player=true,direct=true,attack='projectile',result='penetration',
        target=target.id,source=42,owner=42,damage_info_id=202})
    target.unreadable=true;hit(target,75,42);target.unreadable=false
    hit(target,50,42);total=1;hit(target,0,42,0,2)
    assert(#deaths==1 and not deaths[1].damage_source.type,
        'a failed attempted target read drops its contact instead of reviving a source after the read gap')
    print('PASS bounded cross-poll contact retention for unvisited targets; actual read gaps stay gaps')
end
local function corpse_after_anchor(delay,options)
    reset();local target=actor();hit(target,50,201)
    options=options or {}
    if options.gap then observer:gap();tick()end
    if options.foreign then target.credit=0x22;target.health=40;tick()end
    if options.epoch then epoch=epoch+1 end
    tick(delay or 0)
    local corpses,corpse_entity=api.corpses,api.corpse_entity
    api.corpses=function()return {origins={[target.id]=0}}end
    api.corpse_entity=function(_,_,index,unit)
        assert(index==0 and unit==target.id*7);return target.id+5000
    end
    actors={};total=1;tick(3)
    api.corpses,api.corpse_entity=corpses,corpse_entity
    return deaths[1]
end
local corpse=corpse_after_anchor(0)
assert(corpse and corpse.observed=='corpse' and corpse.local_killer and corpse.inferred
    and corpse.damage_source.type==AC and corpse.damage_source.inferred,
    'same-target corpse fallback inherits its fresh verified local damaging weapon as inferred')
assert(corpse.damage_source.policy=='same_target_recent_damage_before_corpse')
corpse=corpse_after_anchor(39)
assert(corpse and corpse.damage_source.type==AC,'a four-second delayed same-target corpse retains its known damaging weapon')
corpse=corpse_after_anchor(49)
assert(corpse and corpse.damage_source.type==AC,'corpse handoff includes the five-second boundary')
corpse=corpse_after_anchor(50)
assert(corpse and not corpse.damage_source.type,'a corpse after more than 5s inactivity cannot inherit a stale source')
corpse=corpse_after_anchor(0,{epoch=true})
assert(not corpse or not corpse.damage_source.type,'a new life epoch cannot inherit the prior corpse source')
corpse=corpse_after_anchor(0,{gap=true})
assert(corpse and not corpse.damage_source.type,'a target read gap cannot restore a pre-gap corpse source')
assert(not corpse_after_anchor(0,{foreign=true}),'an explicit foreign creditor keeps the original corpse rejection')
print('PASS recent same-target local corpse source; timeout, epoch, read-gap and foreign-credit exclusions')
reset();a=actor();hit(a,75,201)
for id=3001,3065 do
    observer:contact({verified=true,local_player=true,direct=true,attack='projectile',result='penetration',
        target=id,source=42,owner=42,damage_info_id=202})
end
total=1;hit(a,0,0,0,2)
assert(#deaths==1 and deaths[1].damage_source.type==AC,
    'contact-ring saturation on unrelated targets must not erase this target valid damage chain')
reset()
local burst={};for _=1,64 do burst[#burst+1]=actor()end
local unfunded=actor();unfunded.credit=0
for index,target in ipairs(burst)do
    target.health,target.life,target.owner=0,2,index%2==0 and 201 or 202
end
unfunded.health,unfunded.life=0,2;total=64;tick()
assert(observer.diagnostics.source_deferred>0,'the shared byte/read bound really defers part of the burst')
tick(4)
assert(#deaths==64,'deferred native-local deaths reserve their quota once and cannot fund an unrelated death')
for _,event in ipairs(deaths)do
    assert(event.entity_id~=unfunded.id and(event.damage_source.type==AC or event.damage_source.type==LOW),
        'every deferred target keeps its own source without cross-target fallback')
end
assert(observer.diagnostics.source_reads<=512 and observer.diagnostics.source_bytes<=32768)
tick(10);assert(#deaths==64,'retries never replay delivered deaths')
reset();a=actor();a.health,a.life,a.owner=0,2,202;total=1
local native_read=view.read
view.read=function(at,size)
    local value=native_read(at,size)
    if at==a.pointer then os.clock=function()return .003 end end
    return value
end
tick();view.read=native_read;os.clock=function()return 0 end
assert(#deaths==0,'a budget cut inside target enrichment does not immediately commit unknown')
tick();assert(#deaths==1 and deaths[1].damage_source.type==LOW,
    'the exact target is retried in the next poll when the read budget returns')
reset();a=actor();a.health,a.life,a.owner=0,2,202;total=1
native_read=view.read
view.read=function(at,size)
    local value=native_read(at,size)
    if at==a.pointer then os.clock=function()return .003 end end
    return value
end
tick();view.read=native_read;os.clock=function()return 0 end
a.pointer=a.pointer+64;tick(4)
assert(#deaths==0,'a replaced descriptor cannot complete the prior identity deferred death')
reset();a=actor();a.health,a.life,a.owner=0,2,202;total=1
native_read=view.read
view.read=function(at,size)
    local value=native_read(at,size)
    if at==a.pointer then os.clock=function()return .003 end end
    return value
end
for _=1,7 do os.clock=function()return 0 end;tick()end
view.read=native_read;os.clock=function()return 0 end
assert(#deaths==1 and not deaths[1].damage_source.type and observer.diagnostics.source_retry_expired>0,
    'persistent native budget pressure releases one bounded unknown after 0.5s, never holds a kill forever')
tick(10);assert(#deaths==1,'an expired source retry does not replay when native reads return')
do
local prior_corpses,prior_corpse_entity=api.corpses,api.corpse_entity
local corpse_rows={}
api.corpses=function()return{origins=corpse_rows,descriptors=9500000}end
api.corpse_entity=function(_,_,index,unit)return 999999 end
reset()
local victim=actor();victim.health,victim.life,victim.owner=0,2,202;total=1
local prior_read=view.read
view.read=function(at,size)
    local value=prior_read(at,size)
    if at==victim.pointer then os.clock=function()return .003 end end
    return value
end
tick();view.read=prior_read;os.clock=function()return 0 end
assert(#deaths==0,'review setup: defer proven local death inside source enrichment')
actors={};corpse_rows[victim.id]=0;total=2
view.read=function(at,size)
    if at==9500000 then return ptr(9600000)end
    if at==9600000 then return blob(H.descriptor.size,{
        [H.descriptor.type]=tonumber(TYPE:sub(9),16),[H.descriptor.type+4]=tonumber(TYPE:sub(1,8),16),
        [H.descriptor.entity]=999999,[H.descriptor.unit]=victim.id*7})end
    return prior_read(at,size)
end
tick(4)
assert(#deaths==1,'a deferred direct death followed by its exact-type corpse cannot spend a spare credit twice; actual='..#deaths)
assert(deaths[1].entity_id==victim.id)
view.read=prior_read;api.corpses,api.corpse_entity=prior_corpses,prior_corpse_entity
print('PASS independent review: deferred direct -> exact corpse emits once despite spare native credit')
end
print('PASS full-source 64-target retry queue; native-credit reservation; no identity reuse or contact-ring global reset')
reset()
local many={};for _=1,16 do many[#many+1]=actor()end
for _,a in ipairs(many)do a.health,a.life,a.owner=0,2,202 end;total=16;tick()
assert(#deaths==16,'enrichment bounds never discard local kills')
local enriched=0;for _,event in ipairs(deaths)do if event.damage_source.type then enriched=enriched+1 end end
assert(enriched==16, 'all sixteen simultaneous Health owner deaths must retain their known source')
assert(observer.diagnostics.source_reads<=512 and observer.diagnostics.source_bytes<=32768)
print('PASS native lastOwner + generation -> same-target 5s continuous damage chain; metadata/heal/no-HP contact exclusions; gap/epoch/failure; 64 target changes,512 reads,32KiB bounds')
print('Observed source reader peak calls='..observer.diagnostics.source_reads_peak..' bytes='..observer.diagnostics.source_bytes_peak)
]]
arg={observer_path,runtime_root};_TRACE_PATH=trace_path;_RESOLVER_PATH=resolver_path
local fn=assert(loadstring(source:sub(1,start-1)..scenario,'@target-damage-native-map'));assert(xpcall(fn,debug.traceback))
