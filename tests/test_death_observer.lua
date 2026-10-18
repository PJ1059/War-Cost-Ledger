local create=dofile(assert(arg[1]))
local LOCAL,OTHER,THIRD='0123456789ABCDEF','FEDCBA9876543210','ABCDABCDABCDABCD'
local ENEMY,VICTIM,WEAPON='AAAAAAAAAAAAAAAA','BBBBBBBBBBBBBBBB','CCCCCCCCCCCCCCCC'
local function clone(v)if type(v)~='table'then return v end;local out={};for k,x in pairs(v)do out[k]=clone(x)end;return out end
local function fixture(no_reader,resource_names,nearby)
    local f={world={},calls=0,read_avatars={},name='队友甲',persona=2}
    f.players={{peer=LOCAL,avatar=17,slot=0,['local']=true,name='本人'},
        {peer=OTHER,avatar=18,slot=1,['local']=false}}
    f.raw={avatar_id=17,victim_type=VICTIM,life=2,last_owner=18,last_owner_type=VICTIM,last_creditor=OTHER,
        down_owner=0,down_creditor='0000000000000000'}
    local reader={}
    function reader:read(world,avatar)
        f.calls=f.calls+1;f.read_avatars[#f.read_avatars+1]=avatar
        if f.remote and f.remote[avatar]then return clone(f.remote[avatar])end
        if f.read_fail then return nil,'FIXTURE_MISSING' end
        return clone(f.raw)
    end
    function reader:damage_events(world,avatar)
        return clone(f.queue or {events={},token=''})
    end
    function reader:players(world,players)
        local out={}
        for _,p in ipairs(players)do local name='本人';if p.peer==OTHER then name=f.name end;out[#out+1]={peer_id=p.peer,name=name,
            persona_index=p.peer==OTHER and f.persona or 0,slot=p.slot+1,slot_index=p.slot,
            avatar_id=p.avatar,identity_source='contemporaneous_native_roster'}end
        return out
    end
    f.api=create({reader=not no_reader and reader or nil,resource_names=resource_names,nearby_deaths=nearby,catalog={
        [ENEMY]={kill=true,name_zh='虫族战士'},[WEAPON]={name_zh='测试步枪',kind='weapon'}}})
    function f:context(now,index)
        return {sequence=3,world=self.world,now=now,occurred_at=1700000000+now,mission_elapsed=50+now,
            local_peer=LOCAL,avatar=17,players=self.players,death_index=index}
    end
    function f:die(now,index,observed,extra)
        local context=self:context(now,index);for k,v in pairs(extra or {})do context[k]=v end
        return self.api:on_died({local_player=true,avatar_id=17,peer=LOCAL,position=self.position,
            observed=observed or 'dead_state',frame=100+math.floor(now*10)},context)
    end
    function f:damage(now,attacker)
        return self.api:on_damaged({local_player=true,entity_id=17,damage=20,attacker_peer=attacker or OTHER},self:context(now))
    end
    function f:step(now,mission,sequence)
        local context=self:context(now);context.sequence=sequence or context.sequence
        return self.api:step(now,self.world,{mission=mission~=false},self.players,context)
    end
    function f:sample(now,events,token)
        self.queue={events=events,token=token or tostring(now)}
        return self.api:sample_damage(now,self:context(now))
    end
    return f
end
local cases=0
local function check(name,fn)fn();cases=cases+1 end
local function witness(f,now,pos,kind)
    f.remote={[18]={avatar_id=18,victim_type=VICTIM,life=2,last_owner=0,last_creditor='0000000000000000',
        damage_cause={kind=kind or 4,element=0,life=2,owned=true,current=true,source='native_health_extension'}}}
    return f.api:on_died({local_player=false,peer=OTHER,avatar_id=18,position=pos,observed='dead_state'},f:context(now))
end
check('nearby simultaneous remote explosion fills unknown local death only once',function()
    local f=fixture(false,nil,true);f.read_fail=true;f.position={x=0,y=0,z=0}
    f:die(1);assert(select(2,witness(f,1.8,{x=6,y=0,z=0}))=='REMOTE_DEATH_WITNESS')
    f:step(2.2);local rows=f.api:take_records();assert(#rows==1)
    local row=rows[1];assert(row.category=='environment'and row.damage_kind=='爆炸')
    assert(row.confidence=='inferred'and row.evidence.nearby_death_inferred)
    assert(row.evidence.nearby_death_distance==6 and math.abs(row.evidence.nearby_death_interval-.8)<1e-9)
    assert(not row.evidence.damage_kind_proven and not row.evidence.native_fatal_event_proven)
end)
check('nearby inference rejects distant late other mission and missing position',function()
    for _,mode in ipairs({'far','late','sequence','position'})do
        local f=fixture(false,nil,true);f.read_fail=true
        if mode~='position'then f.position={x=0,y=0,z=0}end
        f:die(1)
        local ctx=f:context(mode=='late'and 2.05 or 1.1);if mode=='sequence'then ctx.sequence=4 end
        f.remote={[18]={avatar_id=18,victim_type=VICTIM,life=2,last_owner=0,last_creditor='0000000000000000',
            damage_cause={kind=4,element=0,life=2,owned=true,current=true,source='native_health_extension'}}}
        f.api:on_died({local_player=false,peer=OTHER,avatar_id=18,
            position={x=mode=='far'and 10.1 or 0,y=0,z=0}},ctx)
        f:step(2.2);assert(f.api:take_records()[1].category=='unknown',mode)
    end
end)
check('player identity alone is not a shared death mechanism',function()
    local f=fixture(false,nil,true);f.read_fail=true;f.position={x=0,y=0,z=0};f:die(1)
    f.remote={[18]={avatar_id=18,victim_type=VICTIM,life=2,last_owner=17,last_owner_type=VICTIM,last_creditor=LOCAL}}
    f.api:on_died({local_player=false,peer=OTHER,avatar_id=18,position={x=0,y=0,z=0}},f:context(1.1))
    f:step(2.2);local row=f.api:take_records()[1]
    assert(row.category=='unknown'and not row.evidence.nearby_death_inferred)
end)
check('nearby death does not override a known enemy or own final mechanism',function()
    for _,mode in ipairs({'enemy','drowning'})do
        local f=fixture(false,nil,true);f.position={x=0,y=0,z=0}
        if mode=='enemy'then f.raw.last_owner=42;f.raw.last_owner_type=ENEMY;f.raw.last_creditor='0000000000000000'
        else f.raw.damage_cause={kind=8,element=0,life=2,owned=true,current=true,source='native_health_extension'}end
        f:die(1);witness(f,1.1,{x=0,y=0,z=0});f:step(2.2);local row=f.api:take_records()[1]
        assert(not row.evidence.nearby_death_inferred)
        assert(mode=='enemy'and row.category=='enemy'or mode=='drowning'and row.damage_kind=='溺水')
    end
end)
check('self explosion keeps real dealer weapon after body disappears',function()
    local f=fixture(false,{[WEAPON]={name_zh='测试步枪',kind='weapon'}})
    f:sample(.95,{{target=17,kind=4,element=0,damage=200,dealer_entity=41,
        owner_entity=17,dealer_type=WEAPON,creditor=LOCAL}})
    f.read_fail=true;f:die(1);f:step(1.6);local row=f.api:take_records()[1]
    assert(row.category=='self' and row.damage_kind=='爆炸' and row.weapon_name=='测试步枪')
    assert(row.evidence.damage_kind_id==4 and row.evidence.weapon_type_hash==WEAPON)
    assert(row.evidence.source_channel=='local_damage_queue' and not row.evidence.native_fatal_event_proven)
end)
check('self collision differs from weapon explosion and ignores old peer credit',function()
    local f=fixture();f:sample(.95,{{target=17,kind=5,element=0,damage=300,
        dealer_entity=17,owner_entity=17,creditor=OTHER}})
    f.read_fail=true;f:die(1);f:step(1.6);local row=f.api:take_records()[1]
    assert(row.category=='environment' and row.actor_name=='坠落／碰撞' and row.damage_kind=='坠落／碰撞')
    assert(not row.weapon_name and not row.player)
end)
check('owned final cause maps explosion collision drowning bleeding without queue',function()
    for kind,name in pairs({[4]='爆炸',[5]='撞击',[8]='溺水',[9]='失血'})do
        local f=fixture();f.raw.last_owner=0;f.raw.last_owner_type=nil;f.raw.last_creditor='0000000000000000'
        f.raw.damage_cause={kind=kind,element=0,life=2,owned=true,current=true,source='native_health_extension'}
        f:die(1);f:step(1.6);local row=f.api:take_records()[1]
        assert(row.category=='environment' and row.actor_name==name and row.damage_kind==name)
        assert(row.evidence.damage_kind_id==kind and row.evidence.damage_kind_proven==true)
    end
end)
check('latest unknown dealer does not reuse earlier known weapon',function()
    local f=fixture(false,{[WEAPON]={name_zh='测试步枪',kind='weapon'}})
    f:sample(.8,{{target=17,kind=4,element=0,damage=20,dealer_type=WEAPON,owner_entity=17,creditor=LOCAL}})
    f:sample(.95,{{target=17,kind=4,element=0,damage=200,creditor=LOCAL}})
    f.read_fail=true;f:die(1);f:step(1.6);local row=f.api:take_records()[1]
    assert(row.category=='self' and row.damage_kind=='爆炸' and not row.weapon_name)
end)
check('queue misses cannot inherit old avatar old mission or stale repeated snapshot',function()
    for _,mode in ipairs({'stale','avatar','sequence'})do
        local f=fixture();f:sample(.1,{{target=17,kind=4,element=0,damage=200,creditor=LOCAL}},'unchanged')
        if mode=='stale'then f:sample(3,{{target=17,kind=4,element=0,damage=200,creditor=LOCAL}},'unchanged')
        elseif mode=='avatar'then f.queue={events={{target=18,kind=4,element=0,damage=200,creditor=LOCAL}},token='new'}
            local ctx=f:context(.95);ctx.avatar=18;f.api:sample_damage(.95,ctx)
        else f.queue={events={},token=''};local ctx=f:context(.95);ctx.sequence=4;f.api:sample_damage(.95,ctx)end
        f.read_fail=true;f:die(mode=='stale'and 3 or 1);f:step(mode=='stale'and 3.6 or 1.6)
        assert(f.api:take_records()[1].category=='unknown',mode)
    end
end)
check('owned final kind prevents unrelated queued explosion being assigned to drowning',function()
    local f=fixture(false,{[WEAPON]={name_zh='测试步枪',kind='weapon'}})
    f:sample(.95,{{target=17,kind=4,element=0,damage=100,dealer_type=WEAPON,creditor=LOCAL}})
    f.raw.last_owner=0;f.raw.last_owner_type=nil;f.raw.last_creditor=LOCAL
    f.raw.damage_cause={kind=8,element=0,life=2,owned=true,current=true,source='native_health_extension'}
    f:die(1);f:step(1.6);local row=f.api:take_records()[1]
    assert(row.category=='environment' and row.actor_name=='溺水' and row.damage_kind=='溺水' and not row.weapon_name)
end)
check('event then native counter, one result',function()
    local f=fixture();local id=f:die(1)
    assert(select(1,f:die(1.1,1,'native_death_counter'))==id)
    f:step(1.6);local rows=f.api:take_records();assert(#rows==1)
    assert(rows[1].category=='player' and rows[1].confidence=='low' and rows[1].actor_name=='队友甲')
    assert(rows[1].player.slot==2 and rows[1].player.slot_index==1 and rows[1].player.persona_index==2)
    assert(rows[1].evidence.death_index==1 and rows[1].evidence.runtime_death_event and rows[1].evidence.native_death_counter)
    assert(not rows[1].weapon_name and not rows[1].damage_kind and not rows[1].evidence.native_fatal_event_proven)
    assert(#f.api:take_records()==0)
end)
check('counter then event, explicit event wins',function()
    local f=fixture();local id=f:die(1,1,'native_death_counter');assert(f:die(1.1)==id)
    f:step(1.6);local row=f.api:take_records()[1]
    assert(row.evidence.death_observed=='dead_state' and row.occurred_at==1700000001.1)
end)
check('no event backend keeps unknown counter death',function()
    local f=fixture(true);f:die(1,1,'native_death_counter');f:step(1.6)
    local row=f.api:take_records()[1];assert(row.category=='unknown' and row.confidence=='unknown')
    assert(row.victim.peer_id==LOCAL and row.sequence==3 and row.evidence.native_death_counter)
end)
check('damage snapshot survives name/slot/persona changes',function()
    local f=fixture();f:damage(.9);f.name='更名后';f.persona=1;f.players[2].slot=0
    f:die(1);f.name='死亡后再更名';f.players[2].slot=3
    f:step(1.6);local row=f.api:take_records()[1]
    assert(row.actor_name=='队友甲' and row.player.slot==2 and row.player.persona_index==2)
    assert(row.confidence=='inferred' and not row.player.steam_id and not row.player.psn_id)
end)
check('roster at death remains frozen during delay',function()
    local f=fixture();f:die(1);f.name='另一个玩家';f.players[2].peer=THIRD;f.players[2].slot=0
    f:step(1.6);local row=f.api:take_records()[1]
    assert(row.player.peer_id==OTHER and row.actor_name=='队友甲' and row.player.slot==2)
end)
check('enemy type is inferred only, not a weapon',function()
    local f=fixture();f.raw.last_owner=42;f.raw.last_owner_type=ENEMY;f.raw.last_creditor='0000000000000000'
    f:die(1);f:step(1.6);local row=f.api:take_records()[1]
    assert(row.category=='enemy' and row.actor_name=='虫族战士' and row.confidence=='low' and not row.weapon_name)
end)
check('exact enemy owner is not vetoed by retained creditor or its derived runtime peer',function()
    local f=fixture();f:damage(.9,OTHER)
    f.raw.last_owner=42;f.raw.last_owner_type=ENEMY;f.raw.last_creditor=LOCAL
    f:die(1);f:step(1.6);local row=f.api:take_records()[1]
    assert(row.category=='enemy' and row.actor_name=='虫族战士' and row.confidence=='low' and not row.player)
    assert(row.evidence.actor_type_hash==ENEMY and not row.evidence.source_reason)
end)
check('real player-avatar owner disagreement still refuses an attacker',function()
    local f=fixture();f.raw.last_owner=18;f.raw.last_creditor=LOCAL
    f:die(1);f:step(1.6);local row=f.api:take_records()[1]
    assert(row.category=='unknown' and row.evidence.source_reason=='CONFLICTING_SOURCE_EVIDENCE')
end)
check('owned native current fire and gas death kind identifies environment without a weapon guess',function()
    for element,name in pairs({[1]='燃烧',[5]='毒气'})do
        local f=fixture();f.raw.last_owner=0;f.raw.last_owner_type=nil;f.raw.last_creditor='0000000000000000'
        f.raw.damage_cause={kind=2,element=element,life=2,owned=true,current=true,source='native_health_extension'}
        f:die(1);f:step(1.6);local row=f.api:take_records()[1]
        assert(row.category=='environment' and row.actor_name==name and row.damage_kind==name and row.confidence=='inferred')
        assert(not row.weapon_name and not row.evidence.native_fatal_event_proven and not row.evidence.weapon_source_proven)
    end
end)
check('element cannot overwrite a known player and stale ext cannot become a death kind',function()
    local f=fixture();f.raw.damage_cause={kind=2,element=1,life=2,owned=true,current=true,source='native_health_extension'}
    f:die(1);f:step(1.6);local row=f.api:take_records()[1]
    assert(row.category=='player' and row.actor_name=='队友甲' and row.damage_kind=='燃烧')
    local bleed=fixture();bleed.raw.damage_cause={kind=2,element=4,life=2,owned=true,current=true,source='native_health_extension'}
    bleed:die(1);bleed:step(1.6);assert(bleed.api:take_records()[1].damage_kind=='流血')
    for _,cause in ipairs({{kind=2,element=1,life=1,owned=true,current=true,source='native_health_extension'},
        {kind=2,element=1,life=2,owned=false,current=true,source='native_health_extension'},
        {kind=2,element=1,life=2,owned=true,current=false,source='native_health_extension'}})do
        local f=fixture();f.raw.last_owner=0;f.raw.last_owner_type=nil;f.raw.last_creditor='0000000000000000'
        f.raw.damage_cause=cause;f:die(1);f:step(1.6);local row=f.api:take_records()[1]
        assert(row.category=='unknown' and not row.damage_kind)
    end
end)
check('unknown owner and no peer does not mean environment',function()
    local f=fixture();f.raw.last_owner=0;f.raw.last_owner_type=nil;f.raw.last_creditor='0000000000000000'
    f:die(1);f:step(1.6);local row=f.api:take_records()[1]
    assert(row.category=='unknown' and not row.damage_kind and not row.actor_name)
end)
check('unmapped exact owner type hash survives for later label alignment',function()
    local f=fixture();f.raw.last_owner=42;f.raw.last_owner_type='fedcba9876543210';f.raw.last_creditor='0000000000000000'
    f:die(1);f:step(1.6);local row=f.api:take_records()[1]
    assert(row.category=='unknown' and not row.weapon_name and not row.actor_name)
    assert(row.evidence.actor_type_hash=='FEDCBA9876543210')
    assert(not row.evidence.weapon_source_proven and not row.evidence.native_fatal_event_proven)
end)
check('partial or rounded owner type cannot become a resource identity',function()
    for _,value in ipairs({'FEDCBA98',18446744073709551615,'0000000000000000'})do
        local f=fixture();f.raw.last_owner=42;f.raw.last_owner_type=value;f.raw.last_creditor='0000000000000000'
        f:die(1);f:step(1.6);local row=f.api:take_records()[1]
        assert(row.category=='unknown' and not row.evidence.actor_type_hash)
    end
end)
check('exact unknown source resource name is display only',function()
    local hash='DDDDDDDDDDDDDDDD'
    local f=fixture(false,{[hash]={name_zh='爆炸筒',kind='unknown'}})
    f.raw.last_owner=42;f.raw.last_owner_type=hash:lower();f.raw.last_creditor='0000000000000000'
    f:die(1);f:step(1.6);local row=f.api:take_records()[1]
    assert(row.actor_name=='爆炸筒' and row.category=='unknown' and row.confidence=='unknown')
    assert(not row.weapon_name and not row.damage_kind and not row.evidence.weapon_source_proven)
    assert(not row.evidence.native_fatal_event_proven and row.evidence.actor_type_hash==hash)
    assert(row.evidence.source_channel=='native_health_last_owner_type_label_only')
end)
check('label never overrides conflicting player evidence',function()
    local f=fixture(false,{[VICTIM]={name_zh='资源别名'}})
    f:damage(.9,OTHER);f.raw.last_creditor=LOCAL;f.raw.last_owner=17
    f:die(1);f:step(1.6);local row=f.api:take_records()[1]
    assert(row.category=='unknown' and not row.actor_name and row.evidence.source_reason=='CONFLICTING_SOURCE_EVIDENCE')
end)
check('partial or control-character label is never shown',function()
    for _,hash in ipairs({'DDDDDDDD', 'DDDDDDDDDDDDDDDD'})do
        local f=fixture(false,{[hash]={name_zh='错误\n名称'}})
        f.raw.last_owner=42;f.raw.last_owner_type=hash;f.raw.last_creditor='0000000000000000'
        f:die(1);f:step(1.6);local row=f.api:take_records()[1]
        assert(not row.actor_name and row.category=='unknown')
    end
end)
check('self peer is a session identity',function()
    local f=fixture();f.raw.last_owner=17;f.raw.last_creditor=LOCAL
    f:die(1);f:step(1.6);local row=f.api:take_records()[1]
    assert(row.category=='self' and row.player.peer_id==LOCAL and row.player.identity_scope=='session_peer_not_permanent_account')
end)
check('conflicting event and health peer does not choose a killer',function()
    local f=fixture();f:damage(.9,OTHER);f.raw.last_creditor=LOCAL;f.raw.last_owner=17
    f:die(1);f:step(1.6);local row=f.api:take_records()[1]
    assert(row.category=='unknown' and row.evidence.source_reason=='CONFLICTING_SOURCE_EVIDENCE')
end)
check('weapon catalogue and current held weapon do not prove fatal weapon',function()
    local f=fixture();f.raw.last_owner=99;f.raw.last_owner_type=WEAPON;f.raw.last_creditor='0000000000000000'
    f:die(1,nil,nil,{held_weapon='测试步枪'});f:step(1.6);local row=f.api:take_records()[1]
    assert(row.category=='unknown' and not row.weapon_name)
end)
check('delayed source reads the old avatar, not the respawn',function()
    local f=fixture();f:die(1);f.players[1].avatar=77;f:step(1.6)
    assert(f.read_avatars[#f.read_avatars]==17)
    local row=f.api:take_records()[1];assert(row.victim.avatar_id==17)
end)
check('returning to ship flushes pending without native reads',function()
    local f=fixture();f:die(1);local reads=f.calls;f:step(1.1,false)
    local row=f.api:take_records()[1];assert(row and row.sequence==3 and f.calls==reads)
end)
check('new sequence preserves old record sequence',function()
    local f=fixture();f:die(1);f:step(1.1,true,4)
    local row=f.api:take_records()[1];assert(row and row.sequence==3)
end)
check('repeated events after delivery stay deduplicated',function()
    local f=fixture();local id=f:die(1,1);f:step(1.6);local row=f.api:take_records()[1]
    assert(f:die(2,1,'native_death_counter')==id);f:die(2.1);f:step(3)
    assert(#f.api:take_records()==0 and row.player.name=='队友甲')
end)
check('counter gap never applies last source to multiple deaths',function()
    local f=fixture();f:die(1)
    f:die(1.1,1,'native_death_counter',{skip_attribution=true})
    f:die(1.1,2,'native_death_counter',{skip_attribution=true})
    f:step(1.7);local rows=f.api:take_records();assert(#rows==2)
    for _,row in ipairs(rows)do assert(row.category=='unknown' and row.confidence=='unknown')end
end)
check('foreign player events rejected',function()
    local f=fixture();assert(select(2,f.api:on_died({local_player=false,peer=OTHER},f:context(1)))=='NOT_LOCAL_DEATH')
    assert(not f.api:on_damaged({local_player=false,damage=5},f:context(1)))
    f:step(2);assert(#f.api:take_records()==0)
end)
check('old nonfatal hit not called a death cause',function()
    local f=fixture();f:damage(1);f.read_fail=true;f:die(3);f:step(3.6)
    assert(f.api:take_records()[1].category=='unknown')
end)
check('recent damage source frozen before health record disappears',function()
    local f=fixture();f.raw.last_owner=42;f.raw.last_owner_type=ENEMY;f.raw.last_creditor='0000000000000000'
    f.api:on_damaged({local_player=true,entity_id=17,damage=20},f:context(.9))
    f.read_fail=true;f:die(1);f:step(1.6)
    assert(f.api:take_records()[1].category=='enemy')
end)
check('missing actor name remains missing, never future roster backfill',function()
    local f=fixture();f.name=nil;f:die(1);f.name='之后才知道';f:step(1.6)
    local row=f.api:take_records()[1];assert(row.category=='player' and not row.actor_name and not row.player.name)
end)
check('downing source fallback retains low confidence',function()
    local f=fixture();f.raw.last_owner=0;f.raw.last_owner_type=nil;f.raw.last_creditor='0000000000000000'
    f.raw.down_owner=18;f.raw.down_creditor=OTHER;f:die(1);f:step(1.6)
    local row=f.api:take_records()[1];assert(row.category=='player' and row.confidence=='low' and row.evidence.used_downing_source)
end)
check('pending queue bounded and reset creates a new observer epoch',function()
    local f=fixture()
    for i=1,16 do assert(f:die(1,i,'native_death_counter',{skip_attribution=true}))end
    assert(select(2,f:die(1,17,'native_death_counter',{skip_attribution=true}))=='DEATH_RECORD_CAPACITY')
    f:step(2);assert(#f.api:take_records()==16)
    f.api:reset();assert(f:die(3,1));f:step(4);assert(#f.api:take_records()==1)
end)
check('schema mutation by consumer cannot alter cached death identity',function()
    local f=fixture();local id=f:die(1,1);f:step(1.6);local row=f.api:take_records()[1]
    row.player.name='modified';assert(f:die(2,1,'native_death_counter')==id)
    f:step(3);assert(#f.api:take_records()==0)
end)
check('a new creditor after death cannot replace the death source',function()
    local f=fixture();f:die(1);f.raw.last_owner=17;f.raw.last_creditor=LOCAL
    f:step(1.6);local row=f.api:take_records()[1]
    assert(row.category=='unknown' and row.evidence.source_reason=='DEATH_SOURCE_CHANGED_AFTER_DEATH')
end)
check('changed native victim identity also rejects cached source inference',function()
    local f=fixture();f:damage(.9);f:die(1);f.raw.victim_type=ENEMY
    f:step(1.6);local row=f.api:take_records()[1]
    assert(row.category=='unknown' and row.evidence.source_reason=='DEATH_SOURCE_IDENTITY_CHANGED')
end)
check('late counter after delivery and removed avatar binds the event only once',function()
    local f=fixture();local id=f:die(1);f:step(1.6)
    local old=f.api:take_records()[1];f.players[1].avatar=nil
    local context=f:context(5,1);context.avatar=nil
    assert(f.api:on_died({local_player=true,observed='native_death_counter'},context)==id)
    f:step(5.6);assert(#f.api:take_records()==0 and old.victim.avatar_id==17 and old.actor_name=='队友甲')
end)
check('late counter after delivery never reads the reinforced body',function()
    local f=fixture();local id=f:die(1);f:step(1.6);local row=f.api:take_records()[1]
    f.players[1].avatar=77;f.raw.avatar_id=77;f.raw.life=0;local before=f.calls
    local context=f:context(4,1);context.avatar=77
    assert(f.api:on_died({local_player=true,observed='native_death_counter'},context)==id)
    assert(f.calls==before);f:step(4.6);assert(#f.api:take_records()==0 and row.victim.avatar_id==17)
end)
check('counter cannot use a living replacement or suppress its later real death',function()
    local f=fixture();f.players[1].avatar=77;f.raw.avatar_id=77;f.raw.life=0
    local context=f:context(1,1);context.avatar=77
    local first=f.api:on_died({local_player=true,observed='native_death_counter'},context)
    f:step(1.6);local row=f.api:take_records()[1]
    assert(row.category=='unknown' and row.evidence.source_reason=='COUNTER_VICTIM_AVATAR_NOT_DEAD')
    assert(not row.victim.avatar_id)
    f.raw.life=2;context=f:context(1.8);context.avatar=77
    local second=f.api:on_died({local_player=true,avatar_id=77,peer=LOCAL,observed='dead_state',frame=118},context)
    assert(first~=second)
    context=f:context(1.9,2);context.avatar=77
    assert(f.api:on_died({local_player=true,observed='native_death_counter'},context)==second)
    f:step(2.4);local rows=f.api:take_records();assert(#rows==1 and rows[1].victim.avatar_id==77)
end)
check('counter without a proved body remains unknown when a delayed event arrives',function()
    local f=fixture();f.read_fail=true;f.players[1].avatar=nil
    local context=f:context(1,1);context.avatar=nil
    local id=f.api:on_died({local_player=true,observed='native_death_counter'},context)
    f.read_fail=false;context=f:context(1.1)
    assert(f.api:on_died({local_player=true,avatar_id=17,peer=LOCAL,observed='dead_state',frame=111},context)==id)
    f:step(1.6);local row=f.api:take_records()[1]
    assert(row.category=='unknown' and not row.victim.avatar_id and row.evidence.runtime_death_event)
end)
check('finished unpaired counter also deduplicates its late official event',function()
    local f=fixture();f.read_fail=true;f.players[1].avatar=nil
    local context=f:context(1,1);context.avatar=nil
    local id=f.api:on_died({local_player=true,observed='native_death_counter'},context)
    f:step(1.6);assert(#f.api:take_records()==1);f.read_fail=false
    context=f:context(1.8)
    assert(f.api:on_died({local_player=true,avatar_id=17,peer=LOCAL,observed='dead_state',frame=118},context)==id)
    f:step(2.4);assert(#f.api:take_records()==0)
end)
check('per-event queue token does not renew when rolling snapshots omit then rediscover the row',function()
    local f=fixture()
    local event={target=17,kind=4,element=0,damage=200,owner_entity=17,creditor=LOCAL,
        token='same-112B-native-row'}
    f:sample(.1,{event},'A')
    f:sample(1.5,{},'')
    f:sample(3,{event},'A')
    f.read_fail=true;f:die(3.01);f:step(3.6)
    local rows=f.api:take_records();assert(#rows==1)
    assert(rows[1].category=='unknown' and not rows[1].damage_kind and not rows[1].player)
end)
check('conflicting queue owner and creditor retain the mechanism without blaming a player',function()
    local f=fixture(false,{[WEAPON]={name_zh='测试步枪',kind='weapon'}})
    f:sample(.95,{{target=17,kind=4,element=0,damage=200,owner_entity=18,creditor=LOCAL,
        dealer_type=WEAPON,token='conflicting-current-player-ids'}},'conflicting-current-player-ids')
    f.read_fail=true;f:die(1);f:step(1.6)
    local rows=f.api:take_records();assert(#rows==1)
    local row=rows[1]
    assert(not row.player and row.category~='player' and row.category~='self')
    assert(row.damage_kind=='爆炸' and row.weapon_name=='测试步枪')
    assert(row.evidence.source_reason=='CONFLICTING_SOURCE_EVIDENCE')
    assert(not row.evidence.native_fatal_event_proven and not row.evidence.weapon_source_proven)
end)
check('known enemy dealer survives the victim avatar owner and creditor alias',function()
    local f=fixture()
    f:sample(.95,{{target=17,kind=6,element=0,damage=200,owner_entity=17,owner_type=VICTIM,
        dealer_entity=42,dealer_type=ENEMY,creditor=LOCAL,token='enemy-with-victim-owner'}},'enemy-with-victim-owner')
    f.read_fail=true;f:die(1);f:step(1.6)
    local rows=f.api:take_records();assert(#rows==1)
    local row=rows[1]
    assert(row.category=='enemy' and row.actor_name=='虫族战士' and not row.player)
    assert(row.evidence.actor_type_hash==ENEMY and row.evidence.damage_kind_id==6)
    assert(not row.weapon_name and not row.evidence.native_fatal_event_proven)
end)
check('duplicate remote death preserves first witness time instead of extending the one-second window',function()
    local f=fixture(false,nil,true);f.read_fail=true;f.position={x=0,y=0,z=0}
    f.remote={[18]={avatar_id=18,victim_type=VICTIM,life=2,last_owner=0,last_creditor='0000000000000000',
        damage_cause={kind=4,element=0,life=2,owned=true,current=true,source='native_health_extension'}}}
    local event={local_player=false,peer=OTHER,avatar_id=18,position={x=0,y=0,z=0},
        observed='dead_state',frame=10}
    assert(select(2,f.api:on_died(event,f:context(1)))=='REMOTE_DEATH_WITNESS')
    f:die(2.5)
    assert(select(2,f.api:on_died(event,f:context(2.6)))=='REMOTE_DEATH_DUPLICATE')
    f:step(3.7)
    local rows=f.api:take_records();assert(#rows==1)
    assert(rows[1].category=='unknown' and not rows[1].evidence.nearby_death_inferred)
    assert(#f.api:take_records()==0)
end)
print('PASS: '..cases..' death observer tests; event/counter dedupe, frozen identities, delayed same-avatar evidence, unknown/gap handling, return-to-ship flush and no claimed fatal weapon')
