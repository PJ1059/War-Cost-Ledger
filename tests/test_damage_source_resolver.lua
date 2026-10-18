local create=dofile(assert(arg[1]))
local AC,G6,R36,GAS='A8CFFB316F0B5C5F','4CE9EAB785A79B7B','B6AFF2195568767F','0416984F4922757B'
local resolver=create({damage_info={
    ['202']={candidates={AC},unresolved=false},
    ['189']={candidates={AC,G6,R36},shared=true,unresolved=true},
    ['213']={candidates={AC},shared=true,unresolved=true}},
    explosion={['380']={candidates={AC},shared=true,unresolved=true}}})
local count=0
local function check(label,fn)resolver:reset();fn();count=count+1;print('PASS '..label)end
local function input(fields)
    local row={entity=101,pointer=100000,unit=202,epoch=1,readable=true,
        local_source=true,owner=42,position={x=0,y=0,z=0},damage_observed=true}
    for k,v in pairs(fields or {})do row[k]=v end
    return row
end
local function previous(fields)
    local row=input({type=AC,chain_source=AC,last_damage_at=0,last_known_at=0,complete=true,life=0,barrier=false})
    for k,v in pairs(fields or {})do row[k]=v end
    return row
end
local function blast(fields)
    local row={source_type=AC,owner=42,local_player=true,position={x=0,y=0,z=0},radius=6,explosion_id=380}
    for k,v in pairs(fields or {})do row[k]=v end
    return resolver:explosion(row,.1)
end
check('actual weapon resource wins over shared payload metadata',function()
    local result=resolver:resolve(input({source_type=G6,damage_info_id=189}),nil,0)
    assert(result.type==G6 and not result.inferred and result.basis=='native_resource')
end)
check('only unique fully rooted typed DamageInfo can identify its parent alone',function()
    assert(resolver:resolve(input({damage_info_id=202}),nil,0).type==AC)
    assert(not resolver:resolve(input({damage_info_id=213}),nil,0),'one named candidate is not unique when unresolved actors exist')
    assert(not resolver:resolve(input({damage_info_id=189}),nil,0),'shared shrapnel alone is not AC8')
    assert(not resolver:resolve(input({damage_info_id=380}),nil,0),'Explosion380 must not enter the DamageInfo namespace')
end)
check('shared shrapnel follows the same target active damage chain including G6',function()
    assert(resolver:resolve(input({damage_info_id=189}),previous(),0).type==AC)
    assert(resolver:resolve(input({damage_info_id=189}),previous({type=G6,chain_source=G6}),0).type==G6)
    assert(resolver:resolve(input({damage_info_id=189,owner=900,damage_token=3}),
        previous({inferred=true,unknown_contact=true,owner=80,damage_token=7}),0).type==AC)
    assert(not resolver:resolve(input({damage_info_id=189,epoch=2}),previous(),0))
end)
check('active chain expires after 5 seconds and never uses absolute source age',function()
    assert(resolver:resolve(input({damage_info_id=189}),previous(),5).type==AC)
    assert(not resolver:resolve(input({damage_info_id=189}),previous(),5.001))
    assert(not resolver:resolve(input({damage_info_id=189}),previous({chain_expired=true}),5.001))
    assert(resolver:resolve(input({damage_info_id=189}),previous({last_damage_at=59.5,last_known_at=0}),60).type==AC)
end)
check('shared Eruptor shrapnel uses its same-target parent four seconds after the hit',function()
    local mapped=resolver:resolve(input({damage_info_id=189}),previous({type=R36,chain_source=R36}),4)
    assert(mapped and mapped.type==R36 and mapped.inferred)
    assert(not resolver:resolve(input({damage_info_id=189,pointer=100001}),
        previous({type=R36,chain_source=R36}),4),'five-second window still requires exact target identity')
end)
check('shared payload can use a fresh nearby local blast with compatible parent',function()
    assert(blast())
    local result=resolver:resolve(input({damage_info_id=189}),nil,.2)
    assert(result.type==AC and result.basis=='typed_damage_info_local_blast_parent')
    assert(not resolver:resolve(input({damage_info_id=189,owner=43}),nil,.2))
    assert(not resolver:resolve(input({damage_info_id=189,position={x=7,y=0,z=0}}),nil,.2))
    assert(not resolver:resolve(input({damage_info_id=189}),nil,1))
end)
check('foreign or unverified explosion sources never provide context',function()
    assert(not blast({local_player=false}))
    assert(not blast({source_type=G6}),'catalogued explosion identity contradicts source')
    assert(not blast({radius=1000}))
    assert(not resolver:resolve(input({damage_info_id=189}),nil,.2))
end)
check('untyped blast fallback requires verified explosion damage and cannot claim DOT',function()
    assert(blast())
    assert(not resolver:resolve(input(),nil,.2))
    assert(not resolver:resolve(input({explosion_damage=true,damage_info_id=999}),nil,.2))
    assert(not resolver:resolve(input({explosion_damage=true,local_source=false}),nil,.2))
    assert(resolver:resolve(input({explosion_damage=true}),nil,.2).type==AC)
end)
check('fresh real blast evidence can establish a new source after an old damage chain expires',function()
    assert(blast())
    assert(resolver:resolve(input({damage_info_id=189}),previous({chain_expired=true}),.2).type==AC)
    assert(resolver:resolve(input({explosion_damage=true}),previous({chain_expired=true}),.2).type==AC)
end)
check('metadata and no-HP contacts cannot map a new source or borrow a blast',function()
    assert(blast())
    for _,fields in ipairs({{damage_info_id=202},{source_type=AC},{damage_info_id=189},{explosion_damage=true}})do
        fields.damage_observed=false
        assert(not resolver:resolve(input(fields),previous(),.2))
    end
end)
check('first-seen-dead allows a direct resource or unique typed source but never inferred context',function()
    assert(blast())
    assert(resolver:resolve(input({damage_observed=false,first_seen_dead=true,source_type=G6}),nil,.2).type==G6)
    assert(resolver:resolve(input({damage_observed=false,first_seen_dead=true,damage_info_id=202}),nil,.2).type==AC)
    assert(not resolver:resolve(input({damage_observed=false,first_seen_dead=true,damage_info_id=189}),previous(),.2))
    assert(not resolver:resolve(input({damage_observed=false,first_seen_dead=true,explosion_damage=true}),nil,.2))
end)
check('clock rewind and reset discard old blast context',function()
    assert(blast());assert(resolver:has_context(.2));assert(not resolver:has_context(0))
    assert(blast());resolver:reset();assert(not resolver:has_context(.2))
end)
check('blast cache is bounded independently of combat length',function()
    for _=1,100 do assert(blast())end
    assert(resolver.diagnostics.explosions==64)
end)
local function gas()
    return resolver:explosion({local_player=true,source_type=GAS,owner=42,position={x=0,y=0,z=0},
        radius=7,status='poison',status_duration=6},.1)
