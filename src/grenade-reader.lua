-- Local inventory only; same Runtime 0.30.3 fields as player_equipment.inventory.
-- No import of the action-capable runtime/player_equipment module, hooks or writes.
local b=require('hd2runtime/core/bytes')
local D=require('hd2runtime/domains/player_equipment')
local N=require('hd2runtime/domains/event_natives')
local I=D.inventory
local SHA='2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E'
local U32=4294967296
local function integer(v,max) return type(v)=='number' and v>=0 and v<=max and v%1==0 end
local function address(v) return integer(v,140737488355327) and v>=65536 end
-- These source pins prove the local inventory manager, descriptor ownership,
-- resource +0x28 and exact count array/read/write used by native refill.
local PROOFS={79,80,81,82,83,84,85,86,87,95,96,97,98,99,100,101,102,103,104}
return function(world_api,options)
    options=options or {};local clock=options.clock or os.clock
    local diagnostics={ready=false,reason='NOT_READ',operations=0,bytes=0,
        operations_peak=0,read_peak=0,max_operations=64,max_bytes=4096,soft_budget_ms=1}
    local api={diagnostics=diagnostics}
    local started,operations,bytes,world,proven
    local function read(at,size)
        if not address(at) or not address(at+size-1) then error('GRENADE_ADDRESS',0) end
        if operations>=64 or bytes+size>4096 then error('GRENADE_READ_BUDGET',0) end
        if clock()-started>=.001 then error('GRENADE_TIME_BUDGET',0) end
        operations,bytes=operations+1,bytes+size
        local raw=world.view.read(at,size)
        if type(raw)~='string' or #raw~=size then error('GRENADE_READ_FAILED',0) end
        return raw
    end
    local function pointer(at)
        local raw=read(at,8);local hi=b.u32(raw,4);local value=b.u32(raw,0)+hi*U32
        if hi>32767 or not address(value) then error('GRENADE_POINTER',0) end
        return value
    end
    local function lookup(at,key)
        local header=read(at,20);local cap=b.u32(header,8)
        local empty,factor=b.u32(header,12),b.u32(header,16)
        local buckets=b.u32(header,0)+b.u32(header,4)*U32
        if not address(buckets) or cap<1 or cap>1048576 then error('GRENADE_HASH',0) end
        local n=cap;while n>1 and n%2==0 do n=n/2 end
        if n~=1 then error('GRENADE_HASH',0) end
        local start=world_api.mul32(key,factor)
        for probe=0,math.min(cap,16)-1 do
            local row_at=buckets+((start+probe)%cap)*8;local row=read(row_at,8)
            local found,index=b.u32(row,0),b.u32(row,4)
            if found==key or found==empty then
                if read(at,20)~=header or read(row_at,8)~=row then error('GRENADE_HASH_CHANGED',0) end
                if found==empty or index==U32-1 or index>=65536 then error('GRENADE_AVATAR_UNMAPPED',0) end
                return index,header
            end
        end
        error('GRENADE_HASH_PROBE_LIMIT',0)
    end
    function api:read(current,player)
        diagnostics.ready=false;diagnostics.operations,diagnostics.bytes=0,0
        if type(player)~='table' or player['local']~=true or not integer(player.avatar,U32-1)
            or player.avatar==0 then diagnostics.reason='NOT_LOCAL_AVATAR';return nil,diagnostics.reason end
        if type(current)~='table' or not address(current.game) or not address(current.exe)
            or type(current.view)~='table' or type(current.view.read)~='function' then
            diagnostics.reason='WORLD_UNAVAILABLE';return nil,diagnostics.reason
        end
        world=current;started,operations,bytes=clock(),0,0
        local ok,result=pcall(function()
            if D.source.gameDllSha256~=SHA or N.source.gameDllSha256~=SHA then error('GRENADE_BUILD_PROFILE',0) end
            local key=tostring(world.game)..':'..tostring(world.exe)..':'..tostring(world.key)
            if proven~=key then
                for _,index in ipairs(PROOFS) do
                    local pin=D.pins[index]
                    if read(world.game+pin.rva,#pin.hex/2)~=b.unhex(pin.hex) then error('GRENADE_CODE_PIN_CHANGED',0) end
                end
                proven=key
            end
            local manager=pointer(world.game+I.global)
            local index,header=lookup(manager+I.hash,player.avatar)
            local descriptors=pointer(manager+I.descriptors)
            local descriptor=pointer(descriptors+index*8);local who=read(descriptor,24)
            if b.u32(who,8)~=player.avatar or b.u32(who,20)%2~=1 then error('GRENADE_AVATAR_OWNERSHIP',0) end
            local records,counts=pointer(manager+I.records),pointer(manager+I.counts)
            local record_at=records+index*I.stride
            local held_at=record_at+I.slots.held
            local held_raw=read(held_at,4)
            local held_entity=b.u32(held_raw,0)
            local resource_at=record_at+I.throwable
            local count_at=counts+index*I.countStride+I.throwableCount
            local resource_raw,count_raw=read(resource_at,8),read(count_at,4)
            local count=b.u32(count_raw,0)
            if count>10000 then error('GRENADE_INVALID_COUNT',0) end
            local lo,hi=b.u32(resource_raw,0),b.u32(resource_raw,4)
            if lo==0 and hi==0 then error('GRENADE_NO_TYPE',0) end
            local resource=string.format('%08X%08X',hi,lo)
            -- Reserve excludes the grenade moved to Inventory.slots.held. Add
            -- that exact owned inventory entity back until it leaves the hand.
            -- The total is stable when merely equipping/cancelling a grenade.
            local held_count,held_type=0,nil
            if held_entity~=0 then
                local proxy={game=world.game,exe=world.exe,view={read=read,pointer=pointer,
                    u32=function(at)return b.u32(read(at,4),0)end}}
                if world_api.entity_exists(proxy,held_entity)~=true then error('GRENADE_HELD_UNREADABLE',0)end
                held_type=world_api.entity_type(proxy,held_entity)
                if not held_type then error('GRENADE_HELD_UNREADABLE',0)end
                if held_type==resource then held_count=1 end
            end
            if read(resource_at,8)~=resource_raw or read(count_at,4)~=count_raw or read(held_at,4)~=held_raw
                or read(descriptor,24)~=who or pointer(descriptors+index*8)~=descriptor
                or pointer(manager+I.records)~=records or pointer(manager+I.counts)~=counts
                or pointer(manager+I.descriptors)~=descriptors or read(manager+I.hash,20)~=header
                or pointer(world.game+I.global)~=manager then error('GRENADE_INVENTORY_CHANGED',0) end
            return {resource=resource,count=count+held_count,reserve=count,held_count=held_count,
                held_entity=held_entity,held_type=held_type,avatar=player.avatar}
        end)
        diagnostics.operations,diagnostics.bytes=operations,bytes
        diagnostics.operations_peak=math.max(diagnostics.operations_peak,operations)
        diagnostics.read_peak=math.max(diagnostics.read_peak,bytes)
        diagnostics.elapsed_ms=math.max(0,(clock()-started)*1000)
        if not ok then diagnostics.reason=tostring(result);return nil,diagnostics.reason end
        diagnostics.ready,diagnostics.reason=true,'READY'
        return result
    end
    return api
end
