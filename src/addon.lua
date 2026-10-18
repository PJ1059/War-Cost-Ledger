-- HD2-Addon: mods/hd2_costs/war_cost_ledger
-- Uses code / research from HD2Runtime by SkyeShade
-- https://github.com/SkyeShade/HD2Runtime
-- Reads game state; objective spacing uses the game's native layout on the update thread.
local MOD_ID = 'mods/hd2_costs/war_cost_ledger'
local VERSION = '0.4.66'
local PRICES = __CONFIRMED_PRICES__
local FIRE_SOURCES = __FIRE_SOURCES__
local ENEMY_TYPES = __ENEMY_TYPES__
local SOURCE_NAMES = __SOURCE_NAMES__
local GAME_ICONS = __GAME_ICONS__
local HIT_SOURCES = __HIT_SOURCES__
local NATIVE_HIT_PROFILE = __NATIVE_HIT_PROFILE__
local NATIVE_HIT_TRANSACTION = __NATIVE_HIT_TRANSACTION__
local currency = (function()
__CURRENCY_MODULE__
end)()(__CURRENCY_RATES__)
if rawget(_G, 'HD2WarCostLedgerV1') then return rawget(_G, 'HD2WarCostLedgerV1') end

local ok, hd2 = pcall(require, 'mods/skyeshade/hd2runtime')
assert(ok, 'War Cost Ledger requires HD2Runtime 0.30.3; import and enable its official runtime ZIP.')
local metadata = require('hd2runtime/domains/metadata')
assert(metadata.version == '0.30.3', 'War Cost Ledger 0.4.66 was checked against HD2Runtime 0.30.3.')
local world_api = require('hd2runtime/runtime/event_world')
local beacons = require('hd2runtime/runtime/beacon_redirect')
local loadout = require('hd2runtime/runtime/stratagem_loadout')
local stat_keys = require('hd2runtime/domains/event_natives').stats.keys
local SHOTS, KILLS = stat_keys.projectiles_fired, stat_keys.dealt_kills
local HITS = stat_keys.projectiles_hit
local STIMS = 0xC8256789 -- Runtime's native stims_used counter.
local MELEE, DEATHS = 0xC7680A1B, stat_keys.received_deaths
local mod = hd2.mod(MOD_ID)
local store = mod:store()
local overlay = hd2.ui.overlay({owner = MOD_ID, id = 'costs', visible = false})
local hud = {enabled = store:get('hud_enabled', true) ~= false, mission = false, visible = false}
local ui_settings, game_hud, ui_capture, capture_request, native_hud_feed
local career_award_records,career_panel_feed
local mission_history,mission_history_saved_revision=nil,-1
local career_summary,career_summary_saved_revision=nil,-1
local combat_detail={saved_revision=-1,demolition={},body_sources=__VEHICLE_BODY_SOURCES__,hellpod_sources=__HELLPOD_SOURCES__,source_traits=__KILL_SOURCE_TRAITS__,damage_catalog=__DAMAGE_SOURCE_CATALOG__,status_contexts=__STATUS_DAMAGE_CONTEXTS__}
for id,row in pairs(combat_detail.hellpod_sources)do SOURCE_NAMES[id]=row end
do
    combat_detail.localization=(function()
__LOCALIZATION_MODULE__
    end)()(__LOCALIZATION_CATALOG__)
    function combat_detail.localize(value)return combat_detail.localization:text(value)end
    local ok,api=pcall(require,'hd2runtime/runtime/text_resources')
    combat_detail.language_reader=ok and type(api)=='table'and api.language or nil
end
local career_checkpoint_ready=false
local task_code_probe, task_code_error, task_code_stopped
local hit_session,hit_connector,hit_package,hit_copy_host,hit_install_error
local hit_tail_diag_next_at,hit_tail_diag_key=0,nil
local demolition_candidates,demolition_evidence,demolition_next_at,demolition_sequence=nil,nil,0,nil
-- Use the verified RW dispatch slot and private code copies.
local hit_auto_install = store:get('native_hit_copy_auto_install',true)~=false
local engine_inventory,engine_inventory_at
local ENGINE_EXPORTS_SOURCE_SHA = __ENGINE_EXPORTS_SOURCE_SHA__
local engine_bindings,engine_bindings_at
local ENGINE_CFUNCTION_SOURCE_SHA = __ENGINE_CFUNCTION_SOURCE_SHA__
local plugin_frame_probe, plugin_frame_result, plugin_frame_store
local PLUGIN_FRAME_PROBE_SOURCE_SHA = __PLUGIN_FRAME_PROBE_SOURCE_SHA__
local CODE_COPY_PROBE_SOURCE_SHA = __CODE_COPY_PROBE_SOURCE_SHA__
local code_copy_runner,code_copy_next_at
local hud_time = 0
local create_charge_notifications = (function()
__CHARGE_NOTIFICATIONS_MODULE__
end)()
local charge_notifications = create_charge_notifications()
local bridge_ok, bridge_module = pcall(function()
    return (function()
__NATIVE_UI_BRIDGE_MODULE__
    end)()
end)
local task_ok,task_module=pcall(function()
    return (function()
__NATIVE_TASK_LAYOUT_MODULE__
    end)()
end)
local native_ui = bridge_ok and bridge_module.new({task_module=task_ok and task_module or nil,
    log=function(s) mod:log(s) end}) or nil
if not task_ok then mod:log('任务让位模块未就绪：'..tostring(task_module)) end
if not bridge_ok then mod:log('原生地图读取模块未就绪：' .. tostring(bridge_module)) end
local function load_ui_capture()
    return (function()
__UI_LAYOUT_CAPTURE_MODULE__
    end)()
end
local function auto_ui_enabled()
    return not task_code_stopped and (not ui_settings or ui_settings.config.auto_ui_probe ~= false)
end
local function stop_task_layout_code_probe(reason)
    task_code_stopped = true
    if task_code_probe then
        task_code_probe:cancel(reason or 'TASK_CODE_STOPPED')
        task_code_probe:set_enabled(false)
    end
end
local function step_task_layout_code_probe(world)
    if task_code_error then return end
    local success, failure = pcall(function()
        if not task_code_probe then
            if not auto_ui_enabled() or type(world.runtime) ~= 'table' or world.runtime.mode ~= 'live' then return end
            local module = (function()
__TASK_LAYOUT_CODE_PROBE_MODULE__
            end)()
            task_code_probe = module.new({store = store, enabled = true,
                log = function(message) mod:log(message) end})
        end
        task_code_probe:set_enabled(auto_ui_enabled())
        task_code_probe:step(world, hud_time)
    end)
    if not success then
        task_code_error = tostring(failure)
        if task_code_probe then pcall(stop_task_layout_code_probe, 'TASK_CODE_ERROR') end
        mod:log('任务布局定向读取已停止：' .. task_code_error)
    end
end
local function task_layout_code_status()
    if task_code_probe then return task_code_probe:status_snapshot() end
    return {enabled = auto_ui_enabled(), active = false, status = task_code_error and 'unavailable'
        or (auto_ui_enabled() and 'waiting_for_world' or 'disabled'), reason = task_code_error,
        done = false, read_last = 0, read_peak = 0}
end
local function ui_tree_probe_status()
    -- Full 0.4.6 capture proved the task tree; no further whole-HUD automatic scan.
    -- Keep this diagnostic export without changing any v1/v2/v3 stored evidence.
    return {enabled = false, active = false, status = 'retired', reason = 'TASK_UI_STRUCTURE_VERIFIED',
        read_last = 0, read_peak = 0}
end
local function sync_hud(in_mission)
    hud.mission = in_mission == true
    local preview = game_hud and game_hud:preview_active(hud_time)
    local visible = preview or (hud.enabled and hud.mission)
    if visible ~= hud.visible then
        hud.visible = visible
        if visible then overlay:show() else overlay:hide() end
    end
end
mod:bind('war_cost_ledger.toggle_hud', {key = 'F8', on_press = function()
    if ui_settings then hud.enabled = ui_settings:toggle_enabled()
    else hud.enabled = not hud.enabled; store:set('hud_enabled', hud.enabled) end
    sync_hud(hud.mission)
    mod:log('战果界面 ' .. (hud.enabled and '开启' or '关闭') .. '（F8切换；统计继续记录）。')
end})
-- The new raw/typed reader is initialized only for a manually enabled research probe.
local function load_native_stats()
    return (function()
__NATIVE_STATS_MODULE__
    end)()
end
local create_probe = (function()
__STAT_PROBE_MODULE__
end)()
local probe = create_probe(mod, store, load_native_stats)
local history = store:get('fire_history', {kills = 0})
if type(history) ~= 'table' or type(history.kills) ~= 'number' or history.kills < 0
    or history.kills % 1 ~= 0 or history.kills == math.huge then history = {kills = 0} end
local function valid_count(value)
    return type(value) == 'number' and value >= 0 and value < math.huge and value % 1 == 0
end
local combat_history = store:get('combat_history', {kills = 0, deaths = 0, medals = {}})
if type(combat_history) ~= 'table' then combat_history = {} end
if not valid_count(combat_history.kills) then combat_history.kills = 0 end
if not valid_count(combat_history.deaths) then combat_history.deaths = 0 end
if type(combat_history.medals) ~= 'table' then combat_history.medals = {} end
local create_career_kd = (function()
__CAREER_KD_MODULE__
end)()
local career_kd = create_career_kd(store:get('career_kd', nil))
local career_totals, career_reason = career_kd:totals(combat_history)

local state = {
    version = VERSION, price_version = PRICES.version, workbook_sha256 = PRICES.workbook_sha256,
    mission = false, sequence = store:get('mission_sequence', 0), total_cents = 0,
    billing_enabled = true,
    display_currency = 'MC', currency_rate_date = currency.as_of,
    entries = {}, status = 'waiting', coverage = 'solo_calls_local_stats',
    call_counts = {mg43 = 0, m105 = 0}, shots = nil, kills = nil, stats_ready = false,
    hits = nil, hit_policy = 'local_projectile_stat_known_projectile_weapons', hit_stats_ready = false,
    hit_classification_ready = false, hit_classification_policy = 'native_local_known_projectile_contacts',
    m105_fired = 0, m105_billed_shots = 0, ammo_cents = 0, equipment_ammo_cents = 0,
    fuel_units = 0, fuel_cents = 0, magazine_policy = 'local_held_stable_inventory_including_discard',
    stims_used = nil, stim_units = 0, stim_cents = 0, stim_status = 'waiting',
    grenade_units = 0, grenade_cents = 0, grenade_status = 'waiting',
    inventory_managed = {},
    fire_kills = nil, poison_kills = 0, fire_history = history.kills,
    melee_kills = nil, deaths = nil,
    history_kills = career_totals and career_totals.kills,
    history_deaths = career_totals and career_totals.deaths,
    history_policy = 'career_baseline_plus_observed_deltas', history_reason = career_reason,
    restored_health = 0, life_restored_health = 0, health_ready = false,
    healing_policy = 'local_avatar_observed_positive_deltas_10hz',
    ribbons = {ignite = 0, poison = 0, melee = 0, firepower = 0, air = 0, heavy = 0, giant = 0, demolition = 0, killstreak = 0, crush = 0, recon = 0},
    medals = {fragrant = history.kills >= 500, democracy_undying = false, freedom_in_veins = false,
        democracy_harvester = false, air_expert = false, foreign_parking = false},
    mission_medals = {},
    fire_policy = 'confirmed_flame_and_incendiary_sources',
    unit_kills = {}, class_kills = {}, air_kills = {}, weapon_stats = {}, asset_kills = {},source_reassignments={},kill_pairs={},
    classified_kills = 0, unknown_unit_kills = {}, life_light_kills = 0,
    crush_policy = 'confirmed_player_vehicle_parent_source_kills_as_crush',
    cost_coverage = 'known_local_sources_and_solo_calls',
}
combat_detail.source_totals=(function()
__COMBAT_SOURCE_TOTALS_MODULE__
end)()(combat_detail.source_traits)
combat_detail.damage_sources={}
for id,row in pairs(SOURCE_NAMES)do
    if not ENEMY_TYPES[id]and type(row)=='table'and(row.kind=='weapon'or row.kind=='stratagem'
        or row.kind=='throwable'or combat_detail.source_traits[id]or combat_detail.body_sources[id]
        or combat_detail.hellpod_sources[id]
        or row.kind=='unknown'and row.basis=='exact_cloud_hash_label_only'
            and combat_detail.damage_catalog.resource_nodes[id])then
        combat_detail.damage_sources[id]=row
    end
end
for id,row in pairs(combat_detail.source_traits)do
    if not ENEMY_TYPES[id]then combat_detail.damage_sources[id]=combat_detail.damage_sources[id]or row end
end
local function sync_career_history()
    local totals, reason = career_kd:totals(combat_history)
    state.history_kills, state.history_deaths = totals and totals.kills, totals and totals.deaths
    state.history_reason = reason
end
local career_page_sync = (function()
__CAREER_PAGE_SYNC_MODULE__
end)()({store = store,
    reader = function(world)
        return (function()
__NATIVE_CAREER_READER_MODULE__
        end)().new({visible_only = true, clock = world.runtime.precise_time or os.clock})
    end,
    accepted = function(baseline)
        career_kd = create_career_kd(baseline)
        sync_career_history()
    end,
    log = function(message) mod:log(message) end})
