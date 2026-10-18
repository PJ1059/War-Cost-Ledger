-- Read-only 4 Hz destruction-stage observer. A close is the same hole's
-- registered record changing 0 -> positive, never a despawn or queue receipt.
-- Native layouts and catalog are provided by demolition-world's pinned view.
-- This observes closure only; network ownership is not demolition attribution.
local M={interval=0.25,max_descriptors=1024,max_descriptor_reads=32,
    max_seen=1024,max_positions=4,max_record_index=0x17C00,
    max_record_reads=24,max_record_bytes=49152,max_record_span=4096,max_window_gap=32,max_poll_gap=0.75}
local function uint(n,max)return type(n)=='number'and n==math.floor(n)and n>=0 and n<max end
local function finite(n)return type(n)=='number'and n==n and n~=math.huge and n~=-math.huge end
local function copy_position(at)
    if type(at)~='table'or not finite(at.x)or not finite(at.y)or not finite(at.z)
        or math.abs(at.x)>100000 or math.abs(at.y)>100000 or math.abs(at.z)>100000 then return nil end
    return {x=at.x,y=at.y,z=at.z}
end
function M.new(options)
    assert(type(options)=='table'and type(options.world_api)=='table','BUGHOLE_OPTIONS')
    local source=options.world_api
    local api={diagnostics={}}
    local known,seen,seen_count,next_poll,stamp,record_cursor,position_cursor={}, {},0,0,0,1,1
    local game,destruction,mission,pointers,indices,record_block,last_poll
    local d=api.diagnostics
    function api:reset(sequence)
        known,seen,seen_count,next_poll,stamp,record_cursor,position_cursor={},{},0,0,0,1,1
        game,destruction,mission,pointers,indices,record_block,last_poll=nil,nil,sequence,nil,nil,nil,nil
        d.ready,d.reason=false,'BUGHOLE_NOT_SAMPLED'
        d.polls,d.closures,d.position_missing,d.descriptor_reads,d.descriptor_pending=0,0,0,0,0
        d.known_holes,d.seen,d.record_bytes,d.position_reads,d.skipped_positions=0,0,0,0,0
        d.descriptor_count,d.valid_pointers,d.invalid_pointers,d.invalid_indices=0,0,0,0
        d.cached_descriptors,d.descriptor_failures,d.nonhole_descriptors=0,0,0
        d.resource_samples={}
        d.cached_positions,d.prefetched_positions=0,0
        d.record_reads,d.record_holes_read,d.record_unread,d.incomplete=0,0,0,false
        d.reads_bound,d.bytes_bound=0,0
        -- Worst case includes 13 first-world pins, 5 list reads, 32 new
        -- descriptors, 24 stage windows and 4 x 12 unit-position reads.
        d.max_reads,d.max_bytes=128,65536
        d.world=nil
    end
    api:reset(options.mission)
    local function fail(why)
        -- A gap cannot become a delayed close attributed to a later explosion.
        for _,item in pairs(known)do item.stage=nil end
        d.ready,d.reason=false,why
        return nil,why
    end
    local function step(self,world,now,sequence)
        if not finite(now)or now<0 then return fail('BUGHOLE_TIME')end
        if not world or type(world.view)~='table'then return fail('BUGHOLE_WORLD_UNAVAILABLE')end
        if game~=world.game or mission~=sequence then self:reset(sequence);game=world.game end
        if last_poll and now<last_poll then last_poll=now;return fail('BUGHOLE_POLL_GAP')end
        -- Throttled frames are successful no-ops, even after a prior failed
        -- poll; only the actual failed read signals a new observation gap.
        if now<next_poll then return{}end
        next_poll=now+M.interval
        if last_poll and now-last_poll>M.max_poll_gap then last_poll=now;return fail('BUGHOLE_POLL_GAP')end
        last_poll=now
        d.polls=d.polls+1
        d.ready,d.reason=false,'BUGHOLE_REFRESH_INCOMPLETE'
        if type(source.destructibles)~='function'or type(source.destructible_descriptor)~='function'
            or type(source.bug_hole_kind)~='function'or type(source.destruction_records)~='function'
            or type(source.destruction_record)~='function'or type(source.unit_position)~='function'then
            return fail('BUGHOLE_API_UNAVAILABLE')
        end
        pointers=pointers or world.view.slot();indices=indices or world.view.slot()
        record_block=record_block or world.view.slot()
        local list,why=source.destructibles(world,pointers,indices)
        if not list or not uint(list.count,M.max_descriptors+1)or not list.world then
            return fail(why or'BUGHOLE_LIST_UNREADABLE')
        end
        if destruction~=list.world then
            known,seen,seen_count,record_cursor,position_cursor={},{},0,1,1;destruction=list.world
        end
        stamp=stamp+1
        local reads,pending,holes=0,0,0
        local valid_pointers,invalid_pointers,invalid_indices,failures,nonholes,cached=0,0,0,0,0,0
        local resource_samples,resource_seen={},{}
        local hole_items={}
        for i=0,list.count-1 do
            local pointer,index=list.pointers:ptr(i*8),list.indices:i32(i*4)
            if pointer then valid_pointers=valid_pointers+1 else invalid_pointers=invalid_pointers+1 end
            if not uint(index,M.max_record_index)then invalid_indices=invalid_indices+1 end
            if pointer and uint(index,M.max_record_index)then
                local item=known[pointer]
                if item and item.index~=index then known[pointer]=nil;item=nil end
                if not item and reads<M.max_descriptor_reads then
                    reads=reads+1
                    local descriptor=source.destructible_descriptor(world,pointer)
                    if descriptor and uint(descriptor.unit,4294967296)and descriptor.unit>0
                        and uint(descriptor.entity,4294967296)and type(descriptor.resource)=='string'then
                        item={index=index,unit=descriptor.unit,entity=descriptor.entity,resource=descriptor.resource,
                            kind=source.bug_hole_kind(descriptor.resource)}
                        known[pointer]=item
                    else failures=failures+1 end
                end
                if item then
                    cached=cached+1
                    item.stamp=stamp
                    if item.kind then
                        holes=holes+1
                        hole_items[#hole_items+1]={pointer=pointer,item=item}
                    else nonholes=nonholes+1 end
                    -- Existing descriptor bytes only: enough to distinguish a
                    -- missing resource mapping from an empty/invalid native
                    -- list, without extra process reads or unbounded logs.
                    if #resource_samples<8 and not resource_seen[item.resource]then
                        resource_seen[item.resource]=true
                        resource_samples[#resource_samples+1]=item.resource
                    end
                else pending=pending+1 end
            end
        end
        for pointer,item in pairs(known)do if item.stamp~=stamp then known[pointer]=nil end end
        d.descriptor_reads,d.descriptor_pending,d.known_holes=reads,pending,holes
        d.descriptor_count,d.valid_pointers,d.invalid_pointers,d.invalid_indices=list.count,valid_pointers,invalid_pointers,invalid_indices
        d.cached_descriptors,d.descriptor_failures,d.nonhole_descriptors=cached,failures,nonholes
        d.resource_samples=resource_samples
        d.position_reads,d.skipped_positions,d.record_bytes,d.record_reads=0,0,0,0
        d.cached_positions,d.prefetched_positions=0,0
        d.record_holes_read,d.record_unread,d.incomplete=0,0,pending>0
        d.world=destruction
        if holes==0 then
            d.reads_bound,d.bytes_bound=18+reads,list.count*12+reads*24+128
            d.ready,d.reason,d.seen=true,nil,seen_count;return{}
        end
        table.sort(hole_items,function(a,c)return a.item.index<c.item.index end)
        if record_cursor>#hole_items then record_cursor=1 end
        local snapshots,visited={},0
        local at=record_cursor
        -- One window often covers the whole cluster. Widely separated records
        -- are split instead of reading a megabyte of unrelated destruction.
        while visited<#hole_items and d.record_reads<M.max_record_reads
            and d.record_bytes+12<=M.max_record_bytes do
            local first=hole_items[at].item.index
            local last,last_at=first,at
            local available=math.min(M.max_record_span,math.floor((M.max_record_bytes-d.record_bytes)/12))
            while last_at<#hole_items and visited+(last_at-at+1)<#hole_items do
                local following=hole_items[last_at+1].item.index
                if following-last>M.max_window_gap or following-first+1>available then break end
                last,last_at=following,last_at+1
            end
            d.record_reads=d.record_reads+1;d.record_bytes=d.record_bytes+(last-first+1)*12
            local records,record_why=source.destruction_records(world,list,first,last,record_block)
            if not records then return fail(record_why or'BUGHOLE_RECORDS_UNREADABLE')end
            for i=at,last_at do
                local item=hole_items[i].item
                local unit,stage,registered=source.destruction_record(records,(item.index-first)*12)
                snapshots[item]={unit=unit,stage=stage,registered=registered}
                visited=visited+1
            end
            at=last_at+1
            if at>#hole_items then at=1 end
        end
        record_cursor=at
        d.record_holes_read,d.record_unread=visited,#hole_items-visited
        d.incomplete=d.incomplete or d.record_unread>0
        local rows={}
        for pointer,item in pairs(known)do
            if item.kind then
                local snapshot=snapshots[item]
                -- A budget-skipped record is still the same observed hole.
                -- Clearing its baseline here prevents any closure in a world
                -- with more sparse windows than the per-poll read budget.
                -- Actual failed reads/gaps clear every baseline in fail().
                if snapshot then
                    local unit,stage,registered=snapshot.unit,snapshot.stage,snapshot.registered
                    if unit~=item.unit or not registered or not uint(stage,4)then known[pointer]=nil
                    else
                    if item.stage==0 and stage>0 then
                        local id=table.concat({tostring(destruction),tostring(item.index),tostring(item.unit),
                            tostring(item.entity),item.resource},':')
                        if not seen[id]and seen_count<M.max_seen then
                            -- Mark before callbacks and even without a position: never replay
                            -- a closure later against unrelated explosion candidates.
                            seen[id]=true;seen_count=seen_count+1
                            -- Level units can disappear as soon as they close.
                            -- Prefer the position observed while this exact
                            -- registered hole was live, before reading it anew.
                            local position=copy_position(item.position)
                            if position then d.cached_positions=d.cached_positions+1
                            elseif d.position_reads<M.max_positions then
                                d.position_reads=d.position_reads+1
                                position=copy_position(source.unit_position(world,item.unit,true))
                            else d.skipped_positions=d.skipped_positions+1 end
                            if not position then d.position_missing=d.position_missing+1 end
                            local row={id=id,time=now,stage=stage,level=stage,position=position,
                                hole=item.kind,unit=item.unit,unit_id=item.unit,entity=item.entity,
                                entity_id=item.entity,record_index=item.index,resource=item.resource,
                                type=item.resource,world=destruction,closure_observed=true,
                                creditor_verified=false}
                            rows[#rows+1]=row;d.closures=d.closures+1
                        end
                    end
                    item.stage=stage
                    end
                end
            end
        end
        -- Use the same four-read budget to cache static, live hole positions.
        -- Closures have priority; rotating over remaining live holes prevents
        -- an unreadable first hole from starving all later ones.
        if position_cursor>#hole_items then position_cursor=1 end
        local position_visited=0
        while position_visited<#hole_items and d.position_reads<M.max_positions do
            local entry=hole_items[position_cursor]
            local item=entry.item
            if known[entry.pointer]==item and item.stage==0 and not item.position then
                d.position_reads=d.position_reads+1
                item.position=copy_position(source.unit_position(world,item.unit,true))
                if item.position then d.prefetched_positions=d.prefetched_positions+1 end
            end
            position_visited=position_visited+1
            position_cursor=position_cursor%#hole_items+1
        end
        d.ready,d.reason,d.seen=true,nil,seen_count
        d.reads_bound=18+reads+d.record_reads+d.position_reads*12
        d.bytes_bound=list.count*12+reads*24+d.record_bytes+d.position_reads*96+128
        if options.emit then for _,row in ipairs(rows)do options.emit(row)end end
        return rows
    end
    function api:step(world,now,sequence)
        local ok,rows,why=pcall(step,self,world,now,sequence)
        if not ok then return fail('BUGHOLE_READ_EXCEPTION')end
        return rows,why
    end
    return api
end
return M
