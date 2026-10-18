-- Per-match high-water records; no native reads or store access. Persist snapshot
-- when revision changes. Aggregate pairs come only from target-bound source
-- observations; independent totals never manufacture a weapon/victim pair.
local LIMIT=9007199254740991
local PERIOD={['24h']=86400,['7d']=604800,['30d']=2592000}
local ROLES={primary=true,secondary=true,support=true,throwable=true,stratagem=true,unknown=true}
local CATEGORIES={enemy=true,player=true,self=true,environment=true,unknown=true}
local REJECTED_DEATH_SOURCE={CONFLICTING_SOURCE_EVIDENCE=true,COUNTER_GAP_ATTRIBUTION_SKIPPED=true,
    COUNTER_VICTIM_AVATAR_NOT_DEAD=true,DEATH_SOURCE_IDENTITY_CHANGED=true,DEATH_SOURCE_CHANGED_AFTER_DEATH=true}
local function count(v)return type(v)=='number'and v>=0 and v<=LIMIT and v%1==0 end
local function stamp(v)return type(v)=='number'and v>=0 and v<=LIMIT and v or nil end
local function seq(v)return count(v)and v>0 end
local function resource(v)
    return type(v)=='string'and #v==16 and not v:find('[^%x]')and v~='0000000000000000'and v:upper()or nil
end
local function key(v)return string.format('%.0f',v)end
local function clean(v)
    return type(v)=='string'and #v>0 and #v<=256 and not v:find('[%z\1-\31\127]')and v or nil
end
local UNKNOWN_NAMES={['未知']=true,['未知来源']=true,['来源未知']=true,['未知单位']=true,
    ['未知敌人']=true,['旧未知敌人']=true,['未知武器']=true,['未知武器来源']=true,['未知战备']=true,
    ['未知死因']=true,['未记录']=true,['未记录的旧击杀']=true,
    ['unknown']=true,['unknown source']=true,['unknown unit']=true,['unknown enemy']=true,
    ['unknown weapon']=true,['unrecorded']=true}
local function identified_name(v)
    local name=clean(v)
    if not name or UNKNOWN_NAMES[name:lower()]then return nil end
    if name:lower():find('^entity/v1/unresolved/')then return nil end
    local raw=name:gsub('^#',''):gsub('^0[xX]','')
    if #raw==16 and not raw:find('[^%x]')then return nil end
    return name
end
local function copy(v)
    if type(v)~='table'then return v end
    local out={};for k,x in pairs(v)do out[k]=copy(x)end;return out
