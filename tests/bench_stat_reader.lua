-- Synthetic benchmark, never a game entry point. ReadProcessMemory reads our own FFI allocations.
local opts=assert(_BENCH,'benchmark options required')
table.insert(package.loaders,2,function(name)
    if name:sub(1,11)=='hd2runtime/'then
        local path=opts.runtime_root..'/'..name:sub(12)..'.lua'
        return assert(loadfile(path))
    end
    return '\n\tbenchmark has no module '..name
end)
local ffi=require('ffi')
local runtime=require('hd2runtime/runtime/windows_readonly')()
local native_view=require('hd2runtime/runtime/native_view')
local old=require('hd2runtime/runtime/event_world')
local T=require('hd2runtime/domains/event_natives').stats
local new=opts.include_new and assert(dofile(opts.reader))or nil
local u32p,u64p,f32p=ffi.typeof('uint32_t *'),ffi.typeof('uint64_t *'),ffi.typeof('float *')
local function u32(buffer,offset,value)ffi.cast(u32p,buffer+offset)[0]=value end
local function u64(buffer,offset,value)ffi.cast(u64p,buffer+offset)[0]=value end
local function f32(buffer,offset,value)ffi.cast(f32p,buffer+offset)[0]=value end
local function address(buffer)return tonumber(ffi.cast('uintptr_t',buffer))end
local record_capacity,source_blocks,source_entries=64,T.sourceBlocks,T.sourceEntryCount
assert(source_blocks==64 and source_entries==16 and T.sourceStride==0x148)
local keys={T.keys.projectiles_fired,T.keys.dealt_kills,0xC7680A1B,T.keys.received_deaths,0xA0000002}
for index=6,source_entries do keys[index]=0xB0000000+index end
local memory={score_slot=ffi.new('uint8_t[8]'),
    manager=ffi.new('uint8_t[?]',T.recordBase+T.maxPlayers*T.recordStride),
    index=ffi.new('uint8_t[64]'),main=ffi.new('uint8_t[?]',record_capacity*T.entryStride),
    sources=ffi.new('uint8_t[?]',source_blocks*T.sourceStride)}
local player_entity=1234
u64(memory.score_slot,0,address(memory.manager))
u64(memory.manager,T.indexSlots,address(memory.index))
u32(memory.manager,T.indexCapacity,8);u32(memory.manager,T.indexEmpty,0xFFFFFFFF)
u32(memory.manager,T.indexMultiplier,1)
for slot=0,7 do u32(memory.index,slot*8,0xFFFFFFFF)end
u32(memory.index,(player_entity%8)*8,player_entity);u32(memory.index,(player_entity%8)*8+4,0)
local record=T.recordBase
u64(memory.manager,record+T.tableEntries,address(memory.main))
u32(memory.manager,record+T.tableCapacity,record_capacity)
u32(memory.manager,record+T.tableEmpty,0xFFFFFFFF);u32(memory.manager,record+T.tableMultiplier,1)
u64(memory.manager,record+T.sources,address(memory.sources))
for slot=0,record_capacity-1 do u32(memory.main,slot*T.entryStride,0xFFFFFFFF)end
local function entry(buffer,at,key,integer,real,flag)
    u32(buffer,at,key);u32(buffer,at+4,integer);f32(buffer,at+8,real);buffer[at+12]=flag
end
local function main_entry(key,index)
    local slot=key%record_capacity
    while ffi.cast(u32p,memory.main+slot*T.entryStride)[0]~=0xFFFFFFFF do slot=(slot+1)%record_capacity end
    entry(memory.main,slot*T.entryStride,key,5+index,1.25+index,index%2)
end
for index,key in ipairs(keys)do main_entry(key,index-1)end
for index=#keys+1,record_capacity do main_entry(0xC0000000+index,index-1)end
for source=0,source_blocks-1 do
    local base=source*T.sourceStride
    u32(memory.sources,base,source+1);u32(memory.sources,base+4,0xD0000000)
    for index,key in ipairs(keys)do
        entry(memory.sources,base+T.sourceEntries+(index-1)*T.entryStride,
            key,source+index,source*0.125+(index-1)+0.5,(source+index)%2)
    end
end
local counts={calls=0,bytes=0,into_calls=0}
local raw_read,raw_into=runtime.read,runtime.read_into
runtime.read=function(at,size)
    counts.calls=counts.calls+1;counts.bytes=counts.bytes+size
    return raw_read(at,size)
end
runtime.read_into=function(at,size,buffer)
    counts.calls=counts.calls+1;counts.bytes=counts.bytes+size;counts.into_calls=counts.into_calls+1
    return raw_into(at,size,buffer)
