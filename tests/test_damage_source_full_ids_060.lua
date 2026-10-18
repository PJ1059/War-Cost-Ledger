local create=dofile(assert(arg[1]))
local AC,G6,SENTRY='A8CFFB316F0B5C5F','4CE9EAB785A79B7B','02EECD0B1FA49630'
local CARRIER,SHARED='3B49715551E4CCF1','04C99523A808EF90'
local reverse={damage_info={['7']={candidates={AC},unresolved=false}},
    projectile={['7']={candidates={G6},unresolved=false},
        ['280']={candidates={SENTRY},unresolved=true},
        ['148']={candidates={AC,G6},shared=true,unresolved=true}},
    explosion={['7']={candidates={SENTRY},unresolved=false}},
    beam={['7']={candidates={AC},unresolved=false}},
    arc={['7']={candidates={G6},unresolved=false}}}
local resources={[CARRIER]={{kind='projectile',id=280}},[SHARED]={{kind='projectile',id=148}}}
local resolver=create(reverse,resources)
local count=0
local function input(fields)
    local row={entity=101,pointer=100000,unit=202,epoch=1,readable=true,
        local_source=true,damage_observed=true,health=20,life=0}
    for key,value in pairs(fields or {})do row[key]=value end
    return row
end
local function check(name,fn)resolver:reset();fn();count=count+1;print('PASS '..name)end
check('each complete native namespace resolves its own ID without numeric collisions',function()
    for _,case in ipairs({{'damage_info_id',AC},{'projectile_id',G6},{'explosion_id',SENTRY},
        {'beam_id',AC},{'arc_id',G6}})do
        local result=resolver:resolve(input({[case[1]]=7}),nil,0)
        assert(result and result.type==case[2] and result.inferred,case[1])
    end
end)
check('typed contradictions and invalid IDs do not select an arbitrary parent',function()
    assert(not resolver:resolve(input({damage_info_id=7,projectile_id=7}),nil,0))
    for _,id in ipairs({-1,.5,4294967296,999})do
        assert(not resolver:resolve(input({damage_info_id=id,raw_type=CARRIER}),nil,0))
    end
end)
check('unlabelled native weapon carrier follows its actual typed roots as an inference',function()
    local result=resolver:resolve(input({raw_type=CARRIER}),nil,0)
    assert(result and result.type==SENTRY and result.inferred
        and result.basis=='native_resource_typed_single_named_parent')
    assert(not resolver:resolve(input({raw_type=CARRIER,local_source=false}),nil,0),
        'one named candidate with unresolved native actors needs current local credit')
    assert(resolver:resolve(input({raw_type=CARRIER,source_type=G6}),nil,0).type==G6)
    assert(resolver:resolve(input({raw_type=CARRIER,damage_observed=false,first_seen_dead=true}),nil,0).type==SENTRY,
        'the existing current local first-corpse gate may infer its present carrier without borrowing a chain')
end)
check('shared resource stays unknown without active same-target context',function()
    assert(not resolver:resolve(input({raw_type=SHARED}),nil,0))
    local previous=input({chain_source=AC,last_damage_at=0,complete=true,chain_expired=false})
    assert(resolver:resolve(input({raw_type=SHARED}),previous,.2).type==AC)
    assert(resolver:resolve(input({raw_type=SHARED}),previous,5).type==AC)
    assert(not resolver:resolve(input({raw_type=SHARED}),previous,5.001))
    assert(not resolver:resolve(input({raw_type=SHARED,epoch=2}),previous,.2))
end)
check('complete tables never turn metadata or healing into attributed damage',function()
    for _,fields in ipairs({{raw_type=CARRIER},{projectile_id=7},{beam_id=7},{arc_id=7}})do
        fields.damage_observed=false
        assert(not resolver:resolve(input(fields),nil,0))
    end
end)
check('first-corpse inference stays death-only and cannot create a living damage chain',function()
    local make_trace=dofile(arg[2]or arg[1]:gsub('damage%-source%-resolver','target-damage-attribution'))
    local row=input({raw_type=CARRIER,damage_observed=false,first_seen_dead=true,life=2,now=0})
    local result=assert(resolver:resolve(row,nil,0))
    row.source_type,row.source_inferred,row.source_policy=result.type,true,result.basis
    local trace=make_trace()
    local observed=trace:observe(nil,row)
    assert(observed.type==SENTRY and not observed.chain_source and not observed.last_damage_at)
    assert(not trace:observe(observed,input({damage_observed=false,life=2,now=.1})).type)
end)
print('Complete typed source resolver checks passed: '..count)

