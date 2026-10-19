-- Typed native DamageInfo IDs are separate from resource hashes and the opaque
-- Health damage-run token. A shared payload needs a real parent-weapon context.
return function(reverse,resource_nodes)
    reverse=reverse or {}
    resource_nodes=resource_nodes or {}
    local resource_payloads={}
    -- Fixed-size, aggregate diagnostics: no target log or growing hash table.
    -- Counts describe resolution attempts, not additional kills. They share
    -- the observer's existing diagnostic snapshot and survive no extra saves.
    local fire_diag={events_seen=0,events_local=0,events_foreign=0,events_uncredited=0,
        events_forwarded=0,event_mission_inactive=0,event_missing_source=0,event_missing_radius=0,
        event_not_local=0,event_rejected=0,fire_contexts=0,g8_contexts=0,contexts_expired=0,
        contexts_evicted=0,life_fire_retained=0,death_observations=0,death_cause_missing=0,fatal_nonfire=0,
        fatal_fire_attempts=0,first_dead_fire_attempts=0,known_source_kept=0,typed_source_kept=0,
        unreadable_fire=0,no_position=0,no_fire_context=0,credit_rejected=0,
        typed_rejected=0,outside_area=0,fire_matched=0,g8_matched=0}
    local api={diagnostics={mapped=0,shared_without_context=0,explosions=0,resource_mapped=0,
        ground_fire=fire_diag}}
    local explosions,last_now={},nil
    local WINDOW,MAX_EXPLOSIONS=.8,64
    local function hash(v)return type(v)=='string'and #v==16 and not v:find('[^%x]')and v~='0000000000000000'and v:upper()or nil end
    local function finite(v)return type(v)=='number'and v==v and v>-math.huge and v<math.huge end
    local function position(v)
        return type(v)=='table'and finite(v.x)and finite(v.y)and finite(v.z)
            and {x=v.x,y=v.y,z=v.z}or nil
    end
    local function row(kind,id)
        if not finite(id)or id<0 or id>=4294967296 or id%1~=0 then return nil end
        local rows=reverse[kind]
        return type(rows)=='table'and rows[tostring(id)]or nil
    end
    local function contains(item,id)
        if type(item)~='table'or type(item.candidates)~='table'then return false end
        for _,candidate in ipairs(item.candidates)do if hash(candidate)==id then return true end end
        return false
    end
    local typed_fields={{'damage_info','damage_info_id'},{'projectile','projectile_id'},
        {'explosion','explosion_id'},{'beam','beam_id'},{'arc','arc_id'}}
    local function payload_of(input)
        local combined,provided
        for _,field in ipairs(typed_fields)do
            local id=input[field[2]]
            if id~=nil then
                provided=true
                local item=row(field[1],id)
                if not item then return nil,true end
                local candidates={}
                for _,candidate in ipairs(item.candidates or {})do
                    if not combined or contains(combined,candidate)then candidates[#candidates+1]=candidate end
                end
                combined={candidates=candidates,unresolved=item.unresolved==true
                    or combined and combined.unresolved==true,shared=item.shared==true}
            end
        end
        if provided then return combined,true end
        local resource=hash(input.raw_type)
        local roots=resource and resource_nodes[resource]
        if not roots then return nil,false end
        if resource_payloads[resource]~=nil then return resource_payloads[resource]or nil,false end
        local candidates,seen,unresolved={},{},false
        for _,root in ipairs(roots)do
            local item=row(root.kind,root.id)
            if not item or item.unresolved then unresolved=true end
            for _,candidate in ipairs(item and item.candidates or {})do
                if not seen[candidate]then seen[candidate]=true;candidates[#candidates+1]=candidate end
            end
        end
        if #candidates==0 then resource_payloads[resource]=false;return nil,false end
        table.sort(candidates)
        local result={candidates=candidates,unresolved=unresolved,shared=#candidates>1,resource=resource}
        resource_payloads[resource]=result
        return result,false
    end
    local function clock(now)
        if not finite(now)or now<0 then return false end
        if last_now and now<last_now then explosions={}end
        last_now=now
        local kept={}
        for _,event in ipairs(explosions)do
            if now-event.time<=event.duration then kept[#kept+1]=event
            elseif event.status=='fire'then fire_diag.contexts_expired=fire_diag.contexts_expired+1 end
        end
        explosions=kept;api.diagnostics.explosions=#kept
        return true
    end
    local function stable(previous,input)
        return previous and previous.entity==input.entity and previous.pointer==input.pointer
            and previous.unit==input.unit and previous.epoch==input.epoch
            and type(previous.life)=='number'and previous.life<2 and previous.complete==true
    end
    function api:reset()explosions,last_now={},nil;self.diagnostics.explosions=0 end
    function api:life_changed(now)
        if not clock(now)then return end
        -- A respawn changes the avatar epoch, not the creator peer of fire
        -- already burning on this same world. Retain only those exact local
        -- fire events, at their original time/radius/window. Ordinary blast
        -- context and every per-target damage chain still end with the life.
        local kept={}
        for _,event in ipairs(explosions)do if event.status=='fire'then kept[#kept+1]=event end end
        explosions=kept;self.diagnostics.explosions=#kept
        fire_diag.life_fire_retained=fire_diag.life_fire_retained+#kept
    end
    function api:has_context(now)return clock(now)and #explosions>0 end
    function api:has_status_context(now,include_fire)
        if not clock(now)then return false end
        for _,event in ipairs(explosions)do
            if event.status=='poison'or include_fire~=false and event.status=='fire'then return true end
        end
        return false
    end
    function api:explosion(event,now)
        if not clock(now)or type(event)~='table'or event.local_player~=true then return false end
        local source,pos=hash(event.source_type),position(event.position)
        local radius=event.radius
        if not source or not pos or not finite(radius)or radius<=0 or radius>46.5 then return false end
        local payload=row('explosion',event.explosion_id)
        if payload and not contains(payload,source)then return false end
        local status,duration=nil,WINDOW
        if event.status=='poison'and finite(event.status_duration)and event.status_duration>0
            and event.status_duration<=10 then status,duration='poison',event.status_duration end
        -- Reviewed ground-fire sources outlive their initial explosion.
        -- Each source has its own bounded association window; this is not
        -- a native fire-instance ID or a live Health-element observation.
        if event.status=='fire'and finite(event.status_duration)and event.status_duration>0
            and event.status_duration<=30 then status,duration='fire',event.status_duration end
        if #explosions>=MAX_EXPLOSIONS then
            if explosions[1].status=='fire'then fire_diag.contexts_evicted=fire_diag.contexts_evicted+1 end
            table.remove(explosions,1)
        end
        explosions[#explosions+1]={source_type=source,position=pos,radius=radius,
            owner=event.owner,time=now,status=status,duration=duration}
        if status=='fire'then
            fire_diag.fire_contexts=fire_diag.fire_contexts+1
            if source=='5C14F27759DD3BE0'then fire_diag.g8_contexts=fire_diag.g8_contexts+1 end
        end
        self.diagnostics.explosions=#explosions
        return true
    end
    function api:resolve(input,previous,now)
        if not clock(now)or type(input)~='table'then return nil end
        if input.damage_observed~=true and input.first_seen_dead~=true then return nil end
        local fatal_fire=input.life==2 and input.kind==2 and input.element==1
        if input.life==2 then
            fire_diag.death_observations=fire_diag.death_observations+1
            if input.kind==nil or input.element==nil then fire_diag.death_cause_missing=fire_diag.death_cause_missing+1
            elseif not fatal_fire then fire_diag.fatal_nonfire=fire_diag.fatal_nonfire+1 end
        end
        if fatal_fire then
            fire_diag.fatal_fire_attempts=fire_diag.fatal_fire_attempts+1
            if input.first_seen_dead==true then fire_diag.first_dead_fire_attempts=fire_diag.first_dead_fire_attempts+1 end
        end
        if input.readable~=true then
            if fatal_fire then fire_diag.unreadable_fire=fire_diag.unreadable_fire+1 end
            return nil
        end
        local direct=hash(input.source_type)
        if direct then
            if fatal_fire then fire_diag.known_source_kept=fire_diag.known_source_kept+1 end
            return {type=direct,basis=input.source_policy or 'native_resource',inferred=false}
        end
        local payload,typed=payload_of(input)
        if payload and type(payload.candidates)=='table'and #payload.candidates==1
            and (payload.unresolved~=true or payload.resource and input.local_source==true)then
            local source=hash(payload.candidates[1])
            if source then
                self.diagnostics.mapped=self.diagnostics.mapped+1
                if fatal_fire then fire_diag.typed_source_kept=fire_diag.typed_source_kept+1 end
                if payload.resource then self.diagnostics.resource_mapped=self.diagnostics.resource_mapped+1 end
                return {type=source,basis=payload.resource and 'native_resource_typed_single_named_parent'
                    or input.damage_info_id~=nil and 'typed_damage_info_unique_parent'
                    or 'typed_native_unique_parent',inferred=true}
            end
        end
        -- A first-seen, exact fatal Health record is already a real observed
        -- death. It may use the same verified fire-area evidence without an
        -- invented live HP-loss timestamp. The observer still requires its
        -- existing fresh-death/native-local-kill quota before recording it.
        if input.damage_observed~=true and not(input.first_seen_dead==true and fatal_fire)then return nil end
        -- Unknown IDs/owners/tokens no longer sever a continuous real-damage
        -- chain. Its only time boundary is inactivity since the previous HP
        -- loss/death observation, never the age of the last named weapon.
        local same=stable(previous,input)and finite(previous.last_damage_at)
            and now>=previous.last_damage_at and now-previous.last_damage_at<=5+1e-9
            and previous.chain_expired~=true
        local named=same and hash(previous.chain_source)
        if payload and named and contains(payload,named)then
            self.diagnostics.mapped=self.diagnostics.mapped+1
            return {type=named,basis='typed_damage_info_same_target_parent',inferred=true}
        end
        local pos=position(input.position)
        local has_fire,credit_fire,typed_fire,inside_fire=false,false,false,false
        if pos then
            for i=#explosions,1,-1 do
                local event=explosions[i]
                local status=event.status=='poison'or event.status=='fire'
                local poison_compatible=event.status=='poison'and (input.kind==nil or input.kind==10 or input.kind==2 and input.element==5)
                    and (not typed or contains(payload,event.source_type))
                local fire_compatible=event.status=='fire'and input.life==2 and input.kind==2 and input.element==1
                    and (not typed or contains(payload,event.source_type))
                local blast_compatible=input.damage_observed==true and now-event.time<=WINDOW and
                    (payload and contains(payload,event.source_type)
                    or not payload and not typed and input.explosion_damage==true)
                local compatible=poison_compatible or fire_compatible or blast_compatible
                local credited=input.local_source==true or status and input.creditor_missing==true
                local owner=input.context_owner or input.owner
                -- A status instigator can be the expired throwable rather
                -- than the avatar carried by the explosion request. Current
                -- local credit (or the existing missing-creditor quota path)
                -- and the observed local status area establish this inference.
                local owner_matches=status or not owner or owner==0 or not event.owner or event.owner==0 or owner==event.owner
                local dx,dy,dz=pos.x-event.position.x,pos.y-event.position.y,pos.z-event.position.z
                if fatal_fire and event.status=='fire'then
                    has_fire=true
                    if credited then credit_fire=true end
                    if credited and fire_compatible then
                        typed_fire=true
                        if dx*dx+dy*dy+dz*dz<=event.radius*event.radius then inside_fire=true end
                    end
                end
                if credited and compatible and owner_matches and dx*dx+dy*dy+dz*dz<=event.radius*event.radius then
                    self.diagnostics.mapped=self.diagnostics.mapped+1
                    if fire_compatible then
                        fire_diag.fire_matched=fire_diag.fire_matched+1
                        if event.source_type=='5C14F27759DD3BE0'then fire_diag.g8_matched=fire_diag.g8_matched+1 end
                    end
                    return {type=event.source_type,basis=poison_compatible and 'same_target_local_poison_status_area'
                        or fire_compatible and 'same_target_local_fire_status_area'
                        or payload and 'typed_damage_info_local_blast_parent'
                        or 'same_target_recent_local_blast',inferred=true,local_source=true}
                end
            end
        end
        if fatal_fire then
            if not pos then
                for _,event in ipairs(explosions)do if event.status=='fire'then has_fire=true;break end end
            end
            if not has_fire then fire_diag.no_fire_context=fire_diag.no_fire_context+1
            elseif not pos then fire_diag.no_position=fire_diag.no_position+1
            elseif not credit_fire then fire_diag.credit_rejected=fire_diag.credit_rejected+1
            elseif not typed_fire then fire_diag.typed_rejected=fire_diag.typed_rejected+1
            elseif not inside_fire then fire_diag.outside_area=fire_diag.outside_area+1 end
        end
        if payload and (payload.shared==true or #payload.candidates>1)then
            self.diagnostics.shared_without_context=self.diagnostics.shared_without_context+1
        end
        return nil
    end
    return api
end
