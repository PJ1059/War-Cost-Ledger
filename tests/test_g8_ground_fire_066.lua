-- Source attribution only: an observed local G-8 area may explain actual fire
-- damage after the initial blast, never unrelated damage or a foreign kill.
local create=dofile(assert(arg[1]))
local G8,AC='5C14F27759DD3BE0','A8CFFB316F0B5C5F'
local resolver=create({damage_info={['202']={candidates={AC}},
    ['339']={candidates={G8}}},explosion={['32']={candidates={G8}}}})
local function area(fields)
    local row={local_player=true,source_type=G8,owner=42,position={x=0,y=0,z=0},
        radius=10,status='fire',status_duration=27,explosion_id=32}
    for k,v in pairs(fields or{})do row[k]=v end
    return resolver:explosion(row,0)
end
local function sample(fields)
    local row={entity=101,pointer=100000,unit=202,epoch=1,readable=true,
        local_source=true,owner=900,position={x=2,y=0,z=0},
        kind=2,element=1,damage_observed=true,life=2}
    for k,v in pairs(fields or{})do row[k]=v end
    return row
end
assert(area())
assert(resolver:has_status_context(12),'a reviewed G8 ground area must survive the 0.8s blast window')
local mapped=resolver:resolve(sample(),nil,12)
assert(mapped and mapped.type==G8 and mapped.local_source
    and mapped.basis=='same_target_local_fire_status_area','late ground fire must retain G8')
assert(not resolver:resolve(sample({life=0}),nil,26.9),'live extension elements are not verified and cannot seed a fire chain')
assert(not resolver:has_status_context(26.9,false),'a fire-only area must not trigger live element/position sampling')
assert(not resolver:resolve(sample(),nil,27.001),'the area cannot renew itself forever')
resolver:reset();assert(area())
for _,fields in ipairs({{kind=0,element=0},{kind=4,element=0},{kind=2,element=5},
    {kind=10,element=0},{kind=false,element=false},{damage_observed=false},
    {local_source=false,creditor_missing=false},{position={x=10.1,y=0,z=0}},
    {damage_info_id=999}})do
    assert(not resolver:resolve(sample(fields),nil,12),'G8 must not absorb unrelated/unsupported damage')
end
assert(resolver:resolve(sample({local_source=false,creditor_missing=true}),nil,12).type==G8)
assert(resolver:resolve(sample({source_type=AC}),nil,12).type==AC)
assert(resolver:resolve(sample({damage_info_id=202}),nil,12).type==AC)
resolver:reset();assert(not area({local_player=false}));assert(not resolver:resolve(sample(),nil,12))
resolver:reset();assert(area());resolver:reset();assert(not resolver:resolve(sample(),nil,12))
assert(area());assert(not resolver:has_status_context(-1))
print('PASS G8 ground fire: late real fire/local credit/position, bounded area; nonfire/foreign/typed/expired/reset negatives')
