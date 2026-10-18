-- Per-mission snapshots only. No game/store access and no lifetime totals.
-- entries() is a retained newest-first view; callers must treat it as read-only.
-- Persist snapshot() when revision changes. A deleted sequence stays deleted.
local LIMIT=9007199254740991
local MAX_ENTRIES=500
local CRUSH_POLICY='confirmed_player_vehicle_parent_source_kills_as_crush'
local function count(value)
    return type(value)=='number' and value>=0 and value<=LIMIT and value%1==0
end
local function sequence(value)return count(value) and value>0 end
local function sequence_key(value)return string.format('%.0f',value)end
local function timestamp(value)
    return type(value)=='number' and value>=0 and value<math.huge and value or nil
end
local function copy(value)
    if type(value)~='table' then return value end
    local result={};for key,item in pairs(value)do result[key]=copy(item)end;return result
end
local function mission(state)
    return type(state)=='table' and sequence(state.sequence)
        and (state.mission==true or state.status=='ended')
end
local function totals(state)
    if state.history_reason=='CAREER_BASELINE_PLUS_OBSERVED_DELTAS'
        and count(state.history_kills) and count(state.history_deaths) then
        return {kills=state.history_kills,deaths=state.history_deaths}
    end
end
local function start(state)
    return state.mission==true and state.status~='ended' and state.stats_ready==false
        and (state.kills==nil or state.kills==0) and (state.deaths==nil or state.deaths==0)
end

