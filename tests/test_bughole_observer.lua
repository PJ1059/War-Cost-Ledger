local module=dofile(arg[1])
local world_module=dofile(arg[2])
local upstream=dofile(arg[3])
local function eq(a,b,label)assert(a==b,(label or'')..': '..tostring(a)..' ~= '..tostring(b))end
local list_world,descriptor_count,list_failure,records_failure,throwing=10000,40,false,false,false
local descriptor_reads,record_reads,position_reads=0,0,0
local descriptors,records={},{ }
for i=1,40 do
    descriptors[i]={resource=i==1 and'HOLE'or'DECOR',unit=900+i,entity=700+i}
    records[i+6]={unit=900+i,stage=0,registered=true}
end
local position={x=1,y=2,z=3}
local source={
    destructibles=function()
        if throwing then error('adapter fixture failure')end
        if list_failure then return nil,'LIST_FAILED'end
        return {count=descriptor_count,world=list_world,
            pointers={ptr=function(_,at)return at/8+1 end},indices={i32=function(_,at)return at/4+7 end}}
    end,
    destructible_descriptor=function(_,pointer)descriptor_reads=descriptor_reads+1;return descriptors[pointer]end,
    bug_hole_kind=function(resource)return resource=='HOLE'and'warrior'or nil end,
    destruction_records=function(_,_,first,last)
        record_reads=record_reads+1
        if records_failure then return nil,'RECORD_FAILED'end
        return {first=first,last=last}
    end,
    destruction_record=function(block,at)
        local r=records[block.first+at/12]
        return r.unit,r.stage,r.registered
    end,
    unit_position=function(_,unit,level)eq(unit,901);eq(level,true);position_reads=position_reads+1;return position end,
}
local world={game=0x180000000,view={slot=function()return{}end}}
local emitted={}
local observer=module.new({world_api=source,emit=function(row)emitted[#emitted+1]=row end})
eq(#assert(observer:step(world,1,1)),0,'baseline')
eq(descriptor_reads,32,'descriptor read budget');eq(observer.diagnostics.descriptor_pending,8)
eq(observer.diagnostics.descriptor_count,40,'native instance count')
eq(observer.diagnostics.valid_pointers,40);eq(observer.diagnostics.invalid_pointers,0)
eq(observer.diagnostics.invalid_indices,0);eq(observer.diagnostics.cached_descriptors,32)
eq(observer.diagnostics.nonhole_descriptors,31);eq(observer.diagnostics.descriptor_failures,0)
eq(#observer.diagnostics.resource_samples,2,'bounded distinct source hashes from existing reads')
eq(#assert(observer:step(world,1.1,1)),0);eq(record_reads,1,'4 Hz')
eq(#assert(observer:step(world,1.25,1)),0);eq(descriptor_reads,40)
records[7].stage=2
local rows=assert(observer:step(world,1.5,1));eq(#rows,1,'observed close')
local row=rows[1]
eq(row.time,1.5);eq(row.stage,2);eq(row.position.x,1);eq(row.unit,901);eq(row.entity,701)
eq(row.record_index,7);eq(row.resource,'HOLE');eq(row.hole,'warrior');eq(row.world,10000)
eq(row.creditor_verified,false);eq(row.responsible_local,nil,'no inferred network owner')
position.x=99;eq(row.position.x,1,'position frozen');position.x=1
eq(#emitted,1);eq(position_reads,1)
records[7].stage=3;eq(#assert(observer:step(world,1.75,1)),0,'positive increase no repeat')
records[7].stage=0;assert(observer:step(world,2,1))
records[7].stage=1;eq(#assert(observer:step(world,2.25,1)),0,'identity dedupe even stage reset')
observer:reset(1);eq(#assert(observer:step(world,3,1)),0,'first already closed ignored')
records[7].stage=0;assert(observer:step(world,3.25,1));records_failure=true
eq(observer:step(world,3.5,1),nil);eq(observer.diagnostics.reason,'RECORD_FAILED')
records[7].stage=1;records_failure=false
eq(#assert(observer:step(world,3.75,1)),0,'read gap re-baselines')
records[7].stage=0;assert(observer:step(world,4,1));throwing=true
eq(observer:step(world,4.25,1),nil);eq(observer.diagnostics.reason,'BUGHOLE_READ_EXCEPTION')
records[7].stage=2;throwing=false
eq(#assert(observer:step(world,4.5,1)),0,'exception re-baselines')
records[7].stage=0;assert(observer:step(world,4.75,1));records[7].unit=902;records[7].stage=1
eq(#assert(observer:step(world,5,1)),0,'unit mismatch no close')
records[7].unit=901;eq(#assert(observer:step(world,5.25,1)),0,'mismatch rereads as baseline')
records[7].stage=0;assert(observer:step(world,5.5,1));records[7].registered=false;records[7].stage=1
eq(#assert(observer:step(world,5.75,1)),0,'unregistered record no close')
records[7].registered=true;eq(#assert(observer:step(world,6,1)),0,'registration baseline')
records[7].stage=0;assert(observer:step(world,6.25,1));records[7].stage=1;list_world=20000
eq(#assert(observer:step(world,6.5,1)),0,'destruction world reset')
records[7].stage=0;assert(observer:step(world,6.75,1));records[7].stage=1
eq(#assert(observer:step(world,7,2)),0,'mission reset')
records[7].stage=0;assert(observer:step(world,7.25,2));records[7].stage=1;position=nil
rows=assert(observer:step(world,7.5,2));eq(#rows,1);eq(rows[1].position.x,1,'live position survives destroyed unit')
eq(observer.diagnostics.position_missing,0)
position={x=1,y=2,z=3};eq(#assert(observer:step(world,7.75,2)),0,'missing position never replayed')
descriptor_count=1025;eq(observer:step(world,8,2),nil,'instance schema bound')
descriptor_count=40;list_failure=true;eq(observer:step(world,8.25,2),nil)
eq(#assert(observer:step(world,8.3,2)),0,'throttled frame is a no-op even after failure')
eq(observer.diagnostics.ready,false,'no-op does not turn failed read into ready')

-- A nonempty native manager with invalid index slots is not the same as
-- successfully parsing non-hole resources. This is the missing distinction
-- in the actual .50 mission diagnostics (183 list entries, zero new reads).
local invalid_source={}
for k,v in pairs(source)do invalid_source[k]=v end
invalid_source.destructibles=function()return{count=3,world=30000,
    pointers={ptr=function(_,o)if o==0 then return nil end;return o/8+1 end},
    indices={i32=function(_,o)return o==4 and -1 or 7 end}}end
local invalid_observer=module.new({world_api=invalid_source})
list_failure=false
assert(invalid_observer:step(world,10,1))
eq(invalid_observer.diagnostics.descriptor_count,3)
eq(invalid_observer.diagnostics.invalid_pointers,1)
eq(invalid_observer.diagnostics.invalid_indices,1)
eq(invalid_observer.diagnostics.cached_descriptors,1)
eq(invalid_observer.diagnostics.nonhole_descriptors,1)
eq(invalid_observer.diagnostics.known_holes,0)

-- Sparse record indices cannot grow reads/bytes with the world's hole count.
-- Budget rotation is not a read failure. A previously read live hole must
-- retain its baseline until its next bounded visit, or sparse worlds can
-- never produce any closure at all.
local sparse_stage=0
local sparse={
    destructibles=function()return{count=80,world=30000,
        pointers={ptr=function(_,o)return o/8+1 end},indices={i32=function(_,o)return(o/4+1)*100 end}}end,
    destructible_descriptor=function(_,p)return{unit=p,entity=p+100,resource='HOLE'}end,
    bug_hole_kind=function()return'warrior'end,
    destruction_records=function(_,_,first,last)return{first=first,last=last}end,
    destruction_record=function(block,offset)return(block.first+offset/12)/100,sparse_stage,true end,
    unit_position=function()return{x=1,y=2,z=3}end,
}
local bounded=module.new({world_api=sparse})
for i=1,5 do
    assert(bounded:step(world,20+i*.25,1))
    eq(bounded.diagnostics.record_reads<=24,true,'sparse read cap')
    eq(bounded.diagnostics.record_bytes<=49152,true,'sparse byte cap')
    eq(bounded.diagnostics.descriptor_reads<=32,true,'descriptor cap')
    eq(bounded.diagnostics.incomplete,true,'sparse gap exposed')
end
sparse_stage=1
local sparse_closed={}
for i=1,4 do
    for _,closed in ipairs(assert(bounded:step(world,21.25+i*.25,1)))do
        assert(not sparse_closed[closed.id],'sparse hole awarded twice')
        sparse_closed[closed.id]=true
    end
    eq(bounded.diagnostics.record_reads<=24,true,'closure read cap')
    eq(bounded.diagnostics.position_reads<=4,true,'closure position cap')
end
local sparse_count=0;for _ in pairs(sparse_closed)do sparse_count=sparse_count+1 end
eq(sparse_count,80,'sparse windows eventually report every observed 0->positive hole')
-- Dense closures may exceed the position budget, but each remains consumed.
local dense_stage=0
sparse.destructibles=function()return{count=12,world=40000,
    pointers={ptr=function(_,o)return o/8+1 end},indices={i32=function(_,o)return o/4+1 end}}end
sparse.destruction_record=function(block,offset)return block.first+offset/12,dense_stage,true end
local geometry_reads=0
sparse.unit_position=function()
    geometry_reads=geometry_reads+1
    return geometry_reads>1 and{x=1,y=2,z=3}or nil
end
bounded:reset(2);assert(bounded:step(world,23,2));dense_stage=1
local dense_rows=assert(bounded:step(world,23.25,2));eq(#dense_rows,12)
eq(bounded.diagnostics.position_reads,4,'position read budget');eq(bounded.diagnostics.skipped_positions,5)
local good_positions=0;for _,r in ipairs(dense_rows)do if r.position then good_positions=good_positions+1 end end
eq(good_positions,7,'cached live positions leave budget for uncached closures')
eq(bounded.diagnostics.reads_bound<=128,true);eq(bounded.diagnostics.bytes_bound<=65536,true)
eq(#assert(bounded:step(world,23.5,2)),0,'budget-skipped positions never replay')
dense_stage=0;assert(bounded:step(world,23.75,2));dense_stage=1
eq(bounded:step(world,25,2),nil,'long poll gap cannot provide recent closure evidence')
eq(#assert(bounded:step(world,25.25,2)),0,'post-gap baseline ignores already closed')

-- No prior valid position must remain unknown, even if the unit becomes
-- readable after the observed close. Such a close must never be replayed.
position=nil;observer:reset(3);list_failure=false;records[7].stage=0
assert(observer:step(world,30,3));records[7].stage=1
local unknown_position=assert(observer:step(world,30.25,3))
eq(#unknown_position,1);eq(unknown_position[1].position,nil,'no invented position')
eq(observer.diagnostics.position_missing,1)
position={x=1,y=2,z=3};eq(#assert(observer:step(world,30.5,3)),0,'late position cannot replay close')

-- Exact stage layout and the level-unit position path under installed .30.3
-- schema (engine and fingerprint exist, destruction API does not).
local pins={};for _,pin in ipairs(upstream.pins)do pins[pin.rva]=pin.hex end
for _,pin in ipairs(world_module.record_pins)do eq(pins[pin[1]],pin[2],'official stage pins')end
pins[0x13E1512]='4181f8007c0100';pins[0xBBA67E]='4181f8007c0100'
for _,pin in ipairs(world_module.record_bound_pins)do eq(pins[pin[1]],pin[2],'observed native record bounds')end
local engine=upstream.engine
local game,exe,destruction=0x180000000,0x140000000,0x200000
local registry,generations,objects,object,poses=0x300000,0x400000,0x500000,0x600000,0x700000
local record_address,record_length,position_invalid=nil,nil,false
local native_view={
    proves=function(at,hex)
        if at==exe+upstream.destruction.levelUnit.method then
            eq(hex,upstream.destruction.levelUnit.methodBytes);return true
        end
        eq(pins[at-game],hex,'verified pin');return true
    end,
    fill=function(block,at,length)record_address,record_length=at,length;return block end,
    pointer=function(at)
        local values={
            [exe+engine.units]=registry,[registry+engine.unitGenerations]=generations,
            [registry+engine.unitObjects]=objects,[objects+901*8]=object,
            [object]=exe+upstream.destruction.levelUnit.vtable,
            [exe+upstream.destruction.levelUnit.vtable+0xE8]=exe+upstream.destruction.levelUnit.method,
            [object+upstream.destruction.levelUnit.sceneGraphOffset+engine.poses]=poses,
        }
        return values[at]
    end,
    u32=function(at)
        if at==registry+engine.unitCount then return 4096 end
        if at==object+engine.unitId then return 901 end
    end,
    read=function(at,size)
        if at==generations+901 then eq(size,1);return '\0'end
        eq(at,poses+engine.translation);eq(size,12)
        if position_invalid then return nil end
        return '\0\0\128\63\0\0\0\64\0\0\64\64'
    end,
}
local native_world={game=game,exe=exe,view=native_view}
local adapter=world_module.create({source=upstream.source,engine=engine})
local block={u32=function(_,at)eq(at,12);return 901 end,
    u8=function(_,at)if at==19 then return 2 end;eq(at,20);return 1 end}
eq(adapter.destruction_records(native_world,{world=destruction},7,9,block),block)
eq(record_address,destruction+upstream.destruction.records+7*12);eq(record_length,36)
local unit,stage,registered=adapter.destruction_record(block,12)
eq(unit,901);eq(stage,2);eq(registered,true)
eq(adapter.destruction_records(native_world,{world=destruction},0,0x17C00,block),nil,'native-record bound')
local at=assert(adapter.unit_position(native_world,901,true));eq(at.x,1);eq(at.y,2);eq(at.z,3)
eq(adapter.unit_position(native_world,901,false),nil,'level graph requires explicit level path')
position_invalid=true;eq(adapter.unit_position(native_world,901,true),nil,'position read failure')
print('bughole observer: 0->positive/baseline/dedupe/4Hz/32-descriptors/identity/gaps/world+mission/actual level position PASS')
