-- Retained-match period totals and independent, time-stamped career KD points.
-- No game/store access. Career checkpoints remain independent of match totals.
local LIMIT=9007199254740991
local HOUR,DAY=3600,86400
local KEEP_HOURS=31*24
local PERIODS={{key='24h',seconds=DAY},{key='7d',seconds=7*DAY},{key='30d',seconds=30*DAY}}
local function count(value)
    return type(value)=='number' and value>=0 and value<=LIMIT and value%1==0
end
local function time(value)
    return type(value)=='number' and value>=0 and value<=LIMIT and value or nil
end
local function copy(value)
    if type(value)~='table' then return value end
    local result={};for key,item in pairs(value)do result[key]=copy(item)end;return result
end
local function point(at,kills,deaths)return {at=at,kills=kills,deaths=deaths}end
local function career(state)
    if type(state)=='table' and state.history_reason=='CAREER_BASELINE_PLUS_OBSERVED_DELTAS'
        and count(state.history_kills) and count(state.history_deaths) then
        return {kills=state.history_kills,deaths=state.history_deaths,
            kd=state.history_kills/math.max(1,state.history_deaths)}
    end
end
local function valid_point(value,hour)
    return type(value)=='table' and time(value.at) and math.floor(value.at/HOUR)==hour
        and count(value.kills) and count(value.deaths)
end

