-- Regression replay for a pod contact captured in the same poll as an
-- already-dead Spore Charger. The pod contact is death-only evidence;
-- it must survive the enemy's final self-explosion, without inventing a live
-- HP-loss chain. Uses the existing owned native Health/entity-map fixture.
local observer_path,runtime_root,fixture,trace_path,resolver_path=
    assert(arg[1]),assert(arg[2]),assert(arg[3]),assert(arg[4]),assert(arg[5])
local function read(path)local f=assert(io.open(path,'rb'));local s=f:read('*a'):gsub('\r\n','\n');f:close();return s end
local native=read(fixture)
local boundary=assert(native:find('state=dofile(path).state',1,true))
local target=read('tests/test_target_damage_observer.lua')
local first=assert(target:find('local WI,E=native.wielder,native.engine',1,true))
local last=assert(target:find('local deaths,total,epoch=',first,true))
local setup=target:sub(first,last-1):gsub("'D1E990BAF22D5A52'","'6B202392F4AB605E'")
local scenario=[=[
local create=dofile(path)
local trace=dofile(_TRACE_PATH)()
local POD='EF9EB729A9D6D849'
owners[211]=POD
local api=require('hd2runtime/runtime/event_world')
local deaths,total,epoch={},0,1
local observer=create(api,native,{[TYPE]={kill=true}},function(event)deaths[#deaths+1]=event end,
    {local_kills=function()return total end,damage_attribution=trace,
        source_types={[POD]={kind='hellpod'},[AC]={kind='weapon'}},damage_resolver=dofile(_RESOLVER_PATH)()})
local players={{['local']=true,peer='0000000000000011'}}
local function tick(n)for _=1,n or 1 do observer:poll(world,players,.1,epoch)end end
local function reset()observer:reset();actors,deaths={},{};total,epoch=0,1;tick()end
local function make(life)
    next_id=next_id+1
    local a={id=next_id,pointer=100000+next_id*256,kind=TYPE,life=life or 0,
        health=(life==2)and 0 or 100,credit=0x11,owner=0,damage_kind=4}
    actors[#actors+1]=a;owners[a.id]=TYPE;return a
end
local function pod_contact(a)
    assert(observer:contact({verified=true,local_player=true,direct=true,
        attack='projectile',result='penetration',target=a.id,source=211,owner=42}))
end
local failed={}
local function check(ok,label)
    print((ok and 'PASS 'or'FAIL ')..label)
    if not ok then failed[#failed+1]=label end
end
do
    local function row(fields)
        local r={entity=101,pointer=100000,unit=202,epoch=1,health=100,life=0,
            now=0,damage_observed=false,readable=true,local_source=true,owner=211}
        for k,v in pairs(fields or{})do r[k]=v end
        return r
    end
    local function candidate(fields)
        local t=trace:baseline(row())
        local r=row({now=.1,source_type=POD,raw_type=POD,source_kind='hellpod'})
        for k,v in pairs(fields or{})do r[k]=v end
        return trace:observe(t,r)
    end
    local function blast(t,at,fields)
        local r=row({now=at,health=0,life=2,damage_observed=true,owner=101,
            source_type=TYPE,raw_type=TYPE,mechanism='self_explosion',kind=4})
        for k,v in pairs(fields or{})do r[k]=v end
        return trace:death(trace:observe(t,r))
    end
    local d=blast(candidate(),.85)
    check(d.type==POD and d.inferred and not d.mechanism and d.raw_type==TYPE
        and not d.last_damage_at and not d.last_known_at,
        'pure trace includes exact 0.75 second pod boundary without inventing HP-loss history')
    local t=candidate()
    t=trace:observe(t,row({now=.8,source_type=POD,raw_type=POD,source_kind='hellpod'}))
    check(blast(t,.851).type==TYPE,'re-reading the same no-HP pod owner cannot renew the short window')
    for _,change in ipairs({{entity=102},{pointer=100001},{unit=203},{epoch=2},
            {local_source=false,creditor_missing=false}})do
        check(blast(candidate(),.2,change).type==TYPE,
            'pure trace excludes mismatched target/epoch or explicit foreign credit')
    end
    t=trace:observe(candidate(),row({now=.15,readable=false}))
    check(blast(t,.2).type==TYPE,'a failed target read drops pod-only evidence')
    t=trace:observe(candidate(),row({now=.15,source_type=AC,raw_type=AC,source_kind='weapon'}))
    check(blast(t,.2).type==TYPE,'a newer known non-pod owner contradicts the pending pod source')
    check(blast(candidate({local_source=false,creditor_missing=true}),.2,
        {local_source=false,creditor_missing=true}).type==POD,
        'missing-creditor pod evidence can be resolved before the unchanged native quota gate')
end
-- A pod may already be the exact cached Health owner in the first live
-- baseline, so no intervening owner change triggers enrich() before death.
reset();local baseline_pod=make();baseline_pod.owner=211;tick()
baseline_pod.owner,baseline_pod.health,baseline_pod.life=baseline_pod.id,0,2;total=1;tick(3)
local baseline_source=deaths[1]and deaths[1].damage_source
check(#deaths==1 and baseline_source.type==POD and baseline_source.inferred and not baseline_source.mechanism,
    'first live baseline already bound to a pod is retained before its next-poll self explosion; actual='
        ..tostring(baseline_source and baseline_source.type)..'/'..tostring(baseline_source and baseline_source.mechanism))
reset();baseline_pod=make();baseline_pod.owner=211;tick();tick(8)
baseline_pod.owner,baseline_pod.health,baseline_pod.life=baseline_pod.id,0,2;total=1;tick(3)
check(#deaths==1 and deaths[1].damage_source.type==TYPE,
    'a first-live baseline pod owner older than the short window is not revived')
-- Control: a real pod source observed on an alive-to-dead transition works.
reset();local a=make();tick();a.owner=211;a.health,a.life=50,0;tick()
a.owner,a.health,a.life=a.id,0,2;total=1;tick(3)
check(#deaths==1 and deaths[1].damage_source.type==POD,
    'a recent target-bound live pod damage chain survives the final self explosion')
-- A collision owner can be visible one poll before replicated HP/life falls.
-- This exact falling-body source is suitable for a short pod-only candidate,
-- never for an ordinary held-weapon damage chain.
reset();a=make();tick();a.owner=211;tick();a.owner,a.health,a.life=a.id,0,2;total=1;tick(3)
local d=deaths[1]and deaths[1].damage_source
check(#deaths==1 and d.type==POD and d.inferred and not d.mechanism,
    'recent exact local target Health pod owner survives its final self explosion; actual='
        ..tostring(d and d.type)..'/'..tostring(d and d.mechanism))
-- Failure: contact supplies the exact local pod during the first corpse read.
-- This is an existing verified native contact input, not a proximity guess.
reset();a=make(2);a.owner=a.id;pod_contact(a);total=1;tick(3)
d=deaths[1]and deaths[1].damage_source
check(#deaths==1 and d.type==POD and d.inferred and not d.mechanism
    and d.last_damage_at==nil and d.last_known_at==nil,
    'first-seen-dead local pod contact survives same-poll self explosion without a fake live chain; actual='
        ..tostring(d and d.type)..'/'..tostring(d and d.mechanism))
-- Control: a corpse with no independent weapon evidence remains self blast.
reset();a=make(2);a.owner=a.id;total=1;tick(3)
check(#deaths==1 and deaths[1].damage_source.type==TYPE
    and deaths[1].damage_source.mechanism=='self_explosion',
    'no independent pod evidence remains a genuine self-explosion source')
reset();a=make();tick();a.owner=201;tick();a.owner,a.health,a.life=a.id,0,2;total=1;tick(3)
check(#deaths==1 and deaths[1].damage_source.type==TYPE
    and deaths[1].damage_source.mechanism=='self_explosion',
    'ordinary named weapon metadata without real damage still cannot create an anchor')
reset();a=make();tick();a.owner=211;tick();tick(8)
a.owner,a.health,a.life=a.id,0,2;total=1;tick(3)
check(#deaths==1 and deaths[1].damage_source.type==TYPE
    and deaths[1].damage_source.mechanism=='self_explosion',
    'pod-only no-HP evidence expires after the bounded native observation window')
-- Control: explicit other-player credit must not be funded by local quota.
reset();a=make(2);a.owner,a.credit=a.id,0x22;pod_contact(a);total=1;tick(3)
check(#deaths==0,'an explicit other peer corpse does not become a local pod kill')
assert(#failed==0,'hellpod/spore regression failures: '..table.concat(failed,'; '))
print('PASS hellpod/spore first-seen-dead regression and live/no-evidence/other-peer boundaries.')
]=]
arg={observer_path,runtime_root};_TRACE_PATH=trace_path;_RESOLVER_PATH=resolver_path
assert(loadstring(native:sub(1,boundary-1)..setup..scenario,'@hellpod-spore-066'))()
