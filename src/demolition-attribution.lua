-- An observed bug-hole closure may be associated with local explosions.
-- Association is deliberately labelled inferred; network ownership is never credit.
local function finite(v)
    return type(v)=='number' and v==v and v>-math.huge and v<math.huge
end
local function position(v)
    if type(v)~='table' or not finite(v.x) or not finite(v.y) or not finite(v.z) then return nil end
    return {x=v.x,y=v.y,z=v.z}
end
local function identity(v)
    if type(v)=='string' and #v>0 and #v<=160 then return v end
    if finite(v) and v>=0 and v%1==0 then return tostring(v) end
end
local function distance(a,b)
    local x,y,z=a.x-b.x,a.y-b.y,a.z-b.z
    return math.sqrt(x*x+y*y+z*z)
end
return function(options)
    options=options or {}
    local wait,lookback,late_window=2.25,2.5,0.35
    local max_radius,max_explosions,max_pending,max_seen=46.5,96,64,2048
    local retention=wait+lookback+late_window
    local explosions,pending,seen={},{},{}
    local mission,last_now,unsafe_until,seen_count,exhausted=options.mission,nil,-math.huge,0,false
    local serial=0
    local api={diagnostics={policy='observed_closure_near_local_explosion_reward_favoring',
        inferred=true,awarded=0,conflicts=0,duplicates=0,rejected=0,overflows=0,
        clock_rewinds=0,pending=0,explosions=0}}
    local function reject(reason)
        api.diagnostics.rejected=api.diagnostics.rejected+1
        api.diagnostics.reason=reason
        return nil,reason
    end
    local function sync_counts()
        api.diagnostics.pending,api.diagnostics.explosions=#pending,#explosions
    end
    local function prune(now)
        local kept={}
        for _,row in ipairs(explosions) do
            if row.time>=now-retention then kept[#kept+1]=row end
        end
        explosions=kept
        sync_counts()
    end
    local function clock(now)
        if not finite(now) or now<0 then return nil,'INVALID_OBSERVED_TIME' end
        if last_now and now<last_now then
            -- Preserve closure identities: rewinding the clock must not permit
            -- a repeated callback to award an already processed hole again.
            explosions,pending={},{}
            unsafe_until=now+lookback
            api.diagnostics.clock_rewinds=api.diagnostics.clock_rewinds+1
            api.diagnostics.reason='CLOCK_REWIND'
        end
        last_now=now
        prune(now)
        return true
    end
    local function event_time(event,now)
        -- The adapter supplies observed HUD time, never a foreign event clock.
        if not finite(event.time) or event.time<0 or event.time>now then return nil end
        return event.time
    end
    local function scope(event)
        if event.mission~=nil and event.mission~=mission then
            if mission~=nil then return nil,'MISSION_MISMATCH' end
            mission=event.mission
        end
        return true
    end
    function api:reset(next_mission)
        explosions,pending,seen={},{},{}
        mission,last_now,unsafe_until,seen_count,exhausted=next_mission,nil,-math.huge,0,false
        serial=0
        self.diagnostics.reason=nil
        sync_counts()
    end
    function api:observe_explosion(event,now)
        local ok,why=clock(now)
        if not ok then return reject(why) end
        if type(event)~='table' then return reject('INVALID_EXPLOSION') end
        ok,why=scope(event);if not ok then return reject(why) end
        local at=event_time(event,now)
        if not at or at<now-retention then return reject('STALE_OR_INVALID_EXPLOSION_TIME') end
        local pos=position(event.position)
        -- An unreadable blast cannot match a hole, but must not discard a
        -- different, valid local blast under the user's reward-favoring rule.
        if not pos then return reject('EXPLOSION_POSITION_UNAVAILABLE')end
        local local_player=event.local_player==true
        local radius=finite(event.radius) and event.radius>0 and math.min(event.radius,max_radius) or nil
        -- BFV's ordinary-hole rule uses at least 9m, including unknown local
        -- explosion types. Foreign/unknown blasts are evidence, never credit.
        local radius_basis=radius and(radius<9 and'minimum_9m'or'supplied')or'default_9m'
        radius=local_player and math.max(9,radius or 9)or(radius or max_radius)
        if #explosions>=max_explosions then
            table.remove(explosions,1)
            self.diagnostics.overflows=self.diagnostics.overflows+1
            self.diagnostics.reason='EXPLOSION_CACHE_OVERFLOW'
        end
        serial=serial+1
        local row={serial=serial,time=at,position=pos,radius=radius,radius_basis=radius_basis,local_player=local_player,
            source=event.local_player==false and 'other_player' or local_player and 'local_player' or 'unknown'}
        explosions[#explosions+1]=row
        sync_counts()
        return true
    end
    function api:observe_closure(event,now)
        local ok,why=clock(now)
        if not ok then return reject(why) end
        if type(event)~='table' then return reject('INVALID_CLOSURE') end
        ok,why=scope(event);if not ok then return reject(why) end
        local id,at,pos=identity(event.id),event_time(event,now),position(event.position)
        if not id or not at or at<now-wait or not pos or event.kind~='bug_hole'
            or not finite(event.stage) or event.stage<=0 or event.stage%1~=0 then
            return reject('INVALID_CLOSURE')
        end
        if seen[id] then
            self.diagnostics.duplicates=self.diagnostics.duplicates+1
            return nil,'CLOSURE_DUPLICATE'
        end
        if exhausted or seen_count>=max_seen then
            exhausted=true
            return reject('CLOSURE_IDENTITY_LIMIT')
        end
        -- Retain both rejected and awarded closures until a mission reset.
        -- Clearing this bounded set would let repeated notifications re-award.
        seen[id],seen_count=true,seen_count+1
        if event.responsible_local==false then return reject('EXPLICIT_OTHER_RESPONSIBILITY') end
        if at<=unsafe_until then return reject('INCOMPLETE_EXPLOSION_WINDOW') end
        if #pending>=max_pending then
            self.diagnostics.overflows=self.diagnostics.overflows+1
            return reject('CLOSURE_PENDING_LIMIT')
        end
        pending[#pending+1]={id=id,time=at,position=pos,stage=event.stage,mission=mission}
        sync_counts()
        return true
    end
    function api:advance(now)
        local ok,why=clock(now)
        if not ok then reject(why);return {} end
        local kept,awards={},{}
        for _,hole in ipairs(pending) do
            local selected,count,conflicts=nil,0,0
            if hole.time>unsafe_until then
                for _,blast in ipairs(explosions) do
                    if blast.time>=hole.time-lookback and blast.time<=hole.time+late_window then
                        local meters=distance(blast.position,hole.position)
                        if meters<=blast.radius then
                            if blast.local_player then
                                count=count+1
                                if not selected or meters/blast.radius<selected.distance/selected.radius then
                                    selected={time=blast.time,distance=meters,radius=blast.radius,
                                        radius_basis=blast.radius_basis}
                                end
                            else conflicts=conflicts+1 end
                        end
                    end
                end
            end
            -- The 2.25s bound is a deadline for missing evidence, not a
            -- mandatory delay. BFV also emits as soon as local coverage exists.
            if selected then
                if conflicts>0 then
                    self.diagnostics.conflicts=self.diagnostics.conflicts+1
                end
                awards[#awards+1]={id=hole.id,mission=hole.mission,time=now,closed_at=hole.time,
                    confidence='inferred',creditor_verified=false,ribbon_eligible=true,
                    evidence={policy=self.diagnostics.policy,closed_stage=hole.stage,
                        closed_at=hole.time,decision_at=now,local_explosion_count=count,
                        selected_explosion=selected,conflict_count=conflicts,wait=wait,
                        lookback=lookback,late_window=late_window}}
                self.diagnostics.awarded=self.diagnostics.awarded+1
                self.diagnostics.reason=nil
            elseif now<hole.time+wait then kept[#kept+1]=hole
            else
                reject(hole.time<=unsafe_until and'INCOMPLETE_EXPLOSION_WINDOW'or'NO_LOCAL_EXPLOSION_COVERAGE')
            end
        end
        pending=kept
        sync_counts()
        return awards
    end
    return api
end
