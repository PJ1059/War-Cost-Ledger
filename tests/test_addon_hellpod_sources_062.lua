-- Exact pod owner -> target trace -> live notice -> career -> save/reload.
local addon,runtime,fixture,target_fixture=assert(arg[1]),assert(arg[2]),assert(arg[3]),assert(arg[4])
local function read(path)local f=assert(io.open(path,'rb'));local s=f:read('*a'):gsub('\r\n','\n');f:close();return s end
local native=read(fixture);local boundary=assert(native:find('state=dofile(path).state',1,true))
local target=read(target_fixture)
local first=assert(target:find('local WI,E=native.wielder,native.engine',1,true))
local last=assert(target:find('local deaths,total,epoch=',first,true))
local setup=target:sub(first,last-1):gsub("'D1E990BAF22D5A52'","'1A7FCDFF98C664B0'")
local scenario=[=[
local pods={'E58163E71928D3E2','EF9EB729A9D6D849','73F8498BFFDCF415'}
local labels={'绝地空投仓（初始投放）','绝地空投仓（增援）','装备空投仓'}
local module=dofile(path);state=module.state
local now=0
local function tick(n)for _=1,n or 1 do now=now+.1;clock=clock+100000;frame(.1)end end
local function actor(owner,peer)
    next_id=next_id+1
    local a={id=next_id,pointer=100000+next_id*256,kind=TYPE,life=0,health=100,credit=peer or 0x11,owner=owner,damage_kind=5}
    actors[#actors+1]=a;tick(3);return a
end
tick(12)
local before_cost=state.total_cents
for i,hash in ipairs(pods)do
    owners[210+i]=hash
    local a=actor(210+i);a.health,a.life=0,2
    stats.totals[KILLS]=stats.totals[KILLS]+1
    tick(5)
    local row=assert(state.kill_source_notices.items[1])
    assert(row.source_hash==hash and row.source_text==labels[i],
        'a genuine target-bound dropping pod must have its named source')
    assert(state.weapon_stats[hash]and state.weapon_stats[hash].kills==1,
        'observed pod attribution must reach career totals without a native source counter')
end
assert(state.kills==3 and state.ribbons.crush==0 and state.poison_kills==0,
    'hellpod source identification does not manufacture vehicle-crush or poison credit')
assert(not state.mission_medals.level_not_problem,'pods do not inherit a carried low-AP weapon trait')
assert(state.total_cents==before_cost,'source identity changes do not charge a new drop')
-- Known teammate credit is excluded even when its pod has a reviewed hash.
local remote=actor(211,0x22);remote.health,remote.life=0,2;tick(5)
assert(state.kills==3 and state.weapon_stats[pods[1]].kills==1)
local seq=state.sequence
local q=module.career_combat_query('weapons',{sequence=seq})
assert(q.coverage.unknown_kills==0 and q.totals.kills==3)
assert(q.coverage.inferred_pairs==3 and q.coverage.per_victim_weapon==false,
    'target-bound pod associations must be available as inferred, not native fatal proof')
local found={};for _,row in ipairs(q.rows)do found[row.name]=true end
for _,name in ipairs(labels)do assert(found[name],'career pod name missing: '..name)end
for _,row in ipairs(q.rows)do
    assert(#row.detail_rows==1 and row.detail_rows[1].known~=false
        and row.detail_rows[1].kills==1 and row.detail_rows[1].inferred==true,
        'opening an identified pod must show its identified target instead of a fabricated all-unknown row')
end
local enemies=module.career_combat_query('enemies',{sequence=seq})
assert(#enemies.rows==1 and #enemies.rows[1].detail_rows==3,
    'the target detail must show all three recorded pod sources')
active=false;tick()
rawset(_G,'HD2WarCostLedgerV1',nil);module=dofile(path);state=module.state;tick(3)
q=module.career_combat_query('weapons',{sequence=seq})
assert(q.totals.kills==3 and q.coverage.unknown_kills==0,'pod totals survive saving/reloading')
assert(q.coverage.inferred_pairs==3 and #q.rows[1].detail_rows==1,
    'compact pod-target associations survive saving/reloading without duplication')
print('PASS built three exact dropping pod sources: notice, career, save/reload, no teammate attribution/crush/AP/fee changes.')
]=]
arg={addon,runtime}
assert(loadstring(native:sub(1,boundary-1)..setup..scenario,'@addon-hellpod-sources-062'))()
