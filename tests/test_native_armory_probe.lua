-- Injected image/heap/API fixture only. Never calls a Game entry or writes a file.
local source,runtime=assert(arg[1]),assert(arg[2])
table.insert(package.loaders,2,function(name)
    if name:sub(1,11)=='hd2runtime/'then return assert(loadfile(runtime..'/'..name:sub(12)..'.lua'))end
end)
local b=require('hd2runtime/core/bytes')
local fingerprint=require('hd2runtime/core/fingerprint')
local M=assert(loadfile(source))()
local function qword(v)return b.encode(v%4294967296,'u32')..b.encode(math.floor(v/4294967296),'u32')end
local function fixture(change)
    fingerprint.reset()
    local game_base,exe_base,ctx,ui=0x180000000,0x140000000,0x240000000,0x250000000
    local manager=ui+M.source.manager
    local f={state=3,current=0,depth=0,calls=0,reads=0,hashes=0,change=change}
    if change=='busy'then f.current,f.depth=2,1 end
    if change=='depth'then f.depth=1 end
    if change=='native_state'then f.state=4 end
    local io={mode='live',address=function(x)return x end,
        module=function(n)return n==nil and exe_base or n=='game.dll'and game_base or nil end}
    io.module_hash=function(handle)
        f.hashes=f.hashes+1
        assert(handle==game_base or handle==exe_base,'hash receives a module handle')
        if change=='fingerprint'and handle==game_base then return string.rep('0',64)end
        return handle==game_base and M.source.dll_sha or M.source.exe_sha
    end
    io.query=function(at)
        local image=at>=game_base and at<game_base+0x4744000
        return {base=image and game_base or 0x240000000,size=image and 0x4744000 or 0x20000000,
            state=0x1000,type=image and 0x1000000 or 0x20000,
            allocation_base=image and game_base or 0x240000000,
            protect=at==game_base+M.source.rva and 0x20 or 4}
    end
    io.read=function(at,n)
        f.reads=f.reads+1
        if at==game_base+M.source.state and n==8 then return qword(ctx)end
        if at==ctx+M.source.state_offset and n==4 then return b.encode(f.state,'u32')end
        if at==game_base+M.source.rva and n==16 then
            return change=='pin'and string.rep('\0',16)or b.unhex(M.source.pin)
        end
        if at==game_base+M.source.ui and n==8 then return qword(ui)end
        if at==manager+0x0C and n==32 then
            return b.encode(f.current,'u32')..string.rep('\0',24)..b.encode(f.depth,'u32')
        end
        error('outside fixed source/context/menu fixture reads')
    end
    io.invoke=function(...)
        assert(select('#',...)==5,'nil extra remains the fifth adapter argument')
        local entry,signature,arg1,arg2,arg3=...
        assert(entry==game_base+0x14C0350 and signature=='void (__fastcall *)(void *, int, void *)')
        assert(arg1==manager and arg2==5 and arg3==nil,'exact native GMH arguments')
        f.calls=f.calls+1
        if change=='call_error'then error('OWNED_CALL_ERROR',0)end
        if change~='not_opened'then f.current,f.depth=5,1 end
    end
    f.world={runtime=io,view={read=io.read},game=game_base,exe=exe_base}
    f.game={state=3,mission=false};f.adapter=io
    if change=='state'then f.game.state=2 end
    if change=='mission'then f.game.mission=true end
    f.probe=M.new({adapter=io})
    assert(f.calls==0 and f.reads==0 and f.hashes==0,'new/import performs no capture or request')
    return f
end
local cases=0
for _,case in ipairs({{'normal',true,'ARMORY_CURRENT_OBSERVED'},
    {'busy',false,'ARMORY_MENU_BUSY'},{'depth',false,'ARMORY_MENU_BUSY'},
    {'state',false,'ARMORY_WAITING_SHIP'},{'mission',false,'ARMORY_WAITING_SHIP'},
    {'native_state',false,'ARMORY_NATIVE_SHIP_CHANGED'},
    {'pin',false,'ARMORY_CODE_PIN_CHANGED'},{'fingerprint',false,'ARMORY_FINGERPRINT_MISMATCH'},
    {'not_opened',false,'ARMORY_NOT_OBSERVED'},{'call_error',false,'OWNED_CALL_ERROR'}})do
    local name,want_open,reason=unpack(case)
    local f=fixture(name);local r=f.probe:start(f.world,f.game)
    assert(r.reason==reason,name..': '..tostring(r.reason));assert(r.opened==want_open,name)
    local should_call=name=='normal'or name=='not_opened'or name=='call_error'
    assert(f.calls==(should_call and 1 or 0)and r.requested==should_call,name)
    if name=='normal'then
        assert(r.phase=='opened'and r.current_before==0 and r.depth_before==0
            and r.current_after==5 and r.depth_after==1 and r.calls==1)
    end
    if name=='state'or name=='mission'then assert(f.reads==0 and f.hashes==0)end
    if name=='fingerprint'then assert(f.hashes==2 and f.reads==0)end
    assert(not r.career_ready and not r.page_visibility_proven)
    local reads,hashes,calls=f.reads,f.hashes,f.calls
    f.current,f.depth,f.state,f.game.state,f.game.mission=0,0,3,3,false
    local again=f.probe:start(f.world,f.game)
    assert(again.reason==reason and f.reads==reads and f.hashes==hashes and f.calls==calls,'one shot including rejected/error')
    r.opened=not r.opened
    assert(f.probe:status().opened==want_open,'status snapshot is independent')
    cases=cases+1
end
print('PASS native-armory-probe '..cases..' owned cases; Game_accessed=false Game_calls=0 installed=false')
