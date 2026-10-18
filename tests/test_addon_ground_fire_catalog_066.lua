-- All enabled ground-fire events enter the real built addon's explosion
-- callback and fatal Health bytes. No live element is treated as a hit.
local addon,runtime,fixture,target_fixture,contexts_file=assert(arg[1]),assert(arg[2]),assert(arg[3]),assert(arg[4]),assert(arg[5])
local function read(path)local f=assert(io.open(path,'rb'));local s=f:read('*a'):gsub('\r\n','\n');f:close();return s end
-- Exact numeric boundaries use the source extracted from the installable ZIP.
-- The larger built replay below then tests actual event/Health wiring.
local contexts=dofile(contexts_file)
local resolver_create=dofile(assert(arg[6]))
local pure_checks=0
for _,entry in ipairs(contexts)do
    local function resolve(changes,at)
        local resolver=resolver_create()
        assert(resolver:explosion({source_type=entry.source_type,local_player=true,
            position={x=0,y=0,z=0},radius=entry.radius,status='fire',status_duration=entry.status_duration},0))
        local row={readable=true,damage_observed=true,life=2,kind=2,element=1,
            position={x=entry.radius,y=0,z=0},local_source=true}
        for key,value in pairs(changes or{})do row[key]=value end
        pure_checks=pure_checks+1
        return resolver:resolve(row,nil,at or 1.2)
    end
    assert(resolve(nil,entry.status_duration).type==entry.source_type,entry.name..': inclusive exact radius/time boundary')
    assert(not resolve(nil,entry.status_duration+.000001),entry.name..': exact expiry boundary')
    assert(not resolve({position={x=entry.radius+.000001,y=0,z=0}}),entry.name..': exact outer radius boundary')
    assert(not resolve({life=0}),entry.name..': living Fire extension cannot infer ground damage')
    assert(not resolve({life=1}),entry.name..': nonfatal Fire extension cannot infer ground damage')
    assert(not resolve({kind=0,element=0}),entry.name..': reliable fatal nonfire is incompatible')
    assert(not resolve({kind=2,element=5}),entry.name..': reliable poison is incompatible')
    assert(not resolve({local_source=false}),entry.name..': a foreign creditor is incompatible')
    assert(resolve({local_source=false,creditor_missing=true}).type==entry.source_type,
        entry.name..': missing creditor may enter the observer native-quota path')
    assert(resolve({source_type='A8CFFB316F0B5C5F'}).type=='A8CFFB316F0B5C5F',entry.name..': current known source wins')
    assert(not resolve({damage_observed=false}),entry.name..': retained metadata is not new damage')
    assert(not resolve({damage_info_id=99999}),entry.name..': unknown explicit typed ID cannot borrow a fire area')
