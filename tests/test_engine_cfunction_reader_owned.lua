-- Same DLL real C closures, real own-process readonly reads; image names are fixtures.
local source,runtime,expected=assert(arg[1]),assert(arg[2]),assert(arg[3])
table.insert(package.loaders,2,function(name)
    if name:sub(1,11)=='hd2runtime/'then return assert(loadfile(runtime..'/'..name:sub(12)..'.lua'))end
end)
local M=assert(loadfile(source))()
local JSON=require('hd2runtime/runtime/mod_store')
local rt=require('hd2runtime/runtime/windows_readonly')()
local ffi=require('ffi')
local actual_jit=jit
local lua_handle,host_handle=assert(rt.module('lua51.dll')),assert(rt.module(nil))
local lua_base,host_base=rt.address(lua_handle),rt.address(host_handle)
local addresses=JSON.decode(expected)
local hash=rt.module_hash(lua_handle) -- actual own loaded DLL; one file hash in fixture host
assert(hash==M.source.lua_sha)
local targets={{'World','set_flow_callback_object'},{'Unit','flow_event'},
    {'Application','flow_callback_context_world'},{'Application','flow_callback_context_unit'},
    {'Application','flow_callback_context_entity'},{'Application','flow_callback_context_level'}}
local lua_calls=0
local lua_function=function()lua_calls=lua_calls+1;return 42 end -- never invoked
local function fail()error('metamethod invoked')end
local meta={__index=fail,__newindex=fail,__tostring=fail,__pairs=fail,__call=fail}
local function plain(v,seen)
    local kind=type(v);assert(kind=='table'or kind=='string'or kind=='number'or kind=='boolean')
    if kind=='number'then assert(v==v and v>-math.huge and v<math.huge)end
    if kind~='table'then return end
    assert(getmetatable(v)==nil);seen=seen or{};assert(not seen[v]);seen[v]=true
    for k,x in pairs(v)do
        assert(type(k)=='string'or type(k)=='number')
        if type(k)=='string'then assert(k~='gc'and k~='address'and k~='object_pointer'and k~='native_pointer')end
        plain(x,seen)
    end
    seen[v]=nil
end
local function fixture(mode)
    local root=setmetatable({},meta)
    for _,name in ipairs({'World','Unit','Application'})do rawset(root,name,setmetatable({},meta))end
    local allowed_gc,allowed_code={},{}
    for i,target in ipairs(targets)do
        local fn=assert(rawget(_G,'owned_fn_'..i))
        rawset(rawget(root,target[1]),target[2],fn)
        allowed_gc[tonumber(string.format('%p',fn):sub(3),16)]=true
        allowed_code[addresses[i]]=true
    end
    allowed_gc[tonumber(string.format('%p',type):sub(3),16)]=true
    local ctx={reads=0,bytes=0,queries=0,hashes=0,modules=0,root=root,mode=mode,allowed_gc=allowed_gc}
    local world={exe=lua_base,game=host_base,runtime=rt}
    local adapter={address=rt.address}
    adapter.module=function(name)
        ctx.modules=ctx.modules+1
        if name==nil then return lua_handle end
        if name=='game.dll'then return host_handle end
        if name=='lua51.dll'and mode=='dll_changed'and ctx.reads>0 then return host_handle end
        return rt.module(name)
    end
    adapter.module_hash=function(handle)
        ctx.hashes=ctx.hashes+1;assert(handle==lua_handle)
        if mode=='hash_error'then error('OWNED_HASH_ERROR')end
        return mode=='hash_bad'and string.rep('0',64)or hash
    end
    adapter.query=function(at)
        ctx.queries=ctx.queries+1
        assert(allowed_gc[at]or allowed_code[at],'query outside declared own function objects/code')
        local r=assert(rt.query(at))
        if mode=='not_executable'and allowed_code[at]then r.protect=4 end
        if mode=='private_code'and allowed_code[at]then r.type=0x20000 end
        if mode=='region_changed'and ctx.reads>=2 then r.protect=r.protect==4 and 2 or 0x40 end
        return r
    end
    adapter.read=function(at,n)
        assert((n==32 and allowed_gc[at])or(n==16 and allowed_code[at]),'read outside declared owned ranges')
        ctx.reads=ctx.reads+1;ctx.bytes=ctx.bytes+n
        local raw=assert(rt.read(at,n))
        if mode=='ref_changed'and ctx.reads==1 then rawset(root.World,'set_flow_callback_object',lua_function)end
        if mode=='abi_changed'and ctx.reads==1 then ctx.env.jit.version='changed'end
        if mode=='short_read'and n==16 then return raw:sub(1,15)end
        return raw
    end
    local env={globals={stingray=root},jit={version=actual_jit.version,arch=actual_jit.arch},ffi=ffi,
        clock=function()return 0 end}
    ctx.env=env;ctx.world=world;ctx.adapter=adapter
    ctx.reader=M.new({adapter=adapter,env=env})
    return ctx
