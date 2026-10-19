-- Actual built entry, real MOM public model, and the existing production observer
-- integration. Only native boundaries are simulated by test_integration.lua.
local built, sdk, integration, mom_api = assert(arg[1]), assert(arg[2]), assert(arg[3]), assert(arg[4])
local actual_latest_sdk = arg[5]
local source_file = assert(io.open(integration, 'rb'))
local integration_source = source_file:read('*a'); source_file:close()
local mom_root = assert(mom_api:match('^(.*)[/\\]src[/\\]api%.lua$'))
local load_options, load_api = assert(loadfile(mom_root .. '/src/options.lua')), assert(loadfile(mom_api))
local Text = dofile(mom_root .. '/src/bingus_text.lua')
local original_open, original_rename, original_remove = io.open, os.rename, os.remove
local virtual_root, files = '/virtual-ledger-compat-mom/', {}
io.open = function(path, mode)
    if path:sub(1, #virtual_root) ~= virtual_root then return original_open(path, mode) end
    if mode == 'rb' then
        if not files[path] then return nil, 'fixture file absent' end
        return {read = function() return files[path] end, close = function() return true end}
    end
    assert(mode == 'wb')
    local buffer = ''
    return {write = function(_, text) buffer = buffer .. text; return true end,
        close = function() files[path] = buffer; return true end}
end
os.rename = function(from, to)
    if from:sub(1, #virtual_root) ~= virtual_root then return original_rename(from, to) end
    if not files[from] then return nil, 'fixture file absent' end
    files[to], files[from] = files[from], nil; return true
end
os.remove = function(path)
    if path:sub(1, #virtual_root) ~= virtual_root then return original_remove(path) end
    files[path] = nil; return true
end
local prefix = 'hd2_costs.war_cost_ledger.'
local function menu_fixture()
    local state = {mods = {}, refused = {}, refused_count = 0, options = {}, option_count = 0,
        values = {}, pending = {}, pending_count = 0, queued = {}, queued_any = false,
        saved = {}, callbacks = {}, revision = 0, dirty = false, save_timer = 0}
    local mom = {state = state, note = function() end,
        loader = {log_directory = virtual_root:sub(1, -2)},
        translation = {T = Text, tr = function(x) return x end},
        TEXT_TEMPLATE = 123, MAX_MODS = 112, MAX_ROWS = 32,
        descriptor = function(option) return option.sequence, {} end}
    load_options(mom); load_api(mom)
    return mom
end
local function reset()
    rawset(_G, 'HD2WarCostLedgerV1', nil)
    _G.ModOptionsMenu = nil
    for name in pairs(package.loaded) do
        if name:sub(1, 11) == 'hd2runtime/' or name == 'mods/skyeshade/hd2runtime' then
            package.loaded[name] = nil
        end
    end
    files = {}
end
-- The later version is a controlled API-identical fixture, not a claim that
-- arbitrary future Runtime versions are compatible.
local scenarios = {{version = '0.30.3', sdk = sdk}, {version = '0.30.4', sdk = sdk}}
if actual_latest_sdk then scenarios[#scenarios + 1] = {version = '0.40.1', sdk = actual_latest_sdk, actual_metadata = true} end
for _, scenario in ipairs(scenarios) do
    local version = scenario.version
    reset()
    local mom = menu_fixture()
    _G.ModOptionsMenu = mom.api
    local source, replacements = integration_source:gsub("version='0%.30%.3'", "version='" .. version .. "'")
    assert(replacements == 1, 'integration metadata fixture changed; review test')
    if scenario.actual_metadata then
        source, replacements = source:gsub("return {version='0%.40%.1'}", "return dofile(runtime_root .. '/domains/metadata.lua')")
        assert(replacements == 1, 'actual metadata fixture replacement failed')
    end
    source, replacements = source:gsub('state=dofile%(path%).state', [[
saved.compat_sentinel = {revision = 68, nested = {keep = 'untouched'}}
state=dofile(path).state
]])
    assert(replacements == 1, 'integration entry fixture changed; review test')
    source = source .. [[
assert(saved.compat_sentinel.revision == 68 and saved.compat_sentinel.nested.keep == 'untouched',
    'initialization or mission writes damaged unrelated stored data')
return {state = state, saved = saved}
]]
    arg = {built, scenario.sdk}
    local compiled = assert(loadstring(source, '@runtime-compat-integration-' .. version))
    local ok, result = pcall(compiled)
    assert(ok, 'Runtime ' .. version .. ': ' .. tostring(result))
    assert(mom.state.option_count == 19 and #mom.state.mods == 1,
        'built entry never registered actual MOM options for Runtime ' .. version)
    assert(mom.state.mods[1].id == 'hd2_costs.war_cost_ledger')
    assert(mom.state.options[prefix .. 'enabled'] and mom.state.options[prefix .. 'currency'])
    assert(mom.state.callbacks[prefix .. 'currency'] and #mom.state.callbacks[prefix .. 'currency'] == 1)
    local before_cost = result.state.total_cents
    mom.set_pending(prefix .. 'currency', 2)
    assert(mom.apply_pending() == 1 and result.saved.ui_settings.currency == 2,
        'MOM Apply did not reach built addon and saved setting')
    assert(result.state.total_cents == before_cost, 'display setting changed the raw ledger')
    assert(result.saved.last_mission and result.saved.combat_history,
        'production mission/career persistence did not run')
    print('PASS built Runtime ' .. version .. ': real MOM registration and Apply, production kill/class/ribbon/price observers, mission/career persistence')
end
local entry_prefix = assert(integration_source:match('^(.-)state=dofile%(path%).state'), 'integration entry marker missing')
local negative_cases = {
    {label = 'hd2.mod', mutation = [[
local real = package.preload['mods/skyeshade/hd2runtime']()
real.mod = nil; package.preload['mods/skyeshade/hd2runtime'] = function() return real end
]]},
    {label = 'hd2.ui.overlay', mutation = [[
local real = package.preload['mods/skyeshade/hd2runtime']()
real.ui.overlay = nil; package.preload['mods/skyeshade/hd2runtime'] = function() return real end
]]},
    {label = 'event_world.open', mutation = [[
local real = package.preload['hd2runtime/runtime/event_world']()
real.open = nil; package.preload['hd2runtime/runtime/event_world'] = function() return real end
]]},
    {label = 'dealt_kills', mutation = [[
native.stats.keys.dealt_kills = nil
]]},
    {label = 'mod.on_frame', mutation = [[mod.on_frame = nil]]},
    {label = 'mod.store', mutation = [[mod.store = nil]]},
    {label = 'store.set', mutation = [[store.set = nil]]},
    {label = 'overlay.show', mutation = [[overlay.show = nil]]},
}
for _, case in ipairs(negative_cases) do
    reset()
    local mom = menu_fixture(); _G.ModOptionsMenu = mom.api
    local source = entry_prefix:gsub("version='0%.30%.3'", "version='0.30.4'")
    source = source .. [[
saved.combat_history = {kills = 12345, preserve = {version = 'prior-save'}}
saved.mission_history = {version = 1, missions = {{id = 42, kills = 350}}}
local set_calls, save_calls = 0, 0
function store:set() set_calls = set_calls + 1 end
function store:save() save_calls = save_calls + 1 end
]] .. case.mutation .. '\n' .. [[
local ok, reason = pcall(dofile, path)
return {ok = ok, reason = reason, set_calls = set_calls, save_calls = save_calls,
    saved = saved, frame = frame, draw = draw}
]]
    arg = {built, sdk}
    local result = assert(loadstring(source, '@runtime-compat-missing-' .. case.label))()
    assert(not result.ok and tostring(result.reason):find(case.label, 1, true),
        'built missing capability diagnostic is not specific: ' .. case.label .. ': ' .. tostring(result.reason))
    assert(result.set_calls == 0 and result.save_calls == 0 and result.frame == nil and result.draw == nil
        and mom.state.option_count == 0 and rawget(_G, 'HD2WarCostLedgerV1') == nil,
        'missing required capability partially initialized addon or wrote an account')
    assert(result.saved.combat_history.kills == 12345 and result.saved.combat_history.preserve.version == 'prior-save'
        and result.saved.mission_history.missions[1].id == 42 and result.saved.mission_history.missions[1].kills == 350,
        'failed initialization damaged existing mission/career history')
end
print('PASS built missing required Runtime APIs stop with exact diagnostics before callbacks, MOM options, exports or account writes')
io.open, os.rename, os.remove = original_open, original_rename, original_remove
