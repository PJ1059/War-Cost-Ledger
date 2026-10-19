-- Death can arrive through Health, lifecycle and the native statistics counter
-- in either order. Waiting for reinforcement must not advance the epoch every
-- tick, or the observer continually discards fresh local kill-credit quotas.
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
        callbacks[#callbacks+1]=fn;return{state='active'}end};return value
end
api.unit_position=function(_,unit)return positions[unit]end
local read_players,lifecycle=api.players,3
api.players=function(...)
    local rows=read_players(...);rows[1].lifecycle=lifecycle;return rows
end
local G8,UNKNOWN='5C14F27759DD3BE0','FFFFFFFFFFFFFFFF'
local module=dofile(path);state=module.state
local function tick(n)for _=1,n or 1 do clock=clock+100000;frame(.1)end end
local function mission()
    active=false;tick(3)
    stats={totals={[SHOTS]=0,[KILLS]=0,[DEATHS]=0,[0xC7680A1B]=0},sources={}}
    actors,positions={},{};avatar,health_life,lifecycle=avatar+1,0,3
    active=true;tick(12)
end
local function area()
    callbacks[#callbacks]({name='throwable/g8_immolation/detonation',
        local_player=true,owner_id=42,position={x=0,y=0,z=0}})
end
local function fresh_fire()
    next_id=next_id+1
    local a={id=next_id,pointer=100000+next_id*256,kind=TYPE,life=2,health=0,
        credit=0,owner=900,damage_kind=2,element=1}
    actors[#actors+1]=a;positions[a.id*7]={x=0,y=0,z=0}
    stats.totals[KILLS]=stats.totals[KILLS]+1
    local row=stats.sources[UNKNOWN]or{[SHOTS]=0,[KILLS]=0};stats.sources[UNKNOWN]=row;row[KILLS]=row[KILLS]+1
    tick(5)
    assert(state.kill_pairs[TYPE]and state.kill_pairs[TYPE][G8]==1,
        'missing-creditor first-dead G8 still consumes a single native local-kill credit during the death wait; actual='
        ..tostring(state.classified_kills)..'/'..tostring(state.kill_observer.life_changes)
        ..' source='..tostring(state.kill_observer.ground_fire.g8_matched)
        ..' contexts='..tostring(state.kill_observer.ground_fire.g8_contexts)
        ..' cause='..tostring(state.kill_observer.ground_fire.fatal_fire_attempts)
        ..' noarea='..tostring(state.kill_observer.ground_fire.no_fire_context)
        ..' nopos='..tostring(state.kill_observer.ground_fire.no_position)
        ..' inferred='..tostring(state.kill_observer.inferred_local)
        ..' expired='..tostring(state.kill_observer.expired_candidates))
end
tick(12)
local changes=state.kill_observer.life_changes
area();health_life=2;tick(5)
assert(state.kill_observer.life_changes==changes+1,'one observed death advances the epoch only once while waiting')
stats.totals[DEATHS]=1;tick(3)
assert(state.kill_observer.life_changes==changes+1,'the later native counter merges with that same Health death')
fresh_fire();tick(8)
assert(state.kill_observer.life_changes==changes+1 and state.kill_pairs[TYPE][G8]==1)
health_life,avatar=0,avatar+1;tick(3)
assert(state.kill_observer.life_changes==changes+2,'a new alive avatar still starts a new target-chain epoch')
mission();changes=state.kill_observer.life_changes;area()
stats.totals[DEATHS]=1;tick(3)
assert(state.kill_observer.life_changes==changes+1,'native counter can be the first death observation')
health_life=2;tick(5)
assert(state.kill_observer.life_changes==changes+1,'later Health death merges with the earlier counter')
fresh_fire()
mission();changes=state.kill_observer.life_changes;area();lifecycle=2;tick(5)
assert(state.kill_observer.life_changes==changes+1,'repeated player lifecycle death reports are one transition')
stats.totals[DEATHS]=1;tick(3);fresh_fire()
assert(state.kill_observer.life_changes==changes+1,'lifecycle and native counter death merge during reinforcement wait')
mission();changes=state.kill_observer.life_changes
health_life=2;tick(3);health_life,avatar=0,avatar+1;tick(3)
assert(state.kill_observer.life_changes==changes+2)
stats.totals[DEATHS]=1;tick(4)
assert(state.kill_observer.life_changes==changes+2,'a delayed old death counter cannot clear a newly revived avatar chain')
assert(state.deaths==1 and state.killstreak==0,'the counter still updates death totals and ends unordered kill streaks')
-- Two observed Health deaths can precede one replicated counter batch.
health_life=2;tick(3);health_life,avatar=0,avatar+1;tick(3)
local after=state.kill_observer.life_changes
stats.totals[DEATHS]=2;tick(3)
assert(state.kill_observer.life_changes==after and state.deaths==2)
print('PASS death-wait G8 native quota: one epoch per death, Health/counter either order, late counter after respawn and saved death totals')
]=]
arg={addon,runtime}
assert(loadstring(native:sub(1,boundary-1)..setup..scenario,'@addon-g8-death-wait-067'))()
