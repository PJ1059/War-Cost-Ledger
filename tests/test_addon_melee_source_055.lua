-- Built addon, production target Health reader, native optional MELEE counter,
-- notices and save/reload. Only owned game-memory/stat/store boundaries vary.
local addon,runtime,fixture,target_fixture=assert(arg[1]),assert(arg[2]),assert(arg[3]),assert(arg[4])
local function read(path)local f=assert(io.open(path,'rb'));local s=f:read('*a'):gsub('\r\n','\n');f:close();return s end
local native=read(fixture);local boundary=assert(native:find('state=dofile(path).state',1,true))
local target=read(target_fixture)
local first=assert(target:find('local WI,E=native.wielder,native.engine',1,true))
local last=assert(target:find('local deaths,total,epoch',first,true))
local setup=target:sub(first,last-1):gsub("'D1E990BAF22D5A52'","'1A7FCDFF98C664B0'")
local scenario=[=[
os.clock=function()return 0 end -- deterministic owned-memory replay, not a timing claim
local MELEE,UNKNOWN,CQC=0xC7680A1B,'FFFFFFFFFFFFFFFF','FCD8A6E67EAC635A'
owners[205]=CQC
stats.totals[MELEE]=0
-- An equipped firearm is deliberately present but is not melee evidence.
local equipped_reads=0
api.equipped=function()equipped_reads=equipped_reads+1;return{type=AC,entity=201}end
stats.sources[AC]={[SHOTS]=1,[KILLS]=0}
local module=dofile(path);state=module.state
local now=0
local function tick(n)for _=1,n or 1 do now=now+.1;clock=clock+100000;frame(.1)end end
local function actor(kind,owner)
    next_id=next_id+1
    local row={id=next_id,pointer=100000+next_id*256,kind=TYPE,life=0,health=100,
        credit=0x11,owner=owner or 42,damage_kind=kind or 6,element=0}
    actors[#actors+1]=row;tick(3);return row
end
local function native_kill(melee,source)
    stats.totals[KILLS]=stats.totals[KILLS]+1
    stats.totals[MELEE]=stats.totals[MELEE]+(melee or 0)
    source=source or UNKNOWN
    local row=stats.sources[source]or{[SHOTS]=0,[KILLS]=0};stats.sources[source]=row
    row[KILLS]=row[KILLS]+1
end
local function die(row,melee,source)
    native_kill(melee,source);row.health,row.life=0,2;tick(3)
end
local function latest()return assert(state.kill_source_notices.items[1],'latest source notice')end
local function unknown(message)
    assert(latest().source_text=='未知来源' and latest().source_hash~=AC and latest().source_hash~=CQC,message)
end
tick(3)
local generic=actor(6);die(generic,1)
assert(latest().source_text=='近战' and latest().source_hash==nil
    and latest().attribution=='native_target_melee_with_melee_credit',
    'owned final Ability6 plus this native MELEE kill displays generic melee, never an equipped gun')
assert(state.melee_kills==1 and state.ribbons.melee==1,
    'the existing native melee counter still grants exactly its one ribbon')
assert(not state.weapon_stats[AC] or state.weapon_stats[AC].kills==0,
    'a melee display fallback cannot invent AC8 weapon kills')

local ability=actor(6);die(ability,0)
unknown('Ability6 is not melee without this batch native melee credit')
local gunfire=actor(0);die(gunfire,1)
unknown('a Gunfire0 target cannot borrow an unrelated native melee increment')
local after_gunfire=actor(6);die(after_gunfire,0)
unknown('unused credit from a different batch cannot label the next Ability target')

local saber=actor(6,205);die(saber,1,CQC)
assert(latest().source_hash==CQC and latest().source_text~='近战',
    'a real named CQC source keeps its exact name instead of the generic fallback')
local after_known=actor(6);die(after_known,0)
unknown('the known CQC target also consumes its melee credit')
assert(state.kills==6 and state.melee_kills==3 and state.ribbons.melee==3)
local sequence=state.sequence
local q=module.career_combat_query('weapons',{sequence=sequence})
assert(q.totals.kills==6 and q.coverage.unknown_kills==5,
    'generic melee text does not fabricate a weapon identity in historical unknown records')
active=false;tick(3)
assert(saved.last_mission.kills==6 and saved.last_mission.ribbons.melee==3)
local first_raw=module.combat_records_snapshot().entries[1]
assert(first_raw.weapons[UNKNOWN].kills==5 and first_raw.weapons[CQC].kills==1)

-- A new task starts from a nonzero native counter. Old cumulative melee
-- values are a baseline, never fresh prompt quota.
stats={totals={[SHOTS]=0,[KILLS]=0,[DEATHS]=0,[MELEE]=50},sources={}}
actors={};active=true;tick(3)
local next_sequence=state.sequence
local baseline_victim=actor(6);die(baseline_victim,0);tick(8)
unknown('a new-mission baseline cannot replay old cumulative melee credit')

-- An actual native melee batch with no observed target is discarded on a
-- world gap. The next observed Ability kill cannot reuse it.
native_kill(1);tick()
available=false;tick();available=true;tick(3)
local after_gap=actor(6);die(after_gap,0);tick(8)
unknown('a world gap clears unpaired melee attribution quota')

native_kill(1);tick()
module.ui_settings:set('kill_source_enabled',false)
module.ui_settings:set('kill_source_enabled',true)
assert(#state.kill_source_notices.items==0,'toggle clears old text and pending attribution state')
local after_toggle=actor(6);die(after_toggle,0);tick(8)
unknown('reenabling source text cannot reuse the old unpaired melee quota')
assert(state.kills==5 and state.ribbons.melee==52,
    'clearing hints does not roll back or synthesize native statistics')
active=false;tick(3)
rawset(_G,'HD2WarCostLedgerV1',nil);module=dofile(path);state=module.state;tick(3)
q=module.career_combat_query('weapons',{sequence=sequence})
assert(q.totals.kills==6 and q.coverage.unknown_kills==5,
    'saved unknown sources remain present after restart')
q=module.career_combat_query('weapons',{sequence=next_sequence})
assert(q.totals.kills==5 and q.coverage.unknown_kills==5)
print('PASS built melee source: native MELEE+owned Ability6 generic prompt, no held-gun identity, known CQC priority, kind6/kind0 negatives, consumed quota, new-task baseline/gap/toggle and raw history/reload')
]=]
arg={addon,runtime}
assert(loadstring(native:sub(1,boundary-1)..setup..scenario,'@built-melee-source-owned'))()
