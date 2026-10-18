local make=dofile(assert(arg[1]));local profile=dofile(assert(arg[2])).profile
local base=0x10000000
local package={code_base=base+0x5000000,code_size=0x10000,addresses={},lifetime={functions_registered=true}}
for i,site in ipairs(profile.sites)do package.addresses[site.name]=package.code_base+i*512 end
local reads=0
local function proves(at,pin)
    reads=reads+1
    for _,site in ipairs(profile.sites)do if at==base+site.rva then return pin==site.pin_hex end end
    return false
end
local plan=assert(make.plan({base=base,size=0x4744000},profile,package,proves))
assert(reads==7 and #plan.patches==7 and #plan.pages==3 and plan.mutated==false)
for _,patch in ipairs(plan.patches)do
    assert(#patch.expected==patch.length and #patch.replacement==patch.length and patch.replacement:byte(1)==0xE8)
    local b={patch.replacement:byte(2,5)};local delta=b[1]+b[2]*256+b[3]*65536+b[4]*16777216
    if delta>=2147483648 then delta=delta-4294967296 end
    assert(patch.address+5+delta==package.addresses[patch.name])
    if patch.name=='iteration_end' then assert(patch.length==6 and patch.replacement:byte(6)==0x90)end
end
assert(make.plan({base=base,size=0x4744000},profile,package,function()return false end)==nil)
package.addresses.ap_result=package.code_base+package.code_size
assert(make.plan({base=base,size=0x4744000},profile,package,proves)==nil)
print('PASS seven exact CALL plans, 6-byte end span, signed rel32, three pages and changed-site refusal; no writes')
