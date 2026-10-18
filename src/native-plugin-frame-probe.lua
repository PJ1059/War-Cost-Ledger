-- Explicit, one-shot timing diagnostic. Never starts automatically or calls Game code.
-- Integration MUST call stop on cancellation, callback errors and MOD unload. The
-- two-second soft deadline needs tick; retained RX/RW pages are never freed/reused.
local b=require('hd2runtime/core/bytes')
local profile=require('hd2runtime/schemas/current')
local bit=require('bit')
local M={source={exe_sha='F5FEE03DCFDB2E553A4752C283590950AC13316B376D8196AA556FF0400D5F06',
    dll_sha='2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E',
    game_size=0x4744000,exe_size=0x39E8000,export_rva=0x39D4000,export_size=74,
    getter_rva=0x4EEAD0,frame_rva=0x4EE6C0,table_rva=0x37CEB10,slot_offset=0x68,
    getter_source_sha='4c1c9fdfa8e26bba9bcc4743ee61af2f5bfefe229a2f7bf703b9bc44bcfa6118',
    table_frame_source_sha='03b3fd1cd3459fb3c3d6eb71e47a806dd2376ccd7f36dbc1f60f606bd446f546'}}
local GETTER='85c90f85a2000000488d0581f6ffff48890582002e03488d05d3fbffff48890584002e03488d0515fcffff4889058e002e03488d0547fcffff48890588002e03488d05c9fcffff48890582002e03488d05cbfcffff48890584002e03488d059dfeffff4889058e002e03488d056fffffff48890588002e03488d0541fbffff48890552002e03488d0543fbffff488905c4ff2d03488d0545fbffff488905beff2d03488d0597ff2d03c333c0c3'
local FRAME='4883ec38488b051d7de3020f297424200f28f0ff5020488b05b37ce302ff10488b0d5a7ce3020f28cee812695c00488d0dfb7be3020f287424204883c438e9add32401'
-- Actual export directory is matched byte-exactly, including its internal name,
-- ordinal0->ordinal1 and EAT4EEAD0; no getter invocation/forwarder followup.
local EXPORT_FULL='00000000ffffffff0000000028409d0301000000010000000100000042409d0346409d0340409d0367616d652e646c6c006765745f706c7567696e5f617069000000d0ea4e0031409d03'
local STORES={{0x58,0x4EE160},{0x68,0x4EE6C0},{0x80,0x4EE710},{0x88,0x4EE750},
    {0x90,0x4EE7E0},{0xA0,0x4EE7F0},{0xB8,0x4EE9D0},{0xC0,0x4EEAB0},
    {0x98,0x4EE690},{0x18,0x4EE6A0},{0x20,0x4EE6B0}}
local Controller={};Controller.__index=Controller
local api_cache
local LIFETIME_KEY='HD2LedgerPluginFrameProbeLifetimeV1'
local function finite(v)return type(v)=='number'and v==v and v>-math.huge and v<math.huge end
local function address(v)return finite(v)and v>=65536 and v<140737488355328 and v%1==0 end
local function hexraw(h)return(h:gsub('..',function(x)return string.char(tonumber(x,16))end))end
local function copy(v)if type(v)~='table'then return v end;local o={};for k,x in pairs(v)do o[k]=copy(x)end;return o end
local function bindings()
    if api_cache then return api_cache end
    local win=require('hd2runtime/runtime/windows_ffi');local ffi,k=win.ffi,win.kernel
    assert(ffi.abi('64bit')and jit.arch=='x64','FRAME_PROBE_X64_REQUIRED')
    local api={ffi=ffi,win=win}
    local lib=assert(k.GetModuleHandleA('kernel32.dll'))
    for _,d in ipairs({{'alloc','VirtualAlloc','void *(*)(void *,size_t,uint32_t,uint32_t)'},
        {'protect','VirtualProtect','int (*)(void *,size_t,uint32_t,uint32_t *)'},
        {'flush','FlushInstructionCache','int (*)(void *,const void *,size_t)'},
        {'pid','GetCurrentProcessId','uint32_t (*)(void)'},
        {'clock','GetTickCount64','uint64_t (*)(void)'}})do
        api[d[1]]=ffi.cast(win.fn(d[3]),assert(k.GetProcAddress(lib,d[2])))
    end
    api.process=k.GetCurrentProcess();api.cas_type=win.fn('uint64_t (*)(uint64_t *,uint64_t,uint64_t)')
    api_cache=api;return api
