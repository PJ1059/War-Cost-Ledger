-- Ledger-owned, bounded read-only observer. No Runtime event subscription/native writes.
-- Missing-creditor/corpse attribution is a bounded inference backed by the
-- local native KILLS delta, never by a network owner or a currently held gun.
return function(world_api, natives, catalog, on_death, options)
    options = options or {}
    local H = natives.health
    local self = {diagnostics = {ready = false, scans = 0, incomplete = 0, skipped_descriptors = 0,
        poll_hz = 10, max_descriptors_per_poll = 64, budget_ms = 2,
        policy = 'current_creditor_or_corpse_with_bounded_local_native_kill_credit',
        direct_local = 0, other_peer = 0, inferred_local = 0, missing_creditor = 0,
        corpse_candidates = 0, expired_candidates = 0, max_cpu_ms = 0, cpu_ms = 0}}
    local known, blocks, last_world, cursor, elapsed = {}, nil, nil, 0, 0.1
    local clock, last_peer, last_epoch, native_count = 0, nil, nil, nil
    local credits, debits, pending = {}, {}, {}
    local corpse_seen, corpse_pending, observed, health_seen, health_baseline = nil, {}, {}, {}, false
    local WINDOW, GRACE, MAX_PENDING = 0.75, 0.15, 256
    local CAUSE_PINS={{0x925E38,'f6411401'},{0x925E42,'488b8360100000'},
        {0x925E49,'486bfe1c'},{0x925E58,'448974070c'},
        {0x925E99,'89040f'},{0x925EC9,'89440f04'}}
    local cause_world,cause_ready
    local trace=options.damage_attribution
    local resolver=options.damage_resolver
    if resolver and resolver.diagnostics then self.diagnostics.ground_fire=resolver.diagnostics.ground_fire end
    local source_types=options.source_types or {}
    local function enemy_source(kind)
        local role=kind and catalog[kind]
        return role and role.kill==true and not role.asset
    end
    local contact_pending={}
    local token_world,token_ready
    local TOKEN_PINS={{0x923C24,'45896740'},{0x920D5F,'8b4640'}}
    local bytes = H and require('hd2runtime/core/bytes')
    local function clear_credit()
        native_count, credits, debits, pending = nil, {}, {}, {}
    end
    local function prune(rows)
        while rows[1] and clock - rows[1].time > WINDOW do table.remove(rows, 1) end
    end
    local function consume(rows, amount)
        while amount > 0 and rows[1] do
            local used = math.min(amount, rows[1].count)
            rows[1].count, amount = rows[1].count - used, amount - used
            if rows[1].count == 0 then table.remove(rows, 1) end
        end
        return amount
    end
    local function append(rows, count)
        if count <= 0 then return end
        local last = rows[#rows]
        if last and last.time == clock then last.count = last.count + count
        elseif #rows < 32 then rows[#rows + 1] = {count = count, time = clock} end
    end
    local function sample_credit()
        prune(credits); prune(debits)
        if type(options.local_kills) ~= 'function' then return end
        local ok, count = pcall(options.local_kills)
        if not ok or type(count) ~= 'number' or count < 0 or count > 9007199254740991 or count % 1 ~= 0 then
            clear_credit(); return
        end
        if native_count and count >= native_count then
            local delta = count - native_count
            -- A corrupt/restored bulk total is not a recent attribution quota.
            if delta <= 4096 then append(credits, consume(debits, delta)) else clear_credit() end
        elseif native_count then clear_credit() end
        native_count = count
    end
    local function direct(event)
        event.native_creditor_verified = true
        if event.local_killer then
            self.diagnostics.direct_local = self.diagnostics.direct_local + 1
            -- Assets can share health/creditor fields but do not consume enemy KILLS.
            if event.enemy and not event.reserved_native_credit then append(debits, consume(credits, 1)) end
        else self.diagnostics.other_peer = self.diagnostics.other_peer + 1 end
        event.enemy,event.reserved_native_credit=nil,nil
        on_death(event)
    end
    local function candidate(event)
        if type(options.local_kills) ~= 'function' or not event.enemy then return end
        event.enemy = nil
        if #pending < MAX_PENDING then pending[#pending + 1] = {event = event, time = clock} end
    end
    local function flush()
        local retained = {}
        for _, row in ipairs(pending) do
            if clock - row.time > WINDOW then
                self.diagnostics.expired_candidates = self.diagnostics.expired_candidates + 1
            elseif clock - row.time + 1e-9 >= GRACE and credits[1] then
                consume(credits, 1)
                local event = row.event
                event.local_killer, event.inferred, event.native_creditor_verified = true, true, false
                self.diagnostics.inferred_local = self.diagnostics.inferred_local + 1
                on_death(event)
            else retained[#retained + 1] = row end
        end
        pending = retained
    end
    function self:reset()
        known, blocks, last_world, cursor, elapsed = {}, nil, nil, 0, 0.1
        clock, last_peer, last_epoch = 0, nil, nil
        clear_credit()
        corpse_seen, corpse_pending, observed, health_seen, health_baseline = nil, {}, {}, {}, false
        cause_world,cause_ready=nil,nil
        token_world,token_ready=nil,nil
        contact_pending={}
        if resolver then resolver:reset()end
        self.diagnostics.ready = false
    end
    function self:gap()
        known, cursor = {}, 0; clear_credit(); corpse_seen, corpse_pending, observed, health_seen, health_baseline = nil, {}, {}, {}, false
        contact_pending={}
        if resolver then resolver:reset()end
        self.diagnostics.ready = false
    end
    function self:contact(event)
        if not trace or type(event)~='table'or event.verified~=true or event.local_player~=true
            or event.direct~=true or event.attack~='projectile'
            or(event.result~='penetration'and event.result~='full_penetration')
            or type(event.target)~='number'or event.target<=0 or event.target>=4294967296 then return false end
        if #contact_pending>=64 then
            -- Keep unrelated target chains: a full contact ring is not an
            -- identity/read gap for every enemy in the level.
            table.remove(contact_pending,1)
            self.diagnostics.contact_overflows=(self.diagnostics.contact_overflows or 0)+1
        end
        contact_pending[#contact_pending+1]={target=event.target,source=event.source,owner=event.owner,
            damage_info_id=event.damage_info_id,projectile_id=event.projectile_id,position=event.position}
        return true
    end
    function self:explosion(event)
        return resolver and resolver:explosion(event,clock)or false
    end
    function self:status_event(event,forwarded,reason)
        local diag=self.diagnostics.ground_fire
        if not diag or type(event)~='table'or event.name~='throwable/g8_immolation/detonation'then return end
        diag.events_seen=diag.events_seen+1
        if event.local_player==true then diag.events_local=diag.events_local+1
        elseif event.local_player==false then diag.events_foreign=diag.events_foreign+1
        else diag.events_uncredited=diag.events_uncredited+1 end
        if forwarded==true then diag.events_forwarded=diag.events_forwarded+1
        elseif reason=='mission_inactive'then diag.event_mission_inactive=diag.event_mission_inactive+1
        elseif reason=='missing_source'then diag.event_missing_source=diag.event_missing_source+1
        elseif reason=='missing_radius'then diag.event_missing_radius=diag.event_missing_radius+1
        elseif reason=='not_local'then diag.event_not_local=diag.event_not_local+1
        else diag.event_rejected=diag.event_rejected+1 end
    end
    function self:poll(world, players, dt, life_epoch)
        clock = clock + dt
        elapsed = elapsed + dt
        if elapsed + 1e-9 < 0.1 then return end
        elapsed = 0 -- no catch-up after a slow frame
        if not H or not world_api.health_header then return end
        local started = os.clock()
        local diag = self.diagnostics
        local function finish(reason)
            diag.reason = reason
            local spent = (os.clock() - started) * 1000
            diag.cpu_ms, diag.max_cpu_ms = diag.cpu_ms + spent, math.max(diag.max_cpu_ms, spent)
        end
        if last_world ~= world.game then
            known, cursor, last_world = {}, 0, world.game
            clear_credit()
            corpse_seen, corpse_pending, observed, health_seen, health_baseline = nil, {}, {}, {}, false
            contact_pending={}
            if resolver then resolver:reset()end
            blocks = {world.view.slot(), world.view.slot(), world.view.slot(), world.view.slot(), world.view.slot(), world.view.slot()}
        end
        local player
        for _, p in ipairs(players) do if p['local'] then player = p; break end end
        if not player or not player.peer then self:gap(); finish('local_peer_unavailable'); return end
        if last_peer ~= player.peer then self:gap(); last_peer = player.peer end
        if last_epoch ~= life_epoch then
            diag.life_changes=(diag.life_changes or 0)+1
            clear_credit();contact_pending={}
            if resolver then resolver:life_changed(clock)end
            last_epoch = life_epoch
        end
        local header = world_api.health_header(world, blocks[1])
        if not header or not header.buckets or not header.records or not header.descriptors then
            self:gap(); finish('health_unreadable'); return
        end
        -- Hard read/loop ceilings; huge or corrupt tables must not cause a frame spike.
        if header.live > 4096 or header.hash_capacity > 16384 then
            self:gap(); finish('health_capacity_budget'); return
        end
        local view = world.view
        local buckets = view.fill(blocks[2], header.buckets, header.hash_capacity * 8)
        -- native_view caps a single read at 1 MiB; 4096 health records exceed that.
        -- Split on a record boundary instead of making a rejected oversized read.
        local split = math.floor(1048576 / H.stride) * H.stride
        local record_bytes = header.live * H.stride
        local records = header.live > 0 and view.fill(blocks[3], header.records, math.min(record_bytes, split))
        local extra = record_bytes > split and view.fill(blocks[5], header.records + split, record_bytes - split)
        local pointers = header.live > 0 and view.fill(blocks[4], header.descriptors, header.live * 8)
        if not buckets or (header.live > 0 and (not records or not pointers)) or (record_bytes > split and not extra) then
            self:gap(); finish('bulk_read_failed'); return
        end
        local function record_u32(offset)
            if offset >= split then return extra:u32(offset - split) end
            return records:u32(offset)
        end
        sample_credit()
        local function creditor(base)
            local lo, hi = record_u32(base + H.record.lastCreditor), record_u32(base + H.record.lastCreditor + 4)
            if lo == 0 and hi == 0 then
                lo, hi = record_u32(base + H.record.downCreditor), record_u32(base + H.record.downCreditor + 4)
            end
            if lo and hi and (lo ~= 0 or hi ~= 0) then return string.format('%08X%08X', hi, lo) end
        end
        local function event_of(entry, entity, observed)
            return {entity_id = entity, type = entry.type, info = entry.info,
                same_life = entry.life_epoch == life_epoch, life_epoch = entry.life_epoch,
                observed = observed, enemy = entry.enemy,damage_source=trace and trace:death(nil)or nil}
        end
        local cause_reads=0
        local source_reads,source_bytes=0,0
        local source_budget_hit=false
        local owner_cache={}
        local function source_read(at,size)
            if type(at)~='number'or at<65536 or at+size>=140737488355328 or size>512 then return nil end
            if source_reads>=512 or source_bytes+size>32768 or os.clock()-started>=.002 then
                source_budget_hit=true;return nil
            end
            source_reads,source_bytes=source_reads+1,source_bytes+size
            return view.read(at,size)
        end
        local function source_pointer(at)
            local raw=source_read(at,8);if not raw or #raw~=8 then return nil end
            local value=bytes.u32(raw,0)+bytes.u32(raw,4)*4294967296
            return value>=65536 and value<140737488355328 and value%8==0 and value or nil
        end
        local function owner_type(owner)
            if owner_cache[owner]then return owner_cache[owner]end
            local WI,E=natives.wielder,natives.engine
            if not WI or not E or type(world.exe)~='number'or type(owner)~='number'or owner<=0 or owner>=4294967296 then return nil end
            local generation_manager=source_pointer(world.exe+E.entities)
            local size=generation_manager and source_read(generation_manager+E.generationSize,4)
            local generations=generation_manager and source_pointer(generation_manager+E.generations)
            local index=owner%4194304
            if not size or not generations or index>=bytes.u32(size,0) then return nil end
            local generation=source_read(generations+index,1)
            if not generation or generation:byte()~=math.floor(owner/4194304)%256 then return nil end
            local manager=source_pointer(world.game+WI.entities)
            local raw=manager and source_read(manager+WI.entityMap,20)
            if not raw then return nil end
            local buckets=bytes.u32(raw,0)+bytes.u32(raw,4)*4294967296
            local cap,empty,factor=bytes.u32(raw,8),bytes.u32(raw,12),bytes.u32(raw,16)
            local n=cap
            while n>1 and n%2==0 do n=n/2 end
            if buckets<65536 or cap==0 or cap>1048576 or n~=1 then return nil end
            local start=world_api.mul32(owner,factor)
            for probe=0,math.min(cap,32)-1 do
                local at=buckets+((start+probe)%cap)*8
                local slot=source_read(at,8);if not slot then return nil end
                local id,record=bytes.u32(slot,0),bytes.u32(slot,4)
                if id==empty then return nil end
                if id==owner then
                    if record>=1048576 then return nil end
                    local descriptor=manager+WI.descriptors+record*WI.descriptorStride
                    local value=source_read(descriptor,WI.descriptorStride)
                    if not value or bytes.u32(value,WI.descriptorEntity)~=owner
                        or source_read(descriptor,WI.descriptorStride)~=value
                        or source_read(at,8)~=slot or source_read(manager+WI.entityMap,20)~=raw
                        or source_pointer(world.game+WI.entities)~=manager
                        or source_pointer(world.exe+E.entities)~=generation_manager
                        or source_read(generations+index,1)~=generation then return nil end
                    local kind=string.format('%08X%08X',bytes.u32(value,4),bytes.u32(value,0))
                    -- One poll only, keyed by the complete generation-bearing entity ID.
                    owner_cache[owner]=kind
                    return kind
                end
            end
        end
        local function cause_of(event,entry,index,life)
            if life~=2 or not header.ext or H.extStride~=28 or H.extArray~=0x1060 then return event end
            if cause_reads>=(trace and 64 or 8)or os.clock()-started>=.002 then
                diag.cause_budget_skips=(diag.cause_budget_skips or 0)+1;return event
            end
            cause_reads=cause_reads+1
            local read=trace and source_read or view.read
            local pointer=trace and source_pointer or view.pointer
            -- Optional same-target enrichment; never funds a kill. The same
            -- descriptor/record is checked again after looking up the owner.
            local key=tostring(world.game)..':'..tostring(view)..':'..tostring(view.read)
            if cause_world~=key then
                cause_world,cause_ready=key,true
                for _,pin in ipairs(CAUSE_PINS)do
                    if read(world.game+pin[1],#pin[2]/2)~=bytes.unhex(pin[2])then cause_ready=false;break end
                end
            end
            if not cause_ready then
                if source_budget_hit then cause_world=nil end
                diag.cause_reason='DEATH_CAUSE_CODE_PIN';return event
            end
            local D=H.descriptor
            local who=read(entry.pointer,D.size)
            if not who or bytes.u32(who,D.entity)~=event.entity_id or bytes.u32(who,D.flags)%2~=1
                or string.format('%08X%08X',bytes.u32(who,D.type+4),bytes.u32(who,D.type))~=entry.type then return event end
            local at=header.ext+index*H.extStride
            local value=read(at,H.extStride)
            if not value or bytes.u32(value,12)~=life or read(at,H.extStride)~=value
                or read(entry.pointer,D.size)~=who
                or pointer(header.descriptors+index*8)~=entry.pointer then
                diag.cause_rejected=(diag.cause_rejected or 0)+1;return event
            end
            event.damage_cause={kind=bytes.u32(value,0),element=bytes.u32(value,4),life=life,
                owned=true,current=true,source='native_health_extension'}
            diag.cause_sampled=(diag.cause_sampled or 0)+1;diag.cause_reason=nil
            return event
        end
        local trace_samples=0
        local contacts={}
        for _,contact in ipairs(contact_pending)do
            contact.observed_at=contact.observed_at or clock
            if clock-contact.observed_at<=WINDOW then
                local list=contacts[contact.target]or {};contacts[contact.target]=list;list[#list+1]=contact
            end
        end
        contact_pending={}
        local function enrich(event,entry,index,life)
            local previous_trace,saved_contacts=entry.damage_trace,contacts[event.entity_id]
            source_budget_hit=false
            cause_of(event,entry,index,life)
            if not trace then return event end
            local target_position,position_attempted
            local function position_once()
                if not position_attempted then
                    position_attempted=true
                    if type(options.unit_position)=='function'and os.clock()-started<.002 then
                        local ok,pos=pcall(options.unit_position,world,entry.unit)
                        if ok then target_position=pos end
                    end
                end
                return target_position
            end
            local base,D=index*H.stride,H.descriptor
            local health=record_u32(base+H.record.health)
            local damage_observed=(type(health)=='number'and type(entry.health)=='number'and health<entry.health)
                or(type(entry.life)=='number'and entry.life<2 and type(life)=='number'and life>=2)
            local first_seen_dead=type(entry.life)=='number'and entry.life>=2 and type(life)=='number'and life>=2
            local owner=record_u32(base+H.record.lastOwner)
            local raw_type,stable,pure_contact
            local function contact_rows(read_sources,typed_only)
                local consumed=0
                for _,contact in ipairs(contacts[event.entity_id]or {})do
                    if not typed_only or contact.damage_info_id~=nil then
                        local source=read_sources and owner_type(contact.source)or nil
                        local row={entity=event.entity_id,pointer=entry.pointer,
                            unit=entry.unit,epoch=life_epoch,health=health,life=entry.life<2 and entry.life or 0,
                            now=clock,damage_observed=damage_observed,first_seen_dead=first_seen_dead,
                            source_type=source and (source_types[source]or enemy_source(source))and source or nil,raw_type=source,
                            owner=contact.source,damage_token=token_ready and record_u32(base+0x40)or nil,
                            damage_info_id=contact.damage_info_id,projectile_id=contact.projectile_id,
                            position=contact.position,context_owner=contact.owner,
                            signature_available=token_ready==true or contact.damage_info_id~=nil,
                            readable=true,local_source=true}
                        if read_sources and resolver and row.damage_info_id~=nil and not row.source_type and not row.position
                            and resolver:has_context(clock)then row.position=position_once()end
                        local mapped=resolver and resolver:resolve(row,entry.damage_trace,clock)
                        if mapped then row.source_type,row.source_inferred,row.source_policy=mapped.type,mapped.inferred,mapped.basis end
                        if mapped and mapped.local_source then row.local_source=true end
                        row.source_kind=row.source_type and type(source_types[row.source_type])=='table'
                            and source_types[row.source_type].kind or nil
                        entry.damage_trace=trace:observe(entry.damage_trace,row)
                        consumed=consumed+1
                        diag.contact_sources=(diag.contact_sources or 0)+1
                    end
                end
                contacts[event.entity_id]=nil
                return consumed
            end
            if trace_samples<64 and source_reads<512 and source_bytes<32768 and os.clock()-started<.002 then
                trace_samples=trace_samples+1
                local key=tostring(world.game)..':'..tostring(view)..':'..tostring(view.read)
                if token_world~=key then
                    token_world,token_ready=key,true
                    for _,pin in ipairs(TOKEN_PINS)do
                        local raw=source_read(world.game+pin[1],#pin[2]/2)
                        if not raw then token_world,token_ready=nil,false;break end
                        if raw~=bytes.unhex(pin[2])then token_ready=false;break end
                    end
                end
                local who=source_read(entry.pointer,D.size)
                if who and bytes.u32(who,D.entity)==event.entity_id
                    and string.format('%08X%08X',bytes.u32(who,D.type+4),bytes.u32(who,D.type))==entry.type then
                    contact_rows(true,false)
                    raw_type=owner_type(owner)
                    local after=source_read(header.records+base,H.stride)
                    stable=after and bytes.u32(after,H.record.life)==life
                        and bytes.u32(after,H.record.health)==record_u32(base+H.record.health)
                        and bytes.u32(after,H.record.lastOwner)==owner
                        and bytes.u32(after,0x40)==record_u32(base+0x40)
                        and source_read(entry.pointer,D.size)==who
                        and source_pointer(header.descriptors+index*8)==entry.pointer
                else contacts[event.entity_id]=nil end
            elseif resolver and pointers:ptr(index*8)==entry.pointer then
                -- The native contact already proved this generation's target
                -- and local creditor. Its typed payload needs no owner lookup.
                -- At the shared native-read budget use only this poll's
                -- bulk Health/descriptor identity for remaining typed contacts.
                pure_contact=contact_rows(false,true)>0
                stable=pure_contact
                source_budget_hit=not pure_contact or not(entry.damage_trace and entry.damage_trace.type)
            else contacts[event.entity_id]=nil;source_budget_hit=true
            end
            -- Exhaustion is scheduling, not a failed identity read. Retry the
            -- original target before committing a permanently unknown source.
            if source_budget_hit then
                entry.damage_trace=previous_trace
                contacts[event.entity_id]=saved_contacts
                diag.source_deferred=(diag.source_deferred or 0)+1
                return event,true
            end
            -- A changed creditor is copied in the same Health record. It is
            -- provenance for the existing local-kill gate, never a new kill.
            local cause=event.damage_cause
            if stable and cause and not pure_contact then
                local final=source_read(header.ext+index*H.extStride,H.extStride)
                if not final or bytes.u32(final,0)~=cause.kind or bytes.u32(final,4)~=cause.element
                    or bytes.u32(final,12)~=cause.life then stable=false;event.damage_cause=nil;cause=nil end
            end
            local row={entity=event.entity_id,pointer=entry.pointer,
                unit=entry.unit,epoch=life_epoch,health=health,life=life,now=clock,damage_observed=damage_observed,
                first_seen_dead=first_seen_dead,
                source_type=stable and raw_type and (source_types[raw_type]or enemy_source(raw_type))and raw_type or nil,
                raw_type=raw_type,owner=owner,kind=cause and cause.kind,element=cause and cause.element,
                damage_token=token_ready and record_u32(base+0x40)or nil,
                signature_available=token_ready==true,
                readable=stable==true,local_source=creditor(base)==player.peer,creditor_missing=creditor(base)==nil}
            if stable and cause and cause.kind==4 and owner==event.entity_id and entry.enemy then
                row.source_type,row.mechanism,row.source_policy=raw_type or entry.type,'self_explosion','native_target_self_explosion_owner'
                -- An instant collision may follow the first live baseline:
                -- its cached lastOwner already named the falling body, so
                -- no intermediate HP/owner change called enrich(). Resolve
                -- only that same target's recent cached owner, never a pod
                -- elsewhere in the world or a source from a global batch.
                local prior=previous_trace
                if prior and prior.baseline==true and prior.complete==true and prior.life and prior.life<2
                    and prior.entity==event.entity_id and prior.pointer==entry.pointer
                    and prior.unit==entry.unit and prior.epoch==life_epoch
                    and type(prior.observed_at)=='number'and clock>=prior.observed_at
                    and clock-prior.observed_at<=WINDOW+1e-9
                    and entry.damage_owner and entry.damage_owner~=0 and entry.damage_owner~=event.entity_id
                    and(row.local_source or row.creditor_missing)then
                    local pod=owner_type(entry.damage_owner)
                    if pod and type(source_types[pod])=='table'and source_types[pod].kind=='hellpod'then
                        entry.damage_trace=trace:observe(prior,{entity=event.entity_id,pointer=entry.pointer,
                            unit=entry.unit,epoch=life_epoch,health=entry.health,life=entry.life,
                            now=prior.observed_at,damage_observed=false,readable=true,
                            source_type=pod,source_kind='hellpod',owner=entry.damage_owner,
                            local_source=row.local_source,creditor_missing=row.creditor_missing})
                    end
                end
            elseif stable and enemy_source(raw_type)and owner~=event.entity_id then
                row.mechanism,row.source_policy='enemy_damage','native_enemy_damage_owner'
            end
            if resolver and stable then
                -- No target scan: only an already changing Health entry can
                -- use the optional, bounded native position reader.
                row.explosion_damage=cause and cause.kind==4 or false
                local fire_death=first_seen_dead and life==2 and cause and cause.kind==2 and cause.element==1
                if not pure_contact and (row.explosion_damage or(damage_observed or fire_death)and resolver:has_status_context(clock,life==2))
                    and not row.source_type and resolver:has_context(clock)
                    and type(options.unit_position)=='function'and os.clock()-started<.002 then
                    row.position=position_once()
                end
                local mapped=resolver:resolve(row,entry.damage_trace,clock)
                if mapped then row.source_type,row.source_inferred,row.source_policy=mapped.type,mapped.inferred,mapped.basis end
                if mapped and mapped.local_source then row.local_source=true end
            end
            if source_budget_hit then
                entry.damage_trace=previous_trace
                contacts[event.entity_id]=saved_contacts
                diag.source_deferred=(diag.source_deferred or 0)+1
                return event,true
            end
            row.source_kind=row.source_type and type(source_types[row.source_type])=='table'
                and source_types[row.source_type].kind or nil
            entry.damage_trace=trace:observe(entry.damage_trace,row)
            event.damage_source=trace:death(entry.damage_trace)
            return event
        end
        local function defer_source(entry,event,peer,first_seen)
            if not entry.source_retry then
                entry.source_retry={event=event,peer=peer,first_seen=first_seen,time=clock}
            elseif peer then
                entry.source_retry.event,entry.source_retry.peer=event,peer
            end
            -- Reserve an already-proved local native death exactly once;
            -- otherwise delayed source reads could fund another candidate.
            if not first_seen and peer==player.peer and entry.enemy and not entry.source_retry.reserved then
                append(debits,consume(credits,1))
                entry.source_retry.reserved=true
            end
            if clock-entry.source_retry.time<.5-1e-9 then return true end
            diag.source_retry_expired=(diag.source_retry_expired or 0)+1
            return false
        end
        local function finish_retry(entry,event)
            local retry=entry.source_retry
            if retry then
                event.reserved_native_credit=retry.reserved
                entry.source_retry=nil
            end
            return event
        end
        for entity, time in pairs(observed) do if clock - time > 2 then observed[entity] = nil end end
        diag.scans, diag.ready = diag.scans + 1, true
        local stamp, inspected, descriptors = diag.scans, 0, 0
        local cap, R, D = header.hash_capacity, H.record, H.descriptor
        local start = cursor % cap
        for offset = 0, cap - 1 do
            local slot = (start + offset) % cap
            if offset % 64 == 0 and os.clock() - started >= 0.002 then
                cursor = slot; diag.incomplete = diag.incomplete + 1; break
            end
            inspected = inspected + 1
            local entity, index = buckets:u32(slot * 8), buckets:u32(slot * 8 + 4)
            if entity and entity ~= header.hash_empty and index and index < header.live then
                -- Track first presence even if this poll exhausts its 64 new
                -- descriptor reads. Warm-up rows are never fresh deaths later.
                local seen = health_seen[entity]
                if not seen then seen = {fresh = health_baseline}; health_seen[entity] = seen end
                seen.stamp = stamp
                local pointer = pointers:ptr(index * 8)
                local entry = known[entity]
                local replaced = entry and entry.pointer ~= pointer
                if replaced then known[entity], entry = nil, nil end
                if not entry and pointer then
                    if descriptors < 64 then
                        descriptors = descriptors + 1
                        local raw = view.read(pointer, D.size)
                        if raw and bytes.u32(raw, D.entity) == entity then
                            local kind = string.format('%08X%08X', bytes.u32(raw, D.type + 4), bytes.u32(raw, D.type))
                            local life = record_u32(index * H.stride + R.life)
                            local info = world_api.type_info(kind)
                            local role = catalog[kind]
                            entry = {pointer = pointer, type = kind, life = life, life_epoch = life_epoch,
                                unit = bytes.u32(raw, D.unit), health = record_u32(index * H.stride + R.health),
                                enemy = (role and role.kill == true and not role.asset) or
                                    (not role and info and info.kill == true and (not info.kind or info.kind == 'enemy')),
                                relevant = catalog[kind] ~= nil or (info and info.kill == true), info = info}
                            known[entity] = entry
                            entry.damage_owner,entry.damage_token=record_u32(index*H.stride+R.lastOwner),record_u32(index*H.stride+0x40)
                            if trace then entry.damage_trace=trace:baseline({entity=entity,pointer=pointer,
                                unit=entry.unit,epoch=life_epoch,health=entry.health,life=life,
                                now=clock,damage_observed=false}) end
                            if life and life >= 2 then
                                -- First scan is a baseline. Subsequently a new, already-dead
                                -- enemy can be an instant kill that occurred between two polls.
                                local peer = creditor(index * H.stride)
                                if seen.fresh and not replaced and not observed[entity] and
                                    (not peer or peer == player.peer) then
                                    local event,deferred=enrich(event_of(entry,entity,'dead_state'),entry,index,life)
                                    if deferred and defer_source(entry,event,peer,true)then
                                        entry.first_death_retry=true
                                    else candidate(finish_retry(entry,event));observed[entity]=clock end
                                else observed[entity]=clock end
                            end
                        end
                    else diag.skipped_descriptors = diag.skipped_descriptors + 1 end
                end
                if entry then
                    entry.stamp = stamp
                    entry.missing_since=nil
                    if entry.relevant then
                        local base = index * H.stride
                        local life = record_u32(base + R.life)
                        local health = record_u32(base + R.health)
                        local damage_owner,damage_token=record_u32(base+R.lastOwner),record_u32(base+0x40)
                        local changed_source=trace and entry.life and entry.life<2
                            and (damage_owner~=entry.damage_owner or damage_token~=entry.damage_token or contacts[entity]~=nil)
                        local damage_event,deferred
                        if entry.first_death_retry then
                            damage_event,deferred=enrich(event_of(entry,entity,'dead_state'),entry,index,life)
                            if deferred and defer_source(entry,damage_event,creditor(base),true)then
                                -- Keep the first-dead candidate alive only within the retry window.
                            else
                                candidate(finish_retry(entry,damage_event));observed[entity]=clock
                                entry.first_death_retry=nil
                            end
                        elseif health ~= entry.health or life ~= entry.life or changed_source then
                            entry.credit_peer = creditor(base)
                            if trace and ((health and entry.health and health<entry.health)or life~=entry.life or changed_source)then
                                damage_event,deferred=enrich(event_of(entry,entity,'damage_change'),entry,index,life)
                                if deferred then
                                    deferred=defer_source(entry,damage_event,life and life>=2 and creditor(base)or nil,false)
                                end
                                if not deferred and not damage_event.damage_source then
                                    entry.damage_trace=trace:observe(entry.damage_trace,{entity=entity,pointer=entry.pointer,
                                        unit=entry.unit,epoch=life_epoch,health=health,life=life,readable=false,
                                        now=clock,damage_observed=(type(health)=='number'and type(entry.health)=='number'and health<entry.health)
                                            or(type(entry.life)=='number'and entry.life<2 and type(life)=='number'and life>=2)})
                                    damage_event.damage_source=trace:death(entry.damage_trace)
                                end
                            end
                        end
                        if not deferred and entry.life and entry.life < 2 and life and life >= 2 then
                            observed[entity] = clock
                            local event, peer = damage_event or enrich(event_of(entry, entity, 'dead_state'),entry,index,life), creditor(base)
                            event.observed='dead_state'
                            finish_retry(entry,event)
                            if peer then
                                event.killer_peer, event.local_killer = peer, peer == player.peer
                                direct(event)
                            else
                                diag.missing_creditor = diag.missing_creditor + 1
                                candidate(event)
                            end
                        end
                        if not deferred then
                            entry.life,entry.health=life,health
                            entry.damage_owner,entry.damage_token=damage_owner,damage_token
                            if life and life<2 then entry.life_epoch=life_epoch;entry.source_retry=nil end
                        end
                    end
                end
            end
        end
        local corpses, corpse_reads = nil, 0
        if type(options.local_kills) == 'function' and world_api.corpses and world_api.corpse_entity then
            corpses = world_api.corpses(world, blocks[6]) or false
            if not corpses then corpse_seen,corpse_pending=nil,{} end
        end
        if inspected == cap then
            for entity, entry in pairs(known) do
                if entry.stamp ~= stamp then
                    entry.missing_since=entry.missing_since or clock
                    local within_window=clock-entry.missing_since<=WINDOW
                    known[entity] = nil
                    local retry=entry.source_retry
                    if retry and retry.peer and not retry.first_seen then
                        local event=finish_retry(entry,retry.event)
                        event.killer_peer,event.local_killer=retry.peer,retry.peer==player.peer
                        event.observed='dead_state'
                        observed[entity]=clock
                        direct(event)
                    elseif entry.relevant and entry.life and entry.life < 2 and entry.unit and entry.unit ~= 0 and
                        world_api.corpses and world_api.corpse_entity and within_window then
                        if corpses == nil then corpses = world_api.corpses(world, blocks[6]) or false end
                        local index = corpses and corpses.origins and corpses.origins[entity]
                        if index~=nil and corpse_reads<64 and os.clock()-started<.002 then
                            corpse_reads = corpse_reads + 1
                            local corpse = world_api.corpse_entity(world, corpses, index, entry.unit)
                            if corpse then
                                observed[entity] = clock
                                diag.corpse_candidates = diag.corpse_candidates + 1
                                local event = event_of(entry, entity, 'corpse')
                                event.corpse_entity_id = corpse
                                local damage=entry.damage_trace
                                if trace and damage and damage.entity==entity and damage.pointer==entry.pointer
                                    and damage.unit==entry.unit and damage.epoch==life_epoch and damage.complete==true
                                    and damage.chain_local==true and damage.chain_source and damage.chain_expired~=true
                                    and type(damage.last_damage_at)=='number'and clock>=damage.last_damage_at
                                    and clock-damage.last_damage_at<=5+1e-9 then
                                    event.damage_source=trace:death(damage)
                                    event.damage_source.inferred=true
                                    event.damage_source.policy='same_target_recent_damage_before_corpse'
                                end
                                -- A known teammate's cached hit is never reassigned to us.
                                if not entry.credit_peer or entry.credit_peer == player.peer then candidate(event) end
                            end
                        else
                            -- A full burst can exceed this poll's corpse budget.
                            -- Keep its original identity/time until the exact unit is read.
                            known[entity]=entry
                            diag.corpse_deferred=(diag.corpse_deferred or 0)+1
                        end
                    end
                end
            end
            for entity, seen in pairs(health_seen) do if seen.stamp ~= stamp then health_seen[entity] = nil end end
            health_baseline = true
            cursor = (start + 64) % cap
        end
        -- No live health record is required when the corpse itself still
        -- contains an exact enemy type. A generic corpse type cannot restore
        -- the dead enemy identity, so it is deliberately not guessed.
        if corpses and corpses.origins then
            local next_seen,next_pending={},{}
            for entity,index in pairs(corpses.origins)do
                if not corpse_seen or corpse_seen[entity]or observed[entity]then
                    next_seen[entity]=true
                else
                    local appeared=corpse_pending[entity]or clock
                    if clock-appeared>WINDOW then
                        next_seen[entity]=true
                        diag.corpse_backlog_expired=(diag.corpse_backlog_expired or 0)+1
                    elseif corpse_reads<64 and os.clock()-started<.002 and corpses.descriptors then
                        corpse_reads = corpse_reads + 1
                        local pointer = view.pointer(corpses.descriptors + index * 8)
                        local raw = pointer and view.read(pointer, D.size)
                        if raw then
                            local corpse_id, unit = bytes.u32(raw, D.entity), bytes.u32(raw, D.unit)
                            local kind = string.format('%08X%08X', bytes.u32(raw, D.type + 4), bytes.u32(raw, D.type))
                            local info, role = world_api.type_info(kind), catalog[kind]
                            local enemy = (role and role.kill == true and not role.asset) or
                                (not role and info and info.kill == true and (not info.kind or info.kind == 'enemy'))
                            if corpse_id and corpse_id ~= 0 and unit and unit ~= 0 and enemy then
                                local event = {entity_id = entity, type = kind, info = info, enemy = true,
                                    same_life = true, life_epoch = life_epoch, observed = 'corpse', corpse_entity_id = corpse_id}
                                if trace then event.damage_source=trace:death(nil)end
                                candidate(event); observed[entity] = clock
                                diag.corpse_candidates = diag.corpse_candidates + 1
                            end
                        end

                        next_seen[entity]=true
                    else
                        next_pending[entity]=appeared
                        diag.corpse_deferred=(diag.corpse_deferred or 0)+1
                    end
                end
            end
            corpse_seen,corpse_pending=next_seen,next_pending
        end
        -- An outer scan can stop before reaching a contacted target. Carry
        -- only those unconsumed contacts, within the existing time/cap bounds;
        -- attempted target-read failures and observed deaths already remove them.
        for entity,list in pairs(contacts)do
            if not observed[entity]then
                for _,contact in ipairs(list)do
                    if #contact_pending<64 and clock-contact.observed_at<=WINDOW then
                        contact_pending[#contact_pending+1]=contact
                    end
                end
            end
        end
        flush()
        diag.source_reads_peak=math.max(diag.source_reads_peak or 0,source_reads)
        diag.source_bytes_peak=math.max(diag.source_bytes_peak or 0,source_bytes)
        diag.source_reads,diag.source_bytes=source_reads,source_bytes
        finish(nil)
    end
    return self
end
