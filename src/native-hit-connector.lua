-- Consume a lifetime-owned native bridge supplied by the verified installer.
-- This module installs no hooks and calls only the bridge's bounded drain.
local win=require('hd2runtime/runtime/windows_ffi')
local ffi=win.ffi
local b=require('hd2runtime/core/bytes')
local M={abi=1,stride=96,max_batch=64}
local address=function(n)return type(n)=='number' and n>=65536 and n<140737488355328 and n%1==0 end
local hex=function(s)return type(s)=='string' and #s==16 and not s:find('[^%x]') and s~='0000000000000000' end
local function qword(raw,at)return string.format('%08X%08X',b.u32(raw,at+4),b.u32(raw,at))end
local drain_type=win.fn('uint32_t (*)(void *, void *, uint32_t)')
local control_type=win.fn('uint32_t (*)(void *,void *,uint64_t,uint64_t,uint32_t)')
local run_type=win.fn('uint32_t (*)(void *,void *,uint64_t,uint64_t)')
local function u64(s)
    local value=ffi.new('uint64_t[1]')
    local raw=s:gsub('..',function(pair)return string.char(tonumber(pair,16))end):reverse()
    ffi.copy(value,raw,8)
    return value[0]
end
function M.configure(handle,peer,epoch,enabled)
    if type(handle)~='table' or handle.native_certified~=true or not address(handle.bridge)
        or not address(handle.arena) or not address(handle.configure) or not hex(peer) or not hex(epoch)
        or type(enabled)~='boolean' then return nil,'CONFIGURATION_NOT_CERTIFIED' end
    -- This native control disables producers, checks active observers and tries
    -- the queue lock once. Busy leaves it disabled; retry on the next update.
    local control=handle.control or ffi.cast(control_type,handle.configure)
    handle.control=control
    return tonumber(control(ffi.cast('void *',handle.bridge),ffi.cast('void *',handle.arena),
        u64(epoch),u64(peer),enabled and 1 or 0))==1
end

local function set_running(handle,peer,epoch,operation)
    if type(handle)~='table' or handle.native_certified~=true or not address(handle.bridge)
        or not address(handle.arena) or not address(handle[operation]) or not hex(peer) or not hex(epoch) then
        return nil,'RUN_CONTROL_NOT_CERTIFIED'
    end
    local key=operation..'_control'
    local control=handle[key] or ffi.cast(run_type,handle[operation])
    handle[key]=control
    -- Only changes the producer gate. Queue, mission identity and accepted
    -- sequence remain available to the existing consumer for its final drain.
    return tonumber(control(ffi.cast('void *',handle.bridge),ffi.cast('void *',handle.arena),
        u64(epoch),u64(peer)))==1
end
function M.pause(handle,peer,epoch)return set_running(handle,peer,epoch,'pause')end
function M.resume(handle,peer,epoch)return set_running(handle,peer,epoch,'resume')end

