-- Ledger-owned achievement rules over already attributed local deaths.
-- No process access, polling, UI writes or reconstruction from old totals.
return function(options)
    local state=assert(options.state,'combat achievements need state')
    local award=assert(options.award,'combat achievements need award callback')
    local traits=options.traits or {}
    local elemental=options.on_elemental_kill
    local api={version=1,double_giant_window=.750,streak_window=5,
        policy='local_native_kill_growth_adjacent_gap_max_5s'}
    local sequence,last_time,pending_giant,giants=nil,nil,nil,{}
    local last_kill_time,streak,streak_bots,streak_medals=nil,0,0,{}
    local baseline_pending=true
    local crush_awarded=false
    local source_seen,source_order={},{}
    local thresholds={{'democracy_star',50,30},{'super_democracy_star',80,50},
        {'supreme_democracy_star',100,60}}
    local function finite(v)return type(v)=='number' and v>=0 and v<math.huge end
    local function clear_streak()
        last_kill_time,streak,streak_bots,streak_medals=nil,0,0,{}
        state.killstreak=0
    end
    local function medals()
        for _,tier in ipairs(thresholds)do
            if not streak_medals[tier[1]] and (streak>=tier[2] or (streak>=tier[3] and streak_bots>=tier[3])) then
                streak_medals[tier[1]]=true;award(tier[1],true)
            end
        end
    end
    function api:reset_life()
        state.life_light_kills=0
        pending_giant,giants,last_time=nil,{},nil
        clear_streak()
    end
    function api:reset()
        sequence=state.sequence
        self:reset_life();baseline_pending=true
        crush_awarded=false
        source_seen,source_order={},{}
        state.killstreak_peak=0
    end
    function api:gap()
        clear_streak();baseline_pending=true
        pending_giant,giants,last_time=nil,{},nil
    end
    function api:baseline()
        clear_streak();baseline_pending=false
    end
    -- The caller supplies only the current mission's already-verified local
    -- player vehicle-parent growth. Legacy display sums never enter this path.
    function api:on_crush(total)
        if not state.mission or not finite(total)or total%1~=0 then return end
        if sequence~=state.sequence then self:reset()end
        if total>=100 and not crush_awarded then
            crush_awarded=true;award('tyranny_speed_bump',true)
            return true
        end
    end
    -- Feed only growth in the existing local native kill counter. The first
    -- valid observation after any read gap is a baseline, never a burst.
    function api:on_stats(added,now)
        if not state.mission or not finite(now) or not finite(added) or added%1~=0 then return end
        if sequence~=state.sequence then self:reset() end
        if baseline_pending then self:baseline();return end
        if last_kill_time and now<last_kill_time then return end
        if last_kill_time and now-last_kill_time>api.streak_window+1e-9 then clear_streak() end
        if added==0 then return end
        local previous=streak
        streak=streak+added;last_kill_time=now
        state.killstreak=streak
        state.killstreak_peak=math.max(state.killstreak_peak or 0,streak)
        local ribbons=math.floor(streak/5)-math.floor(previous/5)
        if ribbons>0 then state.ribbons.killstreak=(state.ribbons.killstreak or 0)+ribbons end
        medals()
        return true
    end
    function api:on_kill(event,role,now)
        if not state.mission or type(event)~='table' or event.local_killer~=true
            or type(role)~='table' or role.kill~=true or not finite(now) then return end
        if sequence~=state.sequence then self:reset() end
        if last_time and now<last_time then return end
        last_time=now
        local id=event.entity_id
        local proof=event.damage_source
        local source=type(proof)=='table'and proof.target_bound==true and proof.barrier==false and proof.type or nil
        local fact=source and traits[source]
        -- One actual target death may earn at most one elemental ribbon and
        -- one low-AP achievement, regardless of repeated adapter callbacks.
        local identity=(type(id)=='number'or type(id)=='string')and tostring(event.life_epoch or '')..':'..tostring(id)or nil
        if identity and not source_seen[identity]then
            source_seen[identity]=true;source_order[#source_order+1]=identity
            if #source_order>4096 then source_seen[table.remove(source_order,1)]=nil end
            local cause=event.damage_cause
            local current=type(cause)=='table'and cause.owned==true and cause.current==true
                and cause.life==2 and cause.source=='native_health_extension'
            local element=current and cause.kind==2 and ({[1]='fire',[5]='poison'})[cause.element]or nil
            -- Native kind10 means no damage-source kind. A readable but
            -- unclassified cause is not evidence against a known gas/fire
            -- source. kind0 is Gunfire and must still suppress this fallback.
            if (not current or cause.kind==10 or cause.kind==nil)and type(fact)=='table'then
                if fact.poison then element='poison'elseif fact.fire then element='fire'end
            end
            if element and type(elemental)=='function'then elemental(element,event,proof)end
            if (role.class=='重型'or role.class=='巨型')and type(fact)=='table'
                and type(fact.armor_penetration_max)=='number'and fact.armor_penetration_max>=0
                and fact.armor_penetration_max<=2 then award('level_not_problem',true)end
        end
        -- A mapped robot death is direct evidence for the lower robot tiers.
        -- One seen robot cannot classify the other unknown native counter
        -- increments: require 30/50/60 individually confirmed robot deaths.
        -- Keep this independent proof count when native totals lag one poll;
        -- medals() additionally requires the native streak to reach its tier.
        if role.faction=='automatons' and last_kill_time and now-last_kill_time<=api.streak_window+1e-9 then
            streak_bots=streak_bots+1;medals()
        end
        if role.class=='轻型' and event.same_life==true and state.health_ready==true then
            local before=state.life_light_kills or 0
            state.life_light_kills=before+1
            local earned=math.floor(state.life_light_kills/100)-math.floor(before/100)
            if earned>0 then award('democracy_harvester',true,earned) end
        end
        if role.class~='巨型' then return end
        -- The native observer already identifies local live-to-dead edges;
        -- retaining only this short window also prevents one entity filling
        -- both halves if an adapter happens to repeat a callback.
        id=event.entity_id
        if type(id)~='number' and type(id)~='string' then return end
        for entity,time in pairs(giants)do if now-time>api.double_giant_window+1e-9 then giants[entity]=nil end end
        if giants[id] then return end
        giants[id]=now
        if pending_giant and now-pending_giant.time<=api.double_giant_window+1e-9 then
            pending_giant=nil
            award('double_giant',true)
        else pending_giant={entity=id,time=now} end
    end
    return api
end