end
assert(pure_checks==132)
local native=read(fixture);local boundary=assert(native:find('state=dofile(path).state',1,true))
local target=read(target_fixture)
local first=assert(target:find('local WI,E=native.wielder,native.engine',1,true))
local last=assert(target:find('local deaths,total,epoch',first,true))
local setup=target:sub(first,last-1):gsub("'D1E990BAF22D5A52'","'1A7FCDFF98C664B0'")
local scenario=[=[
os.clock=function()return 0 end
local callbacks,positions={},{}
local base=package.preload['mods/skyeshade/hd2runtime']
package.preload['mods/skyeshade/hd2runtime']=function()
    local value=base();value.events={on=function(name,fn,options)
        assert(name=='explosion'and options.id=='ledger_demolition_explosion')
        callbacks[#callbacks+1]=fn;return{state='active'}
    end};return value
end
api.unit_position=function(_,unit)return positions[unit]end
local UNKNOWN,AC='FFFFFFFFFFFFFFFF','A8CFFB316F0B5C5F'
local module=dofile(path);state=module.state
local actual,area_number,positive,negative=0,0,0,0
local expected={}
local origin={x=0,y=0,z=0}
local function tick(n)for _=1,n or 1 do clock=clock+100000;frame(.1)end end
local function area()
    area_number=area_number+1;origin={x=area_number*1000,y=0,z=0}
end
local function position(distance)return{x=origin.x+(distance or 0),y=origin.y,z=origin.z}end
local function actor(options)
    options=options or{};next_id=next_id+1
    local a={id=next_id,pointer=100000+next_id*256,kind=TYPE,life=0,health=100,
        credit=options.credit==nil and 0x11 or options.credit,owner=options.owner or 900,
        damage_kind=options.kind==nil and 2 or options.kind,element=options.element==nil and 1 or options.element}
    actors[#actors+1]=a;positions[a.id*7]=options.position or position();tick(3);return a
end
local function explosion(entry,options)
    options=options or{}
    local event={name=entry.name,local_player=options.local_player~=false,owner_id=42,position=position()}
    if entry.required_event_types and not options.no_hint then event.source_type=entry.required_event_types[1]end
    if options.source_type then event.source_type=options.source_type end
    if options.owner_type then event.source_type=nil;event.owner_type=options.owner_type end
    assert(#callbacks>0);callbacks[#callbacks](event)
end
local function die(a,local_kill,native_source)
    a.health,a.life=0,2
    if local_kill~=false then
        actual=actual+1;stats.totals[KILLS]=stats.totals[KILLS]+1
        native_source=native_source or UNKNOWN
        local row=stats.sources[native_source]or{[SHOTS]=0,[KILLS]=0};stats.sources[native_source]=row;row[KILLS]=row[KILLS]+1
    end
    tick(5);assert(state.kills==actual,'an area cannot create a native player kill')
end
local function count(source)return state.weapon_stats[source]and state.weapon_stats[source].kills or 0 end
local function notice()return assert(state.kill_source_notices.items[1])end
local function verify_totals()
    for source,kills in pairs(expected)do
        assert(count(source)==kills,'source count mismatch '..source..': '..tostring(count(source))..' versus '..kills)
        assert(state.kill_pairs[TYPE][source]==kills,'target/source pairs must agree with source totals '..source)
    end
end
local function credited(entry,label,source)
    source=source or entry.source_type
    assert(notice().source_hash==source,entry.name..': '..label..' resolved '..tostring(notice().source_hash))
    expected[source]=(expected[source]or 0)+1;positive=positive+1;verify_totals()
end
local function rejected(entry,label)
    assert(notice().source_hash~=entry.source_type,entry.name..': '..label..' must not become local ground fire')
    negative=negative+1;verify_totals()
end
tick(12)
for _,entry in ipairs(contexts)do
    -- Both radius and time are close to each event's own independent boundary.
    -- Death is sampled 0.1s after the last wait, leaving a 0.2s timing margin.
    area();local a=actor({position=position(entry.radius-.01)});explosion(entry)
    tick(math.floor((entry.status_duration-.3)*10));die(a);credited(entry,'late fire near radius/time boundary')
    assert(notice().attribution=='same_target_local_fire_status_area',entry.name..': fatal fire uses the area policy')
    -- A later arrival need not have been in the original blast.
    area();explosion(entry);tick(math.floor(entry.status_duration*5));a=actor();die(a)
    credited(entry,'new target entering an existing area')
    -- A fixed expiry is never renewed by polling the area or retaining corpses.
    area();a=actor();explosion(entry);tick(math.ceil((entry.status_duration+.3)*10));die(a)
    rejected(entry,'expired per-event window')
    area();a=actor({position=position(entry.radius+.01)});explosion(entry);tick(12);die(a)
    rejected(entry,'outside per-event native outer radius')
    area();a=actor({kind=0,element=0});explosion(entry);tick(12);die(a)
    rejected(entry,'nonfire death inside an area')
    area();a=actor({owner=201});explosion(entry);tick(12);die(a,true,AC)
    credited(entry,'actual known weapon source wins',AC)
    area();a=actor();explosion(entry,{local_player=false});tick(12);die(a)
    rejected(entry,'remote event')
    area();a=actor({credit=0x22});explosion(entry);tick(12);die(a,false)
    negative=negative+1;verify_totals()
    -- A stale live Fire extension cannot establish a chain from an unrelated
    -- HP decrease, even if that decrease happens inside the area.
    area();a=actor();explosion(entry);tick(12);a.health=60;tick(2)
    positions[a.id*7]=position(entry.radius+100);a.damage_kind,a.element=0,0;die(a)
    rejected(entry,'stale live Fire bytes followed by a nonfire death elsewhere')
    area();a=actor();tick(12);die(a)
    rejected(entry,'configured capability without an observed event')
    if entry.required_event_types then
        area();a=actor();explosion(entry,{no_hint=true});tick(12);die(a)
        rejected(entry,'shared mine event without a resource identity')
        area();a=actor();explosion(entry,{source_type=UNKNOWN});tick(12);die(a)
        rejected(entry,'shared mine event with an unapproved resource identity')
        area();a=actor();explosion(entry,{owner_type=entry.required_event_types[2]});tick(12);die(a)
        credited(entry,'allowlisted mine owner identity')
    end
end
assert(#contexts==11 and positive==34 and negative==79)
assert(actual==102,'native local kill accounting includes all actual control deaths')
verify_totals()
local seq=state.sequence;active=false;tick(3)
rawset(_G,'HD2WarCostLedgerV1',nil);module=dofile(path);state=module.state;tick(3)
local q=module.career_combat_query('weapons',{sequence=seq})
local saved_counts={};for _,row in ipairs(q.rows)do saved_counts[row.id]=row.kills end
for source,kills in pairs(expected)do assert(saved_counts[source]==kills,'saved source total '..source)end
assert(q.totals.kills==actual,'saved mission total includes every real local kill: '..tostring(q.totals.kills)..' versus '..actual)
print('PASS built all ground-fire contexts: 11 exact events, 9 sources, 34 positive source checks, 79 rejection/foreign controls, independent radius/expiry, mine identity allowlist, native totals/pairs/save-reload')
]=]
arg={addon,runtime}
assert(loadstring('local contexts=(function()\n'..read(contexts_file)..'\nend)()\n'..native:sub(1,boundary-1)..setup..scenario,
    '@addon-ground-fire-catalog-066'))()
print('PASS packaged fire resolver: 132 exact expiry/radius, fatal/live element, creditor, known-source and typed-ID controls')
