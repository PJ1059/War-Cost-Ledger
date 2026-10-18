-- Built entry, production Health observer, awards, source totals, notices,
-- career and history. Only owned native-memory inputs are replaced.
local addon,runtime_root,fixture,native_fixture=assert(arg[1]),assert(arg[2]),assert(arg[3]),assert(arg[4])
local function read(path)local f=assert(io.open(path,'rb'));local s=f:read('*a'):gsub('\r\n','\n');f:close();return s end
local base=read(fixture)
local start=assert(base:find('state=dofile(path).state',1,true))
local helper=read(native_fixture)
local first=assert(helper:find('local WI,E=native.wielder,native.engine',1,true))
local last=assert(helper:find('local deaths,total,epoch={},0,1',first,true))
helper=helper:sub(first,last-1):gsub("'D1E990BAF22D5A52'","'1A7FCDFF98C664B0'")
local scenario=[=[
owners[204],owners[205]='4FB0F8C02F55C82B','88F61AFFF48AC8A4'
owners[206],owners[207],owners[208]='E90F771A36FB441E','31C4DD88C1450282','D54B9505C0F72873'
local module=dofile(path);state=module.state
local function upvalue(fn,name)
    for i=1,255 do local key,value=debug.getupvalue(fn,i);if not key then break end;if key==name then return value end end
end
local observer=assert(upvalue(frame,'kill_observer'),'built frame must own the production kill observer')
local now=0
local function tick(n)for _=1,n or 1 do now=now+.1;clock=clock+100000;frame(.1)end end
local function actor(kind)
    next_id=next_id+1
    local a={id=next_id,pointer=100000+next_id*256,kind=kind or TYPE,life=0,health=100,credit=0x11}
    actors[#actors+1]=a;tick();return a
end
local function hit(a,h,owner,element,life)
    a.health,a.owner,a.element,a.life=h,owner,element or 0,life or 0
    if life==2 then stats.totals[KILLS]=stats.totals[KILLS]+1 end
    tick()
end
local function contact(a,source)
    assert(observer:contact({verified=true,local_player=true,direct=true,attack='projectile',
        result='penetration',target=a.id,source=source,owner=42}))
end
local function find(items,id)for _,row in ipairs(items)do if row.id==id then return row end end end
tick(3)
local a=actor();hit(a,75,201);hit(a,50,0);hit(a,25,0);hit(a,0,0,4,2)
assert(state.weapon_stats[AC].kills==1,'same-target AC8 unknown bleeding is credited to its weapon in the built ledger')
assert(state.mission_medals.level_not_problem==nil,'AP4 AC8 does not become light armour')
local low=actor();contact(low,202);hit(low,75,42);hit(low,0,42,0,2)
local low_trace=assert(upvalue(observer.poll,'known')[low.id]).damage_trace or {}
assert(state.mission_medals.level_not_problem==1 and state.weapon_stats[LOW].kills==1,
    'AP2 award='..tostring(state.mission_medals.level_not_problem)..' source kills='..tostring(state.weapon_stats[LOW]and state.weapon_stats[LOW].kills)
    ..' trace='..tostring(low_trace.type)..' raw='..tostring(low_trace.raw_type)..' barrier='..tostring(low_trace.barrier)
    ..' contacts='..tostring(observer.diagnostics.contact_sources))
local giant=actor('9E2E17F2CCCCAFDD');contact(giant,202);hit(giant,70,42);hit(giant,0,42,0,2)
assert(state.mission_medals.level_not_problem==2,'both heavy and giant targets qualify')
assert(module.career_award_snapshot().totals.medals.level_not_problem==2)
assert(find(module.game_hud:native_model(now,true,600).awards.items,'M11'),'actual new medal popup is wired')
local unknown=actor();contact(unknown,201);hit(unknown,75,42)
contact(unknown,203);hit(unknown,50,42);hit(unknown,0,42,4,2);tick(8)
assert(state.weapon_stats[AC].kills==2,'continuous real damage keeps AC8 even when an intervening weapon ID is unknown')
local latest=assert(state.kill_source_notices.items[1])
assert(latest.source_hash==AC and not latest.damage_source.barrier,
    'the actual HUD follows the same-target continuous damage chain')
local base_type_info=api.type_info
api.type_info=function(kind)
    if kind=='FFFFFFFFFFFFFFFE'then return {kill=true,kind='enemy',name='Unmapped synthetic enemy'}end
    return base_type_info(kind)
end
local fire=actor('FFFFFFFFFFFFFFFE');hit(fire,0,0,1,2)
local gas=actor();hit(gas,0,0,5,2)
assert(state.ribbons.ignite==1 and state.ribbons.poison==1,'native target elements fill unsourced fire and gas kills')
local flame=actor();stats.sources[owners[204]]={[KILLS]=1,[SHOTS]=0};hit(flame,0,204,1,2)
local toxin=actor();stats.sources[owners[205]]={[KILLS]=1,[SHOTS]=0};hit(toxin,0,205,5,2)
assert(state.ribbons.ignite==2 and state.ribbons.poison==2,'native and observed copies of one sourced kill merge without duplicates')
local bullet=actor();hit(bullet,0,204,0,2)
assert(state.ribbons.ignite==2,'source can ignite but an observed physical-only death does not add observed burning')
stats.sources[owners[206]]={[KILLS]=1,[SHOTS]=0};stats.totals[KILLS]=stats.totals[KILLS]+1;tick()
stats.sources[owners[208]]={[KILLS]=1,[SHOTS]=0};stats.totals[KILLS]=stats.totals[KILLS]+1;tick()
assert(state.ribbons.ignite==2,'delivery-pod kills and ordinary LAS98 beam kills do not become native burning kills')
local pod=actor();hit(pod,0,207,0,2)
assert(state.mission_medals.level_not_problem==2,'a same-named M105 delivery pod must not inherit the gun AP2')
assert(not state.ribbons.status_fire and not state.ribbons.status_poison,'retired application ribbons never accrue')
tick(2)
assert(module.career_award_snapshot().totals.ribbons.poison==2)
assert(module.mission_history_snapshot().entries[1].medals.level_not_problem==2)
active=false;tick()
assert(saved.last_mission.ribbons.poison==2 and saved.last_mission.ribbons.ignite==2)
assert(saved.mission_history_v1.entries[1].medals.level_not_problem==2)
local before=module.career_award_snapshot().totals.ribbons.poison
rawset(_G,'HD2WarCostLedgerV1',nil);module=dofile(path);state=module.state;tick(2)
assert(module.career_award_snapshot().totals.ribbons.poison==before,'reload cannot replay elemental acquisitions')
print('PASS built entry: continuous same-target AC8 bleed across unknown IDs, heavy+giant AP2 M11 HUD/career/history, final fire+poison elements, native/observed de-duplication, no ignite-on-application, save/reload')
]=]
arg={addon,runtime_root}
assert(loadstring(base:sub(1,start-1)..helper..scenario,'@built-target-damage-awards'))()