-- Read only the diagnostic's lifetime-owned arena slack. It never drains or
-- classifies these records, and never follows a Game pointer.
function M.diagnostic_snapshot(handle,peer,epoch)
    local d=type(handle)=='table'and type(handle.profile)=='table'and handle.profile.tail_diagnostic
    if type(d)~='table' then return nil,'NO_TAIL_DIAGNOSTIC' end
    if handle.native_certified~=true or not address(handle.arena) or handle.arena%8~=0
        or not hex(peer) or not hex(epoch) then return nil,'TAIL_DIAGNOSTIC_NOT_CERTIFIED' end
    if d.revision~=1 or d.head_offset~=128 or d.head_bytes~=32 or d.scratch_offset~=160
        or d.record_offset~=256 or d.record_bytes~=96 or d.capacity~=16
        or d.alt_tag~=3 or d.true_tag~=4 then return nil,'TAIL_DIAGNOSTIC_LAYOUT_CHANGED' end
    peer,epoch=peer:upper(),epoch:upper()
    local lifetime=handle.lifetime
    if type(lifetime)~='table' or not address(lifetime.data) or type(lifetime.data_size)~='number'
        or lifetime.data_size%1~=0 or lifetime.data_size<=0
        or handle.arena<lifetime.data or handle.arena+64+32*640>lifetime.data+lifetime.data_size then
        return nil,'TAIL_DIAGNOSTIC_RANGE_CHANGED'
    end
    local function read(at,n)return ffi.string(ffi.cast('const uint8_t *',at),n)end
    local first=read(handle.arena,64)
    local generation=b.u32(first,60)
    local rows=b.pointer(first,48)
    local function identity(raw)
        return b.u32(raw,0)==32 and b.u32(raw,4)==640 and qword(raw,8)==epoch
            and qword(raw,16)==peer and b.pointer(raw,48)==handle.arena+64
            and b.u32(raw,60)==generation and generation%2==0
    end
    if not identity(first) or rows~=handle.arena+64 then return nil,'TAIL_DIAGNOSTIC_IDENTITY_CHANGED' end
    local head=read(rows+128,32)
    local claimed,mask=b.u32(head,16),b.u32(head,20)
    if claimed>16 or mask>=2^claimed then return nil,'TAIL_DIAGNOSTIC_MASK_CHANGED' end
    local captured_epoch=qword(head,24)
    if captured_epoch~=epoch and not(captured_epoch=='0000000000000000'and head==string.rep('\0',32))then
        return nil,'TAIL_DIAGNOSTIC_EPOCH_CHANGED'
    end
    local result={revision=1,epoch=epoch,peer=peer,alt_seen=qword(head,0),true_seen=qword(head,8),
        claimed=claimed,committed_mask=mask,records={}}
    for index=0,claimed-1 do
        if math.floor(mask/2^index)%2==1 then
            local raw=read(rows+index*640+256,96)
            local tag=b.u32(raw,60)
            if qword(raw,8)~=epoch or qword(raw,16)~=peer or(tag~=3 and tag~=4)then
                return nil,'TAIL_DIAGNOSTIC_RECORD_CHANGED'
            end
            result.records[#result.records+1]={slot=index,tag=tag,
                raw_hex=(raw:gsub('.',function(c)return string.format('%02X',c:byte())end))}
        end
    end
    local after_head,after_arena=read(rows+128,32),read(handle.arena,64)
    if not identity(after_arena) or qword(after_head,24)~=captured_epoch
        or qword(after_head,0)<result.alt_seen or qword(after_head,8)<result.true_seen then
        return nil,'TAIL_DIAGNOSTIC_CHANGED_DURING_READ'
    end
    local after_claimed,after_mask=b.u32(after_head,16),b.u32(after_head,20)
    if after_claimed<claimed or after_claimed>16 or after_mask>=2^after_claimed then
        return nil,'TAIL_DIAGNOSTIC_CHANGED_DURING_READ'
    end
    for index=0,claimed-1 do
        if math.floor(mask/2^index)%2==1 and math.floor(after_mask/2^index)%2~=1 then
            return nil,'TAIL_DIAGNOSTIC_CHANGED_DURING_READ'
        end
    end
    return result
end