end
check('known local gas status seeds unknown real HP loss without a projectile contact',function()
    assert(gas());assert(resolver:has_status_context(3))
    local mapped=resolver:resolve(input({owner=900}),nil,3)
    assert(mapped.type==GAS and mapped.basis=='same_target_local_poison_status_area'and mapped.local_source)
    assert(not resolver:resolve(input({damage_observed=false}),nil,3),'metadata or no-HP contact never seeds gas')
    assert(resolver:resolve(input({kind=2,element=5}),nil,4).type==GAS)
    assert(resolver:resolve(input({kind=10,element=0}),nil,4).type==GAS,
        'native kind10 is none; it is no positive evidence against the verified local gas area')
    assert(not resolver:has_status_context(6.2))
    assert(not resolver:resolve(input(),nil,6.2),'six second status context is not a claim about the full cloud lifetime')
end)
check('gas does not steal known weapons typed projectiles or proven non-gas final damage',function()
    assert(gas())
    assert(resolver:resolve(input({source_type=AC}),nil,.2).type==AC)
    assert(resolver:resolve(input({damage_info_id=202}),nil,.2).type==AC)
    for _,fields in ipairs({{kind=0,element=0},{kind=2,element=1},{damage_info_id=189}})do
        assert(not resolver:resolve(input(fields),nil,.2))
    end
    assert(resolver:resolve(input({kind=4,element=0,explosion_damage=true}),nil,.2).type==GAS,
        'the actual initial G4 detonation keeps the ordinary .8s blast path')
    assert(not resolver:resolve(input({kind=4,element=0,explosion_damage=true}),nil,3),
        'a later unrelated explosion cannot borrow the six-second poison status context')
end)
check('local gas inference uses missing-creditor quota route but never foreign explicit credit',function()
    assert(gas())
    assert(resolver:resolve(input({local_source=false,creditor_missing=true,owner=0}),nil,.2).type==GAS)
    assert(not resolver:resolve(input({local_source=false,creditor_missing=false}),nil,.2))
    assert(not resolver:resolve(input({position={x=8,y=0,z=0}}),nil,.2))
end)
print('Damage source resolver cases passed: '..count)
