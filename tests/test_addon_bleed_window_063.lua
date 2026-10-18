-- Actual built entry, same target: known Eruptor damage followed by delayed
-- unnamed bleed death, with source totals and compact career pairs persisted.
local addon,runtime,fixture,target_fixture=assert(arg[1]),assert(arg[2]),assert(arg[3]),assert(arg[4])
local function read(path)local f=assert(io.open(path,'rb'));local s=f:read('*a'):gsub('\r\n','\n');f:close();return s end
local native=read(fixture);local boundary=assert(native:find('state=dofile(path).state',1,true))
local target=read(target_fixture)
local first=assert(target:find('local WI,E=native.wielder,native.engine',1,true))
local last=assert(target:find('local deaths,total,epoch',first,true))
local setup=target:sub(first,last-1):gsub("'D1E990BAF22D5A52'","'F79CD8BB654397DF'")
local scenario=[=[
local ERUPTOR,UNKNOWN='B6AFF2195568767F','FFFFFFFFFFFFFFFF'
owners[211]=ERUPTOR
local module=dofile(path);state=module.state
local now=0
local function tick(n)for _=1,n or 1 do now=now+.1;clock=clock+100000;frame(.1)end end
local function actor()
    next_id=next_id+1
    local a={id=next_id,pointer=100000+next_id*256,kind=TYPE,life=0,health=100,credit=0x11,owner=0}
    actors[#actors+1]=a;tick(3);return a
end
local function known_hit(a)a.health,a.owner,a.damage_kind=35,211,0;tick()end
local function bleed(a)
    a.health,a.owner,a.damage_kind,a.life=0,203,9,2
    stats.totals[KILLS]=stats.totals[KILLS]+1
    local row=stats.sources[UNKNOWN]or{[SHOTS]=0,[KILLS]=0};stats.sources[UNKNOWN]=row
    row[KILLS]=row[KILLS]+1;tick(3)
end
tick(12)
local a=actor();known_hit(a);tick(39);bleed(a)
local notice=assert(state.kill_source_notices.items[1])
assert(notice.target_text=='阿尔法指挥官'and notice.source_hash==ERUPTOR
    and notice.source_text=='R-36 爆裂铳'and notice.damage_source.inferred,
    'Eruptor damage followed by the same Alpha Commander bleeding out 4s later retains the weapon')
assert(state.weapon_stats[ERUPTOR].kills==1 and state.kill_pairs[TYPE][ERUPTOR]==1,
    'delayed inferred kill reaches source totals and target association')
local b=actor();known_hit(b);tick(50);bleed(b)
notice=assert(state.kill_source_notices.items[1])
assert(notice.source_hash~=ERUPTOR,'5.1s with no actual damage must expire the earlier weapon')
assert(state.kills==2 and state.weapon_stats[ERUPTOR].kills==1)
local seq=state.sequence
local q=module.career_combat_query('weapons',{sequence=seq})
assert(q.totals.kills==2 and q.coverage.unknown_kills==1 and q.coverage.inferred_pairs==1)
active=false;tick(3)
rawset(_G,'HD2WarCostLedgerV1',nil);module=dofile(path);state=module.state;tick(3)
q=module.career_combat_query('weapons',{sequence=seq})
assert(q.totals.kills==2 and q.coverage.unknown_kills==1 and q.coverage.inferred_pairs==1,
    'saving/reloading retains one linked Eruptor kill and one genuinely expired source')
print('PASS built Eruptor/Alpha: 4s bleed attribution,5.1s expiry,source totals,target pairs,save/reload; no fabricated kills.')
]=]
arg={addon,runtime}
assert(loadstring(native:sub(1,boundary-1)..setup..scenario,'@addon-bleed-window-063'))()
