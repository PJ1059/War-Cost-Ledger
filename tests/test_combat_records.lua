local create=dofile(assert(arg[1]))
local now=2000000
local A,B,C='FEDCBA9876543210','0123456789ABCDEF','A123456789ABCDEF'
local weapons={
    [A]={id='rifle',name='测试步枪',category='primary',weapon_type='突击步枪'},
    [B]={id='rifle',name='测试步枪',category='primary',weapon_type='突击步枪'},
    [C]={id='orbital',name='测试轨道攻击',category='stratagem',weapon_type='轨道攻击'}}
local enemies={['0000000000000001']={key='Charger',name_zh='强袭虫',faction='terminids',class='重型'},
    ['0000000000000002']={key='Voteless',name_zh='无票者',faction='illuminate',class='轻型'}}
local function factory(saved,legacy,history)
    return create({clock=function()return now end,saved=saved,legacy=legacy,history=history,
        weapon_catalog=weapons,enemy_catalog=enemies})
end
local function real_death_rows(result)
    local rows={}
    for _,row in ipairs(result.rows)do
        if row.unknown_group then for _,record in ipairs(row.records)do rows[#rows+1]=record end
        else rows[#rows+1]=row end
    end
    return rows
end
local api=factory()
local state={sequence=1,mission=true,status='active',kills=0,deaths=0,weapon_stats={},unit_kills={}}
assert(api:observe(state));local revision=api.revision
assert(not api:observe(state)and api.revision==revision,'unchanged 10 Hz frames must not write')
state.kills=8;state.deaths=1
state.weapon_stats={[A]={name='raw rifle',kills=3},[B]={kills=2},[C]={kills=2}}
state.unit_kills={Charger={name_zh='强袭虫',class='重型',faction='terminids',count=3}}
assert(api:observe(state));revision=api.revision
local first=api:query('weapons',{period='all'})
assert(first.totals.kills==8 and first.totals.known_kinds==2 and first.totals.linked_kills==0)
assert(first.rows[1].id=='rifle'and first.rows[1].kills==5,'source aliases merge by proven weapon identity')
assert(first.rows[1].unknown_kills==5 and first.rows[1].detail_rows[1].known==false)
assert(first.rows[1].detail_rows[1].kills==5,'no guessed enemy/weapon association')
assert(first.rows[2].id=='orbital'and first.rows[3].id=='unknown')
assert(api:query('weapons',{period='all'})==first,'retained query is reused')
now=now+.4;assert(api:query('weapons',{period='all'})==first,'same second keeps cache')
now=now+1;assert(api:query('weapons',{period='all'})==first,'all-time query stays cached across seconds until records change')
assert(api:query('weapons',{role='primary',query='步枪'}).totals.kills==5)
local types=api:query('weapons',{role='primary',query='does not match',weapon_type='not selected'}).available_weapon_types
assert(#types==1 and types[1]=='突击步枪','subtype choices survive text and subtype filters')
local units=api:query('enemies',{faction='bugs',size='重型'})
assert(#units.rows==1 and units.rows[1].name=='强袭虫'and units.rows[1].kills==3)
assert(units.rows[1].detail_rows[1].known==false and units.totals.linked_kills==0)
assert(api:query('enemies',{}).totals.kills==8,'unclassified local kills remain in the enemy total')
local snapshot=api:snapshot();snapshot.entries[1].kills=99999
assert(api:query('weapons',{}).totals.kills==8,'snapshot cannot mutate live records')
assert(not api:observe(state)and api.revision==revision)
state.kills=2;state.weapon_stats[A].kills=1;state.unit_kills.Charger.count=1
api:observe(state)
assert(api:query('weapons',{}).totals.kills==8 and api:query('enemies',{faction='bugs'}).rows[1].kills==3,
    'lower/reset counters never replay or subtract high-water values')
state.kills=9;state.weapon_stats[A].kills=4
api:observe(state)
assert(api:query('weapons',{}).totals.kills==9 and api:query('weapons',{}).rows[1].kills==6)
state.mission=false;state.status='ended'
assert(api:observe(state),'mid-mission return to ship still finalizes this match')
local saved=api:snapshot();assert(saved.entries[1].ended_at==now)
api=factory(saved);revision=api.revision
assert(not api:observe(state)and api.revision==revision,'restart/final snapshot does not duplicate totals')
assert(api:query('weapons',{}).totals.kills==9)
now=now+90000
local state2={sequence=2,mission=true,status='active',kills=4,deaths=1,
    weapon_stats={[C]={kills=4}},unit_kills={Voteless={count=2}}}
assert(api:observe(state2))
local recent=api:query('weapons',{period='24h'})
assert(recent.totals.kills==4 and recent.rows[1].name=='测试轨道攻击')
assert(api:query('weapons',{period='7d'}).totals.kills==13)
local mission1=api:query('weapons',{sequence=1})
local mission2=api:query('weapons',{sequence=2})
assert(mission1.totals.kills==9 and mission2.totals.kills==4,
    'per-match source totals must not mix with another match or the all-time query cache')
assert(mission1.rows[1].id=='rifle'and mission1.rows[1].kills==6)
assert(mission2.rows[1].id=='orbital'and mission2.rows[1].kills==4)
assert(api:query('enemies',{sequence=2}).rows[1].name=='无票者')
assert(api:query('weapons',{sequence=999}).totals.kills==0,'missing match cannot fall back to all matches')
assert(api:query('enemies',{faction='illuminate'}).rows[1].name=='无票者')
local original={id='hit:0000000000000001',sequence=2,occurred_at=now,mission_elapsed=121,
    category='player',actor_name='同名玩家',weapon_name='榴弹发射器',damage_kind='爆炸',confidence='inferred',
    evidence='target_damage',player={name='同名玩家',callsign='A2',slot=2,
        peer_id='fedcba9876543210',persona_index=0,platform_account_id='not-proven'}}
assert(api:record_death(original));assert(not api:record_death(original),'duplicate death ID rejected')
local death=api:query('deaths',{mode='recent'}).rows[1]
assert(type(death.id)=='string'and death.at==now and death.match==2 and death.actor=='同名玩家')
assert(death.player.peer_id=='FEDCBA9876543210'and type(death.player.peer_id)=='string')
assert(death.player.persona_index==0 and death.player.platform_account_id==nil,
    'session peer stays an exact string; permanent account fields are not synthesized')
assert(original.player.peer_id=='fedcba9876543210','caller snapshot is unchanged')
assert(api:record_death({id='same-name-other-peer',sequence=2,occurred_at=now+1,category='player',
    actor_name='同名玩家',confidence='low',player={peer_id='0000000000000002'}}))
assert(api:record_death({id='unresolved',sequence=2,category='unknown'}))
local ranks=api:query('deaths',{})
assert(#ranks.rows==2 and ranks.rows[1].name=='队友'and ranks.rows[1].count==2,
    'different participant peers remain one friendly-fire cause in ranking')
assert(ranks.rows[1].records[1].player.peer_id~=ranks.rows[1].records[2].player.peer_id,
    'rank grouping preserves the individual participant snapshots')
assert(api:query('deaths',{category='player',query='FEDCBA9876543210'}).totals.recorded_deaths==1)
assert(api:query('deaths',{category='player',query='A2'}).totals.recorded_deaths==1)
assert(api:query('deaths',{query='对局 #2'}).totals.recorded_deaths==3)
assert(api:query('deaths',{query='事件 #same-name-other-peer'}).totals.recorded_deaths==1)
local evidence={death_observed='dead_state',runtime_death_event=true,native_death_counter=true,
    death_index=4,native_fatal_event_proven=false,weapon_source_proven=false,damage_kind_proven=false,
    source_channel='native_health_last_owner_type',actor_type_hash='abcdef9876543210',
    unsafe_pointer=999999,not_plain=function()error('must not be stored')end}
assert(api:record_death({id='structured',sequence=2,occurred_at=now,category='enemy',
    actor_name='强袭虫',confidence='low',evidence=evidence,
    victim={name='本人',peer_id='0000000000000001',avatar_id=314,slot=1,slot_index=0,persona_index=0}}))
local structured=api:query('deaths',{mode='recent',query='事件 #structured'}).rows[1]
assert(structured.evidence.native_fatal_event_proven==false and structured.evidence.weapon_source_proven==false)
assert(structured.evidence.actor_type_hash=='ABCDEF9876543210'and structured.evidence.unsafe_pointer==nil
    and structured.evidence.not_plain==nil,'only declared plain evidence fields are persisted')
assert(structured.observed=='dead_state'and structured.death_index==4
    and structured.evidence_text=='native_health_last_owner_type')
assert(structured.victim.avatar_id==314 and structured.victim.peer_id=='0000000000000001'
    and structured.victim.slot_index==0 and structured.victim.slot==1)
assert(api:query('deaths',{query='native_health_last_owner_type'}).totals.recorded_deaths==1)
assert(api:query('deaths',{mode='recent',period='24h'}).totals.recorded_deaths==2,
    'unknown-time and future deaths do not enter a recent interval')
local stored=api:snapshot();local restarted=factory(stored)
assert(not restarted:record_death(original))
assert(#restarted:query('deaths',{mode='recent'}).rows==4)
assert(restarted:query('deaths',{mode='recent',query='事件 #structured'}).rows[1].evidence.death_index==4,
    'structured death proof survives restart and query')
assert(restarted:snapshot().entries[2].status=='interrupted','a process gap is not an invented ended mission')
-- Old history preserves known totals and any actually stored source rows. Its
-- absent date, source table, and death details are never backfilled from now.
local legacy={sequence=10,status='ended',kills=10,deaths=2}
local history={entries={{sequence=11,status='ended',kills=6,deaths=1,ended_at=now-100,
    weapon_stats={[A]={kills=4}},unit_kills={Charger={count=1}}},
    {sequence=10,status='ended',kills=10,deaths=2}}}
local migrated=factory(nil,legacy,history)
assert(not legacy.ended_at and not legacy.weapon_stats and #history.entries==2)
local all=migrated:query('weapons',{})
assert(all.totals.kills==16 and all.coverage.unknown_time_kills==10)
assert(all.rows[1].id=='rifle'and all.rows[1].kills==4)
assert(#all.rows==2 and all.rows[2].id=='unknown'and all.rows[2].name=='未知'and all.rows[2].kills==12,
    'raw, missing and legacy unknown sources combine in one final display row')
assert(migrated:query('weapons',{period='24h'}).totals.kills==6)
assert(migrated:query('deaths',{}).coverage.unrecorded_deaths==3)
local missing_causes=migrated:query('deaths',{}).rows
assert(#missing_causes==1 and missing_causes[1].unknown_group and missing_causes[1].count==3
    and missing_causes[1].unrecorded_count==3 and #missing_causes[1].records==0,
    'missing historic causes are one numeric summary, never fabricated death events')
local repeated=factory(migrated:snapshot(),legacy,history)
assert(repeated:query('weapons',{}).totals.kills==16,'migration on restart is idempotent')
local overlap=factory(nil,{sequence=50,status='ended',kills=7,deaths=0,weapon_stats={[A]={kills=7}}},
    {{sequence=50,status='ended',kills=7,deaths=0,ended_at=now-30}})
assert(overlap:query('weapons',{period='24h'}).rows[1].id=='rifle'
    and overlap:query('weapons',{}).totals.kills==7,
    'latest saved source fields and history timestamps merge without losing either or double counting')
-- No hidden historical cap or deletion: every retained match survives.
local bulk=create({})
for i=1,501 do assert(bulk:observe({sequence=i,status='ended',kills=1,deaths=0}))end
assert(#bulk:snapshot().entries==501 and bulk:query('weapons',{}).totals.kills==501)
local no_clock=create({})
assert(no_clock:observe({sequence=1,mission=true,kills=0,deaths=0,weapon_stats={},unit_kills={}}))
assert(not no_clock:observe({sequence=1,mission=true,kills=0,deaths=0,weapon_stats={},unit_kills={}}),
    'unavailable clock cannot dirty unchanged frames')
-- Raw enemy and weapon hashes survive unknown catalog entries, then resolve by
-- exact identity on reload. Aggregate gaps cannot be assigned an invented name.
local raw_hash='ABCDEFABCDEFABCD'
local raw=create({clock=function()return now end})
assert(raw:observe({sequence=77,status='ended',kills=8,deaths=1,weapon_stats={[A]={kills=5}},
    unit_kills={},unknown_unit_kills={[raw_hash]={name='旧未知敌人',count=6}}}))
assert(raw:record_death({id='death-1',sequence=77,category='unknown',actor_name='未知来源',confidence='unknown',
    evidence={actor_type_hash=raw_hash,weapon_source_proven=false,native_fatal_event_proven=false}}))
local remapped=create({saved=raw:snapshot(),weapon_catalog=weapons,
    enemy_catalog={[raw_hash]={key='MappedEnemy',name_zh='精确对齐敌人',kill=true,faction='bugs',class='巨型'}}})
local mapped=remapped:query('enemies',{sequence=77})
assert(mapped.rows[1].name=='精确对齐敌人'and mapped.rows[1].kills==6 and mapped.totals.kills==8)
assert(mapped.rows[2].known==false and mapped.rows[2].kills==2,'unnamed aggregate gap stays unknown')
assert(remapped:query('weapons',{sequence=77}).rows[1].name=='测试步枪')
local death=remapped:query('deaths',{sequence=77,mode='recent'}).rows[1]
assert(death.actor_name=='精确对齐敌人'and death.category=='enemy'and death.confidence=='unknown')
assert(not death.weapon_name and death.evidence.weapon_source_proven==false and death.evidence.native_fatal_event_proven==false,
    'name lookup cannot manufacture fatal or weapon evidence')
local duplicate=create({enemy_catalog={[raw_hash]={key='MappedEnemy',name_zh='精确对齐敌人',kill=true}}})
duplicate:observe({sequence=78,status='ended',kills=6,deaths=0,unit_kills={MappedEnemy={count=6}},
    unknown_unit_kills={[raw_hash]={count=6}}})
assert(duplicate:query('enemies',{}).totals.kills==6,'classified and raw snapshot lanes cannot double count')
-- Resource-only hash labels may improve an unknown/scenery source display;
-- they do not supply a player identity, enemy class or fatal-weapon proof.
local resource_hash='DEADBEEF12345678'
local resource_raw=create({})
local function resource_death(id,category,actor,player,hash)
    assert(resource_raw:record_death({id=id,sequence=79,category=category,actor_name=actor,player=player,confidence='unknown',
        evidence={actor_type_hash=hash or resource_hash,weapon_source_proven=false,native_fatal_event_proven=false}}))
end
resource_death('resource-unknown','unknown','未知来源')
resource_death('resource-environment','environment','未知来源')
resource_death('resource-player','player','队友',{name='队友姓名'})
resource_death('resource-enemy','enemy','强袭虫')
resource_death('resource-known','unknown','已有明确名称')
resource_death('resource-player-clue','unknown','未知来源',{name='已知玩家'})
resource_death('resource-invalid','unknown','未知来源',nil,'DEADBEEF')
local resource_named=create({saved=resource_raw:snapshot(),weapon_catalog={[resource_hash]={name='载具碰撞资源'}}})
local resources={}
for _,record in ipairs(real_death_rows(resource_named:query('deaths',{sequence=79,mode='recent'})))do resources[record.source_id]=record end
for _,id in ipairs({'resource-unknown','resource-environment'})do
    local record=resources[id]
    assert(record.actor_name=='载具碰撞资源'and record.confidence=='unknown'and not record.weapon_name)
    assert(record.evidence.weapon_source_proven==false and record.evidence.native_fatal_event_proven==false)
end
assert(resources['resource-unknown'].category=='unknown'and resources['resource-environment'].category=='environment')
assert(resources['resource-player'].actor_name=='队友'and resources['resource-enemy'].actor_name=='强袭虫')
assert(resources['resource-known'].actor_name=='已有明确名称'and resources['resource-player-clue'].actor_name=='未知来源')
assert(resources['resource-invalid'].actor_name=='未知来源','truncated hashes cannot identify a resource')
-- Exercise the actual observer -> persistent-record path. A retained type hash
-- cannot undo the observer's explicit rejection of conflicting source clues.
-- The owner is a known player avatar with a different creditor. An exact
-- enemy owner plus a residual creditor is no longer an explicit conflict.
local make_observer=dofile(arg[1]:gsub('combat%-records%.lua$','death-observer.lua'))
local local_peer,other_peer='1111111111111111','2222222222222222'
local conflict_hash='3333333333333333'
local conflict_catalog={[conflict_hash]={key='ConflictingEnemy',name_zh='不能归因的敌人',kill=true}}
local raw_source={avatar_id=17,victim_type='4444444444444444',life=2,
    last_owner=18,last_owner_type=conflict_hash,last_creditor=local_peer}
local observer=make_observer({catalog=conflict_catalog,reader={read=function()return raw_source end}})
local ctx={sequence=80,world={},now=1,occurred_at=now,local_peer=local_peer,avatar=17,
    players={{peer=local_peer,avatar=17,['local']=true},{peer=other_peer,avatar=18}}}
assert(observer:on_died({local_player=true,avatar_id=17,peer=local_peer,observed='dead_state',frame=10},ctx))
observer:step(1.6,ctx.world,{mission=true},ctx.players,ctx)
local rejected=assert(observer:take_records()[1])
assert(rejected.evidence.source_reason=='CONFLICTING_SOURCE_EVIDENCE'and rejected.category=='unknown')
assert(rejected.evidence.actor_type_hash==conflict_hash and not rejected.actor_name)
local conflict_store=create({enemy_catalog=conflict_catalog,weapon_catalog={[conflict_hash]={name='也不能补这个资源名'}}})
assert(conflict_store:record_death(rejected))
local conflict_row=assert(real_death_rows(conflict_store:query('deaths',{sequence=80,mode='recent'}))[1])
assert(conflict_row.category=='unknown'and conflict_row.actor_name=='未知来源'and conflict_row.confidence=='unknown',
    'persisting an observer-rejected source must not reclassify or name it from the retained hash')
assert(not conflict_row.weapon_name and conflict_row.evidence.source_reason=='CONFLICTING_SOURCE_EVIDENCE')
local reloaded=create({saved=conflict_store:snapshot(),enemy_catalog=conflict_catalog,
    weapon_catalog={[conflict_hash]={name='也不能补这个资源名'}}})
conflict_row=real_death_rows(reloaded:query('deaths',{sequence=80,mode='recent'}))[1]
assert(conflict_row.category=='unknown'and conflict_row.actor_name=='未知来源'and conflict_row.confidence=='unknown',
    'catalog alignment after reload must preserve the explicit source conflict')
for _,reason in ipairs({'COUNTER_GAP_ATTRIBUTION_SKIPPED','COUNTER_VICTIM_AVATAR_NOT_DEAD',
    'DEATH_SOURCE_IDENTITY_CHANGED','DEATH_SOURCE_CHANGED_AFTER_DEATH'})do
    local blocked=create({enemy_catalog=conflict_catalog})
    assert(blocked:record_death({id=reason,sequence=81,category='unknown',confidence='unknown',
        evidence={actor_type_hash=conflict_hash,source_reason=reason,weapon_source_proven=false}}))
    local row=real_death_rows(blocked:query('deaths',{sequence=81,mode='recent'}))[1]
    assert(row.category=='unknown'and row.actor_name=='未知来源'and row.confidence=='unknown',reason)
end
local player_clue=create({enemy_catalog=conflict_catalog})
assert(player_clue:record_death({id='player-and-enemy-hash',sequence=82,category='unknown',confidence='unknown',
    player={name='冻结的玩家身份',peer_id=other_peer},evidence={actor_type_hash=conflict_hash,weapon_source_proven=false}}))
local player_row=real_death_rows(player_clue:query('deaths',{sequence=82,mode='recent'}))[1]
assert(player_row.category=='unknown'and player_row.actor_name=='未知来源'and player_row.player.peer_id==other_peer,
    'a raw enemy hash cannot override an existing frozen player identity')
player_clue=create({saved=player_clue:snapshot(),enemy_catalog=conflict_catalog})
player_row=real_death_rows(player_clue:query('deaths',{sequence=82,mode='recent'}))[1]
assert(player_row.category=='unknown'and player_row.actor_name=='未知来源'and player_row.player.peer_id==other_peer)
-- Legacy crush display reads only exact saved body hashes and only histories
-- without an actual R12. It never mutates source records or fabricates gaps.
local body_hash='16474112801385B6'
local gun_hash='1FA1F596769225C2'
local body_records=create({vehicle_body_sources={[body_hash]={kind='vehicle_body'}}})
body_records:observe({sequence=31,status='ended',kills=676,deaths=1,
    weapon_stats={[body_hash]={kills=154},[gun_hash]={kills=20}}})
body_records:observe({sequence=32,status='ended',kills=12,deaths=0,weapon_stats={[body_hash]={kills=12}}})
body_records:observe({sequence=33,status='ended',kills=8,deaths=0,weapon_stats={[body_hash]={kills=8}}})
body_records:observe({sequence=34,mission=true,status='active',kills=5,deaths=0,weapon_stats={[body_hash]={kills=5}}})
body_records:observe({sequence=36,status='ended',kills=22,deaths=0,weapon_stats={[body_hash]={kills=22}}})
local old_history={entries={{sequence=31,status='ended',ribbons={}},
    {sequence=32,status='ended',ribbons={crush=12}},{sequence=33,status='ended',ribbons={crush=0}},
    {sequence=34,status='active',ribbons={}},{sequence=35,status='ended',ribbons={}},
    {sequence=36,status='ended',ribbons={},crush_policy='confirmed_player_vehicle_parent_source_kills_as_crush'}}}
local body_revision=body_records.revision
local legacy_body=body_records:legacy_crush_summary(old_history)
assert(legacy_body.total==154 and legacy_body.by_sequence[31]==154)
assert(not legacy_body.by_sequence[32]and not legacy_body.by_sequence[33]and not legacy_body.by_sequence[34])
assert(not legacy_body.by_sequence[35]and body_records:vehicle_body_kills(999)==nil)
assert(not legacy_body.by_sequence[36],'a new zero-award mission with a late native baseline is never backfilled')
assert(body_records:vehicle_body_kills(31)==154,'mounted gun and aggregate 522 missing kills are excluded')
assert(body_records.revision==body_revision and old_history.entries[1].ribbons.crush==nil)
assert(body_records:legacy_crush_summary(old_history).total==154,'opening the history twice cannot replay a ledger award')
old_history.revision=1
local cached_crush=body_records:legacy_crush_summary(old_history)
assert(body_records:legacy_crush_summary(old_history)==cached_crush,'versioned history reuses legacy source sums')
old_history.entries[1].ribbons.crush=154;old_history.revision=2
assert(body_records:legacy_crush_summary(old_history).total==0,'history revision invalidates the legacy sum')
old_history.entries[1].ribbons.crush=nil;old_history.revision=nil
assert(body_records:legacy_crush_summary(old_history).total==154)
old_history.entries[1].ribbons.crush=154
assert(body_records:legacy_crush_summary(old_history).total==0,'unversioned in-place edits are not cached')
old_history.entries[1].ribbons.crush=nil
do
    local at=100000;local t=at
    local cached=create({clock=function()return t end})
    cached:observe({sequence=801,status='ended',ended_at=at-86400,kills=2,deaths=1,
        weapon_stats={[A]={name='已知武器',kills=2}}})
    cached:observe({sequence=802,status='ended',ended_at=at+.5,kills=3,deaths=1,
        weapon_stats={[A]={name='已知武器',kills=3}}})
    local boundary=cached:query('weapons',{period='24h'})
    assert(boundary.totals.kills==2,'exact left boundary remains included')
    assert(cached:query('weapons',{period='24h'})==boundary)
    t=at+.0001
    assert(cached:query('weapons',{period='24h'}).totals.kills==0,'left boundary expires immediately after its exact timestamp')
    t=at+.5
    local future=cached:query('weapons',{period='24h'})
    assert(future.totals.kills==3,'future saved match enters on its exact timestamp')
    t=at+.75
    assert(cached:query('weapons',{period='24h'})==future,'subsecond time alone does not rebuild an unchanged period')
    t=at
    assert(cached:query('weapons',{period='24h'}).totals.kills==2,'clock rollback recomputes the exact window')
    cached:record_death({id='first',sequence=801,occurred_at=at-86400+.2,actor_name='强袭虫',category='enemy'})
    cached:record_death({id='future',sequence=802,occurred_at=at+.7,actor_name='强袭虫',category='enemy'})
    assert(cached:query('deaths',{period='24h'}).totals.recorded_deaths==1)
    t=at+.2001;assert(cached:query('deaths',{period='24h'}).totals.recorded_deaths==0)
    t=at+.7;assert(cached:query('deaths',{period='24h'}).totals.recorded_deaths==1,'death timestamps have independent exact expiry')
    local recent=cached:query('deaths',{mode='recent'})
    t=t+1;assert(cached:query('deaths',{mode='recent'})==recent,'all-time deaths survive UI second changes')
    local match=cached:query('weapons',{sequence=801})
    t=t+1;assert(cached:query('weapons',{sequence=801})==match,'fixed-match queries survive UI second changes')
    local first_search=cached:query('weapons',{query='oldest query'})
    for i=1,32 do cached:query('weapons',{query='other query '..i})end
    assert(cached:query('weapons',{query='oldest query'})~=first_search,'search results use a bounded 32-entry cache')
    cached:record_death({id='new',sequence=802,occurred_at=t,actor_name='强袭虫',category='enemy'})
    assert(cached:query('deaths',{mode='recent'})~=recent,'new records invalidate the retained result')
    local reloaded=create({saved=cached:snapshot(),clock=function()return t end})
    assert(reloaded:query('deaths',{}).totals.recorded_deaths==3,'reload retains all original deaths')
end
-- Display-only unknown consolidation must neither erase raw identities nor
-- confuse a known name with a missing slot/faction/size classification.
local U1,U2,U3='ABCDEF0000000001','ABCDEF0000000002','ABCDEF0000000003'
local named_source='ABCDEF0000000004'
local consolidation=create({clock=function()return now end,weapon_catalog=weapons,enemy_catalog=enemies,
    history={{sequence=101,status='ended',kills=50,deaths=0,ended_at=now-20}}})
consolidation:observe({sequence=100,status='ended',kills=1000,deaths=0,ended_at=now-10,
    weapon_stats={[A]={kills=3},[U1]={name=U1,kills=300},[U2]={name='未知武器来源',kills=200},
        [named_source]={name='命名但未分类的来源',category='unknown',known=false,kills=2}},
    unit_kills={Charger={count=3},NamedNoClass={name_zh='命名但未分类的敌人',count=2}},
    unknown_unit_kills={[U1]={name=U1,count=300},[U2]={name='未知敌人',count=200}}})
local before_query=consolidation:snapshot()
local function equal(a,b)
    if type(a)~=type(b)then return false end
    if type(a)~='table'then return a==b end
    for k,v in pairs(a)do if not equal(v,b[k])then return false end end
    for k in pairs(b)do if a[k]==nil then return false end end
    return true
end
for _,view in ipairs({'weapons','enemies'})do
    for _,sort in ipairs({'count','name'})do
        local result=consolidation:query(view,{sort=sort})
        assert(#result.rows==3 and result.totals.kills==1050 and result.totals.known_kinds==2)
        local unknown=result.rows[3]
        assert(unknown.id=='unknown'and unknown.name=='未知'and unknown.known==false and unknown.kills==1045,
            'all raw hashes, legacy omissions and current aggregate gaps are one final unknown row')
        assert(result.rows[1].known and result.rows[2].known,'name/count sort never places a large unknown before named items')
        local named=false
        for _,row in ipairs(result.rows)do
            if row.name=='命名但未分类的来源'or row.name=='命名但未分类的敌人'then
                named=true;assert(row.known and row.kills==2)
                assert(view~='weapons'or row.category=='unknown')
                assert(view~='enemies'or row.size=='未知体型'and row.faction=='unknown')
            end
        end
        assert(named,'a readable retained identity survives without a catalog or a class')
        local focused=consolidation:query(view,{focus_id='unknown'})
        assert(#focused.rows==1 and focused.rows[1].kills==1045)
    end
end
assert(consolidation:query('weapons',{role='primary'}).totals.kills==3)
assert(consolidation:query('enemies',{faction='bugs',size='重型'}).totals.kills==3,
    'known-category filters cannot pull unclassified legacy gaps into their totals')
assert(consolidation:query('weapons',{sequence=100}).rows[3].kills==995)
assert(consolidation:query('weapons',{query=U1}).totals.kills==300,'exact raw-identity search remains available without displaying another unknown item')
assert(equal(before_query,consolidation:snapshot()),'display normalization cannot overwrite raw names, hashes, counts or flags')
local recovered=create({saved=consolidation:snapshot(),clock=function()return now end,
    weapon_catalog={[U1]={name='后来对齐的载具来源'}},
    enemy_catalog={[U1]={key='MappedLater',name_zh='后来对齐的敌人',kill=true}}})
for _,view in ipairs({'weapons','enemies'})do
    local result=recovered:query(view,{})
    assert(#result.rows==4 and result.rows[1].kills==300 and result.rows[1].known)
    assert(result.rows[4].id=='unknown'and result.rows[4].kills==745,
        'a later exact-name catalog restores raw rows while only the remaining unknowns stay merged')
end
-- Unknown death records retain every actual event, while missing historical
-- causes contribute only one summary count. Neither creates synthetic events.
local death_groups=create({clock=function()return now end})
death_groups:observe({sequence=120,status='ended',kills=0,deaths=10,ended_at=now})
local events={
    {id='enemy-known',category='enemy',actor_name='强袭虫',at=now-20},
    {id='friendly-known',category='player',actor_name='本人保留的队友名',at=now-10,
        player={name='队友完整名字',peer_id='1234567890ABCDEF',slot=2}},
    {id='fire-known',category='environment',actor_name='火焰',at=now-30},
    {id='named-but-unattributed',category='unknown',actor_name='已对齐但归属未确认的资源',at=now-1,
        player={peer_id='ABCDEF1234567890'},weapon_name='未确认来源的武器线索'},
    {id='raw-actor',category='enemy',actor_name=U3,at=now-2},
    {id='unresolved-environment',category='environment',actor_name='未知来源',at=now-3},
}
for _,event in ipairs(events)do event.sequence=120;assert(death_groups:record_death(event))end
local death_before=death_groups:snapshot()
for _,mode in ipairs({'rank','recent'})do
    for _,sort in ipairs({'count','name'})do
        local result=death_groups:query('deaths',{mode=mode,sort=sort})
        assert(#result.rows==5 and result.totals.recorded_deaths==6 and result.totals.unrecorded_deaths==4
            and result.totals.filtered_deaths==10)
        local unknown=result.rows[5]
        assert(unknown.id=='unknown'and unknown.name=='未知死因'and unknown.category=='unknown'
            and unknown.known==false and unknown.unknown_group and unknown.count==6)
        assert(unknown.unrecorded_count==4 and #unknown.records==2,
            'native missing causes add numbers, never placeholder death records')
        assert(unknown.records[1].source_id=='raw-actor'and unknown.records[1].at==now-2
            and unknown.records[1].actor_name==U3 and unknown.records[1].category=='enemy',
            'the grouped row preserves original chronology, raw identity and original source category in details')
        if mode=='recent'then
            assert(result.rows[1].source_id=='named-but-unattributed'and result.rows[2].source_id=='friendly-known'
                and result.rows[3].source_id=='enemy-known'and result.rows[4].source_id=='fire-known',
                'known recent events retain their timestamps, independent of rank sort')
            assert(result.rows[1].category=='unknown'and result.rows[1].known
                and result.rows[1].actor_name=='已对齐但归属未确认的资源'
                and result.rows[1].player.peer_id=='ABCDEF1234567890',
                'a usable actor name remains visible without inventing its unknown attribution category')
            assert(result.rows[2].player.name=='队友完整名字'and result.rows[2].player.peer_id=='1234567890ABCDEF')
        else
            local named
            for _,row in ipairs(result.rows)do if row.name=='已对齐但归属未确认的资源'then named=row end end
            assert(named and named.known and named.category=='unknown'and named.count==1
                and named.records[1].player.peer_id=='ABCDEF1234567890')
        end
    end
end
local friendly=death_groups:query('deaths',{category='player',mode='recent'})
assert(#friendly.rows==1 and friendly.rows[1].source_id=='friendly-known'and friendly.totals.unrecorded_deaths==0)
local unknown_deaths=death_groups:query('deaths',{category='unknown'})
assert(#unknown_deaths.rows==2 and unknown_deaths.rows[1].known and unknown_deaths.rows[1].category=='unknown'
    and unknown_deaths.rows[2].count==6 and #unknown_deaths.rows[2].records==2)
local searched=death_groups:query('deaths',{mode='recent',query='事件 #named-but-unattributed'})
assert(#searched.rows==1 and not searched.rows[1].unknown_group and searched.rows[1].known
    and searched.rows[1].source_id=='named-but-unattributed'and searched.rows[1].category=='unknown'
    and searched.totals.unrecorded_deaths==0 and searched.totals.recorded_deaths==1)
local missing_only=create({history={{sequence=121,status='ended',kills=0,deaths=40000}}})
for _,mode in ipairs({'rank','recent'})do
    local result=missing_only:query('deaths',{mode=mode})
    assert(#result.rows==1 and result.rows[1].count==40000 and result.rows[1].unrecorded_count==40000
        and #result.rows[1].records==0 and result.totals.recorded_deaths==0)
end
assert(equal(death_before,death_groups:snapshot())and #death_groups:snapshot().death_records==6,
    'ranking and recent grouping cannot rewrite raw event identity or create old missing records')
local unresolved_path='entity/v1/unresolved/'..U1
local internal_ids=create({weapon_catalog={[U1]={name=unresolved_path}},
    enemy_catalog={[U1]={name=unresolved_path,key='unresolved-unit',kill=true}}})
internal_ids:observe({sequence=122,status='ended',kills=4,deaths=1,
    weapon_stats={[U1]={kills=4}},unknown_unit_kills={[U1]={name=unresolved_path,count=4}}})
internal_ids:record_death({sequence=122,id='internal-path',category='enemy',actor_name=unresolved_path})
for _,view in ipairs({'weapons','enemies','deaths'})do
    local result=internal_ids:query(view,{})
    assert(#result.rows==1 and result.rows[1].id=='unknown'and result.rows[1].known==false,
        'an unresolved native entity path is an internal ID, never a known display name')
end
assert(internal_ids:snapshot().entries[1].weapons[U1].name==unresolved_path,
    'internal identities remain saved for future exact catalog resolution')
-- Real deaths without a native counter in one match cannot pay down missing
-- historical details from another match. Period selection keeps its old gates.
local mixed_deaths=create({clock=function()return now end,history={
    {sequence=130,status='ended',kills=0,deaths=5,ended_at=now-90000},
    {sequence=131,status='ended',kills=0,deaths=0,ended_at=now-100}}})
for i=1,3 do assert(mixed_deaths:record_death({id='extra-'..i,sequence=131,occurred_at=now-i,
    category='enemy',actor_name='强袭虫'}))end
local mixed_before=mixed_deaths:snapshot()
for _,mode in ipairs({'rank','recent'})do
    local result=mixed_deaths:query('deaths',{mode=mode})
    assert(result.totals.deaths==8 and result.totals.recorded_deaths==3
        and result.coverage.unrecorded_deaths==5 and result.totals.unrecorded_deaths==5)
    local last=result.rows[#result.rows]
    assert(last.id=='unknown'and last.count==5 and last.unrecorded_count==5 and #last.records==0)
    local today=mixed_deaths:query('deaths',{mode=mode,period='24h'})
    assert(today.totals.deaths==3 and today.totals.recorded_deaths==3
        and today.coverage.unrecorded_deaths==0 and today.totals.unrecorded_deaths==0,
        'old unmatched native counts stay out of a recent time interval')
    local week=mixed_deaths:query('deaths',{mode=mode,period='7d'})
    assert(week.totals.deaths==8 and week.coverage.unrecorded_deaths==5)
end
assert(mixed_deaths:query('deaths',{sequence=130}).totals.deaths==5
    and mixed_deaths:query('deaths',{sequence=131}).totals.deaths==3)
assert(equal(mixed_before,mixed_deaths:snapshot()),'per-match gap calculation does not alter native totals or actual records')
-- Reattribution replaces the unknown native row in presentation, rather than
-- adding the same target to both a named weapon and unknown source totals.
do
    local raw='ABABABABABABABAB'
    local a=create({clock=function()return now end,weapon_catalog=weapons})
    local s={sequence=201,status='ended',ended_at=now-100,kills=1,deaths=0,
        source_reassignments={[raw]=1},weapon_stats={[raw]={name=raw,kills=1},[A]={kills=1}}}
    assert(a:observe(s))
    local display=a:query('weapons',{})
    assert(display.totals.kills==1 and #display.rows==1 and display.rows[1].id=='rifle'
        and display.rows[1].kills==1 and display.coverage.unknown_kills==0,
        'native unknown one plus target-known one is one kill after correction')
    assert(display.rows[1].detail_rows[1].kills==1 and display.totals.linked_kills==0,
        'association summaries use corrected source totals without inventing victim pairs')
    assert(a:query('weapons',{role='unknown'}).totals.kills==0
        and a:query('weapons',{query='未知'}).totals.kills==0,'correction applies before unknown filters')
    assert(a:query('weapons',{role='primary',query='步枪'}).totals.kills==1)
    local saved=a:snapshot()
    assert(saved.entries[1].weapons[raw].kills==1 and saved.entries[1].source_reassignments[raw]==1,
        'raw weapon hash/count remains intact with a separate correction')
    local revision=a.revision
    assert(not a:observe(s)and a.revision==revision,'same correction does not subtract again')
    s.source_reassignments[raw]=0;assert(not a:observe(s),'decreasing corrections cannot erase their high-water mark')
    assert(a:query('weapons',{}).totals.kills==1)
    local old={sequence=202,status='ended',ended_at=now-90000,kills=2,deaths=0,weapon_stats={[raw]={kills=2}}}
    a:observe(old)
    assert(a:query('weapons',{}).totals.kills==3 and a:query('weapons',{}).coverage.unknown_kills==2)
    assert(a:query('weapons',{sequence=201}).totals.kills==1
        and a:query('weapons',{sequence=202}).totals.kills==2,'corrections cannot pay down another match')
    assert(a:query('weapons',{period='24h'}).totals.kills==1
        and a:query('weapons',{period='7d'}).totals.kills==3,'time filters retain per-match correction ownership')
    assert(a:query('weapons',{period='24h',focus_id='unknown'}).totals.kills==0)
    local persisted=a:snapshot()
    local restarted=create({clock=function()return now end,weapon_catalog=weapons,saved=persisted})
    assert(restarted:query('weapons',{}).totals.kills==3 and restarted:query('weapons',{sequence=201}).totals.kills==1)
    assert(not restarted:observe(s),'restart retains exact correction without duplicate application')
    assert(persisted.entries[1].weapons[raw].kills==1,'queries and restart never rewrite original raw counts')
    local aligned={};for hash,v in pairs(weapons)do aligned[hash]=v end
    aligned[raw]={id='later-known',name='以后补名的武器',category='support'}
    local resolved=create({clock=function()return now end,weapon_catalog=aligned,saved=persisted})
    local exact=resolved:query('weapons',{sequence=201})
    assert(exact.totals.kills==1 and #exact.rows==1 and exact.rows[1].id=='rifle',
        'later catalog names cannot revive an already-reassigned duplicate')
    assert(resolved:query('weapons',{sequence=202}).totals.kills==2,'older uncorrected history is not changed')
    local delayed=create({weapon_catalog=weapons})
    local d={sequence=203,status='ended',kills=1,deaths=0,source_reassignments={[raw]=1},weapon_stats={[A]={kills=1}}}
    delayed:observe(d);assert(delayed:query('weapons',{}).totals.kills==1)
    d.weapon_stats[raw]={kills=1};delayed:observe(d)
    assert(delayed:query('weapons',{}).totals.kills==1,'a delayed native unknown row is covered by its already-recorded correction')
    d.kills=2;d.weapon_stats[raw].kills=2;delayed:observe(d)
    assert(delayed:query('weapons',{}).totals.kills==2 and delayed:query('weapons',{}).coverage.unknown_kills==1,
        'subsequent uncorrected unknown kills retain their own count')
end
-- A typed target attribution can retain the avatar as raw Health owner while
-- native accounting retains a different unknown source resource. It is still
-- one local kill: the unmatched correction can pay down only a proven excess
-- in this match's unknown display pool, never another known source or match.
do
    local avatar,unknown='4D1C334D294DFA97','FFFFFFFFFFFFFFFF'
    local a=create({clock=function()return now end,weapon_catalog=weapons})
    local s={sequence=301,status='ended',ended_at=now-100,kills=1,deaths=0,
        source_reassignments={[avatar]=1},weapon_stats={[A]={kills=1},[unknown]={kills=1}}}
    a:observe(s)
    local display=a:query('weapons',{})
    assert(display.totals.kills==1 and display.coverage.unknown_kills==0 and #display.rows==1,
        'Health-avatar correction removes a duplicate native unknown hash only when source totals exceed local kills')
    assert(a:query('weapons',{role='unknown'}).totals.kills==0
        and a:query('weapons',{query='未知'}).totals.kills==0
        and a:query('weapons',{role='primary'}).totals.kills==1,
        'unmatched correction applies per match before presentation filters')
    local before=a:snapshot()
    assert(before.entries[1].weapons[unknown].kills==1
        and before.entries[1].source_reassignments[avatar]==1
        and before.entries[1].source_reassignments[unknown]==nil,
        'query does not rewrite raw native hashes or saved correction evidence')
    local restarted=create({clock=function()return now end,weapon_catalog=weapons,saved=before})
    assert(restarted:query('weapons',{}).totals.kills==1
        and equal(before,restarted:snapshot()),'reload retains the display-only correction without rewriting raw rows')
    s.sequence=302;s.kills=2
    a:observe(s)
    local legitimate=a:query('weapons',{sequence=302})
    assert(legitimate.totals.kills==2 and legitimate.coverage.unknown_kills==1,
        'known one plus real unknown one remains two kills when native totals do not exceed actual kills')
    assert(a:query('weapons',{}).totals.kills==3,'one match cannot spend its correction on another match')
    s.sequence=303;s.kills=1;s.weapon_stats={[A]={kills=1},[C]={kills=1}}
    a:observe(s)
    assert(a:query('weapons',{sequence=303}).totals.kills==2,
        'unmatched corrections never reduce other known weapons, even with excess source totals')
    s.sequence=304;s.kills=3;s.weapon_stats={[A]={kills=2},[unknown]={kills=3}}
    a:observe(s)
    local bounded=a:query('weapons',{sequence=304})
    assert(bounded.totals.kills==4 and bounded.coverage.unknown_kills==2,
        'display deduction is bounded by unmatched correction, not an arbitrary cap to actual kills')
    assert(equal(before,restarted:snapshot()),'subsequent queries keep the original saved evidence untouched')
end
do
    local unknown='FFFFFFFFFFFFFFFF'
    local a=create({clock=function()return now end,weapon_catalog=weapons})
    local s={sequence=401,status='ended',ended_at=now-100,kills=1,deaths=0,
        source_reassignments={_unknown=1},weapon_stats={[A]={kills=1},[unknown]={kills=1}}}
    a:observe(s)
    local display=a:query('weapons',{})
    assert(display.totals.kills==1 and display.coverage.unknown_kills==0,
        'a continuous chain with no final raw owner may correct one duplicate unknown display count')
    local saved=a:snapshot()
    assert(saved.entries[1].source_reassignments._unknown==1 and saved.entries[1].weapons[unknown].kills==1)
    local restarted=create({clock=function()return now end,weapon_catalog=weapons,saved=saved})
    assert(restarted:query('weapons',{}).totals.kills==1 and equal(saved,restarted:snapshot()),
        'anonymous correction survives reload without a fabricated source hash or rewriting raw evidence')
    s.sequence=402;s.kills=2;a:observe(s)
    assert(a:query('weapons',{sequence=402}).coverage.unknown_kills==1,
        'anonymous allowance cannot erase legitimate unknown counts')
    s.sequence=403;s.kills=1;s.weapon_stats={[A]={kills=1},[C]={kills=1}};a:observe(s)
    assert(a:query('weapons',{sequence=403}).totals.kills==2,
        'anonymous allowance cannot reduce known weapon rows')
end
-- Death mechanism and responsible actor are separate: a self-attributed
-- explosion must not merge with a fall, while friendly fire remains one rank.
do
    local a=factory()
    local function death(id,category,weapon,kind,actor,evidence)
        assert(a:record_death({id=id,sequence=501,occurred_at=now,category=category,
            actor_name=actor or (category=='self'and'自身'or'队友'),weapon_name=weapon,
            damage_kind=kind,evidence=evidence}))
    end
    death('fall','self',nil,'坠落')
    death('fall-again','self',nil,'坠落')
    death('own-explosion','self','AC-8 机炮','爆炸',nil,{damage_kind_id=9,
        damage_element_id=255,damage_dealer=4294967295,damage_owner=0,
        weapon_type_hash='abcdef9876543210',source_channel='local_damage_queue',
        nearby_death_inferred=true,nearby_death_distance=10,nearby_death_interval=1})
    death('old-self','self')
    death('friendly-a','player','AC-8 机炮','爆炸')
    death('friendly-b','player','G-4 毒气弹','毒气')
    death('environment-fall','environment',nil,'坠落','坠落')
    death('unknown','unknown',nil,nil,'未知来源')
    local ranked=a:query('deaths',{})
    local named={};for _,row in ipairs(ranked.rows)do named[row.name]=row end
    assert(named['自身 · 坠落']and named['自身 · 坠落'].count==2,
        'self falls have a visible mechanism rank')
    assert(named['自身 · AC-8 机炮']and named['自身 · AC-8 机炮'].count==1,
        'self weapon explosion uses the resolved weapon before its generic mechanism')
    assert(named['自身']and named['自身'].count==1 and named['队友'].count==2
        and named['坠落'].count==1,'legacy self and friendly/environment grouping stay meaningful')
    assert(ranked.rows[#ranked.rows].unknown_group,'unresolved causes remain one final rank')
    local row=a:query('deaths',{mode='recent',query='事件 #own-explosion'}).rows[1]
    local ev=row.evidence
    assert(ev.damage_kind_id==9 and ev.damage_element_id==255 and ev.damage_dealer==4294967295
        and ev.damage_owner==0 and ev.weapon_type_hash=='ABCDEF9876543210',
        'plain native cause and weapon fields survive persistence without narrowing zero IDs')
    assert(ev.nearby_death_inferred==true and ev.nearby_death_distance==10 and ev.nearby_death_interval==1,
        'nearby simultaneous-death inference remains explicit with measured time and distance')
    local restarted=factory(a:snapshot())
    assert(equal(a:snapshot(),restarted:snapshot()),'cause IDs and source labels round trip unchanged')
    death('fractional-nearby','self',nil,'碰撞',nil,{nearby_death_inferred=false,
        nearby_death_distance=3.25,nearby_death_interval=.5})
    local fractional=a:query('deaths',{mode='recent',query='事件 #fractional-nearby'}).rows[1].evidence
    assert(fractional.nearby_death_inferred==false and fractional.nearby_death_distance==3.25
        and fractional.nearby_death_interval==.5,'distance and elapsed seconds preserve fractional values')
    death('invalid-evidence','self',nil,nil,nil,{damage_kind_id=10,damage_element_id=256,
        damage_dealer=-1,damage_owner=4294967296,weapon_type_hash='not-a-hash',
        nearby_death_inferred='true',nearby_death_distance=10.01,nearby_death_interval=1.01})
    local invalid=a:query('deaths',{mode='recent',query='事件 #invalid-evidence'}).rows[1].evidence
    assert(not invalid.damage_kind_id and not invalid.damage_element_id and not invalid.damage_dealer
        and not invalid.damage_owner and not invalid.weapon_type_hash,'invalid native cause values are omitted')
    assert(invalid.nearby_death_inferred==nil and invalid.nearby_death_distance==nil
        and invalid.nearby_death_interval==nil,'out-of-scope nearby claims are omitted')
end
print('PASS: combat high-water/restart/return, exact peer strings, missing legacy fields, independent source/enemy totals, period/filters, retained cache and 501 uncropped matches; self weapon/fall ranks, bounded native cause evidence and restart preserve raw rows.')
