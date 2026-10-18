-- Explicit one-shot Armory request from the installed GMH v1.7 contract.
-- This opens presenter5 only; it does not request ViewStats or synchronize Career.
local b=require('hd2runtime/core/bytes')
local profile=require('hd2runtime/schemas/current')
local fingerprint=require('hd2runtime/core/fingerprint')
local bit=require('bit')
local M={source={
    exe_sha='F5FEE03DCFDB2E553A4752C283590950AC13316B376D8196AA556FF0400D5F06',
    dll_sha='2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E',
    sender_source_sha='cd5ac17e9be9b1dca46c9ee202006c1719d2e46534d2696e71ba8154f7cad4b3',
    rva=0x14C0350,pin='48895c24084889742410574883ec208b',
    signature='void (__fastcall *)(void *, int, void *)',presenter=5,
    ui=0x347CE28,manager=0x4288,state=0x3326340,state_offset=0xAC21C,
}}
local Controller={};Controller.__index=Controller
local function address(v)
    return type(v)=='number'and v==v and v>=65536 and v<140737488355328 and v%1==0
end
local function pointer(v)return address(v)and v%8==0 end
local function copy(v)
    if type(v)~='table'then return v end
    local o={};for k,x in pairs(v)do o[k]=copy(x)end;return o
end
function M.new(options)
    options=type(options)=='table'and options or{}
    return setmetatable({adapter=rawget(options,'adapter'),d={version=1,phase='idle',
        reason='NOT_STARTED',one_shot=true,requested=false,opened=false,calls=0,
        reads=0,bytes=0,fingerprint_verified=false,career_ready=false,
        page_visibility_proven=false}},Controller)
end
function Controller:status()return copy(self.d)end
function Controller:_read(at,n,image,executable)
    if not address(at)or not address(at+n-1)or n<1 or n>32
        or self.d.reads>=16 or self.d.bytes+n>512 then error('ARMORY_READ_BUDGET',0)end
    local r=self.io.query(at)
    local p=type(r)=='table'and bit.band(r.protect or 0,0xff)
    if type(r)~='table'or not address(r.base)or type(r.size)~='number'or r.size%1~=0
        or r.size<=0 or not address(r.base+r.size-1)or r.state~=0x1000
        or bit.band(r.protect or 0,0x100)~=0 or at<r.base or at+n>r.base+r.size
        or not(p==2 or p==4 or p==8 or p==0x20 or p==0x40 or p==0x80)
        or(image and(r.type~=0x1000000 or r.allocation_base~=self.game_base))
        or(executable and not(p==0x20 or p==0x40 or p==0x80))then
        error('ARMORY_REGION_UNREADABLE',0)
    end
    self.d.reads,self.d.bytes=self.d.reads+1,self.d.bytes+n
    local raw=self.read(at,n)
    if type(raw)~='string'or#raw~=n then error('ARMORY_READ_FAILED',0)end
    return raw
end
function Controller:_pointer(at,image)
    local v=b.pointer(self:_read(at,8,image),0)
    if not pointer(v)then error('ARMORY_POINTER_INVALID',0)end
    return v
end
function Controller:_identity(world,game,initial)
    if type(world)~='table'or type(game)~='table'or game.state~=3 or game.mission~=false
        or world.runtime~=self.runtime or world.view~=self.view
        or world.game~=self.game_base or world.exe~=self.exe_base or self.runtime.mode~='live'
        or self.io.address(self.io.module(nil))~=self.exe_base
        or self.io.address(self.io.module('game.dll'))~=self.game_base then
        error('ARMORY_IDENTITY_OR_SHIP_CHANGED',0)
    end
    local ctx=self:_pointer(self.game_base+M.source.state,true)
    if b.u32(self:_read(ctx+M.source.state_offset,4),0)~=3
        or(not initial and ctx~=self.context)then error('ARMORY_NATIVE_SHIP_CHANGED',0)end
    if initial then self.context=ctx end
