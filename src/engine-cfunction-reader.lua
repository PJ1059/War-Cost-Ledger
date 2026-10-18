-- Read-only identities of six exported functions; no member invocation or contract claim.
-- Requires the already-proven world from Runtime event_world.open(), called on Ship.
local b=require('hd2runtime/core/bytes')
local profile=require('hd2runtime/schemas/current')
local bit=require('bit')
local M={source={lua_sha='2C8720C9F446C848436AD993B1A88099D76F0B0B09DF53689719B797C3039CE7',
    lua_file_bytes=469080,jit_version='LuaJIT 2.1.0-alpha',arch='x64',
    exe_sha='F5FEE03DCFDB2E553A4752C283590950AC13316B376D8196AA556FF0400D5F06',
    game_sha='2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E',
    exe_size=60719104,game_size=74727424,ffid_offset=6,c_pointer_offset=24}}
local TARGETS={{'World','set_flow_callback_object'},{'Unit','flow_event'},
    {'Application','flow_callback_context_world'},{'Application','flow_callback_context_unit'},
    {'Application','flow_callback_context_entity'},{'Application','flow_callback_context_level'}}
local Reader={};Reader.__index=Reader
local function finite(v)return type(v)=='number'and v==v and v>-math.huge and v<math.huge end
local function address(v)return finite(v)and v>=65536 and v<=140737488355327 and v%1==0 end
local function copy(v)
    if type(v)~='table'then return v end
    local out={};for k,x in pairs(v)do out[k]=copy(x)end;return out
end
local function output(reason)
    return {version=1,status='unavailable',reason=reason,complete=false,fresh=false,
        identity_ready=false,contract_ready=false,ProfileVerified=false,coverage='unknown',
        shared_dispatcher='unknown',elapsed_ms=0,found=0,resolved=0,functions={},
        profile={lua_sha=M.source.lua_sha,exe_sha=M.source.exe_sha,game_sha=M.source.game_sha,
            jit_version=M.source.jit_version,arch=M.source.arch,gc64=false,ffid_offset=6,c_pointer_offset=24},
        counts={requested=6,found=0,c_functions=0,identified=0,reads=0,bytes=0,
            hash_attempts=0,hash_file_bytes_observed=0,queries=0},
        limits={functions=6,sampling_read_bytes=288,sampling_read_calls=12,budget_ms=2,
            soft_time_limit=true,hash_separate_from_sampling=true}}
end
function M.new(options)
    options=type(options)=='table'and options or{}
    return setmetatable({adapter=rawget(options,'adapter'),env=rawget(options,'env')},Reader)
end

