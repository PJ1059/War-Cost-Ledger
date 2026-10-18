-- Run the actual built addon with owned source-stat fixtures. No live game.
local addon,runtime_root,fixture=assert(arg[1]),assert(arg[2]),assert(arg[3])
local input=assert(io.open(fixture,'rb'))
local source=input:read('*a'):gsub('\r\n','\n');input:close()
local start=assert(source:find('state=dofile(path).state',1,true))
local scenario=[[
local TANK,CANNON,MG='16474112801385B6','1FA1F596769225C2','439F9E65C18567DA'
local bodies={'16474112801385B6','2D85BFE3D8717FE5','35DBF54F016F3624','79E4B3D2DA5E45E3',
    '7B2326F6FD9C8069','9B2140378640432E','B0C9FAF4AF8903F9','C2D449ECF7FACAB1','CC21C7FFD3EBEFB9'}
local policy='confirmed_player_vehicle_parent_source_kills_as_crush'
-- Mimic a late observer; these 154 body-source kills must not mint old awards.
stats.totals[KILLS]=1403
stats.sources[TANK]={[KILLS]=154,[SHOTS]=0}
stats.sources[CANNON]={[KILLS]=75,[SHOTS]=57}
stats.sources[MG]={[KILLS]=231,[SHOTS]=3850}
local module=dofile(path);state=module.state
local now=0
local function tick(n)for _=1,n or 1 do now=now+.1;clock=clock+100000;frame(.1)end end
local function find(items,id)for _,v in ipairs(items)do if v.id==id then return v end end end
local function total()return module.career_award_snapshot().totals.ribbons.crush end
local function add(hash,n)
    local row=stats.sources[hash]
    if not row then row={[KILLS]=0,[SHOTS]=0};stats.sources[hash]=row end
    row[KILLS]=row[KILLS]+n
    stats.totals[KILLS]=stats.totals[KILLS]+n
end
tick(3)
assert(state.ribbons.crush==0 and total()==0)
assert(not find(module.game_hud:native_model(now,true,600).awards.items,'R12'))
assert(module.mission_history_snapshot().entries[1].crush_policy==policy,
    'new zero-crush snapshots need a policy marker so legacy fallback cannot add initial source totals later')
add(TANK,2);tick()
assert(state.ribbons.crush==2 and total()==2)
local first=find(module.game_hud:native_model(now,true,600).awards.items,'R12')
assert(first and first.count==2 and first.total==2,'new body-source kills reach the real popup path')
assert(module.mission_history_snapshot().entries[1].ribbons.crush==2)
add(CANNON,4);add(MG,7);tick()
assert(state.ribbons.crush==2 and total()==2,'mounted guns cannot masquerade as a parent-body kill')
stats.totals[KILLS]=stats.totals[KILLS]+522;tick()
assert(state.ribbons.crush==2 and total()==2,'unknown source remainder is not vehicle evidence')
-- Dying and replacing the avatar cannot replay mission-level source counters.
stats.totals[DEATHS]=1;health_life=2;tick(2)
avatar=43;health_life=0;tick(2);add(TANK,1);tick()
assert(state.ribbons.crush==3 and total()==3)
available=false;tick();add(TANK,3);available=true;tick()
assert(state.ribbons.crush==3 and total()==3,'read-gap recovery baselines unobserved source growth')
add(TANK,1);tick();assert(state.ribbons.crush==4 and total()==4)
-- Raw source blocks can reset; the reset value is never another acquisition.
stats.sources[TANK][KILLS]=2;stats.totals[KILLS]=stats.totals[KILLS]+2;tick()
assert(state.ribbons.crush==4)
add(TANK,1);tick();assert(state.ribbons.crush==5 and total()==5)
active=false;tick(3)
assert(saved.mission_history_v1.entries[1].ribbons.crush==5)
assert(saved.mission_history_v1.entries[1].crush_policy==policy)
assert(saved.career_awards_v1.totals.ribbons.crush==5)
rawset(_G,'HD2WarCostLedgerV1',nil)
module=dofile(path);state=module.state;tick(2)
assert(total()==5 and #module.game_hud:native_model(now,true,600).awards.items==0,
    'reload must neither replay the prior notification nor re-import old source totals')
-- Every reviewed player vehicle body uses the same rule in the next mission.
stats={totals={[SHOTS]=0,[KILLS]=0,[DEATHS]=0,[0xC7680A1B]=0},sources={}}
actors={};active=true;tick(3)
assert(state.ribbons.crush==0 and total()==5)
for _,hash in ipairs(bodies)do add(hash,1)end
tick();assert(state.ribbons.crush==9 and total()==14,'all nine exact reviewed bodies are covered')
active=false;tick()
local history=module.mission_history_snapshot().entries
assert(history[1].ribbons.crush==9 and history[2].ribbons.crush==5)
assert(module.career_period_summary().all.ribbons.crush==14)
print('PASS: actual built exact-parent kill growth, first baseline without replay, R12 popup/cumulative/history, cannon/MG and522 unknown exclusions, death/avatar, gap, source reset, ship/reload and all nine player bodies.')
]]
arg={addon,runtime_root}
assert(loadstring(source:sub(1,start-1)..scenario,'@vehicle-kill-ribbons-integration'))()
