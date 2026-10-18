-- Exercise the actual built addon. Only Runtime/game and the public menu API
-- are boundaries: the native map bridge, settings, preview and renderer are real.
local addon_path, runtime_path = assert(arg[1]), assert(arg[2])
package.preload['hd2runtime/schemas/current'] = function() return dofile(runtime_path .. '/schemas/current.lua') end
package.preload['hd2runtime/runtime/log'] = function() return {emit = function() end} end
package.preload['hd2runtime/runtime/events'] = function() return {} end
package.preload['hd2runtime/runtime/mod_store'] = function() return dofile(runtime_path .. '/runtime/mod_store.lua') end
local codec = require('hd2runtime/runtime/mod_store')
local tests, data, writes, messages = 0, {ui_settings = {auto_ui_probe = false}}, {}, {}
local available, readable, mission, map_open = true, true, false, false
local frame, draw, overlay, module
local bindings, options, values, callbacks = {}, {}, {}, {}
local pointer_reads, byte_reads, large_reads, queries, stat_reads, image_creations = 0, 0, 0, 0, 0, 0
local allow_capture, native_bytes = false, 0
local game, exe, hud = 0x10000000, 0x50000000, 0x20000000
local world = {game = game, exe = exe, view = {slot = function() return {} end}}
local function copy(value)
    if type(value) ~= 'table' then return value end
    local out = {}; for k, v in pairs(value) do out[k] = copy(v) end; return out
