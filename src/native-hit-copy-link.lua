-- Pure linking of fixed observers into private, same-offset code copies.
-- Never reads or writes Game memory and never calls a native function.
local M={}
local SITES={
    {name='contact_begin',region=3,rva=0x13AD4E8,pin='e8c350efff',original=0x12A25B0},
    {name='default_delta',region=4,rva=0x129CABC,pin='f3410f5cc1'},
    {name='custom_curve',region=4,rva=0x129CADF,pin='e85cfeffff',original=0x129C940},
    {name='normal_final',region=3,rva=0x13AD88B,pin='e8a004efff',original=0x129DD30},
    {name='physical_success',region=6,rva=0x13B11D4,pin='32c088451c'},
    {name='contact_end',region=3,rva=0x13B053F,pin='488b8dc0240000'},
}
local ALT_SITE={name='physical_alt_tail',region=6,rva=0x13B11C8,pin='b00188451c'}
local REFLECTION_SITE={name='reflection_writeback',region=3,rva=0x13AE6BC,pin='f3440f5807'}
local DEMOLITION_SITE={name='demolition_dispatch',region=2,rva=0xAB5FFE,pin='e89d1b9400',original=0x13F7BA0}
local function address(v)return type(v)=='number'and v>=65536 and v<140737488355328 and v%1==0 end
local function unhex(raw)return(raw:gsub('..',function(pair)return string.char(tonumber(pair,16))end))end
local function rel32(v)
    assert(v%1==0 and v>=-2147483648 and v<=2147483647,'HIT_COPY_CALL_DISPLACEMENT')
    if v<0 then v=v+4294967296 end
    local out={}
    for i=1,4 do out[i]=string.char(v%256);v=math.floor(v/256)end
    return table.concat(out)
end

function M.link(plan,profile,handle,source,regions)
    assert(type(plan)=='table'and plan.RF_count==28 and type(plan.layout)=='table'
        and#plan.layout==6 and type(plan.regions)=='table'and#plan.regions==6,'HIT_COPY_SIX_PLAN')
    local reflection=type(profile)=='table'and(profile.revision=='copy_pending_reflection_observer_v1'
        or profile.revision=='copy_pending_living_target_observer_v1')
    local diagnostic=reflection or type(profile)=='table'and(profile.revision=='copy_pending_tail_diagnostic_v1'
        or profile.revision=='copy_pending_normal_result_guard_v1')
    local site_count=reflection and 8 or diagnostic and 7 or 6
    assert(type(profile)=='table'and(diagnostic or profile.revision=='copy_pending_observer_v1')
        and profile.abi==1 and profile.record_bytes==96 and type(profile.sites)=='table'
        and#profile.sites==site_count and type(profile.entries)=='table','HIT_COPY_OBSERVER_PROFILE')
    assert(type(handle)=='table'and type(handle.addresses)=='table'
        and type(handle.lifetime)=='table'and handle.lifetime.functions_registered==true
        and address(handle.code_base)and type(handle.code_size)=='number'
        and handle.code_size>0 and handle.code_size<=65536,'HIT_COPY_OBSERVER_OWNED_CODE')
    assert(type(source)=='table'and#source==6 and type(regions)=='table'and#regions==6,'HIT_COPY_SOURCE')
    local entries={}
    for _,entry in ipairs(profile.entries)do
        assert(type(entry.name)=='string'and not entries[entry.name],'HIT_COPY_ENTRY_DUPLICATE')
        entries[entry.name]=entry
    end
    local demolition=profile.demolition_diagnostic~=nil
    if demolition then
        assert(reflection and type(profile.demolition_site)=='table'
            and profile.demolition_diagnostic.revision==1,'HIT_COPY_DEMOLITION_PROFILE')
    else assert(profile.demolition_site==nil,'HIT_COPY_DEMOLITION_PROFILE')end
    local changes,patches={},{}
    for index=1,site_count+(demolition and 1 or 0) do
        local expected=index>site_count and DEMOLITION_SITE
            or SITES[index]or(index==7 and ALT_SITE or REFLECTION_SITE)
        local site=index>site_count and profile.demolition_site or profile.sites[index]
        assert(site.name==expected.name and site.rva==expected.rva and site.pin_hex==expected.pin
            and site.replace_bytes==#expected.pin/2 and site.original_rva==expected.original,'HIT_COPY_SITE_CONTRACT')
        local region=regions[expected.region]
        local offset=site.rva-region.rva
        local pin=unhex(expected.pin)
        assert(type(source[expected.region])=='string'and type(plan.regions[expected.region])=='string'
            and#source[expected.region]==region.length and#plan.regions[expected.region]==region.length
            and offset>=0 and offset+#pin<=region.length
            and source[expected.region]:sub(offset+1,offset+#pin)==pin,'HIT_COPY_SOURCE_SITE_CHANGED')
        local entry=assert(entries[site.name],'HIT_COPY_GATEWAY_MISSING')
        local target=handle.addresses[site.name]
        assert(address(target)and type(entry.executable_length)=='number'and entry.executable_length>0
            and entry.executable_length<=4096 and entry.executable_length%1==0
            and target>=handle.code_base and target+entry.executable_length<=handle.code_base+handle.code_size,
            'HIT_COPY_GATEWAY_NOT_OWNED')
        local pc=plan.layout[expected.region]+offset
        assert(address(pc),'HIT_COPY_SITE_ADDRESS')
        local patch='\232'..rel32(target-(pc+5))..string.rep('\144',#pin-5)
        patches[#patches+1]={region=expected.region,offset=offset,raw=patch}
        changes[#changes+1]={name=site.name,copy_pc=pc,target=target,length=#pin}
    end
    for _,patch in ipairs(patches)do
        local raw=plan.regions[patch.region]
        plan.regions[patch.region]=raw:sub(1,patch.offset)..patch.raw..raw:sub(patch.offset+#patch.raw+1)
        assert(#plan.regions[patch.region]==#raw,'HIT_COPY_LENGTH_CHANGED')
    end
    plan.observer_sites=changes
    plan.observers_linked=true
    return plan
end
return M