state.career_sync = {status = career_page_sync.status, last = career_page_sync.last, reads = 0}
local career_ship_sync = (function()
__CAREER_SHIP_SYNC_MODULE__
end)()({store = store,
    reader = function(world)
        return (function()
__NATIVE_CAREER_COUNTERS_MODULE__
        end)().new({clock = world.runtime.precise_time or os.clock})
    end,
    accepted = function(baseline)
        career_kd = create_career_kd(baseline)
        sync_career_history()
    end,
    log = function(message) mod:log(message) end})
state.career_sync.auto = {status = career_ship_sync.status, reads = 0}
local saved_engine_inventory = store:get('engine_api_inventory_v1',nil)
if type(saved_engine_inventory)=='table' and saved_engine_inventory.summary_version==1
    and saved_engine_inventory.source_sha==ENGINE_EXPORTS_SOURCE_SHA
    and saved_engine_inventory.exe_sha=='F5FEE03DCFDB2E553A4752C283590950AC13316B376D8196AA556FF0400D5F06'
    and saved_engine_inventory.dll_sha=='2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E' then
    engine_inventory=saved_engine_inventory
end
state.engine_api_inventory=engine_inventory
local saved_bindings=store:get('engine_cfunction_inventory_v1',nil)
if type(saved_bindings)=='table' and saved_bindings.summary_version==1
    and saved_bindings.source_sha==ENGINE_CFUNCTION_SOURCE_SHA
    and saved_bindings.lua_sha=='2C8720C9F446C848436AD993B1A88099D76F0B0B09DF53689719B797C3039CE7'
    and saved_bindings.exe_sha=='F5FEE03DCFDB2E553A4752C283590950AC13316B376D8196AA556FF0400D5F06'
    and saved_bindings.game_sha=='2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E' then
    engine_bindings=saved_bindings
    engine_bindings.status='historical'
    engine_bindings.identity_ready=false
end
state.engine_cfunction_inventory=engine_bindings
local seen = {}
local type_ids = {}
local current_world
local display_status = 'WAITING FOR MISSION'
local group_seen = false
local last_reason
local stat_block, last_stats, ammo_entry
local ammo_entries, ammo_remainders = {}, {}
local grenade_entries = {}
local stim_entry
local barrage_first, barrage_instances, barrage_calls, barrage_prices = true, {}, {}, {}
local life_epoch = 0
local last_melee, last_deaths, health_avatar, last_health, last_max_health
local observe_elapsed, probe_elapsed, persist_elapsed, enemy_elapsed, dirty = 0.1, 0, 0, 0, false
local notification_baseline_sequence
local POLL_INTERVAL, SAVE_INTERVAL = 0.1, 5
local calls_by_id, ammo_types, fire_types = {}, {}, {}
local ammo_by_type = {}
local inventory_prices = {}
local grenade_prices = {}
for _, price in ipairs(PRICES.calls) do calls_by_id[price.native_id] = price end
for _, price in ipairs(PRICES.calls) do if price.payload then barrage_prices[price.payload] = price end end
for _, type_id in ipairs(PRICES.m105_ammo.source_types) do ammo_types[type_id] = true end
for _, price in ipairs(PRICES.ammo) do
    for _, type_id in ipairs(price.source_types) do assert(not ammo_by_type[type_id]); ammo_by_type[type_id] = price end
end
for _, type_id in ipairs(FIRE_SOURCES) do fire_types[type_id] = true end
for _, price in ipairs(PRICES.inventory_ammo or {}) do
    for _, type_id in ipairs(price.source_types) do inventory_prices[type_id] = price end
end
for _, price in ipairs(PRICES.heatsinks or {}) do
    for _, type_id in ipairs(price.source_types) do inventory_prices[type_id] = price end
end
for _, price in ipairs(PRICES.grenades or {}) do
    for _, type_id in ipairs(price.source_types) do grenade_prices[type_id] = price end
end
local grenade_billing = (function()
__GRENADE_BILLING_MODULE__
end)()(grenade_prices)
local grenade_reader_ok, grenade_reader = pcall(function()
    return (function()
__GRENADE_READER_MODULE__
    end)()(world_api)
end)
if not grenade_reader_ok then
    mod:log('投掷物库存读取未就绪：' .. tostring(grenade_reader)); grenade_reader = nil
end
state.grenade_reader = grenade_reader and grenade_reader.diagnostics or {ready=false,reason='UNAVAILABLE'}
local kill_source_attribution=(function()
__KILL_SOURCE_ATTRIBUTION_MODULE__
end)()(SOURCE_NAMES)
local source_subscription_ok,source_subscription,source_subscription_reason=pcall(
    kill_source_attribution.subscribe,kill_source_attribution,hd2.events,MOD_ID)
if not source_subscription_ok then source_subscription_reason=tostring(source_subscription);source_subscription=nil end
local create_magazine_billing = (function()
__MAGAZINE_BILLING_MODULE__
end)()
local magazine_billing = create_magazine_billing(inventory_prices)
local stim_billing = (function()
__STIM_BILLING_MODULE__
end)()({key = STIMS, unit_cents = PRICES.stim.unit_cents})
local reader_ok, consumable_reader = pcall(function()
    local factory = (function()
__CONSUMABLE_READER_MODULE__
    end)()
    return factory(world_api, nil, inventory_prices)
end)
if not reader_ok then
    mod:log('弹匣与燃料读取未就绪：' .. tostring(consumable_reader))
    consumable_reader = nil
end
state.consumable_reader = consumable_reader and consumable_reader.diagnostics or {ready = false, reason = 'UNAVAILABLE'}
local create_hit_stats = (function()
__PROJECTILE_HIT_STATS_MODULE__
end)()
local hit_stats = create_hit_stats(HIT_SOURCES, HITS)
combat_detail.vehicle_kills=(function()
__VEHICLE_KILL_RIBBONS_MODULE__
end)()(combat_detail.body_sources,KILLS)
combat_detail.kill_notices=(function()
__KILL_SOURCE_NOTICES_MODULE__
end)()({sequence=state.sequence,names=SOURCE_NAMES,enemies=ENEMY_TYPES,type_info=world_api.type_info})
combat_detail.recon=(function()
__RECON_CHAT_MODULE__
end)().new()
combat_detail.recon_reader=(function()
__NATIVE_RECON_READER_MODULE__
end)().new()
combat_detail.kill_notice_counts,combat_detail.kill_notice_baseline={},true
function combat_detail.reset_kill_notices(clear_latest)
    if clear_latest==false then combat_detail.kill_notices:gap()
    else combat_detail.kill_notices:reset(state.sequence)end
    combat_detail.kill_notice_counts,combat_detail.kill_notice_baseline={},true
    combat_detail.kill_notice_player,combat_detail.kill_notice_native=nil,nil
    combat_detail.kill_notice_melee=nil
    state.kill_source_notices=combat_detail.kill_notices:snapshot(hud_time)
