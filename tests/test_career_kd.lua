local create = dofile(assert(arg[1]))
local baseline = {version=1,kills=351849,deaths=4633,anchor_mod_kills=449,anchor_mod_deaths=2}
local observed = {kills=449,deaths=2,medals={fragrant=true}}
local api = create(baseline)
local totals, reason = api:totals(observed)
assert(totals.kills==351849 and totals.deaths==4633)
assert(string.format('%.2f',totals.kills/totals.deaths)=='75.94')
observed.kills=549;observed.deaths=3
totals=api:totals(observed)
assert(totals.kills==351949 and totals.deaths==4634, 'only post-anchor growth belongs to the career')
assert(api:totals(observed).kills==totals.kills, 'repeat views must not double count')
assert(baseline.kills==351849 and observed.medals.fragrant)
baseline.kills=999 -- The validated anchor must not be changed by a reused caller table.
assert(api:totals(observed).kills==351949)
local restarted=create({version=1,kills=351849,deaths=4633,anchor_mod_kills=449,anchor_mod_deaths=2})
assert(restarted:totals(observed).kills==351949, 'restart preserves one-time anchor')
assert(not create(nil):totals(observed), 'old MOD history must not pretend to be career history')
assert(not api:totals({kills=448,deaths=2}), 'reset local history cannot subtract from a career')
assert(not api:totals({kills=449,deaths=1}))
assert(not create({version=1,kills=0/0,deaths=1,anchor_mod_kills=0,anchor_mod_deaths=0}):totals(observed))
print('PASS: career screenshot baseline, exact75.94, future deltas, restart, no double count, preserved medals, missing/reset/invalid data.')
