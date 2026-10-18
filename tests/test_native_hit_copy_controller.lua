-- Exercise only the new continuous/copy-observer path using the existing fake
-- adapter. No Windows allocation/registration/CAS or Game execution.
local root=assert(arg[3])
local function file(path)local f=assert(io.open(root..'/'..path,'rb'));local v=f:read('*a');f:close();return v end
local text=file('tests/test_native_code_copy_probe.lua')
local before='src/native-code-copy-profile.lua'
local after='dist/native-six-code-copy-probe-owned-20261013/native-code-copy-profile.lua'
local out,pos={},1
while true do
    local a,c=text:find(before,pos,true)
    if not a then out[#out+1]=text:sub(pos);break end
    out[#out+1]=text:sub(pos,a-1);out[#out+1]=after;pos=c+1
end
text=table.concat(out)
text=text:gsub('req.size==0xB000','req.size==0xD000')
text=text:gsub('count==19','count==28'):gsub('n==0x9000','n==0xB000')
local cut=assert(text:find('local count=0',1,true))
local M,fixture,P=assert(loadstring(text:sub(1,cut-1)..'\nreturn M,fixture,P','=owned_copy_observer_fixture'))()
local link=assert(loadfile(root..'/src/native-hit-copy-link.lua'))()
local specs={
    {'contact_begin',0x13AD4E8,'e8c350efff',0x12A25B0},
    {'default_delta',0x129CABC,'f3410f5cc1'},
    {'custom_curve',0x129CADF,'e85cfeffff',0x129C940},
    {'normal_final',0x13AD88B,'e8a004efff',0x129DD30},
    {'physical_success',0x13B11D4,'32c088451c'},
    {'contact_end',0x13B053F,'488b8dc0240000'},
}
local function observers()
    local profile={revision='copy_pending_observer_v1',abi=1,record_bytes=96,sites={},entries={}}
    local handle={code_base=0x190020000,code_size=4096,addresses={},lifetime={functions_registered=true}}
    for i,s in ipairs(specs)do
        profile.sites[i]={name=s[1],rva=s[2],pin_hex=s[3],replace_bytes=#s[3]/2,original_rva=s[4]}
        profile.entries[i]={name=s[1],executable_length=64}
        handle.addresses[s[1]]=handle.code_base+(i-1)*128
    end
    return profile,handle
end
local f=fixture('normal');local prepared,handle=0
local original_pointer=f.world.view.pointer
f.world.view.pointer=function(at)if at==f.slot_address then return f.slot end;return original_pointer(at)end
f.probe=M.new({adapter=f.probe.adapter,clock=f.probe.clock_override,continuous=true,
    observer_factory=function(image)
        assert(f.reads==28 and f.bytes==35435 and f.cas_calls==0,'full source before observer preparation')
        assert(image.base==0x180000000 and image.size==0x4744000)
        prepared=prepared+1;local profile;profile,handle=observers();return profile,handle
    end,observer_link=link.link})
assert(prepared==0 and f.allocations==0 and f.cas_calls==0)
local r=f.probe:start(f.world,f.game)
assert(r.phase=='running'and r.observers_linked and r.continuous_observation and r.soft_window_seconds==0)
assert(prepared==1 and f.probe:observer_handle()==handle and handle.native_certified)
assert(r.reads==57 and r.bytes==70878 and r.runtime_function_count==28)
f.time=25;f.state=4;f.game.state=4;f.game.mission=true
r=f.probe:tick(f.world,f.game)
assert(r.phase=='running'and r.installed and f.cas_calls==1,'mission transition / two-second timer do not restore observation copy')
if arg[4]then
    f.slot=f.original+16;f.time=26
    r=f.probe:tick(f.world,f.game)
    assert(r.phase=='stopped'and r.reason=='CODE_COPY_DISPATCH_OWNER_CHANGED'
        and r.third_party_preserved and not r.restored and not r.cleanup_required)
    assert(f.slot==f.original+16 and f.probe:observer_handle()==nil and handle.native_certified)
    print('PASS native-hit-copy-controller continuous owner change: paused connector / foreign slot preserved')
    return
end
r=f.probe:stop('EXPLICIT_STOP')
assert(r.restored and not r.installed and f.slot==f.original and f.cas_calls==2)
assert(f.probe:observer_handle()==nil and handle.native_certified,'owned queue can still pause/final-drain')
local failed=fixture('normal');local calls=0
failed.probe=M.new({adapter=failed.probe.adapter,clock=failed.probe.clock_override,continuous=true,
    observer_factory=function()calls=calls+1;error('OWNED_FACTORY_FAILED',0)end,observer_link=link.link})
r=failed.probe:start(failed.world,failed.game)
assert(r.phase=='failed'and r.reason=='OWNED_FACTORY_FAILED'and calls==1)
assert(failed.cas_calls==0 and failed.registers==0 and failed.slot==failed.original)
assert(not pcall(M.new,{continuous=true}),'continuous requires six-region observer factory and linker')
print('PASS native-hit-copy-controller 3 focused cases; continuous mission / prepublication failure / missing observers')
