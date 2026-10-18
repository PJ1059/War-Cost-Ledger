-- Per-target, observation-time damage chains. Unknown damage keeps the latest
-- named weapon while real HP loss/death observations stay at most 5s apart.
return function()
    local api={policy='same_target_continuous_damage_chain',version=2,gap=5}
    local function hash(v)return type(v)=='string'and #v==16 and not v:find('[^%x]')and v~='0000000000000000'and v:upper()or nil end
    local function clock(v)return type(v)=='number'and v==v and v>=0 and v<math.huge end
    local function identity(a,b)
        return a and a.entity==b.entity and a.pointer==b.pointer and a.unit==b.unit and a.epoch==b.epoch
    end
    local function copy_chain(out,previous)
        out.chain_source,out.chain_local=previous.chain_source,previous.chain_local
        out.chain_mechanism=previous.chain_mechanism
        out.last_damage_at,out.last_known_at=previous.last_damage_at,previous.last_known_at
        out.chain_had_source,out.chain_expired=previous.chain_had_source,previous.chain_expired
    end
    function api:baseline(row)
        return {entity=row.entity,pointer=row.pointer,unit=row.unit,epoch=row.epoch,
            health=row.health,life=row.life,complete=true,baseline=true,observed_at=row.now,barrier=false}
    end
    function api:observe(previous,row)
        local id,now=hash(row.source_type),row.now
        local out={entity=row.entity,pointer=row.pointer,unit=row.unit,epoch=row.epoch,
            health=row.health,life=row.life,raw_type=hash(row.raw_type),complete=row.readable==true,
            target_bound=true,barrier=true,policy=self.policy,owner=row.owner,
            kind=row.kind,element=row.element,local_source=row.local_source==true,
            damage_token=row.damage_token,damage_info_id=row.damage_info_id,observed_at=now}
        if row.readable~=true or not clock(now)then out.complete=false;return out end
        -- A first-seen corpse can expose a real source for this one death,
        -- but never supplies an alive damage timestamp or an inheritable chain.
        if row.first_seen_dead==true then
            local same=identity(previous,row)and previous.death_only_at==now
            local source=id or same and previous.death_only_type
            if source then
                out.type,out.barrier=source,false
                if id then out.inferred,out.source_policy=row.source_inferred==true,row.source_policy
                else out.inferred,out.source_policy=previous.inferred==true,previous.source_policy end
                out.mechanism=id and row.mechanism or previous and previous.mechanism
                out.death_only_type,out.death_only_at=source,now
            else out.complete=false end
            return out
        end
        local stable=identity(previous,row)and previous.complete==true
            and type(previous.life)=='number'and previous.life<2
            and (not clock(previous.observed_at)or now>=previous.observed_at)
        if stable then
            copy_chain(out,previous)
            out.barrier=previous.barrier==true
            if out.chain_source and clock(out.last_damage_at)and now-out.last_damage_at>self.gap+1e-9 then
                out.chain_source,out.chain_local=nil,nil
                out.chain_expired,out.barrier=true,true
            end
        end
        if row.damage_observed~=true then
            -- Source-field changes, contact metadata, healing and polling do
            -- not create a new weapon anchor or refresh the inactivity timer.
            if stable then
                out.type=out.chain_source
                out.inferred=out.type and previous.inferred==true or false
                if out.type then out.local_source=out.chain_local==true end
                out.mechanism=out.chain_mechanism
            else out.complete=false end
            return out
        end
        -- A dying enemy can write its own explosion into lastOwner after
        -- the weapon hit. Keep that target's live local weapon chain; the
        -- death blast is still the raw source for native-total correction.
        -- Other enemy owners, expired/foreign chains and source-free deaths
        -- retain their observed enemy/self-explosion mechanism below.
        if row.mechanism=='self_explosion'and row.kind==4 and row.owner==row.entity
            and type(row.life)=='number'and row.life>=2 and stable and out.chain_source
            and out.chain_local==true and out.chain_mechanism==nil and out.chain_source~=id then
            out.type,out.inferred,out.barrier=out.chain_source,true,false
            out.local_source,out.mechanism=true,nil
            out.last_damage_at=now
            out.source_policy='same_target_weapon_before_self_explosion'
            return out
        end
        if id then
            out.type,out.inferred,out.barrier=id,row.source_inferred==true,false
            out.named_source,out.source_policy=true,row.source_policy
            out.chain_source,out.chain_local=id,out.local_source
            out.mechanism,out.chain_mechanism=row.mechanism,row.mechanism
            out.last_damage_at,out.last_known_at=now,now
            out.chain_had_source,out.chain_expired=true,false
        elseif stable then
            out.last_damage_at=now
            if out.chain_source then
                out.type,out.inferred,out.barrier=out.chain_source,true,false
                out.local_source=out.chain_local==true
                out.mechanism=out.chain_mechanism
            end
            -- A chain that expired remains a veto of stale FIFO sources until
            -- a new actual named hit establishes another weapon anchor.
            if out.chain_expired then out.barrier=true end
        else out.complete=false end
        return out
    end
    function api:death(row)
        return {type=row and row.type or nil,raw_type=row and row.raw_type or nil,
            inferred=row and row.inferred==true or false,target_bound=true,
            barrier=not row or row.barrier~=false,history_complete=row and row.complete==true or false,
            local_source=row and row.local_source==true or false,
            owner=row and row.owner or nil,kind=row and row.kind or nil,element=row and row.element or nil,
            damage_token=row and row.damage_token or nil,damage_info_id=row and row.damage_info_id or nil,
            last_damage_at=row and row.last_damage_at or nil,last_known_at=row and row.last_known_at or nil,
            chain_expired=row and row.chain_expired==true or false,
            mechanism=row and row.mechanism or nil,
            policy=row and row.source_policy or self.policy}
    end
    return api
end
