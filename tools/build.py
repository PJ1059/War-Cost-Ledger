"""Read the confirmed workbook and build a Bingus-discoverable Lua-only addon."""
from decimal import Decimal
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import xml.etree.ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED
from hit_sources import generate as generate_hit_sources

ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = ROOT / 'pricing' / 'HD2-军需价格表-v0.2.xlsx'
if not WORKBOOK.is_file():
    WORKBOOK = ROOT.parent / 'pricing' / 'HD2-军需价格表-v0.2.xlsx'
RESOURCE = 'mods/hd2_costs/war_cost_ledger'
GUID = 'fd5e720e-6e58-4e4e-a563-e8274b12214c'
NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
NATIVE_ID = 458198946  # HD2Runtime 0.30.3: MG-43 StratagemDefinition.root.id
VERSION = '0.4.69'
CALL_TARGETS = {'ST-021': (NATIVE_ID, 'mg43', 'MG-43 Machine Gun'),
                'ST-022': (14345846, 'm105', 'M-105 Stalwart')}
M105_SOURCE_TYPES = ['A6A735ACCB4A327F', 'B43235DBD493750C', 'B9606C5AAB32C3C2', 'D53EE03481AE73FD']


def workbook_rows(sheet_numbers=(2, 3)):
    with ZipFile(WORKBOOK) as archive:
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            strings = [''.join(item.itertext()) for item in ET.fromstring(archive.read('xl/sharedStrings.xml'))]
        sheets = {}
        for sheet_number in sheet_numbers:
            sheet = ET.fromstring(archive.read(f'xl/worksheets/sheet{sheet_number}.xml'))
            records = {}
            for row in sheet.findall('.//s:row', NS):
                cells = {'row': int(row.get('r'))}
                for cell in row.findall('s:c', NS):
                    cached = cell.find('s:v', NS)
                    value = cached.text if cached is not None else ''
                    if cell.get('t') == 's':
                        value = strings[int(value)]
                    elif cell.get('t') == 'inlineStr':
                        value = ''.join(cell.find('s:is', NS).itertext())
                    cells[re.sub(r'\d+', '', cell.get('r'))] = value
                if cells.get('A'):
                    records[cells['A']] = cells
            sheets[sheet_number] = records
        return sheets


def cents(value):
    value = Decimal(value) * 100
    assert value >= 0 and value == value.to_integral_value(), 'Invalid cached price'
    return int(value)


def confirmed_prices():
    sheets = workbook_rows()
    calls = []
    for price_id, (native_id, key, name) in CALL_TARGETS.items():
        cells = sheets[3][price_id]
        assert cells['P'] == name, f'{price_id} identity changed'
        total, transport, equipment, payload = [cents(cells[c]) for c in ('G', 'D', 'E', 'F')]
        assert total == transport + equipment + payload, 'Call price components do not match'
        assert payload == 0 and cells['L'] == '弹药消耗另记', 'Call accounting policy changed'
        calls.append({
            'key': key, 'row': cells['row'], 'id': price_id, 'name_zh': cells['C'], 'name_en': cells['P'],
            'native_id': native_id, 'total_cents': total, 'transport_cents': transport,
            'equipment_cents': equipment, 'prepaid_ammo_cents': payload, 'policy': cells['L'], 'source': cells['N'],
        })
    cells = sheets[2]['EQ-082']
    assert cells['P'] == 'M-105 Stalwart' and cells['E'] == '发' and cells['G'] == '消耗时计费'
    integration = json.loads((ROOT / 'docs/integration-catalogs.json').read_text(encoding='utf8'))
    for price in integration['calls']:
        row = sheets[3][price['id']]
        assert price['name_en'] == row['P'] and price['total_cents'] == cents(row['G'])
        assert price['policy'] == row['L']
    for price in integration['ammo']:
        row = sheets[2][price['id']]
        assert price['name_en'] == row['P'] and price['unit_cents'] == cents(row['F'])
    magazine_spec = importlib.util.spec_from_file_location('ledger_magazine_prices', ROOT / 'tools/magazine-prices.py')
    magazine_module = importlib.util.module_from_spec(magazine_spec)
    magazine_spec.loader.exec_module(magazine_module)
    inventory_ammo = magazine_module.inventory_prices(integration['ammo'])
    fuel = sheets[2]['EQ-054']
    assert fuel['P'] == 'FLAM-66 Torcher' and fuel['E'] == '显示单位' and cents(fuel['F']) == 30
    inventory_ammo.append({'id': fuel['A'], 'row': fuel['row'], 'name_zh': fuel['C'], 'name_en': fuel['P'],
        'unit_cents': cents(fuel['F']), 'unit': fuel['E'], 'inventory_mode': 'fuel',
        'source_types': ['4FB0F8C02F55C82B'], 'source': fuel['N']})
    inventory_ammo.extend(magazine_module.backpack_fuel_prices(sheets[2], cents))
    stim = sheets[2]['EQ-360']
    assert stim['E'] == '支' and stim['G'] == '消耗时计费' and cents(stim['F']) == 250000
    grenade_spec = importlib.util.spec_from_file_location('ledger_grenade_prices', ROOT / 'tools/grenade-prices.py')
    grenade_module = importlib.util.module_from_spec(grenade_spec)
    grenade_spec.loader.exec_module(grenade_module)
    grenades = grenade_module.build(sheets[2], cents)
    return {
        'version': 'v0.2', 'workbook': WORKBOOK.name,
        'workbook_sha256': hashlib.sha256(WORKBOOK.read_bytes()).hexdigest(), 'calls': integration['calls'],
        'ammo': integration['ammo'], 'deferred_ammo': integration['deferred_ammo'],
        'inventory_ammo': inventory_ammo,
        'heatsinks': magazine_module.heatsink_prices(sheets[2], cents),
        'grenades': grenades['prices'], 'deferred_grenades': grenades['deferred'],
        'stim': {'id': stim['A'], 'row': stim['row'], 'name_zh': stim['C'],
                 'unit_cents': cents(stim['F']), 'unit': stim['E'], 'policy': stim['M'], 'source': stim['N']},
        'deferred_calls': integration['deferred_calls'],
        'm105_ammo': {'id': cells['A'], 'row': cells['row'], 'name_zh': cells['C'], 'name_en': cells['P'],
                     'unit_cents': cents(cells['F']), 'source_types': M105_SOURCE_TYPES, 'source': cells['N']},
    }


