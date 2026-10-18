-- Death observations and source inference are separate. No native actions or stat changes.
-- Runtime events are supplied by the caller; all identity values are frozen before delay.
local function integer(v,max) return type(v)=='number' and v>=0 and v<=max and v%1==0 end
local function finite(v) return type(v)=='number' and v==v and v>-math.huge and v<math.huge end
local function peer(v)
    return type(v)=='string' and #v==16 and not v:find('[^%x]') and v~='0000000000000000' and v:upper() or nil
end
local function text(v) return type(v)=='string' and #v>0 and #v<=128 and v or nil end
local function position(p)
    if p and finite(p.x)and finite(p.y)and finite(p.z)then return{x=p.x,y=p.y,z=p.z}end
end
local function plain(v)
    if type(v)~='table' then return v end
    local out={};for key,value in pairs(v) do if type(value)~='function' then out[key]=plain(value) end end
    return out
end
local function identity(value)
    if type(value)~='table' then return nil end
    local id=peer(value.peer_id or value.peer)
    if not id then return nil end
    local slot_index=integer(value.slot_index,3) and value.slot_index or integer(value.slot,3) and value.slot or nil
    return {name=text(value.name),callsign=text(value.callsign),slot=slot_index and slot_index+1 or nil,slot_index=slot_index,
        peer_id=id,persona_index=integer(value.persona_index,3) and value.persona_index or nil,
        avatar_id=integer(value.avatar_id or value.avatar,4294967295) and (value.avatar_id or value.avatar) or nil,
        identity_scope='session_peer_not_permanent_account',identity_source=text(value.identity_source)}
end
local function find_peer(list,id)
    if not id then return nil end
    for _,row in ipairs(list or {}) do if row.peer_id==id then return plain(row) end end
end
local function find_avatar(list,id)
    if not id or id==0 then return nil end
    for _,row in ipairs(list or {}) do if row.avatar_id==id then return plain(row) end end
