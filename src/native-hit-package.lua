-- Prepare private native pages; never writes a game instruction or pauses a thread.
-- The copy linker must prove the matching image and all fixed sites before use.
local win=require('hd2runtime/runtime/windows_ffi')
local ffi,kernel=win.ffi,win.kernel
local M={image_size=0x4744000,entity_manager_rva=0x346BF98,current_user_rva=0x347CEF0}
local function integer(n,max)return type(n)=='number' and n>=0 and n<=max and n%1==0 end
local function address(n)return integer(n,140737488355327) and n>=65536 end
local function align(n,a)return math.floor((n+a-1)/a)*a end
local function unhex(s)
    assert(type(s)=='string' and #s%2==0 and not s:find('[^%x]'),'invalid native bytes')
    return (s:gsub('..',function(pair)return string.char(tonumber(pair,16))end))
end
local function procedure(module,name,signature)
    local handle=kernel.GetModuleHandleA(module)
    local p=handle~=nil and kernel.GetProcAddress(handle,name) or nil
    assert(p~=nil,'native system export unavailable: '..name)
    return ffi.cast(win.fn(signature),p)
end
if not rawget(_G,'HD2LedgerHitMemoryTypesV1') then
    ffi.cdef[[
        typedef struct HD2LedgerAddressRequirements {void *lowest;void *highest;size_t alignment;} HD2LedgerAddressRequirements;
        typedef struct HD2LedgerExtendedParameter {uint64_t type;void *pointer;} HD2LedgerExtendedParameter;
        typedef struct HD2LedgerRuntimeFunction {uint32_t begin;uint32_t end;uint32_t unwind;} HD2LedgerRuntimeFunction;
    ]]
    rawset(_G,'HD2LedgerHitMemoryTypesV1',true)
end
assert(ffi.sizeof('HD2LedgerAddressRequirements')==24 and ffi.sizeof('HD2LedgerExtendedParameter')==16)
assert(ffi.sizeof('HD2LedgerRuntimeFunction')==12)
local allocate=procedure('kernel32.dll','VirtualAlloc','void *(*)(void *,size_t,uint32_t,uint32_t)')
local allocate_near=procedure('KernelBase.dll','VirtualAlloc2',
    'void *(*)(void *,void *,size_t,uint32_t,uint32_t,const HD2LedgerExtendedParameter *,uint32_t)')
local protect=procedure('kernel32.dll','VirtualProtect','int (*)(void *,size_t,uint32_t,uint32_t *)')
local flush=procedure('kernel32.dll','FlushInstructionCache','int (*)(void *,const void *,size_t)')
local add_functions=procedure('ntdll.dll','RtlAddFunctionTable','uint8_t (*)(HD2LedgerRuntimeFunction *,uint32_t,uint64_t)')
local lifetimes=rawget(_G,'HD2WarCostLedgerNativePagesV1') or {}
rawset(_G,'HD2WarCostLedgerNativePagesV1',lifetimes)

function M.prepare(image,profile)
    assert(type(image)=='table' and address(image.base) and image.base%4096==0 and image.size==M.image_size,
        'native package requires the proven matching image identity')
    assert(type(profile)=='table' and profile.abi==1 and profile.record_bytes==96
        and profile.arena_capacity==32 and profile.arena_row_bytes==640
        and profile.max_drain==64 and type(profile.entries)=='table' and #profile.entries<=32,
        'native package profile contract changed')
    local layouts,keys,offset={}, {},0
    for _,entry in ipairs(profile.entries)do
        assert(type(entry.name)=='string' and not keys[entry.name],'duplicate native entry')
        local raw,uw=unhex(entry.code_hex),unhex(entry.unwind_hex)
        assert(#raw>0 and #raw<=4096 and #uw>=4 and #uw<=256 and entry.entry_offset==0
            and integer(entry.executable_length,#raw) and entry.executable_length>0,'native entry bounds')
        offset=align(offset,16)
        local item={entry=entry,raw=raw,uw=uw,offset=offset}
        layouts[#layouts+1]=item;keys[entry.name]=item
        offset=offset+#raw
    end
    assert(keys.publish and keys.drain and keys.configure and keys.qualifier,'incomplete native package')
    for _,item in ipairs(layouts)do offset=align(offset,4);item.unwind_offset=offset;offset=offset+#item.uw end
    local table_offset=align(offset,4)
    local code_size=align(table_offset+12*#layouts,4096)
    assert(code_size<=65536,'native code package cap')
    local tables=assert(profile.data_tables,'native type tables missing')
    local data_size=64+1024*96+64+32*640
    local data_offsets={}
    local table_names={'enemy_types','source_types'}
    if profile.damage_id_extension~=nil then
        local damage=profile.damage_id_extension
        assert(damage.revision==1 and damage.record_offset==36 and damage.capture_flag==512
            and damage.attribution_only_flag==1024 and damage.damage_table=='DamageInfoType'
            and damage.concrete_hit_offset==12 and damage.concrete_hit_stride==200
            and damage.attribution_only_hit_count==0 and keys.qualifier_prior,
            'native damage ID extension contract')
        table_names[#table_names+1]='damage_info_types'
    else assert(tables.damage_info_types==nil,'native damage ID extension missing')end
    if profile.projectile_id_extension~=nil then
        local projectile=profile.projectile_id_extension
        assert(profile.damage_id_extension and projectile.revision==1
            and projectile.record_offset==32 and projectile.capture_flag==2048
            and projectile.native_table=='ProjectileType'and projectile.native_type_min==1
            and projectile.native_type_bound==351 and projectile.slot_bound==2048
            and projectile.system_type_array_offset==0xE5040
            and projectile.original_parent_rbp_save_offset==0x130
            and projectile.expected_parent_rbp_from_savebase==0x240
            and projectile.slot_from_parent_rbp==-0x58 and projectile.slot_high32_zero==true
            and projectile.matching_hit_base==0x4D040 and projectile.matching_hit_stride==200
            and projectile.reflection_preserves_typed_value==true
            and projectile.failed_metadata_keeps_damage_info==true
            and projectile.legacy_slot_requires_absent_flag==true
            and projectile.new_hook_sites==0 and projectile.qualifier_unchanged==true,
            'native projectile ID extension contract')
    end
    for _,name in ipairs(table_names)do
        local values=assert(tables[name],'native type table missing')
        assert(type(values)=='table' and #values>0 and #values<=1024,'native type table cap')
        if name=='damage_info_types'then
            assert(#values==profile.damage_id_extension.damage_info_count,'native damage ID count')
            local previous=0
            for _,value in ipairs(values)do
                assert(type(value)=='string'and#value==16 and value:sub(1,8)=='00000000'
                    and not value:find('[^%x]'),'native damage ID encoding')
                local id=tonumber(value,16)
                assert(integer(id,4095)and id>previous,'native damage ID order')
                previous=id
            end
        end
        data_size=align(data_size,8);data_offsets[name]=data_size
        data_size=data_size+#values*8
    end
    local demolition=profile.demolition_diagnostic
    local demolition_offset
    if demolition~=nil then
        assert(type(demolition)=='table' and demolition.revision==1 and demolition.header_bytes==64
            and demolition.record_bytes==128 and demolition.capacity==32
            and keys.demolition_dispatch and keys.demolition_consumer_wrapper and keys.demolition_drain,
            'native demolition diagnostic contract')
        demolition_offset=align(data_size,64)
        data_size=demolition_offset+64+32*128
    end
    data_size=align(data_size,4096)
    local lifetime={code_size=code_size,data_size=data_size,function_count=#layouts,patched=false}
    lifetimes[#lifetimes+1]=lifetime
    local data=allocate(nil,data_size,0x3000,4)
    assert(data~=nil,'native data allocation failed')
    lifetime.data=tonumber(ffi.cast('uintptr_t',data))
    local info=ffi.new('HD2RuntimeSystemInfo[1]');win.get_system_info(info)
    local granularity=tonumber(info[0].allocation_granularity)
    assert(granularity>0 and granularity%4096==0,'native allocation granularity')
    local lo=align(image.base+image.size,granularity)
    local max_system=tonumber(ffi.cast('uintptr_t',info[0].maximum_address))
    local hi=math.floor((math.min(max_system,image.base+0x7FFFFFFF)+1)/granularity)*granularity-1
    assert(lo+code_size-1<=hi,'native near range unavailable')
    local requirement=ffi.new('HD2LedgerAddressRequirements[1]')
    requirement[0].lowest=ffi.cast('void *',lo);requirement[0].highest=ffi.cast('void *',hi)
    requirement[0].alignment=granularity
    local parameter=ffi.new('HD2LedgerExtendedParameter[1]')
    parameter[0].type=1;parameter[0].pointer=ffi.cast('void *',requirement)
    local code=allocate_near(nil,nil,code_size,0x3000,4,parameter,1)
    assert(code~=nil,'native near code allocation failed')
    local base=tonumber(ffi.cast('uintptr_t',code));lifetime.code=base
    assert(base>=lo and base+code_size-1<=hi and base%granularity==0,'native near result outside requested range')
    local data_base=lifetime.data
    local addresses={bridge=data_base,arena=data_base+64+1024*96,
        entity_manager_global=image.base+M.entity_manager_rva,current_user_global=image.base+M.current_user_rva}
    if profile.living_target_filter~=nil then
        local live=profile.living_target_filter
        assert(live.revision==1 and live.health_manager_rva==0x3326688
            and live.max_records==4096 and live.max_hash_capacity==65536
            and live.max_probes==8 and live.record_stride==440 and live.life_offset==412
            and live.alive_life_below==2 and live.commit_rechecks_life==false
            and live.unknown_target_admitted==false and keys.health_alive and keys.qualifier_types,
            'native living-target qualification contract')
        addresses.health_manager_global=image.base+live.health_manager_rva
    end
    for name,item in pairs(keys)do addresses[name]=base+item.offset end
    for name,at in pairs(data_offsets)do addresses[name]=data_base+at end
    if demolition_offset then
        addresses.demolition_diagnostic=data_base+demolition_offset
        addresses.destruction_world_global=image.base+0x346D528
        addresses.original_demolition_consumer=image.base+0x13E1DC0
    end
    for _,site in ipairs(profile.sites)do
        if site.original_rva then addresses['original_'..site.name]=image.base+site.original_rva end
    end
    local word=ffi.new('uint32_t[1]');local qword=ffi.new('uint64_t[1]')
    local function put32(at,n)word[0]=n;ffi.copy(ffi.cast('void *',at),word,4)end
    local function put64(at,n)assert(address(n));qword[0]=n;ffi.copy(ffi.cast('void *',at),qword,8)end
    put32(addresses.bridge,1);put32(addresses.bridge+4,1024)
    put32(addresses.arena,32);put32(addresses.arena+4,640)
    put64(addresses.arena+48,addresses.arena+64)
    if demolition_offset then
        put32(addresses.demolition_diagnostic,32)
        put32(addresses.demolition_diagnostic+4,128)
    end
    for name,at in pairs(data_offsets)do
        for i,value in ipairs(tables[name])do
            assert(type(value)=='string' and #value==16 and not value:find('[^%x]'),'native type hash')
            ffi.copy(ffi.cast('void *',data_base+at+(i-1)*8),unhex(value):reverse(),8)
        end
    end
    for _,item in ipairs(layouts)do
        local at=base+item.offset
        ffi.copy(ffi.cast('void *',at),item.raw,#item.raw)
        local used={}
        for _,reloc in ipairs(item.entry.relocations or {})do
            assert(reloc.width==8 and integer(reloc.offset,#item.raw-8) and integer(reloc.addend or 0,65536),
                'native relocation extent')
            for i=reloc.offset,reloc.offset+7 do assert(not used[i],'overlapping relocation');used[i]=true end
            assert(item.raw:sub(reloc.offset+1,reloc.offset+8)==string.rep('\0',8),'native relocation placeholder')
            local target=assert(addresses[reloc.address_key],'native relocation key missing: '..reloc.address_key)
            put64(at+reloc.offset,target+(reloc.addend or 0))
        end
        -- A copied leaf/dispatch retains its internal branches. Only the
        -- generator's explicit external CALL/RIP operands are rebased here.
        for _,reloc in ipairs(item.entry.copy_rel32_relocations or {})do
            assert(reloc.width==4 and integer(reloc.offset,#item.raw-4)
                and integer(reloc.next_offset,#item.raw)
                and reloc.next_offset>=reloc.offset+4
                and reloc.next_offset<=reloc.offset+8,'native copied relocation extent')
            for i=reloc.offset,reloc.offset+3 do assert(not used[i],'overlapping relocation');used[i]=true end
            assert(item.raw:sub(reloc.offset+1,reloc.offset+4)==string.rep('\0',4),
                'native copied relocation placeholder')
            local target
            if reloc.target_rva~=nil then
                assert(reloc.address_key==nil and integer(reloc.target_rva,image.size-1),
                    'native copied image target')
                target=image.base+reloc.target_rva
            else
                assert(type(reloc.address_key)=='string','native copied target missing')
                target=assert(addresses[reloc.address_key],'native copied target key missing')
            end
            local displacement=target-(at+reloc.next_offset)
            assert(displacement>=-2147483648 and displacement<=2147483647,
                'native copied relocation out of range')
            put32(at+reloc.offset,displacement<0 and displacement+4294967296 or displacement)
        end
        ffi.copy(ffi.cast('void *',base+item.unwind_offset),item.uw,#item.uw)
    end
    local functions=ffi.cast('HD2LedgerRuntimeFunction *',base+table_offset)
    for i,item in ipairs(layouts)do
        functions[i-1].begin=item.offset;functions[i-1]['end']=item.offset+item.entry.executable_length
        functions[i-1].unwind=item.unwind_offset
    end
    local old=ffi.new('uint32_t[1]')
    assert(protect(code,code_size,0x20,old)~=0,'native RX protection failed')
    assert(flush(kernel.GetCurrentProcess(),code,code_size)~=0,'native instruction-cache flush failed')
    assert(add_functions(functions,#layouts,ffi.new('uint64_t',base))~=0,'native function-table registration failed')
    lifetime.functions_registered=true; lifetime.function_table=base+table_offset
    return {abi=1,stride=96,capacity=1024,bridge=addresses.bridge,arena=addresses.arena,
        consumer=addresses.drain,configure=addresses.configure,addresses=addresses,profile=profile,
        pause=addresses.pause,resume=addresses.resume,
        lifetime=lifetime,code_base=base,code_size=code_size,native_certified=false}
end
return M
