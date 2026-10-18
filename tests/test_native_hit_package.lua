-- Own-process allocations only. Image base is a fixture allocation, not game.dll.
local root,sdk,fixture=assert(arg[1]),assert(arg[2]),dofile(assert(arg[3]))
package.preload['hd2runtime/core/bytes']=function()return dofile(sdk..'/core/bytes.lua')end
package.preload['hd2runtime/runtime/windows_ffi']=function()return dofile(sdk..'/runtime/windows_ffi.lua')end
local win=require('hd2runtime/runtime/windows_ffi');local ffi=win.ffi
local package_builder=dofile(root..'/src/native-hit-package.lua')
local package=package_builder.prepare(fixture.image,fixture.profile)
assert(package.native_certified==false and package.lifetime.functions_registered and not package.lifetime.patched)
local count=#fixture.profile.entries
if fixture.profile.living_target_filter then
    assert(package.addresses.health_manager_global==fixture.image.base+0x3326688)
    assert(package.addresses.health_alive and package.addresses.qualifier_types)
end
if fixture.profile.damage_id_extension then
    assert(package.addresses.qualifier_prior and package.addresses.damage_info_types)
    local ids=fixture.profile.data_tables.damage_info_types
    local native=ffi.cast('uint64_t *',package.addresses.damage_info_types)
    for i,value in ipairs(ids)do assert(tonumber(native[i-1])==tonumber(value,16))end
    local saved=ids[2];ids[2]=ids[1]
    local ok,why=pcall(package_builder.prepare,fixture.image,fixture.profile)
    ids[2]=saved
    assert(not ok and tostring(why):find('native damage ID order',1,true))
end
local table=ffi.cast('HD2LedgerRuntimeFunction *',package.lifetime.function_table)
local lookup_address=win.kernel.GetProcAddress(win.kernel.GetModuleHandleA('ntdll.dll'),'RtlLookupFunctionEntry')
local lookup=ffi.cast(win.fn('void *(*)(uint64_t,uint64_t *,void *)'),lookup_address)
local image_out=ffi.new('uint64_t[1]')
for i,entry in ipairs(fixture.profile.entries)do
    local at=package.addresses[entry.name]
    local found=lookup(ffi.new('uint64_t',at),image_out,nil)
    assert(found~=nil and tonumber(image_out[0])==package.code_base)
    assert(tonumber(ffi.cast('uintptr_t',found))==package.lifetime.function_table+12*(i-1))
    assert(table[i-1]['end']>table[i-1].begin and table[i-1].unwind<package.code_size)
end
local region=ffi.new('HD2RuntimeMemoryRegion[1]')
assert(win.kernel.VirtualQuery(ffi.cast('void *',package.code_base),region,ffi.sizeof(region[0]))==ffi.sizeof(region[0]))
assert(tonumber(region[0].protection)==0x20 and tonumber(region[0].type)==0x20000)
local peer=ffi.new('uint64_t[1]');local epoch=ffi.new('uint64_t[1]',7)
ffi.copy(peer,string.char(0x10,0x32,0x54,0x76,0x98,0xBA,0xDC,0xFE),8)
local configure=ffi.cast(win.fn('uint32_t (*)(void *,void *,uint64_t,uint64_t,uint32_t)'),package.configure)
assert(configure(ffi.cast('void *',package.bridge),ffi.cast('void *',package.arena),epoch[0],peer[0],1)==1)
local record=ffi.new('uint8_t[96]')
ffi.copy(record+8,epoch,8);ffi.copy(record+16,peer,8)
ffi.cast('uint32_t *',record+60)[0]=1
ffi.cast('float *',record+64)[0]=4;ffi.cast('float *',record+68)[0]=3
ffi.cast('float *',record+72)[0]=1;ffi.cast('float *',record+92)[0]=1
ffi.cast('uint32_t *',record+84)[0]=1;ffi.cast('uint32_t *',record+88)[0]=511
local publish=ffi.cast(win.fn('uint32_t (*)(void *,void *)'),package.addresses.publish)
for _=1,66 do assert(publish(ffi.cast('void *',package.bridge),record)==1)end
-- Only the fixture grants the certificate: no actual sites were patched.
package.native_certified=true
local seen=0
local connector=dofile(root..'/src/native-hit-connector.lua')
local decoder=dofile(root..'/src/native-hit-feedback.lua')
local consumer=assert(connector.attach(package,{peer='FEDCBA9876543210',epoch='0000000000000007',decoder=decoder,
    accept=function(c)assert(c.result=='full_penetration');seen=seen+c.count;return true end}))
assert(consumer:step(10) and seen==64 and consumer.records==64)
assert(consumer:step(10.1) and seen==66 and consumer.records==66)
assert(consumer:step(10.2) and seen==66)
ffi.cast('uint64_t *',package.arena+32)[0]=1 -- owned diagnostic counter fixture
assert(consumer:step(10.3) and consumer.decoder.partial and consumer.rejected=='0000000000000001')
assert(connector.configure(package,'FEDCBA9876543210','0000000000000007',false))
consumer:detach()
-- BOOLEAN is one byte. A failing native export can leave EAX=0x100 (AL=0).
-- Reading it as an int would falsely certify an unregistered function table.
local actual_kernel=win.kernel
win.kernel=setmetatable({GetProcAddress=function(module,name)
    if name=='RtlAddFunctionTable' then return ffi.cast('void *',fixture.rtl_add_failure) end
    return actual_kernel.GetProcAddress(module,name)
end},{__index=function(_,name)return actual_kernel[name]end})
local failing_builder=dofile(root..'/src/native-hit-package.lua')
local ok,why=pcall(function()return failing_builder.prepare(fixture.image,fixture.profile)end)
win.kernel=actual_kernel
assert(not ok and tostring(why):find('native function%-table registration failed'))
print('PASS private RX/RW package, explicit relocations and '..count..' real registered native function entries')
print('PASS LuaJIT calls configured native publisher/drain; 66 records split 64+2 without replay; no game patch')
print('PASS BOOLEAN AL=0 failure with nonzero upper EAX never certifies function registration')