end
local passed,evidence={},{}
local function test(name,fn)fn();passed[#passed+1]=name end
local ship={state=3,mission=false}
local function read(c)return c.reader:collect(c.world,ship,true)end
local function withheld(r)
    assert(not r.complete and not r.identity_ready and r.resolved==0 and not r.contract_ready)
    for _,row in ipairs(r.functions)do assert(row.rva==nil and row.module==nil and row.hex==nil)end
    plain(r);JSON.decode(JSON.encode(r))
end
local function partial(r,n)
    assert(not r.complete and not r.identity_ready and not r.contract_ready and r.resolved==n)
    local count=0
    for _,row in ipairs(r.functions)do
        if row.status=='identified'then assert(row.module and row.rva and row.hex);count=count+1 end
    end
    assert(count==n);plain(r);JSON.decode(JSON.encode(r))
end

test('disabled mission and missing world do zero IO',function()
    local c=fixture()
    assert(c.reader:collect(c.world,ship,false).reason=='DISABLED')
    assert(c.reader:collect(c.world,{state=4,mission=true},true).reason=='WAITING_SHIP')
    assert(c.reader:collect(nil,ship,true).reason=='WAITING_SHIP')
    assert(c.reads==0 and c.hashes==0 and c.modules==0 and c.queries==0)
end)
test('nil raw root stops before module lookup or file hash',function()
    local c=fixture();c.env.globals.stingray=nil
    local r=read(c);assert(r.reason=='NO_SUPPORTED_FUNCTIONS'and r.found==0)
    assert(c.modules==0 and c.hashes==0 and c.reads==0);withheld(r)
end)
test('six real C closure API addresses via actual readonly own process',function()
    local c=fixture();local r=read(c)
    assert(r.complete and r.identity_ready and r.ProfileVerified and not r.contract_ready)
    assert(r.found==6 and r.resolved==6 and r.hash==hash and c.hashes==1)
    assert(r.counts.reads==12 and r.counts.bytes==288 and c.reads==12 and c.bytes==288)
    for i,row in ipairs(r.functions)do
        assert(row.module=='exe'and row.rva==addresses[i]-lua_base and#row.hex==32)
        assert(row.reason=='PREFIX_CANDIDATE_CONTRACT_UNKNOWN')
    end
    plain(r);local decoded=JSON.decode(JSON.encode(r));assert(decoded.resolved==6)
    evidence.real_readonly=decoded
    local reads,modules=c.reads,c.modules
    r.functions[1].rva=0
    local cached=read(c)
    assert(cached.status=='cached'and not cached.fresh and not cached.identity_ready)
    assert(cached.functions[1].rva==addresses[1]-lua_base and c.reads==reads and c.modules==modules and c.hashes==1)
end)
test('Lua and fast builtin are refused without member invocation',function()
    for _,value in ipairs({lua_function,type})do
        local c=fixture();rawset(c.root.World,'set_flow_callback_object',value)
        local r=read(c);partial(r,5)
        assert(r.functions[1].reason==(value==type and'NON_NORMAL_C_FFID'or'NOT_C_FUNCTION'))
    end
    assert(lua_calls==0)
end)
test('fixed counted C callback is inspected and never executed',function()
    local c=fixture();local fn=assert(owned_callback)
    c.allowed_gc[tonumber(string.format('%p',fn):sub(3),16)]=true
    for _,target in ipairs(targets)do rawset(rawget(c.root,target[1]),target[2],fn)end
    local r=read(c);withheld(r)
    assert(r.counts.c_functions==6 and r.counts.reads==6 and r.counts.bytes==192)
end)
test('DLL hash mismatch and failure are latched without sampling',function()
    for _,mode in ipairs({'hash_bad','hash_error'})do
        local c=fixture(mode);local r=read(c);withheld(r)
        assert(not r.ProfileVerified and c.hashes==1 and c.reads==0)
        read(c);assert(c.hashes==1 and c.reads==0)
    end
end)
test('ABI mismatch is rejected before hash and reads',function()
    local c=fixture();c.env.jit.arch='x86';withheld(read(c));assert(c.hashes==0 and c.reads==0)
    c=fixture();c.env.ffi={abi=function(name)return true end};withheld(read(c));assert(c.hashes==0)
end)
test('per-function failures retain independent evidence while global changes withhold',function()
    for _,mode in ipairs({'not_executable','private_code','region_changed','short_read',
        'ref_changed','dll_changed','abi_changed'})do
        local c=fixture(mode);local r=read(c)
        if mode=='ref_changed'or mode=='region_changed'then partial(r,5)
        else withheld(r)end
        assert(c.hashes==1 and c.bytes<=288 and c.reads<=12)
        if mode=='dll_changed'or mode=='abi_changed'then assert(not r.ProfileVerified)end
    end
end)
test('partial missing function retains five independently verified identities',function()
    local c=fixture();rawset(c.root.Application,'flow_callback_context_level',nil)
    local r=read(c);partial(r,5);assert(r.found==5 and r.counts.identified==5)
end)
test('soft sampling clock yields explicit partial within hard byte limits',function()
    local c=fixture();local n=0
    c.env.clock=function()n=n+1;return n<=3 and 0 or .003 end
    local r=read(c);partial(r,1);assert(r.reason=='TIME_BUDGET'and c.bytes<=288)
    evidence.time_partial=r
    c=fixture();c.env.clock=function()error('OWNED_CLOCK_ERROR')end
    withheld(read(c));assert(c.reads==0)
    c=fixture();local sample=0
    c.env.clock=function()sample=sample+1;return sample==1 and 0 or 1e308 end
    local invalid=read(c);withheld(invalid);assert(invalid.reason=='CLOCK_INVALID'and invalid.elapsed_ms==0)
end)
test('shared C entry reads its candidate prefix once and remains unknown',function()
    local c=fixture()
    for _,target in ipairs(targets)do rawset(rawget(c.root,target[1]),target[2],owned_fn_1)end
    local r=read(c);assert(r.complete and r.shared_dispatcher=='shared_entry_contract_unknown')
    assert(r.counts.bytes==208 and r.counts.reads==7 and not r.contract_ready)
    evidence.shared=r
end)
test('production constructor rejects own fixture image bases',function()
    local c=fixture();local reader=M.new()
    rawset(_G,'stingray',c.root)
    local r=reader:collect(c.world,ship,true);withheld(r)
    assert(r.reason=='WORLD_CHANGED'and r.counts.hash_attempts==0)
    rawset(_G,'stingray',nil)
end)
test('real precise clock smoke has finite bounded outcome',function()
    local c=fixture();c.env.clock=rt.precise_time
    local r=read(c);assert(r.elapsed_ms>=0 and r.elapsed_ms<math.huge and r.counts.bytes<=288)
    assert(r.reason=='IDENTIFIED'or r.reason=='TIME_BUDGET');plain(r)
    evidence.real_clock=r
end)
return JSON.encode({status='PASS',cases=passed,count=#passed,actual_module_hash=hash,
    fixture='Own LuaState functions and real windows_readonly reads/query/hash; exe/game names are explicit image fixtures',
    game_process_reads=0,engine_member_calls=0,lua_function_calls=lua_calls,contract_ready=false,evidence=evidence})
