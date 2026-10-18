"""Verify the installable archive and exercise the built entry inside HD2's LuaJIT."""
import ctypes as c
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile

from build import ROOT, RESOURCE, WORKBOOK, VERSION, resource_hash, workbook_rows, cents, lua_table


def lua_quote(text):
    return '"' + ''.join('\\%03d' % byte for byte in text.encode('utf8')) + '"'


def run_lua(test, *args):
    dll_path = Path(os.environ.get('HD2_LUA51_DLL',
                    r'G:\SteamLibrary\steamapps\common\Helldivers 2\bin\lua51.dll'))
    if not dll_path.is_file():
        raise FileNotFoundError('Set HD2_LUA51_DLL to the installed game lua51.dll path')
    dll = c.CDLL(str(dll_path))
    dll.luaL_newstate.restype = c.c_void_p
    dll.luaL_openlibs.argtypes = [c.c_void_p]
    dll.luaL_loadbuffer.argtypes = [c.c_void_p, c.c_char_p, c.c_size_t, c.c_char_p]
    dll.lua_pcall.argtypes = [c.c_void_p, c.c_int, c.c_int, c.c_int]
    dll.lua_tolstring.argtypes = [c.c_void_p, c.c_int, c.c_void_p]
    dll.lua_tolstring.restype = c.c_char_p
    dll.lua_close.argtypes = [c.c_void_p]
    runtime_root = Path(os.environ.get('HD2_RUNTIME_SOURCE',
        r'external/HD2Runtime'))
    script = '\n'.join([
        'local out = {}',
        'print = function(text) out[#out + 1] = tostring(text) end',
        # Older entry fixtures replace event/IO boundaries, but the current
        # addon also loads pure Runtime schema and byte-decoding modules.
        # Keep explicit fixture loaders/preloads first; this fallback performs
        # no Runtime boot, process access or native calls.
        'table.insert(package.loaders, function(name) '
        'if name:sub(1,11)=="hd2runtime/" then '
        'local f=loadfile(' + lua_quote(str(runtime_root.resolve()).replace('\\', '/'))
        + '.."/"..name:sub(12)..".lua"); if f then return f end end end)',
        # Legacy fixtures specify Chinese UI; dedicated locale fixtures override this input.
        'package.preload["hd2runtime/runtime/text_resources"] = function() return {language=function()return "cn"end} end',
        'arg = {' + ', '.join(lua_quote(str(Path(arg).resolve()).replace('\\', '/')) for arg in args) + '}',
        'dofile(' + lua_quote(str(test.resolve()).replace('\\', '/')) + ')',
        'return table.concat(out, "\\n")',
    ]).encode('utf8')
    state = dll.luaL_newstate()
    if not state:
        raise RuntimeError('Could not open LuaJIT state')
    try:
        dll.luaL_openlibs(state)
        status = dll.luaL_loadbuffer(state, script, len(script), b'=cost_ledger_test')
        if status == 0:
            status = dll.lua_pcall(state, 0, 1, 0)
        message = dll.lua_tolstring(state, -1, None)
        message = message.decode('utf8', errors='replace') if message else '<no result>'
    finally:
        dll.lua_close(state)
    if status:
        raise AssertionError(message)
    print(message)
    return str(dll_path)


