local create=dofile(assert(arg[1]))
local now=2000000
local E,F,G='0000000000000001','0000000000000002','0000000000000003'
local A,B,C,U='FEDCBA9876543210','0123456789ABCDEF','A123456789ABCDEF','FFFFFFFFFFFFFFFF'
local weapons={
    [A]={id='rifle',name='测试步枪',category='primary'},
    [B]={id='rifle',name='测试步枪',category='primary'},
    [C]={id='orbital',name='测试轨道攻击',category='stratagem'}}
local enemies={
    [E]={key='Charger',name_zh='强袭虫',faction='terminids',class='重型'},
    [F]={key='Voteless',name_zh='无票者',faction='illuminate',class='轻型'}}
local function factory(saved)
    return create({clock=function()return now end,weapon_catalog=weapons,enemy_catalog=enemies,saved=saved})
end
local function row(q,id)
    for _,value in ipairs(q.rows)do if value.id==id then return value end end
end
local function detail(value,id)
    for _,item in ipairs(value.detail_rows)do if item.id==id then return item end end
end
local function state(sequence)
    return {sequence=sequence,status='ended',ended_at=now-100,kills=10,deaths=0,
        weapon_stats={[A]={kills=5},[B]={kills=1},[C]={kills=2},[U]={kills=2}},
        unit_kills={Charger={count=4},Voteless={count=3}},
        kill_pairs={[E]={[A]=2,[C]=1},[F]={[A]=1}}}
end
local a=factory();local s=state(1)
assert(a:observe(s))
local weapons_query=a:query('weapons',{})
local rifle=row(weapons_query,'rifle')
assert(rifle.kills==6 and rifle.linked_kills==3 and rifle.unknown_kills==3)
assert(detail(rifle,'Charger').kills==2 and detail(rifle,'Voteless').kills==1)
assert(rifle.detail_rows[#rifle.detail_rows].id=='unknown'and detail(rifle,'unknown').kills==3,
    'known target pairs precede only their actual unknown remainder')
assert(detail(rifle,'Charger').inferred and detail(rifle,'Charger').confidence=='inferred')
assert(weapons_query.totals.kills==10 and weapons_query.totals.linked_kills==4
    and weapons_query.coverage.inferred_pairs==4 and weapons_query.coverage.linkage=='target_bound_inferred'
    and weapons_query.coverage.per_victim_weapon==false,'inferred associations never claim a native per-kill callback')
local enemy_query=a:query('enemies',{})
local charger=row(enemy_query,'Charger')
assert(charger.kills==4 and charger.linked_kills==3 and charger.unknown_kills==1
    and detail(charger,'rifle').kills==2 and detail(charger,'orbital').kills==1,
    'resource-keyed pairs align to semantic enemy IDs and work in both directions')
assert(enemy_query.totals.linked_kills==weapons_query.totals.linked_kills)
assert(a:query('weapons',{role='primary',focus_id='rifle'}).coverage.inferred_pairs==3)
assert(a:query('enemies',{faction='bugs'}).coverage.inferred_pairs==3)
assert(a:query('weapons',{query='未知'}).coverage.inferred_pairs==0)
local revision=a.revision
assert(not a:observe(s)and a.revision==revision,'repeated snapshots do not duplicate a pair')
s.kill_pairs[E][A]=1
assert(not a:observe(s),'decreasing snapshots cannot erase saved associations')
s.kill_pairs[E][A]=3
assert(a:observe(s)and a:query('weapons',{}).coverage.inferred_pairs==5,
    'a new aggregate count invalidates the retained query')
local saved=a:snapshot();local restarted=factory(saved)
assert(restarted:query('weapons',{}).coverage.inferred_pairs==5
    and restarted:snapshot().entries[1].kill_pairs[E][A]==3,'aggregate associations round trip')
saved.entries[1].kill_pairs[E][A]=999
assert(restarted:snapshot().entries[1].kill_pairs[E][A]==3,'caller-owned snapshots cannot mutate stored pairs')

-- A previous match without this optional field keeps its unknown details;
-- a new match cannot use its pairs to rewrite old history.
local old=state(2);old.kill_pairs=nil;old.ended_at=now-90000
a:observe(old)
assert(a:query('weapons',{sequence=2}).totals.linked_kills==0)
assert(a:query('weapons',{period='24h'}).totals.linked_kills==5)
assert(a:query('weapons',{period='7d'}).totals.linked_kills==5)
assert(row(a:query('weapons',{period='7d'}),'rifle').unknown_kills==8)
assert(a:snapshot().entries[2].kill_pairs==nil,'no fabricated legacy associations')

-- Clamp each match to both marginals and its native total before merging.
-- Lexically stable allocation makes weapon and enemy views agree when a
-- malformed/excess snapshot asks for more pairs than recorded kills.
local capped=factory();local excess=state(3)
excess.weapon_stats={[A]={kills=2},[B]={kills=1},[C]={kills=1}}
excess.unit_kills={Charger={count=2},Voteless={count=2}}
excess.kills=4
excess.kill_pairs={[E]={[A]=9,[B]=9,[C]=9},[F]={[A]=9,[C]=9}}
capped:observe(excess)
local wq,eq=capped:query('weapons',{}),capped:query('enemies',{})
assert(wq.totals.linked_kills==4 and eq.totals.linked_kills==4)
assert(row(wq,'rifle').linked_kills<=3 and row(wq,'orbital').linked_kills<=1)
assert(row(eq,'Charger').linked_kills<=2 and row(eq,'Voteless').linked_kills<=2)
for _,wr in ipairs(wq.rows)do
    for _,ed in ipairs(wr.detail_rows)do
        if ed.known then assert(detail(row(eq,ed.id),wr.id).kills==ed.kills,'both sides share the same capped allocation')end
    end
end
assert(capped:snapshot().entries[1].kill_pairs[E][A]==9,'display clamps do not alter raw recorded counters')
local corrected=state(4);corrected.source_reassignments={[A]=5}
corrected.kill_pairs={[E]={[A]=3,[C]=1},[F]={[A]=3}}
capped:observe(corrected)
local corrected_result=capped:query('weapons',{sequence=4})
assert(row(corrected_result,'rifle').kills==1 and row(corrected_result,'rifle').linked_kills<=1,
    'pair capacity uses corrected weapon totals, not duplicate raw source counts')

-- Raw unknown target/source hashes are retained for later labels, but they
-- do not turn readable totals into guessed links. Invalid live input is ignored.
local invalid=state(5)
invalid.kill_pairs={bad={[A]=20},[E]={[A:lower()]=1,[C]=-1,[U]=2,bad=8},[G]={[A]=2},[F]='bad'}
local b=factory();b:observe(invalid)
assert(b:snapshot().entries[1].kill_pairs[E][A]==1)
assert(b:snapshot().entries[1].kill_pairs.bad==nil and b:snapshot().entries[1].kill_pairs[E][C]==nil)
assert(b:query('weapons',{}).coverage.inferred_pairs==1,'unknown or invalid pair endpoints stay unlinked')
local broken=b:snapshot();broken.entries[1].kill_pairs[E][A]=1.5
assert(not pcall(factory,broken),'malformed saved pair counts are rejected consistently with saved combat totals')
print('PASS aggregate target-source pairs: save/reload, no backfill, two-way aliases, per-match caps/corrections, inferred labels, filters, monotone updates and unknown remainder.')
