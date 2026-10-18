-- Independent regression: reserve-first tactical reload retains a chambered round.
local create = assert(loadfile(assert(arg[1])))()
local price = {id = 'clip', unit_cents = 10}
local meter = create({CLIP = price})
local function sample(rounds, spares, time)
    return {world = 1, mission = 1, player = 2, peer = 'peer', avatar = 3, life = 1,
        time = time, reading = {entity = 4, resource = 'CLIP', reserve_mode = 'magazine',
        state = {capacity = 100, spares = spares, rounds = rounds, working = rounds,
            chambered = 1, chamber_empty = 0, from = 'copy'}}}
end
assert(meter:observe(sample(20, 3, 0)).units == 0)
local middle = meter:observe(sample(0, 2, 100))
local finished = meter:observe(sample(100, 2, 200))
print('retained chamber reserve-first: middle=' .. middle.units .. '/' .. middle.status
    .. ', finished=' .. finished.units .. '/' .. finished.status)
assert(middle.units + finished.units == 20, 'reload discarded 20 rounds; must not charge an additional 100-round magazine')
assert(middle.units == 0 and middle.status == 'unsettled')
assert(finished.units == 20 and finished.status == 'consumed')
print('PASS: reserve-first tactical reload with a retained chamber costs only discarded rounds')
