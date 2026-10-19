-- Fixed build-time rates. Converts the final legacy MC cent total for presentation only.
-- No network, game reads, store writes, or per-entry rounding.
return function(snapshot)
    local rates = {}
    for _, code in ipairs({'SC', 'USD', 'CNY', 'EUR', 'GBP', 'SEK'}) do
        local rate = snapshot.rates[code]
        assert(type(rate) == 'number' and rate > 0 and rate < math.huge, 'missing currency rate: ' .. code)
        rates[code] = rate
    end
    assert(snapshot.rates.MC == 1 and rates.USD == 1 and snapshot.mc_usd_rate == 1)
    -- A mod presentation rule, unrelated to the real-money Super Credits store.
    assert(rates.SC == 1, 'SC presentation requires 1 SC = 1 legacy MC / USD')
    local api = {as_of = snapshot.as_of, requested_date = snapshot.requested_date}
    function api:code(value) return rates[value] and value or 'SC' end
    function api:format(cents, code)
        cents = cents or 0
        assert(type(cents) == 'number' and cents >= 0 and cents < math.huge and cents % 1 == 0,
            'currency expects a nonnegative integer MC cent total')
        code = self:code(code)
        local value = cents / 100 * rates[code]
        -- Round only at presentation; positive fractional charges must remain visible.
        return value > 0 and value < 0.01 and '<0.01' or string.format('%.2f', value), code
    end
    return api
end
