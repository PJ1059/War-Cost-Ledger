-- First-seen fatal ground fire through the built public addon, including
-- native local quota, saved weapon totals/pairs, fire ribbons and reload.
local addon,runtime,fixture,target_fixture=assert(arg[1]),assert(arg[2]),assert(arg[3]),assert(arg[4])
local function read(path)local f=assert(io.open(path,'rb'));local s=f:read('*a'):gsub('\r\n','\n');f:close();return s end
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
local G8,UNKNOWN='5C14F27759DD3BE0','FFFFFFFFFFFFFFFF'
local module=dofile(path);state=module.state
local actual=0
local function tick(n)for _=1,n or 1 do clock=clock+100000;frame(.1)end end
local function explosion()
    assert(#callbacks>0)
    callbacks[#callbacks]({name='throwable/g8_immolation/detonation',
        local_player=true,owner_id=42,position={x=0,y=0,z=0}})
end
local function corpse(options)
    options=options or{};next_id=next_id+1
    local a={id=next_id,pointer=100000+next_id*256,kind=TYPE,life=2,health=0,
        credit=options.credit==nil and 0x11 or options.credit,owner=900,
        damage_kind=options.kind or 2,element=options.element==nil and 1 or options.element}
    actors[#actors+1]=a
    positions[a.id*7]=options.position or{x=0,y=0,z=0}
    if options.credit~=0x22 and options.no_quota~=true then
        actual=actual+1;stats.totals[KILLS]=stats.totals[KILLS]+1
        local row=stats.sources[UNKNOWN]or{[SHOTS]=0,[KILLS]=0};stats.sources[UNKNOWN]=row
        row[KILLS]=row[KILLS]+1
    end
    tick(5);assert(state.kills==actual,'ground-fire inference never creates a native kill')
end
local function latest()return assert(state.kill_source_notices.items[1])end
local function expire()tick(280)end
tick(12)
explosion();tick(120);corpse()
assert(latest().source_hash==G8 and latest().attribution=='same_target_local_fire_status_area',
    'fresh first-seen fatal fire enters the visible notice with the observed local G8 source')
assert(state.weapon_stats[G8].kills==1 and state.kill_pairs[TYPE][G8]==1)
expire();explosion();tick(180);corpse({credit=0})
assert(latest().source_hash==G8 and state.weapon_stats[G8].kills==2,
    'first-seen missing-creditor fire waits for the existing local native credit')
expire();explosion();tick(80);avatar=43;tick(3);tick(40);corpse()
assert(latest().source_hash==G8 and state.weapon_stats[G8].kills==3,
    'an avatar replacement retains the original still-burning local fire event')
expire();explosion();tick(80);health_life=2;tick(3)
-- Use a live target transition here: direct native local creditor remains
-- authoritative while the avatar is dead; it needs no first-corpse quota.
next_id=next_id+1
local waiting={id=next_id,pointer=100000+next_id*256,kind=TYPE,life=0,health=100,
    credit=0x11,owner=900,damage_kind=2,element=1}
actors[#actors+1]=waiting;positions[waiting.id*7]={x=0,y=0,z=0};tick(3)
waiting.life,waiting.health=2,0;actual=actual+1;stats.totals[KILLS]=stats.totals[KILLS]+1
stats.sources[UNKNOWN][KILLS]=stats.sources[UNKNOWN][KILLS]+1;tick(5)
assert(latest().source_hash==G8 and state.weapon_stats[G8].kills==4,
    'a local-credit enemy death still resolves the original ground fire while the player awaits reinforcement')
health_life,avatar=0,44;tick(3)
expire();explosion();tick(120);corpse({position={x=11,y=0,z=0}})
assert(latest().source_hash~=G8,'first-seen death outside the reviewed area stays unknown')
expire();explosion();tick(120);corpse({kind=0,element=0})
assert(latest().source_hash~=G8,'first-seen nonfire near G8 stays unknown')
expire();explosion();tick(120);corpse({no_quota=true})
assert(state.weapon_stats[G8].kills==4,'first-seen fire without local native credit adds no award/source kill')
expire();explosion();tick(120);corpse({credit=0x22})
assert(actual==6 and state.kill_pairs[TYPE][G8]==4)
local seq=state.sequence;active=false;tick(3)
rawset(_G,'HD2WarCostLedgerV1',nil);module=dofile(path);state=module.state;tick(3)
local q=module.career_combat_query('weapons',{sequence=seq})
local found;for _,row in ipairs(q.rows)do if row.id==G8 then found=row end end
assert(found and found.kills==4 and q.totals.kills==6,
    'first-seen G8 sources persist exactly once through career history and reload')
assert(module.career_award_snapshot().totals.ribbons.ignite>=4)
print('PASS built first-dead ground fire: late/fresh/missing-credit notices, avatar death/replacement, pair/source/fire awards/save-reload; quota/foreign/outside/nonfire controls')
]=]
arg={addon,runtime}
assert(loadstring(native:sub(1,boundary-1)..setup..scenario,'@addon-g8-first-dead-067'))()
