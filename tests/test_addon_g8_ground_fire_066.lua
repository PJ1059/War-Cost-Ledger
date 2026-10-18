-- Replay the public explosion event into the real built addon, then native
-- Health/element bytes, source totals, awards, career pairs and saved reload.
local addon,runtime,fixture,target_fixture=assert(arg[1]),assert(arg[2]),assert(arg[3]),assert(arg[4])
local function read(path)local f=assert(io.open(path,'rb'));local s=f:read('*a'):gsub('\r\n','\n');f:close();return s end
local native=read(fixture);local boundary=assert(native:find('state=dofile(path).state',1,true))
local target=read(target_fixture)
local first=assert(target:find('local WI,E=native.wielder,native.engine',1,true))
local last=assert(target:find('local deaths,total,epoch',first,true))
local setup=target:sub(first,last-1):gsub("'D1E990BAF22D5A52'","'1A7FCDFF98C664B0'")
local scenario=[=[
os.clock=function()return 0 end -- owned-memory functional replay, not an FPS measurement
local callbacks,positions={},{}
local base=package.preload['mods/skyeshade/hd2runtime']
package.preload['mods/skyeshade/hd2runtime']=function()
    local value=base();value.events={on=function(name,fn,options)
        assert(name=='explosion'and options.id=='ledger_demolition_explosion')
        callbacks[#callbacks+1]=fn;return{state='active'}
    end};return value
end
api.unit_position=function(_,unit)return positions[unit]end
local G8,UNKNOWN='5C14F27759DD3BE0','FFFFFFFFFFFFFFFF'
local module=dofile(path);state=module.state
local actual=0
local function tick(n)for _=1,n or 1 do clock=clock+100000;frame(.1)end end
local function actor(options)
    options=options or{};next_id=next_id+1
    local a={id=next_id,pointer=100000+next_id*256,kind=TYPE,life=0,health=100,
        credit=options.credit==nil and 0x11 or options.credit,owner=900,
        damage_kind=options.kind or 2,element=options.element==nil and 1 or options.element}
    actors[#actors+1]=a
    if options.position~=false then positions[a.id*7]=options.position or{x=0,y=0,z=0}end
    tick(3);return a
end
local function explosion(options)
    options=options or{}
    assert(#callbacks>0)
    callbacks[#callbacks]({name=options.name or'throwable/g8_immolation/detonation',
        local_player=options.local_player~=false,owner_id=42,
        position=options.position==false and nil or{x=0,y=0,z=0}})
end
local function die(a,local_kill)
    a.health,a.life=0,2
    if local_kill~=false then actual=actual+1;stats.totals[KILLS]=stats.totals[KILLS]+1
        local row=stats.sources[UNKNOWN]or{[SHOTS]=0,[KILLS]=0};stats.sources[UNKNOWN]=row
        row[KILLS]=row[KILLS]+1 end
    tick(5);assert(state.kills==actual,'source attribution cannot manufacture native kills')
end
local function latest()return assert(state.kill_source_notices.items[1])end
local function expire()tick(280)end
tick(12)
local late=actor();explosion();tick(120);die(late)
assert(latest().source_hash==G8 and latest().attribution=='same_target_local_fire_status_area',
    'a target killed by actual ground fire after twelve seconds must be credited to G8')
-- A fresh target need not have been present at detonation.
expire();explosion();tick(180);local arrived=actor();die(arrived)
assert(latest().source_hash==G8,'later arrivals in the observed burning area must retain G8')
-- A real known G8 owner, not the unsupported live element extension, can
-- anchor the ordinary 5s damage chain and survive leaving the area.
expire();local carried=actor();explosion();tick(260)
owners[207]=G8;carried.health,carried.owner=60,207;tick(2)
carried.owner=900;positions[carried.id*7]={x=50,y=0,z=0};tick(20);die(carried)
assert(latest().source_hash==G8,'burning after leaving the area retains its own recent real fire hit')
assert(state.weapon_stats[G8].kills==3 and state.kill_pairs[TYPE][G8]==3)
-- The native setter writes kind/element only at death: live Fire bytes can
-- be stale. They must not seed a chain for a later nonfire death elsewhere.
expire();local stale=actor();explosion();tick(120)
stale.health=60;tick(2);positions[stale.id*7]={x=50,y=0,z=0}
stale.damage_kind,stale.element=0,0;die(stale)
assert(latest().source_hash~=G8,'stale live Fire bytes cannot turn unrelated unknown damage into a G8 chain')
expire();local other=actor({credit=0x22});explosion();tick(120)
die(other,false);assert(state.weapon_stats[G8].kills==3,'foreign deaths never borrow a local fire area')
expire();local outside=actor({position={x=11,y=0,z=0}});explosion();tick(120);die(outside)
assert(latest().source_hash~=G8,'outside the bounded area cannot be inferred as G8')
expire();local gun=actor({kind=0,element=0});explosion();tick(120);die(gun)
assert(latest().source_hash~=G8,'nonfire deaths beside G8 cannot be reassigned')
expire();local old=actor();explosion();tick(280);die(old)
assert(latest().source_hash~=G8,'the expired area cannot seed a new source')
expire();local remote=actor();explosion({local_player=false});tick(120);die(remote)
assert(latest().source_hash~=G8,'a foreign detonation cannot seed local G8')
expire();local missing=actor({credit=0});explosion();tick(120);die(missing)
assert(latest().source_hash==G8 and state.weapon_stats[G8].kills==4)
assert(actual==9 and state.kill_pairs[TYPE][G8]==4,'one target/source association per actual credited kill')
local seq=state.sequence;active=false;tick(3)
rawset(_G,'HD2WarCostLedgerV1',nil);module=dofile(path);state=module.state;tick(3)
local q=module.career_combat_query('weapons',{sequence=seq})
local found;for _,row in ipairs(q.rows)do if row.id==G8 then found=row end end
assert(found and found.kills==4 and q.totals.kills==9,'career and saved source totals must preserve the four G8 kills')
assert(module.career_award_snapshot().totals.ribbons.ignite>=4,'burn kills remain represented in fire ribbons')
print('PASS built G8 ground fire: late/new victims, known-owner damage chain, source totals/pairs/fire ribbons/save-reload; stale-live-element/nonfire/remote/outside/expiry controls')
]=]
arg={addon,runtime}
assert(loadstring(native:sub(1,boundary-1)..setup..scenario,'@addon-g8-ground-fire-066'))()
