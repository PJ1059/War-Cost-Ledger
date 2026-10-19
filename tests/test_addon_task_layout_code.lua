-- Built addon integration with its actual task-code reader. The Runtime,
-- memory and persistence boundaries are isolated fixtures, never a live game.
local addon_path, runtime_path = assert(arg[1]), assert(arg[2])
package.preload['hd2runtime/schemas/current'] = function() return dofile(runtime_path .. '/schemas/current.lua') end
package.preload['hd2runtime/runtime/log'] = function() return {emit = function() end} end
package.preload['hd2runtime/runtime/events'] = function() return {} end
package.preload['hd2runtime/runtime/mod_store'] = function() return dofile(runtime_path .. '/runtime/mod_store.lua') end
local codec = require('hd2runtime/runtime/mod_store')
local original_open, tests = io.open, 0
local option_prefix = 'hd2_costs.war_cost_ledger.'
local function copy(value)
    if type(value) ~= 'table' then return value end
    local out = {}; for key, v in pairs(value) do out[key] = copy(v) end; return out
end
local function hex_bytes(text)
    return (text:gsub('..', function(pair) return string.char(assert(tonumber(pair, 16))) end))
end
local function patched(raw, offset, text) return raw:sub(1, offset) .. text .. raw:sub(offset + #text + 1) end
local function u32(number)
    local out = {}; for i = 1, 4 do out[i] = string.char(number % 256); number = math.floor(number / 256) end
    return table.concat(out)
end
local function pointer(number) return u32(number % 4294967296) .. u32(math.floor(number / 4294967296)) end
-- The two caller witnesses are real. The uncollected windows are deliberately
-- synthetic bytes; passing this test never verifies their real game contents.
local caller_pins = {
    {rva = 0x17D0863, bytes = '410f28c8488bcde831f0ffff'},
    {rva = 0x17D08BD, bytes = '488d8df06d0000410f28c8e833ae0700'},
}
if arg[3] then
    local file = assert(original_open(arg[3], 'rb'))
    local evidence = assert(codec.decode(file:read('*a'))); file:close()
    assert(evidence.format == 'HD2-TASK-LAYOUT-CALLER-PINS-1'
        and evidence.source_sha256 == 'fdaf5e1961693bbeb7e910382286d333c5d6e65bce9607ed76232c1ebab9074b')
    assert(#evidence.pins == #caller_pins)
    for i, item in ipairs(evidence.pins) do
        assert(item.rva == caller_pins[i].rva and item.hex:lower() == caller_pins[i].bytes
            and item.length == #hex_bytes(item.hex))
        caller_pins[i] = {rva = item.rva, bytes = item.hex}
    end
end
local runtime_modules = {'mods/skyeshade/hd2runtime', 'hd2runtime/domains/metadata',
    'hd2runtime/domains/event_natives', 'hd2runtime/runtime/event_world',
    'hd2runtime/runtime/beacon_redirect', 'hd2runtime/runtime/stratagem_loadout'}
local function boot(options)
    options = options or {}
    local f = {data = options.data or {}, files = options.files or {}, writes = {}, messages = {},
        options = {}, values = {}, callbacks = {}, bindings = {}, now = 0, available = true,
        mission = false, map_open = false, native_readable = true, shots = 2000, kills = 12, deaths = 0,
        native_bytes = 0, code_bytes = 0, code_reads = 0, queries = 0, stat_reads = 0, step_code_peak = 0}
    if options.disabled then f.data.ui_settings = {auto_ui_probe = false} end
    local game, exe, hud = 0x10000000, 0x50000000, 0x20000000
    local chunks = {{game + 0x17CF800, string.rep('\165', 0x800)},
        {game + 0x184B700, string.rep('\90', 0x3000)}}
    for _, pin in ipairs(caller_pins) do chunks[#chunks + 1] = {game + pin.rva, hex_bytes(pin.bytes)} end
    local function memory(at, size)
        local raw = string.rep('\0', size)
        for _, item in ipairs(chunks) do
            local first, last = math.max(at, item[1]), math.min(at + size, item[1] + #item[2])
            if first < last then raw = patched(raw, first - at, item[2]:sub(first - item[1] + 1, last - item[1])) end
        end
        return raw
    end
    local world = {game = game, exe = exe, key = 'code-fixture-world', view = {},
        runtime = {mode = options.mode == nil and 'live' or options.mode}}
    f.world = world
    function world.view.slot() return {} end
    function world.view.pointer(at)
        f.native_bytes = f.native_bytes + 8
        assert(at == game + 0x346D538, 'unexpected native pointer read'); return hud
    end
    function world.view.read(at, size)
        f.native_bytes = f.native_bytes + size
        if size == 1 then
            if not f.native_readable then return nil end
            if at == hud + 0x24E340 + 0x58 or at == hud + 0x24E340 + 0x21F5B0 then return string.char(f.mission and 1 or 0) end
            if at == hud + 0x3EF2FD then return string.char(f.map_open and 1 or 0) end
            error('unexpected single-byte UI read')
        end
        local is_code = (at >= game + 0x17CF800 and at + size <= game + 0x17D1000)
            or (at >= game + 0x184B700 and at + size <= game + 0x184E700)
        if is_code then
            f.code_reads, f.code_bytes = f.code_reads + 1, f.code_bytes + size
            if f.fail_code then return nil end
            if f.bad_pin and at == game + caller_pins[1].rva then return string.rep('\0', size) end
        else
            assert((at >= hud and at + size <= hud + 0x480000)
                or (at >= game + 0x12E8000 and at + size <= game + 0x12F8000)
                or (at >= game + 0x143A000 and at + size <= game + 0x1452000),
                'read escaped the fixed code windows/PINs or explicit manual HUD ranges')
        end
        return memory(at, size)
    end
    function world.runtime.query(at)
        f.queries = f.queries + 1
        if at >= hud and at < hud + 0x800000 then return {allocation_base = hud, base = hud,
            size = 0x800000, state = 0x1000, protect = 4, type = 0x20000} end
        if at >= game and at < game + 0x4000000 then return {allocation_base = game, base = game,
            size = 0x4000000, state = 0x1000, protect = 0x20, type = 0x1000000} end
        error('query escaped the fixture allocations')
    end
    io.open = function(path, mode)
        local normalized = path:gsub('\\', '/')
        assert(normalized:find('/HD2Runtime/mod_data/', 1, true)
            and normalized:match('/ledger_[^/]+$'), 'probe must only open its own isolated evidence files')
        if mode == 'rb' then
            local file = f.files[path]; if not file then return nil, 'fixture file absent' end
            return {read = function(_, n)
                local raw = table.concat(file.parts); return type(n) == 'number' and raw:sub(1, n) or raw
            end, close = function() return true end}
        end
        assert(mode == 'wb' or mode == 'ab', 'unexpected write mode')
        assert(mode ~= 'ab' or f.files[path], 'append requires existing evidence')
        assert(mode ~= 'wb' or not f.files[path] or path:sub(-5) == '.json', 'existing binary evidence must not be overwritten')
        local file = mode == 'ab' and f.files[path] or {parts = {}}
        file.closed = false; f.files[path] = file
        return {write = function(self, raw) assert(type(raw) == 'string'); file.parts[#file.parts + 1] = raw; return self end,
            flush = function() return true end, close = function() file.closed = true; return true end}
    end
    local store, mod = {}, {}
    function store:get(key, fallback) return copy(f.data[key] == nil and fallback or f.data[key]) end
    function store:set(key, value) f.data[key] = copy(value); f.writes[#f.writes + 1] = key end
    function store:save() return true end
    function mod:store() return store end
    function mod:log(message) f.messages[#f.messages + 1] = tostring(message) end
    function mod:on_frame(fn) f.frame = fn end
    function mod:bind(id, spec) f.bindings[id] = spec; return {state = 'active'} end
    package.preload['mods/skyeshade/hd2runtime'] = function()
        return {mod = function() return mod end, resources = {image = function(id) return id end},
            ui = {overlay = function(config)
                local overlay = {visible = config.visible}; f.overlay = overlay
                function overlay:draw(fn) f.draw = fn end
                function overlay:show() self.visible = true end
                function overlay:hide() self.visible = false end
                return overlay
            end}}
    end
    package.preload['hd2runtime/domains/metadata'] = function() return {version = '0.30.3'} end
    package.preload['hd2runtime/domains/event_natives'] = function() return {stats = {keys = {
        projectiles_fired = 1, dealt_kills = 2, received_deaths = 3, projectiles_hit = 4}}} end
    package.preload['hd2runtime/runtime/event_world'] = function()
        return {open = function() return f.available and world or nil end,
            game_state = function() return {mission = f.mission} end,
            entity_state = function() return nil, 'fixture has no avatar Health record' end,
            players = function() return {{['local'] = true, entity = 42}} end,
            stat_breakdown = function()
                f.stat_reads = f.stat_reads + 1
                return {totals = {[1] = f.shots, [2] = f.kills, [3] = f.deaths, [0xC7680A1B] = 0}, sources = {}}
            end}
    end
    package.preload['hd2runtime/runtime/beacon_redirect'] = function() return {prove = function() return false end, clock = function() return 0 end, beacons = function() return {} end} end
    package.preload['hd2runtime/runtime/stratagem_loadout'] = function() return {prove = function() return false end, id_of = function() return nil end} end
    for _, name in ipairs(runtime_modules) do package.loaded[name] = nil end
    local menu = {api = 1, version = 3}
    function menu.register_option(id, spec) f.options[id], f.values[id] = spec, spec.default; return true end
    function menu.get(id) return f.values[id] end
    function menu.set(id, value) f.values[id] = value; return true end
    function menu.on_change(id, callback) f.callbacks[id] = callback; return true end
    rawset(_G, 'ModOptionsMenu', menu); rawset(_G, 'HD2WarCostLedgerV1', nil)
    f.module = dofile(addon_path)
    assert(type(f.module.task_layout_code_status) == 'function' and type(f.module.stop_task_layout_code_probe) == 'function')
    function f:status() return self.module.task_layout_code_status() end
    function f:apply(id, value)
        id = option_prefix .. id; assert(self.callbacks[id], 'public option missing: ' .. id)
        self.values[id] = value; self.callbacks[id](value, id)
    end
    function f:step(dt, manual)
        local before, code_before = self.native_bytes, self.code_bytes
        self.frame(dt or .1); self.now = self.now + (dt or .1)
        local bytes, code = self.native_bytes - before, self.code_bytes - code_before
        self.step_code_peak = math.max(self.step_code_peak, code)
        assert(code <= 4200, 'fixed reader exceeded its declared total read limit: ' .. code)
        assert(bytes <= (manual and 65536 or 4211), 'combined addon reads exceeded the active budget: ' .. bytes)
        assert(self:status().read_last <= 4200, 'public diagnostics must include every PIN and payload read')
        for path, file in pairs(self.files) do
            if path:gsub('\\', '/'):find('/ledger_task_layout_code_', 1, true) then assert(file.closed, 'code probe left a file open between ticks') end
        end
    end
    function f:tick(seconds, manual)
        for _ = 1, math.floor(seconds / .1 + 1e-9) do self:step(.1, manual) end
    end
    function f:until_status(predicate, maximum)
        for _ = 1, maximum or 100 do if predicate(self:status()) then return self:status() end; self:step(.1) end
        assert(predicate(self:status()), 'unexpected final code status: ' .. codec.encode(self:status()))
        return self:status()
    end
    function f:samples()
        local out = {}
        for path, file in pairs(self.files) do
            if path:gsub('\\', '/'):find('/ledger_task_layout_code_', 1, true) and path:sub(-5) == '.json'
                and path:sub(-11) ~= '.state.json' and path:sub(-12) ~= '.status.json' then
                out[#out + 1] = {path = path, data = codec.decode(table.concat(file.parts))}
            end
        end
        return out
    end
    return f
end
local function check(name, fn)
    local ok, why = pcall(fn); io.open = original_open
    assert(ok, name .. ': ' .. tostring(why)); tests = tests + 1; print('PASS ' .. name)
end

check('ship capture completes once within the 4 KiB budget and retires whole-tree scanning', function()
    local f = boot(); f:step(.1)
    assert(f.values[option_prefix .. 'auto_ui_probe'] == true)
    local retired = f.module.ui_tree_probe_status()
    assert(retired.status == 'retired' and retired.reason == 'TASK_UI_STRUCTURE_VERIFIED' and not retired.enabled)
    f:until_status(function(s) return s.done end)
    assert(not f.mission and not f.module.state.mission and f.module.state.total_cents == 0 and f.module.state.kills == nil)
    assert(f:status().read_peak <= 4096 and f.step_code_peak <= 4096)
    local samples = f:samples(); assert(#samples == 1 and samples[1].data.complete)
    assert(samples[1].data.read_budget == 4200 and samples[1].data.code_per_step == 4096)
    for _, chunk in ipairs(samples[1].data.chunks) do assert(chunk.requested <= 4096 and chunk.length <= 4096) end
    local bin = assert(f.files[samples[1].data.binary_path])
    assert(#table.concat(bin.parts) == 14336, 'complete fixed windows must contain exactly 14 KiB')
    local code = f.code_reads; f:tick(3); assert(f.code_reads == code, 'success must stop all later code reads')
end)

check('saved success survives addon reload without native reads or old evidence changes', function()
    local old = {ui_tree_probe_v1 = {attempts = {map_closed = 3}},
        ui_tree_probe_v2 = {attempts = {map_open = 3}}, ui_tree_probe_v3 = {retained = true}}
    local first = boot({data = copy(old)}); first:until_status(function(s) return s.done end)
    local second = boot({data = first.data, files = first.files}); second:tick(2)
    assert(second:status().done and second.code_reads == 0)
    assert(second.data.task_layout_code_v1, 'success needs independent cross-launch persistence')
    for key, value in pairs(old) do assert(codec.encode(second.data[key]) == codec.encode(value)) end
    for _, key in ipairs(second.writes) do assert(not key:match('^ui_tree_probe_v'), 'retired tree records must remain untouched') end
end)

check('persisted and public OFF add zero code reads while real combat statistics continue', function()
    local f = boot({disabled = true}); f:step(.1); f.mission = true; f:tick(2)
    assert(not f:status().enabled and f.code_reads == 0 and #f:samples() == 0)
    assert(f.module.state.shots == 2000 and f.module.state.kills == 12 and f.stat_reads > 0)
    f:apply('auto_ui_probe', true); f:until_status(function(s) return s.active end)
    local bytes = f.native_bytes; f:apply('auto_ui_probe', false)
    assert(f.native_bytes == bytes and not f:status().active)
    local code, stats = f.code_reads, f.stat_reads; f.shots, f.kills = 2001, 13; f:tick(1)
    assert(f.code_reads == code and f.stat_reads > stats and f.module.state.shots == 2001 and f.module.state.kills == 13)
end)

check('non-live worlds do not start or consume the fixed code capture', function()
    local f = boot({mode = 'offline'}); f:tick(2)
    assert(f.code_reads == 0 and #f:samples() == 0 and not f:status().active and not f:status().done)
    f.world.runtime.mode = nil; f:tick(1); assert(f.code_reads == 0)
    f.world.runtime.mode = 'live'; f:until_status(function(s) return s.done end)
    assert(f.code_reads > 0)
end)

check('queued and active manual capture take priority without overlapping code reads', function()
    local f = boot(); f:until_status(function(s) return s.active end)
    local reads, bytes = f.code_reads, f.native_bytes; f:apply('capture', 3)
    assert(f.native_bytes == bytes and not f:status().active)
    f.mission, f.map_open = true, true; f:tick(4.8)
    assert(f.module.capture_status() == 'queued' and f.code_reads == reads)
    local steps = 0
    repeat f:step(.1, true); steps = steps + 1; assert(steps < 120)
        assert(f.code_reads == reads, 'manual capture and code capture must never share a tick')
    until f.module.capture_status() == 'complete'
    assert(steps > 70 and f.module.state.kills == 12)
    local partial = false
    for _, sample in ipairs(f:samples()) do
        if not sample.data.complete and sample.data.error == 'TASK_CODE_MANUAL_PRIORITY' then partial = true end
    end
    assert(partial, 'manual priority must preserve a parseable incomplete code sample')
end)

check('world loss and explicit stop close partial evidence with no stale reads', function()
    local f = boot(); f:until_status(function(s) return s.active end)
    f.available = false; local bytes = f.native_bytes; f:step(.1)
    assert(f.native_bytes == bytes and not f:status().active)
    local samples = f:samples(); assert(#samples == 1 and not samples[1].data.complete)
    f:tick(1); assert(f.native_bytes == bytes)
    local g = boot(); g:until_status(function(s) return s.active end)
    bytes = g.native_bytes; g.module.stop_task_layout_code_probe('TASK_CODE_TEST_STOP')
    assert(g.native_bytes == bytes and not g:status().active)
    local reads = g.code_reads; g:tick(2); assert(g.code_reads == reads)
end)

check('two failed reads persist a finite limit without fabricating kills or bill', function()
    local f = boot(); f.fail_code, f.mission = true, true
    f:until_status(function(s) return not s.active and not s.done and (s.attempts or 0) >= 2 end, 200)
    assert(f:status().attempts == 2 and f.module.state.shots == 2000 and f.module.state.kills == 12
        and f.module.state.total_cents == 0)
    local reads = f.code_reads; f:tick(2); assert(f.code_reads == reads)
    local again = boot({files = f.files, data = f.data}); again:tick(2)
    assert(not again:status().done and again.code_reads == 0 and again:status().attempts == 2)
end)

check('a long frame still performs only one bounded code step', function()
    local f = boot(); f:until_status(function(s) return s.active end)
    f:step(.1) -- PIN phase, followed by the first payload phase.
    f:step(.1)
    assert(f:status().bytes_written == 0x800)
    local before = f.code_bytes; f:step(2)
    assert(f.code_bytes - before == 4096 and f:status().bytes_written == 0x1800 and not f:status().done,
        'a long frame must not catch up and dump all windows at once')
    f:until_status(function(s) return s.done end)
end)
print('Addon task-layout code integration tests: ' .. tests .. ' passed; actual built entry/reader, real caller pins and synthetic uncollected windows; game/FPS await real evidence.')
