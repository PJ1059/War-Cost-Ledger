local create=dofile(assert(arg[1]))
local icons={{kind='ribbon',key='air'},{kind='ribbon',key='recon'},
    {kind='medal',key='democracy_harvester'},{kind='medal',key='fragrant'}}
local function state(seq)
    return {sequence=seq,mission=true,status='active',stats_ready=false,
        ribbons={},mission_medals={},history_kills=351849,history_deaths=4633,
        history_reason='CAREER_BASELINE_PLUS_OBSERVED_DELTAS'}
end
local tests=0
local function check(name,fn)fn();tests=tests+1;print('PASS '..name)end
check('waiting and invalid sequences never invent a historical mission',function()
    local history=create({icons=icons})
    for _,s in ipairs({{sequence=0,mission=true},{sequence=-1,mission=true},
        {sequence=1.5,mission=true},{sequence=1,status='waiting'},
        {sequence=math.huge,mission=true},{sequence=0/0,mission=true}})do
        assert(not history:observe(s))
    end
    assert(#history:entries()==0 and history.revision==0)
end)
check('actual start active snapshots and all exits keep one exact mission',function()
    local now=100
    local history=create({icons=icons,clock=function()return now end})
    local s=state(19)
    assert(history:observe(s))
    local entry=history:entries()[1]
    assert(entry.sequence==19 and entry.status=='active' and entry.started_at==100)
    assert(entry.kills==nil and entry.deaths==nil and entry.history_before.kills==351849)
    s.stats_ready=true;s.kills=109;s.deaths=0;s.ribbons={air=3,recon=1,unknown=999}
    s.mission_medals={democracy_harvester=true,fragrant=false}
    s.medals={fragrant=true}
    now=110;assert(history:observe(s))
    assert(entry.kills==109 and entry.deaths==0 and entry.ribbons.air==3)
    assert(entry.ribbons.unknown==nil and entry.medals.democracy_harvester==1 and entry.medals.fragrant==nil)
    local revision=history.revision
    assert(not history:observe(s) and history.revision==revision)
    s.ribbons.air=5;s.mission=false;s.status='ended';s.history_kills=351958
    now=130;assert(history:observe(s))
    assert(#history:entries()==1 and entry.status=='ended' and entry.ended_at==130)
    assert(entry.ribbons.air==5 and entry.history_after.kills==351958 and entry.history_after.deaths==4633)
    assert(entry.kd==nil and entry.kd_text==nil,'KD is computed by the presentation model')
    now=140;assert(not history:observe(s) and entry.ended_at==130)
    assert(not history:observe({sequence=19,status='waiting'}) and #history:entries()==1)
    s.mission=true;s.status='active';s.kills=999
    assert(not history:observe(s) and entry.kills==109,'late active sample cannot reopen an ended entry')
end)
check('partial invalid and rolled back samples cannot erase observed awards or counters',function()
    local history=create({icons=icons})
    local s=state(20);s.kills=7;s.deaths=1;s.ribbons={air=4};s.mission_medals={democracy_harvester=true}
    history:observe(s)
    s.kills=-1;s.deaths=0/0;s.ribbons={air=0,recon=math.huge};s.mission_medals={democracy_harvester=1}
    assert(not history:observe(s))
    s.kills=nil;s.deaths=nil;s.ribbons=nil;s.mission_medals=nil
    assert(not history:observe(s))
    local entry=history:entries()[1]
    assert(entry.kills==7 and entry.deaths==1 and entry.ribbons.air==4 and entry.medals.democracy_harvester==1)
    assert(entry.started_at==nil and entry.history_before==nil,'a mid-mission snapshot is not an observed start')
end)
check('new sequence interrupts unfinished snapshot and repeated medals remain per mission',function()
    local history=create({icons=icons,clock=function()return 500 end})
    local a=state(21);a.mission_medals.fragrant=true;history:observe(a)
    local b=state(22);b.mission_medals.fragrant=true;history:observe(b)
    local entries=history:entries()
    assert(#entries==2 and entries[1].sequence==22 and entries[2].sequence==21)
    assert(entries[2].status=='interrupted' and entries[2].ended_at==nil and entries[2].history_after==nil)
    assert(entries[1].medals.fragrant==1 and entries[2].medals.fragrant==1)
    a.status='ended';assert(not history:observe(a),'old frames cannot revise the previous mission')
end)
check('restart marks only active entries interrupted and never guesses an end time',function()
    local original=create({icons=icons,clock=function()return 10 end})
    local s=state(30);original:observe(s);s.mission=false;s.status='ended';original:observe(s,20)
    local active=state(31);active.kills=3;original:observe(active,30)
    local saved=original:snapshot()
    local restarted=create({icons=icons,saved=saved,clock=function()return 999 end})
    assert(saved.entries[1].status=='active','loading must not mutate the persisted input')
    assert(restarted.revision==1 and restarted:entries()[1].status=='interrupted')
    assert(restarted:entries()[1].kills==3 and restarted:entries()[1].ended_at==nil)
    assert(restarted:entries()[2].status=='ended' and restarted:entries()[2].ended_at==20)
    assert(not restarted:observe(active),'saved stale active snapshot must not reopen')
    assert(restarted:observe(state(32)))
end)
check('delete removes only its mission and a persisted tombstone prevents recreation',function()
    local history=create({icons=icons})
    local a,b=state(40),state(41)
    a.ribbons.air=2;b.ribbons.air=6
    history:observe(a);a.status='ended';a.mission=false;history:observe(a)
    history:observe(b)
    local lifetime={ribbons={air=8}}
    assert(history:remove(40) and #history:entries()==1 and history:entries()[1].sequence==41)
    assert(lifetime.ribbons.air==8 and a.ribbons.air==2 and b.ribbons.air==6)
    local revision=history.revision
    assert(not history:remove(40) and history.revision==revision)
    assert(history:remove(41) and #history:entries()==0,'active deletion is explicit and permanent')
    assert(not history:observe(b));b.status='ended';assert(not history:observe(b))
    local restart=create({icons=icons,saved=history:snapshot()})
    assert(not restart:observe(a) and not restart:observe(b))
    assert(restart:observe(state(42)) and #restart:entries()==1)
end)
check('legacy migration imports at most the explicit last mission with unknown timestamps',function()
    local last=state(17);last.status='ended';last.mission=false;last.kills=382;last.deaths=0
    last.ribbons={air=2};last.mission_medals={democracy_harvester=true};last.medals={fragrant=true}
    last.started_at=1;last.ended_at=2
    local legacy={last_mission=last,combat_history={kills=999999,medals={fragrant=true}},
        career_awards_v1={totals={ribbons={air=9999}}}}
    local migrated=create({icons=icons,legacy=legacy,clock=function()return 333 end})
    local entry=migrated:entries()[1]
    assert(#migrated:entries()==1 and entry.kills==382 and entry.ribbons.air==2)
    assert(entry.medals.democracy_harvester==1 and entry.medals.fragrant==nil)
    assert(entry.started_at==nil and entry.ended_at==nil and entry.history_before==nil and entry.history_after==nil)
    local direct=create({icons=icons,legacy=last})
    assert(direct:entries()[1].sequence==17,'offline approved import may pass its source state directly')
    assert(not migrated:observe(last),'repeated legacy ending cannot retime or duplicate it')
    local restarted=create({icons=icons,saved=migrated:snapshot(),legacy=legacy})
    assert(#restarted:entries()==1 and restarted.revision==0)
    legacy.last_mission={sequence=18,status='waiting',ribbons={air=999}}
    assert(#create({icons=icons,legacy=legacy}):entries()==0)
    assert(#create({icons=icons,legacy={combat_history={kills=999999}}}):entries()==0)
    last.status='active';last.mission=true
    assert(create({icons=icons,legacy=last}):entries()[1].status=='interrupted')
end)
check('career delta requires an observed start and known valid totals at the end',function()
    local history=create({icons=icons})
    local s=state(50);s.history_reason=nil;history:observe(s,1)
    s.status='ended';s.mission=false;s.history_reason='CAREER_BASELINE_PLUS_OBSERVED_DELTAS'
    history:observe(s,2)
    assert(history:entries()[1].history_before==nil and history:entries()[1].history_after==nil)
    s=state(51);history:observe(s,3);s.status='ended';s.mission=false;s.history_deaths=4632
    history:observe(s,4);assert(history:entries()[1].history_after==nil,'reset career totals are not a delta')
    s.history_deaths=4633;s.history_kills=351859;assert(not history:observe(s,5))
    assert(history:entries()[1].history_after==nil and history:entries()[1].ended_at==4,
        'a later valid career synchronization cannot backfill an unknown end')
end)
check('first ended career endpoint stays fixed across later syncs and restart',function()
    local history=create({icons=icons})
    local s=state(52);history:observe(s,10)
    s.status='ended';s.mission=false;s.kills=10;s.deaths=1
    s.history_kills=351859;s.history_deaths=4634;history:observe(s,20)
    local entry=history:entries()[1]
    local revision=history.revision
    s.history_kills=400000;s.history_deaths=5000
    assert(not history:observe(s,100) and history.revision==revision)
    assert(entry.history_after.kills==351859 and entry.history_after.deaths==4634 and entry.ended_at==20)
    s.history_kills=351849;s.history_deaths=4633
    assert(not history:observe(s,200),'a valid but stale page must not revise a recorded endpoint downward')
    local restart=create({icons=icons,saved=history:snapshot()})
    assert(not restart:observe(s,300))
    assert(restart:entries()[1].history_after.kills==351859 and restart:entries()[1].history_after.deaths==4634)
    s=state(53);history:observe(s,30);s.status='ended';s.mission=false;s.history_reason=nil
    history:observe(s,40)
    local unknown=create({icons=icons,saved=history:snapshot()})
    s.history_reason='CAREER_BASELINE_PLUS_OBSERVED_DELTAS';s.history_kills=351900
    assert(not unknown:observe(s,50) and unknown:entries()[1].history_after==nil,
        'an unknown endpoint remains unknown across restart too')
end)
check('snapshot copies input and output deeply while stable entries reuse their view',function()
    local s=state(60);s.ribbons.air=1
    local history=create({icons=icons});history:observe(s)
    local view=history:entries();local snap=history:snapshot()
    s.ribbons.air=900;s.history_kills=99
    snap.entries[1].ribbons.air=800;snap.deleted['60']=true
    assert(view[1].ribbons.air==1 and view[1].history_before.kills==351849)
    for _=1,1000 do assert(history:entries()==view)end
    assert(history:snapshot().deleted['60']==nil)
end)
check('missing or failing clock leaves unknown time and the explicit cap never deletes records',function()
    local history=create({icons=icons,clock=function()error('unavailable')end})
    assert(history.limit==500)
    for seq=1,500 do
        local s=state(seq);history:observe(s);s.status='ended';s.mission=false;history:observe(s)
    end
    assert(#history:entries()==500 and history:entries()[1].sequence==500 and history:entries()[500].sequence==1)
    assert(history:entries()[1].started_at==nil and history:entries()[1].ended_at==nil)
    local revision=history.revision
    local changed,why=history:observe(state(501))
    assert(not changed and why=='limit' and history.revision==revision)
    assert(#history:entries()==500 and history:snapshot().max_sequence==500)
    local ended=state(500);ended.status='ended';ended.mission=false;ended.kills=2
    assert(history:observe(ended) and history:entries()[1].kills==2,'the cap only rejects new entries')
    assert(history:remove(1) and history:observe(state(501)))
    assert(#history:entries()==500 and history:entries()[1].sequence==501 and history:entries()[500].sequence==2)
    assert(not history:observe(state(1)),'deleting an older entry cannot make it replayable')
    assert(not pcall(create,{icons=icons,saved={version=2,entries={},deleted={}}}),
        'unsupported saved format must not silently replace history with legacy')
end)
check('saved overflow remains intact and old deletion maps collapse to the maximum sequence',function()
    local saved={version=1,entries={},deleted={['10']=true,['20']=true,['603']=true}}
    for seq=1,602 do
        saved.entries[#saved.entries+1]={sequence=seq,status='ended',kills=seq,ribbons={},medals={}}
    end
    local history=create({icons=icons,saved=saved})
    assert(#history:entries()==600 and history:entries()[1].sequence==602)
    local snapshot=history:snapshot();local tombstones=0
    for key in pairs(snapshot.deleted)do tombstones=tombstones+1;assert(key=='603')end
    assert(tombstones==1 and snapshot.max_sequence==603)
    assert(saved.deleted['10'] and #saved.entries==602,'migration does not mutate its source')
    assert(not history:observe(state(604)) and not history:observe(state(603)))
    assert(not history:observe(state(10)) and not history:observe(state(20)))
    for seq=21,121 do assert(history:remove(seq))end
    assert(#history:entries()==499 and history:observe(state(604)))
    snapshot=history:snapshot()
    assert(snapshot.max_sequence==604 and next(snapshot.deleted)==nil and #snapshot.entries==500)
    local restarted=create({icons=icons,saved=snapshot})
    assert(not restarted:observe(state(603)) and not restarted:observe(state(21)))
end)
check('only the current highest deletion survives and 16 digit sequences round trip exactly',function()
    local history=create({icons=icons})
    for seq=1,1000 do
        assert(history:observe(state(seq)))
        assert(history:remove(seq))
    end
    local snapshot=history:snapshot();local amount=0
    for key in pairs(snapshot.deleted)do amount=amount+1;assert(key=='1000')end
    assert(amount==1 and snapshot.max_sequence==1000 and #snapshot.entries==0)
    local restarted=create({icons=icons,saved=snapshot})
    assert(not restarted:observe(state(999)) and not restarted:observe(state(1000)))
    local maximum=9007199254740991
    assert(restarted:observe(state(maximum)) and restarted:remove(maximum))
    local large=restarted:snapshot()
    assert(large.deleted['9007199254740991']==true)
    local exact=create({icons=icons,saved=large})
    assert(not exact:observe(state(maximum)) and exact:snapshot().max_sequence==maximum)
end)
print('Mission history tests passed: '..tests..' (pure snapshots; no game/account writes)')

check('patriotic bills keep exact charges grouped without native identities and survive disabled billing',function()
    local history=create({icons=icons});local s=state(1002)
    s.billing_enabled=true;s.total_cents=2400
    s.entries={{price_id='ac8',event='ammunition_fired',name='AC-8 弹药',amount_cents=1000,beacon_entity=999},
        {price_id='ac8',event='ammunition_fired',name='AC-8 弹药',amount_cents=1000},
        {price_id='las',event='weapon_maintenance',name='激光维护折旧费',amount_cents=400}}
    assert(history:observe(s));local bill=history:entries()[1].patriotic_bill
    assert(bill.total_cents==2400 and #bill.entries==2 and bill.entries[1].amount_cents==2000)
    assert(bill.entries[1].beacon_entity==nil and bill.entries[1].quantity==nil)
    s.entries[1].amount_cents=0;assert(bill.entries[1].amount_cents==2000,'saved bill does not borrow mutable state rows')
    s.billing_enabled=false;s.total_cents=0;s.entries={};assert(not history:observe(s))
    assert(history:entries()[1].patriotic_bill.total_cents==2400,'disabling does not erase recorded charges')
    local saved=history:snapshot();local restored=create({icons=icons,saved=saved})
    assert(restored:entries()[1].patriotic_bill.total_cents==2400)
    local next=state(1003);next.billing_enabled=false;next.total_cents=0;next.entries={};restored:observe(next)
    assert(restored:entries()[1].patriotic_bill==nil,'disabled new mission stays unrecorded rather than fake zero')
    local disabled_saved=restored:snapshot()
    local restarted=create({icons=icons,saved=disabled_saved,legacy=next})
    assert(restarted:entries()[1].patriotic_bill==nil,'disabled last mission cannot become a false zero bill during restart migration')
end)
check('only the matching legacy last mission bill is imported with real amounts',function()
    local history=create({icons=icons});history:observe(state(1101));history:observe(state(1102))
    local saved=history:snapshot()
    local legacy=state(1102);legacy.total_cents=123;legacy.entries={{name='旧账目',amount_cents=123,event='ammunition_fired'}}
    local restored=create({icons=icons,saved=saved,legacy=legacy})
    assert(restored:entries()[1].patriotic_bill.total_cents==123 and restored:entries()[2].patriotic_bill==nil)
    assert(saved.entries[1].patriotic_bill==nil,'migration does not mutate the saved input')
    local again=create({icons=icons,saved=restored:snapshot(),legacy=legacy})
    assert(again:entries()[1].patriotic_bill.total_cents==123,'legacy import is idempotent')
end)
check('bill snapshot refuses inconsistent amounts and preserves unattributed actual fees',function()
    local history=create({icons=icons});local s=state(1201);s.billing_enabled=true;s.total_cents=200
    s.entries={{name='消费',amount_cents=300}};history:observe(s)
    assert(history:entries()[1].patriotic_bill==nil)
    s.entries={{name='消费',amount_cents=100}};assert(history:observe(s))
    assert(#history:entries()[1].patriotic_bill.entries==2)
    assert(history:entries()[1].patriotic_bill.entries[2].amount_cents==100)
end)

check('numeric medal counts preserve repeated acquisitions and old entries',function()
    local history=create({icons=icons})
    local s=state(1001);s.mission_medals.democracy_harvester=true;history:observe(s)
    s.mission_medals.democracy_harvester=3;assert(history:observe(s))
    assert(history:entries()[1].medals.democracy_harvester==3)
    s.mission_medals.democracy_harvester=true;assert(not history:observe(s))
    s.mission=false;s.status='ended';history:observe(s)
    local snapshot=history:snapshot()
    local reloaded=create({icons=icons,saved=snapshot})
    assert(reloaded:entries()[1].medals.democracy_harvester==3)
    assert(not reloaded:observe(s),'old bool cannot erase or duplicate repeated acquisitions')
end)
check('new crush definition stores exact current counts without rewriting old history',function()
    local crush_icons={{id='R12',kind='ribbon',key='crush'}}
    local history=create({icons=crush_icons})
    local old=state(31);old.mission=false;old.status='ended';history:observe(old)
    local current=state(32);current.crush_policy='confirmed_player_vehicle_parent_source_kills_as_crush'
    current.ribbons.crush=3;history:observe(current)
    current.ribbons.crush=4;assert(history:observe(current))
    local entries=history:entries()
    assert(entries[1].ribbons.crush==4 and entries[2].ribbons.crush==nil)
    assert(entries[1].crush_policy==current.crush_policy and entries[2].crush_policy==nil)
    local saved=history:snapshot();local restored=create({icons=crush_icons,saved=saved})
    assert(restored:entries()[1].ribbons.crush==4 and restored:entries()[2].ribbons.crush==nil)
    assert(restored:entries()[1].crush_policy==current.crush_policy and restored:entries()[2].crush_policy==nil)
    local zero=state(33);zero.crush_policy=current.crush_policy;history:observe(zero)
    zero.mission=false;zero.status='ended';history:observe(zero)
    assert(history:entries()[1].ribbons.crush==nil and history:entries()[1].crush_policy==current.crush_policy,
        'zero remains a valid recorded new policy even though zero ribbons are not serialized')
end)
