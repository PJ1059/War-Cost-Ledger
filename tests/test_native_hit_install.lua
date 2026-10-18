-- Execute the production Lua adapter on private pages in this tool process.
local root,sdk,fixture=assert(arg[1]),assert(arg[2]),dofile(assert(arg[3]))
package.preload['hd2runtime/core/bytes']=function()return dofile(sdk..'/core/bytes.lua')end
package.preload['hd2runtime/runtime/windows_ffi']=function()return dofile(sdk..'/runtime/windows_ffi.lua')end
local win=require('hd2runtime/runtime/windows_ffi');local ffi=win.ffi
local builder=dofile(root..'/src/native-hit-package.lua')
local installer=dofile(root..'/src/native-hit-install.lua')
local bytes=require('hd2runtime/core/bytes')
local handle=builder.prepare(fixture.image,fixture.profile)
local function proves(at,pin)return ffi.string(ffi.cast('void *',at),#pin/2)==bytes.unhex(pin)end
local plan=assert(installer.plan(fixture.image,fixture.profile,handle,proves))
local installed,why,evidence=installer.execute(plan,handle,fixture.transaction)
assert(installed==handle,tostring(why))
assert(evidence.result==0 and evidence.rollback_failures==0 and evidence.resume_failures==0 and evidence.enum_failures==0)
assert(evidence.enumerated==evidence.thread_count+1 and evidence.patched==7 and plan.mutated)
assert(handle.native_certified and handle.lifetime.patched)
for _,patch in ipairs(plan.patches)do
    assert(ffi.string(ffi.cast('void *',patch.address),patch.length)==patch.replacement)
end
local control=dofile(root..'/src/native-hit-connector.lua')
assert(control.configure(handle,'FEDCBA9876543210','0000000000000007',true))
assert(control.pause(handle,'FEDCBA9876543210','0000000000000007'))
assert(not control.resume(handle,'FEDCBA9876543210','0000000000000008'))
assert(control.resume(handle,'FEDCBA9876543210','0000000000000007'))
assert(control.pause(handle,'FEDCBA9876543210','0000000000000007'))
local reverse={patches={},mutated=false}
for _,patch in ipairs(plan.patches)do
    reverse.patches[#reverse.patches+1]={address=patch.address,length=patch.length,
        expected=patch.replacement,replacement=patch.expected}
end
local restored,restore_reason,restored_evidence=installer.execute(reverse,handle,fixture.transaction)
assert(restored==handle,tostring(restore_reason))
assert(restored_evidence.result==0 and restored_evidence.rollback_failures==0 and restored_evidence.resume_failures==0)
for _,patch in ipairs(plan.patches)do assert(proves(patch.address,fixture.profile.sites[_].pin_hex))end
local bad={patches={},mutated=false}
for i,patch in ipairs(plan.patches)do
    bad.patches[i]={address=patch.address,length=patch.length,expected=patch.expected,replacement=patch.replacement}
end
bad.patches[1].expected=string.rep('\0',bad.patches[1].length)
local absent,reason,rejected=installer.execute(bad,handle,fixture.transaction)
assert(not absent and rejected.result==6 and rejected.suspended==0 and rejected.patched==0)
assert(rejected.rollback_failures==0 and rejected.resume_failures==0)
print('PASS production Lua private package -> preprepared all-current-process threads -> native seven-site install/restore')
print('PASS '..evidence.thread_count..' own-host worker threads; full set '..evidence.enumerated..'; actual end span six bytes')
print('PASS connector pause/resume preserves identity, wrong epoch refused; changed site rejects before suspension')
