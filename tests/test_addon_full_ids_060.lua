-- Built entry + real resolver/resource index + owned Health/entity buffers.
local addon,runtime,fixture,target_fixture=assert(arg[1]),assert(arg[2]),assert(arg[3]),assert(arg[4])
local function read(path)local f=assert(io.open(path,'rb'));local s=f:read('*a'):gsub('\r\n','\n');f:close();return s end
local native=read(fixture)
local boundary=assert(native:find('state=dofile(path).state',1,true))
local target=read(target_fixture)
local first=assert(target:find('local WI,E=native.wielder,native.engine',1,true))
local last=assert(target:find('local deaths,total,epoch',first,true))
local setup=target:sub(first,last-1):gsub("'D1E990BAF22D5A52'","'1A7FCDFF98C664B0'")
local scenario=[[
local CARRIER,SENTRY='3B49715551E4CCF1','02EECD0B1FA49630'
owners[209]=CARRIER
local module=dofile(path);state=module.state
local function tick(n)for _=1,n or 1 do clock=clock+100000;frame(.1)end end
tick(3)
next_id=next_id+1
local a={id=next_id,pointer=100000+next_id*256,kind=TYPE,life=0,health=100,credit=0x11,owner=0}
actors[#actors+1]=a;tick(3)
a.health,a.owner=50,209;tick(3)
a.health,a.life=0,2
stats.totals[KILLS]=stats.totals[KILLS]+1
stats.sources[CARRIER]={[KILLS]=1,[SHOTS]=0}
tick(3)
local notice=assert(state.kill_source_notices.items[1])
assert(state.kills==1 and notice.source_hash==SENTRY and notice.damage_source.inferred,
    'actual raw carrier: source='..tostring(notice.source_hash)..' raw='..tostring(notice.damage_source.raw_type)
    ..' local='..tostring(notice.damage_source.local_source)..' barrier='..tostring(notice.damage_source.barrier))
assert(state.weapon_stats[SENTRY].kills==1 and state.source_reassignments[CARRIER]==1,
    'one raw kill and its canonical GL-21 MK2 source are reconciled without a second kill')
local q=module.career_combat_query('weapons',{sequence=state.sequence})
assert(q.totals.kills==1 and q.coverage.unknown_kills==0)
-- A precise existing hash name wins even when the ammo is shared with a
-- player stratagem. Pelican Projectile120 must not become an autocannon sentry.
local PELICAN='8365609B35EF6672'
owners[210]=PELICAN
next_id=next_id+1
local p={id=next_id,pointer=100000+next_id*256,kind=TYPE,life=0,health=100,credit=0x11,owner=0}
actors[#actors+1]=p;tick(3)
p.health,p.owner=50,210;tick(3)
p.health,p.life=0,2;stats.totals[KILLS]=stats.totals[KILLS]+1
stats.sources[PELICAN]={[KILLS]=1,[SHOTS]=0};tick(3)
notice=assert(state.kill_source_notices.items[1])
assert(notice.source_hash==PELICAN and not notice.damage_source.inferred,
    'existing precise Pelican identity is retained rather than relabelled as a sentry')
assert(state.weapon_stats[SENTRY].kills==1 and not state.weapon_stats['54D86057F5DACFB9'])
q=module.career_combat_query('weapons',{sequence=state.sequence})
assert(q.totals.kills==2 and q.coverage.unknown_kills==0)
local seq=state.sequence
active=false;tick(3)
assert(saved.last_mission.kills==2 and saved.last_mission.source_reassignments[CARRIER]==1)
rawset(_G,'HD2WarCostLedgerV1',nil);module=dofile(path);state=module.state;tick(3)
q=module.career_combat_query('weapons',{sequence=seq})
assert(q.totals.kills==2 and q.coverage.unknown_kills==0)
print('PASS built full resource IDs: raw GL-21 MK2 carrier -> actual Projectile280 -> canonical source; precise Pelican identity retained, notice/career reconciliation and persistence.')
]]
arg={addon,runtime}
assert(loadstring(native:sub(1,boundary-1)..setup..scenario,'@built-full-source-060'))()