end
function combat_detail.notice_stats(snapshot,player_entity,kills,first)
    local baseline=first or combat_detail.kill_notice_baseline
        or combat_detail.kill_notice_player~=player_entity
        or (combat_detail.kill_notice_native and snapshot.kills<combat_detail.kill_notice_native)
    local melee=valid_count(snapshot.melee) and snapshot.melee or nil
    local melee_added=not baseline and melee and combat_detail.kill_notice_melee
        and melee>=combat_detail.kill_notice_melee and melee-combat_detail.kill_notice_melee or 0
    if baseline then
        combat_detail.reset_kill_notices(false)
        for hash,value in pairs(snapshot.sources)do combat_detail.kill_notice_counts[hash]=value.kills end
        combat_detail.kill_notice_baseline=false
    else
        local sources,source_kills,ambiguous={},0,false
        for hash,value in pairs(snapshot.sources)do
            local previous=combat_detail.kill_notice_counts[hash] or 0
            if value.kills<previous then ambiguous=true
            elseif value.kills>previous then
                local added=value.kills-previous
                sources[#sources+1]={type=hash,kills=added};source_kills=source_kills+added
            end
            combat_detail.kill_notice_counts[hash]=value.kills
        end
        -- Native KILLS and source counters can advance in adjacent snapshots.
        -- Keep each real delta; the bounded notice matcher joins them without
        -- inventing a victim or throwing away an entire simultaneous batch.
        -- Keep disappeared hashes in the prior map so their return is not new.
        if ambiguous then combat_detail.kill_notices:gap();sources={} end
        combat_detail.kill_notices:on_stats({sequence=state.sequence,local_player=true,
            kills=kills,sources=sources,
            melee_kills=math.min(kills,melee_added)},hud_time)
    end
    combat_detail.kill_notice_player,combat_detail.kill_notice_native=player_entity,snapshot.kills
    combat_detail.kill_notice_melee=melee
end
local REQUESTED_STATS = {SHOTS, KILLS, MELEE, DEATHS, HITS, STIMS}

local function money(cents) return string.format('%.2f', cents / 100) end
local function persist()
    if career_award_records then career_award_records:observe(state) end
    if mission_history then mission_history:observe(state) end
    if career_summary and career_checkpoint_ready then career_summary:observe(state) end
    if combat_detail.records then combat_detail.records:observe(state) end
    dirty = true
end
function combat_detail.poll(world,game,players)
    if not combat_detail.observer then return end
    local local_player
    for _,player in ipairs(players or {})do if player['local']==true then local_player=player;break end end
    combat_detail.context={sequence=state.sequence,occurred_at=os and os.time and os.time() or nil,
        mission_elapsed=combat_detail.started_at and math.max(0,hud_time-combat_detail.started_at) or nil,
        now=hud_time,world=world,players=players,local_peer=local_player and local_player.peer,
        avatar=local_player and local_player.avatar}
    local current=state.deaths
    if state.mission and valid_count(current) then
        if combat_detail.counter~=nil and current>combat_detail.counter then
            local added=current-combat_detail.counter
            -- A gap proves a count, not the last attacker's identity for every
            -- missed death. More than eight is left as explicit missing detail.
            if added<=8 then
                for index=combat_detail.counter+1,current do
                    local context={};for k,v in pairs(combat_detail.context)do context[k]=v end
                    context.death_index=index;context.skip_attribution=added>1
                    if added>1 then context.occurred_at=nil end
                    combat_detail.observer:on_died({local_player=true,observed='native_death_counter'},context)
                end
            end
        end
        combat_detail.counter=current
    end
    combat_detail.observer:step(hud_time,world,game,players,combat_detail.context)
    local changed=false
    for _,record in ipairs(combat_detail.observer:take_records() or {})do
        if combat_detail.records and combat_detail.records:record_death(record) then changed=true end
    end
    state.death_observer=combat_detail.observer.diagnostics
    if changed then persist() end
end
local function observe_career_page(world, game, players)
    if career_panel_feed then career_panel_feed:step(hud_time,world,game,players) end
    local auto_changed = career_ship_sync:step(hud_time,world,game,players,combat_history,state.sequence,
        not ui_settings or ui_settings.config.career_ship_sync)
    local changed = career_page_sync:step(hud_time,world,game,players,combat_history,state.sequence,
        not ui_settings or ui_settings.config.career_page_sync)
    local status = state.career_sync
    status.status,status.reason,status.last,status.reads = career_page_sync.status,career_page_sync.reason,
        career_page_sync.last,career_page_sync.reads
    status.reader = career_page_sync.reader_diagnostics
    local auto = status.auto
    auto.status,auto.reason,auto.last,auto.reads = career_ship_sync.status,career_ship_sync.reason,
        career_ship_sync.last,career_ship_sync.reads
    auto.reader = career_ship_sync.reader_diagnostics
    if career_ship_sync.status=='synced' or career_page_sync.status=='synced' then career_checkpoint_ready=true end
    if career_summary and career_checkpoint_ready and world and game and game.state==3
        and career_summary:observe(state) then dirty=true end
    if changed or auto_changed then persist() end
end
local function observe_engine_inventory(world,game)
    if engine_inventory then return end
    if not world or not game or game.state~=3 or game.mission
        or not world.runtime or world.runtime.mode~='live' then engine_inventory_at=nil;return end
    if not engine_inventory_at then engine_inventory_at=hud_time+6;return end
    if hud_time<engine_inventory_at then return end
    local module=(function()
__ENGINE_EXPORT_INVENTORY_MODULE__
    end)()
    local engine=rawget(_G,'stingray')
    local clock=world.runtime.precise_time or os.clock
    local result=module.collect(engine,{clock=clock})
    result.source_sha=ENGINE_EXPORTS_SOURCE_SHA
    result.exe_sha='F5FEE03DCFDB2E553A4752C283590950AC13316B376D8196AA556FF0400D5F06'
    result.dll_sha='2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E'
    result.captured_at=os.date('!%Y-%m-%dT%H:%M:%SZ')
    -- Keep the static name list out of recurring account/mission saves.
    local summary={summary_version=1,source_sha=result.source_sha,exe_sha=result.exe_sha,
        dll_sha=result.dll_sha,captured_at=result.captured_at,complete=result.complete,
        reason=result.reason,total_entries=result.total_entries,total_scanned=result.total_scanned,
        elapsed_ms=result.elapsed_ms,dump_saved=false,dump_reason='UNSUPPORTED_ROOT'}
    if type(engine)=='table' then
        local start_ok,started=pcall(clock)
        local success,failure=pcall(function()
            local dump=require('hd2runtime/runtime/mod_store').open(MOD_ID..'/engine_exports')
            dump:set('inventory',result)
            local saved,why=dump:save()
            assert(saved,why)
            summary.dump_saved=true
            summary.dump_file=dump:describe().file
            summary.dump_reason=nil
        end)
        local end_ok,finished=pcall(clock)
        if start_ok and end_ok and type(started)=='number' and type(finished)=='number'
            and started==started and finished==finished and started>-math.huge and finished<math.huge
            and finished>=started then summary.dump_elapsed_ms=(finished-started)*1000 end
        if not success then summary.dump_reason=tostring(failure) end
    end
    engine_inventory=summary
    state.engine_api_inventory=summary
    store:set('engine_api_inventory_v1',summary)
    store:save()
    mod:log(string.format('引擎导出诊断：%d个名字，%s，读取Lua表%.3fms，独立存档%s/%s；未调用引擎成员。',
        result.total_entries,result.reason,result.elapsed_ms,
        summary.dump_saved and summary.dump_file or summary.dump_reason,
        summary.dump_elapsed_ms and string.format('%.3fms',summary.dump_elapsed_ms) or '未测'))
end
local function observe_engine_bindings(world,game)
    if engine_bindings then return end
    if not world or not game or game.state~=3 or game.mission~=false
        or not world.runtime or world.runtime.mode~='live' then engine_bindings_at=nil;return end
    if not engine_bindings_at then engine_bindings_at=hud_time+8;return end
    if hud_time<engine_bindings_at then return end
    local clock=world.runtime.precise_time or os.clock
    local start_ok,started=pcall(clock)
    local ok,result=pcall(function()
        local module=(function()
__ENGINE_CFUNCTION_READER_MODULE__
        end)()
        return module.new():collect(world,game,true)
    end)
    if not ok then result={status='unavailable',reason=tostring(result),complete=false,
        identity_ready=false,ProfileVerified=false,found=0,resolved=0,counts={}} end
    result.source_sha=ENGINE_CFUNCTION_SOURCE_SHA
    result.captured_at=os.date('!%Y-%m-%dT%H:%M:%SZ')
    local summary={summary_version=1,source_sha=result.source_sha,captured_at=result.captured_at,
        lua_sha='2C8720C9F446C848436AD993B1A88099D76F0B0B09DF53689719B797C3039CE7',
        exe_sha='F5FEE03DCFDB2E553A4752C283590950AC13316B376D8196AA556FF0400D5F06',
        game_sha='2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E',
        status=result.status,reason=result.reason,complete=result.complete,
        identity_ready=result.identity_ready,contract_ready=false,ProfileVerified=result.ProfileVerified,
        found=result.found,resolved=result.resolved,counts=result.counts,elapsed_ms=result.elapsed_ms,
        hash=result.hash,dump_saved=false,dump_reason='NO_SUPPORTED_FUNCTIONS'}
    if result.found>0 then
        local success,failure=pcall(function()
            local dump=require('hd2runtime/runtime/mod_store').open(MOD_ID..'/engine_bindings')
            dump:set('inventory',result)
            local saved,why=dump:save();assert(saved,why)
            summary.dump_saved=true;summary.dump_file=dump:describe().file;summary.dump_reason=nil
        end)
        if not success then summary.dump_reason=tostring(failure) end
    end
    local end_ok,finished=pcall(clock)
    if start_ok and end_ok and type(started)=='number' and type(finished)=='number'
        and started==started and finished==finished and started>-math.huge and finished<math.huge
        and finished>=started and (finished-started)*1000<math.huge then
        summary.total_elapsed_ms=(finished-started)*1000
    end
    engine_bindings=summary;state.engine_cfunction_inventory=summary
    store:set('engine_cfunction_inventory_v1',summary);store:save()
    mod:log(string.format('脚本入口诊断：%d/%d个独立入口，%s；采样%s，含加载/哈希/独立存档%s；仅候选，命中语义未知。',
        summary.resolved,summary.found,summary.reason,
        summary.elapsed_ms and string.format('%.3fms',summary.elapsed_ms) or '未测',
        summary.total_elapsed_ms and string.format('%.3fms',summary.total_elapsed_ms) or '未测'))
end
local function observe_plugin_frame_probe(world,game)
    local cleanup_pending=plugin_frame_result and (plugin_frame_result.cleanup_required or plugin_frame_result.cleanup_failed)
    if plugin_frame_result and not cleanup_pending then return end
    if not plugin_frame_probe then
        if not world or not game or game.mission~=false or (game.state~=2 and game.state~=3) then return end
        if type(world.runtime)~='table' or world.runtime.mode~='live' or type(world.view)~='table'
            or type(rawget(world.runtime,'read'))~='function' or type(rawget(world.runtime,'query'))~='function'
            or type(rawget(world.runtime,'module'))~='function' or type(rawget(world.runtime,'address'))~='function'
            or type(rawget(world.view,'pointer'))~='function' or type(rawget(world.view,'u32'))~='function' then return end
        local ok,result=pcall(function()
            plugin_frame_store=require('hd2runtime/runtime/mod_store').open(MOD_ID..'/plugin_frame_probe')
            local saved=plugin_frame_store:get('last',nil)
            if type(saved)=='table' and saved.source_sha==PLUGIN_FRAME_PROBE_SOURCE_SHA
                and not saved.cleanup_required and not saved.cleanup_failed then
                plugin_frame_result=saved;return
            end
            local module=(function()
__PLUGIN_FRAME_PROBE_MODULE__
            end)()
            plugin_frame_probe=module.new()
            plugin_frame_probe:start(world,game)
        end)
        if not ok then
            local cleanup_ok,cleanup=false,nil
            if plugin_frame_probe then cleanup_ok,cleanup=pcall(plugin_frame_probe.stop,plugin_frame_probe,'START_ERROR') end
            plugin_frame_result=cleanup_ok and type(cleanup)=='table' and cleanup or {payload_ready=false,engine_dispatch_proven=false}
            plugin_frame_result.phase='failed';plugin_frame_result.reason=tostring(result)
            plugin_frame_result.cleanup_failed=plugin_frame_probe~=nil and not cleanup_ok
        end
    elseif cleanup_pending then
        local ok,result=pcall(plugin_frame_probe.stop,plugin_frame_probe,'CLEANUP_RETRY')
        if ok then plugin_frame_result=result
        else plugin_frame_result.cleanup_failed=true;plugin_frame_result.reason=tostring(result) end
    elseif world and game then
        local ok,result=pcall(plugin_frame_probe.tick,plugin_frame_probe,world,game)
        if not ok then
            local cleanup_ok,cleanup=pcall(plugin_frame_probe.stop,plugin_frame_probe,'TICK_ERROR')
            plugin_frame_result=cleanup_ok and type(cleanup)=='table' and cleanup or {payload_ready=false,engine_dispatch_proven=false}
            plugin_frame_result.phase='failed';plugin_frame_result.reason=tostring(result)
            plugin_frame_result.cleanup_failed=not cleanup_ok
        end
    else
        local ok,result=pcall(plugin_frame_probe.stop,plugin_frame_probe,'WORLD_UNAVAILABLE')
        if not ok then plugin_frame_result={phase='failed',reason=tostring(result),cleanup_failed=true,payload_ready=false,engine_dispatch_proven=false} end
    end
    if plugin_frame_result and plugin_frame_result.source_sha then return end
    local current=plugin_frame_result or (plugin_frame_probe and plugin_frame_probe:status())
    if not current then return end
    if current.cleanup_required or current.cleanup_failed then
        plugin_frame_result=current
        return -- Keep trying ownership-checked cleanup; never cache this as completed.
    end
    if current.phase~='stopped' and current.phase~='failed' then return end
    current.source_sha=PLUGIN_FRAME_PROBE_SOURCE_SHA
    current.captured_at=os.date('!%Y-%m-%dT%H:%M:%SZ')
    current.version=VERSION
    plugin_frame_result=current
    if plugin_frame_store then
        local ok,why=pcall(function()plugin_frame_store:set('last',current);assert(plugin_frame_store:save())end)
        if not ok then current.dump_error=tostring(why) end
    end
    mod:log(string.format('插件更新时序诊断：%s，回调%d次，恢复%s；只检测调用，不产生命中记录。',
        tostring(current.reason),tonumber(current.counter)or 0,tostring(current.restored==true)))
end
local code_copy_controller_module
local function load_code_copy_controller()
    if not code_copy_controller_module then
        code_copy_controller_module=(function()
__NATIVE_CODE_COPY_PROBE_MODULE__
        end)()
    end
    return code_copy_controller_module
end
code_copy_runner=(function()
__CODE_COPY_RUNNER_MODULE__
end)()({source_sha=CODE_COPY_PROBE_SOURCE_SHA,version=VERSION,
    load=load_code_copy_controller,
    persist=function(summary)
        local dump=require('hd2runtime/runtime/mod_store').open(MOD_ID..'/code_copy_probe')
        dump:set('last',summary);assert(dump:save())
    end,
    log=function(message)mod:log(message)end})
local function step_code_copy_probe()
    if not code_copy_runner:active() then return end
    if hit_copy_host and hit_copy_host:handle()then
        code_copy_runner:cancel('OBSERVATION_COPY_RUNNING')
        return
    end
    if code_copy_next_at and hud_time<code_copy_next_at then return end
    code_copy_next_at=hud_time+.1
    local ok,why=pcall(function()
        local world=world_api.open()
        local game=world and world_api.game_state(world)
        code_copy_runner:step(hud_time,world,game)
    end)
    if not ok then
        local stopped,reason=pcall(code_copy_runner.cancel,code_copy_runner,'CALLBACK_ERROR: '..tostring(why))
        if not stopped then mod:log('命中副本测试恢复待重试：'..tostring(reason)) end
    end
end
local function hit_facts(session)
    if not session then return nil end
    return {sequence=session.sequence,peer=session.peer,epoch=session.epoch,accepted=session.accepted,
        records=session.records,unclassified=session.unclassified,stale=session.stale,
        partial=session.partial,status=session.status,reason=session.reason,counts=session.counts}
end
local function load_hit_interface()
    hit_connector=(function()
__NATIVE_HIT_CONNECTOR_MODULE__
    end)()
    hit_package=(function()
__NATIVE_HIT_PACKAGE_MODULE__
    end)()
    if NATIVE_HIT_PROFILE.demolition_diagnostic then
        local demolition_world=(function()
__DEMOLITION_WORLD_MODULE__
        end)()
        local module=(function()
__DEMOLITION_CANDIDATES_MODULE__
        end)()
        demolition_candidates=module.new({world_api=demolition_world.create()})
    end
    local copy_link=(function()
__NATIVE_HIT_COPY_LINK_MODULE__
    end)()
    local copy_host=(function()
__NATIVE_HIT_COPY_HOST_MODULE__
    end)()
    hit_copy_host=copy_host.new({code=load_code_copy_controller(),package=hit_package,
        link=copy_link,profile=NATIVE_HIT_PROFILE,log=function(message)mod:log(message)end})
    local decoder=(function()
__NATIVE_HIT_FEEDBACK_MODULE__
    end)()
    local lifecycle=(function()
__NATIVE_HIT_SESSION_MODULE__
    end)()
    local evidence
    hit_session=lifecycle.new({connector=hit_connector,decoder=decoder,
        observe_record=function(record,contact,raw,offset,now)
            if not evidence or evidence.epoch~=record.epoch then
                evidence={version=VERSION,epoch=record.epoch,peer=record.peer,
                    source_sha=CODE_COPY_PROBE_SOURCE_SHA,records={},counts={},limit=16}
            end
            local count=evidence.counts[contact.result]or 0
            if count<4 and#evidence.records<16 then
                evidence.counts[contact.result]=count+1
                evidence.records[#evidence.records+1]={result=contact.result,
                    raw_hex=(raw:sub(offset+1,offset+96):gsub('.',function(c)return string.format('%02X',c:byte())end)),
                    at=now}
                store:set('native_hit_copy_evidence',evidence);persist()
            end
            return#evidence.records<16
        end,
        accept=function(contact,_,owner)
            if contact.attribution_only==true then
                if owner.sequence==state.sequence and combat_detail.kill_observer then
                    combat_detail.kill_observer:contact(contact)
                end
                return true
            end
            owner.counts=owner.counts or {}
            local count=contact.count or 1
            owner.counts[contact.result]=(owner.counts[contact.result] or 0)+count
            -- A final old batch belongs to its original task even when the
            -- current ledger/HUD has already started the next task.
            if owner.sequence==state.sequence then
                if combat_detail.kill_observer then combat_detail.kill_observer:contact(contact)end
                local key='hit_'..contact.result
                state.ribbons[key]=(state.ribbons[key] or 0)+count
                persist()
            end
            return true
        end,
        changed=function(owner)
            local facts=hit_facts(owner)
            if owner.sequence==state.sequence then
                state.native_hit_classes=facts
                state.hit_classification_ready=owner.ready==true
                persist()
            else store:set('previous_hit_session',facts)end
        end,
        log=function(message)mod:log(message)end})
end
local function observe_demolition_interface(world,game,connected)
    if demolition_candidates and connected and world then
        if demolition_sequence~=state.sequence then
            demolition_sequence,demolition_evidence,demolition_next_at=state.sequence,nil,0
            demolition_candidates:reset()
        end
        -- Only the existing bounded descriptor arrays; unknown +0x30 source
        -- values remain diagnostics until a real closure proves attribution.
        local target_ready,target_reason=demolition_candidates.diagnostics.ready,demolition_candidates.diagnostics.reason
        if game and game.mission then target_ready,target_reason=demolition_candidates:refresh(world,hud_time)end
        if hud_time>=demolition_next_at then
            demolition_next_at=hud_time+1
            local owner=hit_session.current or hit_session.last
            if owner and owner.sequence==state.sequence then
                local read,value,reason=pcall(hit_connector.demolition_snapshot,hit_copy_host:handle(),owner.peer,owner.epoch)
                if read and value then
                    local changed=false
                    if not demolition_evidence or demolition_evidence.epoch~=value.epoch then
                        demolition_evidence={version=VERSION,revision=1,epoch=value.epoch,peer=value.peer,
                            diagnostic_only=true,source_sha=CODE_COPY_PROBE_SOURCE_SHA,records={},unknown_records={}}
                        changed=true
                    end
                    for _,raw in ipairs(value.records)do
                        local row=demolition_candidates:accept(raw,demolition_candidates.diagnostics.world,owner.peer)
                        if row then
                            local list=row.target_verified and demolition_evidence.records or demolition_evidence.unknown_records
                            local limit=row.target_verified and 32 or 8
                            if #list<limit then
                                row.raw_hex=(raw:gsub('.',function(c)return string.format('%02X',c:byte())end))
                                list[#list+1]=row;changed=true
                            end
                        end
                    end
                    -- Sample limits must not freeze later counters or target
                    -- readiness. Keep a fixed scalar summary; no extra reads.
                    for _,key in ipairs({'sequence','dropped','rejected'})do
                        if demolition_evidence[key]~=value[key]then
                            demolition_evidence[key]=value[key];changed=true
                        end
                    end
                    local summary=demolition_evidence.candidate_summary
                    if not summary then summary={};demolition_evidence.candidate_summary=summary;changed=true end
                    local diagnostics=demolition_candidates.diagnostics
                    for _,key in ipairs({'ready','reason','world','descriptor_count','cached_descriptors',
                        'known_holes','pending_descriptors','invalid_descriptors','descriptor_failures','incomplete',
                        'samples','holes','unknown','rejected','receipts_seen','target_missing','unit_mismatch','unknown_limit'})do
                        if summary[key]~=diagnostics[key]then summary[key]=diagnostics[key];changed=true end
                    end
                    if changed then
                        -- Native batches advances even on empty frames and
                        -- scanned is transient. Snapshot both when evidence
                        -- changes, without making idle frames dirty each second.
                        demolition_evidence.batches=value.batches
                        demolition_evidence.scanned=value.scanned
                        store:set('native_demolition_diagnostic',demolition_evidence);persist()
                    end
                    if target_ready then state.demolition_diagnostic_reason=nil
                    else state.demolition_diagnostic_reason=target_reason or 'DESTRUCTION_TARGETS_NOT_READY'end
                elseif read then state.demolition_diagnostic_reason=reason
                else state.demolition_diagnostic_reason='DEMOLITION_DIAGNOSTIC_READ_FAILED'end
            end
        end
    end
end
local function observe_hit_interface(world,game,players)
    if not hit_session and not hit_auto_install then
        state.hit_classification_ready=false
        state.hit_classification_reason='NATIVE_COPY_DISABLED'
        return
    end
    if not hit_session then
        if hit_install_error or not world or type(world.runtime)~='table' or world.runtime.mode~='live' then return end
        if not game or game.state~=3 or game.mission then return end
        local loaded,failure=pcall(load_hit_interface)
        if not loaded then hit_install_error=tostring(failure);mod:log('命中分类初始化停止：'..hit_install_error);return end
    end
    if hit_copy_host and not hit_install_error then
        local ok,value=pcall(hit_copy_host.tick,hit_copy_host,hud_time,world,game)
        if not ok then hit_install_error=tostring(value)
        else
            state.native_hit_copy=value
            local handle=hit_copy_host:handle()
            if handle then assert(hit_session:set_handle(handle));state.hit_classification_reason=nil end
            if value.phase=='failed'and not value.cleanup_required then hit_install_error=value.reason end
        end
        if hit_install_error then state.hit_classification_reason=hit_install_error end
    end
    local peer
    for _,player in ipairs(players or {})do if player['local']==true then peer=player.peer;break end end
    local connected=hit_copy_host and hit_copy_host:handle()~=nil
    local ok,why=hit_session:tick(hud_time,{world=world~=nil and connected,mission=game and game.mission,
        sequence=state.sequence,peer=peer,baseline=state.stats_baseline~=nil})
    if not ok then state.hit_classification_ready=false;state.hit_classification_reason=why end
    local demolition_ok,demolition_why=pcall(observe_demolition_interface,world,game,connected)
    if not demolition_ok then state.demolition_diagnostic_reason='DEMOLITION_OBSERVER_FAILED:'..tostring(demolition_why)end
    -- One bounded read of our own diagnostic memory per second. The alternate
    -- tail is evidence only and cannot add a hit or award a ribbon.
    if connected and hud_time>=hit_tail_diag_next_at and type(hit_connector.diagnostic_snapshot)=='function'then
        hit_tail_diag_next_at=hud_time+1
        local owner=hit_session.current or hit_session.last
        if owner and owner.sequence==state.sequence then
            local read,value,reason=pcall(hit_connector.diagnostic_snapshot,hit_copy_host:handle(),owner.peer,owner.epoch)
            if read and value then
                local key=value.epoch..':'..value.alt_seen..':'..value.true_seen..':'
                    ..tostring(value.claimed)..':'..tostring(value.committed_mask)
                if key~=hit_tail_diag_key then
                    hit_tail_diag_key=key
                    value.version,value.profile_revision,value.source_sha=VERSION,NATIVE_HIT_PROFILE.revision,CODE_COPY_PROBE_SOURCE_SHA
                    store:set('native_hit_tail_diagnostic',value);persist()
                end
                state.native_hit_tail_diagnostic_reason=nil
            elseif read and reason~='NO_TAIL_DIAGNOSTIC'then
                state.native_hit_tail_diagnostic_reason=reason
            elseif not read then state.native_hit_tail_diagnostic_reason='TAIL_DIAGNOSTIC_READ_FAILED'end
        end
    end
end
local function flush(force)
    if dirty and (force or persist_elapsed >= SAVE_INTERVAL) then
        store:set('last_mission', state)
        store:set('fire_history', history)
        store:set('combat_history', combat_history)
        if career_award_records then store:set('career_awards_v1',career_award_records:snapshot()) end
        if mission_history and mission_history_saved_revision~=mission_history.revision then
            store:set('mission_history_v1',mission_history:snapshot())
            mission_history_saved_revision=mission_history.revision
        end
        if career_summary and career_summary_saved_revision~=career_summary.revision then
            store:set('career_kd_checkpoints_v1',career_summary:snapshot())
            career_summary_saved_revision=career_summary.revision
        end
        if combat_detail.records and combat_detail.saved_revision~=combat_detail.records.revision then
            store:set('combat_records_v1',combat_detail.records:snapshot())
            combat_detail.saved_revision=combat_detail.records.revision
        end
        dirty, persist_elapsed = false, 0
    end
end
local function break_health_sample()
    last_health, last_max_health, state.health_ready = nil, nil, false
end
local function new_life()
    life_epoch = life_epoch + 1
    magazine_billing:reset()
    grenade_billing:reset()
    state.life_light_kills = 0
    if combat_detail.achievements then combat_detail.achievements:reset_life() end
    if state.life_restored_health ~= 0 then persist() end
    state.life_restored_health = 0
    break_health_sample()
end
function combat_detail.sync_source_weapon(id)
    if type(id)~='string' then return end
    local entry=state.weapon_stats[id]
    if not entry then
        local name=SOURCE_NAMES[id]or ENEMY_TYPES[id]
        entry={name=name and(name.name_zh or name.name)or id,name_en=name and(name.name_en or name.name),shots=0,kills=0}
        state.weapon_stats[id]=entry
    end
    entry.kills=combat_detail.source_totals:weapon(id)
end
function combat_detail.sync_elemental_kills(baseline)
    local old=state.fire_kills or 0
    local cap=valid_count(state.kills)and state.kills or 2147483647
    local fire=math.min(cap,combat_detail.source_totals:element('fire'))
    local poison=math.min(math.max(0,cap-fire),combat_detail.source_totals:element('poison'))
    state.fire_kills=math.max(old,fire)
    state.poison_kills=math.max(state.poison_kills or 0,poison)
    state.ribbons.ignite,state.ribbons.poison=state.fire_kills,state.poison_kills
    local added=baseline and 0 or math.max(0,state.fire_kills-old)
    if added>0 then
        if history.kills<500 and history.kills+added>=500 then state.mission_medals.fragrant=true end
        history.kills=history.kills+added
    end
    state.fire_history,state.medals.fragrant=history.kills,history.kills>=500
end
local function award_medal(key, repeatable, amount)
    if repeatable or not state.medals[key] then
        amount=amount or 1
        if not valid_count(amount) or amount==0 then return end
        local previous=state.mission_medals[key]
        previous=previous==true and 1 or (valid_count(previous) and previous or 0)
        state.medals[key], combat_history.medals[key] = true, true
        state.mission_medals[key] = previous+amount
        local names = {democracy_undying = '民主永不死', freedom_in_veins = '血管中全是自由的香气',
            democracy_harvester = '民主收割机', air_expert = '防空专家', foreign_parking = '这里不让停外地车',
            double_giant = '一炮双响', democracy_star = '民主之星',
            super_democracy_star = '超级民主之星', supreme_democracy_star = '超级无上民主之星',
            level_not_problem='等级不是问题',tyranny_speed_bump='摧毁暴政减速带'}
        mod:log('成就达成：' .. (names[key] or key)..' x'..tostring(state.mission_medals[key]))
        persist()
    end
end
combat_detail.achievements=(function()
__COMBAT_ACHIEVEMENTS_MODULE__
end)()({state=state,award=award_medal,traits=combat_detail.source_traits,
    on_elemental_kill=function(element,event,source)
        combat_detail.source_totals:observe_element(element,source and source.type)
        combat_detail.sync_elemental_kills(false)
        persist()
    end})
local function record_death(event)
    if not state.mission or not event.local_killer then return end
    local role = ENEMY_TYPES[event.type]
    if (role and role.kill==true and role.asset~=true)
        or (not role and event.info and event.info.kill==true and event.info.kind~='structure') then
        combat_detail.kill_notices:on_death({sequence=state.sequence,local_killer=true,
            observed=event.observed,entity_id=event.entity_id,type=event.type,
            inferred=event.inferred==true,name=event.info and event.info.name,damage_cause=event.damage_cause,
            damage_source=event.damage_source,
            kind=not role and event.info and event.info.kind or nil},hud_time)
        local source=event.damage_source and event.damage_source.type
        local enemy_mechanism=event.damage_source and(event.damage_source.mechanism=='enemy_damage'
            or event.damage_source.mechanism=='self_explosion')
        local raw=event.damage_source and event.damage_source.inferred and event.damage_source.raw_type
        if enemy_mechanism or raw and combat_detail.damage_sources[raw]then raw=nil end
        if combat_detail.source_totals:observe_source(source,raw,
            enemy_mechanism or event.damage_source and event.damage_source.inferred==true and event.damage_source.raw_type==nil)then
            combat_detail.sync_source_weapon(source)
            state.source_reassignments=combat_detail.source_totals:reassignments()
        end
        if source and event.damage_source.target_bound==true and event.type then
            -- Compact target-bound associations, not a per-kill event log.
            -- Native source-stat FIFO guesses remain display-only.
            local pairs=state.kill_pairs[event.type]or{}
            state.kill_pairs[event.type]=pairs
            pairs[source]=(pairs[source]or 0)+1
        end
        combat_detail.achievements:on_kill(event,role or {kill=true},hud_time)
    end
    if not role then
        local info = event.info
        if info and info.kill then
            local entry = state.unknown_unit_kills[event.type]
            if not entry then entry = {name = info.name, count = 0}; state.unknown_unit_kills[event.type] = entry end
            entry.count = entry.count + 1
            persist()
        end
        return
    end
    local function increment(map, key) map[key] = (map[key] or 0) + 1; return map[key] end
    if role.kill then
        local entry = state.unit_kills[role.key]
        if not entry then
            entry = {name_zh = role.name_zh, name_en = role.name_en, class = role.class, faction = role.faction, count = 0}
            state.unit_kills[role.key] = entry
        end
        entry.count = entry.count + 1
        state.classified_kills = state.classified_kills + 1
        increment(state.class_kills, role.class)
        if role.air then
            state.ribbons.air = (state.ribbons.air or 0) + 1
            local count = increment(state.air_kills, role.faction)
            local target = ({terminids = 36, automatons = 12, illuminate = 24})[role.faction]
            if target and count >= target then award_medal('air_expert') end
        end
        local unit_ribbon=combat_detail.unit_ribbons and combat_detail.unit_ribbons[role.key]
        if unit_ribbon then state.ribbons[unit_ribbon]=(state.ribbons[unit_ribbon]or 0)+1
        elseif role.class=='重型'then state.ribbons.heavy=(state.ribbons.heavy or 0)+1
        elseif role.class=='巨型'then state.ribbons.giant=(state.ribbons.giant or 0)+1 end
    end
    if role.asset then
        increment(state.asset_kills, role.key)
        state.ribbons.demolition = (state.ribbons.demolition or 0) + 1
    end
    if role.illuminate_ship then
        state.illuminate_ships = (state.illuminate_ships or 0) + 1
        if state.illuminate_ships >= 10 then award_medal('foreign_parking') end
    end
    persist()
end
local create_kill_observer = (function()
__KILL_OBSERVER_MODULE__
end)()
local kill_observer = create_kill_observer(world_api, require('hd2runtime/domains/event_natives'), ENEMY_TYPES, record_death,
    {local_kills=function()return state.stats_ready and state.kills or nil end,
        source_types=combat_detail.damage_sources,unit_position=world_api.unit_position,
        damage_resolver=(function()
__DAMAGE_SOURCE_RESOLVER_MODULE__
        end)()(combat_detail.damage_catalog.reverse,combat_detail.damage_catalog.resource_nodes),damage_attribution=(function()
__TARGET_DAMAGE_ATTRIBUTION_MODULE__
        end)()()})
state.kill_observer = kill_observer.diagnostics
combat_detail.kill_observer=kill_observer
combat_detail.demolition=(function()
    local create=(function()
__DEMOLITION_ATTRIBUTION_MODULE__
    end)()
    local native=(function()
__BUGHOLE_WORLD_MODULE__
    end)()
    local observe=(function()
__BUGHOLE_OBSERVER_MODULE__
    end)()
    local catalogue=__EXPLOSION_RADII__
    local attribution=create()
    local reader=observe.new({world_api=native.create()})
    local api={peer=nil,world=nil,subscribed=false,next_subscribe=0,reason='WAITING_FOR_MISSION'}
    function api:reset()
        attribution:reset(state.sequence);reader:reset(state.sequence)
        self.peer,self.world,self.destruction,self.active=nil,nil,nil,false
    end
    function api:explosion(event)
        if not state.mission or type(event)~='table' then return end
        if event.local_player==true and combat_detail.kill_observer then
            local status=combat_detail.status_contexts[event.name]
            if status and status.required_event_types then
                -- Shared mine payloads need the observed native resource,
                -- not a name-only fallback, to select their named family.
                local allowed=false
                for _,id in ipairs(status.required_event_types)do
                    if type(event.source_type)=='string'and event.source_type:upper()==id
                        or type(event.owner_type)=='string'and event.owner_type:upper()==id then
                        allowed=true;break
                    end
                end
                if not allowed then status=nil end
            end
            local source=combat_detail.damage_sources[event.source_type] and event.source_type
                or combat_detail.damage_sources[event.owner_type] and event.owner_type
                or status and status.source_type
            local matched=status and source==status.source_type
            local radius=matched and status.radius or source and combat_detail.damage_catalog.source_radius[source]
            if source and radius then
                combat_detail.kill_observer:explosion({local_player=true,source_type=source,
                    owner=event.owner_id,position=event.position,radius=radius,
                    status=matched and status.status or nil,status_duration=matched and status.status_duration or nil,
                    explosion_id=matched and status.explosion_id
                        or combat_detail.damage_catalog.explosion_names[event.name]})
            end
        end
        if not self.active then return end
        local known=catalogue.by_name[event.name]
        local owned
        if event.local_player==true then owned=true
        elseif type(event.player)=='table' and event.local_player==false
            and event.creditor_peer and self.peer and event.creditor_peer~=self.peer then owned=false end
        local radius=known and (owned==true and known.radius or known.conflict_radius)
        attribution:observe_explosion({time=hud_time,position=event.position,radius=radius,
            local_player=owned},hud_time)
    end
    function api:subscribe()
        if self.subscribed or hud_time<self.next_subscribe then return end
        self.next_subscribe=hud_time+5
        if not (hd2.events and type(hd2.events.on)=='function') then
            self.reason='EXPLOSION_EVENTS_UNAVAILABLE';return
        end
        local ok,subscription,why=pcall(hd2.events.on,'explosion',function(event)self:explosion(event)end,
            {id='ledger_demolition_explosion',owner=MOD_ID,scope='session'})
        self.subscribed=false
        if ok and type(subscription)=='table' then
            if type(subscription.active)=='function' then
                local checked,active=pcall(subscription.active,subscription)
                self.subscribed=checked and active==true
            else self.subscribed=subscription.state=='active' end
        end
        if not self.subscribed then self.reason=ok and (why or 'EXPLOSION_SUBSCRIPTION_FAILED') or tostring(subscription) end
    end
    function api:gap(reason)
        self:reset();self.reason=reason or 'OBSERVATION_GAP'
        self:publish()
    end
    function api:poll(world,players)
        self:subscribe()
        local player
        for _,item in ipairs(players or {}) do if item['local']==true then player=item;break end end
        if not state.mission or not world or not player or not player.peer or not self.subscribed then
            self:gap(self.subscribed and 'WORLD_OR_LOCAL_PLAYER_UNAVAILABLE' or self.reason);return
        end
        if self.peer and (self.peer~=player.peer or self.world~=world.game) then self:reset() end
        self.peer,self.world,self.active=player.peer,world.game,true
        local before_poll=reader.diagnostics.polls
        local ok,rows,why=pcall(reader.step,reader,world,hud_time,state.sequence)
        if not ok or not rows then
            self:gap(ok and (why or 'CLOSURE_UNAVAILABLE') or 'CLOSURE_READ_FAILED');return
        end
        -- Only decide after a fresh native sample has checked the destruction
        -- world. A throttled empty success still belongs to the previous world.
        if reader.diagnostics.polls==before_poll then self:publish();return end
        local destruction=reader.diagnostics.world
        if self.destruction and destruction and destruction~=self.destruction then
            attribution:reset(state.sequence);self.destruction=destruction;return
        end
        self.destruction=destruction or self.destruction
        for _,row in ipairs(rows) do
            row.kind='bug_hole';row.time=hud_time
            attribution:observe_closure(row,hud_time)
        end
        local changed=false
        for _,award in ipairs(attribution:advance(hud_time) or {}) do
            state.ribbons.demolition=(state.ribbons.demolition or 0)+1
            state.demolition_inferred=(state.demolition_inferred or 0)+1
            state.asset_kills['虫洞（爆炸关联推测）']=(state.asset_kills['虫洞（爆炸关联推测）'] or 0)+1
            state.demolition_evidence=state.demolition_evidence or {}
            if #state.demolition_evidence<32 then
                state.demolition_evidence[#state.demolition_evidence+1]=award
            end
            changed=true
        end
        self.reason=nil
        self:publish()
        if changed then persist() end
    end
    function api:status()
        local function snapshot(value)
            local out={}
            for key,item in pairs(value or{})do
                if type(item)=='table'then out[key]=snapshot(item)else out[key]=item end
            end
            return out
        end
        return {subscribed=self.subscribed,reason=self.reason,confidence='inferred',
            attribution=snapshot(attribution.diagnostics),reader=snapshot(reader.diagnostics)}
    end
    function api:publish(force)
        local summary=self:status()
        state.demolition_status=summary
        if not force and hud_time<(self.next_diagnostic or 0)then return end
        self.next_diagnostic=hud_time+5
        local key=tostring(state.sequence)..':'..tostring(summary.reason or summary.reader.reason)..':'
            ..tostring(summary.reader.known_holes)..':'..tostring(summary.reader.closures)..':'
            ..tostring(summary.attribution.reason)..':'..tostring(summary.attribution.awarded)..':'
            ..tostring(summary.reader.descriptor_count)..':'..tostring(summary.reader.invalid_indices)..':'
            ..tostring(summary.reader.cached_descriptors)
        if force or key~=self.last_diagnostic then
            self.last_diagnostic=key
            store:set('bughole_diagnostic_v1',summary);persist()
            mod:log('拆巢观察：'..key)
        end
    end
    api:subscribe()
    return api
end)()
function combat_detail.reset_recon()
    combat_detail.recon:reset()
    combat_detail.recon_reader:reset()
end
function combat_detail.poll_recon(world,game,players)
    local snapshot,reason=combat_detail.recon_reader:step(world,players)
    local delta,diagnostics=combat_detail.recon:update(snapshot,{mission=game.mission==true,sequence=state.sequence})
    state.recon_status={reason=reason,reader=combat_detail.recon_reader.diagnostics,counter=diagnostics}
    if delta>0 then
        state.ribbons.recon=(state.ribbons.recon or 0)+delta
        persist()
        mod:log('本人侦察 +'..delta)
    end
end
local function poll_health(world, players)
    local player
    for _, item in ipairs(players) do if item['local'] == true then player = item; break end end
    if not player then break_health_sample(); return end
    if player.lifecycle == 2 then new_life(); return end
    local avatar = player.avatar
    if not avatar then break_health_sample(); return end
    if avatar ~= health_avatar then
        health_avatar = avatar
        new_life()
    end
    local current = world_api.entity_state(world, avatar)
    if current and current.descriptor and current.descriptor.entity == avatar
        and current.descriptor.owned == true and valid_count(current.life) and current.life >= 2 then
        new_life(); return
    end
    if not (current and current.descriptor and current.descriptor.entity == avatar
        and current.descriptor.owned == true and valid_count(current.life) and current.life < 2
        and valid_count(current.health) and valid_count(current.max_health)
        and current.max_health > 0 and current.health <= current.max_health) then
        break_health_sample()
        return
    end
    -- Only consecutive valid samples of this same living avatar can contribute healing.
    local gain = last_health and last_max_health == current.max_health
        and math.max(0, current.health - last_health) or 0
    last_health, last_max_health, state.health_ready = current.health, current.max_health, true
    if gain > 0 then
        state.restored_health = state.restored_health + gain
        state.life_restored_health = state.life_restored_health + gain
        if state.life_restored_health >= 1000 then award_medal('democracy_undying') end
        if state.restored_health >= 5000 then award_medal('freedom_in_veins') end
        persist()
    end
end
local function notice(label, reason)
    display_status = label
    if reason and reason ~= last_reason then
        mod:log(reason)
        last_reason = reason
    end
end
local function start_mission()
    charge_notifications:reset(hud_time)
    kill_source_attribution:reset()
    combat_detail.context,combat_detail.counter,combat_detail.started_at=nil,nil,hud_time
    if combat_detail.observer then combat_detail.observer:reset() end
    state.sequence = state.sequence + 1
    combat_detail.demolition:reset()
    combat_detail.reset_recon()
    state.demolition_inferred,state.demolition_evidence=0,{}
    state.mission, state.total_cents, state.entries = true, 0, {}
    state.status, state.coverage = 'active', 'solo_calls_local_stats'
    state.call_counts = {mg43 = 0, m105 = 0}
    state.shots, state.kills, state.stats_ready = nil, nil, false
    hit_stats:reset()
    combat_detail.vehicle_kills:reset()
    combat_detail.reset_kill_notices()
    state.hits, state.hit_stats_ready, state.hit_sources = nil, false, {}
    state.hit_classification_ready,state.native_hit_classes,state.hit_classification_reason=false,nil,nil
    state.stats_baseline = nil
    state.m105_fired, state.m105_billed_shots, state.ammo_cents = 0, 0, 0
    state.equipment_ammo_cents = 0
    state.fuel_units, state.fuel_cents, state.inventory_managed = 0, 0, {}
    magazine_billing:reset()
    stim_billing:reset()
    state.stims_used, state.stim_units, state.stim_cents, state.stim_status = nil, 0, 0, 'waiting'
    state.grenade_units, state.grenade_cents, state.grenade_status = 0, 0, 'waiting'
    grenade_billing:reset(); grenade_entries = {}
    stim_entry = nil
    state.fire_kills = nil
    state.poison_kills = 0
    combat_detail.source_totals:reset()
    state.melee_kills, state.deaths = nil, nil
    state.restored_health, state.life_restored_health = 0, 0
    state.ribbons = {ignite = 0, poison = 0, melee = 0, firepower = 0, air = 0, heavy = 0, giant = 0, demolition = 0, killstreak = 0, crush = 0, recon = 0}
    for _,key in pairs(combat_detail.unit_ribbons or {})do state.ribbons[key]=0 end
    state.ribbons.hit_total = 0
    state.ribbons.hit_ricochet,state.ribbons.hit_blocked=0,0
    state.ribbons.hit_penetration,state.ribbons.hit_full_penetration=0,0
    state.medals = {fragrant = history.kills >= 500, democracy_undying = false, freedom_in_veins = false,
        democracy_harvester = false, air_expert = false, foreign_parking = false}
    state.mission_medals = {}
    state.unit_kills, state.class_kills, state.air_kills, state.asset_kills, state.weapon_stats = {}, {}, {}, {}, {}
    state.classified_kills, state.unknown_unit_kills, state.life_light_kills, state.illuminate_ships = 0, {}, 0, 0
    state.source_reassignments,state.kill_pairs={},{}
    combat_detail.achievements:reset()
    ammo_entries, ammo_remainders = {}, {}
    barrage_first, barrage_instances, barrage_calls = true, {}, {}
    kill_observer:reset()
    last_melee, last_deaths, health_avatar = nil, nil, nil
    break_health_sample()
    seen, group_seen = {}, false
    last_stats, ammo_entry = nil, nil
    store:set('mission_sequence', state.sequence)
    persist()
    flush(true)
    mod:log('任务 ' .. state.sequence .. ' 开始：战备、个人弹药、武器来源战果及敌军分类。')
end
local function end_mission()
    if state.mission then combat_detail.demolition:publish(true)end
    combat_detail.demolition:reset()
    combat_detail.reset_recon()
    if state.mission then
        combat_detail.reset_kill_notices()
        state.mission, state.status = false, 'ended'
        charge_notifications:reset(hud_time)
        persist()
        flush(true)
        store:save()
        mod:log('任务结束：作战支出 ' .. money(state.total_cents) .. ' MC；本人发射量 '
            .. tostring(state.shots) .. '；击杀 ' .. tostring(state.kills)
            .. '；盟友弹药 ' .. state.m105_billed_shots .. ' 发 / ' .. money(state.ammo_cents) .. ' MC。')
    end
    seen = {}
    magazine_billing:reset()
    grenade_billing:reset()
    stim_billing:reset()
    notice('WAITING FOR MISSION')
end
local function charge_call(price, beacon, game_clock)
    if state.billing_enabled==false then return end
    local entry = {
        sequence = #state.entries + 1, beacon_entity = beacon.entity,
        stratagem_id = price.native_id, price_id = price.id, name = price.name_zh,
        amount_cents = price.total_cents, transport_cents = price.transport_cents,
        equipment_cents = price.equipment_cents, prepaid_ammo_cents = price.prepaid_ammo_cents,
        event = 'beacon_activated', game_clock_us = game_clock,
    }
    state.entries[#state.entries + 1] = entry
    state.total_cents = state.total_cents + entry.amount_cents
    charge_notifications:emit('call:' .. price.id, entry.name, entry.amount_cents, hud_time)
    state.call_counts[price.key] = (state.call_counts[price.key] or 0) + 1
    entry.policy = price.policy
    if price.policy == '逐发计费' then entry.unbilled_component = 'actual_orbital_projectiles' end
    persist()
    mod:log('作战支出：' .. entry.name .. ' +' .. money(entry.amount_cents) .. ' MC；累计 '
        .. money(state.total_cents) .. ' MC；信标 ' .. tostring(beacon.entity))
end

local function charge_ammo(price, quantity, game_clock, inventory)
    if state.billing_enabled==false then return end
    local entry = ammo_entries[price.id]
    if not entry then
        entry = {
            sequence = #state.entries + 1,
            event = price.billing_kind=='maintenance' and 'weapon_maintenance' or 'ammunition_fired', price_id = price.id,
            name = price.name_zh .. (price.billing_label or(price.inventory_mode == 'fuel' and '燃料' or '弹药')), unit_cents = price.unit_cents,
            quantity = 0, amount_cents = 0, first_game_clock_us = game_clock,
        }
        state.entries[#state.entries + 1] = entry
        ammo_entries[price.id] = entry
    end
    local amount = quantity * price.unit_cents
    if inventory then
        entry.event = price.inventory_mode=='heatsink' and 'heatsink_replaced' or 'ammunition_consumed'
        entry.inventory_units = (entry.inventory_units or 0) + quantity
        entry.policy = price.inventory_mode=='heatsink' and '本人实际更换散热片；升温冷却不收费'
            or '射击消耗与换弹废弃统一计费；有效连续库存读数'
    else entry.fired_units = (entry.fired_units or 0) + quantity end
    entry.quantity = entry.quantity + quantity
    entry.amount_cents = entry.amount_cents + amount
    entry.last_game_clock_us = game_clock
    if price.id == PRICES.m105_ammo.id then
        state.m105_billed_shots = state.m105_billed_shots + quantity
        state.ammo_cents = state.ammo_cents + amount
    end
    state.equipment_ammo_cents = state.equipment_ammo_cents + amount
    if price.inventory_mode == 'fuel' then
        state.fuel_units, state.fuel_cents = state.fuel_units + quantity, state.fuel_cents + amount
    end
    state.total_cents = state.total_cents + amount
    charge_notifications:emit('ammo:' .. price.id, entry.name, amount, hud_time)
    persist()
end

local function poll_stims(world, player, current)
    local result = stim_billing:observe({world = tostring(world.game) .. ':' .. tostring(world.exe),
        mission = state.sequence, player = player.entity, peer = player.peer, stats = current})
    state.stim_status = result.status
    if result.ready then state.stims_used = result.current end
    if result.units <= 0 or state.billing_enabled==false then return end
    if not stim_entry then
        stim_entry = {sequence = #state.entries + 1, event = 'stim_used', price_id = PRICES.stim.id,
            name = PRICES.stim.name_zh, unit_cents = PRICES.stim.unit_cents, quantity = 0, amount_cents = 0,
            policy = '本人原生治疗针使用次数增量；补给入库不计费',
            first_game_clock_us = beacons.clock(world)}
        state.entries[#state.entries + 1] = stim_entry
    end
    stim_entry.quantity = stim_entry.quantity + result.units
    stim_entry.amount_cents = stim_entry.amount_cents + result.cents
    stim_entry.last_game_clock_us = beacons.clock(world)
    state.stim_units, state.stim_cents = state.stim_units + result.units, state.stim_cents + result.cents
    state.total_cents = state.total_cents + result.cents
    charge_notifications:emit('stim:' .. PRICES.stim.id, stim_entry.name, result.cents, hud_time)
    persist()
    mod:log('医疗支出：治疗针 ' .. result.units .. ' 支 +' .. money(result.cents) .. ' MC；累计 '
        .. money(state.total_cents) .. ' MC。')
end

local function poll_consumables(world, players)
    local player
    for _, item in ipairs(players) do if item['local'] == true then player = item; break end end
    if not consumable_reader or not player or not state.health_ready then magazine_billing:reset(); return end
    local reading = consumable_reader:read(world, player)
    local result = magazine_billing:observe({world = tostring(world.game) .. ':' .. tostring(world.exe),
        mission = state.sequence, player = player.entity, peer = player.peer, avatar = player.avatar,
        life = life_epoch, time = math.floor(hud_time * 1000), reading = reading})
    state.consumption_status = result.status
    if result.ready then
        -- After the first inventory baseline, SHOTS stays a display counter for this price.
        -- Never fall back mid-mission: an unavailable magazine reading is a coverage gap.
        if not state.inventory_managed[result.price.id] then
            state.inventory_managed[result.price.id] = true; persist()
        end
        if result.units > 0 then charge_ammo(result.price, result.units, beacons.clock(world), true) end
    end
end

local function poll_grenades(world, players)
    local player
    for _, item in ipairs(players) do if item['local']==true then player=item; break end end
    if not grenade_reader or not player or not state.health_ready then
        grenade_billing:reset(); state.grenade_status='unavailable'; return
    end
    local reading=grenade_reader:read(world,player)
    local result=grenade_billing:observe({world=tostring(world.game)..':'..tostring(world.exe),
        mission=state.sequence,player=player.entity,peer=player.peer,avatar=player.avatar,
        life=life_epoch,time=math.floor(hud_time*1000),reading=reading})
    state.grenade_status=result.status
    if result.units<=0 or state.billing_enabled==false then return end
    local price=result.price
    local entry=grenade_entries[price.id]
    if not entry then
        entry={sequence=#state.entries+1,event='throwable_consumed',price_id=price.id,
            name=price.name_zh,unit_cents=price.unit_cents,quantity=0,amount_cents=0,
            policy='本人同身体同类型储备与手持手雷合计下降；拿出或取消不收费',
            first_game_clock_us=beacons.clock(world)}
        state.entries[#state.entries+1]=entry; grenade_entries[price.id]=entry
    end
    entry.quantity=entry.quantity+result.units; entry.amount_cents=entry.amount_cents+result.cents
    entry.last_game_clock_us=beacons.clock(world)
    state.grenade_units,state.grenade_cents=state.grenade_units+result.units,state.grenade_cents+result.cents
    state.equipment_ammo_cents=state.equipment_ammo_cents+result.cents
    state.total_cents=state.total_cents+result.cents
    charge_notifications:emit('grenade:'..price.id,entry.name,result.cents,hud_time)
    persist()
end

local function queue_barrage_call(price, beacon, clock)
    if not valid_count(clock) then return end
    local queue = barrage_calls[price.payload] or {}
    barrage_calls[price.payload] = queue
    if #queue < 64 then queue[#queue + 1] = {price = price, beacon = {entity = beacon.entity}, clock = clock} end
end
local function poll_barrages(world, eligible)
    if not beacons.bombardment then return end
    -- Guard the Runtime reader's 4096-record limit with a small Ledger limit first.
    local layout = require('hd2runtime/domains/bombardment_payload').manager
    local manager = world.view.pointer(world.game + layout.global)
    local total = manager and world.view.u32(manager + layout.instances)
    local count = manager and world.view.u32(manager + layout.barrages)
    if not (total and count and total <= 64 and count <= 64) then return end
    local current = beacons.bombardment(world)
    if not current then return end
    local present, clock = {}, beacons.clock(world)
    if not valid_count(clock) then return end
    for _, item in ipairs(current.list) do
        local hash = item.payload:gsub('^0x', ''):upper()
        present[item.entity] = true
        local entry = barrage_instances[item.entity]
        if entry and entry.payload ~= hash then entry = nil end
        if not entry then
            local call
            local queue = barrage_calls[hash]
            if not barrage_first and eligible and queue then
                while queue[1] and clock - queue[1].clock > 15000000 do table.remove(queue, 1) end
                call = table.remove(queue, 1)
            end
            entry = {payload = hash, fired = call and 0 or item.fired, call = call}
            barrage_instances[item.entity] = entry
        end
        if eligible and entry.call and valid_count(item.fired) and item.fired <= 100000 then
            local added = item.fired - entry.fired
            if added > 0 and state.billing_enabled~=false then
                local call, price = entry.call, entry.call.price
                if not entry.billed then
                    charge_call(price, call.beacon, clock)
                    entry.billed = {sequence = #state.entries + 1, event = 'orbital_shells_fired',
                        price_id = price.shell_price_id, name = price.name_zh .. '炮弹',
                        unit_cents = price.shell_cents, quantity = 0, amount_cents = 0,
                        barrage_entity = item.entity, payload = hash, policy = 'actual_parent_shell_counter'}
                    state.entries[#state.entries + 1] = entry.billed
                    state.entries[#state.entries - 1].unbilled_component = nil
                end
                local amount = added * price.shell_cents
                entry.billed.quantity = entry.billed.quantity + added
                entry.billed.amount_cents = entry.billed.amount_cents + amount
                state.total_cents = state.total_cents + amount
                charge_notifications:emit('shell:' .. price.shell_price_id, entry.billed.name, amount, hud_time)
                persist()
            end
        end
        if valid_count(item.fired) then entry.fired = item.fired end
    end
    for entity in pairs(barrage_instances) do if not present[entity] then barrage_instances[entity] = nil end end
    barrage_first = false
end

local function growth(current, previous)
    if current >= previous then return current - previous end
    -- A native counter reset inside the same mission starts another segment; keep the old segment's total.
    return current
end
local function poll_optional_stats(totals)
    local melee, deaths = totals[MELEE], totals[DEATHS]
    if valid_count(melee) then
        local value = last_melee and state.melee_kills + growth(melee, last_melee) or melee
        if value ~= state.melee_kills then
            state.melee_kills, state.ribbons.melee = value, value
            persist()
        end
        last_melee = melee
    end
    if valid_count(deaths) then
        local delta = last_deaths and growth(deaths, last_deaths) or 0
        local value = last_deaths and state.deaths + delta or deaths
        if value ~= state.deaths then state.deaths = value; persist() end
        if delta > 0 then
            combat_history.deaths = combat_history.deaths + delta
            sync_career_history()
            new_life()
            -- This counter batch cannot order kills before/after the death.
            combat_detail.achievements:gap()
        end
        last_deaths = deaths
    end
end
local function poll_stats(world, players)
    local player
    for _, item in ipairs(players) do if item['local'] == true then player = item; break end end
    if not (player and player.entity) then combat_detail.achievements:gap(); combat_detail.vehicle_kills:gap(); combat_detail.reset_kill_notices(false); stim_billing:reset(); state.stim_status = 'player_missing'; state.stats_ready = false; return end
    if not stat_block then stat_block = world.view.slot() end
    local current = world_api.stat_breakdown(world, player.entity, REQUESTED_STATS, stat_block)
    -- Reuse the existing personal snapshot. Stim billing does not depend on a
    -- held gun, source weapon rows, SHOTS, health gain, or a surviving avatar.
    poll_stims(world, player, current)
    if not (current and valid_count(current.totals[SHOTS]) and valid_count(current.totals[KILLS])) then
        state.stats_ready = false
        combat_detail.achievements:gap()
        combat_detail.vehicle_kills:gap()
        combat_detail.reset_kill_notices(false)
        return
    end
    poll_optional_stats(current.totals)
    local hit_total, hit_growth = hit_stats:sample(current, player.entity)
    state.hit_stats_ready, state.hit_stats_reason = hit_stats.ready, hit_stats.reason
    if hit_total then
        state.hits, state.ribbons.hit_total, state.hit_sources = hit_total, hit_total, hit_stats.sources
        if hit_growth > 0 then persist() end
    end
    local snapshot = {shots = current.totals[SHOTS], kills = current.totals[KILLS], melee=current.totals[MELEE], ammo = {}, fire = {}}
    local m105_total, fire_total = 0, 0
    for type_id in pairs(ammo_types) do
        local count = (current.sources[type_id] or {})[SHOTS] or 0
        if not valid_count(count) then combat_detail.achievements:gap(); combat_detail.vehicle_kills:gap(); combat_detail.reset_kill_notices(false); state.stats_ready = false; return end
        snapshot.ammo[type_id] = count
        m105_total = m105_total + count
    end
    snapshot.sources = {}
    for type_id, values in pairs(current.sources) do
        if not (valid_count(values[SHOTS] or 0) and valid_count(values[KILLS] or 0)) then
            combat_detail.achievements:gap(); combat_detail.vehicle_kills:gap(); combat_detail.reset_kill_notices(false); state.stats_ready = false; return
        end
        snapshot.sources[type_id] = {shots = values[SHOTS] or 0, kills = values[KILLS] or 0}
    end
    for type_id in pairs(fire_types) do
        local count = (current.sources[type_id] or {})[KILLS] or 0
        if not valid_count(count) then combat_detail.achievements:gap(); combat_detail.vehicle_kills:gap(); combat_detail.reset_kill_notices(false); state.stats_ready = false; return end
        snapshot.fire[type_id] = count
        fire_total = fire_total + count
    end
    local crush_total,crush_added=combat_detail.vehicle_kills:sample(current,player.entity)
    state.crush_status=combat_detail.vehicle_kills.reason
    if crush_total then
        state.ribbons.crush=crush_total
        combat_detail.achievements:on_crush(crush_total)
        if crush_added>0 then persist() end
    end
    state.stats_ready = true
    if not last_stats then
        combat_detail.achievements:baseline()
        combat_detail.notice_stats(snapshot,player.entity,0,true)
        -- Show native match totals, including pre-observation stats; costs start at this baseline.
        state.shots, state.kills, state.m105_fired = snapshot.shots, snapshot.kills, m105_total
        state.ribbons.firepower = math.floor(state.shots / 1000)
        state.stats_baseline = {shots = snapshot.shots, kills = snapshot.kills, m105_fired = m105_total}
        last_stats = snapshot
        for type_id, values in pairs(snapshot.sources) do
            local name = SOURCE_NAMES[type_id]
            combat_detail.source_totals:native(type_id,values.kills,true)
            state.weapon_stats[type_id] = {name = name and name.name_zh or (name and name.name or type_id),
                name_en = name and name.name, shots = values.shots, kills = combat_detail.source_totals:weapon(type_id)}
        end
        combat_detail.sync_elemental_kills(true)
        persist()
        return
    end
    local shots, kills = growth(snapshot.shots, last_stats.shots), growth(snapshot.kills, last_stats.kills)
    if snapshot.kills<last_stats.kills then combat_detail.achievements:gap() end
    combat_detail.achievements:on_stats(kills,hud_time)
    combat_detail.notice_stats(snapshot,player.entity,kills,false)
    local billed, fire_growth = 0, 0
    for type_id, count in pairs(snapshot.ammo) do billed = billed + growth(count, last_stats.ammo[type_id]) end
    for type_id, count in pairs(snapshot.fire) do fire_growth = fire_growth + growth(count, last_stats.fire[type_id]) end
    state.shots, state.kills = state.shots + shots, state.kills + kills
    state.m105_fired = state.m105_fired + billed
    state.ribbons.firepower = math.floor(state.shots / 1000)
    combat_history.kills = combat_history.kills + kills
    sync_career_history()
    local ammo_growth = {}
    for type_id, values in pairs(snapshot.sources) do
        local prior = last_stats.sources[type_id] or {shots = 0, kills = 0}
        local fired, dead = growth(values.shots, prior.shots), growth(values.kills, prior.kills)
        local entry = state.weapon_stats[type_id]
        if not entry then
            local name = SOURCE_NAMES[type_id]
            entry = {name = name and name.name_zh or (name and name.name or type_id), name_en = name and name.name,
                shots = 0, kills = 0}; state.weapon_stats[type_id] = entry
        end
        combat_detail.source_totals:native(type_id,dead)
        entry.shots, entry.kills = entry.shots + fired, combat_detail.source_totals:weapon(type_id)
        if fired > 0 or dead > 0 then persist() end
        local price = ammo_by_type[type_id]
        if price and fired > 0 then
            ammo_growth[price.id] = (ammo_growth[price.id] or 0) + fired
        end
    end
    combat_detail.sync_elemental_kills(false)
    for id, fired in pairs(ammo_growth) do
        local price
        for _, candidate in ipairs(PRICES.ammo) do if candidate.id == id then price = candidate; break end end
        local count = (ammo_remainders[id] or 0) + fired
        local units = math.floor(count / price.projectiles_per_unit)
        ammo_remainders[id] = count % price.projectiles_per_unit
        if units > 0 and not state.inventory_managed[id] then charge_ammo(price, units, beacons.clock(world)) end
    end
    last_stats = snapshot
    if shots > 0 or kills > 0 or billed > 0 or fire_growth > 0 then persist() end
end

mod:on_frame(function(dt)
    -- No catch-up loop after a long frame. All native observations share this 10 Hz budget.
    dt = type(dt) == 'number' and dt >= 0 and dt < math.huge and dt or 0
    hud_time = hud_time + dt
    combat_detail.kill_notices:update(hud_time)
    state.kill_source_notices=combat_detail.kill_notices:snapshot(hud_time)
    -- Run ownership cleanup before other ledger/UI work can return or fail.
    step_code_copy_probe()
    -- Damage requests may be consumed between 10 Hz stat polls. Cache only
    -- the current local avatar's bounded queue snapshot on rendering frames.
    if state.mission and combat_detail.observer and combat_detail.context
        and combat_detail.context.sequence==state.sequence then
        combat_detail.observer:sample_damage(hud_time,combat_detail.context)
    end
    if career_panel_feed then career_panel_feed:sample_input(hud_time) end
    if ui_settings then ui_settings:update(dt) end
    if game_hud then game_hud:observe(hud_time) end
    sync_hud(hud.mission)
    persist_elapsed = persist_elapsed + dt
    probe_elapsed = probe_elapsed + dt
    enemy_elapsed = enemy_elapsed + dt
    flush(false)
    observe_elapsed = observe_elapsed + dt
    if observe_elapsed + 1e-9 < POLL_INTERVAL then return end
    observe_elapsed = math.max(0, observe_elapsed - math.floor(observe_elapsed / POLL_INTERVAL + 1e-9) * POLL_INTERVAL)
    local world, reason = world_api.open()
    if world then combat_detail.localization:poll(world.runtime,hud_time,combat_detail.language_reader)end
    if not world then
        combat_detail.demolition:gap('WORLD_UNAVAILABLE')
        combat_detail.poll(nil,nil,nil)
        observe_plugin_frame_probe(nil,nil)
        observe_career_page(nil,nil,nil)
        observe_engine_inventory(nil,nil)
        observe_engine_bindings(nil,nil)
        observe_hit_interface(nil,nil,nil)
        if native_hud_feed then native_hud_feed:clear() end
        if game_hud then game_hud:set_map(nil) end
        if task_code_probe then task_code_probe:cancel('TASK_CODE_WORLD_UNAVAILABLE') end
        if ui_capture and ui_capture.active then ui_capture:cancel() end
        if capture_request and hud_time > capture_request.deadline then
            capture_request = nil; mod:log('UI采集未开始：30秒内未取得任务和对应地图状态。')
        end
        magazine_billing:reset()
        grenade_billing:reset(); state.grenade_status='world_missing'
        stim_billing:reset(); state.stim_status = 'world_missing'
        combat_detail.achievements:gap(); combat_detail.vehicle_kills:gap(); combat_detail.reset_kill_notices(false); kill_observer:gap(); break_health_sample(); sync_hud(false); notice('WAITING FOR GAME', reason); return
    end
    local native_state = native_ui and native_ui:poll(world)
    if game_hud then game_hud:set_map(native_state) end
    -- Manual capture owns its larger read allowance for the entire observation tick.
    local manual_ui_work = capture_request ~= nil or (ui_capture and ui_capture.active ~= nil)
    if native_hud_feed then
        native_hud_feed:update(not manual_ui_work and native_state and native_ui.task
            and native_ui.task:geometry_snapshot() or nil,hud_time,hud.visible)
    end
    if native_ui and native_state then
        if manual_ui_work then native_ui:restore()
        else native_ui:reserve(game_hud:reservation(hud.visible,true,hud_time)) end
    end
    if manual_ui_work and task_code_probe then task_code_probe:cancel('TASK_CODE_MANUAL_PRIORITY') end
    if capture_request and hud_time >= capture_request.start_at then
        if hud_time > capture_request.deadline then
            capture_request = nil; mod:log('UI采集未开始：30秒内未取得任务和对应地图状态。')
        elseif native_state and native_state.mission and native_state.map_open == capture_request.map_open then
            if not ui_capture then ui_capture = load_ui_capture().new({bridge = native_ui, log = function(s) mod:log(s) end}) end
            local sample, why = ui_capture:start(world, capture_request.map_open and '完整任务列表：地图打开' or '完整任务列表：地图关闭')
            capture_request = nil
            if not sample then mod:log('UI采集无法开始：' .. tostring(why)) end
        end
    end
    if ui_capture and ui_capture.active then ui_capture:step(world) end
    if not manual_ui_work then step_task_layout_code_probe(world) end
    if current_world ~= world.game then
        current_world, type_ids, stat_block = world.game, {}, nil
        stim_billing:reset()
        health_avatar = nil
        new_life()
    end
    local game = world_api.game_state(world)
    if not game then combat_detail.demolition:gap('GAME_STATE_UNAVAILABLE');combat_detail.poll(world,nil,nil);observe_plugin_frame_probe(nil,nil);observe_career_page(world,nil,nil);observe_engine_inventory(nil,nil);observe_engine_bindings(nil,nil);observe_hit_interface(world,nil,nil);magazine_billing:reset();grenade_billing:reset();state.grenade_status='state_missing';stim_billing:reset();state.stim_status='state_missing'; combat_detail.achievements:gap(); combat_detail.vehicle_kills:gap(); combat_detail.reset_kill_notices(false); kill_observer:gap(); break_health_sample(); sync_hud(false); notice('STATE UNAVAILABLE'); return end
    observe_plugin_frame_probe(world,game)
    sync_hud(game.mission)
    local players = world_api.players(world, game.mission == true)
    probe:poll(world, players, game, probe_elapsed)
    probe_elapsed = 0
    if not game.mission then
        if state.mission then poll_stats(world, players) end
        combat_detail.poll(world,game,players)
        observe_hit_interface(world,game,players)
        end_mission()
        observe_career_page(world,game,players)
        observe_engine_inventory(world,game)
        observe_engine_bindings(world,game)
        kill_observer:reset()
        enemy_elapsed = 0
        break_health_sample()
        return
    end
    observe_career_page(world,game,players)
    observe_engine_inventory(world,game)
    observe_engine_bindings(world,game)
    if not state.mission then start_mission() end
    -- Personal stats and source-attributed ammo work independently of beacon/call-in detection.
    poll_stats(world, players)
    combat_detail.poll(world,game,players)
    if game_hud and state.stats_ready and notification_baseline_sequence ~= state.sequence then
        game_hud.notifications:baseline(hud_time)
        notification_baseline_sequence = state.sequence
    end
    observe_hit_interface(world,game,players)
    combat_detail.demolition:poll(world,players)
    combat_detail.poll_recon(world,game,players)
    poll_health(world, players)
    poll_consumables(world, players)
    poll_grenades(world, players)
    kill_observer:poll(world, players, enemy_elapsed, life_epoch)
    enemy_elapsed = 0
    if #players > 1 and not group_seen then
        group_seen = true
        state.coverage = 'local_stats_calls_paused'
        persist()
    end
    local proven, why = beacons.prove(world)
    if not proven then notice('BEACON API UNAVAILABLE', why); return end
    local ids_proven, ids_why = loadout.prove(world)
    if not ids_proven then notice('STRATAGEM IDS UNAVAILABLE', ids_why); return end
    local list, unreadable = beacons.beacons(world)
    if not list then notice('BEACONS UNAVAILABLE', unreadable); return end

    local eligible = not group_seen and #players == 1 and players[1]['local'] == true and game.host == true
    if group_seen then notice('LOCAL STATS | CALLS PAUSED')
    elseif eligible then notice('SOLO CALLS + LOCAL STATS')
    else notice('WAITING FOR SOLO HOST') end

    for entity, beacon in pairs(list) do
        local previous = seen[entity]
        -- An already-active beacon on the first read predates observation; never back-charge it.
        if previous and not previous.activated and beacon.activated == true and eligible then
            local id = type_ids[beacon.type]
            if id == nil then
                id = loadout.id_of(world, beacon.type)
                if id then type_ids[beacon.type] = id end
            end
            local price = id and calls_by_id[id]
            if price then
                if price.shell_cents then queue_barrage_call(price, beacon, beacons.clock(world))
                else charge_call(price, beacon, beacons.clock(world)) end
            end
        end
        seen[entity] = {activated = beacon.activated == true}
    end
    for entity in pairs(seen) do if not list[entity] then seen[entity] = nil end end
    poll_barrages(world, eligible)
end, {id = 'observe_calls_and_stats'})

local create_battle_hud = (function()
__BATTLE_HUD_MODULE__
end)()
local battle_hud = create_battle_hud(state, function() return hud.visible end, currency)
combat_detail.unit_ribbons={}
for _,icon in ipairs(battle_hud.icons)do
    if icon.unit_key then
        combat_detail.unit_ribbons[icon.unit_key]=icon.key
        -- Observe zero before the first local kill so the first unit-specific
        -- ribbon is an acquisition, rather than a late notification baseline.
        state.ribbons[icon.key]=0
    end
end
do
    local create=(function()
__CAREER_AWARD_RECORDS_MODULE__
    end)()
    career_award_records=create({icons=battle_hud.icons,saved=store:get('career_awards_v1',nil),
        legacy={last_mission=store:get('last_mission',nil),combat_history=combat_history}})
    -- Queue the initial migration through the existing batched save path.
    -- Waiting/preview states cannot establish a mission or earn an award.
    persist()
end
do
    local create=(function()
__MISSION_HISTORY_MODULE__
    end)()
    mission_history=create({icons=battle_hud.icons,saved=store:get('mission_history_v1',nil),
        legacy=store:get('last_mission',nil),clock=function()
            return os and os.time and os.time() or nil
        end})
    persist()
end
do
    local create=(function()
__COMBAT_RECORDS_MODULE__
    end)()
    combat_detail.records=create({saved=store:get('combat_records_v1',nil),
        search_alias=function(value)return combat_detail.localization:english(value)end,
        clock=function()return os and os.time and os.time() or nil end,
        weapon_catalog=__CAREER_WEAPON_CATALOG__,enemy_catalog=ENEMY_TYPES,
        vehicle_body_sources=combat_detail.body_sources,
        legacy=store:get('last_mission',nil),history=mission_history:entries()})
    local native_ready,native_reader=pcall(function()
        local make_reader=(function()
__NATIVE_DEATH_READER_MODULE__
        end)()
        return make_reader({world_api=world_api})
    end)
    if not native_ready then mod:log('死亡来源读取未就绪：'..tostring(native_reader));native_reader=nil end
    local make_observer=(function()
__DEATH_OBSERVER_MODULE__
    end)()
    combat_detail.observer=make_observer({reader=native_reader,
        catalog=ENEMY_TYPES,source_names=SOURCE_NAMES,resource_names=SOURCE_NAMES,
        damage_catalog=combat_detail.damage_catalog,vehicle_sources=combat_detail.body_sources,nearby_deaths=true})
    state.death_observer=combat_detail.observer.diagnostics
    if hd2.events and type(hd2.events.on)=='function' then
        for _,kind in ipairs({'player_died','player_damaged'})do
            local event_kind=kind
            local subscribed,why=pcall(hd2.events.on,event_kind,function(event)
                if not state.mission or not combat_detail.context then return end
                local context={};for key,value in pairs(combat_detail.context)do context[key]=value end
                context.now=hud_time;context.occurred_at=os and os.time and os.time() or nil
                if event_kind=='player_died' then combat_detail.observer:on_died(event,context)
                else combat_detail.observer:on_damaged(event,context) end
            end,{id='ledger_'..event_kind,owner=MOD_ID,scope='session'})
            if not subscribed then mod:log('死亡线索事件未就绪 '..event_kind..': '..tostring(why)) end
        end
    end
    persist()
end
do
    local create=(function()
__CAREER_HISTORY_SUMMARY_MODULE__
    end)()
    career_summary=create({icons=battle_hud.icons,saved=store:get('career_kd_checkpoints_v1',nil),
        clock=function()return os and os.time and os.time() or nil end})
end
local last_summary,summary_stamp
local function career_period_summary()
    local now=os and os.time and os.time() or nil
    local stamp=table.concat({tostring(now),mission_history.revision,career_summary.revision,
        tostring(state.history_kills),tostring(state.history_deaths),tostring(state.history_reason)},':')
    if summary_stamp~=stamp then
        last_summary=career_summary:summarize(mission_history:entries(),state,now,mission_history.revision)
        summary_stamp=stamp
    end
    return last_summary
end
do
    local reader_module=(function()
__NATIVE_CAREER_PANEL_READER_MODULE__
    end)()
    local create_model=(function()
__CAREER_PANEL_MODEL_MODULE__
    end)()
    local create_feed=(function()
__CAREER_PANEL_FEED_MODULE__
    end)()
    local create_combat=(function()
__CAREER_COMBAT_PANEL_MODEL_MODULE__
    end)()
    local create_search=(function()
__CAREER_SEARCH_INPUT_MODULE__
    end)()
    career_panel_feed=create_feed({reader=function() return reader_module.new() end,
        model=create_model(battle_hud.icons,nil,create_combat,combat_detail.localize),records=function()
            -- The Career layout only reads this snapshot. Copy a growing
            -- award history once per revision, rather than every UI poll.
            local cached=combat_detail.career_award_view
            if not cached or cached.revision~=career_award_records.revision then
                cached={revision=career_award_records.revision,value=career_award_records:snapshot()}
                combat_detail.career_award_view=cached
            end
            return cached.value
        end,
        history=function()return {version=1,revision=mission_history.revision,limit=mission_history.limit,
            entries=mission_history:entries()}end,
        summary=career_period_summary,
        billing_enabled=function()return state.billing_enabled~=false end,
        format_money=function(cents)
            local code=currency:code(state.display_currency)
            return currency:format(cents,code)..' '..code
        end,
        crush_summary=function(history)return combat_detail.records:legacy_crush_summary(history)end,
        combat=function(view,filters)
            filters=filters or {};filters.now=os and os.time and os.time() or nil
            return combat_detail.records:query(view,filters)
        end,
        search_input=create_search,
        key_pressed=hd2.input and type(hd2.input.pressed)=='function' and function(name)return hd2.input.pressed(name)end or nil,
        key_down=hd2.input and type(hd2.input.down)=='function' and function(name)return hd2.input.down(name)end or nil,
        latest_ended=function()return state.status=='ended' and state.sequence or nil end,
        wheel=function()return hd2.input and hd2.input.wheel and hd2.input.wheel() or 0 end,
        block_input=function(spec)
            if hd2.input and type(hd2.input.block)=='function' then return hd2.input.block(spec) end
            return false,'input capture unavailable'
        end,
        format_time=function(timestamp)
            return os and os.date and os.date('%Y-%m-%d %H:%M',timestamp) or nil
        end,
        mouse=function() return hd2.input and hd2.input.mouse and hd2.input.mouse() end,
        gui_resolution=function()
            local engine=rawget(_G,'stingray')
            if engine and engine.Gui and engine.Gui.resolution then return engine.Gui.resolution() end
        end})
end
local create_award_notifications = (function()
__AWARD_NOTIFICATIONS_MODULE__
end)()
local available_icons, notification_icons = {}, {}
for _, icon in ipairs(GAME_ICONS.images) do available_icons[icon.id] = true end
for _, icon in ipairs(battle_hud.icons) do
    if available_icons[icon.id] then notification_icons[#notification_icons + 1] = icon end
end
local awards = create_award_notifications(state, notification_icons)
local create_game_hud = (function()
__GAME_HUD_MODULE__
end)()
local create_hud_layout = (function()
__HUD_LAYOUT_MODULE__
end)()
game_hud = create_game_hud(hd2, state, battle_hud, awards, GAME_ICONS,
    {battle = create_battle_hud, awards = create_award_notifications, currency = currency,
        localize=combat_detail.localize,locale_revision=function()return combat_detail.localization.revision end,
        charges = charge_notifications, create_charges = create_charge_notifications, layout = create_hud_layout})
local create_ui_settings = (function()
__UI_SETTINGS_MODULE__
end)()
ui_settings = create_ui_settings(mod, store, {
    localize=combat_detail.localize,
    career_status = function() return career_page_sync:description() end,
    career_ship_status = function() return career_ship_sync:description() end,
    code_copy_test=function(mode)
        if mode==3 then
            code_copy_runner:cancel('USER_CANCELLED')
            mod:log('命中副本测试已取消；有待恢复时继续重试。')
            return
        end
        if hit_copy_host and hit_copy_host:handle()then
            mod:log('命中分类副本正在运行；测试状态可在日志中读取，无需重复切换。')
            return
        end
        local queued,why=code_copy_runner:request(hud_time)
        mod:log(queued and '命中副本测试已预约：关闭菜单，留在飞船；5秒后运行2秒，每次启动限一次。'
            or ('命中副本测试未开始：'..tostring(why)))
    end,
    changed = function(config, id)
        hud.enabled = config.enabled
        state.display_currency = config.currency
        state.billing_enabled = config.billing_enabled~=false
        if id=='kill_source_enabled' then combat_detail.reset_kill_notices() end
        if id=='billing_enabled' then
            -- Readers keep consuming current counters while disabled; a toggle
            -- never catches up charges from the disabled part of a mission.
            magazine_billing:reset(); grenade_billing:reset(); stim_billing:reset()
            charge_notifications:reset(hud_time)
            barrage_calls,barrage_instances,barrage_first={},{},true
            persist()
        end
        if id == 'auto_ui_probe' then
            task_code_stopped = false
            if task_code_probe then task_code_probe:set_enabled(config.auto_ui_probe) end
        end
        game_hud:configure(config)
        sync_hud(hud.mission)
    end,
    preview = function(mode)
        game_hud:start_preview(mode, hud_time)
        sync_hud(hud.mission)
        mod:log('UI TEST：独立演示8秒，不计入战果或账单。')
    end,
    capture = function(mode)
        if mode == 4 then
            capture_request = nil
            if ui_capture then ui_capture:cancel() end
            mod:log('已取消UI定位采集。')
        elseif ui_capture and ui_capture.active then
            mod:log('已有UI定位采集正在运行；需先取消。')
        elseif not native_ui then
            mod:log('UI采集无法开始：原生UI读取模块未就绪。')
        else
            if task_code_probe then task_code_probe:cancel('TASK_CODE_MANUAL_PRIORITY') end
            capture_request = {map_open = mode == 3, start_at = hud_time + 5, deadline = hud_time + 35}
            mod:log('UI定位采集已预约：请关闭菜单，保持' .. (mode == 3 and '地图打开' or '地图关闭') .. '约15秒；5秒后等待对应状态。')
        end
    end,
})
game_hud:configure(ui_settings.config)
state.display_currency = ui_settings.config.currency
state.billing_enabled = ui_settings.config.billing_enabled~=false
native_hud_feed=(function()
__NATIVE_HUD_FEED_MODULE__
end)()(game_hud,state,battle_hud,awards)
mod:bind('war_cost_ledger.toggle_collection', {key = 'F9', on_press = function()
    local open = game_hud:toggle_collection()
    mod:log('累计绶带备用视图：' .. (open and '展开' or '收起') .. '；真实地图状态可读时优先自动联动。')
end})
overlay:draw(function(d)
    -- The flat overlay remains an isolated ship/menu preview only. Combat uses
    -- the same native widget host as the objective list, never both renderers.
    if not hud.mission and game_hud:preview_active(hud_time) then game_hud:draw(d,hud_time,hud.visible) end
end)
local exported = {version = VERSION, state = state, battle_hud = battle_hud,
    localization=combat_detail.localization,
    demolition_status=function()return combat_detail.demolition:status()end,
    kill_source_snapshot=function()return {latest=kill_source_attribution.latest,
        diagnostics=kill_source_attribution.diagnostics,subscribed=source_subscription~=nil,
        reason=source_subscription_reason,per_victim=false}end,
    career_award_snapshot=function() return career_award_records:snapshot() end,
    mission_history_snapshot=function()return mission_history:snapshot()end,
    combat_records_snapshot=function()return combat_detail.records:snapshot()end,
    career_combat_query=function(view,filters)return combat_detail.records:query(view,filters)end,
    death_observer_status=function()return combat_detail.observer.diagnostics end,
    career_period_summary=career_period_summary,
    career_checkpoint_snapshot=function()return career_summary:snapshot()end,
    career_panel_snapshot=function() return career_panel_feed:snapshot() end,
    career_panel_status=function() return {status=career_panel_feed.status,reader=career_panel_feed.reader_diagnostics} end,
    charge_notifications = charge_notifications,
    game_hud = game_hud, award_notifications = awards, ui_settings = ui_settings, native_ui = native_ui,
    native_hud_snapshot=function() return native_hud_feed:snapshot() end,
    task_layout_status=function() return native_ui and native_ui.task and native_ui.task:status_snapshot() or {status='unavailable'} end,
    ui_tree_probe_status = ui_tree_probe_status,
    task_layout_code_status = task_layout_code_status, stop_task_layout_code_probe = stop_task_layout_code_probe,
    career_sync_status = function() return {status=career_page_sync.status,reason=career_page_sync.reason,
        last=career_page_sync.last,reads=career_page_sync.reads} end,
    career_ship_sync_status = function() return {status=career_ship_sync.status,reason=career_ship_sync.reason,
        last=career_ship_sync.last,reads=career_ship_sync.reads,reader=career_ship_sync.reader_diagnostics} end,
    engine_inventory_status=function()return engine_inventory or {status='waiting_ship'}end,
    engine_bindings_status=function()return engine_bindings or {status='waiting_ship',contract_ready=false}end,
    plugin_frame_probe_status=function()return plugin_frame_result or (plugin_frame_probe and plugin_frame_probe:status()) or {phase='waiting_static',payload_ready=false}end,
    code_copy_probe_status=function()return code_copy_runner:status()end,
    cancel_code_copy_probe=function()return code_copy_runner:cancel('USER_CANCELLED')end,
    native_hit_status=function()return {status=hit_install_error or (hit_session and hit_session.status
        or (hit_auto_install and 'waiting_ship' or 'native_copy_disabled')),
        ready=hit_session and hit_session.ready or false,current=hit_facts(hit_session and hit_session.current),
        previous=hit_facts(hit_session and hit_session.last),copy=hit_copy_host and hit_copy_host:status()}end,
    capture_status = function() return capture_request and 'queued' or (ui_capture and ui_capture.status or 'disabled') end}
rawset(_G, 'HD2WarCostLedgerV1', exported)
mod:log('War Cost Ledger ' .. VERSION .. ' loaded; M-105 盟友呼叫 '
    .. money(calls_by_id[14345846].total_cents) .. ' MC；弹药 '
    .. money(PRICES.m105_ammo.unit_cents) .. ' MC/发；侧边战果停更2秒后收纳；ESC→MODS设置/预览/任务让位；F8显示开关并恢复任务间距。')
return exported
