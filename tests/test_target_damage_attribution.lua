local api=dofile(assert(arg[1]))()
local A,B,R36='A8CFFB316F0B5C5F','968211C0033DCE64','B6AFF2195568767F'
local n=0
local function check(name,fn)fn();n=n+1;print('PASS '..name)end
local function row(fields)
    local x={entity=101,pointer=100000,unit=202,epoch=1,health=100,life=0,
        now=0,damage_observed=false,owner=21,readable=true,local_source=true}
    for k,v in pairs(fields or {})do x[k]=v end
    return x
end
local function baseline()return api:baseline(row())end
local function damage(previous,at,fields)
    local x=row({now=at,damage_observed=true,health=60})
    for k,v in pairs(fields or {})do x[k]=v end
    return api:observe(previous,x)
end
local function known(previous,at,id)
    return damage(previous or baseline(),at or .1,{source_type=id or A,raw_type=id or A,health=90})
end
check('Eruptor known hit survives a four-second delay before unknown bleeding death',function()
    local t=known(nil,.1,R36)
    t=damage(t,4.1,{owner=0,kind=2,element=4,health=0,life=2})
    local d=api:death(t)
    assert(d.type==R36 and d.inferred and not d.barrier and d.last_known_at==.1)
end)
check('all unknown IDs owners and tokens keep the latest source in a continuous real damage chain',function()
    local t=known()
    t=damage(t,.5,{owner=80,damage_info_id=9001,damage_token=5,health=70})
    t=damage(t,1.5,{owner=0,damage_info_id=9002,damage_token=7,kind=2,element=5,health=20})
    t=damage(t,3,{owner=9,damage_info_id=9003,damage_token=99,health=0,life=2})
    local d=api:death(t)
    assert(d.type==A and d.inferred and d.target_bound and not d.barrier and d.history_complete)
    assert(d.last_damage_at==3 and d.last_known_at==.1 and d.damage_info_id==9003)
end)
check('more than 5 seconds without real damage expires the old source and blocks stale FIFO',function()
    local t=damage(known(),5.101,{owner=0,health=30})
    assert(not t.type and not t.chain_source and t.barrier and t.chain_expired and t.complete)
    t=damage(t,6,{owner=0,health=0,life=2})
    local d=api:death(t)
    assert(not d.type and d.barrier and d.history_complete and d.chain_expired)
end)
check('the 5 second boundary is inclusive even after floating point sampling',function()
    local t=damage(known(),5.1,{owner=0})
    assert(t.type==A and t.last_damage_at==5.1)
    t=damage(t,10.1,{owner=8});assert(t.type==A)
end)
check('a new known actual hit replaces the previous chain source including after expiry',function()
    local t=damage(known(),6,{owner=0})
    t=known(t,6.1,B);t=damage(t,7,{owner=0,health=0,life=2})
    assert(t.type==B and t.last_known_at==6.1 and not t.chain_expired)
end)
check('metadata polling owner token and known source fields cannot renew or replace a chain',function()
    local t=known()
    for _,at in ipairs({.5,2,5.1})do
        t=api:observe(t,row({now=at,health=90,source_type=B,owner=80,damage_token=at*10}))
        assert(t.type==A and t.last_damage_at==.1 and t.last_known_at==.1)
    end
    t=api:observe(t,row({now=5.2,health=90,source_type=B}))
    assert(not t.type and t.barrier and t.chain_expired and t.last_damage_at==.1)
    t=damage(t,5.3,{health=0,life=2});assert(not t.type and t.barrier)
end)
check('healing and no-HP native contact evidence do not extend the inactivity timer',function()
    local t=known()
    t=api:observe(t,row({now=4.9,health=110,source_type=B,damage_info_id=202}))
    assert(t.last_damage_at==.1 and t.chain_source==A)
    t=damage(t,5.2,{health=0,life=2});assert(not t.type and t.barrier)
end)
check('continuous unknown damage has no absolute age cap on the last named weapon',function()
    local t=known()
    for i=1,120 do
        t=damage(t,.1+i*.5,{owner=i,damage_token=i,damage_info_id=9000+i})
        assert(t.type==A and t.last_known_at==.1 and not t.barrier)
    end
    assert(t.last_damage_at==60.1)
end)
check('same-poll contact and final Health rows use one observation time',function()
    local t=known(nil,.1)
    t=damage(t,.1,{owner=42,health=50})
    assert(t.type==A and t.last_damage_at==.1)
    t=damage(t,5.1,{owner=0,health=0,life=2});assert(t.type==A)
end)
check('target identity life epoch read gaps and clock rewind never inherit another chain',function()
    for _,fields in ipairs({{readable=false},{entity=102},{pointer=100001},{unit=203},{epoch=2},{now=.05}})do
        local x=row({now=.5,damage_observed=true,owner=0,health=0,life=2})
        for k,v in pairs(fields)do x[k]=v end
        local t=api:observe(known(),x)
        assert(not t.type and not t.chain_source and t.barrier and not t.complete)
    end
    local t=api:observe(known(),row({now=.5,readable=false}))
    t=damage(t,.6,{health=0,life=2});assert(not t.type and not t.chain_source)
end)
check('unknown-only baseline keeps this kill eligible for its real native batch',function()
    local t=damage(baseline(),.1,{raw_type='FFFFFFFFFFFFFFFF',owner=42})
    t=damage(t,5,{raw_type='FFFFFFFFFFFFFFFF',owner=900,health=0,life=2})
    local d=api:death(t)
    assert(not d.type and not d.barrier and d.history_complete and d.raw_type=='FFFFFFFFFFFFFFFF')
end)
check('first-seen-dead direct source is usable only for this death and never creates a chain',function()
    local t=api:baseline(row({life=2}))
    t=api:observe(t,row({now=.1,first_seen_dead=true,source_type=A,health=0,life=0}))
    assert(t.type==A and not t.chain_source and not t.last_damage_at)
    t=api:observe(t,row({now=.1,first_seen_dead=true,owner=42,health=0,life=2}))
    assert(api:death(t).type==A and not t.chain_source)
    t=api:observe(t,row({now=.2,first_seen_dead=true,owner=42,health=0,life=2}))
    assert(not t.type and not t.chain_source)
end)
check('unknown raw identity stays genuine while absent raw hashes stay absent',function()
    local t=damage(known(),.5,{raw_type='FFFFFFFFFFFFFFFF'})
    assert(t.type==A and t.raw_type=='FFFFFFFFFFFFFFFF')
    t=damage(t,1,{health=0,life=2});assert(t.type==A and api:death(t).raw_type==nil)
end)
check('an observed enemy damage mechanism survives continuous unknown damage',function()
    local t=damage(baseline(),.1,{source_type=B,raw_type=B,mechanism='enemy_damage'})
    t=damage(t,.5,{owner=0,health=0,life=2})
    assert(api:death(t).type==B and api:death(t).mechanism=='enemy_damage')
end)
local SPORE='6B202392F4AB605E'
local function self_explosion(t,at,fields)
    local x={source_type=SPORE,raw_type=SPORE,owner=101,kind=4,health=0,life=2,
        mechanism='self_explosion',source_policy='native_target_self_explosion_owner'}
    for k,v in pairs(fields or {})do x[k]=v end
    return damage(t,at,x)
