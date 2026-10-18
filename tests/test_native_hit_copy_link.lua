-- Link real six-region source/reference data into owned synthetic addresses.
local runtime,root=assert(arg[1]),assert(arg[2])
table.insert(package.loaders,2,function(name)
    if name:sub(1,11)=='hd2runtime/'then return assert(loadfile(runtime..'/'..name:sub(12)..'.lua'))end
end)
local function file(path)local f=assert(io.open(root..'/'..path,'rb'));local v=f:read('*a');f:close();return v end
local b=require('hd2runtime/core/bytes')
local profile_dir='dist/native-six-code-copy-probe-owned-20261013/'
local P=assert(loadfile(root..'/'..profile_dir..'native-code-copy-profile.lua'))()
local text=file('src/native-code-copy-probe.lua')
text=text:gsub('__NATIVE_CODE_COPY_PROFILE__',function()return'(function()\n'..file(profile_dir..'native-code-copy-profile.lua')..'\nend)()'end)
local copy=assert(loadstring(text))()
local link=assert(loadfile(root..'/src/native-hit-copy-link.lua'))()
local specs={
    {'contact_begin',3,0x13AD4E8,'e8c350efff',0x12A25B0},
    {'default_delta',4,0x129CABC,'f3410f5cc1'},
    {'custom_curve',4,0x129CADF,'e85cfeffff',0x129C940},
    {'normal_final',3,0x13AD88B,'e8a004efff',0x129DD30},
    {'physical_success',6,0x13B11D4,'32c088451c'},
    {'contact_end',3,0x13B053F,'488b8dc0240000'},
}
local function fixture()
    local sources={};for i,r in ipairs(P.regions)do sources[i]=b.unhex(r.hex)end
    local profile={revision='copy_pending_observer_v1',abi=1,record_bytes=96,sites={},entries={}}
    local handle={code_base=0x190020000,code_size=4096,addresses={},lifetime={functions_registered=true}}
    for i,s in ipairs(specs)do
        profile.sites[i]={name=s[1],rva=s[3],pin_hex=s[4],replace_bytes=#s[4]/2,original_rva=s[5]}
        profile.entries[i]={name=s[1],executable_length=64}
        handle.addresses[s[1]]=handle.code_base+(i-1)*128
    end
    return copy.prepare(0x180000000,0x190000000),profile,handle,sources
end
local plan,profile,handle,sources=fixture()
local original={};for i,raw in ipairs(plan.regions)do original[i]=raw end
local linked=link.link(plan,profile,handle,sources,P.regions)
assert(linked==plan and linked.observers_linked and#linked.observer_sites==6)
for i,s in ipairs(specs)do
    local offset=s[3]-P.regions[s[2]].rva
    local raw=plan.regions[s[2]]
    assert(raw:byte(offset+1)==232)
    local relative=b.u32(raw,offset+1);if relative>=2147483648 then relative=relative-4294967296 end
    assert(plan.layout[s[2]]+offset+5+relative==handle.addresses[s[1]],'six actual CALL targets')
    if s[1]=='contact_end'then assert(raw:sub(offset+6,offset+7)=='\144\144')end
    -- Undo exactly these patches, then compare every code byte with the mapper.
    local before=original[s[2]]
    plan.regions[s[2]]=raw:sub(1,offset)..before:sub(offset+1,offset+#s[4]/2)..raw:sub(offset+#s[4]/2+1)
end
for i,raw in ipairs(plan.regions)do assert(raw==original[i],'no bytes outside six sites change')end
local function reject_last_site(mutate)
    local p,pr,h,src=fixture();local before=table.concat(p.regions)
    mutate(pr,h,src)
    assert(not pcall(link.link,p,pr,h,src,P.regions))
    assert(table.concat(p.regions)==before,'all sites validate before any plan mutation')
end
reject_last_site(function(pr,h)h.addresses.contact_end=h.code_base+h.code_size end)
reject_last_site(function(pr,h,src)
    local at=0x13B053F-P.regions[3].rva
    src[3]=src[3]:sub(1,at)..'\0'..src[3]:sub(at+2)
end)
print('PASS native-hit-copy-link 3 focused cases; six CALLs exact / no Game memory or native APIs')