end
local view=native_view.new(runtime)
local world={game=address(memory.score_slot)-T.score,view=view,runtime=runtime}
local two={keys[1],keys[2]};local three={keys[1],keys[2],keys[3]}
local four={keys[1],keys[2],keys[3],keys[4]}
local five={keys[1],keys[2],keys[3],keys[4],keys[5]}
local mixed={keys[1],keys[2],keys[3],{key=keys[4],kind='f32'},{key=keys[5],kind='bool'}}
local cases={}
local function add(name,reader,specs,snapshot)
    local block=view.slot()
    cases[#cases+1]={name=name,specs=specs,snapshot=snapshot,
        run=function()
            if snapshot then return reader.snapshot(world,player_entity,block)end
            return reader.read(world,player_entity,specs,block)
        end}
end
local old_adapter={read=old.stat_breakdown}
add('runtime_integer_2_keys',old_adapter,two)
add('runtime_integer_3_keys',old_adapter,three)
add('runtime_integer_4_keys',old_adapter,four)
add('runtime_integer_5_keys',old_adapter,five)
-- The production entity_state reader looks up one avatar through its hash; no enemy table enumeration.
local H=require('hd2runtime/domains/event_natives').health
local avatar=9876
local health_memory={global=ffi.new('uint8_t[8]'),
    manager=ffi.new('uint8_t[?]',H.header+H.headerSize),buckets=ffi.new('uint8_t[1024]'),
    descriptors=ffi.new('uint8_t[8]'),descriptor=ffi.new('uint8_t[?]',H.descriptor.size),
    record=ffi.new('uint8_t[?]',H.stride),ext=ffi.new('uint8_t[?]',H.extStride)}
u64(health_memory.global,0,address(health_memory.manager))
u32(health_memory.manager,H.live,1);u32(health_memory.manager,H.capacity,64)
u32(health_memory.manager,H.hashCapacity,128);u32(health_memory.manager,H.hashEmpty,0xFFFFFFFF)
u32(health_memory.manager,H.hashMultiplier,1)
u64(health_memory.manager,H.buckets,address(health_memory.buckets))
u64(health_memory.manager,H.descriptors,address(health_memory.descriptors))
u64(health_memory.manager,H.records,address(health_memory.record))
u64(health_memory.manager,H.extArray,address(health_memory.ext))
for slot=0,127 do u32(health_memory.buckets,slot*8,0xFFFFFFFF)end
u32(health_memory.buckets,avatar%128*8,avatar);u32(health_memory.buckets,avatar%128*8+4,0)
u64(health_memory.descriptors,0,address(health_memory.descriptor))
u32(health_memory.descriptor,H.descriptor.entity,avatar);u32(health_memory.descriptor,H.descriptor.flags,1)
u32(health_memory.record,H.record.health,75);u32(health_memory.record,H.record.life,0)
u32(health_memory.ext,H.extFields.maxHealth,100)
local health_world={game=address(health_memory.global)-H.global,view=view,runtime=runtime}
cases[#cases+1]={name='runtime_local_avatar_health',health=true,
    run=function()return old.entity_state(health_world,avatar)end}
if new then
    add('native_integer_2_keys',new,two)
    add('native_integer_3_keys',new,three)
    add('native_integer_5_keys',new,five)
    add('native_mixed_5_keys',new,mixed)
    add('native_full_raw_snapshot',new,nil,true)
