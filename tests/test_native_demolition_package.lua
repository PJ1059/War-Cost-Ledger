-- Inspect only our own allocations. Captured Game dispatch is never executed.
local root,sdk,fixture=assert(arg[1]),assert(arg[2]),dofile(assert(arg[3]))
package.preload['hd2runtime/core/bytes']=function()return dofile(sdk..'/core/bytes.lua')end
package.preload['hd2runtime/runtime/windows_ffi']=function()return dofile(sdk..'/runtime/windows_ffi.lua')end
local win=require('hd2runtime/runtime/windows_ffi');local ffi=win.ffi
local builder=dofile(root..'/src/native-hit-package.lua')
local h=builder.prepare(fixture.image,fixture.profile)
local function u32(at)return tonumber(ffi.cast('const uint32_t *',at)[0])end
local checked=0
for _,entry in ipairs(fixture.profile.entries)do
    local at=h.addresses[entry.name]
    for _,r in ipairs(entry.copy_rel32_relocations or {})do
        local disp=u32(at+r.offset);if disp>=2147483648 then disp=disp-4294967296 end
        local expected=r.target_rva and fixture.image.base+r.target_rva or h.addresses[r.address_key]
        assert(at+r.next_offset+disp==expected,'every copied CALL/RIP target remains exact')
        checked=checked+1
    end
end
assert(checked>=2)
local d=h.addresses.demolition_diagnostic
assert(d>=h.lifetime.data and d+64+32*128<=h.lifetime.data+h.lifetime.data_size)
assert(d%64==0 and u32(d)==32 and u32(d+4)==128)
assert(ffi.string(ffi.cast('const char *',d+8),64+4096-8)==string.rep('\0',64+4096-8))
assert(h.addresses.original_demolition_consumer==fixture.image.base+0x13E1DC0)
assert(h.addresses.destruction_world_global==fixture.image.base+0x346D528)
local dispatch
for _,e in ipairs(fixture.profile.entries)do if e.name=='demolition_dispatch'then dispatch=e end end
local r=assert(dispatch.copy_rel32_relocations[1])
local original=r.next_offset;r.next_offset=r.offset+3
local ok,why=pcall(builder.prepare,fixture.image,fixture.profile)
assert(not ok and tostring(why):find('native copied relocation extent',1,true))
r.next_offset=original
local original_rva,original_key=r.target_rva,r.address_key
r.target_rva=fixture.image.size;r.address_key=nil
ok,why=pcall(builder.prepare,fixture.image,fixture.profile)
assert(not ok and tostring(why):find('native copied image target',1,true))
r.target_rva,r.address_key=original_rva,original_key
print('PASS demolition private package: '..checked..' exact rel32 targets, dedicated zeroed data, invalid extent/target rejected; no Game access/captured-code execution')
