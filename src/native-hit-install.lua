-- Seven-site plan for the matching, independently verified observer package.
-- Planning is read-only; the native all-thread transaction performs mutations.
local M={image_size=0x4744000}
local SITES={
    {'contact_begin',0x13AD4E8,'e8c350efff'},
    {'default_delta',0x129CABC,'f3410f5cc1'},
    {'custom_curve',0x129CADF,'e85cfeffff'},
    {'ap_result',0x129CB61,'f30f117704'},
    {'normal_final',0x13AD88B,'e8a004efff'},
    {'physical_success',0x13B11D4,'32c088451c'},
    {'iteration_end',0x13AD1D4,'8b442474ffc0'},
}
local function address(n)return type(n)=='number' and n>=65536 and n<140737488355328 and n%1==0 end
local function raw(hex)return (hex:gsub('..',function(pair)return string.char(tonumber(pair,16))end))end
local function u32(n)
    if n<0 then n=n+4294967296 end
    local bytes={}
    for i=1,4 do bytes[i]=string.char(n%256);n=math.floor(n/256)end
    return table.concat(bytes)
end
function M.plan(image,profile,package,proves)
    if type(image)~='table' or not address(image.base) or image.base%4096~=0 or image.size~=M.image_size
        or type(profile)~='table' or type(profile.sites)~='table' or #profile.sites~=7
        or type(package)~='table' or type(package.addresses)~='table' or type(package.lifetime)~='table'
        or package.lifetime.functions_registered~=true or type(proves)~='function' then
        return nil,'INSTALL_PLAN_UNPROVEN'
    end
    local plan={patches={},pages={},code_base=package.code_base,game=image.base,mutated=false}
    local pages={}
    for i,spec in ipairs(SITES)do
        local name,rva,pin=spec[1],spec[2],spec[3]
        local supplied=profile.sites[i]
        if supplied.name~=name or supplied.rva~=rva or supplied.pin_hex~=pin
            or supplied.replace_bytes~=#pin/2 then return nil,'INSTALL_SITE_PROFILE_MISMATCH' end
        local at,target=image.base+rva,package.addresses[name]
        if not address(target) or target<package.code_base or target>=package.code_base+package.code_size then
            return nil,'INSTALL_GATEWAY_OUTSIDE_OWNED_CODE'
        end
        local delta=target-(at+5)
        if delta< -2147483648 or delta>2147483647 then return nil,'INSTALL_CALL_OUT_OF_RANGE' end
        if not proves(at,pin) then return nil,'INSTALL_SITE_ALREADY_CHANGED_'..name end
        local expected=raw(pin)
        local replacement=string.char(0xE8)..u32(delta)..(#expected==6 and string.char(0x90) or '')
        local page=math.floor(at/4096)*4096
        if at+#expected>page+4096 then return nil,'INSTALL_SITE_PAGE_CROSSING' end
        plan.patches[i]={name=name,address=at,length=#expected,expected=expected,replacement=replacement,page=page}
        if not pages[page] then pages[page]=true;plan.pages[#plan.pages+1]=page end
    end
    return plan
end

local function bindings()
    local win=require('hd2runtime/runtime/windows_ffi')
    local ffi,kernel=win.ffi,win.kernel
    if not rawget(_G,'HD2LedgerHitPatchTypesV3') then
        ffi.cdef[[
            typedef struct LedgerPatchThreadV3 {
                void *handle;void *context;uint64_t rip;uint32_t prior;uint32_t resumed;
                uint32_t thread_id;uint32_t seen;
            } LedgerPatchThreadV3;
            typedef struct LedgerPatchRowV3 {
                void *address;uint32_t length;uint32_t expected_protection;
                void *expected;void *replacement;uint32_t prior_protection;
                uint32_t scratch_protection;uint32_t protection_changed;uint32_t written;
            } LedgerPatchRowV3;
            typedef struct LedgerPatchJobV3 {
                uint32_t lock;uint32_t result;uint32_t failed_patch;uint32_t suspended;
                uint32_t patched;uint32_t rollback_failures;uint32_t resume_failures;
                uint32_t thread_count;uint32_t patch_count;uint32_t reserved;
                void *threads;void *patches;void *process;
                void *suspend;void *get_context;void *resume;void *protect;void *flush;
                uint32_t rollback_restored;uint32_t reserved2;
                uint32_t installer_tid;uint32_t enumerated;uint32_t enum_status;uint32_t enum_failures;
                void *nt_get_next_thread;void *get_thread_id;void *close_handle;
                void *enum_cursor;void *enum_next;
                void *wait_thread;uint32_t wait_status_scratch;uint32_t enum_scanned;
            } LedgerPatchJobV3;
        ]]
        rawset(_G,'HD2LedgerHitPatchTypesV3',true)
    end
    assert(ffi.sizeof('LedgerPatchThreadV3')==40 and ffi.sizeof('LedgerPatchRowV3')==48
        and ffi.sizeof('LedgerPatchJobV3')==184,'hit installer ABI changed')
    local function procedure(module,name,signature)
        local lib=kernel.GetModuleHandleA(module)
        local ptr=lib~=nil and kernel.GetProcAddress(lib,name) or nil
        assert(ptr~=nil,'hit installer export unavailable: '..name)
        return ffi.cast(win.fn(signature),ptr)
    end
    local api={ffi=ffi,win=win}
    local declarations={
        {'pid','GetCurrentProcessId','uint32_t (*)(void)'},
        {'tid','GetCurrentThreadId','uint32_t (*)(void)'},
        {'open','OpenThread','void *(*)(uint32_t,int,uint32_t)'},
        {'thread_pid','GetProcessIdOfThread','uint32_t (*)(void *)'},
        {'thread_id','GetThreadId','uint32_t (*)(void *)'},
        {'exit_code','GetExitCodeThread','int (*)(void *,uint32_t *)'},
        {'wait','WaitForSingleObject','uint32_t (*)(void *,uint32_t)'},
        {'close','CloseHandle','int (*)(void *)'},
        {'suspend','SuspendThread','uint32_t (*)(void *)'},
        {'context','GetThreadContext','int (*)(void *,void *)'},
        {'resume','ResumeThread','uint32_t (*)(void *)'},
        {'protect','VirtualProtect','int (*)(void *,size_t,uint32_t,uint32_t *)'},
        {'flush','FlushInstructionCache','int (*)(void *,const void *,size_t)'},
    }
    for _,decl in ipairs(declarations)do api[decl[1]]=procedure('kernel32.dll',decl[2],decl[3])end
    api.next_thread=procedure('ntdll.dll','NtGetNextThread',
        'int32_t (*)(void *,void *,uint32_t,uint32_t,uint32_t,void **)')
    api.process=kernel.GetCurrentProcess()
    return api
end

-- Prepares every handle, context, byte buffer and API binding before the one
-- native transaction call. Lua never runs between SuspendThread and ResumeThread.
-- This also permits an owned-process fixture with its explicit seven-site plan.
function M.execute(plan,package,transaction)
    if type(plan)~='table' or plan.mutated or type(plan.patches)~='table' or #plan.patches~=7
        or type(package)~='table' or type(package.lifetime)~='table'
        or package.lifetime.functions_registered~=true or type(package.addresses)~='table'
        or not address(package.addresses.patch_transaction_v3)
        or not address(package.code_base) or type(package.code_size)~='number'
        or package.addresses.patch_transaction_v3<package.code_base
        or package.addresses.patch_transaction_v3>=package.code_base+package.code_size
        or type(transaction)~='table' or transaction.abi~=3 then
        return nil,'INSTALL_TRANSACTION_UNPROVEN'
    end
    local api=bindings();local ffi=api.ffi
    local current_pid,current_tid=tonumber(api.pid()),tonumber(api.tid())
    local retained={handles={},contexts={},buffers={}}
    local cursor,next_handle=nil,ffi.new('void *[1]')
    local function close_prepared()
        if cursor~=nil then api.close(cursor);cursor=nil end
        for _,handle in ipairs(retained.handles)do api.close(handle)end
        retained.handles={}
    end
    local function prepare()
        local rows=ffi.new('LedgerPatchRowV3[7]')
        retained.rows=rows
        local region=ffi.new('HD2RuntimeMemoryRegion[1]')
        for i,patch in ipairs(plan.patches)do
            assert(address(patch.address) and (patch.length==5 or patch.length==6)
                and type(patch.expected)=='string' and #patch.expected==patch.length
                and type(patch.replacement)=='string' and #patch.replacement==patch.length,
                'invalid hit patch extent')
            assert(api.win.kernel.VirtualQuery(ffi.cast('void *',patch.address),region,ffi.sizeof(region[0]))==ffi.sizeof(region[0])
                and tonumber(region[0].state)==0x1000 and tonumber(region[0].protection)==0x20
                and tonumber(ffi.cast('uintptr_t',region[0].base))<=patch.address
                and tonumber(ffi.cast('uintptr_t',region[0].base))+tonumber(region[0].size)>=patch.address+patch.length,
                'hit site must remain a complete RX instruction')
            local expected,replacement=ffi.new('uint8_t[?]',patch.length),ffi.new('uint8_t[?]',patch.length)
            ffi.copy(expected,patch.expected,patch.length);ffi.copy(replacement,patch.replacement,patch.length)
            retained.buffers[#retained.buffers+1]=expected;retained.buffers[#retained.buffers+1]=replacement
            rows[i-1].address=ffi.cast('void *',patch.address);rows[i-1].length=patch.length
            rows[i-1].expected_protection=0x20;rows[i-1].expected=expected;rows[i-1].replacement=replacement
        end
        local ids,seen={},{}
        -- Enum handles have query-only access; separate owned handles carry
        -- the precise suspend/context rights used by the transaction.
        for _=1,1025 do
            next_handle[0]=nil
            local status=tonumber(api.next_thread(api.process,cursor,0x100800,0,0,next_handle))
            if cursor~=nil then api.close(cursor);cursor=nil end
            if status==-2147483622 then break end -- STATUS_NO_MORE_ENTRIES
            assert(status==0 and next_handle[0]~=nil,'hit thread enumeration failed')
            cursor=next_handle[0]
            local id=tonumber(api.thread_id(cursor))
            assert(id>0 and tonumber(api.thread_pid(cursor))==current_pid,
                'hit thread identity changed')
            local wait_status=tonumber(api.wait(cursor,0))
            assert(wait_status==0 or wait_status==258,'hit thread liveness query failed')
            if wait_status==258 then
                assert(not seen[id],'duplicate live hit thread');seen[id]=true
            end
            if wait_status==258 and id~=current_tid then
                assert(#ids<256,'hit thread count exceeds bounded installer')
                local handle=api.open(0x10080A,0,id)
                assert(handle~=nil,'hit worker handle unavailable')
                retained.handles[#retained.handles+1]=handle
                assert(tonumber(api.thread_id(handle))==id and tonumber(api.thread_pid(handle))==current_pid,
                    'hit worker handle changed identity')
                ids[#ids+1]=id
            end
        end
        assert(cursor==nil and seen[current_tid],'hit thread enumeration did not finish')
        local threads=ffi.new('LedgerPatchThreadV3[?]',math.max(1,#ids))
        retained.threads=threads
        for i,id in ipairs(ids)do
            local storage=ffi.new('uint8_t[1248]')
            local pointer=math.floor((tonumber(ffi.cast('uintptr_t',storage))+15)/16)*16
            ffi.cast('uint32_t *',pointer+0x30)[0]=0x100001
            retained.contexts[i]=storage
            threads[i-1].handle=retained.handles[i];threads[i-1].context=ffi.cast('void *',pointer)
            threads[i-1].thread_id=id
        end
        local job=ffi.new('LedgerPatchJobV3[1]');retained.job=job
        job[0].thread_count=#ids;job[0].patch_count=7;job[0].threads=threads;job[0].patches=rows
        job[0].process=api.process;job[0].installer_tid=current_tid
        for field,key in pairs({suspend='suspend',get_context='context',resume='resume',protect='protect',
            flush='flush',nt_get_next_thread='next_thread',get_thread_id='thread_id',close_handle='close',wait_thread='wait'})do
            job[0][field]=ffi.cast('void *',api[key])
        end
        retained.entry=ffi.cast(api.win.fn('uint32_t (*)(LedgerPatchJobV3 *)'),package.addresses.patch_transaction_v3)
        return job
    end
    local ok,job=pcall(prepare)
    if not ok then close_prepared();return nil,'INSTALL_PREPARE_FAILED: '..tostring(job)end
    local result=tonumber(retained.entry(job))
    local evidence={result=result,thread_count=tonumber(job[0].thread_count),enumerated=tonumber(job[0].enumerated),
        suspended=tonumber(job[0].suspended),patched=tonumber(job[0].patched),
        rollback_failures=tonumber(job[0].rollback_failures),resume_failures=tonumber(job[0].resume_failures),
        enum_failures=tonumber(job[0].enum_failures),enum_status=tonumber(job[0].enum_status),
        enum_scanned=tonumber(job[0].enum_scanned),
        failed_patch=tonumber(job[0].failed_patch),rollback_restored=tonumber(job[0].rollback_restored)}
    if result==2 then
        local index=tonumber(job[0].reserved2)
        evidence.failed_thread_error=evidence.enum_status
        if index>=0 and index<evidence.thread_count then
            local row=retained.threads[index]
            evidence.failed_thread_index=index+1;evidence.failed_thread_id=tonumber(row.thread_id)
            evidence.failed_thread_wait=tonumber(api.wait(row.handle,0))
            local exit_code=ffi.new('uint32_t[1]')
            if api.exit_code(row.handle,exit_code)~=0 then evidence.failed_thread_exit=tonumber(exit_code[0])end
        end
    end
    if result==7 or result==9 then
        local index=evidence.failed_patch
        if index>=0 and index<#plan.patches then
            local row=retained.rows[index]
            evidence.failed_patch_index=index+1
            evidence.failed_patch_name=plan.patches[index+1].name or tostring(index+1)
            evidence.failed_patch_prior=tonumber(row.prior_protection)
            evidence.failed_patch_expected=tonumber(row.expected_protection)
            evidence.failed_patch_protection_changed=tonumber(row.protection_changed)
            evidence.failed_patch_written=tonumber(row.written)
            evidence.failed_patch_kind=result==9 and 'restore_api'
                or (evidence.failed_patch_protection_changed==0 and 'protect_api' or 'prior_protection')
            if evidence.failed_patch_kind~='prior_protection' then
                evidence.failed_patch_error=evidence.enum_status
            end
        end
    end
    package.lifetime.transaction=evidence
    if evidence.resume_failures>0 then
        -- Retain failed handles for diagnosis instead of discarding access to
        -- a thread which the native transaction could not resume.
        package.lifetime.failed_transaction=retained
    else close_prepared()end
    if result~=0 or evidence.rollback_failures~=0 or evidence.resume_failures~=0 or evidence.enum_failures~=0 then
        return nil,'INSTALL_TRANSACTION_FAILED_'..result,evidence
    end
    package.native_certified=true;package.lifetime.patched=true;plan.mutated=true
    return package,nil,evidence
end

function M.install(world,profile,transaction,package_module)
    local schema=require('hd2runtime/schemas/current')
    if schema.exe_sha~='F5FEE03DCFDB2E553A4752C283590950AC13316B376D8196AA556FF0400D5F06'
        or schema.dll_sha~='2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E'
        or type(world)~='table' or type(world.runtime)~='table' or world.runtime.mode~='live'
        or not address(world.game) or type(world.view)~='table' or type(world.view.proves)~='function' then
        return nil,'INSTALL_WORLD_NOT_PROVEN'
    end
    local game=require('hd2runtime/runtime/event_world').game_state(world)
    if not game or game.state~=3 or game.mission then return nil,'INSTALL_WAITING_FOR_SHIP'end
    local win=require('hd2runtime/runtime/windows_ffi')
    local loaded=win.kernel.GetModuleHandleA('game.dll')
    if loaded==nil or tonumber(win.ffi.cast('uintptr_t',loaded))~=world.game then
        return nil,'INSTALL_MODULE_NOT_CURRENT'
    end
    local singleton=rawget(_G,'HD2WarCostLedgerHitInstallationV2')
    if singleton and singleton.game~=world.game then return nil,'INSTALL_MODULE_CHANGED'end
    if singleton and singleton.stopped then return nil,singleton.reason end
    if singleton and singleton.package and singleton.package.native_certified then return singleton.package end
    for _,site in ipairs(SITES)do
        if not world.view.proves(world.game+site[2],site[3]) then return nil,'INSTALL_SITE_ALREADY_CHANGED_'..site[1]end
    end
    if not singleton then
        local image={base=world.game,size=M.image_size}
        -- The SDK already fingerprinted both files; confirm SizeOfImage from
        -- their PE header in addition to the seven fresh instruction pins.
        local bytes=require('hd2runtime/core/bytes')
        local dos=world.view.read(world.game,64)
        local pe_offset=dos and #dos==64 and bytes.u32(dos,60)
        if not pe_offset or pe_offset<64 or pe_offset>4096 then return nil,'INSTALL_IMAGE_HEADER_UNREADABLE'end
        local pe=world.view.read(world.game+pe_offset,88)
        if not pe or #pe~=88 or dos:sub(1,2)~='MZ' or pe:sub(1,4)~='PE\0\0'
            or bytes.u32(pe,80)~=M.image_size then return nil,'INSTALL_IMAGE_SIZE_MISMATCH'end
        singleton={game=world.game,image=image,attempts=0}
        rawset(_G,'HD2WarCostLedgerHitInstallationV2',singleton)
        local prepared,package=pcall(package_module.prepare,image,profile)
        if not prepared then singleton.stopped=true;singleton.reason=tostring(package);return nil,singleton.reason end
        singleton.package=package
    end
    local plan,why=M.plan(singleton.image,profile,singleton.package,world.view.proves)
    if not plan then singleton.stopped=true;singleton.reason=why;return nil,why end
    singleton.attempts=singleton.attempts+1
    local installed,failure,evidence=M.execute(plan,singleton.package,transaction)
    if not installed then
        -- An instruction-in-flight, changed set or known expired handle can retry;
        -- all code/data pages are reused, with at most five Ship attempts.
        local expired=evidence and evidence.result==2 and evidence.patched==0
            and (evidence.failed_thread_error==6 or evidence.failed_thread_error==87
                or (evidence.failed_thread_error==5 and evidence.failed_thread_wait==0))
        local retry=evidence and (evidence.result==5 or evidence.result==11 or expired)
            and evidence.rollback_failures==0 and evidence.resume_failures==0
        singleton.stopped=not retry or singleton.attempts>=5;singleton.reason=failure
    end
    return installed,failure,evidence
end
return M
