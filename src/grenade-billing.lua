-- Disposable throwables only. Native inventory decrements, never buttons or explosions.
local KEYS = {'world', 'mission', 'player', 'peer', 'avatar', 'life'}
local function count(v, maximum)
    return type(v)=='number' and v>=0 and v<=maximum and v%1==0
end
local function identity(v) return type(v)=='string' and v~='' or count(v,9007199254740991) end
return function(prices)
    local previous
    local api={}
    function api:reset() previous=nil end
    function api:observe(sample)
        local result={ready=false,units=0,cents=0,status='missing'}
        if type(sample)~='table' then self:reset();return result end
        for _,key in ipairs(KEYS) do
            if not identity(sample[key]) then self:reset();result.status='identity';return result end
        end
        local reading=sample.reading
        local price=type(reading)=='table' and prices[reading.resource]
        if not price or not count(reading.count,10000) or not count(sample.time,9007199254740991) then
            self:reset();return result
        end
        local same=previous~=nil and previous.resource==reading.resource
            and sample.time>=previous.time and sample.time-previous.time<=500
        for _,key in ipairs(KEYS) do if not previous or previous[key]~=sample[key] then same=false end end
        result.ready,result.price=true,price
        result.status=not same and 'baseline' or reading.count<previous.count and 'consumed'
            or reading.count>previous.count and 'refilled' or 'unchanged'
        if same then result.units=math.max(0,previous.count-reading.count) end
        result.cents=result.units*price.unit_cents
        previous={resource=reading.resource,count=reading.count,time=sample.time}
        for _,key in ipairs(KEYS) do previous[key]=sample[key] end
        return result
    end
    return api
end
