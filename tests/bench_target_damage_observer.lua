-- Real ReadProcessMemory of buffers owned by this process. No game access.
local opts=assert(_BENCH)
table.insert(package.loaders,2,function(name)
    if name:sub(1,11)=='hd2runtime/'then return assert(loadfile(opts.runtime..'/'..name:sub(12)..'.lua'))end
end)
local ffi=require('ffi')
local runtime=require('hd2runtime/runtime/windows_readonly')()
local view=require('hd2runtime/runtime/native_view').new(runtime)
local api=require('hd2runtime/runtime/event_world')
local N=require('hd2runtime/domains/event_natives')
local H,WI,E=N.health,N.wielder,N.engine
local b=require('hd2runtime/core/bytes')
local create,trace,resolve=dofile(opts.observer),dofile(opts.trace),dofile(opts.resolver)
local function addr(p)return tonumber(ffi.cast('uintptr_t',p))end
local function u32(p,o,v)ffi.cast('uint32_t *',p+o)[0]=v end
local function u64(p,o,v)ffi.cast('uint64_t *',p+o)[0]=v end
local read_calls,read_bytes=0,0
local original_read,original_into=runtime.read,runtime.read_into
runtime.read=function(at,size)read_calls=read_calls+1;read_bytes=read_bytes+size;return original_read(at,size)end
runtime.read_into=function(at,size,buf)read_calls=read_calls+1;read_bytes=read_bytes+size;return original_into(at,size,buf)end
local rows,context_rows={},{}
for _,size in ipairs({128,1024,4096})do
    local cap=1;while cap<size*2 do cap=cap*2 end
    local m={game=ffi.new('uint8_t[?]',math.max(H.global,WI.entities,N.corpses.global)+8),exe=ffi.new('uint8_t[8]'),
        health=ffi.new('uint8_t[?]',H.header+H.headerSize),records=ffi.new('uint8_t[?]',size*H.stride),
        descriptors=ffi.new('uint8_t[?]',size*H.descriptor.size),pointers=ffi.new('uint8_t[?]',size*8),
        buckets=ffi.new('uint8_t[?]',cap*8),ext=ffi.new('uint8_t[?]',size*H.extStride),
        entity_manager=ffi.new('uint8_t[?]',WI.descriptors+WI.descriptorStride),
        generation_manager=ffi.new('uint8_t[144]'),generations=ffi.new('uint8_t[256]'),owner_hash=ffi.new('uint8_t[?]',1024*8)}
    local owner=201
    u64(m.game,H.global,addr(m.health));u64(m.game,WI.entities,addr(m.entity_manager))
    u64(m.exe,0,addr(m.generation_manager));u32(m.generation_manager,E.generationSize,256)
    u64(m.generation_manager,E.generations,addr(m.generations))
    u32(m.health,H.live,size);u32(m.health,H.capacity,size);u32(m.health,H.hashCapacity,cap)
    u32(m.health,H.hashEmpty,0xFFFFFFFF);u32(m.health,H.hashMultiplier,1)
    u64(m.health,H.buckets,addr(m.buckets));u64(m.health,H.records,addr(m.records))
    u64(m.health,H.descriptors,addr(m.pointers));u64(m.health,H.extArray,addr(m.ext))
    for i=0,cap-1 do u32(m.buckets,i*8,0xFFFFFFFF)end
    for i=0,1023 do u32(m.owner_hash,i*8,0xFFFFFFFF)end
    u64(m.entity_manager,WI.entityMap,addr(m.owner_hash));u32(m.entity_manager,WI.entityMap+8,1024)
    u32(m.entity_manager,WI.entityMap+12,0xFFFFFFFF);u32(m.entity_manager,WI.entityMap+16,1)
    u32(m.owner_hash,owner*8,owner);u32(m.owner_hash,owner*8+4,0)
    u32(m.entity_manager,WI.descriptors,0x6F0B5C5F);u32(m.entity_manager,WI.descriptors+4,0xA8CFFB31)
    u32(m.entity_manager,WI.descriptors+WI.descriptorEntity,owner)
    for _,pin in ipairs({{0x923C24,'45896740'},{0x920D5F,'8b4640'}})do
        local raw=b.unhex(pin[2]);ffi.copy(m.game+pin[1],raw,#raw)
    end
    for i=0,size-1 do
        local entity=i+1000
        local slot=entity%cap
        u32(m.buckets,slot*8,entity);u32(m.buckets,slot*8+4,i)
        u64(m.pointers,i*8,addr(m.descriptors+i*H.descriptor.size))
        u32(m.descriptors,i*H.descriptor.size+H.descriptor.entity,entity)
        u32(m.descriptors,i*H.descriptor.size+H.descriptor.unit,entity)
        u32(m.descriptors,i*H.descriptor.size+H.descriptor.type,0xA40FBDE4)
        u32(m.descriptors,i*H.descriptor.size+H.descriptor.type+4,0xA1F37BF2)
        u32(m.records,i*H.stride+H.record.health,100000)
        u32(m.records,i*H.stride+H.record.lastOwner,owner)
        u32(m.records,i*H.stride+H.record.lastCreditor,0x11)
    end
    local world={game=addr(m.game),exe=addr(m.exe)-E.entities,view=view}
    local observer=create(api,N,{['A1F37BF2A40FBDE4']={kill=true}},function()error('living target must not die')end,
        {local_kills=function()return 0 end,damage_attribution=trace(),source_types={['A8CFFB316F0B5C5F']={}}})
    local times,sum,peak_calls,peak_bytes={},0,0,0
    for i=1,100+opts.iterations do
        if i>100 then
            for target=0,7 do
                u32(m.records,target*H.stride+H.record.health,100000-i)
                observer:contact({verified=true,local_player=true,direct=true,attack='projectile',
                    result='penetration',target=target+1000,source=owner,owner=42})
            end
        end
        read_calls,read_bytes=0,0
        local start=runtime.precise_time()
        observer:poll(world,{{['local']=true,peer='0000000000000011'}},.1,1)
        local elapsed=(runtime.precise_time()-start)*1000
        assert(observer.diagnostics.ready,'observer failed')
        assert(observer.diagnostics.source_reads<=512 and observer.diagnostics.source_bytes<=32768)
        if i>100 then
            times[#times+1]=elapsed;sum=sum+elapsed
            peak_calls,peak_bytes=math.max(peak_calls,read_calls),math.max(peak_bytes,read_bytes)
        end
    end
    table.sort(times)
    rows[#rows+1]=string.format('{"health_records":%d,"iterations":%d,"avg_ms":%.9g,"p99_ms":%.9g,"max_ms":%.9g,"max_all_read_calls":%d,"max_all_read_bytes":%d,"source_reads_peak":%d,"source_bytes_peak":%d}',
        size,#times,sum/#times,times[math.ceil(#times*.99)],times[#times],peak_calls,peak_bytes,
        observer.diagnostics.source_reads_peak or 0,observer.diagnostics.source_bytes_peak or 0)
    -- A burst of 16 first-contact shared fragments, with no weapon owner in
    -- Health, exercises the actual resolver and the bounded position callback.
    -- Position reads use this process's own buffer, never the game process.
    local position_buffer=ffi.new('uint8_t[?]',size*12)
    local position_calls,deaths,mapped,kills=0,0,0,0
    local resolver=resolve({damage_info={['189']={candidates={'A8CFFB316F0B5C5F','4CE9EAB785A79B7B'},
        shared=true,unresolved=true}}})
    for i=0,15 do
        u32(m.records,i*H.stride+H.record.life,0)
        u32(m.records,i*H.stride+H.record.health,100)
        u32(m.records,i*H.stride+H.record.lastOwner,42)
    end
    local context_observer=create(api,N,{['A1F37BF2A40FBDE4']={kill=true}},function(event)
        deaths=deaths+1
        if event.damage_source and event.damage_source.type=='A8CFFB316F0B5C5F'then mapped=mapped+1 end
    end,{local_kills=function()return kills end,damage_attribution=trace(),damage_resolver=resolver,
        source_types={['A8CFFB316F0B5C5F']={}},unit_position=function(_,unit)
            position_calls=position_calls+1
            local raw=runtime.read(addr(position_buffer)+(unit-1000)*12,12)
            return raw and {x=b.value(raw,0,'f32'),y=b.value(raw,4,'f32'),z=b.value(raw,8,'f32')}
        end})
    for _=1,100 do context_observer:poll(world,{{['local']=true,peer='0000000000000011'}},.1,1)end
    for _=1,64 do assert(context_observer:explosion({local_player=true,source_type='A8CFFB316F0B5C5F',
        owner=42,position={x=0,y=0,z=0},radius=6}))end
    for i=0,15 do
        u32(m.records,i*H.stride+H.record.health,0);u32(m.records,i*H.stride+H.record.life,2)
        context_observer:contact({verified=true,local_player=true,direct=true,attack='projectile',
            result='penetration',target=i+1000,source=42,owner=42,damage_info_id=189,count=0,attribution_only=true})
    end
    kills=16
    local polls,first_deaths,first_mapped=0,0,0
    local max_ms,total_ms,max_calls,max_bytes,max_sources,max_source_bytes,max_positions=0,0,0,0,0,0,0
    repeat
        polls=polls+1
        read_calls,read_bytes=0,0
        local before_positions=position_calls
        local start=runtime.precise_time()
        context_observer:poll(world,{{['local']=true,peer='0000000000000011'}},.1,1)
        local elapsed=(runtime.precise_time()-start)*1000
        if polls==1 then first_deaths,first_mapped=deaths,mapped end
        max_ms,total_ms=math.max(max_ms,elapsed),total_ms+elapsed
        max_calls,max_bytes=math.max(max_calls,read_calls),math.max(max_bytes,read_bytes)
        max_sources=math.max(max_sources,context_observer.diagnostics.source_reads)
        max_source_bytes=math.max(max_source_bytes,context_observer.diagnostics.source_bytes)
        max_positions=math.max(max_positions,position_calls-before_positions)
        assert(context_observer.diagnostics.source_reads<=512 and context_observer.diagnostics.source_bytes<=32768)
        assert(position_calls-before_positions<=64,'at most one position read per target under the shared 64-target budget')
        assert(deaths<=16,'deferred source enrichment must not duplicate deaths')
    until deaths==16 or polls>=6
    assert(deaths==16 and mapped==16,'every shared fragment must resolve within the bounded source retry: deaths='..deaths..' mapped='..mapped..' size='..size)
    context_rows[#context_rows+1]=string.format('{"health_records":%d,"death_burst":16,"mapped":%d,"position_calls":%d,"cached_blasts":%d,"poll_ms":%.9g,"all_read_calls":%d,"all_read_bytes":%d,"source_reads":%d,"source_bytes":%d,"polls":%d,"first_poll_deaths":%d,"first_poll_mapped":%d,"total_poll_ms":%.9g,"max_position_calls_per_poll":%d}',
        size,mapped,position_calls,resolver.diagnostics.explosions,max_ms,max_calls,max_bytes,
        max_sources,max_source_bytes,polls,first_deaths,first_mapped,total_ms,max_positions)
end
return '{"cases":['..table.concat(rows,',')..'],"shared_fragment_context_cases":['..table.concat(context_rows,',')..'],"failed_reads":0}'
