-- A user-supplied career total is an anchor, not the MOD's old local history.
-- This module performs no game reads and never changes either input.
local function count(n)
    return type(n) == 'number' and n >= 0 and n < math.huge and n % 1 == 0
end
return function(baseline)
    local anchor
    if type(baseline) == 'table' and baseline.version == 1
        and count(baseline.kills) and count(baseline.deaths)
        and count(baseline.anchor_mod_kills) and count(baseline.anchor_mod_deaths) then
        anchor = {kills = baseline.kills, deaths = baseline.deaths,
            local_kills = baseline.anchor_mod_kills, local_deaths = baseline.anchor_mod_deaths}
    end
    local api = {}
    function api:totals(observed)
        if not anchor then return nil, 'CAREER_BASELINE_UNAVAILABLE' end
        if type(observed) ~= 'table' or not count(observed.kills) or not count(observed.deaths)
            or observed.kills < anchor.local_kills or observed.deaths < anchor.local_deaths then
            return nil, 'CAREER_LOCAL_HISTORY_RESET'
        end
        return {kills = anchor.kills + observed.kills - anchor.local_kills,
            deaths = anchor.deaths + observed.deaths - anchor.local_deaths},
            'CAREER_BASELINE_PLUS_OBSERVED_DELTAS'
    end
    return api
end
