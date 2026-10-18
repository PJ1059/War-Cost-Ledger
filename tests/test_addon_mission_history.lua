-- Execute actual built lifecycle/storage with owned Runtime fixtures.
-- The transition to non-mission covers returning to ship midway too: no
-- victory signal is required to archive a record.
local addon,runtime,fixture=assert(arg[1]),assert(arg[2]),assert(arg[3])
local file=assert(io.open(fixture,'rb'));local source=file:read('*a'):gsub('\r\n','\n');file:close()
local start=assert(source:find('state=dofile(path).state',1,true))
local scenario=[[
saved.mission_sequence=7
saved.combat_history={kills=10000,deaths=100,medals={}}
saved.career_kd={version=1,kills=50000,deaths=1000,anchor_mod_kills=10000,anchor_mod_deaths=100}
saved.last_mission={sequence=7,status='ended',kills=10,deaths=2,ribbons={melee=3},mission_medals={air_expert=true}}
local history_writes,save_calls=0,0
local old_set=store.set
function store:set(key,value)
    if key=='mission_history_v1'then history_writes=history_writes+1 end
    return old_set(self,key,value)
end
function store:save()save_calls=save_calls+1 end
local module=dofile(path);state=module.state
local function tick(n)for _=1,n or 1 do clock=clock+100000;frame(.1)end end
local function find(sequence)
    for _,entry in ipairs(module.mission_history_snapshot().entries)do
        if entry.sequence==sequence then return entry end
    end
end
assert(find(7).kills==10 and find(7).ribbons.melee==3)
tick();assert(state.sequence==8 and find(8).status=='active')
local after_start=history_writes
tick(20);assert(history_writes==after_start,'idle observations cannot serialize history every frame')
stats.totals[KILLS],stats.totals[DEATHS],stats.totals[0xC7680A1B]=12,2,3
tick();module.game_hud:start_preview(4,1)
tick(2);assert(find(8).kills==12 and find(8).ribbons.melee==3,'preview is isolated')
-- No success/completion event: the user leaves the unfinished mission.
active=false;tick()
local ended=find(8)
assert(ended.status=='ended' and ended.kills==12 and ended.deaths==2)
assert(ended.ribbons.melee==3)
assert(ended.history_before.kills==50000 and ended.history_after.kills==50012)
assert(ended.history_before.deaths==1000 and ended.history_after.deaths==1002)
assert(saved.mission_history_v1 and save_calls>0)
local cumulative=module.career_award_snapshot().totals.ribbons.melee
assert(module.delete_mission_history==nil,'public deletion entry point is removed')
tick(70);assert(find(7) and find(8),'completed history is retained')
assert(module.career_award_snapshot().totals.ribbons.melee==cumulative,'history viewing keeps lifetime totals')
rawset(_G,'HD2WarCostLedgerV1',nil)
module=dofile(path);state=module.state
tick(2);assert(find(7) and find(8),'saved history survives restart and legacy migration')
stats={totals={[SHOTS]=0,[KILLS]=0,[DEATHS]=0,[0xC7680A1B]=0},sources={}}
active=true;tick();stats.totals[KILLS]=4;tick(60)
local current=state.sequence
assert(find(current).kills==4 and find(current).deaths==0)
-- Simulate exit without a mission-end transition; saved checkpoint remains.
rawset(_G,'HD2WarCostLedgerV1',nil);active=false
module=dofile(path);state=module.state
assert(find(current).status=='interrupted' and find(current).kills==4)
tick(60);assert(saved.mission_history_v1.entries[1].status=='interrupted')
print('PASS actual built mission history: baseline, idle save batching, mid-mission return, per-match KD/awards, isolated preview, no deletion API, retained history after restart, unchanged career totals, interrupted checkpoint.')
]]
arg={addon,runtime}
assert(loadstring(source:sub(1,start-1)..scenario,'@mission-history-integration'))()