end
local function validate(result,specs,snapshot,raw,health)
    if health then
        assert(result.health==75 and result.max_health==100 and result.life==0)
        assert(result.descriptor.entity==avatar and result.descriptor.owned==true)
        return
    end
    if raw then
        assert(result.capacity==record_capacity and result.empty==0xFFFFFFFF and result.score_index==0)
        assert(#result.main_bytes==record_capacity*T.entryStride and
            #result.sources_bytes==source_blocks*T.sourceStride,'incomplete binary raw buffers')
        return
    end
    if snapshot then
        assert(result and#result.main==record_capacity and#result.sources==source_blocks,'incomplete raw snapshot')
        for _,source in ipairs(result.sources)do
            assert(#source.entries==source_entries,'raw snapshot lost source entries')
        end
        return
    end
    assert(result and result.totals and result.sources,'reader result unavailable')
    local count=0;for _ in pairs(result.sources)do count=count+1 end
    assert(count==source_blocks,'fixture did not retain all source blocks')
    for index,spec in ipairs(specs)do
        if type(spec)=='number'then
            local expected=5+(index-1)+(source_blocks-1)*source_blocks/2+source_blocks*index
            assert(result.totals[spec]==expected,'wrong integer total for '..spec)
        elseif spec.kind=='f32'then
            local expected=1.25+(index-1)+source_blocks*((index-1)+0.5)
                +0.125*(source_blocks-1)*source_blocks/2
            assert(result.totals[spec.key]==expected,'wrong f32 total')
        elseif spec.kind=='bool'then assert(result.totals[spec.key]==true,'wrong bool total')end
    end
end
local timer=runtime.precise_time
if opts.capture_cost then
    assert(new and opts.capture_dir,'capture benchmark needs the new reader and an owned temporary folder')
    -- Use the production encoder; suppress only its unused logging/event dependencies.
    package.preload['hd2runtime/runtime/log']=function()return{emit=function()end}end
    package.preload['hd2runtime/runtime/events']=function()return{}end
    local codec=require('hd2runtime/runtime/mod_store')
    local function word(value)
        return string.char(value%256,math.floor(value/256)%256,
            math.floor(value/65536)%256,math.floor(value/16777216)%256)
    end
    cases={}
    local formats=opts.capture_format=='both'and{'json','binary'}or{opts.capture_format or'json'}
    for _,format in ipairs(formats)do for _,capacity in ipairs({64,4096})do
        local binary=format=='binary'
        local case={name=(binary and'probe_binary_capture_main_'or'probe_capture_main_')..capacity,
            snapshot=not binary,raw=binary,capture=true,specs=nil,capacity=capacity,format=format}
        local block=view.slot()
        local target=opts.capture_dir..'/capture_'..capacity..(binary and'.bin'or'.json')
        local pending=target..'.tmp'
        case.setup=function()
            record_capacity=case.capacity
            memory.main=ffi.new('uint8_t[?]',record_capacity*T.entryStride)
            u64(memory.manager,record+T.tableEntries,address(memory.main))
            u32(memory.manager,record+T.tableCapacity,record_capacity)
            for slot=0,record_capacity-1 do u32(memory.main,slot*T.entryStride,0xFFFFFFFF)end
            for index,key in ipairs(keys)do main_entry(key,index-1)end
            for index=#keys+1,record_capacity do main_entry(0xC0000000+index,index-1)end
        end
        case.run=function()
            local started=timer()
            local captured
            if binary then captured=assert(new.raw(world,player_entity),'raw capture returned nil')
            else captured=assert(new.snapshot(world,player_entity,block),'snapshot returned nil')end
            local read_finished=timer()
            local result={version='0.3.1',id='0123456789abcdef0123456789abcdef',
                label='automatic-benchmark',time=os.time(),mission=true,build=25480438,
                player_entity=player_entity}
            if binary then
                result.capacity,result.empty,result.score_index=captured.capacity,captured.empty,captured.score_index
                result.game_state,result.game_mode,result.host,result.player_lifecycle=4,'Mission',false,3
                result.avatar=1234;result.position={x=12.5,y=-17,z=100}
            else result.stats=captured end
            local encoded=codec.encode(result)
            local encode_finished=timer()
            local parts,size={encoded},#encoded
            if binary then
                parts={encoded,captured.main_bytes,captured.sources_bytes,'',''}
                local header='HD2STAT1';size=28
                for _,part in ipairs(parts)do header=header..word(#part);size=size+#part end
                table.insert(parts,1,header)
            end
            assert(size<=1048576,'capture exceeded the production 1 MiB limit')
            local output=assert(io.open(pending,'wb'),'could not open temporary capture')
            for _,part in ipairs(parts)do assert(output:write(part),'capture write failed')end
            assert(output:close(),'capture close failed')
            assert(os.rename(pending,target),'capture rename failed')
            local write_finished=timer()
            case.last_stages={snapshot=(read_finished-started)*1e6,
                encode=(encode_finished-read_finished)*1e6,
                file_write=(write_finished-encode_finished)*1e6,
                total=(write_finished-started)*1e6}
            case.last_bytes=size
            -- Check real contents and clean only this case's owned files after timing.
            local verify=assert(io.open(target,'rb'),'renamed capture unavailable')
            local content=verify:read('*a');assert(verify:close())
            local offset=0
            for _,part in ipairs(parts)do
                assert(content:sub(offset+1,offset+#part)==part,'written capture bytes changed')
                offset=offset+#part
            end
            assert(offset==#content,'capture had trailing bytes')
            assert(os.remove(target),'capture cleanup failed')
            assert(not io.open(pending,'rb'),'pending capture leaked')
            if not case.roundtrip_verified then
                local decoded=codec.decode(encoded)
                assert(decoded.id==result.id,'production JSON roundtrip lost capture metadata')
                if binary then
                    assert(content:sub(1,8)=='HD2STAT1'and#parts[1]==28)
                    assert(decoded.capacity==case.capacity and decoded.empty==0xFFFFFFFF)
                    assert(decoded.position.x==12.5 and decoded.host==false)
                else
                    assert(#decoded.stats.main==case.capacity,'JSON lost main entries')
                    assert(#decoded.stats.sources==source_blocks,'JSON lost source blocks')
                    assert(decoded.stats.main[1].f32==captured.main[1].f32,'JSON changed the float slot')
                end
                case.roundtrip_verified=true
            end
            return captured
        end
        cases[#cases+1]=case
    end end
end
local timer_samples={}
for index=1,1000 do local start=timer();timer_samples[index]=(timer()-start)*1e6 end
table.sort(timer_samples)
local report={lua_version=_VERSION,luajit_version=jit.version,jit_enabled=jit.status(),
    iterations=opts.iterations,warmup_iterations=opts.warmup,
    fixture={player_index_capacity=8,main_capacity=record_capacity,main_populated=record_capacity,
        source_blocks=source_blocks,source_entries_each=source_entries,
        source_bytes=source_blocks*T.sourceStride,integer_keys=three},
    timing={clock='QueryPerformanceCounter',timer_pair_median_us=timer_samples[500],
        garbage_collection='default enabled; collected before each measurement case'},cases={}}
if opts.capture_cost then
    report.fixture.capture_main_capacities={64,4096}
    report.fixture.main_capacity=nil;report.fixture.main_populated=nil
    report.capture_limit_bytes=1048576
    report.filesystem={write='io.open wb / io.write / io.close / os.rename',
        fsync=false,cache='warm after preflight and warmup',
        cleanup='each result verified byte-for-byte and removed outside timing'}
end
local function distribution(values)
    local total=0;for _,value in ipairs(values)do total=total+value end
    table.sort(values)
    return{avg_us=total/#values,p50_us=values[math.ceil(#values*0.50)],
        p95_us=values[math.ceil(#values*0.95)],p99_us=values[math.ceil(#values*0.99)],
        max_us=values[#values]}
end
for _,case in ipairs(cases)do
    if case.setup then case.setup()end
    local initial=assert(case.run(),'reader returned nil')
    validate(initial,case.specs,case.snapshot,case.raw,case.health)
    for _=1,opts.warmup do assert(case.run(),'warmup read failed')end
    collectgarbage('collect')
    counts.calls,counts.bytes,counts.into_calls=0,0,0
    local failures_before=view.failures
    local samples,total,last={},0
    local stage_samples={snapshot={},encode={},file_write={}}
    local capture_bytes={}
    for index=1,opts.iterations do
        local start=timer();last=case.run();local elapsed=(timer()-start)*1e6
        if case.capture then
            elapsed=case.last_stages.total
            for name,values in pairs(stage_samples)do values[index]=case.last_stages[name]end
            capture_bytes[index]=case.last_bytes
        end
        assert(last,'measured read failed');samples[index]=elapsed;total=total+elapsed
    end
    assert(view.failures==failures_before,'ReadProcessMemory failed')
    validate(last,case.specs,case.snapshot,case.raw,case.health)
    table.sort(samples)
    local item={name=case.name,avg_us=total/opts.iterations,
        p50_us=samples[math.ceil(opts.iterations*0.50)],p95_us=samples[math.ceil(opts.iterations*0.95)],
        p99_us=samples[math.ceil(opts.iterations*0.99)],max_us=samples[#samples],
        read_calls_per_poll=counts.calls/opts.iterations,read_bytes_per_poll=counts.bytes/opts.iterations,
        read_into_calls_per_poll=counts.into_calls/opts.iterations,read_failures=0}
    if case.capture then
        item.stages={}
        for name,values in pairs(stage_samples)do item.stages[name]=distribution(values)end
        local sizes=distribution(capture_bytes)
        item.capture_bytes={avg=sizes.avg_us,p50=sizes.p50_us,p95=sizes.p95_us,
            p99=sizes.p99_us,max=sizes.max_us}
        item.main_capacity=case.capacity;item.main_populated=case.capacity
        item.entries_per_capture=case.capacity+source_blocks*source_entries
        item.production_json_roundtrip_verified=case.roundtrip_verified
        item.production_json_limit_passed=true
        item.capture_format=case.format
        if case.raw then item.production_binary_roundtrip_verified=case.roundtrip_verified end
    end
    report.cases[#report.cases+1]=item
end
local function json(value)
    if type(value)=='string'then
        return '"'..value:gsub('[%z\1-\31\\"]',function(c)
            return string.format('\\u%04x',c:byte())end)..'"'
    elseif type(value)=='number'then assert(value==value and math.abs(value)<math.huge);return string.format('%.12g',value)
    elseif type(value)=='boolean'then return value and'true'or'false'
    elseif type(value)=='table'then
        local parts={}
        if #value>0 then for _,item in ipairs(value)do parts[#parts+1]=json(item)end
            return '['..table.concat(parts,',')..']'end
        local names={};for key in pairs(value)do names[#names+1]=key end;table.sort(names)
        for _,key in ipairs(names)do parts[#parts+1]=json(key)..':'..json(value[key])end
        return '{'..table.concat(parts,',')..'}'
    end
    error('unsupported JSON type '..type(value))
end
return json(report)
