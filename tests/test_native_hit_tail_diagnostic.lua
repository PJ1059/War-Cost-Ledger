-- Read-only owned-arena fixture; no Windows API, Game or native code.
local runtime,root=assert(arg[1]),assert(arg[2])
table.insert(package.loaders,2,function(name)
    if name:sub(1,11)=='hd2runtime/'then return assert(loadfile(runtime..'/'..name:sub(12)..'.lua'))end
end)
local b=require('hd2runtime/core/bytes')
local memory,reads,after_read
local BASE,ARENA,ROWS=0x300000000,0x300018040,0x300018080
local PEER,EPOCH='06464E240E0D372A','000000000000000E'
local function wire(s)return(s:gsub('..',function(p)return string.char(tonumber(p,16))end)):reverse()end
local function u32(n)return b.encode(n,'u32')end
local function qword(n)return u32(n%4294967296)..u32(math.floor(n/4294967296))end
local function write(at,raw)local offset=at-BASE;memory=memory:sub(1,offset)..raw..memory:sub(offset+#raw+1)end
package.preload['hd2runtime/runtime/windows_ffi']=function()
    return{fn=function(s)return s end,ffi={cast=function(_,at)return at end,string=function(at,n)
        assert(type(at)=='number'and at>=BASE and at+n<=BASE+#memory,'owned range only')
        reads[#reads+1]={at,n};local raw=memory:sub(at-BASE+1,at-BASE+n)
        if after_read then after_read(at,n)end
        return raw
    end}}
end
local connector=assert(loadfile(root..'/src/native-hit-connector.lua'))()
local function fixture(claimed,mask)
    memory,reads,after_read=string.rep('\0',128*1024),{},nil
    write(ARENA,u32(32)..u32(640)..wire(EPOCH)..wire(PEER))
    write(ARENA+48,qword(ROWS));write(ARENA+60,u32(2))
    write(ROWS+128,qword(20)..qword(2)..u32(claimed)..u32(mask)..wire(EPOCH))
    for index=0,15 do
        local raw=qword(index+1)..wire(EPOCH)..wire(PEER)..string.rep('\0',36)..u32(index%2==0 and 3 or 4)..string.rep('\0',32)
        assert(#raw==96);write(ROWS+index*640+256,raw)
    end
    return{native_certified=true,arena=ARENA,lifetime={data=BASE,data_size=#memory},
        profile={tail_diagnostic={revision=1,head_offset=128,head_bytes=32,scratch_offset=160,
            record_offset=256,record_bytes=96,capacity=16,alt_tag=3,true_tag=4}}}
end
local h=fixture(16,65535)
local value=assert(connector.diagnostic_snapshot(h,PEER,EPOCH))
assert(value.alt_seen=='0000000000000014'and value.true_seen=='0000000000000002'and#value.records==16)
assert(#reads==20 and value.records[1].tag==3 and value.records[16].tag==4)
local bytes=0;for _,r in ipairs(reads)do bytes=bytes+r[2]end;assert(bytes==1728)
local original=memory;assert(connector.diagnostic_snapshot(h,PEER,EPOCH));assert(memory==original,'never changes ordinary or diagnostic data')

h=fixture(2,1)
value=assert(connector.diagnostic_snapshot(h,PEER,EPOCH))
assert(#value.records==1 and#reads==5,'uncommitted slot not read')
for _,r in ipairs(reads)do assert(r[1]~=ROWS+640+256)end

h=fixture(1,1)
after_read=function(at,n)if at==ROWS+256 then write(ARENA+60,u32(4))end end
local v,why=connector.diagnostic_snapshot(h,PEER,EPOCH)
assert(v==nil and why=='TAIL_DIAGNOSTIC_CHANGED_DURING_READ','configure race rejects sample')

h=fixture(1,2)
v,why=connector.diagnostic_snapshot(h,PEER,EPOCH)
assert(v==nil and why=='TAIL_DIAGNOSTIC_MASK_CHANGED'and#reads==2)
h=fixture(1,1)
write(ARENA+16,wire('1111111111111111'))
v,why=connector.diagnostic_snapshot(h,PEER,EPOCH)
assert(v==nil and why=='TAIL_DIAGNOSTIC_IDENTITY_CHANGED'and#reads==1)
h=fixture(1,1)
h.lifetime.data_size=64
v,why=connector.diagnostic_snapshot(h,PEER,EPOCH)
assert(v==nil and why=='TAIL_DIAGNOSTIC_RANGE_CHANGED'and#reads==0)
print('PASS tail diagnostic read: 16/1728B bound; uncommitted ignored; reset/invalid/foreign rejected; no mutations')
