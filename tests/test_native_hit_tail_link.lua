-- Link the actual seven-site diagnostic profile into synthetic owned addresses.
local runtime,root,observer_path=assert(arg[1]),assert(arg[2]),assert(arg[3])
table.insert(package.loaders,2,function(name)
    if name:sub(1,11)=='hd2runtime/'then return assert(loadfile(runtime..'/'..name:sub(12)..'.lua'))end
end)
local function file(path)local f=assert(io.open(root..'/'..path,'rb'));local v=f:read('*a');f:close();return v end
local b=require('hd2runtime/core/bytes')
local P=assert(loadfile(root..'/dist/native-six-code-copy-probe-owned-20261013/native-code-copy-profile.lua'))()
local code=file('src/native-code-copy-probe.lua'):gsub('__NATIVE_CODE_COPY_PROFILE__',function()
    return'(function()\n'..file('dist/native-six-code-copy-probe-owned-20261013/native-code-copy-profile.lua')..'\nend)()'
end)
local copy=assert(loadstring(code))()
local linker=assert(loadfile(root..'/src/native-hit-copy-link.lua'))()
local function fixture()
    local profile=assert(loadfile(observer_path))()
    assert(profile.revision=='copy_pending_tail_diagnostic_v1'and#profile.sites==7)
    local handle={code_base=0x190020000,code_size=65536,addresses={},lifetime={functions_registered=true}}
    local offset=0
    for _,entry in ipairs(profile.entries)do
        offset=math.floor((offset+15)/16)*16
        handle.addresses[entry.name]=handle.code_base+offset
        offset=offset+#entry.code_hex/2
    end
    assert(offset<=65536)
    local source={};for i,r in ipairs(P.regions)do source[i]=b.unhex(r.hex)end
    return copy.prepare(0x180000000,0x190000000),profile,handle,source
end
local plan,profile,handle,source=fixture()
local original={};for i,raw in ipairs(plan.regions)do original[i]=raw end
assert(linker.link(plan,profile,handle,source,P.regions)==plan and#plan.observer_sites==7)
for _,site in ipairs(profile.sites)do
    local region=(site.name=='physical_success'or site.name=='physical_alt_tail')and 6
        or(site.name=='default_delta'or site.name=='custom_curve')and 4 or 3
    local offset=site.rva-P.regions[region].rva
    local raw=plan.regions[region]
    assert(raw:byte(offset+1)==232)
    local displacement=b.u32(raw,offset+1)
    if displacement>=2147483648 then displacement=displacement-4294967296 end
    assert(plan.layout[region]+offset+5+displacement==handle.addresses[site.name])
    local before=original[region]
    plan.regions[region]=raw:sub(1,offset)..before:sub(offset+1,offset+site.replace_bytes)..raw:sub(offset+site.replace_bytes+1)
end
for i,raw in ipairs(plan.regions)do assert(raw==original[i],'only seven exact sites changed')end

local function reject(mutate)
    local p,pr,h,s=fixture();local before=table.concat(p.regions)
    mutate(pr,h,s)
    assert(not pcall(linker.link,p,pr,h,s,P.regions))
    assert(table.concat(p.regions)==before,'all seven validate before mutation')
end
reject(function(pr,h,s)
    local at=0x13B11C8-P.regions[6].rva
    s[6]=s[6]:sub(1,at)..'\0'..s[6]:sub(at+2)
end)
reject(function(pr,h)h.addresses.physical_alt_tail=h.code_base+h.code_size end)
print('PASS diagnostic seven-site actual profile: exact CALLs and byte conservation; alternate PIN/range rejects atomic')