def main(package_only=False):
    run_lua(ROOT / 'tests/test_career_kd.lua', ROOT / 'src/career-kd.lua')
    run_lua(ROOT / 'tests/test_career_award_records.lua', ROOT / 'src/career-award-records.lua')
    run_lua(ROOT / 'tests/test_mission_history.lua', ROOT / 'src/mission-history.lua')
    run_lua(ROOT / 'tests/test_career_history_summary.lua', ROOT / 'src/career-history-summary.lua')
    run_lua(ROOT / 'tests/test_career_panel_model.lua', ROOT / 'src/career-panel-model.lua', ROOT / 'src/battle-hud.lua')
    run_lua(ROOT / 'tests/test_career_page_sync.lua', ROOT / 'src/career-page-sync.lua', ROOT / 'src/career-kd.lua')
    for filename, expected in (
        ('ui-root-window-0.4.4.bin', 'c1ebdf76c73b00410bb0fd83cc2586b934bd54a7bae4ace189091981a81758e5'),
        ('ui-root-node-0.4.5.bin', '5306d56db507af8ce4ec8f5ba2fdeb029019eb8916fa4167e57f6703c1bc952f'),
    ):
        assert hashlib.sha256((ROOT / 'tests/fixtures' / filename).read_bytes()).hexdigest() == expected
    package = ROOT / 'dist' / ('HD2-War-Cost-Ledger-' + VERSION + '.zip')
    with ZipFile(package) as z:
        assert z.testzip() is None
        manifest = json.loads(z.read('manifest.json'))
        fx = json.loads(z.read('docs/currency-rates-2026-10-11.json'))
        assert fx == json.loads((ROOT / 'docs/currency-rates-2026-10-11.json').read_text(encoding='utf8'))
        assert set(fx['rates']) == {'MC', 'USD', 'CNY', 'EUR', 'GBP', 'SEK'}
        assert fx['mc_usd_rate'] == fx['rates']['MC'] == fx['rates']['USD'] == 1
        for code in ('CNY', 'EUR', 'GBP', 'SEK'):
            expected = float(fx['original_eur_rates'][code]) / float(fx['original_eur_rates']['USD'])
            assert abs(fx['rates'][code] - expected) < 1e-14
        assert manifest['Name'] == 'HD2 War Cost Ledger - ' + VERSION
        assert manifest['Options'][0]['Include'] == ['Addon']
        archive = z.read('Addon/9ba626afa44a3aa3.patch_0')
        gpu = z.read('Addon/9ba626afa44a3aa3.patch_0.gpu_resources')
        spec = importlib.util.spec_from_file_location('ledger_icons_test', ROOT / 'tools/prepare-game-icons.py')
        icon_tool = importlib.util.module_from_spec(spec); spec.loader.exec_module(icon_tool)
        sdk = icon_tool._sdk_module('hd2_archive')
        resources = sdk.read_archive(archive, gpu)
        image_manifest = json.loads(z.read('Source/GameIcons/manifest.json'))
        expected_resources = image_manifest['resource_count'] + 2  # main addon + native HUD Lua resources
        assert expected_resources == 125
        assert struct.unpack_from('<III', archive) == (0xF0000011, 3, expected_resources)
        assert len(resources) == expected_resources and len(gpu) >= 1267648
        resource, lua_gpu = resources[(sdk.LUA_TYPE, resource_hash(RESOURCE))]
        assert lua_gpu == b''
        assert image_manifest['revision'] == 'v18'
        image_ids = {item['id'] for item in image_manifest['images']}
        unit_ids = {f'G{i:02d}' for i in range(1, 7)} | {f'T{i:02d}' for i in range(1, 19)}
        assert set(icon_tool.INTEGRATION_ADDITIONS) == unit_ids | {'M12'}
        assert image_ids == (set(icon_tool.IDS) | set(icon_tool.EXTRA_IDS)
                             | set(icon_tool.COMBAT_ADDITIONS) | unit_ids | {'M12'})
        assert len(image_manifest['images']) == 53 and len(image_manifest['metrics']) == 4
        assert image_manifest['texture_family_count'] == 61 and image_manifest['resource_count'] == 123
        assert {'R11','R12','M07','M08','M09','M10','M11','M12'} <= image_ids
        integration = json.loads(z.read('Source/Artwork/integration-0.4.58/catalog.json'))
        assert integration == json.loads((icon_tool.INTEGRATED / 'catalog.json').read_bytes())
        assert image_manifest['integration_revision'] == integration['revision']
        assert z.read('docs/unit-ribbon-icons.json') == (ROOT / 'docs/unit-ribbon-icons.json').read_bytes()
        assert [item['id'] for item in image_manifest['indicators']] == ['I01', 'I02']
        assert image_manifest['frame']['image_id'] == 'ribbon_frame'
        for item in [*image_manifest['images'], *image_manifest['metrics'], *image_manifest['indicators']]:
            assert hashlib.sha256(z.read(item['package_source_file'])).hexdigest() == item['source_sha256']
        assert sdk.make_resource_archive(resources) == (archive, gpu)
        size, version = struct.unpack_from('<II', resource)
        source = resource[8:]
        assert version == 2 and size == len(source)
        assert source.startswith(('-- HD2-Addon: ' + RESOURCE + '\n').encode())
        assert source == z.read('Source/addon.lua') == (ROOT / 'dist/addon.lua').read_bytes()
        for module in ('mission-history', 'career-history-summary', 'career-panel-model', 'career-panel-feed', 'native-career-hud',
                       'grenade-reader', 'grenade-billing', 'kill-source-attribution',
                       'combat-source-totals', 'target-damage-attribution', 'damage-source-resolver', 'combat-records', 'native-death-reader', 'death-observer', 'combat-achievements', 'vehicle-kill-ribbons', 'kill-source-notices',
                       'career-combat-panel-model', 'career-search-input'):
            assert z.read('Source/' + module + '.lua') == (ROOT / 'src' / (module + '.lua')).read_bytes()
        native_resource = 'mods/hd2_costs/war_cost_native_hud'
        native_lua, native_gpu = resources[(sdk.LUA_TYPE, resource_hash(native_resource))]
        native_size, native_version = struct.unpack_from('<II', native_lua)
        native_source = native_lua[8:]
        assert native_gpu == b'' and native_version == 2 and native_size == len(native_source)
        assert native_source.startswith(f'local HD2_HUD_ADDON = "{native_resource}"\n'.encode())
        assert native_source == z.read('Source/native-hud-addon.lua') == (ROOT / 'dist/native-hud-addon.lua').read_bytes()
        for token in ('__CONFIRMED_PRICES__', '__NATIVE_STATS_MODULE__', '__STAT_PROBE_MODULE__',
                      '__FIRE_SOURCES__', '__ENEMY_TYPES__', '__SOURCE_NAMES__', '__KILL_OBSERVER_MODULE__',
                      '__BATTLE_HUD_MODULE__', '__GAME_ICONS__', '__GAME_HUD_MODULE__',
                      '__AWARD_NOTIFICATIONS_MODULE__', '__NATIVE_HUD_FEED_MODULE__',
                      '__HUD_LAYOUT_MODULE__', '__CHARGE_NOTIFICATIONS_MODULE__',
                      '__MAGAZINE_BILLING_MODULE__', '__CONSUMABLE_READER_MODULE__', '__GRENADE_READER_MODULE__',
                      '__GRENADE_BILLING_MODULE__', '__KILL_SOURCE_ATTRIBUTION_MODULE__', '__CAREER_KD_MODULE__', '__MISSION_HISTORY_MODULE__', '__CAREER_HISTORY_SUMMARY_MODULE__',
                      '__NATIVE_HIT_PROFILE__','__NATIVE_HIT_TRANSACTION__','__NATIVE_HIT_FEEDBACK_MODULE__',
                      '__NATIVE_HIT_CONNECTOR_MODULE__','__NATIVE_HIT_PACKAGE_MODULE__','__NATIVE_HIT_INSTALL_MODULE__',
                      '__NATIVE_HIT_SESSION_MODULE__', '__ENGINE_CFUNCTION_READER_MODULE__',
                      '__ENGINE_CFUNCTION_SOURCE_SHA__', '__COMBAT_ACHIEVEMENTS_MODULE__',
                      '__VEHICLE_KILL_RIBBONS_MODULE__', '__VEHICLE_BODY_SOURCES__', '__KILL_SOURCE_NOTICES_MODULE__',
                      '__RECON_CHAT_MODULE__', '__NATIVE_RECON_READER_MODULE__', '__KILL_SOURCE_TRAITS__', '__TARGET_DAMAGE_ATTRIBUTION_MODULE__', '__COMBAT_SOURCE_TOTALS_MODULE__',
                      '__DAMAGE_SOURCE_CATALOG__', '__DAMAGE_SOURCE_RESOLVER_MODULE__', '__STATUS_DAMAGE_CONTEXTS__'):
            assert token not in source.decode('utf8')
        assert z.read('Addon/9ba626afa44a3aa3.patch_0.stream') == b''
        hit_profile=json.loads(z.read('docs/native-hit-observer-package-v6.json'))
        living_profile=json.loads(z.read('docs/native-hit-living-target-profile-v1.json'))
        assert living_profile == json.loads((ROOT / 'docs/native-hit-living-target-profile-v1.json').read_text(encoding='utf8'))
        assert living_profile['revision']=='copy_pending_living_target_observer_v1'
        assert len(living_profile['entries'])==26 and len(living_profile['sites'])==8
        assert living_profile['living_target_filter']['commit_rechecks_life'] is False
        assert living_profile['count_contract']['target_alive_at_capture_required'] is True
        vehicle_profile=json.loads(z.read('docs/native-hit-vehicle-source-profile-v1.json'))
        assert vehicle_profile == json.loads((ROOT / 'docs/native-hit-vehicle-source-profile-v1.json').read_text(encoding='utf8'))
        assert vehicle_profile['vehicle_source_extension']['source_count_after']==94
        assert set(vehicle_profile['vehicle_source_extension']['sources'])=={
            '16474112801385B6','1FA1F596769225C2','439F9E65C18567DA'}
        assert vehicle_profile['living_target_filter']==living_profile['living_target_filter']
        damage_profile=json.loads(z.read('docs/native-hit-damage-id-profile-0.4.60.json'))
        assert damage_profile == json.loads((ROOT / 'docs/native-hit-damage-id-profile-0.4.60.json').read_text(encoding='utf8'))
        assert z.read('docs/native-hit-damage-id-profile-v1.json')==(ROOT/'docs/native-hit-damage-id-profile-v1.json').read_bytes()
        assert damage_profile['abi']==1 and damage_profile['record_bytes']==96
        assert damage_profile['projectile_id_extension']['record_offset']==32
        assert damage_profile['projectile_id_extension']['capture_flag']==2048
        assert damage_profile['projectile_id_extension']['new_hook_sites']==0
        assert z.read('docs/damage-source-catalog.json')==(ROOT/'docs/damage-source-catalog.json').read_bytes()
        hit_transaction=json.loads(z.read('docs/native-hit-patch-transaction-v6.json'))
        assert len(hit_profile['entries'])==19 and len(hit_profile['sites'])==7 and hit_transaction['abi']==3
        for module in ['native-hit-feedback','native-hit-connector','native-hit-package','native-hit-install','native-hit-session','native-hit-copy-link']:
            assert z.read('Source/'+module+'.lua')==(ROOT/'src'/(module+'.lua')).read_bytes()
        assert z.read('Source/engine-cfunction-reader.lua')==(ROOT/'src/engine-cfunction-reader.lua').read_bytes()
        assert z.read('docs/engine-cfunction-reader.md')==(ROOT/'docs/engine-cfunction-reader.md').read_bytes()
        assert all('wwise' not in name and 'boot' not in name for name in z.namelist())
        price = json.loads(z.read('Source/confirmed-prices.json'))
        assert price['calls'][0]['total_cents'] == 4200000
        assert price['calls'][0]['native_id'] == 458198946
        assert price['calls'][1]['total_cents'] == 3840000
        assert price['calls'][1]['native_id'] == 14345846
        assert price['m105_ammo']['unit_cents'] == 35
        assert len(set(price['m105_ammo']['source_types'])) == 4
        assert price['workbook_sha256'] == hashlib.sha256(WORKBOOK.read_bytes()).hexdigest()
        integration = json.loads(z.read('docs/integration-catalogs.json'))
        assert integration['calls'] == price['calls'] and integration['ammo'] == price['ammo']
        assert len(price['calls']) == len({p['native_id'] for p in price['calls']}) == 94
        assert len(price['ammo']) == len({p['id'] for p in price['ammo']}) == 81
        source_types = [t for p in price['ammo'] for t in p['source_types']]
        assert len(source_types) == len(set(source_types)) == 87
        assert all(re.fullmatch('[0-9A-F]{16}', t) for t in source_types)
        sheets = workbook_rows((2, 3, 4))
        for p in price['calls']:
            row = sheets[3][p['id']]
            assert p['name_zh'] == row['C'] and p['name_en'] == row['P']
            assert p['total_cents'] == cents(row['G']) == sum(p[k] for k in
                ('transport_cents', 'equipment_cents', 'prepaid_ammo_cents'))
            assert [p[k] for k in ('transport_cents', 'equipment_cents', 'prepaid_ammo_cents')] == [
                cents(row[k]) for k in ('D', 'E', 'F')]
            assert p['policy'] == row['L']
        for p in price['ammo']:
            row = sheets[2][p['id']]
            assert p['name_zh'] == row['C'] and p['name_en'] == row['P']
            assert p['unit_cents'] == cents(row['F'])
            assert row['G'] in ('消耗时计费', '场景拾取；消耗时计费')
            assert row['E'] in ('发', '次', '枚', '支') and p['projectiles_per_unit'] >= 1
        shell_prices = {p['id']: p for p in price['calls'] if 'shell_cents' in p}
        assert set(shell_prices) == {'ST-002', 'ST-004', 'ST-005', 'ST-008', 'ST-009', 'ST-011'}
        for p in shell_prices.values():
            assert p['shell_cents'] == cents(sheets[4][p['shell_price_id']]['D'])
            assert p['policy'] == '逐发计费' and re.fullmatch('[0-9A-F]{16}', p['payload'])
        assert len(integration['entities']) == 134
        assert sum(row.get('basis')=='exact_cloud_hash_and_runtime_enemy_type'
                   for row in integration['entities'].values())==36
        for value in ('32541FC4EC7C9CDC','9A8A3AAE287B230C','B2A6FA1E4284C7E6'):
            assert integration['entities'][value]['kill'] is True
        roster = json.loads((ROOT / 'docs/enemy-catalog/units.json').read_text(encoding='utf8'))['units']
        roles = {u['name_en']: u for u in roster}
        mapped_names = {p['key'] for p in integration['entities'].values()} & roles.keys()
        assert len(mapped_names) == 76
        reviewed_entities = [p for p in integration['entities'].values()
                             if p.get('basis') not in ('exact_cloud_hash_and_runtime_enemy_type',
                                                     'reviewed_exact_hash_runtime_unresolved_enemy')]
        assert len(reviewed_entities) == 84
        assert len({p['key'] for p in reviewed_entities} & roles.keys()) == 62
        for p in integration['entities'].values():
            if p['key'] in roles and p in reviewed_entities:
                role = roles[p['key']]
                assert p['name_zh'] == role['name_zh'] and p['class'] == role['display_class']
                assert p['air'] == ('飞行' in role['tags'])
        assert len(integration['unmapped_roster']) == 21
        assert integration['roster_sha256'] == hashlib.sha256(
            (ROOT / 'docs/enemy-catalog/units.json').read_bytes()).hexdigest()
        perf = json.loads(z.read('docs/kill-observer-performance.json'))
        assert perf['observer_sha256'] == hashlib.sha256(z.read('Source/kill-observer.lua')).hexdigest()
        assert perf['failed_reads'] == 0 and perf['actual_fps_verified'] is False
        original_copy = z.read('docs/绶带与成就-原文副本.md')
        catalog = json.loads(z.read('docs/achievement-catalog.json'))
        assert hashlib.sha256(original_copy).hexdigest() == catalog['source_sha256']
        original_path = Path(catalog['source'])
        if original_path.is_file() and original_path.read_bytes() != original_copy:
            print('NOTE: the external author document has later edits; this package preserves the reviewed 41-item source snapshot.')
        original_names = re.findall(r'^\*\*([^*]+)\*\*\s*$', original_copy.decode('utf8'), re.M)
        items = catalog['items']
        assert len(items) == 43 and len(original_names) == 41
        assert len(set(i['name'] for i in items)) == 43
        assert (set(original_names)-{'点燃'}|{'燃烧击杀','毒气击杀','摧毁暴政减速带'}) == {i['name'] for i in items}
        ready = [i for i in items if i['status'] == 'current_interfaces']
        pending = [i for i in items if i['status'] == 'requires_interface']
        assert len(ready) == catalog['ready_count'] == 22
        assert len(pending) == catalog['requires_interface_count'] == 21
        assert all(i['implementation_status'] == 'implemented_offline_verified' for i in ready)
        tank = next(item for item in ready if item['key'] == 'tyranny_speed_bump')
        assert tank['name'] == '摧毁暴政减速带' and tank['implementation_version'] == '0.4.58'
        assert '100' in tank['rule'] and '每局获得一次' in tank['rule'] and '阵亡不清零' in tank['rule']
        assert '排除炮、机枪、队友、旧历史派生' in tank['interface']
        for name in ('绶带与成就-原文副本.md', '绶带与成就-实现分类.md', 'achievement-catalog.json',
                     'integration-catalogs.json', 'enemy-hash-evidence.json', 'integration-0.4.0.md',
                     'kill-observer-performance.json'):
            assert z.read('docs/' + name) == (ROOT / 'docs' / name).read_bytes()
    print('PASS: manager manifest, discoverable resource identity, archive/envelope, ZIP integrity, exact workbook price.')
    print('PASS: exact workbook components, 94 calls / 81 ammo prices, six actual-shell prices, 134 target hashes / 76 named roster roles; original 62 classifications preserved.')
    print('PASS: original MD byte-for-byte preserved, 41 original items retained, user amendments yield 43 rules, 22 implemented / 21 pending; native-body100 once-per-match M12 contract and bundled docs match.')
    if package_only:
        return
    dll = run_lua(ROOT / 'tests/test_events.lua', ROOT / 'dist/addon.lua')
    run_lua(ROOT / 'tests/test_currency.lua', ROOT / 'src/currency.lua', ROOT / 'dist/currency-rates.lua',
            ROOT / 'src/battle-hud.lua')
    run_lua(ROOT / 'tests/test_hud.lua', ROOT / 'dist/addon.lua')
    run_lua(ROOT / 'tests/test_battle_hud.lua', ROOT / 'src/battle-hud.lua', ROOT / 'docs/ui-layout-samples.json')
    run_lua(ROOT / 'tests/test_award_notifications.lua', ROOT / 'src/award-notifications.lua')
    run_lua(ROOT / 'tests/test_charge_notifications.lua', ROOT / 'src/charge-notifications.lua')
    run_lua(ROOT / 'tests/test_hud_layout.lua', ROOT / 'src/hud-layout.lua')
    run_lua(ROOT / 'tests/test_feedback_positions.lua', ROOT / 'src/hud-layout.lua')
    run_lua(ROOT / 'tests/test_projectile_hit_stats.lua', ROOT / 'src/projectile-hit-stats.lua')
    run_lua(ROOT / 'tests/test_game_hud.lua', ROOT / 'src/game-hud.lua', ROOT / 'src/battle-hud.lua',
            ROOT / 'src/award-notifications.lua', ROOT / 'dist/game-icons.lua')
    run_lua(ROOT / 'tests/test_achievements.lua', ROOT / 'dist/addon.lua')
    runtime = Path(os.environ.get('HD2_RUNTIME_SOURCE',
        r'external/HD2Runtime'))
    run_lua(ROOT / 'tests/test_combat_achievements.lua', ROOT / 'src/combat-achievements.lua')
    run_lua(ROOT / 'tests/test_combat_source_totals.lua', ROOT / 'src/combat-source-totals.lua')
    run_lua(ROOT / 'tests/test_combat_pairs_062.lua', ROOT / 'src/combat-records.lua')
    run_lua(ROOT / 'tests/test_target_damage_attribution.lua', ROOT / 'src/target-damage-attribution.lua')
    run_lua(ROOT / 'tests/test_damage_source_resolver.lua', ROOT / 'src/damage-source-resolver.lua')
    run_lua(ROOT / 'tests/test_damage_source_full_ids_060.lua', ROOT / 'src/damage-source-resolver.lua', ROOT / 'src/target-damage-attribution.lua')
    run_lua(ROOT / 'tests/test_target_damage_observer.lua', ROOT / 'src/kill-observer.lua', runtime, ROOT / 'tests/test_integration.lua', ROOT / 'src/target-damage-attribution.lua', ROOT / 'src/damage-source-resolver.lua')
    run_lua(ROOT / 'tests/test_addon_repeat_achievements.lua', ROOT / 'dist/addon.lua', runtime,
            ROOT / 'tests/test_integration.lua')
    run_lua(ROOT / 'tests/test_vehicle_kill_ribbons.lua', ROOT / 'src/vehicle-kill-ribbons.lua')
    run_lua(ROOT / 'tests/test_addon_vehicle_kill_ribbons.lua', ROOT / 'dist/addon.lua', runtime,
            ROOT / 'tests/test_integration.lua')
    run_lua(ROOT / 'tests/test_kill_source_notices.lua', ROOT / 'src/kill-source-notices.lua')
    run_lua(ROOT / 'tests/test_recon_chat.lua', ROOT / 'src/recon-chat.lua')
    run_lua(ROOT / 'tests/test_native_recon_reader.lua', ROOT / 'src/native-recon-reader.lua',
            ROOT / 'src/recon-chat.lua')
    run_lua(ROOT / 'tests/test_addon_recon_chat.lua', ROOT / 'dist/addon.lua', runtime,
            ROOT / 'tests/test_integration.lua')
    run_lua(ROOT / 'tests/test_kill_observer.lua', ROOT / 'src/kill-observer.lua', runtime,
            ROOT / 'tests/test_integration.lua')
    run_lua(ROOT / 'tests/test_addon_kill_source_notices.lua', ROOT / 'dist/addon.lua', runtime,
            ROOT / 'tests/test_integration.lua')
    run_lua(ROOT / 'tests/test_addon_burst_sources_062.lua', ROOT / 'dist/addon.lua', runtime,
            ROOT / 'tests/test_integration.lua')
    run_lua(ROOT / 'tests/test_addon_hellpod_sources_062.lua', ROOT / 'dist/addon.lua', runtime,
            ROOT / 'tests/test_integration.lua', ROOT / 'tests/test_target_damage_observer.lua')
    run_lua(ROOT / 'tests/test_addon_bleed_window_063.lua', ROOT / 'dist/addon.lua', runtime,
            ROOT / 'tests/test_integration.lua', ROOT / 'tests/test_target_damage_observer.lua')
    run_lua(ROOT / 'tests/test_addon_spore_source_064.lua', ROOT / 'dist/addon.lua', runtime,
            ROOT / 'tests/test_integration.lua', ROOT / 'tests/test_target_damage_observer.lua')
    vehicle_spec = importlib.util.spec_from_file_location('test_vehicle_body_kill_sources', ROOT / 'tests/test_vehicle_body_kill_sources.py')
    vehicle_tests = importlib.util.module_from_spec(vehicle_spec)
    vehicle_spec.loader.exec_module(vehicle_tests)
    assert unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(vehicle_tests)).wasSuccessful()
    hellpod_spec = importlib.util.spec_from_file_location('test_hellpod_kill_sources', ROOT / 'tests/test_hellpod_kill_sources.py')
    hellpod_tests = importlib.util.module_from_spec(hellpod_spec)
    hellpod_spec.loader.exec_module(hellpod_tests)
    assert unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(hellpod_tests)).wasSuccessful()
    labels_spec = importlib.util.spec_from_file_location('test_resource_hash_labels', ROOT / 'tests/test_resource_hash_labels.py')
    labels_tests = importlib.util.module_from_spec(labels_spec)
    labels_spec.loader.exec_module(labels_tests)
    assert unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(labels_tests)).wasSuccessful()
    run_lua(ROOT / 'tests/test_demolition_attribution.lua', ROOT / 'src/demolition-attribution.lua')
    destruction_schema = Path(os.environ.get('HD2_EVENT_NATIVES_SOURCE', 'external/HD2Runtime-upstream/domains/event_natives.lua'))
    run_lua(ROOT / 'tests/test_demolition_world.lua', ROOT / 'src/demolition-world.lua', destruction_schema)
    run_lua(ROOT / 'tests/test_bughole_observer.lua', ROOT / 'src/bughole-observer.lua',
            ROOT / 'src/demolition-world.lua', destruction_schema)
    run_lua(ROOT / 'tests/test_bughole_dynamic_records.lua', ROOT / 'src/bughole-observer.lua',
            ROOT / 'src/demolition-world.lua', ROOT / 'tests/fixtures/bughole-dynamic-records-20261016.lua')
    run_lua(ROOT / 'tests/test_addon_demolition.lua', ROOT / 'dist/addon.lua', runtime,
            ROOT / 'tests/test_integration.lua')
    radii_spec = importlib.util.spec_from_file_location('test_explosion_radii', ROOT / 'tests/test_explosion_radii.py')
    radii_tests = importlib.util.module_from_spec(radii_spec)
    radii_spec.loader.exec_module(radii_tests)
    assert unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(radii_tests)).wasSuccessful()
    for module_name in ('test_bughole_descriptor_snapshot', 'test_recon_discovery_target_snapshot', 'test_billing_prices_052', 'test_kill_source_traits', 'test_damage_source_catalog', 'test_unit_ribbon_catalog', 'test_game_icon_assets'):
        diagnostic_spec = importlib.util.spec_from_file_location(module_name, ROOT / 'tests' / (module_name + '.py'))
        diagnostic_tests = importlib.util.module_from_spec(diagnostic_spec)
        diagnostic_spec.loader.exec_module(diagnostic_tests)
        assert unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(diagnostic_tests)).wasSuccessful()
    subprocess.run([sys.executable, '-X', 'utf8', '-B',
                    str(ROOT / 'tools/native/test_hit_copy_damage_id_054_owned.py'),
                    '--output', str(ROOT / 'dist' / ('damage-id-' + VERSION) / 'full-native-owned')], check=True)
    subprocess.run([sys.executable, '-X', 'utf8', '-B',
                    str(ROOT / 'tools/native/test_hit_copy_typed_ids_060_owned.py'),
                    '--output', str(ROOT / 'dist/damage-decode-0.4.60/full-native-owned')], check=True)
    with tempfile.TemporaryDirectory(prefix='hd2-living-link-test-') as name:
        profile_path = Path(name) / 'profile.lua'
        profile = json.loads((ROOT / 'docs/native-hit-living-target-profile-v1.json').read_text(encoding='utf8'))
        profile_path.write_text('return ' + lua_table(profile), encoding='utf8')
        run_lua(ROOT / 'tests/test_native_hit_living_target_link.lua', runtime, ROOT, profile_path)
    run_lua(ROOT / 'tests/test_combat_records.lua', ROOT / 'src/combat-records.lua')
    run_lua(ROOT / 'tests/test_death_observer.lua', ROOT / 'src/death-observer.lua')
    run_lua(ROOT / 'tests/test_native_death_reader.lua', ROOT / 'src/native-death-reader.lua', runtime)
    run_lua(ROOT / 'tests/test_addon_death_causes_061.lua', ROOT / 'dist/addon.lua', runtime, ROOT / 'tests/test_integration.lua')
    run_lua(ROOT / 'tests/test_career_search_input.lua', ROOT / 'src/career-search-input.lua')
    run_lua(ROOT / 'tests/test_career_combat_panel.lua', ROOT / 'src/career-panel-model.lua', ROOT / 'src/career-combat-panel-model.lua')
    run_lua(ROOT / 'tests/test_career_combat_feed.lua', ROOT)
    run_lua(ROOT / 'tests/test_career_dropdown.lua', ROOT)
    run_lua(ROOT / 'tests/test_career_guard_read.lua', ROOT / 'src/career-panel-feed.lua')
    run_lua(ROOT / 'tests/test_addon_career_awards.lua', ROOT / 'dist/addon.lua', runtime, ROOT / 'tests/test_integration.lua')
    run_lua(ROOT / 'tests/test_addon_mission_history.lua', ROOT / 'dist/addon.lua', runtime, ROOT / 'tests/test_integration.lua')
    run_lua(ROOT / 'tests/test_addon_career_billing.lua', ROOT / 'dist/addon.lua', runtime, ROOT / 'tests/test_integration.lua')
    run_lua(ROOT / 'tests/test_addon_target_sources.lua', ROOT / 'dist/addon.lua', runtime, ROOT / 'tests/test_integration.lua', ROOT / 'tests/test_target_damage_observer.lua')
    run_lua(ROOT / 'tests/test_addon_full_ids_060.lua', ROOT / 'dist/addon.lua', runtime, ROOT / 'tests/test_integration.lua', ROOT / 'tests/test_target_damage_observer.lua')
    run_lua(ROOT / 'tests/test_addon_continuous_damage_056.lua', ROOT / 'dist/addon.lua', runtime,
            ROOT / 'tests/test_integration.lua', ROOT / 'tests/test_target_damage_observer.lua')
    run_lua(ROOT / 'tests/test_addon_gas_status_057.lua', ROOT / 'dist/addon.lua', runtime,
            ROOT / 'tests/test_integration.lua', ROOT / 'tests/test_target_damage_observer.lua')
    run_lua(ROOT / 'tests/test_addon_damage_ids_054.lua', ROOT / 'dist/addon.lua', runtime,
            ROOT / 'tests/test_integration.lua', ROOT / 'tests/test_target_damage_observer.lua', ROOT / 'tests/test_addon_native_hit_copy.lua')
    run_lua(ROOT / 'tests/test_addon_projectile_ids_060.lua', ROOT / 'dist/addon.lua', runtime,
            ROOT / 'tests/test_integration.lua', ROOT / 'tests/test_target_damage_observer.lua',
            ROOT / 'tests/test_addon_native_hit_copy.lua', ROOT / 'tests/test_addon_damage_ids_054.lua')
    run_lua(ROOT / 'tests/test_addon_melee_source_055.lua', ROOT / 'dist/addon.lua', runtime,
            ROOT / 'tests/test_integration.lua', ROOT / 'tests/test_target_damage_observer.lua')
    run_lua(ROOT / 'tests/test_addon_damage_attribution.lua', ROOT / 'dist/addon.lua', runtime, ROOT / 'tests/test_integration.lua', ROOT / 'tests/test_target_damage_observer.lua')
    run_lua(ROOT / 'tests/test_addon_combat_records.lua', ROOT / 'dist/addon.lua', runtime, ROOT / 'tests/test_integration.lua')
    run_lua(ROOT / 'tests/test_addon_unknown_grouping.lua', ROOT / 'dist/addon.lua', runtime,
            ROOT / 'tests/test_integration.lua', ROOT)
    with tempfile.TemporaryDirectory(prefix='hd2-engine-exports-test-') as name:
        run_lua(ROOT / 'tests/test_addon_engine_inventory.lua', ROOT / 'dist/addon.lua', runtime, name)
    run_lua(ROOT / 'tests/test_native_career_reader.lua', ROOT / 'src/native-career-reader.lua', runtime,
            ROOT / 'tests/fixtures/career-visible-rows.lua')
    run_lua(ROOT / 'tests/test_addon_career_page.lua', ROOT / 'dist/addon.lua', runtime,
            ROOT / 'tests/test_native_career_reader.lua', ROOT / 'src/native-career-reader.lua',
            ROOT / 'tests/fixtures/career-visible-rows.lua')
    run_lua(ROOT / 'tests/test_addon_hits.lua', ROOT / 'dist/addon.lua', runtime)
    inventory = price['inventory_ammo']
    assert len(inventory) == 55 and sum(len(p['source_types']) for p in inventory) == 59
    assert len({h for p in inventory for h in p['source_types']}) == 59
    assert all(p['inventory_mode'] in ('magazine', 'fuel') for p in inventory)
    fuel = next(p for p in inventory if p['id'] == 'EQ-054')
    assert fuel['unit_cents'] == 30 and fuel['source_types'] == ['4FB0F8C02F55C82B']
    assert not {'P-4 Senator', 'SG-8 Punisher'} & {p['name_en'] for p in inventory}
    run_lua(ROOT / 'tests/test_consumable_billing.lua', ROOT / 'src/consumable-billing.lua')
    run_lua(ROOT / 'tests/test_magazine_billing.lua', ROOT / 'src/magazine-billing.lua')
    run_lua(ROOT / 'tests/test_magazine_billing_review.lua', ROOT / 'src/magazine-billing.lua')
    run_lua(ROOT / 'tests/test_consumable_reader.lua', ROOT / 'src/consumable-reader.lua', runtime)
    run_lua(ROOT / 'tests/test_backpack_fuel_reader.lua', ROOT / 'src/consumable-reader.lua', ROOT / 'tests/test_consumable_reader.lua', runtime, ROOT / 'src/magazine-billing.lua')
    run_lua(ROOT / 'tests/test_heatsink_reader.lua', ROOT / 'src/consumable-reader.lua', ROOT / 'tests/test_consumable_reader.lua', runtime, ROOT / 'src/magazine-billing.lua')
    run_lua(ROOT / 'tests/test_addon_billing_052.lua', ROOT / 'dist/addon.lua', ROOT / 'tests/test_consumable_reader.lua', runtime)
    assert len(price['grenades']) == 22 and len(price['deferred_grenades']) == 1
    assert next(p for p in price['grenades'] if p['id'] == 'EQ-127')['unit_cents'] == 18000
    assert price['deferred_grenades'][0]['id'] == 'EQ-126'
    run_lua(ROOT / 'tests/test_grenade_billing.lua', ROOT / 'src/grenade-billing.lua')
    run_lua(ROOT / 'tests/test_grenade_reader.lua', ROOT / 'src/grenade-reader.lua',
            ROOT / 'tests/test_consumable_reader.lua', runtime)
    run_lua(ROOT / 'tests/test_addon_grenades.lua', ROOT / 'dist/addon.lua',
            ROOT / 'tests/test_consumable_reader.lua', runtime)
    run_lua(ROOT / 'tests/test_kill_source_attribution.lua', ROOT / 'src/kill-source-attribution.lua')
    run_lua(ROOT / 'tests/test_addon_consumables.lua', ROOT / 'dist/addon.lua',
            ROOT / 'tests/test_consumable_reader.lua', runtime)
    run_lua(ROOT / 'tests/test_addon_consumables_review.lua', ROOT / 'dist/addon.lua',
            ROOT / 'tests/test_consumable_reader.lua', runtime)
    run_lua(ROOT / 'tests/test_integration.lua', ROOT / 'dist/addon.lua', runtime)
    run_lua(ROOT / 'tests/test_addon_unit_ribbons_058.lua', ROOT / 'dist/addon.lua', runtime,
            ROOT / 'tests/test_integration.lua')
    run_lua(ROOT / 'tests/test_native_stats.lua', ROOT / 'src/native-stats.lua', runtime)
    menu_api = Path(os.environ.get('HD2_MENU_API_SOURCE',
        r'external/VanillaPlusMegapack/components/ModOptionsMenu/src/api.lua'))
    run_lua(ROOT / 'tests/test_ui_settings.lua', ROOT / 'src/ui-settings.lua', menu_api)
    run_lua(ROOT/'tests/test_ui_settings_localization_065.lua', ROOT/'src/ui-settings.lua', menu_api.parent.parent)
    run_lua(ROOT/'tests/test_game_hud_localization_065.lua', ROOT/'src/game-hud.lua')
    run_lua(ROOT/'tests/test_localization_065.lua', ROOT/'src/localization.lua', ROOT/'dist/localization-en.lua')
    run_lua(ROOT/'tests/test_addon_localization_065.lua', ROOT/'dist/addon.lua', runtime, ROOT/'tests/test_integration.lua', menu_api.parent.parent)
    run_lua(ROOT/'tests/test_career_localization_065.lua', ROOT/'src/career-panel-model.lua', ROOT/'src/career-combat-panel-model.lua')
    run_lua(ROOT/'tests/test_native_career_word_wrap_065.lua', ROOT/'src/native-career-hud.lua')
    run_lua(ROOT / 'tests/test_addon_charge_notifications.lua', ROOT / 'dist/addon.lua', runtime, ROOT / 'tests/test_integration.lua')
    run_lua(ROOT / 'tests/test_addon_charge_discard_notifications.lua', ROOT / 'dist/addon.lua', ROOT / 'tests/test_consumable_reader.lua', runtime, ROOT / 'tests/test_addon_consumables.lua')
    run_lua(ROOT / 'tests/test_native_ui_bridge.lua', ROOT / 'src/native-ui-bridge.lua', runtime)
    run_lua(ROOT / 'tests/test_native_task_layout.lua', ROOT / 'src/native-task-layout.lua', runtime,
            ROOT / 'tests/fixtures/task-native-layout-0.4.7.json')
    hud_plus = Path(os.environ.get('HD2_HUD_PLUS_021_SOURCE', 'external/HD2-HUD-Plus-0.2.1/56E46A6DC1DF0A13.lua'))
    hud_plus_024 = Path(os.environ.get('HD2_HUD_PLUS_024_SOURCE', 'external/HD2-HUD-Plus-0.2.4/56E46A6DC1DF0A13.lua'))
    for host in (hud_plus, hud_plus_024):
        run_lua(ROOT / 'tests/test_native_hud_addon.lua', ROOT / 'src/native-hud-addon.lua', host,
                ROOT / 'dist/native-game-art.lua')
        run_lua(ROOT / 'tests/test_native_career_hud.lua',
                ROOT / 'src/native-hud-addon.lua', ROOT / 'src/native-career-hud.lua', host,
                ROOT / 'dist/native-game-art.lua', ROOT / 'tests/test_native_career_panel_reader.lua',
                ROOT / 'src/native-career-panel-reader.lua', runtime,
                ROOT / 'tests/fixtures/career-parent-headers.lua', ROOT / 'src/career-panel-model.lua',
                ROOT / 'src/battle-hud.lua', ROOT / 'tests/test_native_hud_addon.lua')
    run_lua(ROOT / 'tests/test_projectile_hit_stats_review.lua', ROOT / 'src/projectile-hit-stats.lua',
            ROOT / 'src/battle-hud.lua', ROOT / 'src/award-notifications.lua',
            ROOT / 'src/native-hud-addon.lua', ROOT / 'dist/native-game-art.lua')
    run_lua(ROOT / 'tests/test_native_hud_feed.lua', ROOT / 'src/native-hud-feed.lua',
            ROOT / 'src/game-hud.lua', ROOT / 'src/battle-hud.lua',
            ROOT / 'src/award-notifications.lua', ROOT / 'dist/game-icons.lua')
    run_lua(ROOT / 'tests/test_ui_layout_capture.lua', ROOT / 'src/ui-layout-capture.lua',
            ROOT / 'src/native-ui-bridge.lua', runtime)
    run_lua(ROOT / 'tests/test_addon_options.lua', ROOT / 'dist/addon.lua', runtime)
    run_lua(ROOT / 'tests/test_addon_plugin_frame_probe.lua', ROOT / 'dist/addon.lua', runtime)
    run_lua(ROOT / 'tests/test_ui_tree_probe.lua', ROOT / 'src/ui-tree-probe.lua',
            ROOT / 'src/native-ui-bridge.lua', runtime)
    # The whole-HUD automatic path retired after the successful full capture.
    # Its standalone reader regression above remains; exercise the replacement
    # automatic path against the actual built addon instead.
    run_lua(ROOT / 'tests/test_task_layout_code_probe.lua', ROOT / 'src/task-layout-code-probe.lua', runtime,
            ROOT / 'tests/fixtures/task-layout-caller-pins-0.4.7.json')
    run_lua(ROOT / 'tests/test_addon_task_layout_code.lua', ROOT / 'dist/addon.lua', runtime,
            ROOT / 'tests/fixtures/task-layout-caller-pins-0.4.7.json')
    run_lua(ROOT / 'tests/test_addon_task_layout.lua', ROOT / 'dist/addon.lua', runtime,
            ROOT / 'tests/fixtures/addon-task-layout-0.4.8.json')
    run_lua(ROOT / 'tests/test_native_hit_reader.lua', ROOT / 'src/native-hit-reader.lua', runtime)
    run_lua(ROOT / 'tests/test_native_status_reader.lua', ROOT / 'src/native-status-reader.lua', runtime)
    with tempfile.TemporaryDirectory(prefix='hd2-stat-probe-test-') as name:
        temp = Path(name)
        (temp / 'HD2Runtime/mod_data').mkdir(parents=True)
        run_lua(ROOT / 'tests/test_stat_probe.lua', ROOT / 'src/stat-probe.lua', runtime, temp)
    report = {
        'version': VERSION, 'status': 'offline_passed', 'game_verified': False, 'lua_dll': dll,
        'package_sha256': hashlib.sha256(package.read_bytes()).hexdigest(),
        'workbook_sha256': price['workbook_sha256'], 'm105_call_mc': 38400, 'm105_round_mc': 0.35,
        'stats_scope': 'local_player', 'test_example_mc': 38487.5,
        'fire_source_types': len(json.loads((ROOT / 'docs/fire-sources.json').read_text(encoding='utf8'))['source_types']),
        'gameplay_observation_hz': 10, 'store_checkpoint_seconds': 5,
        'currencies': {'codes': list(fx['rates']), 'mc_usd_rate': 1, 'as_of': fx['as_of'],
                       'requested_date': fx['requested_date'], 'offline_snapshot': True,
                       'accounting_unit': 'integer_MC_cents', 'live_pixels_verified': False},
        'probe_default_enabled': False, 'actual_fps_verified': False,
        'pricing': {'call_prices': 94, 'ammunition_prices': 81, 'ammo_source_types': 87,
                    'actual_shell_barrages': 6, 'shell_count_tests': 'passed', 'call_scope': 'solo_host',
                    'discarded_magazines_covered': '53_proven_clip_weapons_continuous_local_held_inventory',
                    'torcher_fuel_covered': True, 'torcher_fuel_unit_mc': 0.30,
                    'inventory_authority_no_shots_double_billing': True,
                    'inventory_prices': 55, 'inventory_source_types': 59, 'heatsink_prices': 8, 'heatsink_source_types': 10,
                    'consumable_read_max_operations': 64, 'ordinary_consumable_read_max_operations': 48,
                    'consumable_read_max_bytes': 4096,
                    'consumable_read_soft_budget_ms': 1, 'consumable_game_verified': False,
                    'pelican_trips_covered': False},
        'achievements': {'implemented': 21, 'requires_interface': 21, 'threshold_tests': 'passed',
                         'local_health_reads_per_600_frames_at_60fps': 100,
                         'enemy_health_observer_enabled': True, 'runtime_per_frame_health_events_enabled': False,
                         'enemy_observation_hz': 10, 'enemy_polls_per_600_frames_at_60fps': 100,
                         'max_new_descriptors_per_poll': 64, 'max_live_records': 4096,
                         'observer_budget_checkpoint_ms': 2, 'mapped_enemy_asset_hashes': 134,
                         'mapped_roster_names': 76, 'original_classified_roster_names': 62,
                         'original_unmapped_roster_names': 21,
                         'live_new_readers_verified': False},
        'hud': {'mission_only': True, 'toggle_key': 'F8', 'saved_preference': True,
                'native_parent_offset': '0x2944A0', 'native_size': [336, 106], 'earned_medals_max': 10,
                'flat_combat_excluded_at_five_resolutions': True, 'live_pixels_verified': False},
        'native_battle_hud_preparation': {'icons': 20, 'artwork': 'placeholders', 'native_binding': False,
                'native_map_open_interface_verified': False, 'native_objective_node_verified': False,
                'layout_tests': 'passed', 'cached_read_only_feed': True, 'added_game_memory_reads': 0,
                'map_ribbons': 12, 'mission_medals': 6, 'current_mission_only': True,
                'reference_native_width': 336, 'closed_task_offset': 60, 'open_full_task_offset': 118,
                'installed': False},
        'game_icon_hud': {'artwork': 'v17_icon_masks', 'icon_families': 18, 'ribbon_frames': 1,
                'resource_count': len(resources), 'gpu_bytes': len(gpu), 'draw_game_memory_reads': 0,
                'native_binding': True, 'public_host': 'HD2 HUD+ 0.2.1',
                'native_widgets_contract': 'passed with real installed host and simulated native IO',
                'same_native_parent': True, 'native_text_font': [2, 1, 1],
                'curvature_path': 'game mask_material with dynamically refreshed c2',
                'cached_combat_feed': True, 'source_widget_and_compiled_resource_tests': 'passed',
                'map_poll_reads': 4, 'map_poll_bytes': 11, 'map_poll_hz': 10,
                'side_notifications': True, 'same_type_merge': True, 'shared_idle_seconds': 2,
                'late_join_no_replay': True, 'toggle_key': 'F8', 'collection_toggle_key': 'F9',
                'native_map_open_interface_verified': True, 'native_objective_node_verified': True,
                'hover_details_implemented': False, 'synthetic_drawing_tests': 'passed',
                'native_feedback_readers_verified': False, 'live_pixels_verified': False,
                'actual_fps_verified': False, 'installed': False},
        'in_game_options': {'public_api': 'ModOptionsMenu api 1/version 3', 'controls': 17,
                'chinese_labels': True, 'f8_sync': True, 'applied_only': True,
                'preview_seconds': 8, 'preview_isolated': True, 'native_menu_game_verified': False,
                'task_move_implemented': True, 'task_settings_saved_only': False},
        'ui_capture': {'default_enabled': False, 'explicit_manual_request': True,
                'start_delay_seconds': 5, 'state_wait_timeout_seconds': 30,
                'read_bytes_per_step_max': 65536, 'poll_hz': 10, 'binary_bytes_per_sample': 4882432,
                'complete_requires_stable_identity': True, 'atomic': False, 'live_sample_verified': True,
                'live_sample_binary_sha256': 'ee338b1688205b060d545a99659a36005fb3c9d370f52314df3acef92eab9648'},
        'automatic_ui_probe': {'default_enabled': False, 'retired_from_addon': True, 'poll_hz': 10,
                'source_revision': 'root_base_v3',
                'real_root_node_regression': 'passed', 'real_root_fixture_sha256':
                '5306d56db507af8ce4ec8f5ba2fdeb029019eb8916fa4167e57f6703c1bc952f',
                'root_kind': 0, 'previous_v1_v2_evidence_preserved': True,
                'real_code_window_regression': 'passed', 'real_fixture_sha256':
                'c1ebdf76c73b00410bb0fd83cc2586b934bd54a7bae4ace189091981a81758e5',
                'total_ui_read_bytes_per_step_max': 16384, 'bridge_bytes_reserved': 11,
                'tree_nodes_per_step_max': 16, 'operations_per_step_max': 32,
                'soft_checkpoint_ms': 2, 'atomic_io_can_exceed_checkpoint': True,
                'start_tick_tree_reads': 0, 'phase_changes_yield': True,
                'wait_for_mission_ready': True, 'startup_timeout_seconds': None,
                'map_modes': 2, 'successful_samples_per_mode': 1, 'attempts_per_mode_max': 3,
                'nodes_per_sample_max': 1024, 'depth_max': 24,
                'manual_capture_priority': True, 'completed_probe_extra_native_reads': 0,
                'atomic': False, 'task_move_implemented': False,
                'synthetic_tests': 'passed', 'live_sample_verified': False, 'actual_fps_verified': False},
        'task_layout_code_probe': {'default_enabled': True, 'source_revision': 'task_layout_code_v1',
                'read_bytes_per_step_max': 4096, 'binary_bytes_per_sample': 14336, 'poll_hz': 10,
                'complete_outputs_per_build': 1, 'real_failures_max': 2, 'requires_mission': False,
                'requires_map_open': False, 'manual_capture_priority': True, 'native_calls': 0,
                'game_writes': 0, 'whole_hud_scans': 0, 'completed_extra_native_reads': 0,
                'real_caller_pins_regression': 'passed', 'built_addon_integration': 'passed',
                'live_sample_verified': True, 'live_binary_sha256': '690bd873297e1330195b97facf6441fe7804845cc6119ed55f72779ad0129c0b',
                'task_move_implemented': False, 'actual_fps_verified': False},
        'native_task_layout': {'implemented': True, 'source': 'real current-build HUD/layout/code captures',
                'list_offset': '0x29B180', 'focused_offset': '0x38CA10', 'layout_offset': '0x392328',
                'gap_offset': '0x2C', 'native_place_rva': '0x18F5C70', 'poll_hz': 10,
                'read_bytes_per_normal_step_max': 3042, 'pickup_read_bytes_max': 772,
                'calls_per_changed_step_max': 1,
                'source_geometry_no_animation_drift': True, 'foreign_gap_yields': True,
                'float32_pixel_tolerance': 0.01, 'exact_original_gap_restore': True,
                'draw_game_io': 0, 'real_fixture_boundary_tests': 'passed',
                'built_addon_integration': 'passed',
                'native_local_reservation': True, 'requires_flat_viewport': False,
                'previous_0_4_8_live_task_down_and_f8_restore_user_confirmed': True,
                'installed': False, 'live_pixels_verified': False, 'actual_fps_verified': False},
    }
    (ROOT / 'dist/verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    print('Game LuaJIT verification passed. Live game observation is still pending.')


if __name__ == '__main__':
    if sys.argv[1:] == ['--package-only']:
        main(package_only=True)
    elif sys.argv[1:] == ['--feedback-only']:
        run_lua(ROOT / 'tests/test_hit_feedback.lua', ROOT / 'src/hit-feedback.lua')
        run_lua(ROOT / 'tests/test_status_feedback.lua', ROOT / 'src/status-feedback.lua', ROOT / 'src/battle-hud.lua')
        run_lua(ROOT / 'tests/test_battle_hud.lua', ROOT / 'src/battle-hud.lua', ROOT / 'docs/ui-layout-samples.json')
        print('Offline synthetic feedback and layout passed. No game reader or installation was changed.')
    else:
        main()