end
function Controller:_menu()
    local ui=self:_pointer(self.game_base+M.source.ui,true)
    local manager=ui+M.source.manager
    if not pointer(manager)or(self.ui and ui~=self.ui)then error('ARMORY_UI_CHANGED',0)end
    self.ui,self.manager=ui,manager
    local raw=self:_read(manager+0x0C,32)
    return b.u32(raw,0),b.u32(raw,0x1C)
end
function Controller:_pin()
    if b.hex(self:_read(self.game_base+M.source.rva,16,true,true))~=M.source.pin then
        error('ARMORY_CODE_PIN_CHANGED',0)
    end
end
function Controller:_caller()
    if self.adapter then
        if type(self.adapter.invoke)~='function'then error('ARMORY_ADAPTER_INVOKE_UNAVAILABLE',0)end
        return function(manager)
            self.adapter.invoke(self.game_base+M.source.rva,M.source.signature,manager,5,nil)
        end
    end
    local win=require('hd2runtime/runtime/windows_ffi');local ffi=win.ffi
    if not ffi.abi('64bit')or type(jit)~='table'or jit.arch~='x64'then error('ARMORY_X64_REQUIRED',0)end
    local fn=ffi.cast(win.fn(M.source.signature),self.game_base+M.source.rva)
    return function(manager)fn(ffi.cast('void *',manager),5,nil)end
end
function Controller:start(world,game)
    if self.attempted then return self:status()end
    self.attempted=true
    local ok,why=pcall(function()
        if type(game)~='table'or game.state~=3 or game.mission~=false then error('ARMORY_WAITING_SHIP',0)end
        if type(world)~='table'or type(world.runtime)~='table'or type(world.view)~='table'
            or world.runtime.mode~='live'or not pointer(world.game)or world.game%4096~=0
            or not pointer(world.exe)or world.exe%4096~=0 then error('ARMORY_WORLD_UNAVAILABLE',0)end
        if profile.exe_sha~=M.source.exe_sha or profile.dll_sha~=M.source.dll_sha then error('ARMORY_PROFILE_MISMATCH',0)end
        self.runtime,self.view,self.game_base,self.exe_base=world.runtime,world.view,world.game,world.exe
        self.io=self.adapter or self.runtime
        self.read=self.adapter and self.adapter.read or self.view.read
        for _,name in ipairs({'query','module','address','module_hash'})do
            if type(self.io[name])~='function'then error('ARMORY_RUNTIME_UNAVAILABLE',0)end
        end
        if type(self.read)~='function'then error('ARMORY_VIEW_UNAVAILABLE',0)end
        if fingerprint.matches(self.io)~=true then error('ARMORY_FINGERPRINT_MISMATCH',0)end
        self.d.fingerprint_verified=true
        self:_identity(world,game,true);self:_pin()
        local current,depth=self:_menu()
        self.d.current_before,self.d.depth_before=current,depth
        if current~=0 or depth~=0 then error(current==5 and'ARMORY_ALREADY_OPEN'or'ARMORY_MENU_BUSY',0)end
        local invoke=self:_caller()
        -- Recheck the actual Ship, source bytes and idle manager immediately before the one call.
        self:_identity(world,game,false);self:_pin()
        current,depth=self:_menu()
        if current~=0 or depth~=0 then error('ARMORY_MENU_CHANGED_BEFORE_REQUEST',0)end
        self.d.requested,self.d.calls=true,1
        invoke(self.manager)
        self:_identity(world,game,false)
        current,depth=self:_menu()
        self.d.current_after,self.d.depth_after=current,depth
        self.d.opened=current==5 and depth>=1 and depth<=5
        self.d.phase=self.d.opened and'opened'or'requested'
        self.d.reason=self.d.opened and'ARMORY_CURRENT_OBSERVED'or'ARMORY_NOT_OBSERVED'
    end)
    if not ok then
        self.d.phase=self.d.requested and'failed'or'rejected'
        self.d.reason=type(why)=='string'and why or'ARMORY_REQUEST_ERROR'
    end
    return self:status()
end
return M
