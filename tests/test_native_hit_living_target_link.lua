-- Real 8-site/26-entry living-target profile, linked into owned byte copies.
-- No copied instruction, Game memory, Windows API or native function executes.
local runtime,root,observer_path=assert(arg[1]),assert(arg[2]),assert(arg[3])
table.insert(package.loaders,2,function(name)
    if name:sub(1,11)=='hd2runtime/'then return assert(loadfile(runtime..'/'..name:sub(12)..'.lua'))end
end)
local function file(path)local f=assert(io.open(root..'/'..path,'rb'));local v=f:read('*a');f:close();return v end
local b=require('hd2runtime/core/bytes')
local P=dofile(root..'/src/native-code-copy-profile.lua')
local text=file('src/native-code-copy-probe.lua'):gsub('__NATIVE_CODE_COPY_PROFILE__',function()
    return '(function()\n'..file('src/native-code-copy-profile.lua')..'\nend)()'
end)
local copy=assert(loadstring(text))()
local link=dofile(root..'/src/native-hit-copy-link.lua')
local function fixture()
    local profile=dofile(observer_path)
    assert(profile.revision=='copy_pending_living_target_observer_v1'and profile.abi==1
        and profile.record_bytes==96 and #profile.sites==8 and #profile.entries==26)
    assert(profile.living_target_filter.preserves_killing_hit==true
        and profile.living_target_filter.commit_rechecks_life==false)
    local handle={code_base=0x190020000,code_size=65536,addresses={},lifetime={functions_registered=true}}
    local offset=0
    for _,entry in ipairs(profile.entries)do
        offset=math.floor((offset+15)/16)*16
        handle.addresses[entry.name]=handle.code_base+offset
        offset=offset+#entry.code_hex/2
    end
    assert(offset<=handle.code_size and handle.addresses.health_alive and handle.addresses.qualifier_types)
    local source={};for i,r in ipairs(P.regions)do source[i]=b.unhex(r.hex)end
    return copy.prepare(0x180000000,0x190000000),profile,handle,source
end
local plan,profile,handle,source=fixture()
local original={};for i,raw in ipairs(plan.regions)do original[i]=raw end
assert(link.link(plan,profile,handle,source,P.regions)==plan)
assert(plan.observers_linked and #plan.observer_sites==9,'eight hit sites plus bounded demolition dispatch')
for _,site in ipairs(plan.observer_sites)do
    local region=site.name=='demolition_dispatch'and 2
        or(site.name=='physical_success'or site.name=='physical_alt_tail')and 6
        or(site.name=='default_delta'or site.name=='custom_curve')and 4 or 3
    local offset=site.copy_pc-plan.layout[region]
    local raw=plan.regions[region]
    local relative=b.u32(raw,offset+1);if relative>=2147483648 then relative=relative-4294967296 end
    assert(raw:byte(offset+1)==232 and site.copy_pc+5+relative==handle.addresses[site.name],
        'every actual CALL targets its registered owned entry')
    plan.regions[region]=raw:sub(1,offset)..original[region]:sub(offset+1,offset+site.length)..raw:sub(offset+site.length+1)
end
for i,raw in ipairs(plan.regions)do assert(raw==original[i],'only the nine exact sites change')end
local rejects=0
local function reject(mutate,reason)
    local p,pr,h,s=fixture();local before=table.concat(p.regions)
    mutate(pr,h,s)
    local ok,err=pcall(link.link,p,pr,h,s,P.regions)
    assert(not ok and tostring(err):find(reason,1,true),'expected rejection '..reason)
    assert(table.concat(p.regions)==before,'all contracts validate before plan mutation')
    rejects=rejects+1
end
reject(function(pr)pr.revision='copy_pending_living_target_observer_v2'end,'HIT_COPY_OBSERVER_PROFILE')
reject(function(pr)table.remove(pr.sites)end,'HIT_COPY_OBSERVER_PROFILE')
reject(function(pr)pr.sites[9]=pr.sites[8]end,'HIT_COPY_OBSERVER_PROFILE')
reject(function(pr)pr.abi=2 end,'HIT_COPY_OBSERVER_PROFILE')
reject(function(pr)pr.record_bytes=128 end,'HIT_COPY_OBSERVER_PROFILE')
reject(function(pr)pr.sites[8].rva=pr.sites[8].rva+1 end,'HIT_COPY_SITE_CONTRACT')
reject(function(pr,h)h.addresses.reflection_writeback=h.code_base+h.code_size end,'HIT_COPY_GATEWAY_NOT_OWNED')
reject(function(pr)pr.entries[26].name=pr.entries[1].name end,'HIT_COPY_ENTRY_DUPLICATE')
reject(function(pr,h,s)
    local at=0x13AE6BC-P.regions[3].rva;s[3]=s[3]:sub(1,at)..'\0'..s[3]:sub(at+2)
end,'HIT_COPY_SOURCE_SITE_CHANGED')
reject(function(pr,h,s)
    local at=0xAB5FFE-P.regions[2].rva;s[2]=s[2]:sub(1,at)..'\0'..s[2]:sub(at+2)
end,'HIT_COPY_SOURCE_SITE_CHANGED')
print('PASS living-target link: actual 8-site/26-entry profile, nine exact private CALLs, byte conservation, '..rejects..' atomic protocol rejects')