end
return function(options)
    options=options or {}
    local reader,catalog=options.reader,options.catalog or {}
    local resource_names=type(options.resource_names)=='table'and options.resource_names or {}
    local payloads=type(options.damage_catalog)=='table'and options.damage_catalog or {}
    local vehicles=type(options.vehicle_sources)=='table'and options.vehicle_sources or {}
    local api={diagnostics={records=0,pending=0,duplicates=0,rejected=0,dropped=0,reader_failures=0,
        reader_reasons={},
        native_fatal_event_proven=false,policy='observed_death_with_optional_last_source_inference'}}
    local pending,output,indices,avatars,event_keys,damages={},{},{},{},{},{}
    local unindexed_events,unpaired_counters={},{}
    local last_context,last_roster,last_now,ordinal,next_roster=nil,{},0,0,0
    local queued,queue_scope,queue_token={},nil,nil
    local seen_queue,seen_queue_order={},{}
    local witnesses={}
    local remote_ids,remote_order={},{}
    local nearby=options.nearby_deaths==true
    local KIND={[0]='射击',[1]='跳弹',[2]='持续伤害',[3]='光束',[4]='爆炸',
        [5]='撞击',[6]='近战／特殊攻击',[7]='其他伤害',[8]='溺水',[9]='失血'}
    local ELEMENT={[1]='燃烧',[2]='电击',[3]='酸蚀',[4]='流血',[5]='毒气'}
    local function cause_name(kind,element)
        return kind==2 and(ELEMENT[element]or KIND[2])or KIND[kind]
    end
    local function final_cause(raw)
        local cause=raw and raw.damage_cause
        if type(cause)=='table'and cause.owned==true and cause.current==true
            and cause.source=='native_health_extension'and raw.life==2 and cause.life==2
            and integer(cause.kind,9)and integer(cause.element,255)then return cause end
    end
    local function weapon(hash)
        hash=peer(hash);if not hash then return nil end
        local vehicle=vehicles[hash]
        if type(vehicle)=='table'then return text(vehicle.name_zh or vehicle.name),hash end
        local info=resource_names[hash]
        if type(info)=='table'and(info.kind=='weapon'or info.kind=='stratagem'or info.kind=='throwable')then
            return text(info.name_zh or info.name or info.name_en),hash
        end
        -- Reuse the complete static resource-to-payload graph. Shared roots
        -- and unlabelled origins cannot uniquely identify a death weapon.
        local roots=payloads.resource_nodes and payloads.resource_nodes[hash]
        local candidates,seen={},{}
        for _,root in ipairs(roots or {})do
            local row=payloads.reverse and payloads.reverse[root.kind]and payloads.reverse[root.kind][tostring(root.id)]
            if not row or row.unresolved then return nil end
            for _,candidate in ipairs(row.candidates or {})do
                if not seen[candidate]then candidates[#candidates+1]=candidate;seen[candidate]=true end
            end
        end
        if #candidates==1 then
            local candidate=candidates[1];local row=resource_names[candidate]
            if type(row)=='table'then return text(row.name_zh or row.name or row.name_en),candidate end
        end
    end
    local function reader_call(method,...)
        if type(reader)~='table' or type(reader[method])~='function' then return nil,'DEATH_READER_UNAVAILABLE' end
        local ok,result,reason=pcall(reader[method],reader,...)
        if not ok or not result then
            local key=tostring(not ok and result or reason or'DEATH_READER_NO_RESULT'):sub(1,128)
            api.diagnostics.reader_failures=api.diagnostics.reader_failures+1
            api.diagnostics.last_reader_reason=key
            local counts=api.diagnostics.reader_reasons
            if counts[key]then counts[key]=counts[key]+1
            else local n=0;for _ in pairs(counts)do n=n+1 end;if n<16 then counts[key]=1 end end
        end
        if not ok then return nil,tostring(result) end
        return result,reason
    end
    local function roster(context,world,list,now,force)
        list=list or context.players or {}
        local enriched
        if world and (force or now>=next_roster) then
            enriched=reader_call('players',world,list)
            next_roster=now+1
            if enriched then last_roster=plain(enriched) end
        end
        local out={}
        for i,row in ipairs(list) do
            if i>4 then break end
            local copy=identity(row)
            if copy then
                local known=find_peer(enriched or last_roster,copy.peer_id)
                -- The cached peer identity predates this event. A later P-slot
                -- occupant is never allowed to fill a missing name after death.
                if known then
                    copy.name=copy.name or known.name;copy.persona_index=copy.persona_index or known.persona_index
                    copy.callsign=copy.callsign or known.callsign
                    copy.identity_source=known.identity_source or 'pre_event_peer_snapshot'
                end
                out[#out+1]=copy
            end
        end
        return out
    end
    local function freeze(event,context,allow_remote)
        context=context or last_context or {}
        local now=finite(context.now) and context.now or last_now
        local seq=integer(context.sequence,9007199254740991) and context.sequence or nil
        if not seq then return nil,'DEATH_SEQUENCE_UNAVAILABLE' end
        local local_peer=peer(context.local_peer)
        local victim_peer=peer(event.peer or type(event.player)=='table' and event.player.peer) or local_peer
        if not allow_remote and(event.local_player~=true or local_peer and victim_peer and local_peer~=victim_peer)then return nil,'NOT_LOCAL_DEATH' end
        local raw_avatar=event.avatar_id or event.entity_id or type(event.avatar)=='table' and event.avatar.id or context.avatar
        local avatar=integer(raw_avatar,4294967295) and raw_avatar>0 and raw_avatar or nil
        local players=roster(context,context.world,context.players,now,true)
        local victim=find_peer(players,victim_peer) or {peer_id=victim_peer,identity_scope='session_peer_not_permanent_account'}
        victim.avatar_id=avatar
        return {sequence=seq,now=now,world=context.world,local_peer=local_peer or victim_peer,
            victim=victim,players=players,avatar=avatar,death_index=integer(context.death_index,2147483647)
                and context.death_index>0 and context.death_index or nil,
            occurred_at=finite(context.occurred_at) and context.occurred_at>=0 and context.occurred_at or nil,
            mission_elapsed=finite(context.mission_elapsed) and context.mission_elapsed>=0
                and context.mission_elapsed or nil,skip_attribution=context.skip_attribution==true,
                position=position(event.position)}
    end
    local function sequence_peer(ctx) return tostring(ctx.sequence)..':'..tostring(ctx.local_peer or '-') end
    local function source_snapshot(ctx)
        if ctx.skip_attribution or not ctx.world or not ctx.avatar then return nil,'DEATH_SOURCE_NOT_SAMPLED' end
        local raw,reason=reader_call('read',ctx.world,ctx.avatar)
        if raw and raw.avatar_id~=ctx.avatar then return nil,'DEATH_SOURCE_AVATAR_CHANGED' end
        if raw then ctx.position=ctx.position or position(raw.position)end
        return raw and plain(raw),reason
    end
    local function recent_damage(ctx)
        for i=#damages,1,-1 do local damage=damages[i]
            if damage.sequence==ctx.sequence and damage.avatar==ctx.avatar and damage.peer==ctx.local_peer
                and ctx.now>=damage.now and ctx.now-damage.now<=1.5 then return plain(damage) end
        end
    end
    local function recent_queue(ctx)
        for i=#queued,1,-1 do local item=queued[i]
            if item.sequence==ctx.sequence and item.avatar==ctx.avatar and item.peer==ctx.local_peer
                and ctx.now>=item.now and ctx.now-item.now<=1.5 then return plain(item)end
        end
    end
    function api:sample_damage(now,context)
        if not finite(now)or type(context)~='table'or not integer(context.sequence,9007199254740991)
            or not integer(context.avatar,4294967295)or context.avatar==0 or not context.world then return false end
        if not reader or type(reader.damage_events)~='function'then return false end
        local scope=tostring(context.sequence)..':'..tostring(context.avatar)..':'..tostring(context.local_peer)
        if scope~=queue_scope or last_now>now then
            queued,queue_token,seen_queue,seen_queue_order={},nil,{},{};queue_scope=scope
        end
        local snapshot=reader_call('damage_events',context.world,context.avatar)
        if not snapshot or type(snapshot.events)~='table'then return false end
        if snapshot.token==queue_token then return true end
        queue_token=snapshot.token
        for _,event in ipairs(snapshot.events)do
            if event.target==context.avatar and integer(event.kind,9)and integer(event.element,255)
                and finite(event.damage)and event.damage>0 and(not event.token or not seen_queue[event.token])then
                if type(event.token)=='string'then
                    seen_queue[event.token]=true;seen_queue_order[#seen_queue_order+1]=event.token
                    if #seen_queue_order>256 then seen_queue[table.remove(seen_queue_order,1)]=nil end
                end
                queued[#queued+1]={sequence=context.sequence,avatar=context.avatar,peer=context.local_peer,
                    now=now,event=plain(event),players=plain(context.players or {})}
                if #queued>8 then table.remove(queued,1)end
            end
        end
        return true
    end
    local function queue_source(entry,raw,cause)
        local ctx,record=entry.context,entry.record
        local saved=entry.queued
        local event=saved and saved.event
        if not event or cause and(event.kind~=cause.kind or event.element~=cause.element)then return false end
        local evidence=record.evidence
        evidence.damage_kind_id,evidence.damage_element_id=event.kind,event.element
        evidence.damage_dealer,evidence.damage_owner=event.dealer_goid,event.owner_goid
        evidence.source_channel='local_damage_queue'
        record.damage_kind=cause_name(event.kind,event.element)
        local players={}
        for _,row in ipairs(saved.players or {})do local p=identity(row);if p then players[#players+1]=p end end
        local native_actor=find_avatar(players,event.owner_entity)
        local creditor=peer(event.creditor)
        local conflict=native_actor and creditor and native_actor.peer_id~=creditor
        local actor=not conflict and(native_actor or find_peer(players,creditor))or nil
        local dealer=event.dealer_entity
        if event.kind==8 or event.kind==5 and dealer==ctx.avatar
            and(not event.owner_entity or event.owner_entity==ctx.avatar)then
            record.category='environment'
            record.damage_kind=event.kind==8 and'溺水'or'坠落／碰撞'
            record.actor_name=record.damage_kind
        else
            local type_hash=peer(event.owner_type)
            local info=type_hash and catalog[type_hash]
            local dealer_hash=peer(event.dealer_type)
            local dealer_info=dealer_hash and catalog[dealer_hash]
            -- Some attacks retain the victim as owner. A real enemy dealer
            -- must not be hidden by that avatar alias or its stale creditor.
            if dealer_info and dealer_info.kill==true and dealer_info.asset~=true
                and(not info or info.kill~=true or event.owner_entity==ctx.avatar)then
                type_hash,info=dealer_hash,dealer_info
            end
            local enemy=type(info)=='table'and info.kill==true and info.asset~=true
            if enemy and(type_hash==dealer_hash or not native_actor)then
                record.category='enemy';record.actor_name=text(info.name_zh or info.name or info.name_en)
                evidence.actor_type_hash=type_hash
            elseif actor then
                record.category=actor.peer_id==ctx.local_peer and'self'or'player'
                record.actor_name=actor.name;record.player=actor
            else
                record.category='environment';record.actor_name=record.damage_kind
                if conflict then evidence.source_reason='CONFLICTING_SOURCE_EVIDENCE'end
            end
            local name,hash=weapon(event.dealer_type)
            if not name then name,hash=weapon(event.owner_type)end
            if name then record.weapon_name=name;evidence.weapon_type_hash=hash end
        end
        record.confidence='inferred'
        evidence.damage_kind_proven=cause~=nil
        return true
    end
    local function classify(entry)
        local record,ctx=entry.record,entry.context
        record.category,record.confidence='unknown','unknown'
        if ctx.skip_attribution then record.evidence.source_reason='COUNTER_GAP_ATTRIBUTION_SKIPPED';return end
        if entry.counter_avatar_unproven then record.evidence.source_reason='COUNTER_VICTIM_AVATAR_NOT_DEAD';return end
        local damage=entry.damage
        local raw=entry.native or damage and damage.native
        local cause=final_cause(raw)
        if queue_source(entry,raw,cause)then return end
        if entry.native_conflict then record.evidence.source_reason=entry.native_conflict;return end
        local creditor,owner,kind
        if raw then
            creditor=peer(raw.last_creditor);owner=raw.last_owner;kind=raw.last_owner_type
            if (not owner or owner==0) and not creditor then
                owner,kind,creditor=raw.down_owner,raw.down_owner_type,peer(raw.down_creditor)
                record.evidence.used_downing_source=true
            end
        end
        local damage_peer=damage and damage.attacker_peer
        -- These persisted cause fields are written on the owned Health death
        -- transition, not inferred from a weapon name or a creditor peer. A
        -- player can be identified independently of the fire/gas death kind.
        local status_kind=cause and cause_name(cause.kind,cause.element)
        if status_kind then
            record.damage_kind=status_kind
            record.evidence.damage_kind_id,record.evidence.damage_element_id=cause.kind,cause.element
            record.evidence.damage_kind_proven=true
            -- Drowning and self-generated impact must not inherit a stale
            -- Health creditor from the last player who dealt damage.
            if cause.kind==8 or cause.kind==5 and owner==ctx.avatar then
                record.category='environment';record.actor_name=cause.kind==8 and'溺水'or'坠落／碰撞'
                record.damage_kind=record.actor_name;record.confidence='inferred'
                record.evidence.source_channel='native_owned_health_death_cause';return
            end
            local name,hash=weapon(kind)
            if name then record.weapon_name=name;record.evidence.weapon_type_hash=hash end
        end
        -- Preserve the complete exact resource hash even when this build's
        -- label catalog does not know it yet. Future reviewed aliases may
        -- resolve a name, but never invent a weapon or a fatal-event claim.
        kind=peer(kind)
        if kind then record.evidence.actor_type_hash=kind end
        local info=kind and catalog[kind]
        local native_actor=find_avatar(ctx.players,owner)
        local credited_actor=find_peer(ctx.players,creditor) or creditor and {peer_id=creditor,
            identity_scope='session_peer_not_permanent_account'}
        local enemy_owner=info and info.kill==true and info.asset~=true and owner and owner~=0 and not native_actor
        -- A zero-creditor attack keeps an earlier Health.lastCreditor. The
        -- Runtime damage peer is derived from that same field, so it is not
        -- independent evidence against a newly recorded exact enemy owner.
        -- Actual player-avatar disagreements remain unresolved.
        if creditor and native_actor and native_actor.peer_id~=creditor
            or not enemy_owner and creditor and damage_peer and creditor~=damage_peer then
            record.evidence.source_reason='CONFLICTING_SOURCE_EVIDENCE';return
        end
        local actor=native_actor or not enemy_owner and credited_actor
        if actor then
            if damage and damage.attacker and damage.attacker.peer_id==actor.peer_id then actor=plain(damage.attacker) end
            record.category=actor.peer_id==ctx.local_peer and 'self' or 'player'
            record.actor_name=actor.name;record.player=plain(actor)
            record.confidence=damage_peer and damage_peer==actor.peer_id and creditor==actor.peer_id and 'inferred' or 'low'
            record.evidence.source_channel='native_health_last_owner_creditor'
        elseif info and info.kill==true and info.asset~=true then
            record.category='enemy';record.actor_name=text(info.name_zh or info.name_en or info.name or info.key)
            record.confidence='low';record.evidence.actor_type_hash=kind
            record.evidence.source_channel='native_health_last_owner_type'
        elseif info and info.kind=='environment' then
            record.category='environment';record.actor_name=text(info.name_zh or info.name)
            record.confidence='low';record.evidence.actor_type_hash=kind
            record.evidence.source_channel='native_health_last_owner_type'
        elseif damage_peer and damage then
            -- Freeze the attacker's identity at the DAMAGE event, not the roster
            -- at death or the roster at the delayed finalisation.
            actor=damage.attacker
            record.category=damage_peer==ctx.local_peer and 'self' or 'player'
            record.player=actor or {peer_id=damage_peer,identity_scope='session_peer_not_permanent_account'}
            record.actor_name=actor and actor.name
            record.confidence='low';record.evidence.source_channel='recent_runtime_player_damaged'
        elseif status_kind then
            record.category='environment';record.actor_name=status_kind;record.confidence='inferred'
            record.evidence.source_channel='native_owned_health_death_cause'
        else
            record.evidence.source_reason=entry.native_reason or 'NO_PROVEN_RECENT_SOURCE'
            local label=kind and resource_names[kind]
            if type(label)=='table'then
                local name=text(label.name_zh or label.name or label.name_en)
                if name and not name:find('[%z\1-\31\127]')then
                    -- Exact resource identity gives a display name only. A
                    -- barrel, vehicle or weapon type is not a proven fatal
                    -- weapon or enemy, so category/confidence stay unknown.
                    record.actor_name=name
                    record.evidence.source_channel='native_health_last_owner_type_label_only'
                end
            end
        end
        -- A contemporaneous resource identity can suggest a weapon, while the
        -- owned extension supplies the final damage kind. Their pairing stays
        -- an inference; there is no native fatal-event callback claim.
    end
    local function finish(entry)
        classify(entry)
        local row,ctx=entry.record,entry.context
        if nearby and not ctx.skip_attribution and not entry.counter_avatar_unproven
            and ctx.position and not row.weapon_name and not row.damage_kind
            and(row.category=='unknown'or row.category=='self'or row.category=='player')then
            local best,distance,interval
            for _,w in ipairs(witnesses)do
                local dt=math.abs(w.context.now-ctx.now)
                if w.context.sequence==ctx.sequence and dt<=1 and w.context.position then
                    local a,p=ctx.position,w.context.position
                    local d=(a.x-p.x)^2+(a.y-p.y)^2+(a.z-p.z)^2
                    if d<=100 and(not best or d<distance or d==distance and dt<interval)then
                        best,distance,interval=w,d,dt
                    end
                end
            end
            if best then
                local source=best.record
                row.weapon_name,row.damage_kind=source.weapon_name,source.damage_kind
                if row.category=='unknown'then
                    row.category=source.category=='enemy'and'enemy'or'environment'
                    row.actor_name=source.weapon_name or source.actor_name or source.damage_kind
                end
                row.confidence='inferred'
                row.evidence.source_reason=nil
                row.evidence.source_channel='nearby_simultaneous_death'
                row.evidence.nearby_death_inferred=true
                row.evidence.nearby_death_distance=math.sqrt(distance)
                row.evidence.nearby_death_interval=interval
                row.evidence.weapon_type_hash=source.evidence.weapon_type_hash
                row.evidence.damage_kind_id=source.evidence.damage_kind_id
                row.evidence.damage_element_id=source.evidence.damage_element_id
                row.evidence.damage_kind_proven=false
            end
        end
        if #output<128 then output[#output+1]=plain(entry.record);api.diagnostics.records=api.diagnostics.records+1
        else api.diagnostics.dropped=api.diagnostics.dropped+1 end
        entry.finished=true;entry.native,entry.damage=nil,nil
    end
    local function remember(queue,entry,unmatched)
        local kept={}
        for _,candidate in ipairs(queue)do if unmatched(candidate)then kept[#kept+1]=candidate end end
        kept[#kept+1]=entry
        if #kept>16 then table.remove(kept,1)end
        return kept
    end
    function api:reset()
        pending,output,indices,avatars,event_keys,damages={},{},{},{},{},{}
        unindexed_events,unpaired_counters={},{}
        last_context,last_roster,last_now,ordinal,next_roster=nil,{},0,0,0
        queued,queue_scope,queue_token,witnesses={},nil,nil,{}
        seen_queue,seen_queue_order={},{}
        remote_ids,remote_order={},{}
        self.diagnostics.pending=0
        if reader and type(reader.reset)=='function' then pcall(reader.reset,reader) end
    end
    function api:on_damaged(event,context)
        if type(event)~='table' or not finite(event.damage) or event.damage<=0 then return nil,'INVALID_DAMAGE_EVENT' end
        local ctx,reason=freeze(event,context)
        if not ctx then return nil,reason end
        self:sample_damage(ctx.now,ctx)
        local attacker_peer=peer(event.attacker_peer or type(event.attacker)=='table' and event.attacker.peer)
        local attacker=find_peer(ctx.players,attacker_peer)
        local raw,native_reason=source_snapshot(ctx)
        damages[#damages+1]={sequence=ctx.sequence,now=ctx.now,avatar=ctx.avatar,peer=ctx.local_peer,
            attacker_peer=attacker_peer,attacker=attacker,native=raw,native_reason=native_reason}
        if #damages>8 then table.remove(damages,1) end
        return true
    end
    function api:on_died(event,context)
        if type(event)~='table' then return nil,'INVALID_DEATH_EVENT' end
        if nearby and event.local_player==false then
            local ctx,why=freeze(event,context,true)
            if not ctx or not ctx.avatar or ctx.victim.peer_id==ctx.local_peer then return nil,why or'NOT_REMOTE_DEATH'end
            local remote_key=tostring(ctx.sequence)..':'..tostring(ctx.victim.peer_id)..':'..tostring(ctx.avatar)
            if remote_ids[remote_key]then return nil,'REMOTE_DEATH_DUPLICATE'end
            remote_ids[remote_key]=true;remote_order[#remote_order+1]=remote_key
            if #remote_order>256 then remote_ids[table.remove(remote_order,1)]=nil end
            -- One remote event is a witness only. It never becomes an extra
            -- local death, and another inferred witness cannot form a chain.
            local raw,reason=source_snapshot(ctx)
            local q=reader and type(reader.damage_events)=='function'and reader_call('damage_events',ctx.world,ctx.avatar)
            local last=q and q.events and q.events[#q.events]
            local w={context=ctx,native=raw,native_reason=reason,
                queued=last and{event=last,players=ctx.players}or nil,
                record={category='unknown',confidence='unknown',evidence={native_fatal_event_proven=false,
                    weapon_source_proven=false,damage_kind_proven=false}}}
            classify(w)
            local r=w.record
            if ctx.position and(r.weapon_name or r.damage_kind or r.category=='enemy'and r.actor_name
                or(r.category=='environment'or r.category=='unknown')and r.actor_name and r.evidence.actor_type_hash)then
                witnesses[#witnesses+1]=w
                if #witnesses>16 then table.remove(witnesses,1)end
            end
            return nil,'REMOTE_DEATH_WITNESS'
        end
        local ctx,reason=freeze(event,context)
        if not ctx then self.diagnostics.rejected=self.diagnostics.rejected+1;return nil,reason end
        self:sample_damage(ctx.now,ctx)
        local base=sequence_peer(ctx)
        local ikey=ctx.death_index and base..':index:'..ctx.death_index
        local akey=ctx.avatar and base..':avatar:'..ctx.avatar
        local counter=event.observed=='native_death_counter'
        local ekey=not counter and base..':'..tostring(ctx.avatar or '-')..':'..tostring(event.frame or event.time or event.observed or '-done')
        local entry=ikey and indices[ikey] or ekey and event_keys[ekey]
        local same_avatar=akey and avatars[akey]
        if not entry and same_avatar then
            if not ctx.death_index or not same_avatar.index or ctx.death_index==same_avatar.index then entry=same_avatar end
        end
        if not entry and counter then
            -- An official event may already have left the pending queue before
            -- the cumulative native statistic arrives. Bind its counter index
            -- without emitting it again or consulting a respawned avatar.
            for _,candidate in ipairs(unindexed_events) do
                if not candidate.index and candidate.context.sequence==ctx.sequence
                    and candidate.context.local_peer==ctx.local_peer then
                    entry=candidate;break
                end
            end
        end
        if not entry and not counter then
            for _,candidate in ipairs(unpaired_counters)do
                if not candidate.has_event and candidate.context.sequence==ctx.sequence
                    and candidate.context.local_peer==ctx.local_peer
                    and (not candidate.excluded_avatar or candidate.excluded_avatar~=ctx.avatar)
                    and math.abs(candidate.context.now-ctx.now)<=2 then
                    entry=candidate;break
                end
            end
        end
        if entry then
            self.diagnostics.duplicates=self.diagnostics.duplicates+1
            if ikey then indices[ikey]=entry;entry.index=ctx.death_index end
            if ekey then event_keys[ekey]=entry end
            if not counter then
                entry.has_event=true
                if akey then avatars[akey]=entry end
            end
            if not entry.finished then
                if counter then entry.record.evidence.native_death_counter=true end
                if ctx.death_index then entry.record.evidence.death_index=ctx.death_index end
                entry.context.skip_attribution=entry.context.skip_attribution or ctx.skip_attribution
                if not counter then
                    entry.record.evidence.death_observed=text(event.observed) or 'runtime_player_died'
                    entry.record.evidence.runtime_death_event=true
                    -- Prefer the explicit death event snapshot to a preceding
                    -- statistics fallback; never enrich it after finalisation.
                    if not entry.counter_avatar_unproven then
                        entry.context.players,entry.context.victim=ctx.players,ctx.victim
                        entry.record.victim=plain(ctx.victim)
                        if ctx.occurred_at~=nil then entry.record.occurred_at=ctx.occurred_at end
                        if ctx.mission_elapsed~=nil then entry.record.mission_elapsed=ctx.mission_elapsed end
                        entry.native,entry.native_reason=source_snapshot(ctx)
                        entry.damage=recent_damage(ctx)
                        entry.queued=recent_queue(ctx)
                    end
                end
            end
            return entry.record.id,'duplicate'
        end
        if #pending>=16 or ordinal>=1024 then self.diagnostics.dropped=self.diagnostics.dropped+1;return nil,'DEATH_RECORD_CAPACITY' end
        ordinal=ordinal+1
        local raw,native_reason=source_snapshot(ctx)
        local counter_avatar_unproven=counter and not(raw and finite(raw.life) and raw.life>=2)
        local excluded_avatar=counter_avatar_unproven and raw and finite(raw.life) and raw.life<2 and ctx.avatar or nil
        if counter_avatar_unproven then
            -- A cumulative count identifies a death, not the body now occupying
            -- the local slot. Do not keep or later read a living replacement.
            ctx.avatar,ctx.victim.avatar_id=nil,nil
            raw,native_reason=nil,'COUNTER_VICTIM_AVATAR_NOT_DEAD'
            akey=nil
        end
        local record={id=base..':death:'..ordinal,sequence=ctx.sequence,occurred_at=ctx.occurred_at,
            mission_elapsed=ctx.mission_elapsed,category='unknown',confidence='unknown',victim=plain(ctx.victim),
            evidence={death_observed=text(event.observed) or 'runtime_player_died',runtime_death_event=not counter,
                native_death_counter=counter,death_index=ctx.death_index,native_fatal_event_proven=false,
                weapon_source_proven=false,damage_kind_proven=false}}
        entry={record=record,context=ctx,native=raw,native_reason=native_reason,
            damage=not counter_avatar_unproven and recent_damage(ctx) or nil,
            queued=not counter_avatar_unproven and recent_queue(ctx)or nil,
            deadline=ctx.now+(nearby and 1.1 or .5),index=ctx.death_index,has_event=not counter,
            counter_avatar_unproven=counter_avatar_unproven,excluded_avatar=excluded_avatar}
        pending[#pending+1]=entry
        if not counter then unindexed_events=remember(unindexed_events,entry,function(value)return not value.index end)
        else unpaired_counters=remember(unpaired_counters,entry,function(value)return not value.has_event end)end
        if ikey then indices[ikey]=entry end;if akey then avatars[akey]=entry end;if ekey then event_keys[ekey]=entry end
        self.diagnostics.pending=#pending
        return record.id,'queued'
    end
    function api:step(now,world,game,players,context)
        if not finite(now) then return nil,'DEATH_INVALID_CLOCK' end
        last_now=now
        context=context or {};local current={}
        for _,field in ipairs({'sequence','occurred_at','mission_elapsed','local_peer','avatar'}) do current[field]=context[field] end
        current.now,current.world,current.players=now,world,players or context.players or {}
        if type(game)=='table' and game.mission==true then
            roster(current,world,current.players,now,false);last_context=current
        end
        local kept,reads={},0
        for _,entry in ipairs(pending) do
            local leaving=not game or game.mission~=true or current.sequence and current.sequence~=entry.context.sequence
            if leaving or now>=entry.deadline then
                if not leaving and not entry.context.skip_attribution and entry.context.avatar and reads<1 then
                    reads=reads+1
                    local raw,reason=reader_call('read',world,entry.context.avatar)
                    if raw and raw.avatar_id==entry.context.avatar and raw.life and raw.life>=2 then
                        if entry.native and entry.native.victim_type and raw.victim_type~=entry.native.victim_type then
                            entry.native=nil;entry.native_conflict='DEATH_SOURCE_IDENTITY_CHANGED'
                        else
                            local before=entry.native
                            local before_peer=before and peer(before.last_creditor)
                            local after_peer=peer(raw.last_creditor)
                            if before and (before.last_owner and before.last_owner~=0 and raw.last_owner and raw.last_owner~=0
                                    and before.last_owner~=raw.last_owner
                                or before_peer and after_peer and before_peer~=after_peer
                                or before.last_owner_type and raw.last_owner_type and before.last_owner_type~=raw.last_owner_type) then
                                entry.native_conflict='DEATH_SOURCE_CHANGED_AFTER_DEATH'
                            elseif not before or raw.last_owner and raw.last_owner~=0 or after_peer then
                                entry.native=plain(raw);entry.native_reason=nil
                            end
                        end
                    elseif not entry.native then entry.native_reason=reason or 'DEATH_SOURCE_UNAVAILABLE' end
                end
                finish(entry)
            else kept[#kept+1]=entry end
        end
        pending=kept;self.diagnostics.pending=#pending
        return true
    end
    function api:take_records() local records=output;output={};return records end
    return api
end
