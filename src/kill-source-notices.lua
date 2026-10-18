-- BFV-style immediate FIFO pairing. User-approved approximate attribution.
-- Only the latest target [source] is displayed, for five seconds after that kill.
return function(options)
    options=options or {}
    local names,enemies=options.names or {},options.enemies or {}
    local WINDOW,RECENT,CAP=.75,2.5,128
    local api={revision=0,window=WINDOW,policy='latest_fifo_with_bounded_async_source_fragments'}
    local sequence,last_now,ordinal,arrival=nil,0,0,0
    local deaths,batches,seen,seen_order={},{},{},{}
    local fragments,claims={},{}
    local latest,recent,cached,cached_revision=nil,nil,nil,-1
    local function integer(v,max)return type(v)=='number'and v>=0 and v<=max and v%1==0 end
    local function clock(v)return type(v)=='number'and v>=0 and v<math.huge end
    local function hash(v)return type(v)=='string'and #v==16 and not v:find('[^%x]')and v~='0000000000000000'and v:upper()or nil end
    local function clean(v)
        if type(v)~='string'or #v==0 or #v>256 or v:find('[%z\1-\31\127]')then return nil end
        return v
    end
    local function clip(v,limit)
        if #v<=limit then return v end
        local n=limit-3
        while n>0 do local b=v:byte(n+1);if not b or b<128 or b>191 then break end;n=n-1 end
        return v:sub(1,n)..'...'
    end
    local function label(catalog,id,raw,fallback)
        local row=id and catalog[id]
        if type(row)=='table'then
            raw=clean(row.name_zh)or clean(row.name_en)or clean(row.name)or clean(row.key)or raw
        elseif clean(row)then raw=row end
        if not clean(raw)and id and type(options.type_info)=='function'then
            local ok,info=pcall(options.type_info,id)
            if ok and type(info)=='table'then raw=clean(info.name_zh)or clean(info.display_name)or clean(info.name)end
        end
        if raw==id then raw=nil end
        return clip(clean(raw)or fallback,72)
    end
    local function fallback(now)return recent and now>=recent.at and now-recent.at<=RECENT and recent or nil end
    local function cause_label(value)
        if type(value)=='table'and value.source=='native_health_extension'and value.kind==2
            and value.life==2 and value.owned==true and value.current==true then
            return({[1]='火焰伤害',[5]='毒气伤害'})[value.element]
        end
    end
    local function melee_cause(value)
        return type(value)=='table'and value.source=='native_health_extension'and value.kind==6
            and value.life==2 and value.owned==true and value.current==true
    end
    local function show(death,source,now,basis,melee_credit)
        -- A later target may already have a direct source while this older
        -- target waits for a delayed stat fragment. Never rewind the HUD.
        if latest and death.order<latest.death_order then return end
        local target=death.damage_source
        local blocked=target and target.target_bound==true and target.barrier==true
            and target.history_complete~=false
        if target and target.target_bound==true and target.type then
            source={type=target.type,name=label(names,target.type,nil,'未知来源')}
            basis=target.policy or 'same_target_damage_source'
        elseif blocked then source=nil;basis='same_target_unknown_barrier' end
        local exact=source
        -- Missing target reads may still use this kill's actual native credit
        -- batch. They never borrow a previously fired/credited recent weapon.
        if not blocked and not(target and target.target_bound==true and not target.type)then
            source=source or fallback(now)
        end
        ordinal=ordinal+1
        local source_name=source and source.name or'未知来源'
        local source_hash=source and source.type
        if target and target.mechanism=='self_explosion'and source then
            source_name=label(enemies,source_hash,source_name,'敌方单位')..'（自爆）'
        elseif target and target.mechanism=='enemy_damage'and source then
            source_name=label(enemies,source_hash,source_name,'敌方单位')..'（友伤）'
        end
        local cause=cause_label(death.damage_cause)
        if cause and(not exact or source_name=='未知来源')then
            source_name=cause;basis='native_target_damage_element'
            if not exact then source_hash=nil end
        end
        if melee_credit and source_name=='未知来源'then
            source_name,source_hash,basis='近战',nil,'native_target_melee_with_melee_credit'
        end
        local text=death.name..' ['..source_name..']'
        latest={id=ordinal,death_order=death.order,sequence=sequence,expires_at=death.at+5,lines={text},text=text,
            target_text=death.name,source_text=source_name,target_hash=death.type,
            source_hash=source_hash,at=death.at,shown_at=now,kills=1,observed_victims=1,
            damage_cause=death.damage_cause,
            damage_source=target,
            status=(source or cause or melee_credit)and'inferred'or'unknown',attribution=basis or'recent_source',per_victim_proven=false}
        api.revision=api.revision+1
    end
    local function source_for(batch,death,consume)
        -- A per-target source replaces the batch label below. Charge its own
        -- quota, otherwise it would consume an unrelated weapon and leave
        -- the next unresolved victim with an avoidable unknown source.
        local target=death.damage_source
        local known=target and target.target_bound==true and target.type
        if not known and target and target.target_bound==true and target.barrier==true
            and target.history_complete~=false then return nil end
        for _,row in ipairs(batch.async and fragments or batch.sources)do
            if row.remaining>0 and(not known or row.type==known)
                and(not batch.async or math.abs(row.at-batch.at)<WINDOW-1e-9)then
                if consume then row.remaining=row.remaining-1 end
                return row
            end
        end
        return nil
    end
    local function match(now)
        while deaths[1]and batches[1]do
            local batch=batches[1]
            local death,index=deaths[1],1
            local source=source_for(batch,death,false)
            local target=death.damage_source
            local direct=target and(target.type or target.barrier==true and target.history_complete~=false)
                or melee_cause(death.damage_cause)and batch.melee_remaining>0
            if batch.async and not source and not direct and now-batch.at<WINDOW-1e-9
                and now-death.at<WINDOW-1e-9 then
                -- Wait for the source counter, but let an already resolved
                -- later target display without waiting behind this one.
                index=nil
                for i=2,#deaths do
                    local later=deaths[i].damage_source
                    if later and later.type then index=i;break end
                end
                if not index then break end
                death=deaths[index]
            end
            table.remove(deaths,index)
            source=source_for(batch,death,true)
            if batch.async then
                if source then recent={at=death.at,type=source.type,name=source.name}
                elseif death.damage_source and death.damage_source.type then
                    -- Reconcile a counter arriving after its directly known
                    -- target, so it cannot be spent on another victim.
                    if #claims>=CAP then table.remove(claims,1)end
                    claims[#claims+1]={at=batch.at,type=death.damage_source.type,remaining=1}
                end
            end
            -- kind6 also includes abilities. Only this native MELEE kill
            -- batch can explain it as melee, even when a named CQC weapon
            -- already wins the display and consumes this same credit.
            local melee_credit=melee_cause(death.damage_cause)and batch.melee_remaining>0
                and now-batch.at<WINDOW and now-death.at<WINDOW
            if melee_credit then batch.melee_remaining=batch.melee_remaining-1 end
            local basis=batch.async and source and source.at~=batch.at and'asynchronous_source_count'or'fifo_source_count'
            show(death,source,now,basis,melee_credit)
            batch.remaining=batch.remaining-1
            if batch.remaining<=0 then table.remove(batches,1)end
        end
    end
    function api:update(now)
        if not clock(now)or now<last_now then return false,'INVALID_CLOCK'end
        last_now=now
        for _,rows in ipairs({fragments,claims})do
            for i=#rows,1,-1 do
                if rows[i].remaining<=0 or now-rows[i].at>=WINDOW-1e-9 then table.remove(rows,i)end
            end
        end
        match(now)
        while deaths[1]and now-deaths[1].at>=WINDOW-1e-9 do show(table.remove(deaths,1),nil,now,'recent_source_fallback')end
        while batches[1]and now-batches[1].at>=WINDOW-1e-9 do table.remove(batches,1)end
        if latest and now>=latest.expires_at then latest=nil;self.revision=self.revision+1 end
        return true
    end
    function api:reset(value)
        assert(value==nil or integer(value,9007199254740991),'KILL_NOTICE_SEQUENCE')
        sequence,last_now,arrival=value,0,0;deaths,batches,seen,seen_order={},{},{},{}
        fragments,claims={},{}
        latest,recent=nil,nil;self.revision=self.revision+1
    end
    function api:gap()deaths,batches,recent,fragments,claims={},{},nil,{},{} end
    function api:on_death(event,now)
        if type(event)~='table'or sequence==nil or event.sequence~=sequence then return false,'OTHER_MISSION'end
        if event.local_killer~=true or(event.observed~='dead_state'and not(event.observed=='corpse'and event.inferred==true))
            or event.avatar==true or event.kind=='structure'then return false,'NOT_LOCAL_ENEMY_DEATH'end
        if not integer(event.entity_id,4294967294)or event.entity_id==0 then return false,'INVALID_ENTITY'end
        if not clock(now)or now<last_now then return false,'INVALID_CLOCK'end
        if seen[event.entity_id]then return false,'DUPLICATE_DEATH'end
        -- Expire existing work before adding a new event. Otherwise match()
        -- can spend an old empty batch on this target before its real credit.
        self:update(now)
        local id=hash(event.type)
        seen[event.entity_id]=true;seen_order[#seen_order+1]=event.entity_id
        if #seen_order>1024 then seen[table.remove(seen_order,1)]=nil end
        if #deaths>=CAP then show(table.remove(deaths,1),nil,now,'queue_fallback')end
        local cause=event.damage_cause
        local target=event.damage_source
        local bound=type(target)=='table'and target.target_bound==true
        arrival=arrival+1
        deaths[#deaths+1]={at=now,order=arrival,type=id,name=label(enemies,id,event.display_name or event.name,'未知目标'),
            damage_source=bound and{type=hash(target.type),raw_type=hash(target.raw_type),target_bound=true,
                barrier=target.barrier==true,inferred=target.inferred==true,policy=clean(target.policy),
                mechanism=(target.mechanism=='self_explosion'or target.mechanism=='enemy_damage')and target.mechanism or nil,
                history_complete=target.history_complete}or nil,
            damage_cause=(cause_label(cause)or melee_cause(cause))and{kind=cause.kind,element=cause.element,life=cause.life,
                owned=true,current=true,source=cause.source}or nil}
        return self:update(now)
    end
    function api:on_stats(event,now)
        if type(event)~='table'or sequence==nil or event.sequence~=sequence then return false,'OTHER_MISSION'end
        if event.local_player~=true then return false,'NOT_LOCAL_CREDIT'end
        if not integer(event.kills,2147483647)or type(event.sources)~='table'then return false,'INVALID_KILLS'end
        local melee_kills=event.melee_kills==nil and 0 or event.melee_kills
        if not integer(melee_kills,event.kills)then return false,'INVALID_MELEE'end
        if not clock(now)or now<last_now then return false,'INVALID_CLOCK'end
        self:update(now)
        -- Native total kills and per-source counts can advance on different
        -- polls. Keep each fragment briefly; only kill credits spend it.
        local incoming={}
        for i,row in ipairs(event.sources)do
            if i>CAP then break end
            if type(row)=='table'and integer(row.kills,2147483647)and row.kills>0 then
                local id=hash(row.type)
                if id then
                    incoming[#incoming+1]={type=id,name=row.name,remaining=row.kills}
                end
            end
        end
        -- The native map has no iteration order. Preserve the established
        -- count/hash order inside one poll without moving older fragments.
        table.sort(incoming,function(a,b)return a.remaining>b.remaining or(a.remaining==b.remaining and a.type<b.type)end)
        for _,row in ipairs(incoming)do
            local id,remaining=row.type,row.remaining
            for _,claim in ipairs(claims)do
                if claim.type==id and claim.remaining>0 and now-claim.at<WINDOW-1e-9 then
                    local used=math.min(remaining,claim.remaining)
                    remaining,claim.remaining=remaining-used,claim.remaining-used
                    if remaining==0 then break end
                end
            end
            if remaining>0 then
                if #fragments>=CAP then table.remove(fragments,1)end
                fragments[#fragments+1]={at=now,type=id,name=label(names,id,row.name,'未知来源'),remaining=remaining}
            end
        end
        if event.kills>0 then
            if #batches>=CAP then table.remove(batches,1)end
            batches[#batches+1]={at=now,remaining=event.kills,melee_remaining=melee_kills,sources={},async=true}
        end
        return self:update(now)
    end
    function api:on_batch(event,now)
        if type(event)~='table'or sequence==nil or event.sequence~=sequence then return false,'OTHER_MISSION'end
        if event.local_player~=true then return false,'NOT_LOCAL_CREDIT'end
        if not integer(event.kills,2147483647)or event.kills==0 or type(event.sources)~='table'then return false,'INVALID_KILLS'end
        local melee_kills=event.melee_kills==nil and 0 or event.melee_kills
        if not integer(melee_kills,event.kills)then return false,'INVALID_MELEE'end
        if not clock(now)or now<last_now then return false,'INVALID_CLOCK'end
        self:update(now)
        local sources={}
        for i,row in ipairs(event.sources)do
            if i>CAP then break end
            if type(row)=='table'and integer(row.kills,2147483647)and row.kills>0 then
                local id=hash(row.type)
                if id then sources[#sources+1]={type=id,name=label(names,id,row.name,'未知来源'),remaining=row.kills}end
            end
        end
        table.sort(sources,function(a,b)return a.remaining>b.remaining or(a.remaining==b.remaining and a.type<b.type)end)
        local preferred=sources[1]
        if preferred then recent={at=now,type=preferred.type,name=preferred.name}end
        if #batches>=CAP then table.remove(batches,1)end
        batches[#batches+1]={at=now,remaining=event.kills,melee_remaining=melee_kills,sources=sources,preferred=preferred}
        return self:update(now)
    end
    function api:snapshot(now)
        if now~=nil then self:update(now)end
        if cached_revision~=self.revision then
            cached_revision=self.revision;cached={revision=self.revision,items=latest and{latest}or{}}
        end
        return cached
    end
    api:reset(options.sequence)
    return api
end
