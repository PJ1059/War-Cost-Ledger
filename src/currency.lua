-- Fixed build-time rates. Converts the final MC total for presentation only.
-- No network, game reads, store writes, or per-entry rounding.
return function(snapshot)
    local rates = {}
    for _, code in ipairs({'MC', 'USD', 'CNY', 'EUR', 'GBP', 'SEK'}) do
        local rate = snapshot.rates[code]
        assert(type(rate) == 'number' and rate > 0 and rate < math.huge, 'missing currency rate: ' .. code)
        rates[code] = rate
    end
    assert(rates.MC == 1 and rates.USD == 1 and snapshot.mc_usd_rate == 1)
    local api = {as_of = snapshot.as_of, requested_date = snapshot.requested_date}
    function api:code(value) return rates[value] and value or 'MC' end
    function api:format(cents, code)
        cents = cents or 0
        assert(type(cents) == 'number' and cents >= 0 and cents < math.huge and cents % 1 == 0,
            'currency expects a nonnegative integer MC cent total')
        code = self:code(code)
        return string.format('%.2f', cents / 100 * rates[code]), code
    end
    return api
end
