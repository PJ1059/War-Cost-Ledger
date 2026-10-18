-- Actual ReadProcessMemory over owned synthetic buffers. No game process access.
local opts = assert(_BENCH)
table.insert(package.loaders, 2, function(name)
    if name:sub(1,11)=='hd2runtime/' then return assert(loadfile(opts.runtime..'/'..name:sub(12)..'.lua')) end
end)
local ffi = require('ffi')
local runtime = require('hd2runtime/runtime/windows_readonly')()
local native_view = require('hd2runtime/runtime/native_view')
local api = require('hd2runtime/runtime/event_world')
local native = require('hd2runtime/domains/event_natives')
local H = native.health
local function address(p) return tonumber(ffi.cast('uintptr_t',p)) end
local function u32(p,o,v) ffi.cast('uint32_t *',p+o)[0]=v end
local function u64(p,o,v) ffi.cast('uint64_t *',p+o)[0]=v end
local calls, bytes = 0, 0
local original_read, original_into = runtime.read, runtime.read_into
runtime.read=function(at,size) calls=calls+1;bytes=bytes+size;return original_read(at,size) end
runtime.read_into=function(at,size,buf) calls=calls+1;bytes=bytes+size;return original_into(at,size,buf) end
local create = assert(dofile(opts.observer))
local results = {}
for _, size in ipairs({128,1024,4096}) do
    local capacity=1;while capacity<size*2 do capacity=capacity*2 end
    -- The fresh-corpse path also reads this known native global. Keep its
    -- pointer in owned, zeroed memory (an absent corpse manager), not past root.
    local memory={root=ffi.new('uint8_t[?]',math.max(8,native.corpses.global-H.global+8)),manager=ffi.new('uint8_t[?]',H.header+H.headerSize),
        buckets=ffi.new('uint8_t[?]',capacity*8), records=ffi.new('uint8_t[?]',size*H.stride),
        pointers=ffi.new('uint8_t[?]',size*8), descriptors=ffi.new('uint8_t[?]',size*H.descriptor.size)}
    u64(memory.root,0,address(memory.manager))
    u32(memory.manager,H.live,size);u32(memory.manager,H.capacity,size)
    u32(memory.manager,H.hashCapacity,capacity);u32(memory.manager,H.hashEmpty,0xFFFFFFFF)
    u32(memory.manager,H.hashMultiplier,1)
    u64(memory.manager,H.buckets,address(memory.buckets));u64(memory.manager,H.records,address(memory.records))
    u64(memory.manager,H.descriptors,address(memory.pointers))
    for i=0,capacity-1 do u32(memory.buckets,i*8,0xFFFFFFFF) end
    for i=0,size-1 do
        local entity=i+1
        u32(memory.buckets,entity*8,entity);u32(memory.buckets,entity*8+4,i)
        u64(memory.pointers,i*8,address(memory.descriptors+i*H.descriptor.size))
        u32(memory.descriptors,i*H.descriptor.size+H.descriptor.entity,entity)
        u32(memory.descriptors,i*H.descriptor.size+H.descriptor.type,0xA40FBDE4)
        u32(memory.descriptors,i*H.descriptor.size+H.descriptor.type+4,0xA1F37BF2)
        u32(memory.records,i*H.stride+H.record.life,0)
    end
    local world={game=address(memory.root)-H.global,view=native_view.new(runtime)}
    local players={{['local']=true,peer='0000000000000011'}}
    local observer=create(api,{health=H},{},function() error('synthetic living actors must never die') end,
        {local_kills=function()return 0 end})
    local timings, sum, max_calls, max_bytes = {}, 0, 0, 0
    for i=1,250+opts.iterations do
        calls,bytes=0,0
        local start=runtime.precise_time()
        observer:poll(world,players,0.1,1)
        local ms=(runtime.precise_time()-start)*1000
        assert(observer.diagnostics.ready, 'observer unavailable: '..tostring(observer.diagnostics.reason)..' size='..size)
        assert(calls<=71,'descriptor reads exceeded 64 plus bounded bulk/header/corpse-global reads: '..calls)
        if i>250 then
            timings[#timings+1]=ms;sum=sum+ms;max_calls=math.max(max_calls,calls);max_bytes=math.max(max_bytes,bytes)
        end
    end
    table.sort(timings)
    results[#results+1]={health_records=size,hash_capacity=capacity,iterations=opts.iterations,
        avg_ms=sum/#timings,p99_ms=timings[math.ceil(#timings*0.99)],max_ms=timings[#timings],
        max_read_calls=max_calls,max_read_bytes=max_bytes,incomplete_polls=observer.diagnostics.incomplete,
        poll_hz=10,limit_ms=2}
end
local pieces={}
for _, r in ipairs(results) do
    local props={};for k,v in pairs(r) do props[#props+1]=string.format('"%s":%.9g',k,v) end
    pieces[#pieces+1]='{'..table.concat(props,',')..'}'
end
return '{"cases":['..table.concat(pieces,',')..'],"failed_reads":0}'
