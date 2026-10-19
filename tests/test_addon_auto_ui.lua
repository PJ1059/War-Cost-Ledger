-- Exercise the built entry and its actual automatic UI tree probe. Only the
-- Runtime/game memory, menu, store and file-system boundaries are fixtures.
-- No fixture file is written into the user's real Runtime mod_data directory.
local addon_path, runtime_path = assert(arg[1]), assert(arg[2])
local fixture_path = arg[3] or (assert(addon_path:match('^(.*)/dist/[^/]+$'), 'built addon must be under project/dist')
    .. '/tests/fixtures/ui-root-window-0.4.4.bin')
local fixture_file = assert(io.open(fixture_path, 'rb'))
local root_window = fixture_file:read('*a'); fixture_file:close()
assert(#root_window == 8192, 'use the actual 0.4.4 captured root window, never a fabricated instruction pin')
local root_node_path = arg[4] or (assert(addon_path:match('^(.*)/dist/[^/]+$'))
    .. '/tests/fixtures/ui-root-node-0.4.5.bin')
local root_node_file = assert(io.open(root_node_path, 'rb'))
local root_node = root_node_file:read('*a'); root_node_file:close()
assert(#root_node == 256, 'use the actual 0.4.5 captured root node as the root shape witness')
package.preload['hd2runtime/schemas/current'] = function() return dofile(runtime_path .. '/schemas/current.lua') end
package.preload['hd2runtime/runtime/log'] = function() return {emit = function() end} end
package.preload['hd2runtime/runtime/events'] = function() return {} end
package.preload['hd2runtime/runtime/mod_store'] = function() return dofile(runtime_path .. '/runtime/mod_store.lua') end
local codec = require('hd2runtime/runtime/mod_store')
local ffi = require('ffi')
local original_open, tests = io.open, 0
local prefix = 'hd2_costs.war_cost_ledger.'
local function copy(v)
    if type(v) ~= 'table' then return v end
    local out = {}; for k, x in pairs(v) do out[k] = copy(x) end; return out
end
local function canonical(v)
    if type(v) ~= 'table' then return v == nil and 'nil' or codec.encode(v) end
    local keys, out = {}, {}; for k in pairs(v) do keys[#keys + 1] = k end
    table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
    for _, k in ipairs(keys) do out[#out + 1] = '[' .. canonical(k) .. ']=' .. canonical(v[k]) end
    return '{' .. table.concat(out, ',') .. '}'
end
local function u32(n)
    local bytes = {}; for i = 1, 4 do bytes[i] = string.char(n % 256); n = math.floor(n / 256) end
    return table.concat(bytes)
end
local function pointer(n) return u32(n % 4294967296) .. u32(math.floor(n / 4294967296)) end
local function float(n)
    local value = ffi.new('float[1]', n); return ffi.string(value, 4)
end
local function patched(raw, offset, text) return raw:sub(1, offset) .. text .. raw:sub(offset + #text + 1) end
local function node(parent, child, sibling, context)
    local raw = string.rep('\0', 256)
    raw = patched(raw, 0, u32(0x40010))
    raw = patched(raw, 0x24, float(180)); raw = patched(raw, 0x28, float(40))
    raw = patched(raw, 0x64, float(1)); raw = patched(raw, 0x78, float(1))
    raw = patched(raw, 0x94, float(1200)); raw = patched(raw, 0x98, float(200))
    raw = patched(raw, 0xE0, pointer(child or 0)); raw = patched(raw, 0xE8, pointer(sibling or 0))
    raw = patched(raw, 0xF0, pointer(parent or 0)); return patched(raw, 0xF8, pointer(context))
end
local runtime_modules = {'mods/skyeshade/hd2runtime', 'hd2runtime/domains/metadata',
    'hd2runtime/domains/event_natives', 'hd2runtime/runtime/event_world',
    'hd2runtime/runtime/beacon_redirect', 'hd2runtime/runtime/stratagem_loadout'}
local function boot(options)
    options = options or {}
    local f = {data = options.data or {}, files = options.files or {}, writes = {}, messages = {},
        options = {}, values = {}, callbacks = {}, bindings = {}, now = 0,
        native_bytes = 0, native_reads = 0, large_reads = 0, queries = 0, stat_reads = 0,
        available = true, readable = true, native_readable = true, mission = false, map_open = false,
        shots = 2000, kills = 12, deaths = 0, frame_bytes = 0, peak = 0}
    if options.disabled then f.data.ui_settings = {auto_ui_probe = false} end
    local game, exe, hud, root, context = 0x10000000, 0x50000000, 0x20000000, 0x20000258, 0x40000000
    f.game, f.exe, f.hud, f.root = game, exe, hud, root
    local chunks, count = {}, options.nodes or 3
    local first = count > 1 and 0x30000200 or 0
    -- Preserve the captured root shape (kind 0). Pointer identities are rebased
    -- to isolated fixture allocations; descendants remain synthetic below.
    local fixture_root = patched(root_node, 0xE0, pointer(first))
    fixture_root = patched(fixture_root, 0xE8, pointer(0))
    fixture_root = patched(fixture_root, 0xF0, pointer(0))
    fixture_root = patched(fixture_root, 0xF8, pointer(context))
    chunks[#chunks + 1] = {root, fixture_root}
    chunks[#chunks + 1] = {hud + 0x24E340 + 0x60, node(root, 0, 0, context)}
    for i = 1, count - 1 do
        local at = 0x30000000 + i * 0x200
        chunks[#chunks + 1] = {at, node(root, 0, i < count - 1 and at + 0x200 or 0, context)}
    end
    -- The code window and root shape were saved by the game. Rebasing and the
    -- descendant tree are synthetic boundaries, not proof of a task identity.
    chunks[#chunks + 1] = {game + 0x12F0000, root_window}
    chunks[#chunks + 1] = {game + 0x346D538, pointer(hud)}
    local function read_memory(at, size)
        local raw = string.rep('\0', size)
        for _, chunk in ipairs(chunks) do
            local start, finish = math.max(at, chunk[1]), math.min(at + size, chunk[1] + #chunk[2])
            if start < finish then raw = patched(raw, start - at, chunk[2]:sub(start - chunk[1] + 1, finish - chunk[1])) end
        end
        return raw
    end
    local world = {game = game, exe = exe, key = 'fixture-world', view = {slot = function() return {} end}}
    f.world = world
    local function account(n)
        f.native_bytes, f.native_reads = f.native_bytes + n, f.native_reads + 1
    end
    if not options.old_mock then
        function world.view.pointer(at)
            account(8); assert(at == game + 0x346D538, 'pointer read outside the proven HUD global'); return hud
        end
        function world.view.read(at, size)
            account(size)
            if size == 1 then
                if not f.native_readable then return nil end
                if at == hud + 0x24E340 + 0x58 or at == hud + 0x24E340 + 0x21F5B0 then return string.char(f.mission and 1 or 0) end
                if at == hud + 0x3EF2FD then return string.char(f.map_open and 1 or 0) end
                error('unexpected single-byte native read')
            end
            f.large_reads = f.large_reads + 1
            assert((at >= hud and at + size <= hud + 0x480000)
                or (at >= game + 0x12E8000 and at + size <= game + 0x12F8000)
                or (at >= game + 0x143A000 and at + size <= game + 0x1452000)
                or (at >= 0x30000000 and at + size <= 0x30800000)
                or (at == game + 0x346D538 and size == 8), 'UI read outside the explicit fixture allocations')
            if f.fail_tree and at == root and size == 256 then return nil end
            return read_memory(at, size)
        end
        world.runtime = {query = function(at)
            f.queries = f.queries + 1
            if at >= hud and at < hud + 0x800000 then return {allocation_base = hud, base = hud, size = 0x800000, type = 0x20000, protect = 4, state = 0x1000} end
            if at >= game and at < game + 0x5000000 then return {allocation_base = game, base = game, size = 0x5000000, type = 0x1000000, protect = 0x20, state = 0x1000} end
            if at >= 0x30000000 and at < 0x30800000 then return {allocation_base = 0x30000000, base = 0x30000000, size = 0x800000, type = 0x20000, protect = 4, state = 0x1000} end
            error('unexpected region query')
        end}
    end
    io.open = function(path, mode)
        assert(type(path) == 'string' and path:gsub('\\', '/'):find('/ledger_ui_', 1, true), 'probe must only open its own evidence files')
        if mode == 'rb' then
            local item = f.files[path]; if not item then return nil, 'fixture file absent' end
            return {read = function(self, n)
                local text = table.concat(item.parts); return type(n) == 'number' and text:sub(1, n) or text
            end, close = function() return true end}
        end
        assert(mode == 'wb' or mode == 'ab', 'unexpected file access mode')
        if mode == 'ab' then assert(f.files[path], 'append requires an existing owned evidence file') end
        assert(mode == 'ab' or not f.files[path] or path:sub(-11) == '.state.json'
            or path:sub(-12) == '.status.json' or path:sub(-10) == '.done.json',
            'sample evidence must never be overwritten')
        local item = mode == 'ab' and f.files[path] or {parts = {}}
        item.closed = false; f.files[path] = item
        return {write = function(self, text) assert(type(text) == 'string'); item.parts[#item.parts + 1] = text; return self end,
            flush = function() return true end,
            close = function() item.closed = true; return true end}
    end
    local store = {}
    function store:get(key, fallback) return copy(f.data[key] == nil and fallback or f.data[key]) end
    function store:set(key, value) f.data[key] = copy(value); f.writes[#f.writes + 1] = key end
    function store:save() return true end
    local mod = {}
    function mod:store() return store end
    function mod:log(text) f.messages[#f.messages + 1] = tostring(text) end
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
    package.preload['hd2runtime/domains/event_natives'] = function() return {stats = {keys = {projectiles_fired = 1, dealt_kills = 2, received_deaths = 3, projectiles_hit = 4}}} end
    package.preload['hd2runtime/runtime/event_world'] = function()
        return {open = function() return f.available and world or nil end,
            game_state = function() return f.readable and {mission = f.mission} or nil end,
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
    local menu = {api = 1, version = 3, ready = function() return false end}
    function menu.register_option(id, spec) assert(not f.options[id]); f.options[id], f.values[id] = spec, spec.default; return true end
    function menu.get(id) return f.values[id] end
    function menu.set(id, value) assert(f.options[id]); f.values[id] = value; return true end
    function menu.on_change(id, cb) assert(f.options[id]); f.callbacks[id] = cb; return true end
    rawset(_G, 'ModOptionsMenu', menu); rawset(_G, 'HD2WarCostLedgerV1', nil)
    f.module = dofile(addon_path)
    assert(type(f.module.ui_tree_probe_status) == 'function', 'addon must export its actual probe status')
    function f:status() return self.module.ui_tree_probe_status() end
    function f:apply(id, value)
        id = prefix .. id; assert(self.callbacks[id], 'public option missing: ' .. id)
        self.values[id] = value; self.callbacks[id](value, id)
    end
    function f:step(dt, budget)
        local before = self.native_bytes; self.frame(dt or .1); self.now = self.now + (dt or .1)
        self.frame_bytes = self.native_bytes - before; self.peak = math.max(self.peak, self.frame_bytes)
        assert(self.frame_bytes <= (budget or 16384), 'addon UI reads exceed the combined step budget: ' .. self.frame_bytes)
        local status = self:status()
        assert((status.nodes_last or 0) <= 16, 'automatic probe processed more than 16 tree nodes in one step')
        assert((status.operations_last or 0) <= 32, 'automatic probe processed more than 32 operations in one step')
    end
    function f:tick(seconds, budget)
        local whole = math.floor(seconds / .1 + 1e-9); for _ = 1, whole do self:step(.1, budget) end
        local tail = seconds - whole * .1; if tail > 1e-9 then self:step(tail, budget) end
    end
    function f:until_status(predicate, maximum, budget)
        for _ = 1, maximum or 100 do if predicate(self:status()) then return self:status() end; self:step(.1, budget) end
        assert(predicate(self:status()), 'expected bounded probe outcome; got ' .. canonical(self:status()))
        return self:status()
    end
    function f:samples()
        local out = {}
        for path, item in pairs(self.files) do
            if path:sub(-5) == '.json' and path:sub(-11) ~= '.state.json'
                and path:sub(-10) ~= '.done.json' and path:sub(-12) ~= '.status.json' then
                assert(item.closed, 'evidence metadata left open')
                out[#out + 1] = {path = path, data = codec.decode(table.concat(item.parts))}
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

check('default automatic probe waits for actual mission even after 120 seconds', function()
    local f = boot(); f:step(.1)
    assert(f.values[prefix .. 'auto_ui_probe'] == true and f:status().enabled)
    f:tick(121)
    assert(f.large_reads == 0 and (f:status().attempts.map_closed or 0) == 0
        and (f:status().status == 'waiting_mission' or f:status().status == 'waiting_for_mission'))
    f.mission = true; f:step(.1)
    assert(f.module.state.shots == 2000 and f.module.state.kills == 12 and f.overlay.visible)
    local done = f:until_status(function(s) return s.done.map_closed end, 100)
    assert(done.attempts.map_closed == 1 and not done.done.map_open and done.read_peak <= 16373)
    assert(done.max_nodes_per_step == 16 and done.max_operations_per_step == 32 and done.soft_budget_ms == 2,
        'published diagnostics must disclose the real operation limits and soft time checkpoint')
    local samples = f:samples(); assert(#samples == 1 and samples[1].data.summary.complete)
    assert(samples[1].data.summary.self_root_corroborated and #samples[1].data.nodes == 3)
    local pin = samples[1].data.summary.source_pin
    assert(pin.rva == 0x12F133A and pin.length == 22 and pin.hud_global == 0x346D538
        and pin.root_offset == 0x258 and pin.widget_attach == 0x144C5C0,
        'actual captured code must prove the HUD global, root offset and widget attach target together')
    local large, bytes = f.large_reads, f.native_bytes; f:tick(3)
    assert(f.large_reads == large and f.native_bytes - bytes == 30 * 11, 'completed mode must stop all tree reads')
    f.map_open = true
    f:until_status(function(s) return s.done.map_closed and s.done.map_open end, 100)
    assert(f:status().attempts.map_open == 1 and #f:samples() == 2)
    large, bytes = f.large_reads, f.native_bytes; f:tick(3)
    assert(f.large_reads == large and f.native_bytes - bytes == 30 * 11)
end)

check('both successful samples persist and never rescan after addon reload', function()
    local first = boot(); first.mission = true; first:until_status(function(s) return s.done.map_closed end, 100)
    first.map_open = true; first:until_status(function(s) return s.done.map_open end, 100)
    local count = #first:samples()
    local second = boot({files = first.files, data = first.data}); second.mission = true; second:tick(3)
    assert(second:status().done.map_closed and second:status().done.map_open and second:status().status == 'complete')
    assert(second.large_reads == 0 and #second:samples() == count and second.module.state.kills == 12)
    assert(second.data.ui_tree_probe_v3 and second.data.ui_tree_probe_v1 == nil and second.data.ui_tree_probe_v2 == nil)
end)

check('old v1 exhausted attempts do not block v3 or modify old evidence', function()
    local old = {format = 'HD2-UI-TREE-STATE-1',
        build = 'F5FEE03DCFDB2E553A4752C283590950AC13316B376D8196AA556FF0400D5F06',
        dll_sha = '2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E',
        attempts = {map_closed = 3, map_open = 3}, saved = {}}
    local base = assert(os.getenv('LOCALAPPDATA')) .. '/HD2Runtime/mod_data/ledger_ui_tree_F5FEE03DCFDB'
    local data, files = {ui_tree_probe_v1 = copy(old)}, {}
    files[base .. '.state.json'] = {parts = {codec.encode(old)}, closed = true}
    files[base .. '_old_map_closed_1_1.bin'] = {parts = {root_window}, closed = true}
    files[base .. '_old_map_closed_1_1.json'] = {parts = {codec.encode({format = 'HD2-UI-TREE-1',
        nodes = {}, summary = {complete = false, error = 'UI_TREE_ROOT_PIN_NOT_UNIQUE'}})}, closed = true}
    files[base .. '_old_map_closed_1_1.status.json'] = {parts = {codec.encode({complete = false,
        error = 'UI_TREE_ROOT_PIN_NOT_UNIQUE', mode = 'map_closed'})}, closed = true}
    local preserved = {}; for path, file in pairs(files) do preserved[path] = table.concat(file.parts) end
    local f = boot({data = data, files = files}); f.mission = true
    f:until_status(function(s) return s.done.map_closed end, 100)
    assert(f:status().attempts.map_closed == 1 and f:status().attempts.map_open == 0,
        'new witnessed source revision needs its own bounded attempt history')
    assert(canonical(f.data.ui_tree_probe_v1) == canonical(old) and f.data.ui_tree_probe_v3)
    for path, contents in pairs(preserved) do assert(table.concat(f.files[path].parts) == contents and f.files[path].closed) end
    for _, key in ipairs(f.writes) do assert(key ~= 'ui_tree_probe_v1', 'legacy state must remain untouched') end
    assert(f:status().last_path:find('/ledger_ui_tree_v3_F5FEE03DCFDB_', 1, true), 'v3 artifacts need a distinct prefix')
end)

check('old v2 exhausted attempts and root-invalid samples remain untouched by v3', function()
    local old = {format = 'HD2-UI-TREE-STATE-2', source_revision = 'root_attach_v2',
        build = 'F5FEE03DCFDB2E553A4752C283590950AC13316B376D8196AA556FF0400D5F06',
        dll_sha = '2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E',
        attempts = {map_closed = 3, map_open = 3}, saved = {}}
    local base = assert(os.getenv('LOCALAPPDATA')) .. '/HD2Runtime/mod_data/ledger_ui_tree_v2_F5FEE03DCFDB'
    local data, files = {ui_tree_probe_v2 = copy(old)}, {}
    files[base .. '.state.json'] = {parts = {codec.encode(old)}, closed = true}
    files[base .. '_old_map_closed_3_3.bin'] = {parts = {root_window, root_node}, closed = true}
    files[base .. '_old_map_closed_3_3.json'] = {parts = {codec.encode({format = 'HD2-UI-TREE-2',
        source_revision = 'root_attach_v2', nodes = {},
        summary = {complete = false, error = 'UI_TREE_ROOT_INVALID'}})}, closed = true}
    files[base .. '_old_map_closed_3_3.status.json'] = {parts = {codec.encode({complete = false,
        error = 'UI_TREE_ROOT_INVALID', mode = 'map_closed'})}, closed = true}
    local preserved = {}; for path, file in pairs(files) do preserved[path] = table.concat(file.parts) end
    local f = boot({data = data, files = files}); f.mission = true
    f:until_status(function(s) return s.done.map_closed end, 100)
    assert(f:status().attempts.map_closed == 1 and f:status().attempts.map_open == 0)
    assert(canonical(f.data.ui_tree_probe_v2) == canonical(old) and f.data.ui_tree_probe_v3)
    for path, contents in pairs(preserved) do assert(table.concat(f.files[path].parts) == contents and f.files[path].closed) end
    for _, key in ipairs(f.writes) do assert(key ~= 'ui_tree_probe_v2', 'legacy v2 state must remain untouched') end
    assert(f:status().last_path:find('/ledger_ui_tree_v3_F5FEE03DCFDB_', 1, true))
end)

check('persisted OFF and public OFF cause zero extra reads while statistics continue', function()
    local f = boot({disabled = true}); f.mission = true; f:tick(3)
    assert(not f:status().enabled and f:status().status == 'disabled' and f.large_reads == 0)
    assert(f.module.state.shots == 2000 and f.module.state.kills == 12 and f.stat_reads > 0)
    f:apply('auto_ui_probe', true); f:until_status(function(s) return s.active end, 30)
    local before = f.native_bytes; f:apply('auto_ui_probe', false)
    assert(f.native_bytes == before and not f:status().active and f:status().status == 'disabled', 'disabling must cancel without another native read')
    local large, stats = f.large_reads, f.stat_reads; f.shots, f.kills = 2001, 13; f:tick(1)
    assert(f.large_reads == large and f.stat_reads > stats and f.module.state.shots == 2001 and f.module.state.kills == 13)
    local samples = f:samples(); assert(#samples == 1 and not samples[1].data.summary.complete)
end)

check('F8 and ship UI preview do not control or corrupt automatic/statistical sampling', function()
    local f = boot(); f:step(.1); f:apply('preview', 4); f:tick(1)
    assert(f.large_reads == 0 and f.module.state.kills == nil and f.overlay.visible)
    f.mission = true; f:step(.1); f:apply('enabled', false)
    local before = f.stat_reads; f:until_status(function(s) return s.done.map_closed end, 100)
    assert(f.stat_reads > before and f.module.state.kills == 12 and f:status().done.map_closed)
    f:tick(8); assert(not f.overlay.visible and f.module.state.shots == 2000)
end)

check('manual request cancels partial auto evidence and owns the complete 64 KiB budget', function()
    local f = boot(); f.mission = true; f:until_status(function(s) return s.active end, 30)
    local before = f.native_bytes; f:apply('capture', 2)
    assert(f.native_bytes == before, 'manual priority cancellation must add zero reads')
    f:step(.1); assert(not f:status().active)
    local large, attempts = f.large_reads, f:status().attempts.map_closed
    f:tick(4.7); assert(f.module.capture_status() == 'queued' and f.large_reads == large)
    local steps = 0
    repeat f:step(.1, 65536); steps = steps + 1; assert(steps < 100) until f.module.capture_status() == 'complete'
    assert(steps > 70 and f:status().attempts.map_closed == attempts,
        'automatic probe must stay paused during deferred/active manual capture')
    local partial = false
    for _, sample in ipairs(f:samples()) do
        if sample.data.format == 'HD2-UI-TREE-3' and sample.data.source_revision == 'root_base_v3' then
            partial = not sample.data.summary.complete and sample.data.summary.error == 'UI_TREE_MANUAL_PRIORITY'
        end
    end
    assert(partial, 'manual priority must leave partial automatic evidence')
end)

check('tree short reads have finite persistent attempts and never invent combat results', function()
    local f = boot(); f.mission, f.fail_tree = true, true; f:step(.1)
    local real = {shots = f.module.state.shots, kills = f.module.state.kills, bill = f.module.state.total_cents,
        ribbons = canonical(f.module.state.ribbons), medals = canonical(f.module.state.mission_medals)}
    f:until_status(function(s) return s.status == 'exhausted' end, 150)
    assert(f:status().attempts.map_closed == 3 and not f:status().done.map_closed and #f:samples() == 3)
    for _, sample in ipairs(f:samples()) do assert(not sample.data.summary.complete and sample.data.summary.error) end
    assert(f.module.state.shots == real.shots and f.module.state.kills == real.kills and f.module.state.total_cents == real.bill)
    assert(canonical(f.module.state.ribbons) == real.ribbons and canonical(f.module.state.mission_medals) == real.medals)
    local large = f.large_reads; f:tick(5); assert(f.large_reads == large)
    local reloaded = boot({data = f.data, files = f.files}); reloaded.mission = true; reloaded:tick(2)
    assert(reloaded:status().attempts.map_closed == 3 and reloaded:status().status == 'exhausted' and reloaded.large_reads == 0)
end)

check('long frames never catch up with multiple automatic scans', function()
    local f = boot({nodes = 200}); f.mission = true; f:until_status(function(s) return s.active end, 30)
    local before = f:status().attempts.map_closed; f:step(1)
    assert(f.frame_bytes <= 16384 and f:status().attempts.map_closed == before)
    f:until_status(function(s) return s.done.map_closed end, 100)
    assert(f:status().nodes == 200)
end)

check('each automatic step closes files and leaves a valid incomplete exit witness', function()
    local f = boot({nodes = 200}); f.mission = true; f:until_status(function(s) return s.active end, 30)
    local status_files, samples = 0, 0
    for path, file in pairs(f.files) do
        assert(file.closed, 'automatic probe must flush and close handles before returning to the game')
        if path:sub(-12) == '.status.json' then
            status_files = status_files + 1
            local evidence = codec.decode(table.concat(file.parts))
            assert(evidence.complete == false and evidence.error and evidence.mode == 'map_closed',
                'unexpected process exit must leave a parseable incomplete witness')
        elseif path:sub(-4) == '.bin' then samples = samples + 1 end
    end
    assert(status_files == 1 and samples == 1 and not f:status().done.map_closed)
    f.module.stop_ui_tree_probe('UI_TREE_SHUTDOWN')
end)

check('world loss cancels partial evidence and never reads stale world memory', function()
    local f = boot({nodes = 200}); f.mission = true; f:until_status(function(s) return s.active end, 30)
    f.available = false; local before = f.native_bytes; f:step(.1)
    assert(f.native_bytes == before and not f:status().active and not f.overlay.visible)
    local samples = f:samples(); assert(#samples == 1 and not samples[1].data.summary.complete and samples[1].data.summary.error)
    f:tick(2); assert(f.native_bytes == before)
end)

check('explicit shutdown cleanup cancels active evidence with no native reads', function()
    local f = boot(); f.mission = true; f:until_status(function(s) return s.active end, 30)
    local before = f.native_bytes; assert(type(f.module.stop_ui_tree_probe) == 'function')
    f.module.stop_ui_tree_probe('UI_TREE_SHUTDOWN')
    assert(f.native_bytes == before and not f:status().active)
    local samples = f:samples(); assert(#samples == 1 and not samples[1].data.summary.complete and samples[1].data.summary.error)
end)

check('older Runtime mocks lacking native UI APIs keep combat statistics usable', function()
    local f = boot({old_mock = true}); f.mission = true; f:tick(3)
    assert(f.native_bytes == 0 and f.large_reads == 0 and (f:status().attempts.map_closed or 0) == 0 and not f:status().active)
    assert(f.module.state.shots == 2000 and f.module.state.kills == 12 and f.stat_reads > 0)
end)
print('Addon automatic UI integration tests: ' .. tests .. ' passed; captured code/root shape with rebased pointers and synthetic descendants; task identity/FPS await a game session.')
