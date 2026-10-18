-- Exercise the built entry's real persist/flush and native-stat/death boundaries.
-- Uses the same owned native records as test_integration; no live process.
local addon,runtime_root,fixture=assert(arg[1]),assert(arg[2]),assert(arg[3])
local input=assert(io.open(fixture,'rb'))
local source=input:read('*a'):gsub('\r\n','\n');input:close()
local start=assert(source:find('state=dofile(path).state',1,true))
local scenario=[[
saved.last_mission={sequence=7,status='ended',ribbons={melee=3,demolition=2},
    mission_medals={air_expert=true},medals={air_expert=true}}
saved.combat_history={kills=10000,deaths=100,medals={air_expert=true}}
saved.mission_sequence=7
local writes=0
local old_set=store.set
function store:set(key,value)
    if key=='career_awards_v1' then writes=writes+1 end
    return old_set(self,key,value)
end
local module=dofile(path);state=module.state
local function totals() return module.career_award_snapshot().totals end
local now=0
local function tick(n) for _=1,n or 1 do now=now+.1;clock=clock+100000;frame(.1) end end
local function actor(kind)
    next_id=next_id+1
    local a={id=next_id,pointer=100000+next_id*256,kind=kind,life=0,credit=0}
    actors[#actors+1]=a
    return a
end
local function ships()
    for i=1,10 do actor('74E2285C01DA4F71') end
    tick(4)
    for _,a in ipairs(actors) do a.life=2;a.credit=0x11 end
    tick(2)
end
assert(totals().ribbons.melee==3 and totals().ribbons.demolition==2)
assert(totals().medals.air_expert==1,'legacy unlock and last mission represent at least one, not two')
tick()
assert(state.sequence==8 and saved.career_awards_v1.checkpoint.sequence==8)
local after_start=writes
stats.totals[0xC7680A1B]=2;tick()
assert(totals().ribbons.melee==5,'real native melee increments lifetime records')
tick(20)
assert(totals().ribbons.melee==5 and writes==after_start,'unchanged frames do not write award state each frame')
local charger,titan=actor('1A7FCDFF98C664B0'),actor('9E2E17F2CCCCAFDD')
tick(4);charger.life,charger.credit=2,0x11;titan.life,titan.credit=2,0x11;tick(2)
assert(ribbon_family(state.ribbons,'heavy')==1 and ribbon_family(state.ribbons,'giant')==1)
assert(state.ribbons.heavy==0 and state.ribbons.giant==0
    and state.ribbons.heavy_charger==1 and state.ribbons.giant_bile_titan==1)
local popup=module.game_hud:native_model(now,true,600)
local seen={}
for _,item in ipairs(popup.awards.items)do seen[item.id]=item.count end
assert(seen.T01==1 and seen.G02==1 and seen.R02==nil and seen.R03==nil,
    'observed local units reach their specific live popup, never a duplicate generic item')
seen={}
for _,item in ipairs(popup.layout.glyphs)do
    if item.group=='side_ribbons'then seen[item.id]=item.count_text end
end
assert(seen.T01=='x1' and seen.G02=='x1' and seen.R02==nil and seen.R03==nil,
    'both unit ribbons reach the native picture/count layout without generic duplicates')
assert(ribbon_family(totals().ribbons,'heavy')==1 and ribbon_family(totals().ribbons,'giant')==1,
    'popup and lifetime use the same real kill event')
module.game_hud:start_preview(4,now)
tick(2)
assert(totals().ribbons.melee==5 and totals().ribbons.air==0,'independent preview cannot award actual records')
ships()
assert(state.ribbons.demolition==10 and totals().ribbons.demolition==12)
assert(totals().medals.foreign_parking==1,'real same-mission threshold records one medal')
tick(4)
assert(totals().medals.foreign_parking==1 and totals().ribbons.demolition==12)
active=false;tick()
assert(saved.career_awards_v1.totals.ribbons.demolition==12 and saved.last_mission.ribbons.demolition==10,
    'end_mission persists the award checkpoint with the matching mission state')
local persisted=saved.career_awards_v1
rawset(_G,'HD2WarCostLedgerV1',nil)
module=dofile(path);state=module.state
assert(module.career_award_snapshot().totals.ribbons.demolition==12)
tick(2)
assert(module.career_award_snapshot().totals.medals.foreign_parking==1,'reload must not re-import the last mission')
stats={totals={[SHOTS]=0,[KILLS]=0,[DEATHS]=0,[0xC7680A1B]=0},sources={}}
actors={};active=true;tick()
ships()
active=false;tick()
assert(saved.career_awards_v1.totals.ribbons.demolition==22)
assert(saved.career_awards_v1.totals.medals.foreign_parking==2,'next real mission may earn the medal again')
assert(persisted.totals.ribbons.demolition==12,'new saves cannot mutate an earlier snapshot')
print('PASS: built-entry native melee/death awards, conservative migration, mission reset/end, batched persistence, separate preview, same-mission dedupe and reload/next-mission accumulation.')
]]
arg={addon,runtime_root}
assert(loadstring(source:sub(1,start-1)..scenario,'@career-awards-integration'))()
