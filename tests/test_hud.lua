-- Exercise the actual built addon with only read-only Runtime boundaries replaced.
local addon_path = assert(arg[1], 'built addon path required')
local data, mission, available, state_readable = {}, false, true, true
local frame, draw, binding, collection_binding, overlay, module
local stat_reads, sets, shows, hides = 0, 0, 0, 0
local world = {game = 1, view = {slot = function() return {} end}}
local store = {}
function store:get(key, fallback) if data[key] == nil then return fallback end; return data[key] end
function store:set(key, value) data[key] = value; sets = sets + 1 end
function store:save() return true end
local mod = {}
function mod:store() return store end
function mod:log() end
function mod:on_frame(fn) frame = fn end
function mod:bind(id, opts)
    if id == 'war_cost_ledger.toggle_hud' then
        assert(opts.key == 'F8'); binding = opts
    else
        assert(id == 'war_cost_ledger.toggle_collection' and opts.key == 'F9'); collection_binding = opts
    end
    return {state = 'active'}
end
package.preload['mods/skyeshade/hd2runtime'] = function()
    return {mod = function() return mod end, ui = {overlay = function(opts)
        overlay = {visible = opts.visible}
        function overlay:draw(fn) draw = fn end
        function overlay:show() self.visible = true; shows = shows + 1 end
        function overlay:hide() self.visible = false; hides = hides + 1 end
        return overlay
    end}}
end
package.preload['hd2runtime/domains/metadata'] = function() return {version = '0.30.3'} end
package.preload['hd2runtime/domains/event_natives'] = function()
    return {stats = {keys = {projectiles_fired = 1, dealt_kills = 2, received_deaths = 3}}}
end
package.preload['hd2runtime/runtime/event_world'] = function()
    return {
        open = function() return available and world or nil end,
        game_state = function() return state_readable and {mission = mission} or nil end,
        players = function() return {{['local'] = true, entity = 42}} end,
        stat_breakdown = function()
            stat_reads = stat_reads + 1
            return {totals = {[1] = stat_reads, [2] = stat_reads}, sources = {}}
        end,
    }
end
package.preload['hd2runtime/runtime/beacon_redirect'] = function()
    return {prove = function() return false end, clock = function() return 0 end}
end
package.preload['hd2runtime/runtime/stratagem_loadout'] = function() return {} end
local function load()
    rawset(_G, 'HD2WarCostLedgerV1', nil)
    module = dofile(addon_path)
end
local function render(width, height)
    local items = {}
    local d = {width = width, height = height, scale = math.min(width / 1920, height / 1080)}
    function d:rect(x, y, w, h, colour)
        items[#items + 1] = {kind = 'rect', x = x, y = y, w = w, h = h, colour = colour}
    end
    function d:text(text, x, y, opts)
        items[#items + 1] = {kind = 'text', text = text, x = x, y = y, opts = opts}
    end
    draw(d)
    return items
end
load()
assert(overlay.visible == false, 'HUD must start hidden, before mission state is known')
frame(0.1)
assert(#render(1920, 1080) == 0 and not overlay.visible, 'ship/menu must draw no HUD')
mission = true; frame(0.1)
assert(overlay.visible and #render(1920, 1080) == 0, 'combat must not draw a second flat HUD')
assert(type(module.native_hud_snapshot)=='function' and module.native_hud_snapshot()==nil,
    'missing native geometry must not publish a detached combat feed')
assert(module.battle_hud and #module.battle_hud.icons == 52)
local blocked_icon
for _,icon in ipairs(module.battle_hud.icons)do if icon.id=='H03' then blocked_icon=icon end end
assert(blocked_icon and blocked_icon.key=='hit_blocked', 'blocked hits remain a separate earned ribbon')
assert(module.game_hud and module.game_hud.image_count == 59 and not module.game_hud.collection_open)
assert(module.game_hud.artwork == 'v18_icon_masks' and not module.game_hud.image_api_available,
    'missing optional image API must not create a flat combat fallback')
local before_collection = stat_reads
collection_binding.on_press(); assert(module.game_hud.collection_open)
collection_binding.on_press(); assert(not module.game_hud.collection_open)
assert(stat_reads == before_collection, 'F9 changes presentation only')
local before_preview_reads, before_preview_sets = stat_reads, sets
local preview = module.battle_hud:snapshot({map_open = false})
assert(preview.shown and preview.artwork == 'placeholders' and preview.native_binding == false)
assert(preview.stats.kills == tostring(module.state.kills) and #preview.ribbons == 0)
assert(module.battle_hud:snapshot({map_open = false}) == preview)
assert(stat_reads == before_preview_reads and sets == before_preview_sets,
    'the UI feed must neither poll game memory nor store anything')
for _, size in ipairs({{1280, 720}, {1920, 1080}, {2560, 1440}, {3840, 2160}, {3440, 1440}}) do
    local w, h = size[1], size[2]
    local items, rows = render(w, h), 0
    for _, item in ipairs(items) do
        assert(item.x >= w * 0.85 and item.x <= w and item.y >= 0 and item.y <= h * 0.12,
            'HUD must stay within the small top-right area')
        if item.kind == 'rect' then
            assert(item.x + item.w <= w and item.y + item.h <= h * 0.12)
            assert(item.w * item.h / (w * h) < 0.01, 'HUD background must occupy less than 1% of screen')
        else
            assert(item.opts.size <= 22 * math.min(w / 1920, h / 1080))
            if item.opts.align == 'right' then rows = rows + 1 end
        end
    end
    assert(rows == 0 and #items == 0, 'combat must use native widgets at every resolution')
end
local before_toggle = sets
binding.on_press()
assert(not overlay.visible and data.hud_enabled == false and #render(1920, 1080) == 0)
assert(not module.battle_hud:snapshot({map_open = true}).shown, 'native feed must follow the existing F8 setting')
assert(sets == before_toggle + 1, 'one toggle must store only its own setting')
local before_hidden = stat_reads
frame(0.1)
assert(stat_reads == before_hidden + 1, 'hidden HUD must keep recording stats')
mission = false; frame(0.1)
mission = true; frame(0.1)
assert(not overlay.visible, 'mission changes must not override the user toggle')
load(); frame(0.1)
assert(not overlay.visible, 'saved OFF must survive addon reload')
binding.on_press()
assert(overlay.visible and data.hud_enabled == true)
local before_stable = shows + hides
for _ = 1, 10 do frame(0.1) end
assert(shows + hides == before_stable, 'stable gameplay must not toggle engine visibility each poll')
available = false; frame(0.1)
assert(not overlay.visible and #render(1920, 1080) == 0, 'missing world must hide stale HUD')
available = true; frame(0.1)
assert(overlay.visible)
state_readable = false; frame(0.1)
assert(not overlay.visible, 'unknown game state must hide HUD')
state_readable = true; mission = false; frame(0.1)
assert(not overlay.visible and #render(1920, 1080) == 0, 'returning to ship must hide HUD')
binding.on_press(); binding.on_press()
assert(not overlay.visible and data.hud_enabled == true, 'turning ON on the ship must still draw nothing')
print('PASS: native-only combat rendering at five resolutions, F8 preference, recording while hidden and stale-state hiding.')
