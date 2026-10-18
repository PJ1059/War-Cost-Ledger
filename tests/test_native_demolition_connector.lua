-- Own LuaJIT buffers, injected already-tested drain boundary; no Game access.
local runtime,root=assert(arg[1]),assert(arg[2])
table.insert(package.loaders,2,function(name)
    if name:sub(1,11)=='hd2runtime/'then return assert(loadfile(runtime..'/'..name:sub(12)..'.lua'))end
end)
local win=require('hd2runtime/runtime/windows_ffi');local ffi=win.ffi
local connector=dofile(root..'/src/native-hit-connector.lua')
local function wire(s)return(s:gsub('..',function(p)return string.char(tonumber(p,16))end)):reverse()end
local PEER,EPOCH='F123456789ABCDEF','0000000000000011'
local keep
local function fixture()
    keep=ffi.new('uint8_t[8192]')
    local base=tonumber(ffi.cast('uintptr_t',keep))
    local d=math.floor((base+63)/64)*64
    local function set32(off,n)ffi.cast('uint32_t *',d+off)[0]=n end
    local function setpeer(off,s)ffi.copy(ffi.cast('void *',d+off),wire(s),8)end
    set32(0,32);set32(4,128);setpeer(8,EPOCH);setpeer(16,PEER);set32(24,2)
    local h={native_certified=true,code_base=0x190000000,code_size=4096,
        lifetime={data=base,data_size=8192},addresses={demolition_diagnostic=d,demolition_drain=0x190000100},
        profile={demolition_diagnostic={revision=1,header_bytes=64,record_bytes=128,capacity=32}},
        demolition_output=ffi.new('uint8_t[4096]')}
    local calls=0
    function h.demolition_consumer(at,out,max)
        assert(tonumber(ffi.cast('uintptr_t',at))==d and max==32)
        calls=calls+1
        local n=tonumber(ffi.cast('uint32_t *',d+24)[0])
        for i=0,n-1 do ffi.fill(out+i*128,128);ffi.copy(out+i*128+8,wire(PEER),8)end
        set32(24,0)
        return n
    end
    return h,set32,setpeer,function()return calls end
end
local h,set32,setpeer,calls=fixture()
local result=assert(connector.demolition_snapshot(h,PEER,EPOCH))
assert(#result.records==2 and #result.records[1]==128 and calls()==1)
result=assert(connector.demolition_snapshot(h,PEER,EPOCH))
assert(#result.records==0 and calls()==2,'same batch is not replayed')
h,set32,setpeer,calls=fixture();setpeer(8,'0000000000000012')
local value,why=connector.demolition_snapshot(h,PEER,EPOCH)
assert(not value and why=='DEMOLITION_DIAGNOSTIC_WAITING_EPOCH'and calls()==0)
h,set32,setpeer,calls=fixture();h.lifetime.data_size=32
value,why=connector.demolition_snapshot(h,PEER,EPOCH)
assert(not value and why=='DEMOLITION_DIAGNOSTIC_RANGE_CHANGED'and calls()==0)
h,set32,setpeer,calls=fixture()
local original=h.demolition_consumer
function h.demolition_consumer(...)local n=original(...);setpeer(16,'0123456789ABCDEF');return n end
value,why=connector.demolition_snapshot(h,PEER,EPOCH)
assert(not value and why=='DEMOLITION_DIAGNOSTIC_EPOCH_CHANGED','identity race discards copied rows')
h,set32,setpeer,calls=fixture()
function h.demolition_consumer()return 33 end
value,why=connector.demolition_snapshot(h,PEER,EPOCH)
assert(not value and why=='DEMOLITION_DIAGNOSTIC_DRAIN_INVALID')
print('PASS demolition connector: exact once batch, empty, identity/range/bounds rejection; own memory only')
