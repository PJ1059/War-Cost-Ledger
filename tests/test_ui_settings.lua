-- Exercises real ledger settings and MOM's real public API/options model.
-- Only descriptor allocation, logging and file IO are mocked; no native UI or game reads.
local create = dofile(assert(arg[1], 'ui-settings.lua required'))
local api_source = assert(arg[2], 'ModOptionsMenu/src/api.lua required')
local mom_root = assert(api_source:match('^(.*)[/\\]src[/\\]api%.lua$'), 'MOM component root required')
local load_options = assert(loadfile(mom_root .. '/src/options.lua'))
local load_api = assert(loadfile(api_source))
local Text = dofile(mom_root .. '/src/bingus_text.lua')
local PREFIX = 'hd2_costs.war_cost_ledger.'
local STORE_KEYS = {ui_settings = true, hud_enabled = true}
local EXPECTED = {'enabled', 'billing_enabled', 'currency', 'scale_percent', 'opacity_percent', 'right_margin', 'top_margin',
    'ribbon_mode','hit_position','charge_position','kill_source_enabled', 'move_tasks', 'task_gap', 'auto_ui_probe', 'career_ship_sync', 'career_page_sync', 'preview', 'capture','code_copy_test'}
local files, file_writes, game_reads = {}, 0, 0
local REAL_OPEN, REAL_RENAME, REAL_REMOVE = io.open, os.rename, os.remove
local FILE_ROOT = '/virtual-ledger-mom-test/'
io.open = function(path, mode)
    assert(path:sub(1, #FILE_ROOT) == FILE_ROOT, 'no real file IO permitted')
    if mode == 'rb' then
        if not files[path] then return nil, 'missing fixture' end
        return {read = function() return files[path] end, close = function() return true end}
    end
    assert(mode == 'wb'); file_writes = file_writes + 1
    local buffer = ''
    return {write = function(_, text) buffer = buffer .. text; return true end,
            close = function() files[path] = buffer; return true end}
end
os.rename = function(from, to)
    assert(from:sub(1, #FILE_ROOT) == FILE_ROOT and to:sub(1, #FILE_ROOT) == FILE_ROOT)
    if not files[from] then return nil, 'missing fixture' end
    files[to], files[from] = files[from], nil; return true
end
os.remove = function(path)
    assert(path:sub(1, #FILE_ROOT) == FILE_ROOT); files[path] = nil; return true
end
local function clone(value)
    if type(value) ~= 'table' then return value end
    local out = {}; for k, v in pairs(value) do out[k] = clone(v) end; return out
end
local function fresh(saved_store, saved_menu, career_status)
    _G.ModOptionsMenu = nil
    local notes, logs, writes, sets, registrations, actions, changes = {}, {}, {}, {}, {}, {}, {}
    local state = {mods = {}, refused = {}, refused_count = 0, options = {}, option_count = 0,
        values = {}, pending = {}, pending_count = 0, queued = {}, queued_any = false,
        saved = clone(saved_menu or {}), callbacks = {}, revision = 0, dirty = false, save_timer = 0}
    local mom = {state = state, note = function(text) notes[#notes + 1] = text end,
        loader = {log_directory = FILE_ROOT:sub(1, -2)}, translation = {T = Text, tr = function(x) return x end},
        TEXT_TEMPLATE = 123, MAX_MODS = 112, MAX_ROWS = 32,
        descriptor = function(option) return option.sequence, {} end}
    load_options(mom); load_api(mom)
    local menu, real_set, real_register = mom.api, mom.api.set, mom.api.register_option
    menu.set = function(id, value) sets[#sets + 1] = {id = id, value = value}; return real_set(id, value) end
    menu.register_option = function(id, spec)
        registrations[#registrations + 1] = {id = id, spec = clone(spec)}
        return real_register(id, spec)
    end
    local data = clone(saved_store or {})
    local store = {get = function(_, key, default)
        assert(STORE_KEYS[key], 'settings read an unrelated store key')
        if data[key] == nil then return clone(default) end
        return clone(data[key])
    end, set = function(_, key, value)
        assert(STORE_KEYS[key], 'settings wrote real combat statistics')
        data[key] = clone(value); writes[#writes + 1] = {key = key, value = clone(value)}
    end}
    local mod = {log = function(_, text) logs[#logs + 1] = text end,
        read = function() game_reads = game_reads + 1; error('settings must not read game memory') end}
    local settings = create(mod, store, {
        career_status = career_status,
        preview = function(value) actions[#actions + 1] = {'preview', value} end,
        capture = function(value) actions[#actions + 1] = {'capture', value} end,
        code_copy_test = function(value) actions[#actions + 1] = {'code_copy_test', value} end,
        changed = function(config, id) changes[#changes + 1] = {id = id, config = clone(config)} end})
    return {settings = settings, menu = menu, mom = mom, state = state, notes = notes, logs = logs,
        writes = writes, sets = sets, registrations = registrations, actions = actions, changes = changes, data = data}
end
local function publish(f)
    _G.ModOptionsMenu = f.menu; f.settings:update(0.5)
    assert(f.settings.status == 'registered', 'public MOM registration failed')
end
local function apply(f, id, value)
    assert(f.state.options[PREFIX .. id], 'unregistered option')
    f.mom.set_pending(PREFIX .. id, value)
    return f.mom.apply_pending()
end

-- Saved false stays false. Action choices remembered by either store never run at startup.
local f = fresh({hud_enabled = false, ui_settings = {move_tasks = false, auto_ui_probe = false, preview = 3, capture = 4,code_copy_test=2,
        legacy_preference = {enabled = false, value = 7}}},
    {[PREFIX .. 'enabled'] = 'false', [PREFIX .. 'move_tasks'] = 'false',
     [PREFIX .. 'preview'] = '3', [PREFIX .. 'capture'] = '4',[PREFIX..'code_copy_test']='2'})
assert(f.settings.config.enabled == false, 'saved HUD false lost before menu registration')
assert(f.settings.config.move_tasks == false, 'saved move_tasks=false became true')
assert(f.settings.config.auto_ui_probe == false, 'saved automatic probe=false became true')
assert(#f.actions == 0 and f.settings.values.preview == 1 and f.settings.values.capture == 1)
publish(f)
assert(#f.registrations == #EXPECTED and f.state.option_count == #EXPECTED and #f.state.mods == 1)
assert(f.state.mods[1].id == 'hd2_costs.war_cost_ledger' and f.state.mods[1].title == '战果与战争账单')
for index, id in ipairs(EXPECTED) do
    local registration = f.registrations[index]
    assert(registration.id == PREFIX .. id and f.settings.registered[id])
    assert(registration.spec.mod == '战果与战争账单' and registration.spec.mod_id == 'hd2_costs.war_cost_ledger')
    assert(registration.spec.label:find('[\128-\255]') and Text.check(registration.spec.label))
    assert(f.state.callbacks[PREFIX .. id] and #f.state.callbacks[PREFIX .. id] == 1)
end
assert(f.settings.config.enabled == false and f.settings.config.move_tasks == false)
assert(#f.actions == 0 and f.menu.get(PREFIX .. 'preview') == 1 and f.menu.get(PREFIX .. 'capture') == 1)
assert(#f.sets == 5, 'startup resets three actions and migrates two stock insets')
for _, set in ipairs(f.sets) do assert((set.value == 1 and (set.id == PREFIX .. 'preview' or set.id == PREFIX .. 'capture' or set.id==PREFIX..'code_copy_test')) or (set.value==0 and (set.id==PREFIX..'right_margin' or set.id==PREFIX..'top_margin'))) end
assert(f.settings.config.currency == 'SC' and f.settings.values.currency == 1)
assert(f.registrations[3].spec.label == '账单显示币种')
assert(f.registrations[3].spec.description == '选择战争账单的显示币种。SC按1 SC＝1 USD折算，仅为本MOD的虚拟军费显示规则。' and Text.check(f.registrations[3].spec.description))
assert(f.registrations[3].spec.choices[1] == 'SC（超级货币）' and #f.registrations[3].spec.choices == 6)
assert(f.settings.values.code_copy_test==1 and f.menu.get(PREFIX..'code_copy_test')==1)
print('PASS: '..#EXPECTED..' Chinese options use real MOM v1.2 API/model in one category; false preferences preserved; saved actions reset without firing')
local migrated=fresh({ui_settings={right_margin=18,top_margin=18}}, {[PREFIX..'right_margin']='18',[PREFIX..'top_margin']='18'})
publish(migrated)
assert(migrated.settings.config.right_margin==0 and migrated.settings.config.top_margin==0)
assert(migrated.menu.get(PREFIX..'right_margin')==0 and migrated.data.ui_settings.layout_revision=='hud-common-right-edge-v6')
local custom=fresh({ui_settings={right_margin=42,top_margin=30}})
publish(custom)
assert(custom.settings.config.right_margin==42 and custom.settings.config.top_margin==30)
local once=fresh({ui_settings={right_margin=18,top_margin=18,layout_revision='hud-common-right-edge-v6'}})
publish(once)
assert(once.settings.config.right_margin==18 and once.settings.config.top_margin==18)
print('PASS: native edge migration runs once, custom offsets preserved, obsolete side offsets not registered')
local dynamic_text = '等待打开完整生涯统计页。'
local dynamic = fresh(nil,nil,function() return dynamic_text end)
publish(dynamic)
local career_option = dynamic.state.options[PREFIX .. 'career_page_sync']
assert(type(career_option.sources.description)=='function' and career_option.description==dynamic_text)
dynamic_text = '最近同步：351849杀 / 4633阵亡，KD75.94。'
local saved_before = #dynamic.writes
dynamic.mom.translation.refresh()
assert(career_option.description==dynamic_text and #dynamic.writes==saved_before)
print('PASS: public MOM function description refreshes latest career totals on menu open, without a preference write')

-- Edits wait for public Apply. Programmatic set intentionally does not invoke on_change.
f.mom.set_pending(PREFIX .. 'scale_percent', 115)
assert(f.settings.config.scale == 1 and f.menu.get(PREFIX .. 'scale_percent') == 100)
assert(f.mom.apply_pending() == 1 and f.settings.config.scale == 1.15)
assert(f.data.ui_settings.scale_percent == 115 and f.data.ui_settings.move_tasks == false)
assert(f.data.ui_settings.preview == nil and f.data.ui_settings.capture == nil and f.data.ui_settings.enabled == nil)
local before_changes, before_sets = #f.changes, #f.sets
assert(f.menu.set(PREFIX .. 'scale_percent', 120))
assert(#f.changes == before_changes and f.settings.config.scale == 1.15, 'MOM set must not act like player Apply')
assert(apply(f, 'scale_percent', 125) == 1 and f.settings.config.scale == 1.25)
assert(#f.sets == before_sets + 1, 'Apply callback mirrored into MOM a second time')
assert(apply(f, 'enabled', true) == 1 and f.settings.config.enabled == true and f.data.hud_enabled == true)
assert(apply(f, 'enabled', false) == 1 and f.settings.config.enabled == false and f.data.hud_enabled == false)
assert(apply(f, 'move_tasks', true) == 1 and f.settings.config.move_tasks == true)
assert(apply(f, 'move_tasks', false) == 1 and f.settings.config.move_tasks == false)
assert(f.settings.config.kill_source_enabled == true, 'new kill source display must default on')
assert(apply(f, 'kill_source_enabled', false) == 1 and f.settings.config.kill_source_enabled == false)
assert(f.data.ui_settings.kill_source_enabled == false and f.changes[#f.changes].id == 'kill_source_enabled')
local hidden_source = fresh(f.data, f.state.saved)
assert(hidden_source.settings.config.kill_source_enabled == false, 'saved display false must stay false before menu')
publish(hidden_source)
assert(hidden_source.settings.config.kill_source_enabled == false and hidden_source.menu.get(PREFIX .. 'kill_source_enabled') == false)
_G.ModOptionsMenu = f.menu
assert(apply(f, 'kill_source_enabled', true) == 1 and f.settings.config.kill_source_enabled == true)
assert(f.data.ui_settings.kill_source_enabled == true)
assert(apply(f, 'auto_ui_probe', true) == 1 and f.settings.config.auto_ui_probe == true)
assert(apply(f, 'auto_ui_probe', false) == 1 and f.settings.config.auto_ui_probe == false)
assert(f.data.ui_settings.auto_ui_probe == false)
assert(f.settings.config.career_page_sync == true)
assert(apply(f, 'career_page_sync', false) == 1 and f.settings.config.career_page_sync == false)
assert(f.data.ui_settings.career_page_sync == false)
assert(apply(f, 'career_page_sync', true) == 1 and f.settings.config.career_page_sync == true)
assert(f.settings.config.career_ship_sync == true)
assert(apply(f, 'career_ship_sync', false) == 1 and f.settings.config.career_ship_sync == false)
assert(f.data.ui_settings.career_ship_sync == false)
assert(apply(f, 'career_ship_sync', true) == 1 and f.settings.config.career_ship_sync == true)
print('PASS: real pending/apply callbacks persist settings including false; programmatic MOM set has no callbacks')

-- Currency waits for Apply, maps to display codes, and keeps unrelated stored options.
local currencies = {'SC', 'USD', 'CNY', 'EUR', 'GBP', 'SEK'}
f.data.ui_settings.other_option_added_later = 'keep'
for index = 2, #currencies do
    local before = f.settings.config.currency
    f.mom.set_pending(PREFIX .. 'currency', index)
    assert(f.settings.config.currency == before and f.menu.get(PREFIX .. 'currency') == index - 1)
    assert(f.mom.apply_pending() == 1 and f.settings.config.currency == currencies[index])
    assert(f.data.ui_settings.currency == index and f.data.ui_settings.move_tasks == false)
    assert(f.data.ui_settings.legacy_preference.enabled == false and f.data.ui_settings.legacy_preference.value == 7)
    assert(f.data.ui_settings.other_option_added_later == 'keep')
    assert(f.data.ui_settings.enabled == nil and f.data.ui_settings.preview == nil and f.data.ui_settings.capture == nil)
end
local restored = fresh(f.data, f.state.saved)
assert(restored.settings.config.currency == 'SEK')
publish(restored)
assert(restored.settings.config.currency == 'SEK' and restored.menu.get(PREFIX .. 'currency') == 6)
local invalid_saved = fresh({ui_settings = {currency = 7}})
assert(invalid_saved.settings.config.currency == 'SC')
publish(invalid_saved)
assert(invalid_saved.registrations[3].spec.description == '选择战争账单的显示币种。SC按1 SC＝1 USD折算，仅为本MOD的虚拟军费显示规则。')
_G.ModOptionsMenu = f.menu
assert(apply(f, 'currency', 1) == 1 and f.settings.config.currency == 'SC')
for _,legacy in ipairs({1,'MC','SC'}) do
    local old=fresh({ui_settings={currency=legacy}})
    assert(old.settings.config.currency=='SC' and old.settings.values.currency==1)
    publish(old);assert(old.settings.config.currency=='SC' and old.menu.get(PREFIX..'currency')==1)
end
for index=2,6 do
    local explicit=fresh({ui_settings={currency=index}}, {[PREFIX..'currency']=tostring(index)})
    publish(explicit);assert(explicit.settings.config.currency==currencies[index], 'explicit real currency was reset to SC')
end
_G.ModOptionsMenu=f.menu
print('PASS: six currency codes change only after real MOM Apply, restore from both stores, and retain legacy settings; concise function description verified')

-- F8 mirrors one public set, saves only hud_enabled, and withdraws an unapplied menu edit.
f.mom.set_pending(PREFIX .. 'enabled', true)
before_sets, before_changes = #f.sets, #f.changes
local before_writes = #f.writes
assert(f.settings:toggle_enabled() == true)
assert(#f.sets == before_sets + 1 and f.sets[#f.sets].id == PREFIX .. 'enabled' and f.sets[#f.sets].value == true)
assert(#f.writes == before_writes + 1 and f.writes[#f.writes].key == 'hud_enabled')
assert(#f.changes == before_changes + 1 and f.menu.get(PREFIX .. 'enabled') == true and f.state.pending_count == 0)
assert(f.settings:toggle_enabled() == false and f.menu.get(PREFIX .. 'enabled') == false)
assert(#f.sets == before_sets + 2 and f.data.hud_enabled == false)
print('PASS: F8 uses one MOM set and one HUD preference write per toggle, including true-to-false')

-- Each chosen test action applies once and returns to OFF, so the same choice can be applied again.
for _, id in ipairs({'preview', 'capture','code_copy_test'}) do
    for _ = 1, 2 do
        local actions, saved, mirrored = #f.actions, #f.writes, #f.sets
        f.mom.set_pending(PREFIX .. id, 2)
        assert(#f.actions == actions and f.settings.values[id] == 1)
        assert(f.mom.apply_pending() == 1)
        assert(#f.actions == actions + 1 and f.actions[#f.actions][1] == id and f.actions[#f.actions][2] == 2)
        assert(f.settings.values[id] == 1 and f.menu.get(PREFIX .. id) == 1)
        assert(#f.sets == mirrored + 1 and #f.writes == saved, 'test action persisted in real ledger store')
        assert(f.state.saved[PREFIX .. id] == '1', 'MOM persisted a live action for next startup')
    end
end
assert(file_writes > 0 and files[FILE_ROOT .. 'ModOptionsMenu.values'])
print('PASS: preview/capture run only after Apply, reset through public API, can run again, and do not write real statistics')

-- Invalid inputs do not change values, mirror a menu value, save, or trigger an action.
local bad = {{'enabled', 0}, {'enabled', 'false'}, {'move_tasks', {}}, {'scale_percent', 0/0},
    {'scale_percent', math.huge}, {'opacity_percent', -math.huge}, {'right_margin', '12'},
    {'preview', 1.5}, {'preview', 0}, {'capture', 5}, {'ribbon_mode', 3}, {'currency', 0},
    {'currency', 7}, {'currency', 1.5}, {'currency', 'USD'}, {'currency', 0/0}, {'unknown', 1}}
for _, pair in ipairs(bad) do
    local mirrored, saved, actions, changes = #f.sets, #f.writes, #f.actions, #f.changes
    assert(f.settings:set(pair[1], pair[2]) == false)
    assert(#f.sets == mirrored and #f.writes == saved and #f.actions == actions and #f.changes == changes)
end
for _, value in ipairs({0, 7, 1.5, 'USD', 0/0, math.huge, -math.huge}) do
    local saved, changes, currency = #f.writes, #f.changes, f.settings.config.currency
    assert(f.menu.set(PREFIX .. 'currency', value) == false, 'real MOM API accepted invalid currency')
    assert(f.menu.get(PREFIX .. 'currency') == 1 and f.settings.config.currency == currency)
    assert(#f.writes == saved and #f.changes == changes and f.state.pending_count == 0)
end
assert(f.settings:set('right_margin', 19) and f.settings.config.right_margin == 18)
assert(f.settings:set('scale_percent', 999) and f.settings.config.scale == 1.4)
assert(game_reads == 0)
print('PASS: NaN/infinity/wrong types and invalid choices rejected; finite slider values snap/clamp; no game reads')

-- Missing/incompatible menu logs once at five seconds, then keeps retrying and registers a later real API.
local delayed = fresh({hud_enabled = false, ui_settings = {move_tasks = false}})
_G.ModOptionsMenu = {api = 0}
for _ = 1, 9 do delayed.settings:update(0.5) end
assert(#delayed.logs == 0 and delayed.settings.status == 'waiting_for_menu')
delayed.settings:update(0.5)
assert(#delayed.logs == 1 and delayed.settings.status == 'menu_unavailable')
for _ = 1, 20 do delayed.settings:update(0.5) end
assert(#delayed.logs == 1 and #delayed.registrations == 0)
publish(delayed)
assert(#delayed.logs == 2 and #delayed.registrations == #EXPECTED and delayed.settings.config.enabled == false)
assert(delayed.settings.config.auto_ui_probe == true, 'new automatic UI probe defaults off')
assert(delayed.settings.config.move_tasks == false and #delayed.actions == 0)
for _ = 1, 100 do delayed.settings:update(0.1) end
assert(#delayed.registrations == #EXPECTED and #delayed.logs == 2, 'idle frames re-registered settings')
assert(game_reads == 0)
-- A delayed menu may contain an older saved value than a hotkey used this session.
-- Registration must not undo the player's latest local F8 action.
local late = fresh({hud_enabled = true}, {[PREFIX .. 'enabled'] = 'true'})
assert(late.settings:toggle_enabled() == false and late.data.hud_enabled == false)
assert(#late.sets == 0, 'no menu exists to mirror into yet')
publish(late)
assert(late.settings.config.enabled == false and late.data.hud_enabled == false,
    'late MOM registration undid F8 by replaying its older saved enabled=true')
assert(late.menu.get(PREFIX .. 'enabled') == false)
local enabled_sets = 0
for _, set in ipairs(late.sets) do if set.id == PREFIX .. 'enabled' then enabled_sets = enabled_sets + 1 end end
assert(enabled_sets == 1, 'the pre-menu F8 value must be mirrored exactly once when MOM arrives')
print('PASS: late MOM registration keeps the current-session F8 choice and mirrors it once')
local billing=fresh({ui_settings={billing_enabled=false}})
publish(billing);assert(billing.settings.config.billing_enabled==false)
assert(apply(billing,'billing_enabled',true)==1 and billing.settings.config.billing_enabled==true)
assert(billing.data.ui_settings.billing_enabled==true)
local billing_restored=fresh(billing.data);assert(billing_restored.settings.config.billing_enabled==true)
print('PASS: separate war bill toggle preserves saved false and real MOM Apply without changing HUD visibility')
io.open, os.rename, os.remove = REAL_OPEN, REAL_RENAME, REAL_REMOVE
_G.ModOptionsMenu = nil
print('PASS: missing menu logs once after 5 seconds and later loads successfully; idle frames do not register/read again')