function Reader:collect(world,game,enabled)
    if enabled~=true then return output('DISABLED')end
    if type(world)~='table'or type(game)~='table'or rawget(game,'state')~=3
        or rawget(game,'mission')~=false then return output('WAITING_SHIP')end
    local runtime=rawget(world,'runtime')
    if type(runtime)~='table'or rawget(runtime,'mode')~='live'then return output('WORLD_UNAVAILABLE')end
    if self.result then
        local cached=copy(self.result);cached.status='cached';cached.fresh=false;cached.identity_ready=false
        return cached
    end
    local out=output('NOT_COLLECTED')
    local env=type(self.env)=='table'and self.env or{}
    local globals=rawget(env,'globals')or _G
    local root=type(globals)=='table'and rawget(globals,'stingray')or nil
    local plan={}
    for _,target in ipairs(TARGETS)do
        local row={name=target[1]..'.'..target[2],status='unsupported',reason='MODULE_UNSUPPORTED'}
        out.functions[#out.functions+1]=row
        local module=type(root)=='table'and rawget(root,target[1])or nil
        local fn=type(module)=='table'and rawget(module,target[2])or nil
        if type(fn)=='function'then
            out.counts.found=out.counts.found+1;row.reason='NOT_SAMPLED'
            plan[#plan+1]={row=row,module=module,fn=fn,group=target[1],member=target[2]}
        elseif type(module)=='table'then row.reason='FUNCTION_UNSUPPORTED'end
    end
    local function finish(reason,withhold)
        out.reason=reason;out.complete=reason=='IDENTIFIED';out.fresh=true
        out.found=out.counts.found;out.resolved=withhold and 0 or out.counts.identified
        out.identity_ready=out.complete;out.status=out.complete and'identified'or'partial'
        if withhold then
            for _,row in ipairs(out.functions)do
                if row.status=='identified'then row.status='withheld';row.reason='GLOBAL_IDENTITY_CHANGED'end
                row.module,row.rva,row.hex=nil,nil,nil
            end
        end
        self.result=copy(out);return out
    end
    if out.counts.found==0 then return finish('NO_SUPPORTED_FUNCTIONS')end
    local adapter=self.adapter or runtime
    local exe,game_base=rawget(world,'exe'),rawget(world,'game')
    local function method(name)
        local fn=type(adapter)=='table'and rawget(adapter,name)or nil
        if type(fn)~='function'then error('ADAPTER_UNSUPPORTED',0)end
        return fn
    end
    local jit_table=rawget(env,'jit')or rawget(_G,'jit')
    local ffi=rawget(env,'ffi')
    if not ffi then local ok,value=pcall(require,'ffi');if ok then ffi=value end end
    local function abi()
        if (rawget(env,'jit')or rawget(_G,'jit'))~=jit_table or type(jit_table)~='table'or rawget(jit_table,'arch')~=M.source.arch
            or rawget(jit_table,'version')~=M.source.jit_version then error('LUA_ABI_MISMATCH',0)end
        local abi_fn=type(ffi)=='table'and rawget(ffi,'abi')or nil
        if type(abi_fn)~='function'or abi_fn('64bit')~=true or abi_fn('gc64')~=false then
            error('LUA_ABI_MISMATCH',0)
        end
    end
    local function bases()
        if not address(exe)or not address(game_base)or exe%4096~=0 or game_base%4096~=0
            or rawget(world,'exe')~=exe or rawget(world,'game')~=game_base
            or rawget(world,'runtime')~=runtime or rawget(runtime,'mode')~='live' then error('WORLD_CHANGED',0)end
        if method('address')(method('module')(nil))~=exe
            or method('address')(method('module')('game.dll'))~=game_base then error('WORLD_CHANGED',0)end
    end
    local lua_base
    local ok,why=pcall(function()
        if profile.exe_sha~=M.source.exe_sha or profile.dll_sha~=M.source.game_sha then
            error('BUILD_PROFILE_MISMATCH',0)
        end
        abi();bases()
        local handle=method('module')('lua51.dll')
        if handle==nil then error('LUA_MODULE_UNAVAILABLE',0)end
        lua_base=method('address')(handle)
        if not address(lua_base)then error('LUA_MODULE_UNAVAILABLE',0)end
        out.counts.hash_attempts=1
        local hash=method('module_hash')(handle)
        if type(hash)=='string'then out.hash=hash:upper()end
        if type(hash)~='string'or hash:upper()~=M.source.lua_sha then error('LUA_DLL_MISMATCH',0)end
        out.counts.hash_file_bytes_observed=M.source.lua_file_bytes
        out.ProfileVerified=true
    end)
    if not ok then return finish(type(why)=='string'and why or'PROFILE_ERROR')end
    local debug_table=rawget(_G,'debug');local string_table=rawget(_G,'string')
    local info=rawget(env,'debug_info')or(type(debug_table)=='table'and rawget(debug_table,'getinfo'))
    local format=rawget(env,'format_pointer')or(type(string_table)=='table'and rawget(string_table,'format'))
    local clock=rawget(env,'clock')or rawget(runtime,'precise_time')or os.clock
    local started
    local function tick()
        local now=clock()
        if not finite(now)or(started and now<started)then error('CLOCK_INVALID',0)end
        if not started then started=now end
        local elapsed=(now-started)*1000
        if not finite(elapsed)then error('CLOCK_INVALID',0)end
        out.elapsed_ms=elapsed
        if out.elapsed_ms>=2 then error('TIME_BUDGET',0)end
    end
    local function query(at,n,executable,module_base)
        out.counts.queries=out.counts.queries+1
        local r=method('query')(at)
        if type(r)~='table'or not address(r.base)or not finite(r.size)or r.size<=0
            or r.state~=0x1000 or not finite(r.protect)or bit.band(r.protect,0x100)~=0
            or at<r.base or at+n>r.base+r.size then error('REGION_UNREADABLE',0)end
        local p=bit.band(r.protect,0xff)
        if not(p==2 or p==4 or p==8 or p==0x20 or p==0x40 or p==0x80)then
            error('REGION_UNREADABLE',0)
        end
        if executable and not(p==0x20 or p==0x40 or p==0x80)then error('REGION_NOT_EXECUTABLE',0)end
        if executable and(r.type~=0x1000000 or r.allocation_base~=module_base)then
            error('REGION_NOT_CURRENT_IMAGE',0)
        end
        return r
    end
    local function same_region(a,c)
        for _,k in ipairs({'base','size','state','protect','type','allocation_base'})do
            if a[k]~=c[k]then error('REGION_CHANGED',0)end
        end
    end
    local function read(at,n)
        tick()
        if not address(at)or not address(at+n-1)or out.counts.reads>=12 or out.counts.bytes+n>288 then
            error('READ_BUDGET',0)
        end
        out.counts.reads=out.counts.reads+1;out.counts.bytes=out.counts.bytes+n
        local raw=method('read')(at,n)
        if type(raw)~='string'or#raw~=n then error('READ_FAILED',0)end
        return raw
    end
    local function reference(item)
        if rawget(globals,'stingray')~=root or rawget(root,item.group)~=item.module
            or rawget(item.module,item.member)~=item.fn then error('FUNCTION_REF_CHANGED',0)end
    end
    local all,first_error=out.counts.found==6,nil
    local pin_cache={}
    for _,item in ipairs(plan)do
        local success,error_reason=pcall(function()
            tick();reference(item)
            if type(info)~='function'or type(format)~='function'then error('LUA_INTROSPECTION_UNSUPPORTED',0)end
            local details=info(item.fn,'S')
            if type(details)~='table'or rawget(details,'what')~='C'then error('NOT_C_FUNCTION',0)end
            out.counts.c_functions=out.counts.c_functions+1
            local text=format('%p',item.fn)
            if type(text)~='string'or not text:match('^0x%x+$')then error('GC_IDENTITY_UNSUPPORTED',0)end
            local gc=tonumber(text:sub(3),16)
            if not address(gc)or gc%8~=0 or gc>4294967295 then error('GC32_IDENTITY_UNSUPPORTED',0)end
            local region=query(gc,32,false)
            local header=read(gc,32)
            if header:byte(7)~=1 then error('NON_NORMAL_C_FFID',0)end
            local high=b.u32(header,28)
            if high>0x7fff then error('NATIVE_POINTER_INVALID',0)end
            local native=b.u32(header,24)+high*4294967296
            if not address(native)then error('NATIVE_POINTER_INVALID',0)end
            local module,base,size
            if native>=exe and native+16<=exe+M.source.exe_size then module,base,size='exe',exe,M.source.exe_size
            elseif native>=game_base and native+16<=game_base+M.source.game_size then
                module,base,size='game',game_base,M.source.game_size
            else error('NATIVE_OUTSIDE_PINNED_IMAGES',0)end
            local code_region=query(native,16,true,base)
            local cached_pin=pin_cache[native]
            local pin
            if cached_pin then same_region(cached_pin.region,code_region);pin=cached_pin.raw
            else pin=read(native,16);pin_cache[native]={raw=pin,region=code_region}end
            same_region(region,query(gc,32,false))
            same_region(code_region,query(native,16,true,base))
            reference(item)
            item.row.status='identified';item.row.reason='PREFIX_CANDIDATE_CONTRACT_UNKNOWN'
            item.row.module,item.row.rva,item.row.hex=module,native-base,b.hex(pin)
            out.counts.identified=out.counts.identified+1
            item.native=native
        end)
        if not success then
            all=false;item.row.status='unsupported';item.row.reason=type(error_reason)=='string'and error_reason or'READ_ERROR'
            if not first_error then first_error=item.row.reason end
            if item.row.reason=='TIME_BUDGET'or item.row.reason=='CLOCK_INVALID'then break end
        end
    end
    local stable,changed=pcall(function()
        abi();bases()
        if method('address')(method('module')('lua51.dll'))~=lua_base then error('LUA_MODULE_CHANGED',0)end
        if (rawget(env,'globals')or _G)~=globals or rawget(globals,'stingray')~=root then
            error('ENGINE_ROOT_CHANGED',0)
        end
    end)
    if not stable then
        all=false;out.ProfileVerified=false;first_error=type(changed)=='string'and changed or'IDENTITY_CHANGED'
        return finish(first_error,true)
    end
    for _,item in ipairs(plan)do
        if item.row.status=='identified'then
            local current,ref_error=pcall(reference,item)
            if not current then
                all=false;item.row.status='unsupported';item.row.reason='FUNCTION_REF_CHANGED'
                item.row.module,item.row.rva,item.row.hex=nil,nil,nil;item.native=nil
                out.counts.identified=out.counts.identified-1
                first_error=first_error or'FUNCTION_REF_CHANGED'
            end
        end
    end
    local timed,time_error=pcall(tick)
    if not timed then all=false;first_error=first_error or(type(time_error)=='string'and time_error or'CLOCK_INVALID')end
    local seen,shared={},false
    for _,item in ipairs(plan)do
        if item.native then if seen[item.native]then shared=true end;seen[item.native]=true end
    end
    if out.counts.identified>0 then
        out.shared_dispatcher=shared and'shared_entry_contract_unknown'or'distinct_entries_contract_unknown'
    end
    if all and out.counts.identified==6 then
        return finish('IDENTIFIED')
    end
    return finish(first_error or'BATCH_INCOMPLETE')
end
return M
