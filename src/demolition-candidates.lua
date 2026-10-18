-- Diagnostic-only destruction receipts. Native before/after bytes prove a
-- stage transition; +0x30 in the queue remains an UNVERIFIED creditor candidate.
-- Nothing in this module updates ribbons, kills, medals or the account.
local M = {record_bytes=128, revision='destruction_consumer_receipt_v1'}
local function u32(raw, at)
    local a,b,c,d=raw:byte(at+1,at+4)
    return d and a+b*256+c*65536+d*16777216 or nil
end
local function peer(raw,at)
    return string.format('%08X%08X',u32(raw,at+4),u32(raw,at))
end
local function pointer(raw,at)
    local lo,hi=u32(raw,at),u32(raw,at+4)
    if not hi or hi>=32768 then return nil end
    local value=lo+hi*4294967296
    return value>=65536 and value or nil
end
local function uint(n,limit)
    return type(n)=='number'and n==math.floor(n)and n>=0 and n<(limit or 4294967296)
end

function M.decode(raw)
    if type(raw)~='string'or#raw~=M.record_bytes then return nil,'RECEIPT_SIZE'end
    local world=pointer(raw,0)
    if not world then return nil,'RECEIPT_WORLD'end
    local index=u32(raw,0x28)
    -- Deliberately limited to the static-record branch explicitly compared in
    -- the enqueue (13E16D6). Dynamic records require their own future proof.
    if index>=0x17000 then return nil,'RECEIPT_RECORD_INDEX'end
    local before_unit,after_unit=u32(raw,0x50),u32(raw,0x5c)
    local before_stage,after_stage=raw:byte(0x58),raw:byte(0x64)
    local before_flags,after_flags=raw:byte(0x59),raw:byte(0x65)
    local processed_before=raw:byte(0x49)
    return {world=world,local_peer=peer(raw,8),source_peer_candidate=peer(raw,0x40),
        sequence=u32(raw,0x68),record_index=index,unit=before_unit,
        before_stage=before_stage,after_stage=after_stage,
        before_flags=before_flags,after_flags=after_flags,
        source_u32_a=u32(raw,0x2c),source_u32_b=u32(raw,0x30),
        requested_stage=raw:byte(0x39),processed_before=processed_before,
        stage_transition=before_unit==after_unit and before_unit~=0
            and before_flags%2==1 and after_flags%2==1
            and processed_before==0 and before_stage==0 and after_stage>0,
        creditor_verified=false, ribbon_eligible=false}
end

