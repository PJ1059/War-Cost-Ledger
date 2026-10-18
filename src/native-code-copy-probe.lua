-- Explicit one-shot, two-second code-copy smoke preparation. Never starts on import/new.
-- Integration must call stop on disable/cancel/error/unload; tick drives the soft deadline.
-- Owned code, metadata, table and counters are retained until process exit; never freed/unregistered.
local b=require('hd2runtime/core/bytes')
local schema=require('hd2runtime/schemas/current')
local fingerprint=require('hd2runtime/core/fingerprint')
local bit=require('bit')
-- build embeds (function() <native-code-copy-profile.lua> end)() here.
local P=__NATIVE_CODE_COPY_PROFILE__
-- Two fixed profiles only. The three-region shipped profile keeps its original
-- limits; the six-region profile compares all additional code and metadata.
local PROFILE={fields=1443,RF=19,chains=16,unwind=492,code=27185,metadata=720,bytes=65536,reads=64}
if P.version==2 then
    assert(P.allocation_bytes==0xD000 and P.code_page_bytes==0xB000
        and P.unwind_offset==0xB000 and P.table_offset==0xB400 and P.counter_offset==0xC000
        and P.field_count==1574 and P.RF_count==28 and P.chain_count==22 and P.unwind_bytes==732
        and P.full_code_bytes==29824 and P.full_metadata_bytes==1068
        and P.read_budget_bytes==73728 and P.read_budget_calls==64,'CODE_COPY_SIX_PROFILE_CONTRACT')
    PROFILE={fields=1574,RF=28,chains=22,unwind=732,code=29824,metadata=1068,bytes=73728,reads=64}
else assert(P.version==1,'CODE_COPY_PROFILE_VERSION')end
local M={source={exe_sha='F5FEE03DCFDB2E553A4752C283590950AC13316B376D8196AA556FF0400D5F06',
    dll_sha='2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E',
    game_size=0x4744000,exe_size=0x39E8000,export_rva=0x39D4000,getter_rva=0x4EEAD0,
    frame_rva=0x4EE6C0,table_rva=0x37CEB10,slot_offset=0x68,state_rva=0x3326340,state_offset=0xAC21C}}
local GETTER='85c90f85a2000000488d0581f6ffff48890582002e03488d05d3fbffff48890584002e03488d0515fcffff4889058e002e03488d0547fcffff48890588002e03488d05c9fcffff48890582002e03488d05cbfcffff48890584002e03488d059dfeffff4889058e002e03488d056fffffff48890588002e03488d0541fbffff48890552002e03488d0543fbffff488905c4ff2d03488d0545fbffff488905beff2d03488d0597ff2d03c333c0c3'
local EXPORT='00000000ffffffff0000000028409d0301000000010000000100000042409d0346409d0340409d0367616d652e646c6c006765745f706c7567696e5f617069000000d0ea4e0031409d03'
local STORES={{0x58,0x4EE160},{0x68,0x4EE6C0},{0x80,0x4EE710},{0x88,0x4EE750},
    {0x90,0x4EE7E0},{0xA0,0x4EE7F0},{0xB8,0x4EE9D0},{0xC0,0x4EEAB0},
    {0x98,0x4EE690},{0x18,0x4EE6A0},{0x20,0x4EE6B0}}
local Controller={};Controller.__index=Controller
local api_cache,material_cache
local LIFE='HD2LedgerCodeCopyProbeLifetimeV1'
local function finite(v)return type(v)=='number'and v==v and v>-math.huge and v<math.huge end
local function address(v)return finite(v)and v>=65536 and v<140737488355328 and v%1==0 end
local function pointer(v)return address(v)and v%8==0 end
local function copy(v)if type(v)~='table'then return v end;local x={};for k,a in pairs(v)do x[k]=copy(a)end;return x end
local function encode(v,width,signed)
    assert(finite(v)and v%1==0,'CODE_COPY_INTEGER')
    if signed then assert(v>=-2^(width*8-1)and v<2^(width*8-1),'CODE_COPY_DISPLACEMENT_OVERFLOW')
    else assert(v>=0 and v<2^(width*8),'CODE_COPY_RVA32_OVERFLOW')end
    if width==1 then return string.char(v%256)end
    assert(width==4,'CODE_COPY_FIELD_WIDTH');return b.encode(v<0 and v+4294967296 or v,'u32')
