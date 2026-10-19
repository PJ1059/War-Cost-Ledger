-- Existing native-owned Health buffers: only the timing differs from 0.4.66.
-- The enemy enters Health as already dead between polls; its fatal extension
-- is verified, but there is no observed live HP-loss row to seed a chain.
local observer_path,runtime_root,fixture,trace_path,resolver_path=
    assert(arg[1]),assert(arg[2]),assert(arg[3]),assert(arg[4]),assert(arg[5])
local respawn_only=arg[6]and arg[6]:gsub('\\','/'):match('/respawn$')~=nil
local function read(path)local f=assert(io.open(path,'rb'));local s=f:read('*a'):gsub('\r\n','\n');f:close();return s end
local native=read(fixture)
local boundary=assert(native:find('state=dofile(path).state',1,true))
local target=read('tests/test_target_damage_observer.lua')
local first=assert(target:find('local WI,E=native.wielder,native.engine',1,true))
local last=assert(target:find('local deaths,total,epoch=',first,true))
local setup=target:sub(first,last-1)
local scenario=[=[
local create=dofile(path)
local trace=dofile(_TRACE_PATH)()
local G8='5C14F27759DD3BE0'
local api=require('hd2runtime/runtime/event_world')
local deaths,total,epoch={},0,1
local positions,position_calls={},0
local observer=create(api,native,{[TYPE]={kill=true}},function(event)deaths[#deaths+1]=event end,
    {local_kills=function()return total end,damage_attribution=trace,
        source_types={[G8]={kind='weapon'}},damage_resolver=dofile(_RESOLVER_PATH)(),
        unit_position=function(_,unit)position_calls=position_calls+1;return positions[unit]end})
local players={{['local']=true,peer='0000000000000011'}}
local function tick(n)for _=1,n or 1 do observer:poll(world,players,.1,epoch)end end
local function reset()observer:reset();actors,deaths,positions={},{},{};total,epoch,position_calls=0,1,0;tick()end
local function area()
    assert(observer:explosion({local_player=true,source_type=G8,position={x=0,y=0,z=0},
        radius=10,status='fire',status_duration=27}))
end
local function make(fields)
    next_id=next_id+1
    local a={id=next_id,pointer=100000+next_id*256,kind=TYPE,life=2,health=0,
        credit=0x11,owner=900,damage_kind=2,element=1}
    for k,v in pairs(fields or{})do a[k]=v end
    actors[#actors+1]=a;positions[a.id*7]={x=0,y=0,z=0};return a
end
if _RESPAWN_ONLY then
    reset();local a=make({life=0,health=100});tick();area();tick(80)
    epoch=epoch+1;tick();tick(40);a.life,a.health=2,0;total=1;tick(4)
    assert(#deaths==1 and deaths[1].damage_source.type==G8,
        'respawn must not discard the original same-world local G8 area before expiry')
    print('PASS isolated respawn: original local G8 area remains within its original 27s window')
    return
end
reset();area();tick(120);make();total=1;tick(4)
assert(#deaths==1 and deaths[1].damage_source.type==G8,
    'first-seen dead native fatal fire inside the local area must resolve to G8')
local source=deaths[1].damage_source
assert(source.target_bound and source.inferred and source.local_source
    and source.policy=='same_target_local_fire_status_area'and not source.last_damage_at,
    'first-seen fire supplies death-only evidence and never invents a live chain')
assert(observer.diagnostics.ground_fire.first_dead_fire_attempts>0
    and observer.diagnostics.ground_fire.g8_matched>0)
reset();area();tick(80);epoch=epoch+1;tick();tick(40);make();total=1;tick(4)
assert(#deaths==1 and deaths[1].damage_source.type==G8,
    'same-world same-peer ground fire retains original evidence after an avatar life change')
reset();area();tick(80);epoch=epoch+1;tick();tick(200);make();total=1;tick(4)
assert(#deaths==1 and not deaths[1].damage_source.type,
    'a respawn cannot renew the original fixed ground-fire expiry')
reset();area();tick(80);observer:gap();tick();make();total=1;tick(4)
assert(#deaths==1 and not deaths[1].damage_source.type,'an actual observation gap still clears old ground fire')
reset();area();tick(80);players[1].peer='0000000000000022';tick();make({credit=0x22});total=1;tick(4)
assert(#deaths==1 and not deaths[1].damage_source.type,'a new local creditor peer cannot inherit the previous player fire')
players[1].peer='0000000000000011'
reset();area();tick(80);world.game=2;tick();make();total=1;tick(4)
assert(#deaths==1 and not deaths[1].damage_source.type,'a different world cannot inherit the old fire area')
world.game=1
reset();area();tick(120);make({credit=0});total=1;tick(4)
assert(#deaths==1 and deaths[1].damage_source.type==G8,
    'missing creditor keeps the unchanged fresh-death local-native quota gate')
reset();area();tick(120);make();tick(9)
assert(#deaths==0,'first-seen fatal fire without native kill credit does not create a kill')
reset();area();tick(120);make({credit=0x22});total=1;tick(9)
assert(#deaths==0,'a foreign creditor never borrows local fire attribution')
reset();area();tick(120);local a=make();positions[a.id*7]={x=11,y=0,z=0};total=1;tick(4)
assert(#deaths==1 and not deaths[1].damage_source.type,'first-seen fire keeps the radius bound')
reset();area();tick(120);make({damage_kind=0,element=0});total=1;tick(4)
assert(#deaths==1 and not deaths[1].damage_source.type,'a nonfire first-seen death stays unknown')
reset();area();tick(120);a=make();positions[a.id*7]=nil;total=1;tick(4)
assert(#deaths==1 and not deaths[1].damage_source.type,'missing position cannot resolve a fire area')
reset();area();tick(280);make();total=1;tick(4)
assert(#deaths==1 and not deaths[1].damage_source.type,'expired contexts do not cover first-seen deaths')
reset();make();observer:reset();tick();area();total=1;tick(9)
assert(#deaths==0,'a preexisting startup corpse is a baseline, not a fresh kill')
-- Diagnostics are fixed numeric fields and accept only the precise G8 event.
local diag=observer.diagnostics.ground_fire
local count=diag.events_seen
observer:status_event({name='unrelated/name',local_player=true},true)
assert(diag.events_seen==count)
observer:status_event({name='throwable/g8_immolation/detonation',local_player=true},true)
observer:status_event({name='throwable/g8_immolation/detonation',local_player=false},false,'not_local')
observer:status_event({name='throwable/g8_immolation/detonation'},false,'not_local')
assert(diag.events_seen==count+3 and diag.events_local==1 and diag.events_foreign==1
    and diag.events_uncredited==1 and diag.events_forwarded==1 and diag.event_not_local==2)
local keys=0;for key,value in pairs(diag)do keys=keys+1;assert(type(value)=='number',key)end
assert(keys<=40,'diagnostics cannot become a per-kill history')
assert(diag.outside_area>0 and diag.no_position>0 and diag.no_fire_context>0)
print('PASS native observer first-dead G8 fire: death-only source/local quota, respawn keeps original fire expiry and negative controls; fixed-size diagnostics')
]=]
_TRACE_PATH,_RESOLVER_PATH=trace_path,resolver_path
_RESPAWN_ONLY=respawn_only
arg={observer_path,runtime_root}
assert(loadstring(native:sub(1,boundary-1)..setup..scenario,'@observer-g8-first-dead-067'))()
