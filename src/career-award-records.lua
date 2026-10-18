-- Lifetime counts of awards this mod actually observed. No store/game access.
-- Persist snapshot() together with the mission state after observe() changes it.
-- A first positive snapshot establishes a baseline; call observe() immediately
-- after the real start_mission reset to count every subsequent earned award.
local LIMIT = 9007199254740991
local function count(value)
    return type(value)=='number' and value>=0 and value<=LIMIT and value%1==0
end
local function medal_count(value)
    if value==true then return 1 end
    return count(value) and value or nil
end
local function copy(value)
    if type(value)~='table' then return value end
    local result={}
    for key,item in pairs(value) do result[key]=copy(item) end
    return result
end
local function mission(state)
    return type(state)=='table' and count(state.sequence) and state.sequence>0
        and (state.mission==true or state.status=='ended')
end

return function(options)
    options=options or {}
    local definitions,seen={},{}
    for _,icon in ipairs(assert(options.icons,'career awards need icon definitions')) do
        assert((icon.kind=='ribbon' or icon.kind=='medal') and type(icon.key)=='string',
            'invalid career award definition')
        local group=icon.kind=='ribbon' and 'ribbons' or 'medals'
        local identity=group..':'..icon.key
        assert(not seen[identity],'duplicate career award definition')
        seen[identity]=true
        definitions[#definitions+1]={key=icon.key,group=group}
    end
    local data={version=1,migrated_legacy=true,totals={ribbons={},medals={}}}
    local saved=options.saved
    if saved~=nil then
        assert(type(saved)=='table' and saved.version==1 and type(saved.totals)=='table',
            'unsupported career award records')
        data=copy(saved)
        data.migrated_legacy=true
        for _,group in ipairs({'ribbons','medals'}) do
            assert(type(data.totals[group])=='table','invalid career award totals')
            for _,value in pairs(data.totals[group]) do assert(count(value),'invalid career award count') end
        end
        if data.checkpoint~=nil then
            local checkpoint=data.checkpoint
            assert(type(checkpoint)=='table' and count(checkpoint.sequence) and checkpoint.sequence>0
                and type(checkpoint.ribbons)=='table' and type(checkpoint.medals)=='table',
                'invalid career award checkpoint')
            for _,value in pairs(checkpoint.ribbons) do assert(count(value),'invalid ribbon checkpoint') end
            for key,value in pairs(checkpoint.medals) do
                local n=medal_count(value);assert(n~=nil,'invalid medal checkpoint')
                checkpoint.medals[key]=n
            end
        end
    end
    for _,item in ipairs(definitions) do
        if data.totals[item.group][item.key]==nil then data.totals[item.group][item.key]=0 end
    end
    local function values(state,item)
        local group=item.group=='ribbons' and state.ribbons or state.mission_medals
        return type(group)=='table' and group[item.key] or nil
    end
    local function new_checkpoint(state)
        local checkpoint={sequence=state.sequence,ribbons={},medals={}}
        for _,item in ipairs(definitions) do
            checkpoint[item.group][item.key]=0
        end
        return checkpoint
    end
    -- The old store proves at most one last mission plus historical unlocks.
    -- A historical true and a true in the last mission may be the same award:
    -- use max(1), never add those two booleans. No kills-based reconstruction.
    if saved==nil then
        local legacy=type(options.legacy)=='table' and options.legacy or {}
        local last=legacy.last_mission
        local historical=type(legacy.combat_history)=='table' and legacy.combat_history.medals or nil
        if mission(last) then data.checkpoint=new_checkpoint(last) end
        for _,item in ipairs(definitions) do
            local total=0
            if item.group=='medals' and type(historical)=='table' then total=medal_count(historical[item.key]) or 0 end
            if item.group=='medals' and mission(last) and type(last.medals)=='table' then
                total=math.max(total,medal_count(last.medals[item.key]) or 0)
            end
            if data.checkpoint then
                local value=values(last,item)
                if item.group=='ribbons' and count(value) then
                    total=value
                    data.checkpoint.ribbons[item.key]=value
                elseif item.group=='medals' and medal_count(value) then
                    local n=medal_count(value)
                    total=math.max(total,n)
                    data.checkpoint.medals[item.key]=n
                end
            end
            data.totals[item.group][item.key]=total
        end
    end
    local api={version=1,revision=0}
    local function sample(state,suppress)
        if not mission(state) then return false,'no_mission' end
        local checkpoint=data.checkpoint
        if checkpoint and state.sequence<checkpoint.sequence then return false,'older_sequence' end
        local changed=false
        if not checkpoint or state.sequence>checkpoint.sequence then
            checkpoint=new_checkpoint(state)
            data.checkpoint=checkpoint
            changed,suppress=true,true
        end
        local earned=0
        for _,item in ipairs(definitions) do
            local value=values(state,item)
            local previous=checkpoint[item.group][item.key]
            local delta=0
            if item.group=='ribbons' and count(value) then
                if previous==nil or value>previous then
                    if not suppress and previous~=nil then delta=value-previous end
                    checkpoint.ribbons[item.key]=value
                    changed=true
                end
            elseif item.group=='medals' then
                local n=medal_count(value)
                previous=medal_count(previous) or 0
                if n and n>previous then
                    if not suppress then delta=n-previous end
                    checkpoint.medals[item.key]=n
                    changed=true
                end
            end
            if delta>0 then
                local total=data.totals[item.group][item.key]
                assert(total<=LIMIT-delta,'career award total exceeds exact integer range')
                data.totals[item.group][item.key]=total+delta
                earned=earned+delta
            end
        end
        if changed then api.revision=api.revision+1 end
        return changed,suppress and 'baseline' or 'observed',earned
    end
    function api:observe(state) return sample(state,false) end
    function api:baseline(state) return sample(state,true) end
    function api:snapshot() return copy(data) end
    return api
end