end
local function qword(v)return b.encode(v%4294967296,'u32')..b.encode(math.floor(v/4294967296),'u32')end
local function material()
    if material_cache then return material_cache end
    local x={regions={},metadata={},unwind=b.unhex(P.unwind_hex),getter=b.unhex(GETTER),export=b.unhex(EXPORT)}
    for i,r in ipairs(P.regions)do x.regions[i]=b.unhex(r.hex);assert(#x.regions[i]==r.length,'CODE_COPY_PROFILE_SIZE')end
    for i,r in ipairs(P.source_metadata)do x.metadata[i]=b.unhex(r.hex);assert(#x.metadata[i]==r.length,'CODE_COPY_METADATA_SIZE')end
    assert(#P.fields==PROFILE.fields and#P.runtime_functions==PROFILE.RF
        and#P.chains==PROFILE.chains and#x.unwind==PROFILE.unwind,'CODE_COPY_PROFILE_COUNTS')
    material_cache=x;return x
end
local function patch(raw,fields)
    table.sort(fields,function(a,c)return a[1]<c[1]end)
    local out,cursor={},1
    for _,f in ipairs(fields)do
        assert(f[1]>=cursor-1 and f[1]+#f[2]<=#raw,'CODE_COPY_PATCH_RANGE')
        out[#out+1]=raw:sub(cursor,f[1]);out[#out+1]=f[2];cursor=f[1]+#f[2]+1
    end
    out[#out+1]=raw:sub(cursor);local result=table.concat(out)
    assert(#result==#raw,'CODE_COPY_SIZE_CHANGED');return result
end
-- Pure fixed-profile relocation, also exercised by the injected owned test.
function M.prepare(game_base,base)
    assert(address(game_base)and game_base%4096==0 and address(base)and base%4096==0,'CODE_COPY_LAYOUT_ADDRESS')
    assert(base>=game_base+M.source.game_size and base+P.allocation_bytes-1<=game_base+0x7FFFFFFF,'CODE_COPY_NEAR_RANGE')
    local x=material();local layout,regions={},{}
    for i,r in ipairs(P.regions)do layout[i]=base+r.offset end
    for i,raw in ipairs(x.regions)do
        local fields={}
        for _,f in ipairs(P.fields)do if f[1]==i then
            local target=f[5]==0 and game_base+f[6]or layout[f[5]]+f[6]
            assert(target>=game_base and target-game_base<=4294967295,'CODE_COPY_TARGET_RVA32')
            local value=f[7]==1 and target-(layout[i]+f[4])or target-game_base
            fields[#fields+1]={f[2],encode(value,f[3],f[7]~=2)}
        end end
        regions[i]=patch(raw,fields)
    end
    local changes={}
    for _,f in ipairs(P.chains)do
        changes[#changes+1]={f[1],encode(layout[f[2]]-game_base+f[3],4,false)
            ..encode(layout[f[2]]-game_base+f[4],4,false)..encode(base+P.unwind_offset-game_base+f[5],4,false)}
    end
    local uw=patch(x.unwind,changes);local records={}
    for _,f in ipairs(P.runtime_functions)do
        records[#records+1]={layout[f[1]]-game_base+f[2],layout[f[1]]-game_base+f[3],
            base+P.unwind_offset-game_base+f[4]}
    end
    table.sort(records,function(a,c)return a[1]<c[1]end)
    local rows={}
    for i,r in ipairs(records)do
        assert(r[1]<r[2]and(i==1 or records[i-1][2]<=r[1]),'CODE_COPY_RF_ORDER')
        rows[i]=encode(r[1],4,false)..encode(r[2],4,false)..encode(r[3],4,false)
    end
    local counter,target=base+P.counter_offset,base+P.counter_offset+8
    local wrapper=b.unhex('f048ff05')..encode(counter-(base+8),4,true)
        ..b.unhex('ff25')..encode(target-(base+14),4,true)
    return {layout=layout,regions=regions,unwind=uw,table=table.concat(rows),wrapper=wrapper,
        cas=b.unhex('4c89c0f0480fb111c3'),counter=counter,target=target,table_address=base+P.table_offset,
        counter_bytes=qword(0)..qword(layout[1]),RF_count=PROFILE.RF}
end
local function bindings()
    if api_cache then return api_cache end
    local win=require('hd2runtime/runtime/windows_ffi');local ffi,k=win.ffi,win.kernel
    assert(ffi.abi('64bit')and jit.arch=='x64','CODE_COPY_X64_REQUIRED')
    if not rawget(_G,'HD2LedgerCodeCopyFfiV1')then
        ffi.cdef[[typedef struct HD2LedgerCodeAddressRequirements {void *lowest;void *highest;size_t alignment;} HD2LedgerCodeAddressRequirements;
            typedef struct HD2LedgerCodeExtendedParameter {uint64_t type_and_reserved;void *pointer;} HD2LedgerCodeExtendedParameter;]]
        rawset(_G,'HD2LedgerCodeCopyFfiV1',true)
    end
    assert(ffi.sizeof('HD2LedgerCodeAddressRequirements')==24 and ffi.sizeof('HD2LedgerCodeExtendedParameter')==16,'CODE_COPY_FFI_LAYOUT')
    local function proc(lib,name,signature)
        local handle=k.GetModuleHandleA(lib)
        if handle==nil then error('CODE_COPY_MODULE_UNAVAILABLE:'..lib,0)end
        local entry=k.GetProcAddress(handle,name)
        if entry==nil then error('CODE_COPY_API_UNAVAILABLE:'..name,0)end
        return ffi.cast(win.fn(signature),entry)
    end
    local alloc=proc('KernelBase.dll','VirtualAlloc2','void *(*)(void *,void *,size_t,uint32_t,uint32_t,HD2LedgerCodeExtendedParameter *,uint32_t)')
    local protect=proc('kernel32.dll','VirtualProtect','int (*)(void *,size_t,uint32_t,uint32_t *)')
    local flush=proc('kernel32.dll','FlushInstructionCache','int (*)(void *,const void *,size_t)')
    local pid=proc('kernel32.dll','GetCurrentProcessId','uint32_t (*)(void)')
    local register=proc('ntdll.dll','RtlAddFunctionTable','uint8_t (*)(void *,uint32_t,uint64_t)')
    local cas_type=win.fn('uint64_t (*)(uint64_t *,uint64_t,uint64_t)')
    local api={}
    function api.pid()return tonumber(pid())end
    function api.system_info()
        local info=ffi.new('HD2RuntimeSystemInfo[1]');win.get_system_info(info)
        return tonumber(info[0].page_size),tonumber(ffi.cast('uintptr_t',info[0].maximum_address)),tonumber(info[0].allocation_granularity)
    end
    function api.allocate(req)
        local ar=ffi.new('HD2LedgerCodeAddressRequirements[1]');ar[0].lowest=ffi.cast('void *',req.lowest)
        ar[0].highest=ffi.cast('void *',req.highest);ar[0].alignment=req.alignment
        local ep=ffi.new('HD2LedgerCodeExtendedParameter[1]');ep[0].type_and_reserved=1;ep[0].pointer=ar
        local memory=alloc(nil,nil,req.size,0x3000,4,ep,1)
        if memory==nil then error('CODE_COPY_ALLOC_FAILED',0)end
        return {base=tonumber(ffi.cast('uintptr_t',memory)),memory=memory,requirements=ar,parameters=ep}
    end
    function api.write(at,raw)ffi.copy(ffi.cast('void *',at),raw,#raw)end
    function api.register(at,count,game_base)return register(ffi.cast('void *',at),count,game_base)~=0 end
    function api.protect(at,size,mode)local old=ffi.new('uint32_t[1]');return protect(ffi.cast('void *',at),size,mode,old)~=0 end
    function api.flush(at,size)return flush(k.GetCurrentProcess(),ffi.cast('void *',at),size)~=0 end
    function api.cas(p,slot,replacement,expected)
        local fn=ffi.cast(cas_type,p.base+P.cas_offset)
        return tonumber(fn(ffi.cast('uint64_t *',slot),replacement,expected))
    end
    function api.counter(p)return tonumber(ffi.cast('uint64_t *',p.base+P.counter_offset)[0])end
    api_cache=api;return api
end
local function retain(p)
    local life=rawget(_G,LIFE);if not life then life={};rawset(_G,LIFE,life)end
    life[#life+1]=p
end
function M.new(options)
    options=type(options)=='table'and options or{}
    local factory,linker=rawget(options,'observer_factory'),rawget(options,'observer_link')
    local continuous=rawget(options,'continuous')==true
    assert((factory==nil and linker==nil and not continuous)
        or(P.version==2 and type(factory)=='function'and type(linker)=='function'and continuous),
        'CODE_COPY_OBSERVER_OPTIONS')
    return setmetatable({adapter=rawget(options,'adapter'),clock_override=rawget(options,'clock'),
        observer_factory=factory,observer_link=linker,continuous=continuous,
        d={version=P.version,phase='idle',reason='NOT_STARTED',one_shot=true,payload_ready=false,
            classification_ready=false,engine_dispatch_proven=false,Game_or_exception_safety_proven=false,
            owned_unwind_parity_recorded=true,owned_unwind_parity_sha=P.owned_parity_sha,
            prior_owned_unwind_parity_sha=P.prior_owned_parity_sha,
            owned_unwind_parity_new_regions_only=P.version==2,
            requested=false,installed=false,registered=false,restored=false,restore_attempted=false,
            third_party_preserved=false,cleanup_required=false,retained_pages=0,allocation_calls=0,
            counter=0,wrapper_invoked=false,elapsed_seconds=0,soft_window_seconds=continuous and 0 or 2,
            continuous_observation=continuous,deadline_requires_tick=not continuous,
            reads=0,bytes=0,fsm_reads=0,full_code_bytes=PROFILE.code,full_metadata_bytes=PROFILE.metadata,
            runtime_function_count=PROFILE.RF,chain_count=PROFILE.chains}},Controller)
end
function Controller:status()return copy(self.d)end
function Controller:observer_handle()
    if self.d.phase=='running'and self.d.installed and self.d.observers_linked then return self.observer end
end
function Controller:_query(at,n,image,executable,writable)
    local r=self.io.query(at);local p=type(r)=='table'and bit.band(r.protect or 0,0xff)
    if type(r)~='table'or not address(r.base)or not finite(r.size)or r.size%1~=0 or r.size<=0
        or r.state~=0x1000 or bit.band(r.protect or 0,0x100)~=0 or at<r.base or at+n>r.base+r.size
        or not(p==2 or p==4 or p==8 or p==0x20 or p==0x40 or p==0x80)
        or(image and(r.type~=0x1000000 or r.allocation_base~=self.game_base))
        or(executable and not(p==0x20 or p==0x40 or p==0x80))or(writable and p~=4)then
        error('CODE_COPY_REGION_CHANGED',0)
    end
    return r
end
function Controller:_read(at,n,executable,writable)
    if not address(at)or not address(at+n-1)or n<1 or n>4096
        or self.d.reads>=PROFILE.reads or self.d.bytes+n>PROFILE.bytes then
        error('CODE_COPY_SOURCE_READ_BUDGET',0)
    end
    self:_query(at,n,true,executable,writable);self.d.reads,self.d.bytes=self.d.reads+1,self.d.bytes+n
    local raw=self.io.read(at,n);if type(raw)~='string'or#raw~=n then error('CODE_COPY_READ_FAILED',0)end;return raw
end
function Controller:_identity(world,game,initial)
    if type(world)~='table'or type(game)~='table'or type(game.mission)~='boolean'
        or(not self.continuous and(game.mission~=false or(game.state~=2 and game.state~=3)))
        or world.runtime~=self.runtime or world.view~=self.view or self.runtime.mode~='live'
        or world.game~=self.game_base or world.exe~=self.exe_base
        or self.io.address(self.io.module(nil))~=self.exe_base or self.io.address(self.io.module('game.dll'))~=self.game_base
        or self.api.pid()~=self.pid then error('CODE_COPY_IDENTITY_OR_PHASE_CHANGED',0)end
    local ctx=self.view.pointer(self.game_base+M.source.state_rva)
    if not pointer(ctx)then error('CODE_COPY_CONTEXT_UNAVAILABLE',0)end
    local state=self.view.u32(ctx+M.source.state_offset);self.d.fsm_reads=self.d.fsm_reads+2
    if state~=game.state or(not self.continuous and not initial and(ctx~=self.context or state~=self.state))then error('CODE_COPY_CONTEXT_OR_PHASE_CHANGED',0)end
    if self.continuous and self.published then
        local current=self.view.pointer(self.slot)
        self.d.dispatch_reads=(self.d.dispatch_reads or 0)+1
        if current~=self.native.wrapper then error('CODE_COPY_DISPATCH_OWNER_CHANGED',0)end
    end
    if initial then self.context,self.state=ctx,state end
end
function Controller:_now()
    local t=self.clock();if not finite(t)or(self.last_clock and t<self.last_clock)then error('CODE_COPY_CLOCK_INVALID',0)end
    self.last_clock=t;return t
end
function Controller:_source(post)
    local x=material();local raw=self:_read(self.game_base,4096)
    local pe=b.u32(raw,60)
    if raw:sub(1,2)~='MZ'or pe~=0x110 or raw:sub(pe+1,pe+4)~='PE\0\0'
        or b.u16(raw,pe+4)~=0x8664 or b.u16(raw,pe+6)~=16 or b.u16(raw,pe+20)~=240
        or b.u16(raw,pe+24)~=0x20B or b.u32(raw,pe+80)~=M.source.game_size
        or b.u32(raw,pe+24+112)~=M.source.export_rva or b.u32(raw,pe+24+116)~=74 then error('CODE_COPY_PE_CHANGED',0)end
    if post and raw~=self.header then error('CODE_COPY_HEADER_CHANGED',0)end;self.header=raw
    if self:_read(self.game_base+M.source.export_rva,74)~=x.export
        or self:_read(self.game_base+M.source.getter_rva,173,true)~=x.getter then error('CODE_COPY_EXPORT_GETTER_CHANGED',0)end
    local tbl=self:_read(self.game_base+M.source.table_rva,200)
    for _,s in ipairs(STORES)do if b.pointer(tbl,s[1])~=self.game_base+s[2]then error('CODE_COPY_PLUGIN_TABLE_CHANGED',0)end end
    if post and tbl~=self.table_pin then error('CODE_COPY_PLUGIN_TABLE_CHANGED',0)end;self.table_pin=tbl
    for i,r in ipairs(P.regions)do
        local offset=0
        while offset<r.length do
            local n=math.min(4096,r.length-offset)
            if self:_read(self.game_base+r.rva+offset,n,true)~=x.regions[i]:sub(offset+1,offset+n)then error('CODE_COPY_FULL_CODE_CHANGED:'..r.name,0)end
            offset=offset+n
        end
    end
    for i,r in ipairs(P.source_metadata)do
        if self:_read(self.game_base+r.rva,r.length)~=x.metadata[i]then error('CODE_COPY_FULL_METADATA_CHANGED:'..r.name,0)end
    end
    self.slot=self.game_base+M.source.table_rva+M.source.slot_offset;self.original=self.game_base+M.source.frame_rva
    assert(self.slot%8==0,'CODE_COPY_SLOT_ALIGNMENT');self:_query(self.slot,8,true,false,true)
    if post then self.d.full_source_verified_after=true else self.d.full_source_verified_before=true end
end
function Controller:_owned(at,n,writable)
    local p=self.native
    if not address(at)or not address(at+n-1)or at<p.base or at+n>p.base+P.allocation_bytes then error('CODE_COPY_OWNED_BOUND',0)end
    local r=self:_query(at,n,false,false,writable)
    if r.type~=0x20000 or r.allocation_base~=p.base then error('CODE_COPY_OWNED_ALLOCATION_CHANGED',0)end
end
-- Optional destruction dispatch is outside the six unchanged hit regions.
-- Verify its exact captured body and unwind metadata before publication and
-- again immediately before the existing ownership-checked slot update.
function Controller:_observer_source(profile)
    if not profile or not profile.demolition_diagnostic then return end
    local ranges=profile.demolition_source
    local expected={{0x13F7BA0,1532,true},{0x409DA80,12,false},{0x25161DC,64,false}}
    assert(type(ranges)=='table'and#ranges==3,'CODE_COPY_DEMOLITION_SOURCE_CONTRACT')
    local reads,bytes=self.d.demolition_source_reads or 0,self.d.demolition_source_bytes or 0
    for i,e in ipairs(expected)do
        local item=ranges[i]
        assert(type(item)=='table'and item.rva==e[1]and type(item.hex)=='string'
            and#item.hex==e[2]*2 and not item.hex:find('[^%x]'),'CODE_COPY_DEMOLITION_SOURCE_CONTRACT')
        assert(reads<6 and bytes+e[2]<=3216,'CODE_COPY_DEMOLITION_SOURCE_BUDGET')
        local at=self.game_base+e[1]
        self:_query(at,e[2],true,e[3],false)
        local raw=self.io.read(at,e[2])
        reads,bytes=reads+1,bytes+e[2]
        self.d.demolition_source_reads,self.d.demolition_source_bytes=reads,bytes
        assert(type(raw)=='string'and raw==b.unhex(item.hex),'CODE_COPY_DEMOLITION_SOURCE_CHANGED')
    end
end
function Controller:_prepare()
    local page,maximum,granularity=self.api.system_info()
    if page~=4096 or not finite(granularity)or granularity%1~=0 or granularity<4096
        or bit.band(granularity,granularity-1)~=0 or not address(maximum)then error('CODE_COPY_SYSTEM_INFO',0)end
    local lowest=math.ceil((self.game_base+M.source.game_size)/granularity)*granularity
    local highest=math.floor((math.min(maximum,self.game_base+0x7FFFFFFF)+1)/granularity)*granularity-1
    if lowest+P.allocation_bytes-1>highest then error('CODE_COPY_NEAR_RANGE_UNAVAILABLE',0)end
    self.step='allocate';self.d.allocation_calls=1
    local p=self.api.allocate({lowest=lowest,highest=highest,alignment=granularity,size=P.allocation_bytes})
    if type(p)~='table'then error('CODE_COPY_ALLOC_FAILED',0)end
    self.native=p;retain(p);self.d.retained_pages=P.allocation_bytes/4096
    if not address(p.base)or p.base%granularity~=0 or p.base<lowest or p.base+P.allocation_bytes-1>highest then error('CODE_COPY_ALLOC_RANGE',0)end
    p.api=self.api;p.prepared=M.prepare(self.game_base,p.base);p.wrapper=p.base+P.wrapper_offset
    if self.observer_factory then
        self.step='prepare_observer'
        local profile,handle=self.observer_factory({base=self.game_base,size=M.source.game_size})
        self:_observer_source(profile)
        self.observer_profile=profile
        local linked=self.observer_link(p.prepared,profile,handle,material().regions,P.regions)
        assert(linked==p.prepared and linked.observers_linked==true,'CODE_COPY_OBSERVER_LINK_FAILED')
        self.observer=handle;p.observer=handle;self.d.observers_linked=true
    end
    local plan=p.prepared
    local function write(offset,bytes)
        self:_owned(p.base+offset,#bytes,true);self.api.write(p.base+offset,bytes)
    end
    self.step='write_owned'
    for i,r in ipairs(P.regions)do write(r.offset,plan.regions[i])end
    write(P.unwind_offset,plan.unwind);write(P.table_offset,plan.table)
    write(P.wrapper_offset,plan.wrapper);write(P.cas_offset,plan.cas);write(P.counter_offset,plan.counter_bytes)
    self.step='register';if self.api.register(plan.table_address,PROFILE.RF,self.game_base)~=true then error('CODE_COPY_REGISTER_FAILED',0)end
    self.d.registered=true
    self.step='protect';self:_owned(p.base,P.code_page_bytes,true)
    if self.api.protect(p.base,P.code_page_bytes,0x20)~=true then error('CODE_COPY_OWN_RX_FAILED',0)end
    self.step='flush';if self.api.flush(p.base,P.code_page_bytes)~=true then error('CODE_COPY_FLUSH_FAILED',0)end
end
function Controller:_cas(replacement,expected)return self.api.cas(self.native,self.slot,replacement,expected)end
function Controller:_counter()
    local count=self.api.counter(self.native)
    if not finite(count)or count<0 or count%1~=0 then error('CODE_COPY_COUNTER_INVALID',0)end
    self.d.counter=count;self.d.wrapper_invoked=count>0
end
function Controller:start(world,game)
    if self.attempted then return self:status()end;self.attempted=true
    local ok,why=pcall(function()
        if type(game)~='table'or game.mission~=false or(game.state~=2 and game.state~=3)then error('CODE_COPY_WAITING_TITLE_OR_SHIP',0)end
        if self.continuous and game.state~=3 then error('CODE_COPY_OBSERVER_WAITING_SHIP',0)end
        if type(world)~='table'or type(world.runtime)~='table'or type(world.view)~='table'or world.runtime.mode~='live'
            or not pointer(world.game)or world.game%4096~=0 or not pointer(world.exe)or world.exe%4096~=0 then error('CODE_COPY_WORLD_UNAVAILABLE',0)end
        if schema.exe_sha~=M.source.exe_sha or schema.dll_sha~=M.source.dll_sha then error('CODE_COPY_BUILD_MISMATCH',0)end
        self.runtime,self.view,self.game_base,self.exe_base=world.runtime,world.view,world.game,world.exe
        self.io=self.adapter or self.runtime
        for _,name in ipairs({'query','read','module','address','module_hash'})do assert(type(self.io[name])=='function','CODE_COPY_RUNTIME_UNAVAILABLE')end
        assert(type(self.view.pointer)=='function'and type(self.view.u32)=='function','CODE_COPY_VIEW_UNAVAILABLE')
        fingerprint.require(self.io);self.api=self.adapter or bindings()
        for _,name in ipairs({'pid','system_info','allocate','write','register','protect','flush','cas','counter'})do
            assert(type(self.api[name])=='function','CODE_COPY_API_UNAVAILABLE:'..name)
        end
        self.pid=self.api.pid();self.clock=self.clock_override or self.runtime.precise_time or self.runtime.monotonic_time
        assert(type(self.clock)=='function','CODE_COPY_CLOCK_UNAVAILABLE');self:_now()
        self:_identity(world,game,true);self:_source(false);self:_prepare()
        self:_identity(world,game,false);self:_source(true);self:_observer_source(self.observer_profile)
        self:_identity(world,game,false)
        if b.pointer(self:_read(self.slot,8,false,true),0)~=self.original then error('CODE_COPY_OWNER_CHANGED_BEFORE_CAS',0)end
        self.started_time=self:_now();self.step='install';self.d.requested=true
        -- Mark a possible publication before CAS so a caller exception still restores by expected-wrapper CAS.
        self.published=true
        if self:_cas(self.native.wrapper,self.original)~=self.original then
            self.published=false;self.d.third_party_preserved=true;error('CODE_COPY_INSTALL_OWNER_CHANGED',0)
        end
        self.d.installed=true;self.d.phase='running';self.d.reason='WINDOW_RUNNING';self.d.started_state=self.state
        if self.observer then self.observer.native_certified=true;self.d.reason='OBSERVATION_COPY_INSTALLED'end
    end)
    if not ok then
        local failure=tostring(why)
        if self.published then self:stop('START_EXCEPTION')end
        self.d.phase='failed';self.d.reason=failure;self.d.native_error={step=self.step or'validation',message=failure}
    end
    return self:status()
end
function Controller:stop(reason)
    if not self.published then return self:status()end
    self.d.phase='stopped';self.d.reason=type(reason)=='string'and reason or'STOPPED'
    -- Diagnostic failure must not prevent the ownership-checked restore.
    local counted,counter_why=pcall(self._counter,self)
    if not counted then self.d.counter_reason=tostring(counter_why)end
    local ok,why=pcall(function()
        self:_query(self.slot,8,true,false,true)
        if self.api.pid()~=self.pid or self.io.address(self.io.module('game.dll'))~=self.game_base
            or self.io.address(self.io.module(nil))~=self.exe_base then error('CODE_COPY_RESTORE_IDENTITY_CHANGED',0)end
        self.d.restore_attempted=true
        local previous=self:_cas(self.original,self.native.wrapper)
        self.d.restored=previous==self.native.wrapper;self.d.third_party_preserved=not self.d.restored
        self.published=false;self.d.installed=false
        -- The lifetime-owned bridge remains certified for its final drain.
        -- Restoring this dispatch slot stops future entry; it does not free the
        -- queue or invalidate the connector's pause/drain functions.
    end)
    if not ok then self.d.cleanup_required=true;self.d.phase='failed';self.d.restore_reason=tostring(why)
    else self.d.cleanup_required=false;self.d.restore_reason=self.d.restored and'ORIGINAL_RESTORED'or'OWNER_CHANGED_PRESERVED'end
    return self:status()
end
function Controller:tick(world,game)
    if self.d.phase~='running'then return self:status()end
    local ok,why=pcall(function()
        self:_identity(world,game,false);local now=self:_now();self.d.elapsed_seconds=now-self.started_time
        self:_counter()
        if not self.continuous and self.d.elapsed_seconds>=2 then self:stop('WINDOW_ENDED')end
    end)
    if not ok then self:stop(tostring(why))end
    return self:status()
end
return M
