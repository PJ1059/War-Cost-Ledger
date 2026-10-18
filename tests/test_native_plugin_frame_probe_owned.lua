-- Actual same-DLL LuaJIT/native14B/CAS. Source/world boundary is an explicit
-- injected fixture; fake image addresses never reach CAS/native memory writes.
local source,runtime,root=assert(arg[1]),assert(arg[2]),assert(arg[3])
table.insert(package.loaders,2,function(name)
    if name:sub(1,11)=='hd2runtime/'then return assert(loadfile(runtime..'/'..name:sub(12)..'.lua'))end
end)
local M=assert(loadfile(source))()
local win=require('hd2runtime/runtime/windows_ffi');local ffi=win.ffi
local JSON=require('hd2runtime/runtime/mod_store')
local function file(path)local f=assert(io.open(root..'/'..path,'rb'));local x=f:read('*a');f:close();return x end
local getter=file('dist/hit-game-plugin-entry-window-live-20261013-v1/plugin-entry-window.bin'):sub(1,173)
local saved=file('dist/hit-game-plugin-table-update-live-20261013-v1/plugin-table-update.bin')
local frame=saved:sub(201,267)
local header=file('dist/hit-contact-registration-source-20261013/game-pe-header.bin')
local export=file('dist/game-plugin-export-source-20261013/original-export.bin')
local stores=JSON.decode(file('dist/hit-game-plugin-entry-window-live-20261013-v1/getter-analysis.json')).stores
local lib=win.kernel.GetModuleHandleA('kernel32.dll')
local function proc(n,t)return ffi.cast(win.fn(t),assert(win.kernel.GetProcAddress(lib,n)))end
local alloc=proc('VirtualAlloc','void *(*)(void *,size_t,uint32_t,uint32_t)')
local protect=proc('VirtualProtect','int (*)(void *,size_t,uint32_t,uint32_t *)')
local flush=proc('FlushInstructionCache','int (*)(void *,const void *,size_t)')
local owned=assert(alloc(nil,8192,0x3000,4));local base=tonumber(ffi.cast('uintptr_t',owned))
local function u32(n)if n<0 then n=n+4294967296 end;local o={};for i=1,4 do o[i]=string.char(n%256);n=math.floor(n/256)end;return table.concat(o)end
local function raw(h)return(h:gsub('..',function(x)return string.char(tonumber(x,16))end))end
local original,third=base+0x6C0,base+0x700
local native='\240\72\255\5'..u32(base+4096-(original+8))
    ..raw('f30f5805')..u32(base+4104-(original+16))..'\195'