return function(options)
    options=options or {}
    local keys={ribbons={},medals={}}
    for _,icon in ipairs(assert(options.icons,'period summary needs award definitions'))do
        assert((icon.kind=='ribbon' or icon.kind=='medal') and type(icon.key)=='string',
            'invalid period summary award definition')
        keys[icon.kind=='medal' and 'medals' or 'ribbons'][icon.key]=true
    end
    local data={version=1,buckets={}}
    if options.saved~=nil then
        local saved=options.saved
        assert(type(saved)=='table' and saved.version==1 and type(saved.buckets)=='table'
            and #saved.buckets<=750,'unsupported career KD checkpoints')
        local previous=-1
        for _,bucket in ipairs(saved.buckets)do
            assert(type(bucket)=='table' and count(bucket.hour) and bucket.hour>previous
                and valid_point(bucket.first,bucket.hour) and valid_point(bucket.last,bucket.hour)
                and bucket.first.at<=bucket.last.at,'invalid career KD checkpoint bucket')
            data.buckets[#data.buckets+1]={hour=bucket.hour,
                first=point(bucket.first.at,bucket.first.kills,bucket.first.deaths),
                last=point(bucket.last.at,bucket.last.kills,bucket.last.deaths)}
            previous=bucket.hour
        end
    end
    local api={version=1,revision=0,checkpoint_limit=1500,retention_seconds=31*DAY,max_gap_seconds=HOUR}
    local aggregate_entries,aggregate_revision,aggregate_cache
    local AGGREGATE_FIELDS={'missions','kills','deaths','known_kills','known_deaths','missing_kills',
        'missing_deaths','unknown_time','patriotic_bill','ribbons','medals','overflow'}
    local function now(value)
        if value~=nil then return time(value) end
        if type(options.clock)=='function' then
            local ok,result=pcall(options.clock)
            if ok then return time(result) end
        end
    end
    function api:observe(state,at)
        local current=career(state)
        if not current then return false,'career_unavailable' end
        at=now(at)
        if not at then return false,'clock_unavailable' end
        local buckets=data.buckets
        local latest=buckets[#buckets]
        if latest and at<latest.last.at then return false,'clock_rollback' end
        local hour=math.floor(at/HOUR)
        if latest and hour==latest.hour then
            if current.kills==latest.last.kills and current.deaths==latest.last.deaths then
                return false,'unchanged'
            end
            latest.last=point(at,current.kills,current.deaths)
            -- os.time resolves to seconds; retain the latest observation when
            -- several changes share the same first timestamp.
            if latest.first.at==at then latest.first=copy(latest.last) end
        else
            local value=point(at,current.kills,current.deaths)
            buckets[#buckets+1]={hour=hour,first=value,last=copy(value)}
        end
        local cutoff=hour-KEEP_HOURS
        while buckets[1] and buckets[1].hour<cutoff do table.remove(buckets,1)end
        -- At most 745 hourly buckets including the current partial hour.
        assert(#buckets*2<=self.checkpoint_limit,'career checkpoint retention exceeded')
        self.revision=self.revision+1
        return true,'observed'
    end
    function api:snapshot()return copy(data)end
    local function baseline(target)
        local candidate
        for index=#data.buckets,1,-1 do
            local bucket=data.buckets[index]
            if bucket.first.at<=target then
                candidate=bucket.last.at<=target and bucket.last or bucket.first
                break
            end
        end
        if not candidate then return nil,'baseline_unavailable' end
        local gap=target-candidate.at
        if gap>HOUR then return nil,'baseline_too_old',gap end
        local value=copy(candidate);value.kd=value.kills/math.max(1,value.deaths)
        return value,'available',gap
    end
    local function first_in_period(target,at)
        -- An offline gap at the cutoff must not hide genuine observations later
        -- in the period. Keep their actual timestamps instead of inventing a
        -- checkpoint at midnight, the cutoff, or from match-only totals.
        for _,bucket in ipairs(data.buckets)do
            for _,value in ipairs({bucket.first,bucket.last})do
                if value.at>=target and value.at<=at then
                    local prior=copy(value);prior.kd=prior.kills/math.max(1,prior.deaths)
                    return prior
                end
            end
        end
    end
    local function add(total,value)
        if total==nil or total>LIMIT-value then return nil end
        return total+value
    end
    local function series(prior,at,current)
        if not prior then return nil end
        local points={}
        local function insert(value)
            if value.at<prior.at or value.at>at then return end
            local item={at=value.at,kd=value.kd or value.kills/math.max(1,value.deaths)}
            if points[#points] and points[#points].at==item.at then points[#points]=item
            else points[#points+1]=item end
        end
        insert(prior)
        for _,bucket in ipairs(data.buckets)do insert(bucket.first);insert(bucket.last)end
        -- The supplied current state is the same confirmed state used by observe.
        insert({at=at,kd=current.kd})
        if #points<=24 then return points end
        local reduced={}
        for index=0,23 do reduced[#reduced+1]=points[1+math.floor(index*(#points-1)/23)]end
        return reduced
    end
    function api:summarize(entries,current_state,at,entries_revision)
        at=now(at)
        -- Production supplies the retained history revision. Old callers without
        -- one may mutate entries in place, so they deliberately stay uncached.
        local cached_history=count(entries_revision)
        if cached_history and(entries~=aggregate_entries or entries_revision~=aggregate_revision)then
            aggregate_entries,aggregate_revision,aggregate_cache=entries,entries_revision,{}
        elseif not cached_history then
            aggregate_entries,aggregate_revision,aggregate_cache=nil,nil,nil
        end
        local current=career(current_state)
        local result={version=1,as_of=at,current=current,periods={}}
        local ranges={{key='all'}}
        for _,period in ipairs(PERIODS)do ranges[#ranges+1]=period end
        for _,period in ipairs(ranges)do
            local all=period.key=='all'
            local row={key=period.key,seconds=period.seconds,from_at=not all and at and at-period.seconds or nil,
                to_at=at,missions=0,kills=0,deaths=0,known_kills=0,known_deaths=0,
                missing_kills=0,missing_deaths=0,unknown_time=0,
                patriotic_bill={version=1,total_cents=0,recorded_missions=0,missing_missions=0,entries={}},
                ribbons={},medals={},overflow={ribbons={},medals={}},
                career={target_at=not all and at and at-period.seconds or nil,current_kd=current and current.kd}}
            local comparison=row.career
            local bill_items={}
            if not at then comparison.reason='clock_unavailable'
            elseif not current then comparison.reason='career_unavailable'
            else
                local prior,reason,gap
                if all then
                    local oldest=data.buckets[1] and data.buckets[1].first
                    if oldest and oldest.at<=at then
                        prior=copy(oldest);prior.kd=prior.kills/math.max(1,prior.deaths)
                        comparison.target_at=prior.at;reason='available';gap=0
                    else reason='baseline_unavailable' end
                else
                    prior,reason,gap=baseline(comparison.target_at)
                    if not prior then
                        prior=first_in_period(comparison.target_at,at)
                        if prior then reason='available_partial';comparison.partial=true;gap=nil end
                    end
                end
                comparison.baseline,comparison.reason,comparison.gap_seconds=prior,reason,gap
                if prior then comparison.delta=current.kd-prior.kd;comparison.series=series(prior,at,current) end
            end
            local cached=cached_history and aggregate_cache[period.key]
            local reusable=cached and(all or at==nil and cached.at==nil
                or at and cached.at and at>=cached.at and(not cached.until_at
                    or at<cached.until_at or cached.inclusive and at==cached.until_at))
            if reusable then
                for _,field in ipairs(AGGREGATE_FIELDS)do row[field]=copy(cached.values[field])end
            else
            local until_at,inclusive
            for _,entry in ipairs(type(entries)=='table' and entries or {})do
                if type(entry)=='table' and (entry.status=='ended' or entry.status=='interrupted') then
                    local ended=time(entry.ended_at)
                    if not all and at and ended then
                        local edge,include
                        if ended>at then edge,include=ended,false
                        elseif ended+period.seconds>=at then edge,include=ended+period.seconds,true end
                        if edge and(not until_at or edge<until_at or edge==until_at and not include)then
                            until_at,inclusive=edge,include
                        end
                    end
                    if not ended then row.unknown_time=row.unknown_time+1 end
                    if all or (ended and at and ended>=row.from_at and ended<=at) then
                        row.missions=row.missions+1
                        local bill=row.patriotic_bill
                        local source=entry.patriotic_bill
                        if type(source)=='table'and source.version==1 and count(source.total_cents)
                            and type(source.entries)=='table'then
                            bill.recorded_missions=bill.recorded_missions+1
                            bill.total_cents=add(bill.total_cents,source.total_cents)
                            if bill.total_cents==nil then bill.overflow=true end
                            for _,item in ipairs(source.entries)do
                                if type(item)=='table'and type(item.key)=='string'and type(item.name)=='string'
                                    and count(item.amount_cents)then
                                    local key=item.key;local current=bill_items[key]
                                    if not current then
                                        if #bill.entries>=256 then key='other';current=bill_items[key]end
                                        if not current then current={key=key,name=key=='other'and'其他已记录费用'or item.name,amount_cents=0}
                                            bill_items[key]=current;bill.entries[#bill.entries+1]=current end
                                    end
                                    current.amount_cents=add(current.amount_cents,item.amount_cents)
                                    if current.amount_cents==nil then bill.overflow=true end
                                end
                            end
                        else bill.missing_missions=bill.missing_missions+1 end
                        for _,key in ipairs({'kills','deaths'})do
                            if count(entry[key])then
                                row['known_'..key]=add(row['known_'..key],entry[key])
                                if row['known_'..key]==nil then row.overflow[key]=true end
                            else row['missing_'..key]=row['missing_'..key]+1 end
                        end
                        for _,group in ipairs({'ribbons','medals'})do
                            if type(entry[group])=='table' then
                                for key in pairs(keys[group])do
                                    local value=entry[group][key]
                                    if count(value) and value>0 and not row.overflow[group][key]then
                                        local total=add(row[group][key] or 0,value)
                                        row[group][key]=total
                                        if total==nil then row.overflow[group][key]=true end
                                    end
                                end
                            end
                        end
                    end
                end
            end
            row.kills=row.missing_kills==0 and row.known_kills or nil
            row.deaths=row.missing_deaths==0 and row.known_deaths or nil
            table.sort(row.patriotic_bill.entries,function(a,b)
                local av,bv=a.amount_cents or -1,b.amount_cents or -1
                return av>bv or(av==bv and a.key<b.key)
            end)
            if cached_history then
                local values={}
                for _,field in ipairs(AGGREGATE_FIELDS)do values[field]=copy(row[field])end
                aggregate_cache[period.key]={values=values,at=at,until_at=until_at,inclusive=inclusive}
            end
            end
            if all then result.all=row else result.periods[#result.periods+1]=row end
        end
        return result
    end
    return api
end