-- Uses Runtime descriptor APIs or demolition-world's pinned read-only subset;
-- no code/heap scan. Refresh
-- at 4 Hz, at most 32 new 24-byte descriptors per poll. The instance arrays are
-- already capped at 1,024 by the Runtime schema. Failed reads never reuse maps.
function M.new(options)
    assert(type(options)=='table'and type(options.world_api)=='table','DEMOLITION_OPTIONS')
    local api,known,by_index,seen={diagnostics={samples=0,holes=0,unknown=0,rejected=0,
        ready=false,reason='DESTRUCTION_NOT_SAMPLED',descriptor_count=0,
        cached_descriptors=0,known_holes=0,pending_descriptors=0,invalid_descriptors=0,
        descriptor_failures=0,incomplete=true,receipts_seen=0,target_missing=0,
        unit_mismatch=0,unknown_limit=0}}, {},{},{}
    local source=options.world_api
    local last_game,last_world,next_poll,stamp=nil,nil,0,0
    local pointer_block,index_block
    function api:reset()
        known,by_index,seen={},{},{}
        last_game,last_world,next_poll,stamp=nil,nil,0,0
        pointer_block,index_block=nil,nil
        self.diagnostics.samples,self.diagnostics.holes,self.diagnostics.unknown,self.diagnostics.rejected=0,0,0,0
        self.diagnostics.ready,self.diagnostics.reason=false,'DESTRUCTION_NOT_SAMPLED'
        self.diagnostics.world,self.diagnostics.descriptor_reads=nil,0
        self.diagnostics.descriptor_count,self.diagnostics.cached_descriptors,self.diagnostics.known_holes=0,0,0
        self.diagnostics.pending_descriptors,self.diagnostics.invalid_descriptors,self.diagnostics.descriptor_failures=0,0,0
        self.diagnostics.incomplete=true
        self.diagnostics.receipts_seen,self.diagnostics.target_missing,self.diagnostics.unit_mismatch,self.diagnostics.unknown_limit=0,0,0,0
    end
    local function failed(self,why)
        by_index={}
        self.diagnostics.ready,self.diagnostics.reason=false,why
        self.diagnostics.world=nil
        self.diagnostics.known_holes,self.diagnostics.incomplete=0,true
        return nil,why
    end
    function api:refresh(world,now)
        if not world or type(now)~='number'then return failed(self,'WORLD_UNAVAILABLE')end
        if world.game~=last_game then self:reset();last_game=world.game end
        if now<next_poll then return self.diagnostics.ready or nil,self.diagnostics.reason end
        next_poll=now+0.25
        -- Mark stale before any adapter call: a caller-caught Lua exception
        -- must not leave a successful-looking map during the throttle window.
        failed(self,'DESTRUCTION_REFRESH_INCOMPLETE')
        if type(source.destructibles)~='function'or type(source.destructible_descriptor)~='function'
            or type(source.bug_hole_kind)~='function'then return failed(self,'RUNTIME_DESTRUCTION_UNAVAILABLE')end
        pointer_block=pointer_block or world.view.slot()
        index_block=index_block or world.view.slot()
        local list,reason=source.destructibles(world,pointer_block,index_block)
        if not list or not uint(list.count,1025)or not list.world then
            return failed(self,reason or'DESTRUCTIBLES_UNREADABLE')
        end
        if last_world~=list.world then
            known,seen={},{ };last_world=list.world
            self.diagnostics.samples,self.diagnostics.holes,self.diagnostics.unknown=0,0,0
        end
        stamp=stamp+1
        local next_map,reads={},0
        local cached,hole_count,pending,invalid,failures=0,0,0,0,0
        for i=0,list.count-1 do
            local p,index=list.pointers:ptr(i*8),list.indices:i32(i*4)
            if p and uint(index,0x17000)then
                local item=known[p]
                if item and item.index~=index then item=nil;known[p]=nil end
                if not item and reads<32 then
                    reads=reads+1
                    local d=source.destructible_descriptor(world,p)
                    if d then
                        item={index=index,unit=d.unit,entity=d.entity,resource=d.resource,
                            kind=source.bug_hole_kind(d.resource)}
                        known[p]=item
                    else failures=failures+1 end
                end
                if item then
                    item.stamp=stamp
                    cached=cached+1
                    if item.kind then next_map[index]=item;hole_count=hole_count+1 end
                else pending=pending+1 end
            else invalid=invalid+1 end
        end
        for p,item in pairs(known)do if item.stamp~=stamp then known[p]=nil end end
        by_index=next_map
        self.diagnostics.descriptor_reads=reads
        self.diagnostics.descriptor_count,self.diagnostics.cached_descriptors,self.diagnostics.known_holes=list.count,cached,hole_count
        self.diagnostics.pending_descriptors,self.diagnostics.invalid_descriptors,self.diagnostics.descriptor_failures=pending,invalid,failures
        self.diagnostics.incomplete=pending>0 or invalid>0
        self.diagnostics.world=last_world
        self.diagnostics.ready,self.diagnostics.reason=true,nil
        return true
    end
    function api:accept(raw,expected_world,expected_peer)
        self.diagnostics.receipts_seen=self.diagnostics.receipts_seen+1
        local row,why=M.decode(raw)
        if not row then self.diagnostics.rejected=self.diagnostics.rejected+1;return nil,why end
        if row.world~=expected_world or row.world~=last_world or row.local_peer~=expected_peer then
            self.diagnostics.rejected=self.diagnostics.rejected+1;return nil,'RECEIPT_CONTEXT_CHANGED'
        end
        local key=tostring(row.sequence)..':'..tostring(row.record_index)..':'..tostring(row.unit)
        if seen[key]then return nil,'RECEIPT_DUPLICATE'end
        local item=by_index[row.record_index]
        row.target_verified=item~=nil and item.unit==row.unit
        if not item then self.diagnostics.target_missing=self.diagnostics.target_missing+1
        elseif item.unit~=row.unit then self.diagnostics.unit_mismatch=self.diagnostics.unit_mismatch+1 end
        -- Reserve capacity for holes so incidental decoration cannot exhaust
        -- the sample before the player seals a hole. Seen keys stay <=40.
        if row.target_verified then
            if self.diagnostics.holes>=32 then return nil,'RECEIPT_HOLE_LIMIT'end
        elseif self.diagnostics.unknown>=8 then
            self.diagnostics.unknown_limit=self.diagnostics.unknown_limit+1
            return nil,'RECEIPT_UNKNOWN_LIMIT'
        end
        seen[key]=true
        if row.target_verified then
            row.target_kind,row.entity,row.type=item.kind,item.entity,item.resource
            self.diagnostics.holes=self.diagnostics.holes+1
        else
            self.diagnostics.unknown=self.diagnostics.unknown+1
        end
        row.candidate_matches_local=row.source_peer_candidate==row.local_peer
            and row.local_peer~='0000000000000000'
        self.diagnostics.samples=self.diagnostics.samples+1
        if options.emit then options.emit(row)end
        return row
    end
    return api
end
return M
