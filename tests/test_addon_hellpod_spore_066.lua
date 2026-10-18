-- Real built addon: pod-only target evidence must correct the death source
-- before the notice, source totals, enemy/weapon pairs and saving consume it.
local addon,runtime,fixture,target_fixture=assert(arg[1]),assert(arg[2]),assert(arg[3]),assert(arg[4])
local function read(path)local f=assert(io.open(path,'rb'));local s=f:read('*a'):gsub('\r\n','\n');f:close();return s end
local native=read(fixture);local boundary=assert(native:find('state=dofile(path).state',1,true))
local target=read(target_fixture)
local first=assert(target:find('local WI,E=native.wielder,native.engine',1,true))
local last=assert(target:find('local deaths,total,epoch',first,true))
local setup=target:sub(first,last-1):gsub("'D1E990BAF22D5A52'","'6B202392F4AB605E'")
local scenario=[=[
os.clock=function()return 0 end
local pods={'E58163E71928D3E2','EF9EB729A9D6D849','73F8498BFFDCF415'}
local labels={'绝地空投仓（初始投放）','绝地空投仓（增援）','装备空投仓'}
for i,id in ipairs(pods)do owners[210+i]=id end
local module=dofile(path);state=module.state
local now=0
local function tick(n)for _=1,n or 1 do now=now+.1;clock=clock+100000;frame(.1)end end
local function actor(credit,owner)
    next_id=next_id+1
    local a={id=next_id,pointer=100000+next_id*256,kind=TYPE,life=0,health=100,
        credit=credit==nil and 0x11 or credit,owner=owner or 0,damage_kind=4}
    actors[#actors+1]=a;owners[a.id]=TYPE;tick(3);return a
end
local function pod_owner(a,index)a.owner=210+(index or 2);tick()end
local function death(a,counted)
    a.health,a.life,a.owner,a.damage_kind=0,2,a.id,4
    if counted~=false then
        stats.totals[KILLS]=stats.totals[KILLS]+1
        stats.sources[TYPE]=stats.sources[TYPE]or{[SHOTS]=0,[KILLS]=0}
        stats.sources[TYPE][KILLS]=stats.sources[TYPE][KILLS]+1
    end
end
local function latest()return assert(state.kill_source_notices.items[1])end
local function source(id,label)
    local n=latest()
    assert(n.target_hash==TYPE and n.source_hash==id and not n.damage_source.mechanism,
        label..'; actual='..tostring(n.source_hash)..'/'..tostring(n.damage_source.mechanism))
    assert(n.damage_source.inferred and n.attribution=='same_target_recent_pod_before_self_explosion')
end
tick(12)
local before_cost=state.total_cents
for i,id in ipairs(pods)do
    -- Reinforcement pod also covers the first-live baseline already holding
    -- the pod owner; there is no intermediate owner change or HP loss.
    local a=actor(nil,i==2 and 212 or nil)
    if i~=2 then pod_owner(a,i)end
    death(a);tick(4)
    source(id,'each reviewed exact local falling body survives its target final self blast')
    assert(latest().source_text==labels[i]and state.weapon_stats[id].kills==1
        and state.kill_pairs[TYPE][id]==1,'source reaches visible notice, weapon totals and target pair')
end
assert(state.kills==3 and state.source_reassignments[TYPE]==3,
    'three native self-source counters are corrected exactly once, not added to three pod kills')
assert(state.total_cents==before_cost and state.ribbons.crush==0
    and not state.mission_medals.level_not_problem,'source-only repair adds no pod fees, vehicle crush or carried-weapon AP reward')
-- One shared poll: pod signal belongs only to its actual target, never to the
-- unanchored second enemy or to an enemy hit by another known weapon.
local self_only=actor()
local gun=actor();gun.owner,gun.health,gun.damage_kind=201,60,0;tick()
local pod=actor();pod_owner(pod,2)
death(pod);death(self_only);death(gun);tick(8)
assert(state.kills==6 and state.weapon_stats[pods[2]].kills==2
    and state.weapon_stats[AC].kills==1 and state.kill_pairs[TYPE][AC]==1,
    'mixed simultaneous deaths keep separate pod, known gun, and unanchored self sources')
assert(state.kill_pairs[TYPE][TYPE]==1 and state.source_reassignments[TYPE]==5)
-- Missing creditor is still gated by a genuine local native kill quota.
local missing=actor(0);pod_owner(missing,2);death(missing);tick(5)
source(pods[2],'missing creditor uses the existing real native quota after target pod attribution')
assert(state.kills==7 and state.kill_pairs[TYPE][pods[2]]==3)
local pair_count=state.kill_pairs[TYPE][pods[2]]
local reward_count=state.ribbons.heavy_spore_charger
local no_quota=actor(0);pod_owner(no_quota,2);death(no_quota,false);tick(10)
assert(state.kills==7 and state.kill_pairs[TYPE][pods[2]]==pair_count
    and state.ribbons.heavy_spore_charger==reward_count,'no native quota cannot turn an unattributed pod candidate into rewards')
local remote=actor(0x22);pod_owner(remote,2);death(remote,false);tick(5)
assert(state.kills==7 and state.kill_pairs[TYPE][pods[2]]==pair_count
    and state.ribbons.heavy_spore_charger==reward_count,'explicit other peer cannot receive local pod credit or rewards')
local seq=state.sequence
local function verify()
    local q=module.career_combat_query('weapons',{sequence=seq})
    assert(q.totals.kills==7 and q.coverage.unknown_kills==0)
    local counts={};for _,row in ipairs(q.rows)do counts[row.id]=row.kills end
    assert(counts[pods[1]]==1 and counts[pods[2]]==3 and counts[pods[3]]==1
        and counts[AC]==1 and counts[TYPE]==1,'career applies raw self-source corrections without duplicate kills')
end
verify();active=false;tick(3)
rawset(_G,'HD2WarCostLedgerV1',nil);module=dofile(path);state=module.state;tick(3)
verify()
print('PASS built pod/spore: three pod variants, target-specific notice/totals/pairs/correction, mixed burst, missing quota and foreign exclusions, no extra fee/crush/AP, save/reload.')
]=]
arg={addon,runtime}
assert(loadstring(native:sub(1,boundary-1)..setup..scenario,'@addon-hellpod-spore-066'))()
