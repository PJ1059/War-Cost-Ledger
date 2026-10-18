-- Decode the proposed observer ABI. This module installs no observer or hook.
-- capture_flags mean fields proven by the producer; they are not game enums.
local bytes = require('hd2runtime/core/bytes')
local M = {abi = 1, stride = 96, max_batch = 64,
    flags = {direct = 1, peer = 2, selected_ap = 4, armour = 8,
        curve_known = 16, force_known = 32, hostile = 64, delta = 128, mode = 256,
        damage_info = 512, attribution_only = 1024, projectile_type = 2048}}
local function uint(n) return type(n)=='number' and n>=0 and n<4294967296 and n%1==0 end
local function hex(s) return type(s)=='string' and #s==16 and not s:find('[^%x]') end
local function finite(n) return type(n)=='number' and n==n and n>-math.huge and n<math.huge end
local function flag(n, bit) return math.floor(n/bit)%2==1 end
local function required(n, mask)
    for _,bit in pairs(M.flags) do if flag(mask,bit) and not flag(n,bit) then return false end end
    return true
end
local function qword(raw, offset)
    return string.format('%08X%08X',bytes.u32(raw,offset+4),bytes.u32(raw,offset))
end
local function float(raw, offset)
    if math.floor(bytes.u32(raw,offset)/8388608)%256==255 then return nil end
    return bytes.value(raw,offset,'f32')
end

function M.decode(raw, offset)
    offset = offset or 0
    if type(raw)~='string' or not uint(offset) or offset+96>#raw then return nil,'SHORT_RECORD' end
    local r = {sequence=qword(raw,offset),epoch=qword(raw,offset+8),peer=qword(raw,offset+16),
        target=bytes.u32(raw,offset+44),source=bytes.u32(raw,offset+48),owner=bytes.u32(raw,offset+52),
        effects=bytes.u32(raw,offset+56),branch=bytes.u32(raw,offset+60),
        selected_ap=float(raw,offset+64),armour=float(raw,offset+68),factor=float(raw,offset+72),
        damage=float(raw,offset+76),source_kind=bytes.u32(raw,offset+80),
        target_kind=bytes.u32(raw,offset+84),flags=bytes.u32(raw,offset+88),delta=float(raw,offset+92)}
    -- +36 was never populated by the old producer. The extension names it
    -- only with explicit per-record validity; old bytes cannot become an ID.
    if flag(r.flags,M.flags.damage_info) then r.damage_info_id=bytes.u32(raw,offset+36) end
    if flag(r.flags,M.flags.projectile_type) then r.projectile_id=bytes.u32(raw,offset+32) end
    return r
end

function M.classify(r, peer, epoch)
    if type(r)~='table' or not hex(peer) or not hex(epoch) or peer=='0000000000000000'
        or epoch=='0000000000000000' or not hex(r.peer) or not hex(r.epoch)
        or not uint(r.flags) or not uint(r.effects) then return nil,'INVALID_RECORD' end
    if r.peer~=peer:upper() then return nil,'OTHER_PLAYER' end
    if r.epoch~=epoch:upper() then return nil,'OTHER_MISSION' end
    -- A fire element can be an ordinary incendiary bullet. Mode comes from the
    -- actual attack branch, not its element, equipped gun or last kill.
    if not required(r.flags,0x143) or r.target_kind~=1 then return nil,'CONTACT_NOT_PROVEN' end
    local result
    if r.branch==2 then
        result='ricochet' -- current copy emits 2 only at the qualified reflection writeback
    elseif r.branch==1 then
        if not required(r.flags,0x1FF) then return nil,'ARMOUR_FIELDS_NOT_PROVEN' end
        if r.effects~=0 then return nil,'FORCED_OR_CUSTOM_RESULT' end
        if not finite(r.delta) or not finite(r.selected_ap) or not finite(r.armour)
            or not finite(r.factor) then return nil,'NONFINITE_ARMOUR_RESULT' end
        -- delta is the native f32 subtraction. Do not recompute in Lua double.
        if r.delta<0 then result='blocked'
        elseif r.delta<1 then result='penetration'
        else result='full_penetration' end
    else return nil,'UNKNOWN_NATIVE_BRANCH' end
    local attribution_only=flag(r.flags,M.flags.attribution_only)
    if attribution_only and(not flag(r.flags,M.flags.damage_info)or not uint(r.damage_info_id))then
        return nil,'DAMAGE_INFO_NOT_PROVEN'
    end
    return {verified=true,local_player=true,direct=true,attack='projectile',
        result=result,count=attribution_only and 0 or 1,target=r.target,source=r.source,owner=r.owner,
        attribution_only=attribution_only or nil,
        damage_info_id=flag(r.flags,M.flags.damage_info)and uint(r.damage_info_id)and r.damage_info_id or nil,
        projectile_id=flag(r.flags,M.flags.projectile_type)and uint(r.projectile_id)and r.projectile_id or nil,
        native_sequence=r.sequence}
end

function M.new(options)
    assert(type(options)=='table' and hex(options.peer) and hex(options.epoch)
        and options.peer~='0000000000000000' and options.epoch~='0000000000000000'
        and type(options.accept)=='function','native hit feedback needs exact peer/epoch and a sink')
    local peer,epoch=options.peer:upper(),options.epoch:upper()
    local observe_record=options.observe_record
    assert(observe_record==nil or type(observe_record)=='function','native hit record observer')
    local api={accepted=0,unclassified=0,stale=0,partial=false,last_sequence='0000000000000000'}
    local dropped,last_now='0000000000000000',0
    function api:consume(raw,now,transport)
        if not finite(now) or now<last_now or now<0 then return nil,'INVALID_CLOCK' end
        if type(transport)~='table' or transport.abi~=1 or transport.stride~=96
            or transport.connector_proven~=true or not uint(transport.count)
            or transport.count>64 or not hex(transport.epoch) or transport.epoch:upper()~=epoch
            or not hex(transport.dropped) then return nil,'TRANSPORT_NOT_PROVEN' end
        if type(raw)~='string' or #raw~=transport.count*96 then return nil,'BATCH_SIZE' end
        local current_drop=transport.dropped:upper()
        if current_drop<dropped then return nil,'TRANSPORT_COUNTER_REWIND' end
        if current_drop~=dropped then self.partial=true;dropped=current_drop end
        last_now=now
        for index=0,transport.count-1 do
            local r=M.decode(raw,index*96)
            if r.epoch~=epoch then
                self.unclassified=self.unclassified+1
            elseif r.sequence<=self.last_sequence then
                self.stale=self.stale+1
            else
                self.last_sequence=r.sequence
                local contact,why=M.classify(r,peer,epoch)
                if contact then
                    if options.accept(contact,now)~=false then self.accepted=self.accepted+1 end
                    if observe_record then
                        local ok,keep=pcall(observe_record,r,contact,raw,index*96,now)
                        if not ok then self.observer_reason=tostring(keep);observe_record=nil
                        elseif keep==false then observe_record=nil end
                    end
                else self.unclassified=self.unclassified+1;self.last_reason=why end
            end
        end
        return true
    end
    return api
end

return M
