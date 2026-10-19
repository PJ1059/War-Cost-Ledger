-- Fire attribution must also work for an exact Health death first seen between
-- polls. This does not grant a kill; the observer's existing native quota does.
local create=dofile(assert(arg[1]))
local G8='5C14F27759DD3BE0'
local resolver=create()
assert(resolver:explosion({local_player=true,source_type=G8,position={x=0,y=0,z=0},
    radius=10,status='fire',status_duration=27},0))
local function sample(fields)
    local row={entity=101,pointer=100000,unit=202,epoch=1,readable=true,
        local_source=true,owner=900,position={x=2,y=0,z=0},
        kind=2,element=1,damage_observed=false,first_seen_dead=true,life=2}
    for k,v in pairs(fields or{})do row[k]=v end
    return row
end
local result=resolver:resolve(sample(),nil,12)
assert(result and result.type==G8 and result.basis=='same_target_local_fire_status_area',
    'first-seen exact fatal fire must be eligible for the same bounded local area')
for _,fields in ipairs({{life=0},{first_seen_dead=false},{kind=0},{element=0},
    {local_source=false,creditor_missing=false},{position={x=11,y=0,z=0}},
    {readable=false},{damage_info_id=999}})do
    assert(not resolver:resolve(sample(fields),nil,12),'first-seen fire keeps all provenance gates')
end
assert(resolver:resolve(sample({local_source=false,creditor_missing=true}),nil,12))
resolver:life_changed(15)
assert(resolver:resolve(sample({epoch=2}),nil,20),
    'an avatar respawn does not extinguish an already observed local ground-fire area')
assert(not resolver:resolve(sample(),nil,27.01),'first-seen death cannot renew an expired area')
resolver:reset()
assert(not resolver:resolve(sample(),nil,27.02),'world/peer/read gaps still discard the previous fire context')
print('PASS first-dead fatal-fire source: position/element/local-quota eligibility; no live damage chain')
