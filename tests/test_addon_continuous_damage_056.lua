-- Actual built entry: source notices, weapon totals, awards and persistence use
-- owned native Health/stat buffers. Unknown IDs/tokens do not break a real
-- <=5-second damage chain; idle metadata cannot keep that chain alive.
local addon,runtime,fixture,target_fixture=assert(arg[1]),assert(arg[2]),assert(arg[3]),assert(arg[4])
local function read(path)local f=assert(io.open(path,'rb'));local s=f:read('*a'):gsub('\r\n','\n');f:close();return s end
local expected_version='0.4.65'
assert(read(addon):find("local VERSION = '"..expected_version.."'",1,true),'actual built '..expected_version)
local native=read(fixture);local boundary=assert(native:find('state=dofile(path).state',1,true))
local target=read(target_fixture)
local first=assert(target:find('local WI,E=native.wielder,native.engine',1,true))
local last=assert(target:find('local deaths,total,epoch',first,true))
local setup=target:sub(first,last-1):gsub("'D1E990BAF22D5A52'","'1A7FCDFF98C664B0'")
local scenario=[=[
os.clock=function()return 0 end -- deterministic owned-memory replay, not a frame-time measurement
local UNKNOWN,G6,MELEE='FFFFFFFFFFFFFFFF','4CE9EAB785A79B7B',0xC7680A1B
owners[205]=G6
stats.totals[MELEE]=0
local module=dofile(path);state=module.state
local function upvalue(fn,name)
    for i=1,255 do local key,value=debug.getupvalue(fn,i);if not key then break end;if key==name then return value end end
end
local observer=assert(upvalue(frame,'kill_observer'))
local now=0
local function tick(n)for _=1,n or 1 do now=now+.1;clock=clock+100000;frame(.1)end end
local function actor(health)
    next_id=next_id+1
    local row={id=next_id,pointer=100000+next_id*256,kind=TYPE,life=0,health=health or 100,
        credit=0x11,owner=42,damage_kind=0,token=0}
    actors[#actors+1]=row;tick(3);return row
end
local function hit(row,health,owner,token)
    row.health,row.owner,row.token=health,owner or 42,token or row.token;tick()
end
local function contact(row,damage_id)
    assert(observer:contact({verified=true,local_player=true,direct=true,attack='projectile',
        result='penetration',target=row.id,source=42,owner=42,damage_info_id=damage_id}))
end
local function die(row,owner,token,melee)
    stats.totals[KILLS]=stats.totals[KILLS]+1
    stats.totals[MELEE]=stats.totals[MELEE]+(melee or 0)
    local source=stats.sources[UNKNOWN]or{[SHOTS]=0,[KILLS]=0};stats.sources[UNKNOWN]=source
    source[KILLS]=source[KILLS]+1
    row.life=2;hit(row,0,owner,token);tick(2) -- publish the real notice snapshot after the death poll
end
local function latest()return assert(state.kill_source_notices.items[1],'latest target source notice')end
local function unknown(message)
    assert(latest().source_text=='未知来源' and latest().source_hash~=AC and latest().source_hash~=LOW
        and latest().source_hash~=G6,message..'; source='..tostring(latest().source_hash))
end
tick(3)

local sustained=actor(1000);hit(sustained,999,201,1)
for pulse=1,60 do
    tick(4)
    local owner=({203,0,42})[(pulse-1)%3+1]
    hit(sustained,999-pulse,owner,pulse+10)
end
die(sustained,42,999)
assert(latest().source_hash==AC and state.weapon_stats[AC].kills==1,
    'thirty seconds of actual unknown damage keeps the latest AC8 across changing owners/tokens with no absolute-age cap')
assert(now>30,'the continuous-chain fixture must really advance beyond30 seconds')

-- A single unknown damage run used to inherit AC8 forever. Idling no longer
-- lets its later death search back beyond the5-second actual-damage gap.
local expired=actor();hit(expired,75,201,1);hit(expired,70,42,2)
tick(50);die(expired,42,2)
unknown('more than5s without actual damage clears even an unchanged unknown run')

local replacement=actor();hit(replacement,75,201,1);hit(replacement,60,203,2)
hit(replacement,40,202,3);hit(replacement,20,42,4);die(replacement,42,5)
assert(latest().source_hash==LOW and state.weapon_stats[LOW].kills==1,
    'a new known damaging weapon replaces the earlier AC8 before later unknown damage')
assert(state.mission_medals.level_not_problem==1,
    'the surviving low-AP source reaches the actual heavy-target achievement path')

local inclusive=actor();hit(inclusive,75,201,1);tick(49);die(inclusive,42,2)
assert(latest().source_hash==AC and state.weapon_stats[AC].kills==2,
    'an actual damage gap of exactly5s remains in the same chain')
local outside=actor();hit(outside,75,201,1);tick(50);die(outside,42,2)
unknown('a5.1s actual-damage gap starts an unknown chain')

-- Owner/type/token changes are metadata unless Health actually drops. Even a
-- known LOW owner appearing in metadata cannot refresh or replace the source.
local metadata=actor();hit(metadata,75,201,1)
for step=1,26 do
    metadata.owner=step%2==0 and 202 or 42;metadata.token=100+step;tick(2)
end
die(metadata,42,200)
unknown('metadata-only owner/token/known-type changes cannot refresh the damage deadline')
assert(state.weapon_stats[LOW].kills==1 and state.mission_medals.level_not_problem==1,
    'a known metadata-only owner is neither a weapon kill nor another low-AP achievement')

local shared_without_parent=actor();contact(shared_without_parent,189);die(shared_without_parent,42,1)
unknown('shared189 on a different target cannot borrow another target\'s most recent weapon')
local shared_with_g6=actor();hit(shared_with_g6,75,205,1)
contact(shared_with_g6,189);hit(shared_with_g6,50,42,2)
contact(shared_with_g6,999999);die(shared_with_g6,42,3)
assert(latest().source_hash==G6 and state.weapon_stats[G6].kills==1,
    'shared189 then a different unknown DamageInfo keeps its actual same-target G6 parent')

local melee=actor();melee.damage_kind=6;die(melee,42,1,1)
assert(latest().source_text=='近战' and latest().source_hash==nil and state.ribbons.melee==1,
    'the0.4.55 native melee fallback remains available without a known weapon chain')
local sequence=state.sequence
local q=module.career_combat_query('weapons',{sequence=sequence})
assert(state.kills==9 and q.totals.kills==9 and q.coverage.unknown_kills==5,
    'nine native kills stay four known plus five unknown in the career query; got '..q.totals.kills)
assert(ribbon_family(state.ribbons,'heavy')==9 and state.ribbons.heavy==0
    and state.source_reassignments['4D1C334D294DFA97']==4,
    'source inference leaves the native total and raw correction provenance intact')
active=false;tick(3)
local raw=module.combat_records_snapshot().entries[1]
assert(raw.weapons[UNKNOWN].kills==9 and raw.weapons[AC].kills==2
    and raw.weapons[LOW].kills==1 and raw.weapons[G6].kills==1)
assert(saved.last_mission.kills==9 and ribbon_family(saved.last_mission.ribbons,'heavy')==9
    and saved.last_mission.mission_medals.level_not_problem==1)
rawset(_G,'HD2WarCostLedgerV1',nil);module=dofile(path);state=module.state;tick(3)
q=module.career_combat_query('weapons',{sequence=sequence})
assert(q.totals.kills==9 and q.coverage.unknown_kills==5,
    'reload preserves source corrections without duplicate kills')
assert(ribbon_family(module.career_award_snapshot().totals.ribbons,'heavy')==9
    and module.career_award_snapshot().totals.medals.level_not_problem==1)
print('PASS built continuous damage:30s changing unknowns, inclusive5s/expired5.1s, known replacement, metadata-only deadline, shared189/G6/unknownID, melee, native/career/awards/save-reload')
]=]
arg={addon,runtime}
assert(loadstring(native:sub(1,boundary-1)..setup..scenario,'@built-continuous-damage-owned'))()