end
local function canonical(value)
    if value == nil then return 'nil' end
    if type(value) ~= 'table' then return codec.encode(value) end
    local keys, out = {}, {}
    for k in pairs(value) do keys[#keys + 1] = k end
    table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
    for _, k in ipairs(keys) do out[#out + 1] = '[' .. canonical(k) .. ']=' .. canonical(value[k]) end
    return '{' .. table.concat(out, ',') .. '}'
end
function world.view.pointer(at)
    pointer_reads = pointer_reads + 1
    native_bytes = native_bytes + 8
    assert(at == game + 0x346D538, 'native bridge read outside the proven HUD global')
    return hud
end
function world.view.read(at, size)
    native_bytes = native_bytes + size
    if size ~= 1 then
        large_reads = large_reads + 1
        assert(allow_capture, 'unexpected UI capture or scan')
        assert((at >= hud and at + size <= hud + 0x480000)
            or (at >= game + 0x12E8000 and at + size <= game + 0x12F8000)
            or (at >= game + 0x143A000 and at + size <= game + 0x1452000),
            'capture read outside the explicit HUD/code ranges')
        return string.rep('\0', size)
    end
    byte_reads = byte_reads + 1
    if at == hud + 0x24E340 + 0x58 or at == hud + 0x24E340 + 0x21F5B0 then
        return string.char(mission and 1 or 0)
    end
    if at == hud + 0x3EF2FD then return readable and string.char(map_open and 1 or 0) or nil end
    error('native bridge read outside the proven UI bytes')
end
world.runtime = {query = function(at)
    queries = queries + 1; assert(allow_capture, 'unexpected capture region query')
    if at >= hud and at < hud + 0x800000 then
        return {allocation_base = hud, base = hud, size = 0x800000, type = 0x20000, protect = 4, state = 0x1000}
    end
    if at >= game and at < game + 0x5000000 then
        return {allocation_base = game, base = game, size = 0x5000000, type = 0x1000000, protect = 0x20, state = 0x1000}
    end
    error('capture query outside known fixture allocations')
end}
local store = {}
function store:get(key, fallback) if data[key] == nil then return copy(fallback) end; return copy(data[key]) end
function store:set(key, value) data[key] = copy(value); writes[#writes + 1] = key end
function store:save() return true end
local mod = {}
function mod:store() return store end
function mod:log(message) messages[#messages + 1] = tostring(message) end
function mod:on_frame(fn) frame = fn end
function mod:bind(id, opts) bindings[id] = opts; return {state = 'active'} end
package.preload['mods/skyeshade/hd2runtime'] = function()
    return {mod = function() return mod end,
        resources = {image = function(id) image_creations = image_creations + 1; return id end},
        ui = {overlay = function(opts)
            overlay = {visible = opts.visible}
            function overlay:draw(fn) draw = fn end
            function overlay:show() self.visible = true end
            function overlay:hide() self.visible = false end
            return overlay
        end}}
end
package.preload['hd2runtime/domains/metadata'] = function() return {version = '0.30.3'} end
package.preload['hd2runtime/domains/event_natives'] = function()
    return {stats = {keys = {projectiles_fired = 1, dealt_kills = 2, received_deaths = 3}}}
end
package.preload['hd2runtime/runtime/event_world'] = function()
    return {open = function() return available and world or nil end,
        game_state = function() return readable and {mission = mission} or nil end,
        players = function() return {{['local'] = true, entity = 42}} end,
        stat_breakdown = function()
            stat_reads = stat_reads + 1
            return {totals = {[1] = 2000, [2] = 12, [3] = 0, [0xC7680A1B] = 0}, sources = {}}
        end}
end
package.preload['hd2runtime/runtime/beacon_redirect'] = function()
    return {prove = function() return false end, clock = function() return 0 end}
end
package.preload['hd2runtime/runtime/stratagem_loadout'] = function() return {} end
local menu = {api = 1, version = 3, ready = function() return false end}
function menu.register_option(id, spec)
    assert(options[id] == nil, 'each option must register once')
    options[id], values[id] = spec, spec.default; return true
end
function menu.get(id) return values[id] end
function menu.set(id, value) assert(options[id]); values[id] = value; return true end
function menu.on_change(id, callback) assert(options[id]); callbacks[id] = callback; return true end
rawset(_G, 'ModOptionsMenu', menu)
rawset(_G, 'HD2WarCostLedgerV1', nil)
module = dofile(addon_path)
local prefix = 'hd2_costs.war_cost_ledger.'
local function apply(id, value)
    id = prefix .. id
    assert(callbacks[id], 'public callback not registered: ' .. id)
    values[id] = value; callbacks[id](value, id)
end
local function tick(seconds)
    local whole = math.floor(seconds / .1 + 1e-9)
    for _ = 1, whole do frame(.1) end
    local tail = seconds - whole * .1
    if tail > 1e-9 then frame(tail) end
end
local function render()
    local result = {items = {}, frames = 0, images = 0}
    local d = {width = 1920, height = 1080, scale = 1}
    function d:rect(x, y, w, h, opts) result.items[#result.items + 1] = {kind = 'rect', x = x, y = y, w = w, h = h, opts = opts} end
    function d:text(text, x, y, opts) result.items[#result.items + 1] = {kind = 'text', text = tostring(text), x = x, y = y, opts = opts} end
    function d:image(handle, x, y, w, h, opts)
        assert(x >= 0 and y >= 0 and x + w <= d.width + 1e-6 and y + h <= d.height + 1e-6,
            'whole native image quad must be within viewport')
        result.images = result.images + 1
        if handle == 'ribbon_frame' then result.frames = result.frames + 1 end
        result.items[#result.items + 1] = {kind = 'image', handle = handle, x = x, y = y, w = w, h = h, opts = opts}
    end
    draw(d); return result
end
local function check(name, fn)
    local ok, why = pcall(fn); assert(ok, name .. ': ' .. tostring(why))
    tests = tests + 1; print('PASS ' .. name)
end

check('public menu registers actual addon settings before native menu ready', function()
    assert(not overlay.visible and module.native_ui, 'native bridge must load using the real current schema')
    frame(.1)
    assert(module.ui_settings.status == 'registered')
    local n = 0
    for id, spec in pairs(options) do
        n = n + 1
        assert(id:sub(1, #prefix) == prefix and spec.mod_id == 'hd2_costs.war_cost_ledger')
        assert(type(spec.mod)=='function', 'localized category uses the public dynamic-text contract')
        assert(spec.mod() == '战果与战争账单' and callbacks[id])
    end
    assert(n == 19 and n <= 32 and image_creations == 60)
    for _, name in ipairs({'hit_position', 'charge_position'}) do
        local spec = assert(options[prefix .. name], 'separate placement choice missing: ' .. name)
        assert(spec.type == 'choice' and #spec.choices == 3)
    end
    assert(options[prefix .. 'side_margin'] == nil and options[prefix .. 'side_vertical_percent'] == nil)
    assert(options[prefix .. 'right_margin'].default == 0 and options[prefix .. 'top_margin'].default == 0)
    assert(module.native_ui.state.hud == hud and module.game_hud.native_map_verified)
    assert(#render().items == 0 and large_reads == 0 and queries == 0)
end)
check('applied settings reach renderer and F8 synchronizes the same public option', function()
    apply('scale_percent', 125); apply('opacity_percent', 61)
    apply('right_margin', 60); apply('top_margin', 42)
    apply('move_tasks', false); apply('task_gap', 30)
    local c = module.game_hud.config
    assert(c.scale == 1.25 and c.opacity == .61 and c.right_margin == 60 and c.top_margin == 42)
    assert(not c.move_tasks and c.task_gap == 30)
    assert(module.game_hud:reservation(true,true,0).move_tasks == false)
    bindings['war_cost_ledger.toggle_hud'].on_press()
    assert(values[prefix .. 'enabled'] == false and data.hud_enabled == false and not overlay.visible)
    apply('enabled', true)
    assert(module.ui_settings.config.enabled and data.hud_enabled == true and not overlay.visible)
    assert(data.ui_settings.scale_percent == 125 and data.ui_settings.opacity_percent == 61)
end)
check('independent kill source display toggle reaches the real addon and clears stale notices only', function()
    local option=assert(options[prefix..'kill_source_enabled'])
    assert(option.type=='toggle' and option.default==true and type(option.label)=='function' and option.label()=='显示击杀来源')
    assert(module.game_hud.config.kill_source_enabled==true)
    local kills,bill,ribbons=module.state.kills,module.state.total_cents,canonical(module.state.ribbons)
    module.state.kill_source_notices={revision=123,items={{expires_at=999,lines={'旧目标 [旧来源]'}}}}
    apply('kill_source_enabled',false)
    assert(module.ui_settings.config.kill_source_enabled==false and module.game_hud.config.kill_source_enabled==false)
    assert(data.ui_settings.kill_source_enabled==false and #module.state.kill_source_notices.items==0,
        'disabling source text clears the retained latest entry')
    apply('kill_source_enabled',true)
    assert(module.game_hud.config.kill_source_enabled==true and #module.state.kill_source_notices.items==0,
        'enabling source text must not replay the old entry')
    assert(module.state.kills==kills and module.state.total_cents==bill and canonical(module.state.ribbons)==ribbons,
        'source display setting changes no combat, award or fee totals')
end)
check('ship UI preview lasts eight seconds and never enters real state or last mission', function()
    -- Settle the preceding real settings/checkpoint before testing the preview;
    -- the regular five-second flush must not be mistaken for preview data.
    tick(5.1)
    local before, last, before_reads = canonical(module.state), canonical(data.last_mission), stat_reads
    apply('preview', 4)
    assert(values[prefix .. 'preview'] == 1 and overlay.visible)
    local test = render(); assert(test.images > 0)
    local named_medal,legacy_label = false,false
    for _, item in ipairs(test.items) do
        if item.text == '民主收割机' then named_medal = true end
        if item.text == 'UI TEST' then legacy_label = true end
    end
    assert(named_medal and not legacy_label and module.game_hud.preview_mode == 4)
    assert(module.game_hud:native_model(0,true).layout.revision == 'hud-common-right-edge-v6')
    tick(7.9); assert(overlay.visible and #render().items > 0)
    tick(.2); assert(not overlay.visible and #render().items == 0 and module.game_hud.preview_mode == nil)
    assert(canonical(module.state) == before and canonical(data.last_mission) == last and stat_reads == before_reads,
        'independent preview must not mutate/persist real counters')
    assert(image_creations == 60, 'preview must reuse cached image handles')
end)
check('currency Apply reaches live and isolated preview HUD without rewriting the account', function()
    local total, entries, last = module.state.total_cents, canonical(module.state.entries), canonical(data.last_mission)
    local reads = pointer_reads + byte_reads + stat_reads + queries
    module.state.total_cents = 10000 -- fixture balance: 100 MC
    local cases = {{1,'MC','100.00','MC'},{2,'USD','100.00','$'},{3,'CNY','669.21','¥'},
        {4,'EUR','89.24','€'},{5,'GBP','75.64','£'},{6,'SEK','996.56','kr'}}
    for _, c in ipairs(cases) do
        apply('currency', c[1])
        local view = module.game_hud:native_model(0,true)
        assert(view.stats.currency == c[2] and view.stats.bill == c[3])
        assert(view.stats.bill_text == c[3] .. c[4])
        assert(module.state.display_currency == c[2] and data.ui_settings.currency == c[1])
        assert(module.state.total_cents == 10000 and canonical(module.state.entries) == entries)
    end
    assert(reads == pointer_reads + byte_reads + stat_reads + queries, 'currency added game reads')
    apply('preview',3)
    local view = module.game_hud:native_model(0,true)
    assert(view.testing and view.stats.currency == 'SEK')
    local found = false
    for _, item in ipairs(render().items) do
        if item.kind == 'text' and item.text:sub(-2) == 'kr' then found = true end
        assert(item.text ~= 'SEK', 'currency is a value suffix, not a separate label')
    end
    assert(found, 'flat ship preview did not show the selected currency suffix')
    apply('currency',3)
    assert(module.game_hud:native_model(0,true).stats.currency == 'CNY', 'active preview kept old currency')
    assert(canonical(data.last_mission) == last, 'ship settings overwrote last mission')
    tick(8.1)
    apply('currency',1)
    module.state.total_cents = total
end)
check('numeric native HUD map state immediately gates collected ribbons', function()
    mission, map_open = true, false; frame(.1)
    assert(overlay.visible and module.state.shots == 2000 and module.game_hud.native_map_verified)
    assert(render().frames == 0)
    map_open = true; frame(.1)
    assert(module.native_ui.state.map_open and #module.game_hud:native_model(0,true).awards.ribbons>0)
    map_open = false; frame(.1)
    assert(not module.native_ui.state.map_open and #module.game_hud:native_model(0,true).awards.ribbons==0)
    bindings['war_cost_ledger.toggle_collection'].on_press()
    assert(module.game_hud.collection_open and #module.game_hud:native_model(0,true).awards.ribbons==0, 'verified closed map takes precedence over F9')
    apply('ribbon_mode', 2); assert(#module.game_hud:native_model(0,true).awards.ribbons>0)
    apply('ribbon_mode', 1); assert(#module.game_hud:native_model(0,true).awards.ribbons==0)
    assert(#render().items==0, 'map changes must not re-enable flat combat rendering')
end)
check('F8 hiding preserves real statistics and stale native map is discarded', function()
    local before = stat_reads
    apply('enabled', false); frame(.1)
    assert(not overlay.visible and stat_reads == before + 1 and #render().items == 0)
    map_open, readable = true, false; frame(.1)
    assert(not module.game_hud.native_map_verified and module.native_ui.state == nil and not overlay.visible)
    readable, map_open = true, false; apply('enabled', true); frame(.1)
    assert(module.game_hud.native_map_verified and overlay.visible)
end)
check('capture is manual, deferred five seconds, cancellable and never starts on wrong map', function()
    assert(module.capture_status() == 'disabled' and large_reads == 0 and queries == 0)
    apply('capture', 3)
    assert(values[prefix .. 'capture'] == 1 and module.capture_status() == 'queued')
    tick(4.9); assert(module.capture_status() == 'queued' and large_reads == 0 and queries == 0)
    tick(.2); assert(module.capture_status() == 'queued' and large_reads == 0 and queries == 0)
    apply('capture', 4); assert(module.capture_status() == 'disabled')
    tick(.2); assert(large_reads == 0 and queries == 0)
end)
check('capture timeout with no world cannot revive after world returns', function()
    available = false
    apply('capture', 2); assert(module.capture_status() == 'queued')
    tick(35.2); assert(module.capture_status() == 'disabled')
    available = true; frame(.1)
    assert(module.capture_status() == 'disabled' and large_reads == 0 and queries == 0)
    local timeout = false
    for _, line in ipairs(messages) do if line:find('30秒内', 1, true) then timeout = true end end
    assert(timeout, 'timed-out manual request must explain why it did not start')
end)
check('normal capture OFF and ship return perform only bounded map reads', function()
    apply('capture', 1); mission = false; frame(.1)
    local before_ptr, before_byte = pointer_reads, byte_reads
    tick(2)
    assert(pointer_reads - before_ptr == 20 and byte_reads - before_byte == 60,
        'only the normal four-read native map bridge may run')
    assert(module.capture_status() == 'disabled' and large_reads == 0 and queries == 0 and not overlay.visible)
    assert(data.ui_settings.preview == nil and data.ui_settings.capture == nil, 'manual actions must not persist')
end)
check('public manual request reaches lazy capture and completes bounded binary plus actual JSON codec', function()
    -- In-memory file boundary only: never create a fixture file in the user's mod_data.
    local original_open, files = io.open, {}
    io.open = function(path, mode)
        assert(path:find('/ledger_ui_', 1, true), 'manual capture must only open its own evidence files')
        if mode == 'rb' then
            if not files[path] then return nil, 'fixture file absent' end
            return {close = function() return true end}
        end
        assert(mode == 'wb' and files[path] == nil, 'capture must not overwrite an evidence file')
        local item = {parts = {}, closed = false}; files[path] = item
        return {write = function(self, text) item.parts[#item.parts + 1] = text; return self end,
            close = function() item.closed = true; return true end}
    end
    local ok, why = pcall(function()
        mission, map_open, allow_capture = true, false, true
        frame(.1); apply('capture', 2)
        local before_reads, before_queries = large_reads, queries
        tick(4.9)
        assert(module.capture_status() == 'queued' and large_reads == before_reads and queries == before_queries)
        local steps, peak = 0, 0
        repeat
            local before = native_bytes; frame(.1)
            peak = math.max(peak, native_bytes - before); steps = steps + 1
            assert(steps <= 100, 'bounded capture must finish rather than restart itself')
        until module.capture_status() == 'complete'
        assert(steps > 70 and peak <= 65536, 'addon map poll plus capture must fit the per-frame read budget')
        local binary, metadata, count = nil, nil, 0
        for path, file in pairs(files) do
            count = count + 1; assert(file.closed)
            local contents = table.concat(file.parts)
            if path:sub(-4) == '.bin' then binary = contents
            elseif path:sub(-5) == '.json' then metadata = codec.decode(contents)
            else error('unexpected evidence file suffix') end
        end
        assert(count == 2 and binary and #binary == 4882432)
        assert(metadata.complete and metadata.atomic == false and metadata.mode == 'map_closed')
        assert(metadata.bytes_written == #binary and metadata.bytes_planned == #binary)
        assert(metadata.exe_sha == module.native_ui.source.exe_sha and metadata.dll_sha == module.native_ui.source.dll_sha)
        assert(metadata.identity_consistent and metadata.boundaries_consistent and #metadata.ranges == 3)
        assert(metadata.start_state.hud == hud and metadata.end_state.hud == hud)
        local done_reads, done_queries = large_reads, queries
        tick(1); assert(large_reads == done_reads and queries == done_queries, 'successful capture must stop')
    end)
    io.open, allow_capture = original_open, false
    assert(ok, why)
end)
check('another map sample reports queued after the first sample completes', function()
    apply('capture', 3)
    assert(module.capture_status() == 'queued', 'pending request must take precedence over the previous completed sample')
    local before_reads, before_queries = large_reads, queries
    tick(.2)
    assert(module.capture_status() == 'queued' and large_reads == before_reads and queries == before_queries)
    apply('capture', 4)
    assert(module.capture_status() == 'complete', 'cancelling a pending second request retains the first completed report')
end)
print('Addon options integration tests: ' .. tests .. ' passed; real native menu rendering and task relocation await a game session.')
