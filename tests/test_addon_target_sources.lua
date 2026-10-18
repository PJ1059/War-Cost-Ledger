-- Built addon and production native target trace/reconciliation/persistence.
-- Reuse owned Health/entity-map byte buffers; do not replace production modules.
local addon,runtime,fixture,target_fixture=assert(arg[1]),assert(arg[2]),assert(arg[3]),assert(arg[4])
local function read(path)local f=assert(io.open(path,'rb'));local s=f:read('*a'):gsub('\r\n','\n');f:close();return s end
local native=read(fixture);local boundary=assert(native:find('state=dofile(path).state',1,true))
local target=read(target_fixture)
local first=assert(target:find('local WI,E=native.wielder,native.engine',1,true))
local last=assert(target:find('local deaths,total,epoch=',first,true))
local setup=target:sub(first,last-1):gsub("'D1E990BAF22D5A52'","'1A7FCDFF98C664B0'")
local scenario=[=[
local module=dofile(path);state=module.state
local now=0
local function tick(n)for _=1,n or 1 do now=now+.1;clock=clock+100000;frame(.1)end end
local function actor()
    next_id=next_id+1
    local a={id=next_id,pointer=100000+next_id*256,kind=TYPE,life=0,health=100,credit=0x11,owner=0}
    actors[#actors+1]=a;tick(3);return a
end
local function hit(a,health,owner,dead,credited)
    a.health,a.owner=health,owner
    if dead then
        a.life=2;stats.totals[KILLS]=stats.totals[KILLS]+1
        local hash=credited or owners[owner]or'FFFFFFFFFFFFFFFF'
        local row=stats.sources[hash]or{[SHOTS]=0,[KILLS]=0};stats.sources[hash]=row
        row[KILLS]=row[KILLS]+1
    end
    tick(3)
end
local function find(rows,id)for _,row in ipairs(rows)do if row.id==id then return row end end end
tick(3)
local a=actor();hit(a,75,201);hit(a,50,203);hit(a,25,203);hit(a,0,203,true)
assert(state.kills==1 and state.weapon_stats[AC].kills==1)
assert(state.weapon_stats['FFFFFFFFFFFFFFFF'].kills==1 and state.source_reassignments['FFFFFFFFFFFFFFFF']==1,
    'target-bound inherited weapon preserves native unknown hash with a separate exact correction')
local q=module.career_combat_query('weapons',{sequence=state.sequence})
assert(q.totals.kills==1 and q.coverage.unknown_kills==0 and #q.rows==1 and q.rows[1].name=='AC-8 机炮',
    'the native unknown source kill and the inherited weapon represent one kill')
local notice=state.kill_source_notices.items[1]
assert(notice and notice.source_hash==AC and notice.damage_source.inferred,'compact feedback uses the same target-bound inherited weapon')

local b=actor();hit(b,75,201);hit(b,50,203);hit(b,25,0);hit(b,0,0,true)
q=module.career_combat_query('weapons',{sequence=state.sequence})
assert(state.kills==2 and state.weapon_stats[AC].kills==2 and q.totals.kills==2 and q.coverage.unknown_kills==0,
    'continuous real damage keeps the latest AC8 across unknown owner changes without duplicating native kills')
assert(state.source_reassignments._unknown==1,
    'an inferred kill with no raw resource records an anonymous correction budget rather than inventing a hash')
notice=state.kill_source_notices.items[1]
assert(notice and not notice.damage_source.barrier and notice.source_hash==AC,
    'changing unknown owner within1.5s no longer interrupts the same-target damage chain')

local c=actor();hit(c,75,202);hit(c,0,202,true)
assert(state.mission_medals.level_not_problem==1,'actual low-AP source kills a heavy target and earns M11')
assert(module.career_award_snapshot().totals.medals.level_not_problem==1
    and module.mission_history_snapshot().entries[1].medals.level_not_problem==1)
assert(find(module.game_hud:native_model(now,true,600).awards.items,'M11'),
    'the acquisition reaches the actual live achievement popup pipeline')
q=module.career_combat_query('weapons',{sequence=state.sequence})
assert(q.totals.kills==3 and q.coverage.unknown_kills==0)
local d=actor();hit(d,60,42);hit(d,0,42,true,AC)
notice=state.kill_source_notices.items[1]
assert(notice and notice.source_hash==AC and notice.attribution=='fifo_source_count'
    and notice.damage_source.history_complete and not notice.damage_source.barrier
    and not notice.damage_source.type,
    'actual native AC8 credit survives an avatar-only target history with no source contradiction')
local gas='0416984F4922757B'
local e=actor();hit(e,60,42);hit(e,0,42,true,gas)
notice=state.kill_source_notices.items[1]
assert(notice and notice.source_hash==gas and notice.source_text=='G-4 毒气榴弹'
    and notice.attribution=='fifo_source_count',
    'actual native G4 credit survives the same missing target weapon observation')
q=module.career_combat_query('weapons',{sequence=state.sequence})
assert(state.kills==5 and stats.sources[AC][KILLS]==1 and state.weapon_stats[gas].kills==1
    and q.totals.kills==5,
    'restored notices do not add any native source kill statistics')
local expected_unknown=q.coverage.unknown_kills
local seq=state.sequence;active=false;tick()
assert(saved.last_mission.source_reassignments['FFFFFFFFFFFFFFFF']==state.source_reassignments['FFFFFFFFFFFFFFFF'])
local raw=module.combat_records_snapshot().entries[1]
assert(raw.weapons['FFFFFFFFFFFFFFFF'].kills==2
    and raw.source_reassignments['FFFFFFFFFFFFFFFF']==state.source_reassignments['FFFFFFFFFFFFFFFF']
    and raw.source_reassignments._unknown==1,
    'raw native source totals remain unchanged in the saved match')
rawset(_G,'HD2WarCostLedgerV1',nil);module=dofile(path);state=module.state;tick(3)
q=module.career_combat_query('weapons',{sequence=seq})
assert(q.totals.kills==5 and q.coverage.unknown_kills==expected_unknown
    and module.career_award_snapshot().totals.medals.level_not_problem==1,
    'restart does not duplicate the correction or the acquisition')
print('PASS built target attribution: continuous AC8 across unknown owners, current native AC8/G4 despite unknown-only avatar history, no added kills, low AP M11, save/restart.')
]=]
arg={addon,runtime}
assert(loadstring(native:sub(1,boundary-1)..setup..scenario,'@addon-native-target-sources'))()