end
local function sorted_keys(value)
    local out={};for k in pairs(value or {})do out[#out+1]=k end
    table.sort(out);return out
end
local function faction(v)
    return ({terminids='bugs',automatons='bots',bugs='bugs',bots='bots',illuminate='illuminate'})[v]or'unknown'
end
local function normal_player(p)
    if type(p)~='table'then return nil end
    local out={name=clean(p.name),callsign=clean(p.callsign)}
    local peer=clean(p.peer_id or p.peerId or p.peer)
    if peer and #peer==16 and not peer:find('[^%x]')then out.peer_id=peer:upper()end
    local slot=p.slot;local persona=p.persona_index or p.personaIndex
    if count(slot)and slot>=1 and slot<=4 then out.slot=slot end
    if count(persona)and persona<8 then out.persona_index=persona end
    if count(p.slot_index)and p.slot_index<=3 then out.slot_index=p.slot_index end
    if count(p.avatar_id)and p.avatar_id>0 and p.avatar_id<4294967295 then out.avatar_id=p.avatar_id end
    out.identity_source=clean(p.identity_source)
    if out.peer_id then out.identity_scope='session_peer_not_permanent_account'end
    if type(p.name_fallback)=='boolean'then out.name_fallback=p.name_fallback end
    -- Peer is a session communication identifier. No permanent/platform account
    -- identity is synthesized from it or from a persona/entity slot.
    return out
end
local function normal_evidence(value)
    if type(value)=='string'then return clean(value),clean(value)end
    if type(value)~='table'then return nil,nil end
    local out={}
    for _,field in ipairs({'death_observed','source_channel','source_reason'})do out[field]=clean(value[field])end
    for _,field in ipairs({'runtime_death_event','native_death_counter','native_fatal_event_proven',
        'weapon_source_proven','damage_kind_proven','used_downing_source','nearby_death_inferred'})do
        if type(value[field])=='boolean'then out[field]=value[field]end
    end
    if count(value.death_index)and value.death_index<=2147483647 then out.death_index=value.death_index end
    local hash=clean(value.actor_type_hash)
    if hash and #hash==16 and not hash:find('[^%x]')then out.actor_type_hash=hash:upper()end
    for field,maximum in pairs({damage_kind_id=9,damage_element_id=255,
        damage_dealer=4294967295,damage_owner=4294967295})do
        if count(value[field])and value[field]<=maximum then out[field]=value[field]end
    end
    out.weapon_type_hash=resource(value.weapon_type_hash)
    for field,maximum in pairs({nearby_death_distance=10,nearby_death_interval=1})do
        local n=value[field]
        if type(n)=='number'and n>=0 and n<=maximum then out[field]=n end
    end
    return out,out.source_channel or out.source_reason or out.death_observed
end

return function(options)
    options=options or {}
    local weapons=type(options.weapon_catalog)=='table'and options.weapon_catalog or {}
    local enemies={}
    for id,v in pairs(type(options.enemy_catalog)=='table'and options.enemy_catalog or {})do
        if type(v)=='table'then
            enemies[id]=v
            if clean(v.key)then enemies[v.key]=v end
        end
    end
    local data={version=1,entries={},death_records={}}
    local by_sequence,death_ids={},{}
    local query_cache,cache_revision,cache_size,cache_use={},-1,0,0
    local crush_cache
    local QUERY_CACHE_LIMIT=32
    local api={version=1,revision=0,policy='source_and_enemy_totals_with_optional_target_bound_inferred_pairs'}
    local function clock()
        if type(options.clock)=='function'then
            local ok,v=pcall(options.clock);if ok then return stamp(v)end
        end
    end
    local function entry_for(sequence)
        local id=key(sequence);local entry=by_sequence[id]
        if not entry then
            entry={sequence=sequence,status='unknown',weapons={},enemies={}}
            by_sequence[id]=entry;data.entries[#data.entries+1]=entry
        end
        return entry
    end
    local function metadata(view,id,row)
        local catalog=(view=='weapons'and weapons or enemies)[id]
        local c=type(catalog)=='table'and catalog or {}
        local name=identified_name(c.name_zh)or identified_name(c.name)or identified_name(row.name_zh)or identified_name(row.name)
            or clean(c.name_zh)or clean(c.name)or clean(row.name_zh)or clean(row.name)
        local out={id=clean(c.id)or clean(c.key)or clean(row.id)or id,
            name=name or id,known=identified_name(name)~=nil}
        if view=='weapons'then
            out.category=ROLES[c.category]and c.category or ROLES[c.slot]and c.slot
                or ROLES[row.category]and row.category or ROLES[row.slot]and row.slot or'unknown'
            out.weapon_type=clean(c.weapon_type)or clean(c.weaponType)or clean(row.weapon_type)or'未知分类'
        else
            out.category='enemy';out.faction=faction(c.faction or row.faction)
            out.size=clean(c.size)or clean(c.class)or clean(row.size)or clean(row.class)or'未知体型'
        end
        return out
    end
    local function refresh_source(view,id,row)
        local catalog=(view=='weapons'and weapons or enemies)[id]
        if not catalog and #id==16 and not id:find('[^%x]')then
            catalog=(view=='weapons'and weapons or enemies)[id:upper()]
            if catalog then id=id:upper()end
        end
        if not catalog then return false end
        local changed=false
        for field,value in pairs(metadata(view,id,row))do
            if row[field]~=value then row[field]=value;changed=true end
        end
        return changed
    end
    local function refresh_death(row)
        -- These are explicit refusals made by the actual death observer, not
        -- merely an unresolved label. A later hash directory cannot undo them.
        if type(row.evidence)=='table'and REJECTED_DEATH_SOURCE[row.evidence.source_reason]
            or(type(row.player)=='table'and next(row.player)~=nil)then return false end
        local hash=type(row.evidence)=='table'and row.evidence.actor_type_hash
        if type(hash)~='string'or #hash~=16 or hash:find('[^%x]')or hash=='0000000000000000'then return false end
        local info=enemies[hash:upper()]
        local category=type(info)=='table'and(info.kind=='environment'and'environment'or(info.kill==true and info.asset~=true and'enemy'))
        if category and(row.category=='unknown'or row.category==category)then
            local name=clean(info.name_zh)or clean(info.name)or clean(info.key)
            if name then
                local changed=row.actor_name~=name or row.category~=category
                row.actor_name,row.category=name,category
                return changed
            end
        end
        -- Resolving an entity hash only supplies its display identity. Keep
        -- all original confidence, fatal-event and weapon evidence untouched.
        local name=clean(row.actor_name)
        local missing=not name or name=='未知来源'or name=='来源未知'or name=='未知敌人'or name=='未知单位'
            or name:upper()==hash:upper()
        if not missing or(row.category~='unknown'and row.category~='environment')
            or(type(row.player)=='table'and next(row.player)~=nil)or category=='enemy'then return false end
        local resource=weapons[hash:upper()]
        local label=type(resource)=='table'and(clean(resource.name_zh)or clean(resource.name))or nil
        if not label then return false end
        row.actor_name=label
        -- The shared hash-name directory also contains scenery, effects and
        -- vehicles. Its label identifies this source, never a proven weapon.
        return true
    end
    local function update_rows(entry,view,rows,legacy)
        if type(rows)~='table'then return false end
        local changed=false
        for id,row in pairs(rows)do
            local n=type(row)=='table'and (view=='weapons'and row.kills or row.count or row.kills)
            if clean(id)and count(n)and n>0 then
                local old=entry[view][id]
                if not old or n>old.kills then
                    local value=metadata(view,id,row);value.kills=n
                    entry[view][id]=value;changed=true
                end
            end
        end
        local observed=view..'_observed'
        if (not legacy or next(entry[view])~=nil)and entry[observed]~=true then entry[observed]=true;changed=true end
        return changed
    end
    local function observe(state,legacy)
        if type(state)~='table'or not seq(state.sequence)then return false,'no_mission' end
        local status=state.mission==true and'active'or state.status
        if status~='active'and status~='ended'and status~='interrupted'then return false,'no_mission' end
        local id=key(state.sequence);local entry=by_sequence[id]
        if entry and entry.status=='ended'and status=='active'then return false,'ended' end
        local fresh=entry==nil;entry=entry or entry_for(state.sequence)
        local changed=fresh
        if fresh then
            entry.legacy=legacy==true
            entry.started_at=stamp(state.started_at)
            entry.ended_at=stamp(state.ended_at)
            entry.first_observed_at=not legacy and clock()or nil
        end
        for _,field in ipairs({'started_at','ended_at'})do
            if entry[field]==nil and stamp(state[field])then entry[field]=state[field];changed=true end
        end
        if not legacy and not entry.first_observed_at then
            local at=clock();if at then entry.first_observed_at=at;changed=true end
        end
        for _,field in ipairs({'kills','deaths'})do
            local n=state[field]
            if count(n)and(entry[field]==nil or n>entry[field])then entry[field]=n;changed=true end
        end
        -- A target-bound inherited source can replace a raw unknown native
        -- source for the same kill. Keep both raw rows and a monotone, local
        -- correction; only the query presentation consumes the correction.
        for raw,n in pairs(type(state.source_reassignments)=='table'and state.source_reassignments or {})do
            local hash=raw=='_unknown'and raw or resource(raw)
            if hash and count(n)and n>0 then
                local corrections=entry.source_reassignments
                if not corrections then corrections={};entry.source_reassignments=corrections end
                if n>(corrections[hash]or 0)then corrections[hash]=n;changed=true end
            end
        end
        changed=update_rows(entry,'weapons',state.weapon_stats,legacy)or changed
        changed=update_rows(entry,'enemies',state.unit_kills,legacy)or changed
        -- Monotone aggregate counts, not an event log. Old records without
        -- target-bound observations remain without associations.
        for target,values in pairs(type(state.kill_pairs)=='table'and state.kill_pairs or {})do
            local enemy=resource(target)
            if enemy and type(values)=='table'then
                for source,n in pairs(values)do
                    local weapon=resource(source)
                    if weapon and count(n)and n>0 then
                        if not entry.kill_pairs then entry.kill_pairs={}end
                        local row=entry.kill_pairs[enemy]
                        if not row then row={};entry.kill_pairs[enemy]=row end
                        if n>(row[weapon]or 0)then row[weapon]=n;changed=true end
                    end
                end
            end
        end
        local unknown={}
        for id,row in pairs(type(state.unknown_unit_kills)=='table'and state.unknown_unit_kills or {})do
            if type(id)=='string'and #id==16 and not id:find('[^%x]')and type(row)=='table'then
                local exact=enemies[id:upper()]
                -- A classified row with that semantic key is authoritative;
                -- do not also count the same snapshot's raw unknown lane.
                local classified=type(state.unit_kills)=='table'and
                    (state.unit_kills[id]or(exact and state.unit_kills[exact.key]))
                if not classified then unknown[id:upper()]=row end
            end
        end
        if next(unknown)then changed=update_rows(entry,'enemies',unknown,legacy)or changed end
        if legacy and entry.status=='ended'then status='ended'end
        if entry.status~=status then
            -- Returning to the ship is still an ended match. A process restart
            -- is interrupted; it cannot supply an invented end timestamp.
            if not legacy and status=='ended'and entry.status=='active'then entry.ended_at=stamp(state.ended_at)or clock()end
            entry.status=status;changed=true
        end
        if not legacy and changed then entry.last_observed_at=clock()end
        if changed then api.revision=api.revision+1 end
        return changed,changed and'observed'or'unchanged'
    end
    if options.saved~=nil then
        local saved=options.saved
        assert(type(saved)=='table'and saved.version==1 and type(saved.entries)=='table'
            and type(saved.death_records)=='table','unsupported combat records')
        for _,v in ipairs(saved.entries)do
            assert(type(v)=='table'and seq(v.sequence)and not by_sequence[key(v.sequence)]
                and type(v.weapons)=='table'and type(v.enemies)=='table','invalid combat match')
            for _,field in ipairs({'kills','deaths'})do assert(v[field]==nil or count(v[field]),'invalid combat total')end
            for _,field in ipairs({'started_at','ended_at','first_observed_at','last_observed_at'})do
                assert(v[field]==nil or stamp(v[field]),'invalid combat timestamp')
            end
            for _,view in ipairs({'weapons','enemies'})do
                for id,row in pairs(v[view])do
                    assert(clean(id)and type(row)=='table'and clean(row.id)and clean(row.name)
                        and count(row.kills),'invalid saved combat source')
                end
            end
            if v.source_reassignments~=nil then
                assert(type(v.source_reassignments)=='table','invalid saved source reassignments')
                for raw,n in pairs(v.source_reassignments)do
                    assert((raw=='_unknown'or resource(raw)==raw)and count(n)and n>0,'invalid saved source reassignment')
                end
            end
            if v.kill_pairs~=nil then
                assert(type(v.kill_pairs)=='table','invalid saved kill pairs')
                for target,values in pairs(v.kill_pairs)do
                    assert(resource(target)==target and type(values)=='table','invalid saved pair target')
                    for source,n in pairs(values)do
                        assert(resource(source)==source and count(n)and n>0,'invalid saved pair source/count')
                    end
                end
            end
            local entry=copy(v)
            for _,view in ipairs({'weapons','enemies'})do
                for id,row in pairs(entry[view])do
                    if refresh_source(view,id,row)then api.revision=api.revision+1 end
                end
            end
            if entry.status=='active'then entry.status='interrupted';api.revision=api.revision+1 end
            data.entries[#data.entries+1]=entry;by_sequence[key(entry.sequence)]=entry
        end
        for _,v in ipairs(saved.death_records)do
            assert(type(v)=='table'and clean(v.id)and seq(v.sequence)and CATEGORIES[v.category]
                and not death_ids[v.id],'invalid saved death record')
            assert(v.occurred_at==nil or stamp(v.occurred_at),'invalid saved death timestamp')
            local row=copy(v)
            if refresh_death(row)then api.revision=api.revision+1 end
            data.death_records[#data.death_records+1]=row;death_ids[row.id]=true
        end
    end
    -- Import only actual saved fields. An old final snapshot has no proven
    -- wall-clock timestamp unless that timestamp was already stored with it.
    local imported={}
    local function import(v)
        if type(v)~='table'then return end
        if seq(v.sequence)then imported[#imported+1]=v
        elseif type(v.entries)=='table'then for _,entry in ipairs(v.entries)do import(entry)end
        else for _,entry in ipairs(v)do import(entry)end end
    end
    import(options.legacy);import(options.history)
    table.sort(imported,function(a,b)return a.sequence<b.sequence end)
    for _,v in ipairs(imported)do
        local row=copy(v);row.mission=false
        row.status=row.status=='ended'and'ended'or'interrupted';observe(row,true)
    end
    function api:observe(state)return observe(state,false)end
    function api:record_death(value)
        if type(value)~='table'or not seq(value.sequence)or not clean(value.id)then return false,'invalid_death' end
        local id=key(value.sequence)..':'..value.id
        if not clean(id)then return false,'invalid_death_id'end
        if death_ids[id]then return false,'duplicate' end
        local category=CATEGORIES[value.category]and value.category or'unknown'
        local confidence=({inferred=true,low=true,unknown=true})[value.confidence]and value.confidence or'unknown'
        local evidence,evidence_text=normal_evidence(value.evidence)
        local row={id=id,source_id=value.id,sequence=value.sequence,occurred_at=stamp(value.occurred_at or value.at),
            mission_elapsed=stamp(value.mission_elapsed),category=category,
            actor_name=clean(value.actor_name or value.actor)or'未知来源',
            weapon_name=clean(value.weapon_name or value.weapon),damage_kind=clean(value.damage_kind or value.attack),
            confidence=confidence,evidence=evidence,evidence_text=evidence_text,event=clean(value.event),
            player=normal_player(value.player),victim=normal_player(value.victim)}
        row.observed=clean(value.observed)or(type(evidence)=='table'and evidence.death_observed or nil)
        local death_index=value.death_index or(type(evidence)=='table'and evidence.death_index or nil)
        if count(death_index)and death_index<=2147483647 then row.death_index=death_index end
        refresh_death(row)
        -- Preserve a proven observation time; never label the UI opening time
        -- as the death time, and never infer a platform ID from a peer string.
        data.death_records[#data.death_records+1]=row;death_ids[id]=true
        local entry=entry_for(value.sequence)
        if not entry.first_observed_at then entry.first_observed_at=row.occurred_at end
        self.revision=self.revision+1;return true,'recorded'
    end
    function api:snapshot()return copy(data)end
    function api:vehicle_body_kills(sequence)
        if not seq(sequence)then return nil end
        local entry=by_sequence[key(sequence)]
        if not entry then return nil end
        local sources=options.vehicle_body_sources or {}
        local total=0
        for id,row in pairs(entry.weapons)do
            local exact=type(id)=='string'and #id==16 and not id:find('[^%x]')and sources[id:upper()]
            if exact and count(row.kills)then
                if total>LIMIT-row.kills then return nil end
                total=total+row.kills
            end
        end
        return total
    end
    function api:legacy_crush_summary(history)
        local entries=type(history)=='table'and(history.entries or history)or {}
        local revision=type(history)=='table'and count(history.revision)and history.revision or nil
        if not revision then crush_cache=nil end
        if revision and crush_cache and crush_cache.entries==entries and crush_cache.history_revision==revision
            and crush_cache.revision==self.revision then return crush_cache.result end
        local summary={total=0,by_sequence={},policy='exact_saved_vehicle_body_sources_display_only'}
        for _,entry in ipairs(entries)do
            if type(entry)=='table'and seq(entry.sequence)and type(entry.ribbons)=='table'
                and(entry.status=='ended'or entry.status=='interrupted')and entry.ribbons.crush==nil
                and entry.crush_policy~='confirmed_player_vehicle_parent_source_kills_as_crush'
                and summary.by_sequence[entry.sequence]==nil then
                local kills=self:vehicle_body_kills(entry.sequence)
                if kills and kills>0 then
                    if summary.total>LIMIT-kills then return {total=0,by_sequence={},overflow=true}end
                    summary.total=summary.total+kills;summary.by_sequence[entry.sequence]=kills
                end
            end
        end
        -- Without an explicit history revision, callers may edit the same table
        -- in place. Keep the legacy path uncached rather than miss that change.
        if revision then crush_cache={entries=entries,history_revision=revision,revision=self.revision,result=summary}end
        return summary
    end
    local function match_time(entry)return entry.ended_at or entry.started_at or entry.first_observed_at end
    local function within(at,period,now)
        return period=='all'or(at~=nil and now~=nil and at>=now-PERIOD[period]and at<=now)
    end
    local function death_aliases(v)
        local out=copy(v)
        out.at,out.match,out.actor,out.weapon,out.attack=out.occurred_at,out.sequence,out.actor_name,out.weapon_name,out.damage_kind
        return out
    end
    local function corrected_sources(entry)
        local amounts,unmatched,total,unknown_total={},0,0,0
        for _,n in pairs(entry.source_reassignments or {})do unmatched=unmatched+n end
        for id,row in pairs(entry.weapons)do
            local hash=resource(id)
            local correction=hash and entry.source_reassignments and entry.source_reassignments[hash]or 0
            local removed=math.min(row.kills,correction)
            local n=row.kills-removed
            amounts[id]=n;unmatched=unmatched-removed;total=total+n
            if not metadata('weapons',id,row).known then unknown_total=unknown_total+n end
        end
        local remaining=count(entry.kills)and math.min(math.max(0,unmatched),math.max(0,total-entry.kills),unknown_total)or 0
        for _,id in ipairs(sorted_keys(amounts))do
            if remaining>0 and not metadata('weapons',id,entry.weapons[id]).known then
                local removed=math.min(amounts[id],remaining)
                amounts[id]=amounts[id]-removed;remaining=remaining-removed
            end
        end
        return amounts
    end
    local function inferred_pairs(entry,amounts,view,associations)
        if not entry.kill_pairs then return end
        local available={weapons={},enemies={}}
        for _,lane in ipairs({'weapons','enemies'})do
            for id,row in pairs(entry[lane])do
                local meta=metadata(lane,id,row)
                local n=lane=='weapons'and amounts[id]or row.kills
                if meta.known then available[lane][meta.id]=(available[lane][meta.id]or 0)+n end
            end
        end
        local budget=entry.kills or LIMIT
        for _,target in ipairs(sorted_keys(entry.kill_pairs))do
            local enemy=metadata('enemies',target,entry.enemies[target]or {})
            for _,source in ipairs(sorted_keys(entry.kill_pairs[target]))do
                local weapon=metadata('weapons',source,entry.weapons[source]or {})
                local n=math.min(entry.kill_pairs[target][source],available.enemies[enemy.id]or 0,
                    available.weapons[weapon.id]or 0,budget)
                if n>0 and enemy.known and weapon.known then
                    available.enemies[enemy.id]=available.enemies[enemy.id]-n
                    available.weapons[weapon.id]=available.weapons[weapon.id]-n;budget=budget-n
                    local owner,detail=weapon,enemy
                    if view=='enemies'then owner,detail=enemy,weapon end
                    local row=associations[owner.id]
                    if not row then row={};associations[owner.id]=row end
                    local item=row[detail.id]
                    if not item then
                        item=copy(detail);item.kills=0;item.inferred=true;item.confidence='inferred'
                        row[detail.id]=item
                    end
                    item.kills=item.kills+n
                end
            end
        end
    end
    function api:query(view,filters)
        filters=filters or {};assert(view=='weapons'or view=='enemies'or view=='deaths','unknown combat view')
        local period=PERIOD[filters.period]and filters.period or'all'
        local now=stamp(filters.now)or clock()
        if cache_revision~=self.revision then
            query_cache={};cache_revision=self.revision;cache_size=0
        end
        local cache_key={view,period}
        for _,field in ipairs({'sequence','query','role','weapon_type','faction','size','category','mode','focus_id','sort'})do
            local value=tostring(filters[field]or'')
            cache_key[#cache_key+1]=#value..':'..value
        end
        cache_key=table.concat(cache_key,'|')
        cache_use=cache_use+1
        local cached=query_cache[cache_key]
        if cached and(period=='all'or now==nil and cached.at==nil
            or now and cached.at and now>=cached.at and(not cached.until_at
                or now<cached.until_at or cached.inclusive and now==cached.until_at))then
            cached.used=cache_use;return cached.result
        end
        local until_at,inclusive
        local function boundary(at)
            if period=='all'or not now or not at then return end
            local edge,include
            if at>now then edge,include=at,false
            elseif at+PERIOD[period]>=now then edge,include=at+PERIOD[period],true end
            if edge and(not until_at or edge<until_at or edge==until_at and not include)then
                until_at,inclusive=edge,include
            end
        end
        local query=(clean(filters.query)or''):lower()
        local function matches(s)
            local raw=tostring(s or'')
            if raw:lower():find(query,1,true)~=nil then return true end
            return type(options.search_alias)=='function'and tostring(options.search_alias(raw)):lower():find(query,1,true)~=nil
        end
        local result={view=view,rows={},totals={kills=0,known_kinds=0,linked_kills=0,deaths=0},
            coverage={weapon_details=false,enemy_details=false,death_records=false,linkage='unavailable',
                per_victim_weapon=false,inferred_pairs=0,legacy_kills=0,legacy_deaths=0,unknown_time_kills=0,
                unknown_time_deaths=0,unknown_kills=0,unrecorded_deaths=0,
                period_basis='match_end_or_first_observation',partial=false},available_weapon_types={}}
        local c=result.coverage;local map,types,associations={},{},{}
        local native_deaths={}
        for _,entry in ipairs(data.entries)do
            local at=match_time(entry)
            local selected=filters.sequence==nil or filters.sequence==entry.sequence
            if selected then boundary(at)end
            if selected and not at then c.unknown_time_kills=c.unknown_time_kills+(entry.kills or 0);c.unknown_time_deaths=c.unknown_time_deaths+(entry.deaths or 0)end
            if selected and within(at,period,now)then
                native_deaths[entry.sequence]=entry.deaths or 0
                c.weapon_details=c.weapon_details or entry.weapons_observed==true
                c.enemy_details=c.enemy_details or entry.enemies_observed==true
                if entry.legacy then c.legacy_kills=c.legacy_kills+(entry.kills or 0);c.legacy_deaths=c.legacy_deaths+(entry.deaths or 0)end
                if view~='deaths'then
                    local known=0
                    local amounts=(view=='weapons'or entry.kill_pairs)and corrected_sources(entry)or nil
                    inferred_pairs(entry,amounts,view,associations)
                    local function add(id,meta,kills)
                        if kills<=0 then return end
                        local row=map[id]
                        if not row then row=copy(meta);row.id=id;row.kills=0;map[id]=row end
                        row.kills=row.kills+kills
                    end
                    for id,source in pairs(entry[view])do
                        -- Identity is separate from classification: a retained
                        -- readable name does not need a known slot/size or a
                        -- current catalog entry. Recompute only this view.
                        local meta=metadata(view,id,source)
                        local n=view=='weapons'and amounts[id]or source.kills
                        known=known+n;add(meta.id,meta,n)
                    end
                    local unknown=math.max(0,(entry.kills or 0)-known)
                    if unknown>0 then
                        add('unknown',{name='未知',category='unknown',faction='unknown',size='未知体型',known=false},unknown)
                    end
                end
            end
        end
        if view=='deaths'then
            local records,recorded_by_sequence={},{}
            for _,row in ipairs(data.death_records)do
                if filters.sequence==nil or filters.sequence==row.sequence then boundary(row.occurred_at)end
                if (filters.sequence==nil or filters.sequence==row.sequence)and within(row.occurred_at,period,now)then
                    records[#records+1]=death_aliases(row)
                    recorded_by_sequence[row.sequence]=(recorded_by_sequence[row.sequence]or 0)+1
                end
            end
            -- Each match owns its own missing-count gap. Extra real records in
            -- a different match cannot consume an old match's missing causes.
            for sequence,native in pairs(native_deaths)do
                c.unrecorded_deaths=c.unrecorded_deaths+math.max(0,native-(recorded_by_sequence[sequence]or 0))
            end
            result.totals.deaths=#records+c.unrecorded_deaths
            c.death_records=#records>0
            table.sort(records,function(a,b)
                if(a.at or-1)~=(b.at or-1)then return(a.at or-1)>(b.at or-1)end
                if a.sequence~=b.sequence then return a.sequence>b.sequence end
                return a.id>b.id
            end)
            local filtered_recorded=0
            local function unknown_group()
                local group=map.unknown
                if not group then
                    group={id='unknown',name='未知死因',category='unknown',known=false,
                        unknown_group=true,count=0,records={},unrecorded_count=0}
                    map.unknown=group
                end
                return group
            end
            for _,row in ipairs(records)do
                local player=row.player or {}
                local unknown=row.category~='player'and row.category~='self'
                    and not identified_name(row.actor_name)
                if (not filters.category or filters.category=='all'or filters.category==row.category
                    or filters.category=='unknown'and unknown)
                    and matches(table.concat({row.actor_name or'',row.weapon_name or'',row.damage_kind or'',
                        player.name or'',player.peer_id or'',player.callsign or'',row.id,row.source_id or'',
                        '对局 #'..key(row.sequence),'事件 #'..(row.source_id or row.id),
                        row.evidence_text or(type(row.evidence)=='string'and row.evidence)or'',row.event or'',
                        unknown and'未知死因'or''},' '))then
                    filtered_recorded=filtered_recorded+1
                    if unknown then
                        local group=unknown_group()
                        group.count=group.count+1;group.records[#group.records+1]=row
                    elseif filters.mode=='recent'then row.known=true;result.rows[#result.rows+1]=row
                    else
                        -- Rank friendly fire as one cause. Participant identities
                        -- remain in each detail record, never separate TK ranks.
                        local group_name=({player='队友',self='自身'})[row.category]or row.actor_name
                        if row.category=='self'then
                            local cause=identified_name(row.weapon_name)or identified_name(row.damage_kind)
                            if cause then group_name=group_name..' · '..cause end
                        end
                        local group_id=row.category..':'..group_name
                        local group=map[group_id]
                        if not group then group={id=group_id,name=group_name,category=row.category,known=true,count=0,records={}};map[group_id]=group end
                        group.count=group.count+1;group.records[#group.records+1]=row
                    end
                end
            end
            local missing_allowed=not filters.category or filters.category=='all'or filters.category=='unknown'
            if c.unrecorded_deaths>0 and missing_allowed and matches('未知死因 未记录 未采集')then
                local group=unknown_group()
                group.unrecorded_count=c.unrecorded_deaths;group.count=group.count+c.unrecorded_deaths
            end
            if filters.mode~='recent'then
                for _,row in pairs(map)do result.rows[#result.rows+1]=row end
                table.sort(result.rows,function(a,b)
                    if(a.known==false)~=(b.known==false)then return a.known~=false end
                    if filters.sort=='name'then return a.name<b.name end
                    return a.count>b.count or(a.count==b.count and a.id<b.id)
                end)
            elseif map.unknown then
                -- Known recent events retain chronology. One final group keeps
                -- all actual unknown events (with original times/TK details)
                -- and only a numeric summary for never-collected deaths.
                result.rows[#result.rows+1]=map.unknown
            end
            result.totals.recorded_deaths=filtered_recorded
            result.totals.unrecorded_deaths=map.unknown and map.unknown.unrecorded_count or 0
            result.totals.filtered_deaths=filtered_recorded+result.totals.unrecorded_deaths
            result.totals.known_kinds=0
            if filters.mode~='recent'then for _,row in ipairs(result.rows)do
                if row.known then result.totals.known_kinds=result.totals.known_kinds+1 end
            end end
        else
            local unknown
            for _,row in pairs(map)do
                if view=='weapons'and(not filters.role or filters.role=='all'or filters.role==row.category)and row.weapon_type then types[row.weapon_type]=true end
                local role=filters.role or filters.category
                local allowed=view=='weapons'and(not role or role=='all'or row.category==role)
                    and(not filters.weapon_type or filters.weapon_type=='all'or row.weapon_type==filters.weapon_type)
                    or view=='enemies'and(not filters.faction or filters.faction=='all'or row.faction==faction(filters.faction))
                    and(not filters.size or filters.size=='all'or row.size==filters.size)
                local display_id=row.known and row.id or'unknown'
                if allowed and(matches(row.name)or not row.known and matches('未知'))
                    and(not filters.focus_id or filters.focus_id==display_id)then
                    result.totals.kills=result.totals.kills+row.kills
                    if row.known then
                        result.rows[#result.rows+1]=row;result.totals.known_kinds=result.totals.known_kinds+1
                    else
                        if not unknown then unknown={id='unknown',name='未知',category='unknown',
                            faction='unknown',size='未知体型',known=false,kills=0}end
                        unknown.kills=unknown.kills+row.kills;c.unknown_kills=c.unknown_kills+row.kills
                    end
                end
            end
            if unknown then result.rows[#result.rows+1]=unknown end
            for _,row in ipairs(result.rows)do
                local linked=0;row.detail_rows={}
                for _,item in pairs(row.known and associations[row.id]or {})do
                    local detail=copy(item);detail.kills=math.min(detail.kills,row.kills-linked)
                    if detail.kills>0 then row.detail_rows[#row.detail_rows+1]=detail;linked=linked+detail.kills end
                end
                table.sort(row.detail_rows,function(a,b)return a.kills>b.kills or a.kills==b.kills and a.id<b.id end)
                row.linked_kills=linked;row.unknown_kills=row.kills-linked
                if row.unknown_kills>0 then row.detail_rows[#row.detail_rows+1]={id='unknown',name='未知',kills=row.unknown_kills,known=false}end
                result.totals.linked_kills=result.totals.linked_kills+linked
            end
            c.inferred_pairs=result.totals.linked_kills
            if c.inferred_pairs>0 then c.linkage='target_bound_inferred'end
            table.sort(result.rows,function(a,b)
                if(a.known==false)~=(b.known==false)then return a.known~=false end
                if filters.sort=='name'then return a.name<b.name end
                return a.kills>b.kills or(a.kills==b.kills and a.id<b.id)
            end)
        end
        for value in pairs(types)do result.available_weapon_types[#result.available_weapon_types+1]=value end
        table.sort(result.available_weapon_types)
        c.partial=c.unknown_kills>0 or c.unrecorded_deaths>0 or(period~='all'and c.unknown_time_kills+c.unknown_time_deaths>0)
        c.message=view=='deaths'and'未知死因已合并置底；展开查看已保存线索。'
            or(c.inferred_pairs>0 and'缺少关联的部分归为未知。'
                or'武器与敌人各自汇总；逐敌人武器关联未取得。')
        if not cached then
            if cache_size>=QUERY_CACHE_LIMIT then
                local oldest,used
                for id,item in pairs(query_cache)do if not used or item.used<used then oldest,used=id,item.used end end
                query_cache[oldest]=nil;cache_size=cache_size-1
            end
            cache_size=cache_size+1
        end
        query_cache[cache_key]={result=result,at=now,until_at=until_at,inclusive=inclusive,used=cache_use}
        return result
    end
    return api
end
