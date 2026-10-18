local currency = dofile(assert(arg[1]))(dofile(assert(arg[2])))
local state = {sequence=1,kills=12,deaths=3,history_kills=1200,history_deaths=30,
    total_cents=10000,entries={{amount_cents=10000}},ribbons={},mission_medals={}}
local battle = dofile(assert(arg[3]))(state,function() return true end,currency)
local cases = {{'MC','100.00'},{'USD','100.00'},{'CNY','669.21'},
    {'EUR','89.24'},{'GBP','75.64'},{'SEK','996.56'}}
local context = {map_open=false,width=336}
local previous
for _, case in ipairs(cases) do
    local number, code = currency:format(10000,case[1])
    assert(number == case[2] and code == case[1])
    context.currency = case[1]
    local view = battle:snapshot(context)
    assert(view ~= previous and view.stats.bill == case[2] and view.stats.currency == case[1])
    assert(battle:snapshot(context) == view, 'unchanged currency invalidated cached HUD')
    assert(state.total_cents == 10000 and state.entries[1].amount_cents == 10000
        and state.kills == 12 and state.history_kills == 1200)
    previous = view
end
assert(currency:format(1,'MC') == '0.01' and currency:format(0,'SEK') == '0.00')
assert(currency:format(7243128500,'MC') == '72431285.00')
assert(currency:format(10000,'unknown') == '100.00' and currency:code(nil) == 'MC')
-- Convert the accumulated total once: one hundred 0.01-MC entries sum to 6.69 CNY,
-- not 7.00 CNY from rounding each entry.
assert(currency:format(100,'CNY') == '6.69')
assert(not pcall(currency.format,currency,-1,'MC'))
assert(not pcall(currency.format,currency,0/0,'MC'))
assert(not pcall(currency.format,currency,math.huge,'MC'))
local open = io.open
io.open = function() error('currency must never open files during presentation') end
for _=1,10000 do assert(currency:format(10000,'CNY') == '669.21') end
io.open = open
print('PASS: six official-rate conversions, final-total rounding, currency-only cache refresh, unchanged MC entries/history and zero presentation IO.')