-- Store the amounts that were actually charged, without retaining native
-- pointers or guessing amounts for older matches. Repeated call rows are
-- grouped by their original price/event identity for a bounded Career view.
local function bill_snapshot(state,legacy)
    if type(state)~='table' or (not legacy and state.billing_enabled~=true)
        or(legacy and state.billing_enabled==false)
        or not count(state.total_cents) or type(state.entries)~='table' then return nil end
    local out={version=1,total_cents=state.total_cents,entries={}}
    local grouped,total={},0
    for _,source in ipairs(state.entries)do
        if type(source)=='table' and count(source.amount_cents) and source.amount_cents>0 then
            if total>LIMIT-source.amount_cents then return nil end
            total=total+source.amount_cents
            local event=type(source.event)=='string'and source.event:sub(1,64)or'charge'
            local price=type(source.price_id)=='string'and source.price_id:sub(1,128)or''
            local name=type(source.name)=='string'and source.name~=''and source.name or'其他已记录费用'
            local key=event..':'..(price~=''and price or name)
            local row=grouped[key]
            if not row then
                if #out.entries>=256 then key='other';name='其他已记录费用';row=grouped[key]end
                if not row then row={key=key,event=event,price_id=price,name=name,amount_cents=0}
                    grouped[key]=row;out.entries[#out.entries+1]=row end
            end
            row.amount_cents=row.amount_cents+source.amount_cents
        end
    end
    if total>out.total_cents then return nil end
    if total<out.total_cents then
        out.entries[#out.entries+1]={key='unitemized',event='charge',name='其他已记录费用',
            amount_cents=out.total_cents-total}
    end
    table.sort(out.entries,function(a,b)
        return a.amount_cents>b.amount_cents or(a.amount_cents==b.amount_cents and a.key<b.key)
    end)
    return out
end
local function same_bill(a,b)
    if not a or a.total_cents~=b.total_cents or #a.entries~=#b.entries then return false end
    for i,row in ipairs(b.entries)do local previous=a.entries[i]
        if previous.key~=row.key or previous.name~=row.name or previous.amount_cents~=row.amount_cents then return false end
    end
    return true
end

return function(options)
    options=options or {}
    local keys={ribbons={},medals={}}
    for _,icon in ipairs(assert(options.icons,'mission history needs icon definitions'))do
        assert((icon.kind=='ribbon' or icon.kind=='medal') and type(icon.key)=='string',
            'invalid mission history award definition')
        local group=icon.kind=='ribbon' and 'ribbons' or 'medals'
        assert(not keys[group][icon.key],'duplicate mission history award definition')
        keys[group][icon.key]=true
    end
    local data={version=1,entries={},deleted={},max_sequence=0}
    local by_sequence,highest={},0
    local api={version=1,revision=0,limit=MAX_ENTRIES}
    local function clock(value)
        if value~=nil then return timestamp(value) end
        if type(options.clock)=='function' then
            local ok,result=pcall(options.clock)
            if ok then return timestamp(result) end
        end
    end
    local function update(entry,state)
        local changed=false
        local bill=bill_snapshot(state)
        if bill and (not entry.patriotic_bill or bill.total_cents>=entry.patriotic_bill.total_cents)
            and not same_bill(entry.patriotic_bill,bill)then entry.patriotic_bill=bill;changed=true end
        if state.mission==true and state.crush_policy==CRUSH_POLICY and entry.crush_policy~=CRUSH_POLICY then
            entry.crush_policy=CRUSH_POLICY;changed=true
        end
        for _,key in ipairs({'kills','deaths'})do
            local value=state[key]
            if count(value) and (entry[key]==nil or value>entry[key])then
                entry[key]=value;changed=true
            end
        end
        if type(state.ribbons)=='table' then
            for key in pairs(keys.ribbons)do
                local value=state.ribbons[key]
                if count(value) and value>0 and value>(entry.ribbons[key] or 0)then
                    entry.ribbons[key]=value;changed=true
                end
            end
        end
        if type(state.mission_medals)=='table' then
            for key in pairs(keys.medals)do
                local value=state.mission_medals[key]
                value=value==true and 1 or value
                if count(value) and value>(entry.medals[key] or 0) then
                    entry.medals[key]=value;changed=true
                end
            end
        end
        return changed
    end
    local function validate_entry(entry)
        assert(type(entry)=='table' and sequence(entry.sequence),'invalid mission history sequence')
        assert(entry.status=='active' or entry.status=='ended' or entry.status=='interrupted',
            'invalid mission history status')
        for _,key in ipairs({'kills','deaths'})do
            assert(entry[key]==nil or count(entry[key]),'invalid mission history statistic')
        end
        for _,key in ipairs({'started_at','ended_at'})do
            assert(entry[key]==nil or timestamp(entry[key]),'invalid mission history timestamp')
        end
        for _,group in ipairs({'ribbons','medals'})do
            assert(type(entry[group])=='table','invalid mission history awards')
            for key,value in pairs(entry[group])do
                assert(type(key)=='string' and count(value) and value>0,'invalid mission history award count')
            end
        end
        for _,key in ipairs({'history_before','history_after'})do
            local value=entry[key]
            assert(value==nil or (type(value)=='table' and count(value.kills) and count(value.deaths)),
                'invalid mission history career baseline')
        end
        local bill=entry.patriotic_bill
        if bill~=nil then
            assert(type(bill)=='table'and bill.version==1 and count(bill.total_cents)
                and type(bill.entries)=='table'and #bill.entries<=258,'invalid mission patriotic bill')
            local total=0
            for _,row in ipairs(bill.entries)do
                assert(type(row)=='table'and type(row.key)=='string'and type(row.name)=='string'
                    and count(row.amount_cents)and total<=LIMIT-row.amount_cents,'invalid mission bill item')
                total=total+row.amount_cents
            end
            assert(total==bill.total_cents,'mission bill items do not match total')
        end
    end
    if options.saved~=nil then
        local saved=options.saved
        assert(type(saved)=='table' and saved.version==1 and type(saved.entries)=='table'
            and type(saved.deleted)=='table','unsupported mission history records')
        assert(saved.max_sequence==nil or count(saved.max_sequence),'invalid mission history maximum sequence')
        highest=saved.max_sequence or 0
        local deleted={}
        for key,value in pairs(saved.deleted)do
            local seq=tonumber(key)
            assert(value==true and sequence(seq),'invalid mission history deletion')
            deleted[sequence_key(seq)]=true;highest=math.max(highest,seq)
        end
        local seen={}
        for _,original in ipairs(saved.entries)do
            validate_entry(original)
            local entry=copy(original)
            assert(not seen[entry.sequence],'duplicate saved mission sequence')
            seen[entry.sequence]=true;highest=math.max(highest,entry.sequence)
            if not deleted[sequence_key(entry.sequence)] then
                if entry.status=='active' then
                    -- We know the process stopped, not when/how the mission ended.
                    entry.status='interrupted';entry.ended_at=nil
                    entry.history_after=nil;api.revision=1
                end
                data.entries[#data.entries+1]=entry;by_sequence[entry.sequence]=entry
            else api.revision=1 end
        end
        table.sort(data.entries,function(a,b)return a.sequence>b.sequence end)
        -- The high water mark rejects every older replay, including deletions.
        -- Only deleting the highest sequence still needs an explicit tombstone.
        local latest=sequence_key(highest)
        if deleted[latest]then data.deleted[latest]=true end
        for key in pairs(deleted)do if key~=latest then api.revision=1 end end
        if saved.max_sequence~=highest then api.revision=1 end
    else
        local legacy=type(options.legacy)=='table' and options.legacy or {}
        local last=legacy.last_mission or legacy
        if mission(last)then
            local entry={sequence=last.sequence,status=last.status=='ended' and 'ended' or 'interrupted',
                ribbons={},medals={}}
            update(entry,last)
            -- Old last_mission proves one snapshot, not a start time or KD delta.
            data.entries[1]=entry;by_sequence[entry.sequence]=entry
            highest=entry.sequence;api.revision=1
        end
    end
    data.max_sequence=highest
    -- The previous release retained only its most recent full bill. Import
    -- that exact matching sequence once; every other older bill stays absent.
    do
        local legacy=type(options.legacy)=='table'and(options.legacy.last_mission or options.legacy)or nil
        local entry=legacy and by_sequence[legacy.sequence]
        if entry and entry.patriotic_bill==nil then
            local bill=bill_snapshot(legacy,true)
            if bill then entry.patriotic_bill=bill;api.revision=api.revision+1 end
        end
    end
    function api:observe(state,time)
        if not mission(state)then return false,'no_mission' end
        local seq=state.sequence
        if data.deleted[sequence_key(seq)]then return false,'deleted' end
        if seq<highest then return false,'older_sequence' end
        local entry=by_sequence[seq]
        -- Saved interrupted records cannot be mistaken for resumed missions on
        -- startup. A new start_mission must allocate the next real sequence.
        if entry and entry.status=='interrupted' then return false,'interrupted' end
        if entry and entry.status=='ended' and state.status~='ended' then return false,'ended' end
        local changed=false
        if not entry then
            if #data.entries>=MAX_ENTRIES then return false,'limit' end
            for _,previous in ipairs(data.entries)do
                if previous.status=='active' then
                    previous.status='interrupted';previous.ended_at=nil
                    previous.history_after=nil
                end
            end
            entry={sequence=seq,status='active',ribbons={},medals={}}
            if start(state)then entry.started_at=clock(time);entry.history_before=totals(state)end
            by_sequence[seq]=entry;highest=seq;data.max_sequence=seq;data.deleted={}
            table.insert(data.entries,1,entry);changed=true
        end
        changed=update(entry,state) or changed
        if state.status=='ended' and entry.status~='ended' then
            entry.status='ended';entry.ended_at=clock(time);changed=true
            -- The first end observation owns this endpoint. Later ship/page
            -- synchronizations change the global career anchor, not this match.
            -- An unavailable endpoint stays unknown instead of being backfilled.
            local before,after=entry.history_before,totals(state)
            if before and after and after.kills>=before.kills and after.deaths>=before.deaths then
                entry.history_after=after
            end
        end
        if changed then self.revision=self.revision+1 end
        return changed,changed and 'observed' or 'unchanged'
    end
    function api:remove(seq)
        if not sequence(seq) or not by_sequence[seq]then return false,'not_found' end
        for index,entry in ipairs(data.entries)do
            if entry.sequence==seq then table.remove(data.entries,index);break end
        end
        by_sequence[seq]=nil
        if seq==highest then data.deleted[sequence_key(seq)]=true end
        self.revision=self.revision+1
        return true,'deleted'
    end
    function api:entries()return data.entries end
    function api:snapshot()return copy(data)end
    return api
end