end
check('a target death explosion retains its own recent local weapon instead of overwriting it',function()
    local t=self_explosion(known(nil,.1,R36),4.1)
    local d=api:death(t)
    assert(d.type==R36 and d.raw_type==SPORE and d.inferred and not d.mechanism
        and d.policy=='same_target_weapon_before_self_explosion'and d.last_known_at==.1)
end)
check('death explosions use the latest local weapon and include the five second boundary',function()
    local t=known(known(nil,.1),.5,B)
    t=self_explosion(t,5.5)
    assert(t.type==B and t.inferred and t.last_known_at==.5)
end)
check('a source-free or expired self explosion remains a self explosion',function()
    for _,t in ipairs({baseline(),known(nil,.1)})do
        local d=api:death(self_explosion(t,5.2))
        assert(d.type==SPORE and d.mechanism=='self_explosion'and not d.inferred)
    end
end)
check('other-enemy damage and nonlocal weapons are not converted into local weapon self explosion credit',function()
    local enemy=damage(baseline(),.1,{source_type=B,raw_type=B,mechanism='enemy_damage'})
    local foreign=damage(baseline(),.1,{source_type=A,raw_type=A,local_source=false})
    for _,t in ipairs({enemy,foreign})do
        local d=api:death(self_explosion(t,.5))
        assert(d.type==SPORE and d.mechanism=='self_explosion'and not d.inferred)
    end
    local d=api:death(damage(known(),.5,{source_type=B,raw_type=B,mechanism='enemy_damage',life=2,health=0}))
    assert(d.type==B and d.mechanism=='enemy_damage','a different enemy owner remains the observed source')
end)
check('self explosion cannot cross target identity read or mission boundaries',function()
    for _,fields in ipairs({{entity=102},{pointer=100001},{unit=203},{epoch=2}})do
        local d=api:death(self_explosion(known(),.5,fields))
        assert(d.type==SPORE and d.mechanism=='self_explosion'and not d.inferred)
    end
    local t=api:observe(known(),row({now=.2,readable=false}))
    assert(self_explosion(t,.5).type==SPORE)
end)
print('Target continuous damage chain cases passed: '..n)