ffi.copy(ffi.cast('void *',original),native,#native);ffi.copy(ffi.cast('void *',third),'\195',1)
local original_calls=ffi.cast('uint64_t *',base+4096)
ffi.cast('float *',base+4104)[0]=1.25
local slot=ffi.cast('uint64_t *',base+4112);slot[0]=original
local prior=ffi.new('uint32_t[1]');assert(protect(owned,4096,0x20,prior)~=0)
assert(flush(win.kernel.GetCurrentProcess(),owned,4096)~=0)
local game_base=original-M.source.frame_rva
assert(game_base%4096==0)
local exe_base=0x140000000
local context=base+4160
local time,state,reads,queries,cas_calls=100,3,0,0,0
local table_bytes={};for i=1,200 do table_bytes[i]='\0'end
for _,s in ipairs(stores)do
    local q=ffi.new('uint64_t[1]',game_base+s.value_rva)
    local str=ffi.string(q,8)
    for i=1,8 do table_bytes[s.offset_from_return+i]=str:sub(i,i)end
end
local static_table=table.concat(table_bytes)
local slot_address=game_base+M.source.table_rva+0x68
local io={mode='live',address=function(p)return p end,module=function(n)return n==nil and exe_base or n=='game.dll'and game_base or nil end}
io.fingerprint=function()return true end -- Fixture role/build proof only, never a real Game claim.
io.query=function(at)
    queries=queries+1
    return{base=game_base,size=M.source.game_size,state=0x1000,type=0x1000000,
        allocation_base=game_base,protect=at==slot_address and 4 or(at==original or at==game_base+M.source.getter_rva)and 0x20 or 4}
end
io.read=function(at,n)
    reads=reads+1
    if at==game_base and n==4096 then return header end
    if at==game_base+M.source.export_rva and n==74 then return export end
    if at==game_base+M.source.getter_rva and n==173 then return getter end
    if at==original and n==67 then return frame end -- Declared source fixture, not the owned callee17B.
    if at==game_base+M.source.table_rva and n==200 then return static_table end
    if at==slot_address and n==8 then return ffi.string(slot,8)end
    error('outside declared fixture source reads')
end
io.cas=function(package,at,replacement,expected)
    assert(at==slot_address,'no real writes to fake image addresses')
    cas_calls=cas_calls+1;return tonumber(package.cas(slot,replacement,expected))
end
local view={pointer=function(at)assert(at==game_base+0x3326340);reads=reads+1;return context end,
    u32=function(at)assert(at==context+0xAC21C);reads=reads+1;return state end}
local world={runtime=io,view=view,game=game_base,exe=exe_base}
local ship={state=3,mission=false}
local float_type=win.fn('float (*)(float)')
local function invoke(x)return tonumber(ffi.cast(float_type,ffi.cast('void *',slot[0]))(x))end
local inputs={.5,2,3.5};local expected={1.75,3.25,4.75}
for i,x in ipairs(inputs)do assert(invoke(x)==expected[i])end
local probe=M.new({adapter=io,clock=function()return time end})
assert(probe:status().phase=='idle'and probe.native==nil)
local r=probe:start(world,ship);assert(r.phase=='running',r.reason)
for i,x in ipairs(inputs)do assert(invoke(x)==expected[i])end
time=102.1;r=probe:tick(world,ship)
assert(r.phase=='stopped'and r.reason=='WINDOW_ENDED'and r.restored and r.counter==3)
assert(tonumber(slot[0])==original and tonumber(original_calls[0])==6)
for i,x in ipairs(inputs)do assert(invoke(x)==expected[i])end
assert(tonumber(original_calls[0])==9)
local before=reads;probe:tick(nil,nil);probe:status();probe:stop('again');assert(reads==before)
local other=M.new({adapter=io,clock=function()return time end});assert(other:start(world,ship).phase=='running')
assert(tonumber(other.native.cas(slot,third,other.native.wrapper))==other.native.wrapper)
local stopped=other:stop('THIRD_PARTY');assert(stopped.third_party_preserved and not stopped.restored and tonumber(slot[0])==third)
assert(tonumber(ffi.cast(float_type,other.native.wrapper)(.5))==1.75) -- Retained cached entry remains callable.
slot[0]=original
local rejected=M.new({adapter=io,clock=function()return time end});before=reads
local bad=rejected:start(world,{state=4,mission=true});assert(bad.phase=='failed'and rejected.native==nil and reads==before)
assert(not r.payload_ready and not r.engine_dispatch_proven)
JSON.decode(JSON.encode(r));JSON.decode(JSON.encode(stopped));JSON.decode(JSON.encode(bad))
return JSON.encode({status='PASS',cases=1,normal_counter=r.counter,original_calls_after_restore=9,
    float_results=expected,third_party_preserved=stopped.third_party_preserved,mission_refused=true,
    zero_reads_after_stop=true,native_wrapper_bytes=14,native_cas_bytes=9,retained_pages=r.retained_pages,
    actual_luajit=true,actual_owned_native=true,source_boundary='explicit injected saved-PIN/role fixture',
    wall_clock_injected_for_soft_deadline=true,game_accessed=false,installed=false,payload_ready=false,
    counts={source_and_context_reads=reads,queries=queries,cas_calls=cas_calls}})
