local create = dofile(assert(arg[1]))
local state = {sequence = 1, kills = 238, deaths = 2, history_kills = 15600, history_deaths = 348,
    total_cents = 7243128500, ribbons = {}, mission_medals = {}, medals = {fragrant = true}}
local visible = true
local hud = create(state, function() return visible end)
assert(#hud.icons == 52 and hud.native_binding == false and hud.artwork == 'placeholders')
local seen = {}
for _, icon in ipairs(hud.icons) do assert(not seen[icon.id]); seen[icon.id] = true end
local crush_icon
for _,icon in ipairs(hud.icons)do if icon.id=='R12'then crush_icon=icon end end
assert(crush_icon and crush_icon.key=='crush'and crush_icon.name=='碾压'and crush_icon.kind=='ribbon')
local closed = hud:snapshot({map_open = false})
assert(closed.stats.kills == '238' and closed.stats.kd == '119.00' and closed.stats.history_kd == '44.83')
assert(closed.stats.bill == '72431285.00' and #closed.medals == 0 and #closed.ribbons == 0)
assert(closed.height == 52 and closed.task_offset_y == 60)
assert(hud:snapshot({map_open = false}) == closed, 'unchanged data must reuse the retained view')
assert(#closed.medals == 0, 'a historical unlock must not become a current-mission medal')
state.mission_medals.democracy_undying = true
state.mission_medals.freedom_in_veins = true
state.mission_medals.air_expert = true
state.ribbons.air, state.ribbons.heavy, state.ribbons.melee = 36, 16, 10
closed = hud:snapshot({map_open = false})
assert(#closed.medals == 3 and #closed.ribbons == 0)
local opened = hud:snapshot({map_open = true})
assert(#opened.medals == 3 and #opened.ribbons == 3 and opened.ribbons[1].count == 36)
assert(opened.task_offset_y > closed.task_offset_y, 'map ribbons must reserve real height above ALL tasks')
assert(hud:snapshot({map_open = false}).task_offset_y == closed.task_offset_y,
    'closing the map must return the complete ribbon space')
-- Status values are known synthetic effective-period totals, not a native game feed.
local counts = {air = 36, heavy = 16, giant = 6, demolition = 12, melee = 10, ignite = 82,
    firepower = 5, poison=12, status_fire = 8, status_poison = 12}
state.ribbons = counts
for _, icon in ipairs(hud.icons) do if icon.kind == 'medal' then state.mission_medals[icon.key] = true end end
local samples = {}
for _, width in ipairs({160, 224, 300, 336, 480}) do
    local pair = {width = width, closed = hud:snapshot({map_open = false, width = width}),
        opened = hud:snapshot({map_open = true, width = width})}
    for _, view in ipairs({pair.closed, pair.opened}) do
        assert(view.task_offset_y == view.height + 8)
        for _, row in ipairs({view.medals, view.ribbons}) do
            for _, item in ipairs(row) do
                assert(item.x >= 0 and item.y >= 0 and item.x + item.width <= view.width)
                assert(item.y + item.height <= view.height and item.placeholder == true)
                if item.count then assert(item.count == counts[item.key]) end
            end
        end
        for _, medal in ipairs(view.medals) do assert(medal.x + medal.width <= view.stats.x - 8) end
    end
    assert(#pair.closed.medals == 12 and #pair.closed.ribbons == 0 and #pair.opened.ribbons == 8)
    assert(pair.opened.ribbons[6].key == 'ignite' and pair.opened.ribbons[6].name == '燃烧击杀')
    assert(pair.opened.ribbons[8].key == 'poison' and pair.opened.ribbons[8].name == '毒气击杀')
    for _,r in ipairs(pair.opened.ribbons)do assert(r.id~='R08'and r.key~='status_poison')end
    samples[#samples + 1] = pair
end
state.ribbons.crush=154
local crush_view=hud:snapshot({map_open=true})
local crush_shown
for _,item in ipairs(crush_view.ribbons)do if item.id=='R12'then crush_shown=item end end
assert(crush_shown and crush_shown.name=='碾压'and crush_shown.count==154)
state.ribbons.crush=nil
visible = false
local hidden = hud:snapshot({map_open = true})
assert(not hidden.shown and hidden.height == 0 and hidden.task_offset_y == 0)
assert(#hidden.medals == 0 and #hidden.ribbons == 0)
assert(state.ribbons.ignite == 82, 'hiding the display must not change the ledger')
assert(state.ribbons.status_fire == 8 and state.ribbons.status_poison == 12)
visible = true
state.sequence, state.ribbons, state.mission_medals = 2, {}, {}
local reset = hud:snapshot({map_open = true})
assert(#reset.medals == 0 and #reset.ribbons == 0 and reset.task_offset_y == 60)
state.ribbons = nil
state.mission_medals.status_fire = 99
assert(#hud:snapshot({map_open = true}).ribbons == 0, 'missing ribbon feed must not use medal values')
state.kills, state.deaths = 1, 0
assert(hud:snapshot({map_open = false}).stats.kd == '1/0')
state.kills, state.deaths = 0, 0
assert(hud:snapshot({map_open = false}).stats.kd == '0/0')
state.kills,state.deaths,state.history_kills,state.history_deaths=240,0,7596,100
assert(hud:snapshot({map_open=false}).stats.kd_text=='240/0［75.96↑］')
state.deaths=4
assert(hud:snapshot({map_open=false}).stats.kd_text=='60.00［75.96↓］')
state.kills,state.deaths,state.history_kills,state.history_deaths=12,2,6,1
assert(hud:snapshot({map_open=false}).stats.kd_text=='6.00［6.00］')
state.kills,state.deaths,state.history_kills,state.history_deaths=10000,10000,10001,10000
assert(hud:snapshot({map_open=false}).stats.kd_text=='1.00［1.00↓］','comparison uses actual ratios before rounding')
state.shots=19
local shots_view=hud:snapshot({map_open=false})
state.shots=20
assert(hud:snapshot({map_open=false})~=shots_view and hud:snapshot({map_open=false}).stats.shots=='20')
state.kills, state.deaths = nil, nil
assert(hud:snapshot({map_open = false}).stats.kills == '--')
assert(not pcall(function() hud:snapshot({}) end), 'missing native map state must never be guessed')
assert(not pcall(function() hud:snapshot({map_open = true, width = 0}) end))
-- Review fixtures come from the actual Lua layout, not a second JavaScript implementation.
local function encode(value, key)
    if type(value) == 'string' then
        return '"' .. value:gsub('\\', '\\\\'):gsub('"', '\\"'):gsub('\n', '\\n') .. '"'
    elseif type(value) == 'number' or type(value) == 'boolean' then return tostring(value)
    elseif type(value) == 'table' then
        local pieces, array = {}, #value > 0 or key == 'medals' or key == 'ribbons' or key == 'samples'
        if array then for _, item in ipairs(value) do pieces[#pieces + 1] = encode(item) end
        else
            local keys = {}; for name in pairs(value) do keys[#keys + 1] = name end; table.sort(keys)
            for _, name in ipairs(keys) do pieces[#pieces + 1] = encode(name) .. ':' .. encode(value[name], name) end
        end
        return (array and '[' or '{') .. table.concat(pieces, ',') .. (array and ']' or '}')
    end
    error('unsupported JSON fixture value')
end
if arg[2] then
    local file = assert(io.open(arg[2], 'wb'))
    file:write(encode({schema = 1, native_binding_verified = false, data = 'synthetic_preview', samples = samples}), '\n')
    file:close()
end
-- Adding the asset alone must not publish a discovery. Only verified totals
-- supplied by the caller enter the same retained ribbon presentation.
local recon_state={ribbons={recon=0},mission_medals={}}
local recon_hud=create(recon_state,function() return true end)
assert(#recon_hud:snapshot({map_open=true}).ribbons==0)
recon_state.ribbons.recon=1
local recon_view=recon_hud:snapshot({map_open=true})
assert(#recon_view.ribbons==1 and recon_view.ribbons[1].id=='R10' and recon_view.ribbons[1].count==1)
recon_state.ribbons.recon=2
recon_view=recon_hud:snapshot({map_open=true})
assert(#recon_view.ribbons==1 and recon_view.ribbons[1].count==2)
print('PASS: 52 definitions, exact synthetic status totals, map layout, full task space reclaim, five native widths, twelve medals, cache, hidden state, missing ribbons, recon zero/positive totals and reset.')