-- Diagnostic-only receipts from the private destruction wrapper. Draining
-- invokes our bounded copy/clear routine and never calls a Game function.
function M.demolition_snapshot(handle,peer,epoch)
    local d=type(handle)=='table'and type(handle.profile)=='table'and handle.profile.demolition_diagnostic
    if type(d)~='table'then return nil,'NO_DEMOLITION_DIAGNOSTIC'end
    local a=handle.addresses
    if handle.native_certified~=true or type(a)~='table'or not address(a.demolition_diagnostic)
        or not address(a.demolition_drain)or not hex(peer)or not hex(epoch)then
        return nil,'DEMOLITION_DIAGNOSTIC_NOT_CERTIFIED'
    end
    if d.revision~=1 or d.header_bytes~=64 or d.record_bytes~=128 or d.capacity~=32 then
        return nil,'DEMOLITION_DIAGNOSTIC_LAYOUT_CHANGED'
    end
    local life,base=handle.lifetime,a.demolition_diagnostic
    if type(life)~='table'or not address(life.data)or type(life.data_size)~='number'
        or base%64~=0 or base<life.data or base+64+32*128>life.data+life.data_size
        or not address(handle.code_base)or type(handle.code_size)~='number'
        or a.demolition_drain<handle.code_base or a.demolition_drain>=handle.code_base+handle.code_size then
        return nil,'DEMOLITION_DIAGNOSTIC_RANGE_CHANGED'
    end
    peer,epoch=peer:upper(),epoch:upper()
    local function header()return ffi.string(ffi.cast('const uint8_t *',base),64)end
    local function identity(raw)
        return b.u32(raw,0)==32 and b.u32(raw,4)==128 and qword(raw,8)==epoch
            and qword(raw,16)==peer and b.u32(raw,24)<=32 and b.u32(raw,28)<=1
    end
    if not identity(header())then return nil,'DEMOLITION_DIAGNOSTIC_WAITING_EPOCH'end
    local drain=handle.demolition_consumer
    if not drain then
        drain=ffi.cast(win.fn('uint32_t (*)(void *,void *,uint32_t)'),a.demolition_drain)
        handle.demolition_consumer=drain
        handle.demolition_output=ffi.new('uint8_t[4096]')
    end
    local count=tonumber(drain(ffi.cast('void *',base),handle.demolition_output,32))
    if count<0 or count>32 then return nil,'DEMOLITION_DIAGNOSTIC_DRAIN_INVALID'end
    local after=header()
    if not identity(after)then return nil,'DEMOLITION_DIAGNOSTIC_EPOCH_CHANGED'end
    local result={revision=1,epoch=epoch,peer=peer,records={},sequence=b.u32(after,32),
        dropped=b.u32(after,36),rejected=b.u32(after,40),batches=b.u32(after,44),scanned=b.u32(after,52)}
    for i=0,count-1 do
        local raw=ffi.string(handle.demolition_output+i*128,128)
        if qword(raw,8)~=peer then return nil,'DEMOLITION_DIAGNOSTIC_RECORD_CHANGED'end
        result.records[#result.records+1]=raw
    end
    return result
end

function M.attach(handle,options)
    options=options or {}
    if type(handle)~='table' or handle.native_certified~=true or handle.abi~=1 or handle.stride~=96
        or not address(handle.bridge) or handle.bridge%8~=0 or not address(handle.consumer)
        or type(handle.lifetime)~='table' or not hex(options.peer) or not hex(options.epoch)
        or type(options.decoder)~='table' or type(options.decoder.new)~='function'
        or type(options.accept)~='function' then return nil,'BRIDGE_NOT_CERTIFIED' end
    local peer,epoch=options.peer:upper(),options.epoch:upper()
    local header=ffi.cast('const uint8_t *',handle.bridge)
    local capacity=handle.capacity
    if type(capacity)~='number' or capacity<1 or capacity>1024 or capacity%1~=0 then
        return nil,'BRIDGE_CAPACITY_INVALID'
    end
    -- Owned pages remain allocated for the process lifetime. The installer
    -- proves their ranges/permissions and the consumer's registered unwind.
    local function identity()
        local raw=ffi.string(header,24)
        return b.u32(raw,0)==1 and b.u32(raw,4)==capacity and qword(raw,8)==epoch and qword(raw,16)==peer
    end
    if not identity() then return nil,'BRIDGE_IDENTITY_MISMATCH' end
    local drain=ffi.cast(drain_type,handle.consumer)
    local output=ffi.new('uint8_t[6144]')
    local decoder=options.decoder.new({peer=peer,epoch=epoch,accept=options.accept,
        observe_record=options.observe_record})
    local api={decoder=decoder,drains=0,records=0,ready=true,lifetime=handle.lifetime}
    local arena
    if handle.arena~=nil then
        if not address(handle.arena) or handle.arena%8~=0 then return nil,'ARENA_ADDRESS_INVALID' end
        arena=ffi.cast('const uint8_t *',handle.arena)
        if b.u32(ffi.string(arena,8),0)~=32 or b.u32(ffi.string(arena,8),4)~=640 then
            return nil,'ARENA_CONTRACT_CHANGED'
        end
    end
    api.rejected='0000000000000000'
    local metadata={abi=1,stride=96,connector_proven=true,epoch=epoch,count=0,dropped='0000000000000000'}
    local last_time=0
    function api:step(now)
        if type(now)~='number' or now~=now or now<last_time or now==math.huge then
            return nil,'INVALID_CLOCK'
        end
        if not self.ready or not identity() then
            self.ready=false;return nil,'BRIDGE_IDENTITY_CHANGED'
        end
        local count=tonumber(drain(ffi.cast('void *',handle.bridge),output,64))
        self.drains=self.drains+1
        if count<0 or count>64 or not identity() then
            self.ready=false;return nil,'BRIDGE_DRAIN_INVALID'
        end
        metadata.count=count
        metadata.dropped=qword(ffi.string(header+48,8),0)
        if arena then
            local rejected=qword(ffi.string(arena+32,8),0)
            if rejected<self.rejected then self.ready=false;return nil,'ARENA_COUNTER_REWIND' end
            if rejected~=self.rejected then decoder.partial=true;self.rejected=rejected end
        end
        local ok,why=decoder:consume(ffi.string(output,count*96),now,metadata)
        if ok then self.records=self.records+count;last_time=now end
        return ok,why
    end
    function api:detach()
        -- Detachment stops Lua reads. It never frees native pages or tables
        -- while a worker might still be executing an observation gateway.
        self.ready=false
    end
    return api
end
return M