end
local function retain(p)
    local life=rawget(_G,LIFETIME_KEY)
    if not life then life={};rawset(_G,LIFETIME_KEY,life)end
    life[#life+1]=p -- Keep even failed preparation; no callbacks/pages are ever reclaimed here.
end
local function allocate(original)
    local api=bindings();local ffi=api.ffi
    local memory=api.alloc(nil,8192,0x3000,4);assert(memory~=nil,'FRAME_PROBE_ALLOC_FAILED')
    local base=tonumber(ffi.cast('uintptr_t',memory))
    local p={api=api,memory=memory,base=base,wrapper=base,cas_address=base+64,
        counter=ffi.cast('uint64_t *',base+4096),target=ffi.cast('uint64_t *',base+4104),
        retained=true};retain(p)
    p.target[0]=original;p.counter[0]=0
    p.wrapper_code=hexraw('f048ff05f80f0000ff25fa0f0000')
    ffi.copy(memory,p.wrapper_code,14);ffi.copy(ffi.cast('void *',p.cas_address),hexraw('4c89c0f0480fb111c3'),9)
    p.prior=ffi.new('uint32_t[1]')
    assert(api.protect(memory,4096,0x20,p.prior)~=0,'FRAME_PROBE_OWN_RX_FAILED')
    assert(api.flush(api.process,memory,4096)~=0,'FRAME_PROBE_OWN_FLUSH_FAILED')
    p.cas=ffi.cast(api.cas_type,p.cas_address)
    return p
end
function M.new(options)
    options=type(options)=='table'and options or{}
    return setmetatable({adapter=rawget(options,'adapter'),clock_override=rawget(options,'clock'),
        d={version=1,phase='idle',reason='NOT_STARTED',one_shot=true,payload_ready=false,
            engine_dispatch_proven=false,wrapper_invoked=false,counter=0,elapsed_seconds=0,
            soft_window_seconds=2,deadline_requires_tick=true,restore_attempted=false,
            restored=false,third_party_preserved=false,retained_pages=0,reads=0,bytes=0}},Controller)
end
function Controller:status()return copy(self.d)end
function Controller:_query(at,n,executable,writable)
    local r=self.io.query(at);local p=type(r)=='table'and bit.band(r.protect or 0,0xff)
    if type(r)~='table'or not address(r.base)or not finite(r.size)or r.state~=0x1000
        or r.type~=0x1000000 or r.allocation_base~=self.game_base
        or bit.band(r.protect or 0,0x100)~=0 or at<r.base or at+n>r.base+r.size
        or not(p==2 or p==4 or p==8 or p==0x20 or p==0x40 or p==0x80)
        or(executable and not(p==0x20 or p==0x40 or p==0x80))
        or(writable and p~=4)then error('FRAME_PROBE_REGION_CHANGED',0)end
end
function Controller:_read(at,n,executable,writable)
    if not address(at)or not address(at+n-1)or n<1 or n>4096
        or self.d.reads>=24 or self.d.bytes+n>16384 then error('FRAME_PROBE_READ_BUDGET',0)end
    self:_query(at,n,executable,writable)
    self.d.reads=self.d.reads+1;self.d.bytes=self.d.bytes+n
    local r=self.io.read(at,n);if type(r)~='string'or#r~=n then error('FRAME_PROBE_READ_FAILED',0)end
    return r
end
function Controller:_now()
    local t=self.clock()
    if not finite(t)or(self.last_clock and t<self.last_clock)then error('FRAME_PROBE_CLOCK_INVALID',0)end
    self.last_clock=t;return t
end
function Controller:_identity(world,game,initial)
    if type(world)~='table'or type(game)~='table'or game.mission~=false
        or(game.state~=2 and game.state~=3)or world.runtime~=self.runtime or world.view~=self.view
        or world.game~=self.game_base or world.exe~=self.exe_base or self.runtime.mode~='live'
        or profile.exe_sha~=M.source.exe_sha or profile.dll_sha~=M.source.dll_sha
        or self.io.address(self.io.module('game.dll'))~=self.game_base
        or self.io.address(self.io.module(nil))~=self.exe_base
        or tonumber(bindings().pid())~=self.pid then error('FRAME_PROBE_IDENTITY_OR_PHASE_CHANGED',0)end
    local ctx=self.view.pointer(self.game_base+0x3326340)
    if not address(ctx)or ctx%8~=0 or self.view.u32(ctx+0xAC21C)~=game.state
        or(not initial and(ctx~=self.context or game.state~=self.state))then
        error('FRAME_PROBE_CONTEXT_OR_PHASE_CHANGED',0)
    end
    if initial then self.context,self.state=ctx,game.state end
end
function Controller:_source()
    local raw=self:_read(self.game_base,4096)
    local pe=b.u32(raw,60)
    if raw:sub(1,2)~='MZ'or pe~=0x110 or raw:sub(pe+1,pe+4)~='PE\0\0'
        or b.u16(raw,pe+4)~=0x8664 or b.u16(raw,pe+6)~=16 or b.u16(raw,pe+20)~=240
        or b.u16(raw,pe+24)~=0x20B or b.u32(raw,pe+80)~=M.source.game_size
        or b.u32(raw,pe+24+112)~=M.source.export_rva or b.u32(raw,pe+24+116)~=74 then
        error('FRAME_PROBE_PE_EXPORT_CHANGED',0)
    end
    if b.hex(self:_read(self.game_base+M.source.export_rva,74))~=EXPORT_FULL then error('FRAME_PROBE_EXPORT_CHANGED',0)end
    if b.hex(self:_read(self.game_base+M.source.getter_rva,173,true))~=GETTER
        or b.hex(self:_read(self.game_base+M.source.frame_rva,67,true))~=FRAME then error('FRAME_PROBE_CODE_PIN_CHANGED',0)end
    local table_raw=self:_read(self.game_base+M.source.table_rva,200)
    for _,s in ipairs(STORES)do
        if b.pointer(table_raw,s[1])~=self.game_base+s[2]then error('FRAME_PROBE_TABLE_SLOT_CHANGED',0)end
    end
    self.slot=self.game_base+M.source.table_rva+M.source.slot_offset
    assert(self.slot%8==0,'FRAME_PROBE_SLOT_UNALIGNED');self:_query(self.slot,8,false,true)
    self.original=self.game_base+M.source.frame_rva
end
function Controller:_cas(replacement,expected)
    if self.adapter and type(self.adapter.cas)=='function'then
        return self.adapter.cas(self.native,self.slot,replacement,expected)
    end
    return tonumber(self.native.cas(self.native.api.ffi.cast('uint64_t *',self.slot),replacement,expected))
end
function Controller:start(world,game)
    if self.attempted then return self:status()end
    self.attempted=true
    local ok,why=pcall(function()
        if type(game)~='table'or game.mission~=false or(game.state~=2 and game.state~=3)then
            error('FRAME_PROBE_WAITING_TITLE_OR_SHIP',0)
        end
        if type(world)~='table'or type(world.runtime)~='table'or type(world.view)~='table'
            or world.runtime.mode~='live'or not address(world.game)or not address(world.exe)
            or world.game%4096~=0 or world.exe%4096~=0 then error('FRAME_PROBE_WORLD_UNAVAILABLE',0)end
        self.runtime,self.view,self.game_base,self.exe_base=world.runtime,world.view,world.game,world.exe
        self.io=self.adapter or self.runtime
        if self.adapter and type(self.adapter.fingerprint)=='function'then
            assert(self.adapter.fingerprint(world)==true,'FRAME_PROBE_PROFILE_UNPROVEN')
        else require('hd2runtime/core/fingerprint').require(self.runtime)end
        self.pid=tonumber(bindings().pid())
        self.clock=self.clock_override or self.runtime.precise_time or function()return tonumber(bindings().clock())/1000 end
        self:_now();self:_identity(world,game,true);self:_source()
        self.native=allocate(self.original);self.d.retained_pages=2
        self:_identity(world,game,false)
        if b.hex(self:_read(self.game_base+M.source.getter_rva,173,true))~=GETTER
            or b.hex(self:_read(self.original,67,true))~=FRAME
            or b.pointer(self:_read(self.slot,8,false,true),0)~=self.original then error('FRAME_PROBE_SOURCE_CHANGED_BEFORE_CAS',0)end
        self.started_time=self:_now()
        if self:_cas(self.native.wrapper,self.original)~=self.original then error('FRAME_PROBE_INSTALL_OWNER_CHANGED',0)end
        self.published=true;self.d.phase='running';self.d.reason='WINDOW_RUNNING';self.d.started_state=self.state
    end)
    if not ok then
        if self.published then self:stop('START_EXCEPTION')end
        self.d.phase='failed';self.d.reason=type(why)=='string'and why or'START_EXCEPTION'
    end
    return self:status()
end
function Controller:stop(reason)
    if not self.published then return self:status()end
    self.d.phase='stopped';self.d.reason=type(reason)=='string'and reason or'STOPPED'
    self.d.counter=tonumber(self.native.counter[0]);self.d.wrapper_invoked=self.d.counter>0
    local ok,why=pcall(function()
        self:_query(self.slot,8,false,true)
        if self.io.address(self.io.module('game.dll'))~=self.game_base then error('FRAME_PROBE_RESTORE_MODULE_CHANGED',0)end
        self.d.restore_attempted=true
        local previous=self:_cas(self.original,self.native.wrapper)
        self.d.restored=previous==self.native.wrapper
        self.d.third_party_preserved=not self.d.restored
        self.published=false
    end)
    if not ok then self.d.restore_reason=type(why)=='string'and why or'RESTORE_UNAVAILABLE';self.d.cleanup_required=true
    else self.d.cleanup_required=false;self.d.restore_reason=self.d.restored and'ORIGINAL_RESTORED'or'OWNER_CHANGED_PRESERVED'end
    return self:status()
end
function Controller:tick(world,game)
    if self.d.phase~='running'then return self:status()end
    local ok,why=pcall(function()
        self:_identity(world,game,false)
        local now=self:_now();self.d.elapsed_seconds=now-self.started_time
        self.d.counter=tonumber(self.native.counter[0]);self.d.wrapper_invoked=self.d.counter>0
        if self.d.elapsed_seconds>=2 then self:stop('WINDOW_ENDED')end
    end)
    if not ok then self:stop(type(why)=='string'and why or'TICK_EXCEPTION')end
    return self:status()
end
return M