def lua_table(data):
    if isinstance(data, bool):
        return 'true' if data else 'false'
    if data is None:
        return 'nil'
    if isinstance(data, dict):
        return '{' + ',\n'.join('[' + json.dumps(key, ensure_ascii=False) + '] = ' + lua_table(value)
                               for key, value in data.items()) + '}'
    if isinstance(data, list):
        return '{' + ','.join(lua_table(value) for value in data) + '}'
    return str(data) if isinstance(data, int) else json.dumps(data, ensure_ascii=False)


# Bingus Shared Loader archive format / seed-zero MurmurHash64A, adapted from CowboyBingus (0BSD).
def resource_hash(name):
    data = name.encode('utf8')
    mask, mix = (1 << 64) - 1, 0xC6A4A7935BD1E995
    value = len(data) * mix & mask
    end = len(data) // 8 * 8
    for (word,) in struct.iter_unpack('<Q', data[:end]):
        word = word * mix & mask
        word ^= word >> 47
        value = (value ^ (word * mix & mask)) * mix & mask
    if data[end:]:
        value = (value ^ int.from_bytes(data[end:], 'little')) * mix & mask
    value ^= value >> 47
    value = value * mix & mask
    return value ^ (value >> 47)


def build():
    price = confirmed_prices()
    hits = generate_hit_sources(ROOT, include_vehicle=True)
    icon_spec = importlib.util.spec_from_file_location('ledger_icons', ROOT / 'tools/prepare-game-icons.py')
    icon_tool = importlib.util.module_from_spec(icon_spec)
    icon_spec.loader.exec_module(icon_tool)
    prepared = icon_tool.game_icon_resources(RESOURCE)
    archive_sdk = icon_tool._sdk_module('hd2_archive')
    radii_spec = importlib.util.spec_from_file_location('ledger_explosion_radii', ROOT / 'tools/explosion-radii.py')
    radii_tool = importlib.util.module_from_spec(radii_spec)
    radii_spec.loader.exec_module(radii_tool)
    explosion_radii = radii_tool.build(icon_tool.SDK)
    icon_fields = ('id', 'key', 'image_id', 'accent', 'packed_bbox', 'symbol_width', 'display_scale')
    game_icons = {'revision': prepared['manifest']['revision'],
        'images': [{key: item[key] for key in icon_fields} for item in prepared['manifest']['images']],
        'metrics': [{key: item[key] for key in icon_fields} for item in prepared['manifest']['metrics']],
        'indicators': [{key: item[key] for key in icon_fields} for item in prepared['manifest']['indicators']],
        'frame': {key: prepared['manifest']['frame'][key] for key in ('image_id', 'accent')}}
    source = (ROOT / 'src' / 'addon.lua').read_text(encoding='utf8')
    copy_probe = (ROOT / 'src/native-code-copy-probe.lua').read_text(encoding='utf8')
    assert copy_probe.count('__NATIVE_CODE_COPY_PROFILE__') == 1
    copy_profile = (ROOT / 'src/native-code-copy-profile.lua').read_text(encoding='utf8')
    copy_probe = copy_probe.replace('__NATIVE_CODE_COPY_PROFILE__', '(function()\n' + copy_profile + '\nend)()')
    copy_source_sha = hashlib.sha256(((ROOT / 'src/native-code-copy-probe.lua').read_bytes()
                                    + (ROOT / 'src/native-code-copy-profile.lua').read_bytes())).hexdigest()
    assert source.count('__CONFIRMED_PRICES__') == 1
    fire = json.loads((ROOT / 'docs/fire-sources.json').read_text(encoding='utf8'))
    integration = json.loads((ROOT / 'docs/integration-catalogs.json').read_text(encoding='utf8'))
    catalog_spec = importlib.util.spec_from_file_location('ledger_career_catalogs', ROOT / 'tools/career-catalogs.py')
    catalog_tool = importlib.util.module_from_spec(catalog_spec)
    catalog_spec.loader.exec_module(catalog_tool)
    career_catalog = catalog_tool.build_catalogs(integration, icon_tool.SDK)
    hellpod_sources = json.loads((ROOT / 'docs/hellpod-kill-sources.json').read_text(encoding='utf8'))['sources']
    for source_hash, pod in hellpod_sources.items():
        career_catalog['weapon_catalog'][source_hash] = {
            'id': source_hash, 'name': pod['name_zh'], 'category': 'stratagem',
            'weapon_type': '空投仓', 'basis': pod['basis']}
    career_catalog['unknown_source_types'] = [value for value in career_catalog['unknown_source_types']
                                               if value not in hellpod_sources]
    assert integration['roster_sha256'] == hashlib.sha256((ROOT / 'docs/enemy-catalog/units.json').read_bytes()).hexdigest()
    source_types = fire['source_types']
    currency = json.loads((ROOT / 'docs/currency-rates-2026-10-11.json').read_text(encoding='utf8'))
    native_hit_profile = json.loads((ROOT / 'docs/native-hit-damage-id-profile-0.4.60.json').read_text(encoding='utf8'))
    native_hit_transaction = json.loads((ROOT / 'docs/native-hit-patch-transaction-v6.json').read_text(encoding='utf8'))
    assert native_hit_profile['revision'] == 'copy_pending_living_target_observer_v1'
    assert native_hit_profile['ricochet_producer_verified'] is False
    assert native_hit_profile['reflection_writeback_source_verified'] is True
    assert native_hit_profile['ordinary_physical_FIFO_publish'] is False
    assert native_hit_profile['physical_success_keeps_normal_AP_pending'] is True
    assert len(native_hit_profile['entries']) == 27 and len(native_hit_profile['sites']) == 8
    assert native_hit_profile['damage_id_extension']['capture_flag'] == 512
    assert native_hit_profile['damage_id_extension']['attribution_only_hit_count'] == 0
    assert native_hit_profile['projectile_id_extension']['capture_flag'] == 2048
    assert native_hit_profile['projectile_id_extension']['record_offset'] == 32
    assert native_hit_profile['projectile_id_extension']['new_hook_sites'] == 0
    assert native_hit_profile['living_target_filter']['health_manager_rva'] == 0x3326688
    assert native_hit_profile['living_target_filter']['commit_rechecks_life'] is False
    assert native_hit_profile['count_contract']['target_alive_at_capture_required'] is True
    assert native_hit_profile['demolition_diagnostic'] == {'revision': 1, 'header_bytes': 64,
                                                         'record_bytes': 128, 'capacity': 32}
    assert native_hit_profile['count_contract']['reflection_writeback_overrides_normal'] is True
    assert native_hit_profile['count_contract']['reflection_writeback_publishes'] is False
    assert native_hit_profile['count_contract']['fresh_reflection_qualification_required'] is True
    assert native_hit_profile['count_contract']['physical_success_overrides_normal'] is False
    assert native_hit_profile['sites'][7] == {'name': 'reflection_writeback', 'region': 'contact',
        'rva': 0x13AE6BC, 'pin_hex': 'f3440f5807', 'replace_bytes': 5,
        'patch_kind': 'OWN_COPY_E8_CALL_NOP', 'original_rva': None}
    assert native_hit_profile['tail_diagnostic'] == {'revision': 1, 'head_offset': 128,
        'head_bytes': 32, 'scratch_offset': 160, 'record_offset': 256, 'record_bytes': 96,
        'capacity': 16, 'alt_tag': 3, 'true_tag': 4}
    assert native_hit_transaction['abi'] == 3
    assert source_types and len(source_types) == len(set(source_types))
    assert all(re.fullmatch('[0-9A-F]{16}', value) for value in source_types)
    replacements = {'__RUNTIME_COMPAT_MODULE__': (ROOT / 'src/runtime-compat.lua').read_text(encoding='utf8'),
                    '__LOCALIZATION_MODULE__': (ROOT / 'src/localization.lua').read_text(encoding='utf8'),
                    '__LOCALIZATION_CATALOG__': lua_table(json.loads((ROOT / 'docs/localization-en.json').read_text(encoding='utf8'))),
                    '__CONFIRMED_PRICES__': lua_table(price), '__FIRE_SOURCES__': lua_table(source_types),
                    '__KILL_SOURCE_TRAITS__': lua_table(json.loads((ROOT / 'docs/kill-source-traits.json').read_text(encoding='utf8'))['source_types']),
                    '__TARGET_DAMAGE_ATTRIBUTION_MODULE__': (ROOT / 'src/target-damage-attribution.lua').read_text(encoding='utf8'),
                    '__DAMAGE_SOURCE_CATALOG__': lua_table({key: json.loads((ROOT / 'docs/damage-source-catalog.json').read_text(encoding='utf8'))[key]
                                                         for key in ('reverse', 'source_radius', 'resource_nodes', 'explosion_names')}),
                    '__DAMAGE_SOURCE_RESOLVER_MODULE__': (ROOT / 'src/damage-source-resolver.lua').read_text(encoding='utf8'),
                    '__STATUS_DAMAGE_CONTEXTS__': lua_table({**json.loads((ROOT / 'docs/gas-status-contexts-0.4.57.json').read_text(encoding='utf8'))['entries'],
                        **json.loads((ROOT / 'docs/ground-fire-contexts-0.4.66.json').read_text(encoding='utf8'))['entries']}),
                    '__COMBAT_SOURCE_TOTALS_MODULE__': (ROOT / 'src/combat-source-totals.lua').read_text(encoding='utf8'),
                    '__CAREER_WEAPON_CATALOG__': lua_table(career_catalog['weapon_catalog']),
                    '__COMBAT_RECORDS_MODULE__': (ROOT / 'src/combat-records.lua').read_text(encoding='utf8'),
                    '__NATIVE_DEATH_READER_MODULE__': (ROOT / 'src/native-death-reader.lua').read_text(encoding='utf8'),
                    '__DEATH_OBSERVER_MODULE__': (ROOT / 'src/death-observer.lua').read_text(encoding='utf8'),
                    '__CAREER_COMBAT_PANEL_MODEL_MODULE__': (ROOT / 'src/career-combat-panel-model.lua').read_text(encoding='utf8'),
                    '__CAREER_SEARCH_INPUT_MODULE__': (ROOT / 'src/career-search-input.lua').read_text(encoding='utf8'),
                    '__HIT_SOURCES__': lua_table(hits['sources']),
                    '__NATIVE_HIT_PROFILE__': lua_table(native_hit_profile),
                    '__NATIVE_HIT_TRANSACTION__': lua_table(native_hit_transaction),
                    '__NATIVE_HIT_FEEDBACK_MODULE__': (ROOT / 'src/native-hit-feedback.lua').read_text(encoding='utf8'),
                    '__NATIVE_HIT_CONNECTOR_MODULE__': (ROOT / 'src/native-hit-connector.lua').read_text(encoding='utf8'),
                    '__NATIVE_HIT_PACKAGE_MODULE__': (ROOT / 'src/native-hit-package.lua').read_text(encoding='utf8'),
                    '__DEMOLITION_WORLD_MODULE__': (ROOT / 'src/demolition-world.lua').read_text(encoding='utf8'),
                    '__DEMOLITION_CANDIDATES_MODULE__': (ROOT / 'src/demolition-candidates.lua').read_text(encoding='utf8'),
                    '__DEMOLITION_ATTRIBUTION_MODULE__': (ROOT / 'src/demolition-attribution.lua').read_text(encoding='utf8'),
                    '__BUGHOLE_WORLD_MODULE__': (ROOT / 'src/demolition-world.lua').read_text(encoding='utf8'),
                    '__BUGHOLE_OBSERVER_MODULE__': (ROOT / 'src/bughole-observer.lua').read_text(encoding='utf8'),
                    '__EXPLOSION_RADII__': lua_table(explosion_radii),
                    '__NATIVE_HIT_COPY_LINK_MODULE__': (ROOT / 'src/native-hit-copy-link.lua').read_text(encoding='utf8'),
                    '__NATIVE_HIT_COPY_HOST_MODULE__': (ROOT / 'src/native-hit-copy-host.lua').read_text(encoding='utf8'),
                    '__NATIVE_HIT_SESSION_MODULE__': (ROOT / 'src/native-hit-session.lua').read_text(encoding='utf8'),
                    '__PROJECTILE_HIT_STATS_MODULE__': (ROOT / 'src/projectile-hit-stats.lua').read_text(encoding='utf8'),
                    '__CAREER_KD_MODULE__': (ROOT / 'src/career-kd.lua').read_text(encoding='utf8'),
                    '__CAREER_AWARD_RECORDS_MODULE__': (ROOT / 'src/career-award-records.lua').read_text(encoding='utf8'),
                    '__MISSION_HISTORY_MODULE__': (ROOT / 'src/mission-history.lua').read_text(encoding='utf8'),
                    '__CAREER_HISTORY_SUMMARY_MODULE__': (ROOT / 'src/career-history-summary.lua').read_text(encoding='utf8'),
                    '__CAREER_PAGE_SYNC_MODULE__': (ROOT / 'src/career-page-sync.lua').read_text(encoding='utf8'),
                    '__CAREER_SHIP_SYNC_MODULE__': (ROOT / 'src/career-ship-sync.lua').read_text(encoding='utf8'),
                    '__NATIVE_CAREER_COUNTERS_MODULE__': (ROOT / 'src/native-career-counters.lua').read_text(encoding='utf8'),
                    '__NATIVE_CAREER_READER_MODULE__': (ROOT / 'src/native-career-reader.lua').read_text(encoding='utf8'),
                    '__NATIVE_CAREER_PANEL_READER_MODULE__': (ROOT / 'src/native-career-panel-reader.lua').read_text(encoding='utf8'),
                    '__CAREER_PANEL_MODEL_MODULE__': (ROOT / 'src/career-panel-model.lua').read_text(encoding='utf8'),
                    '__CAREER_PANEL_FEED_MODULE__': (ROOT / 'src/career-panel-feed.lua').read_text(encoding='utf8'),
                    '__ENGINE_EXPORT_INVENTORY_MODULE__': (ROOT / 'src/engine-export-inventory.lua').read_text(encoding='utf8'),
                    '__ENGINE_EXPORTS_SOURCE_SHA__': lua_table(hashlib.sha256((ROOT / 'src/engine-export-inventory.lua').read_bytes()).hexdigest()),
                    '__ENGINE_CFUNCTION_READER_MODULE__': (ROOT / 'src/engine-cfunction-reader.lua').read_text(encoding='utf8'),
                    '__ENGINE_CFUNCTION_SOURCE_SHA__': lua_table(hashlib.sha256((ROOT / 'src/engine-cfunction-reader.lua').read_bytes()).hexdigest()),
                    '__PLUGIN_FRAME_PROBE_MODULE__': (ROOT / 'src/native-plugin-frame-probe.lua').read_text(encoding='utf8'),
                    '__PLUGIN_FRAME_PROBE_SOURCE_SHA__': lua_table(hashlib.sha256((ROOT / 'src/native-plugin-frame-probe.lua').read_bytes()).hexdigest()),
                    '__NATIVE_CODE_COPY_PROBE_MODULE__': copy_probe,
                    '__CODE_COPY_RUNNER_MODULE__': (ROOT / 'src/code-copy-runner.lua').read_text(encoding='utf8'),
                    '__CODE_COPY_PROBE_SOURCE_SHA__': lua_table(copy_source_sha),
                    '__CURRENCY_RATES__': lua_table({key: currency[key] for key in ('rates', 'as_of', 'requested_date', 'mc_usd_rate')}),
                    '__CURRENCY_MODULE__': (ROOT / 'src/currency.lua').read_text(encoding='utf8'),
                    '__ENEMY_TYPES__': lua_table(integration['entities']), '__SOURCE_NAMES__': lua_table(integration['stat_sources']),
                    '__KILL_OBSERVER_MODULE__': (ROOT / 'src/kill-observer.lua').read_text(encoding='utf8'),
                    '__COMBAT_ACHIEVEMENTS_MODULE__': (ROOT / 'src/combat-achievements.lua').read_text(encoding='utf8'),
                    '__VEHICLE_KILL_RIBBONS_MODULE__': (ROOT / 'src/vehicle-kill-ribbons.lua').read_text(encoding='utf8'),
                    '__VEHICLE_BODY_SOURCES__': lua_table(json.loads((ROOT / 'docs/vehicle-body-kill-sources.json').read_text(encoding='utf8'))['sources']),
                    '__HELLPOD_SOURCES__': lua_table(hellpod_sources),
                    '__KILL_SOURCE_NOTICES_MODULE__': (ROOT / 'src/kill-source-notices.lua').read_text(encoding='utf8'),
                    '__RECON_CHAT_MODULE__': (ROOT / 'src/recon-chat.lua').read_text(encoding='utf8'),
                    '__NATIVE_RECON_READER_MODULE__': (ROOT / 'src/native-recon-reader.lua').read_text(encoding='utf8'),
                    '__MAGAZINE_BILLING_MODULE__': (ROOT / 'src/magazine-billing.lua').read_text(encoding='utf8'),
                    '__STIM_BILLING_MODULE__': (ROOT / 'src/stim-billing.lua').read_text(encoding='utf8'),
                    '__CONSUMABLE_READER_MODULE__': (ROOT / 'src/consumable-reader.lua').read_text(encoding='utf8'),
                    '__GRENADE_READER_MODULE__': (ROOT / 'src/grenade-reader.lua').read_text(encoding='utf8'),
                    '__GRENADE_BILLING_MODULE__': (ROOT / 'src/grenade-billing.lua').read_text(encoding='utf8'),
                    '__KILL_SOURCE_ATTRIBUTION_MODULE__': (ROOT / 'src/kill-source-attribution.lua').read_text(encoding='utf8'),
                    '__NATIVE_STATS_MODULE__': (ROOT / 'src/native-stats.lua').read_text(encoding='utf8'),
                    '__STAT_PROBE_MODULE__': (ROOT / 'src/stat-probe.lua').read_text(encoding='utf8'),
                    '__BATTLE_HUD_MODULE__': (ROOT / 'src/battle-hud.lua').read_text(encoding='utf8'),
                    '__GAME_ICONS__': lua_table(game_icons),
                    '__GAME_HUD_MODULE__': (ROOT / 'src/game-hud.lua').read_text(encoding='utf8'),
                    '__HUD_LAYOUT_MODULE__': (ROOT / 'src/hud-layout.lua').read_text(encoding='utf8'),
                    '__CHARGE_NOTIFICATIONS_MODULE__': (ROOT / 'src/charge-notifications.lua').read_text(encoding='utf8'),
                    '__NATIVE_HUD_FEED_MODULE__': (ROOT / 'src/native-hud-feed.lua').read_text(encoding='utf8'),
                    '__AWARD_NOTIFICATIONS_MODULE__': (ROOT / 'src/award-notifications.lua').read_text(encoding='utf8'),
                    '__UI_SETTINGS_MODULE__': (ROOT / 'src/ui-settings.lua').read_text(encoding='utf8'),
                    '__NATIVE_UI_BRIDGE_MODULE__': (ROOT / 'src/native-ui-bridge.lua').read_text(encoding='utf8'),
                    '__NATIVE_TASK_LAYOUT_MODULE__': (ROOT / 'src/native-task-layout.lua').read_text(encoding='utf8'),
                    '__UI_LAYOUT_CAPTURE_MODULE__': (ROOT / 'src/ui-layout-capture.lua').read_text(encoding='utf8'),
                    '__TASK_LAYOUT_CODE_PROBE_MODULE__': (ROOT / 'src/task-layout-code-probe.lua').read_text(encoding='utf8')}
    for token, value in replacements.items():
        assert source.count(token) == 1
        source = source.replace(token, value)
    source = source.encode('utf8')
    resources = prepared['resources']
    resources[(archive_sdk.LUA_TYPE, resource_hash(RESOURCE))] = (archive_sdk.lua_resource(source), b'')
    native_resource = 'mods/hd2_costs/war_cost_native_hud'
    native_module = (ROOT / 'src/native-hud-addon.lua').read_text(encoding='utf8')
    declaration = f'local HD2_HUD_ADDON = "{native_resource}"\n'
    assert native_module.startswith(declaration), 'HUD+ discovery declaration must be the first line'
    native_art = {**prepared['manifest'], 'images': [dict(item) for item in prepared['manifest']['images']],
                  'frame': dict(prepared['manifest']['frame']),
                  'ui': {key: {**item, 'resource_name': item['resource'], 'resource': item['resource_hash']}
                         for key, item in prepared['manifest']['ui'].items()}}
    for item in [*native_art['images'], *native_art['metrics'], *native_art['indicators'], native_art['frame']]:
        item['resource_hash'] = f"{archive_sdk.resource_hash(item['resource']):016x}"
    native_source = (declaration + 'return (function()\n' + native_module
                     + '\nend)()({art=' + lua_table(native_art) + ',career=(function()\n'
                     + (ROOT / 'src/native-career-hud.lua').read_text(encoding='utf8')
                     + '\nend)()})\n').encode('utf8')
    resources[(archive_sdk.LUA_TYPE, resource_hash(native_resource))] = (archive_sdk.lua_resource(native_source), b'')
    archive, gpu = archive_sdk.make_resource_archive(resources)
    assert archive_sdk.read_archive(archive, gpu) == resources
    description = '0.4.69: Remove the F9 shortcut and independent archive window. Keep the normal Armory Career entry, Runtime API 1 compatibility checks, existing native HUD integration and Runtime combat fallback. F8 still toggles the combat display. Existing history, settings and accounts are preserved.'
    manifest = {'Version': 1, 'Guid': GUID, 'Name': 'HD2 War Cost Ledger - ' + VERSION,
                'Description': description, 'Options': [{'Name': '盟友计费与个人战斗统计',
                'Description': description, 'Include': ['Addon']}]}
    files = {
        'manifest.json': json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf8'),
        'Addon/9ba626afa44a3aa3.patch_0': archive,
        'Addon/9ba626afa44a3aa3.patch_0.stream': b'',
        'Addon/9ba626afa44a3aa3.patch_0.gpu_resources': gpu,
        'README.md': (ROOT / 'README.md').read_bytes(),
        'CURRENT-STATUS.md': (ROOT / 'CURRENT-STATUS.md').read_bytes(),
        'LIMITATIONS.md': (ROOT / 'LIMITATIONS.md').read_bytes(),
        'docs/artwork-integration-0.4.58.md': (ROOT / 'docs/artwork-integration-0.4.58.md').read_bytes(),
        'docs/ribbon-frame-fix-0.4.59.md': (ROOT / 'docs/ribbon-frame-fix-0.4.59.md').read_bytes(),
        'docs/damage-decode-0.4.60.md': (ROOT / 'docs/damage-decode-0.4.60.md').read_bytes(),
        'docs/death-causes-0.4.61.md': (ROOT / 'docs/death-causes-0.4.61.md').read_bytes(),
        'docs/burst-kill-sources-0.4.62.md': (ROOT / 'docs/burst-kill-sources-0.4.62.md').read_bytes(),
        'docs/damage-window-kd-0.4.63.md': (ROOT / 'docs/damage-window-kd-0.4.63.md').read_bytes(),
        'docs/career-fixes-0.4.64.md': (ROOT / 'docs/career-fixes-0.4.64.md').read_bytes(),
        'docs/target-kill-pairs-0.4.62.md': (ROOT / 'docs/target-kill-pairs-0.4.62.md').read_bytes(),
        'Source/hellpod-kill-sources.json': (ROOT / 'docs/hellpod-kill-sources.json').read_bytes(),
        'docs/combat-records.md': (ROOT / 'docs/combat-records.md').read_bytes(),
        'docs/death-observer-contract.md': (ROOT / 'docs/death-observer-contract.md').read_bytes(),
        'THIRD-PARTY.md': (ROOT / 'THIRD-PARTY.md').read_bytes(),
        'LICENSE': (ROOT / 'LICENSE').read_bytes(),
        'NOTICE': (ROOT / 'NOTICE').read_bytes(),
        'docs/DATA-SOURCES.md': (ROOT / 'docs/DATA-SOURCES.md').read_bytes(),
        'docs/releases/v0.4.65.md': (ROOT / 'docs/releases/v0.4.65.md').read_bytes(),
        'docs/releases/v0.4.68.md': (ROOT / 'docs/releases/v0.4.68.md').read_bytes(),
        'docs/releases/v0.4.69.md': (ROOT / 'docs/releases/v0.4.69.md').read_bytes(),
        'docs/dependency-compatibility-0.4.68.md': (ROOT / 'docs/dependency-compatibility-0.4.68.md').read_bytes(),
        'docs/releases/v0.4.65-credits.txt': (ROOT / 'docs/releases/v0.4.65-credits.txt').read_bytes(),
        'artwork/mod-covers-0.4.65-v2/war-cost-ledger-cover-en-1920x1080.png': (ROOT / 'artwork/mod-covers-0.4.65-v2/war-cost-ledger-cover-en-1920x1080.png').read_bytes(),
        'pricing/HD2-军需价格表-v0.2.xlsx': WORKBOOK.read_bytes(),
        'Source/addon.lua': source,
        'Source/runtime-compat.lua': (ROOT / 'src/runtime-compat.lua').read_bytes(),
        'Source/confirmed-prices.json': json.dumps(price, ensure_ascii=False, indent=2).encode('utf8'),
        'Source/fire-sources.json': (ROOT / 'docs/fire-sources.json').read_bytes(),
        'Source/native-stats.lua': (ROOT / 'src/native-stats.lua').read_bytes(),
        'Source/stat-probe.lua': (ROOT / 'src/stat-probe.lua').read_bytes(),
        'Source/kill-observer.lua': (ROOT / 'src/kill-observer.lua').read_bytes(),
        'Source/combat-achievements.lua': (ROOT / 'src/combat-achievements.lua').read_bytes(),
        'Source/target-damage-attribution.lua': (ROOT / 'src/target-damage-attribution.lua').read_bytes(),
        'Source/damage-source-resolver.lua': (ROOT / 'src/damage-source-resolver.lua').read_bytes(),
        'docs/damage-source-catalog.json': (ROOT / 'docs/damage-source-catalog.json').read_bytes(),
        'docs/damage-id-attribution-0.4.54.md': (ROOT / 'docs/damage-id-attribution-0.4.54.md').read_bytes(),
        'docs/melee-source-0.4.55.md': (ROOT / 'docs/melee-source-0.4.55.md').read_bytes(),
        'docs/continuous-damage-chain-0.4.56.md': (ROOT / 'docs/continuous-damage-chain-0.4.56.md').read_bytes(),
        'docs/gas-status-contexts-0.4.57.json': (ROOT / 'docs/gas-status-contexts-0.4.57.json').read_bytes(),
        'docs/ground-fire-contexts-0.4.66.json': (ROOT / 'docs/ground-fire-contexts-0.4.66.json').read_bytes(),
        'docs/releases/v0.4.66.md': (ROOT / 'docs/releases/v0.4.66.md').read_bytes(),
        'docs/releases/v0.4.67.md': (ROOT / 'docs/releases/v0.4.67.md').read_bytes(),
        'docs/career-records-0.4.67.md': (ROOT / 'docs/career-records-0.4.67.md').read_bytes(),
        'docs/sc-currency-0.4.67.md': (ROOT / 'docs/sc-currency-0.4.67.md').read_bytes(),
        'docs/unit-ribbon-coverage-0.4.67.md': (ROOT / 'docs/unit-ribbon-coverage-0.4.67.md').read_bytes(),
        'docs/g8-ground-fire-0.4.67.md': (ROOT / 'docs/g8-ground-fire-0.4.67.md').read_bytes(),
        'docs/combat-polish-0.4.57.md': (ROOT / 'docs/combat-polish-0.4.57.md').read_bytes(),
        'docs/storage-status-0.4.57.md': (ROOT / 'docs/storage-status-0.4.57.md').read_bytes(),
        'docs/career-query-performance-0.4.57.json': (ROOT / 'docs/career-query-performance-0.4.57.json').read_bytes(),
        'Source/combat-source-totals.lua': (ROOT / 'src/combat-source-totals.lua').read_bytes(),
        'Source/kill-source-traits.json': (ROOT / 'docs/kill-source-traits.json').read_bytes(),
        'docs/heatsink-reader-evidence.json': (ROOT / 'docs/heatsink-reader-evidence.json').read_bytes(),
        'docs/backpack-fuel-billing-evidence.json': (ROOT / 'docs/backpack-fuel-billing-evidence.json').read_bytes(),
        'docs/billing-fixes-0.4.52.md': (ROOT / 'docs/billing-fixes-0.4.52.md').read_bytes(),
        'docs/career-patriotic-bill-0.4.52.md': (ROOT / 'docs/career-patriotic-bill-0.4.52.md').read_bytes(),
        'docs/target-damage-performance.json': (ROOT / 'docs/target-damage-performance.json').read_bytes(),
        'docs/damage-attribution-0.4.52.md': (ROOT / 'docs/damage-attribution-0.4.52.md').read_bytes(),
        'docs/kill-source-regression-0.4.53.md': (ROOT / 'docs/kill-source-regression-0.4.53.md').read_bytes(),
        'Source/vehicle-kill-ribbons.lua': (ROOT / 'src/vehicle-kill-ribbons.lua').read_bytes(),
        'Source/kill-source-notices.lua': (ROOT / 'src/kill-source-notices.lua').read_bytes(),
        'Source/recon-chat.lua': (ROOT / 'src/recon-chat.lua').read_bytes(),
        'Source/native-recon-reader.lua': (ROOT / 'src/native-recon-reader.lua').read_bytes(),
        'docs/enemy-observer-0.4.49.md': (ROOT / 'docs/enemy-observer-0.4.49.md').read_bytes(),
        'docs/fire-gas-source-research-0.4.51.md': (ROOT / 'docs/fire-gas-source-research-0.4.51.md').read_bytes(),
        'docs/vehicle-body-kill-sources.json': (ROOT / 'docs/vehicle-body-kill-sources.json').read_bytes(),
        'docs/vehicle-body-kill-contract.md': (ROOT / 'docs/vehicle-body-kill-contract.md').read_bytes(),
        'docs/kill-source-notice-research.md': (ROOT / 'docs/kill-source-notice-research.md').read_bytes(),
        'Source/magazine-billing.lua': (ROOT / 'src/magazine-billing.lua').read_bytes(),
        'Source/stim-billing.lua': (ROOT / 'src/stim-billing.lua').read_bytes(),
        'Source/consumable-reader.lua': (ROOT / 'src/consumable-reader.lua').read_bytes(),
        'Source/grenade-reader.lua': (ROOT / 'src/grenade-reader.lua').read_bytes(),
        'Source/grenade-billing.lua': (ROOT / 'src/grenade-billing.lua').read_bytes(),
        'Source/kill-source-attribution.lua': (ROOT / 'src/kill-source-attribution.lua').read_bytes(),
        'Source/combat-records.lua': (ROOT / 'src/combat-records.lua').read_bytes(),
        'Source/native-death-reader.lua': (ROOT / 'src/native-death-reader.lua').read_bytes(),
        'Source/death-observer.lua': (ROOT / 'src/death-observer.lua').read_bytes(),
        'Source/career-combat-panel-model.lua': (ROOT / 'src/career-combat-panel-model.lua').read_bytes(),
        'Source/career-search-input.lua': (ROOT / 'src/career-search-input.lua').read_bytes(),
        'Source/career-weapon-catalog.json': json.dumps(career_catalog, ensure_ascii=False, indent=2).encode('utf8'),
        'Source/projectile-hit-stats.lua': (ROOT / 'src/projectile-hit-stats.lua').read_bytes(),
        'Source/career-kd.lua': (ROOT / 'src/career-kd.lua').read_bytes(),
        'Source/career-award-records.lua': (ROOT / 'src/career-award-records.lua').read_bytes(),
        'Source/mission-history.lua': (ROOT / 'src/mission-history.lua').read_bytes(),
        'Source/career-history-summary.lua': (ROOT / 'src/career-history-summary.lua').read_bytes(),
        'Source/native-career-panel-reader.lua': (ROOT / 'src/native-career-panel-reader.lua').read_bytes(),
        'Source/career-panel-model.lua': (ROOT / 'src/career-panel-model.lua').read_bytes(),
        'Source/career-panel-feed.lua': (ROOT / 'src/career-panel-feed.lua').read_bytes(),
        'Source/native-career-hud.lua': (ROOT / 'src/native-career-hud.lua').read_bytes(),
        'docs/career-awards-panel.md': (ROOT / 'docs/career-awards-panel.md').read_bytes(),
        'Source/career-page-sync.lua': (ROOT / 'src/career-page-sync.lua').read_bytes(),
        'Source/career-ship-sync.lua': (ROOT / 'src/career-ship-sync.lua').read_bytes(),
        'Source/native-career-counters.lua': (ROOT / 'src/native-career-counters.lua').read_bytes(),
        'Source/native-career-reader.lua': (ROOT / 'src/native-career-reader.lua').read_bytes(),
        'Source/engine-export-inventory.lua': (ROOT / 'src/engine-export-inventory.lua').read_bytes(),
        'Source/engine-cfunction-reader.lua': (ROOT / 'src/engine-cfunction-reader.lua').read_bytes(),
        'Source/native-plugin-frame-probe.lua': (ROOT / 'src/native-plugin-frame-probe.lua').read_bytes(),
        'Source/native-code-copy-probe.lua': (ROOT / 'src/native-code-copy-probe.lua').read_bytes(),
        'Source/native-code-copy-profile.lua': (ROOT / 'src/native-code-copy-profile.lua').read_bytes(),
        'Source/code-copy-runner.lua': (ROOT / 'src/code-copy-runner.lua').read_bytes(),
        'docs/engine-cfunction-reader.md': (ROOT / 'docs/engine-cfunction-reader.md').read_bytes(),
        'docs/engine-export-inventory.md': (ROOT / 'docs/engine-export-inventory.md').read_bytes(),
        'docs/career-page-sync.md': (ROOT / 'docs/career-page-sync.md').read_bytes(),
        'Source/native-hit-feedback.lua': (ROOT / 'src/native-hit-feedback.lua').read_bytes(),
        'Source/native-hit-connector.lua': (ROOT / 'src/native-hit-connector.lua').read_bytes(),
        'Source/native-hit-package.lua': (ROOT / 'src/native-hit-package.lua').read_bytes(),
        'Source/demolition-world.lua': (ROOT / 'src/demolition-world.lua').read_bytes(),
        'Source/demolition-candidates.lua': (ROOT / 'src/demolition-candidates.lua').read_bytes(),
        'Source/demolition-attribution.lua': (ROOT / 'src/demolition-attribution.lua').read_bytes(),
        'Source/bughole-observer.lua': (ROOT / 'src/bughole-observer.lua').read_bytes(),
        'Source/explosion-radii.json': json.dumps(explosion_radii,ensure_ascii=False,indent=2).encode('utf8'),
        'docs/demolition-attribution.md': (ROOT / 'docs/demolition-attribution.md').read_bytes(),
        'docs/native-demolition-diagnostic-profile-v1.json': (ROOT / 'docs/native-demolition-diagnostic-profile-v1.json').read_bytes(),
        'docs/native-hit-living-target-profile-v1.json': (ROOT / 'docs/native-hit-living-target-profile-v1.json').read_bytes(),
        'docs/native-hit-vehicle-source-profile-v1.json': (ROOT / 'docs/native-hit-vehicle-source-profile-v1.json').read_bytes(),
        'docs/native-hit-damage-id-profile-v1.json': (ROOT / 'docs/native-hit-damage-id-profile-v1.json').read_bytes(),
        'docs/native-hit-damage-id-profile-0.4.60.json': (ROOT / 'docs/native-hit-damage-id-profile-0.4.60.json').read_bytes(),
        'docs/tank-hit-source-evidence.json': (ROOT / 'docs/tank-hit-source-evidence.json').read_bytes(),
        'docs/tank-hit-contract.md': (ROOT / 'docs/tank-hit-contract.md').read_bytes(),
        'docs/resource-hash-aliases.json': (ROOT / 'docs/resource-hash-aliases.json').read_bytes(),
        'docs/BUILDING.md': (ROOT / 'docs/BUILDING.md').read_bytes(),
        'docs/demolition-consumer-contract.md': (ROOT / 'docs/demolition-consumer-contract.md').read_bytes(),
        'Source/native-hit-copy-link.lua': (ROOT / 'src/native-hit-copy-link.lua').read_bytes(),
        'Source/native-hit-copy-host.lua': (ROOT / 'src/native-hit-copy-host.lua').read_bytes(),
        'Source/native-hit-install.lua': (ROOT / 'src/native-hit-install.lua').read_bytes(),
        'Source/native-hit-session.lua': (ROOT / 'src/native-hit-session.lua').read_bytes(),
        'docs/native-hit-observer-package-v6.json': (ROOT / 'docs/native-hit-observer-package-v6.json').read_bytes(),
        'docs/native-hit-copy-observer-v1.json': (ROOT / 'docs/native-hit-copy-observer-v1.json').read_bytes(),
        'docs/native-hit-patch-transaction-v6.json': (ROOT / 'docs/native-hit-patch-transaction-v6.json').read_bytes(),
        'docs/native-hit-run-control-v1.json': (ROOT / 'docs/native-hit-run-control-v1.json').read_bytes(),
        'docs/hit-stat-sources.json': json.dumps(hits, ensure_ascii=False, indent=2).encode('utf8'),
        'Source/localization.lua': (ROOT / 'src/localization.lua').read_bytes(),
        'Source/localization-en.lua': ('return ' + lua_table(json.loads((ROOT / 'docs/localization-en.json').read_text(encoding='utf8'))) + '\n').encode('utf8'),
        'docs/localization-en.json': (ROOT / 'docs/localization-en.json').read_bytes(),
        'docs/localization-0.4.65.md': (ROOT / 'docs/localization-0.4.65.md').read_bytes(),
        'Source/currency.lua': (ROOT / 'src/currency.lua').read_bytes(),
        'docs/currency-rates-2026-10-11.json': (ROOT / 'docs/currency-rates-2026-10-11.json').read_bytes(),
        'docs/consumable-billing.md': (ROOT / 'docs/consumable-billing.md').read_bytes(),
        'docs/grenade-pricing-evidence.json': (ROOT / 'docs/grenade-pricing-evidence.json').read_bytes(),
        'docs/grenade-billing.md': (ROOT / 'docs/grenade-billing.md').read_bytes(),
        'docs/magazine-pricing-evidence.json': (ROOT / 'docs/magazine-pricing-evidence.json').read_bytes(),
        'Source/battle-hud.lua': (ROOT / 'src/battle-hud.lua').read_bytes(),
        'Source/game-hud.lua': (ROOT / 'src/game-hud.lua').read_bytes(),
        'Source/hud-layout.lua': (ROOT / 'src/hud-layout.lua').read_bytes(),
        'Source/charge-notifications.lua': (ROOT / 'src/charge-notifications.lua').read_bytes(),
        'docs/hud-layout-0.4.30.md': (ROOT / 'docs/hud-layout-0.4.30.md').read_bytes(),
        'Source/native-hud-feed.lua': (ROOT / 'src/native-hud-feed.lua').read_bytes(),
        'Source/native-hud-addon.lua': native_source,
        'Source/award-notifications.lua': (ROOT / 'src/award-notifications.lua').read_bytes(),
        'Source/ui-settings.lua': (ROOT / 'src/ui-settings.lua').read_bytes(),
        'Source/native-ui-bridge.lua': (ROOT / 'src/native-ui-bridge.lua').read_bytes(),
        'Source/native-task-layout.lua': (ROOT / 'src/native-task-layout.lua').read_bytes(),
        'Source/ui-layout-capture.lua': (ROOT / 'src/ui-layout-capture.lua').read_bytes(),
        'Source/ui-tree-probe.lua': (ROOT / 'src/ui-tree-probe.lua').read_bytes(),
        'Source/task-layout-code-probe.lua': (ROOT / 'src/task-layout-code-probe.lua').read_bytes(),
        'Source/game-icons.lua': ('return ' + lua_table(game_icons) + '\n').encode('utf8'),
        'docs/integration-catalogs.json': (ROOT / 'docs/integration-catalogs.json').read_bytes(),
        'docs/enemy-hash-evidence.json': (ROOT / 'docs/enemy-hash-evidence.json').read_bytes(),
        'docs/integration-0.4.0.md': (ROOT / 'docs/integration-0.4.0.md').read_bytes(),
        'docs/ui-design.md': (ROOT / 'docs/ui-design.md').read_bytes(),
        'docs/native-hit-reader-research.md': (ROOT / 'docs/native-hit-reader-research.md').read_bytes(),
        'docs/integration-0.4.12.md': (ROOT / 'docs/integration-0.4.12.md').read_bytes(),
        'docs/recon-chat-integration.md': (ROOT / 'docs/recon-chat-integration.md').read_bytes(),
        'docs/native-status-reader-research.md': (ROOT / 'docs/native-status-reader-research.md').read_bytes(),
        'docs/kill-observer-performance.json': (ROOT / 'docs/kill-observer-performance.json').read_bytes(),
        'docs/fire-sources.json': (ROOT / 'docs/fire-sources.json').read_bytes(),
        'docs/native-stat-verification.md': (ROOT / 'docs/native-stat-verification.md').read_bytes(),
        'docs/performance-baseline.json': (ROOT / 'docs/performance-baseline.json').read_bytes(),
        'docs/probe-capture-performance.json': (ROOT / 'docs/probe-capture-performance.json').read_bytes(),
        'docs/external-probe.md': (ROOT / 'docs/external-probe.md').read_bytes(),
        'docs/automatic-ui-probe.md': (ROOT / 'docs/automatic-ui-probe.md').read_bytes(),
        'docs/task-layout-code-probe.md': (ROOT / 'docs/task-layout-code-probe.md').read_bytes(),
        'docs/native-task-layout.md': (ROOT / 'docs/native-task-layout.md').read_bytes(),
        'docs/绶带与成就-原文副本.md': (ROOT / 'docs/绶带与成就-原文副本.md').read_bytes(),
        'docs/绶带与成就-实现分类.md': (ROOT / 'docs/绶带与成就-实现分类.md').read_bytes(),
        'docs/achievement-catalog.json': (ROOT / 'docs/achievement-catalog.json').read_bytes(),
        'docs/achievement-reader-performance.json': (ROOT / 'docs/achievement-reader-performance.json').read_bytes(),
        'tools/stat-probe.py': (ROOT / 'tools/stat-probe.py').read_bytes(),
        'tools/probe_session.py': (ROOT / 'tools/probe_session.py').read_bytes(),
        'tools/probe_decode.py': (ROOT / 'tools/probe_decode.py').read_bytes(),
        'tools/probe-launcher.pyw': (ROOT / 'tools/probe-launcher.pyw').read_bytes(),
        'tools/interface-code-capture.py': (ROOT / 'tools/interface-code-capture.py').read_bytes(),
        'tools/recon_chat_code_capture.py': (ROOT / 'tools/recon_chat_code_capture.py').read_bytes(),
        'tools/status-code-capture.py': (ROOT / 'tools/status-code-capture.py').read_bytes(),
        'tools/hit-code-capture.py': (ROOT / 'tools/hit-code-capture.py').read_bytes(),
        'tools/fire_code_capture.py': (ROOT / 'tools/fire_code_capture.py').read_bytes(),
        'tools/fire_code_windows.py': (ROOT / 'tools/fire_code_windows.py').read_bytes(),
        '启动探针.cmd': (ROOT / '启动探针.cmd').read_bytes(),
    }
    files.update(prepared['files'])
    output = ROOT / 'dist'
    output.mkdir(exist_ok=True)
    (output / 'addon.lua').write_bytes(source)
    (output / 'native-hud-addon.lua').write_bytes(native_source)
    (output / 'native-game-art.lua').write_text('return ' + lua_table(native_art) + '\n', encoding='utf8')
    (output / 'localization-en.lua').write_bytes(files['Source/localization-en.lua'])
    (output / 'game-icons.lua').write_bytes(files['Source/game-icons.lua'])
    (output / 'confirmed-prices.json').write_bytes(files['Source/confirmed-prices.json'])
    (output / 'hit-stat-sources.json').write_bytes(files['docs/hit-stat-sources.json'])
    (output / 'currency-rates.lua').write_text('return ' + lua_table(currency) + '\n', encoding='utf8')
    target = output / ('HD2-War-Cost-Ledger-' + VERSION + '.zip')
    with ZipFile(target, 'w', compression=ZIP_DEFLATED) as package:
        for name, data in files.items():
            package.writestr(name, data)
    print(f'Built {target}')
    print(f'{len(price["calls"])} stratagem prices; {len(price["ammo"])} ammunition prices; '
          f'M-105: {price["m105_ammo"]["unit_cents"] / 100:.2f} MC/round')
    return target


if __name__ == '__main__':
    build()
