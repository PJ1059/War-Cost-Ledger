"""Ground-fire inventory and built-addon regression for the pinned 0.4.66 scope.

Run directly with Python. The generator check is read-only; the Lua replay uses
owned memory fixtures and never opens the game process or calls a native API.
"""
from __future__ import annotations

from collections import Counter
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from build import VERSION, lua_table
from test import run_lua

CONFIG = ROOT / 'docs/ground-fire-contexts-0.4.66.json'
GENERATOR = ROOT / 'tools/ground-fire-contexts.py'
RUNTIME = Path(os.environ.get('HD2_RUNTIME_SOURCE',
    r'external/HD2Runtime'))

# These are this release's reviewed native event identities, not guesses based
# on a weapon name containing "fire" or a shared FireTemplate number.
EXPECTED = {
    'stratagem/eagle_napalm_airstrike/payload_impact': (359, '27BB558C893383CC', 10, 5),
    'stratagem/mdi4_incendiary_mines/mine': (72, 'BF32E12923A9A252', 4, 5),
    'stratagem/orbital_napalm_barrage/shell_impact': (63, 'A16AB4FF66AE6970', 10, 5),
    'stratagem/orbital_napalm_barrage/shell_impact_2': (74, 'A16AB4FF66AE6970', 10, 5),
    'support_weapon/eat700_expendable_napalm/impact': (316, 'B2B5E0D185605F9E', 8, 5),
    'support_weapon/eat700_expendable_napalm/impact/shrapnel_impact': (26, 'B2B5E0D185605F9E', 5, 5),
    'throwable/g10_incendiary/detonation': (224, '04653AB33F3FFB44', 7, 20),
    'throwable/g13_incendiary_impact/detonation': (69, 'EB725C39FC38B87C', 7, 15),
    'throwable/g142_pyrotech/detonation': (409, '03F31CAF3A7D8F4E', 5, 6),
    'throwable/g40k_melta_mine/detonation': (368, 'EE4C107B941AB7F4', 6, 5),
    'throwable/g8_immolation/detonation': (32, '5C14F27759DD3BE0', 10, 27),
}


def load_generator():
    spec = importlib.util.spec_from_file_location('ground_fire_066', GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GroundFireCatalogue066(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = json.loads(CONFIG.read_text(encoding='utf8'))
        cls.generator = load_generator()
        damage = cls.generator.load_module()
        cls.folder = damage.discover_datalibrary(RUNTIME, None)
        sys.path.insert(0, str(RUNTIME / 'scripts'))
        from scan.tables import EntityTables, decode
        from scan.settings import SettingsView
        cls.tables = EntityTables(cls.folder)
        cls.settings = SettingsView(cls.tables)
        cls.decode = staticmethod(decode)

    def test_generator_is_reproducible(self):
        result = subprocess.run([sys.executable, '-X', 'utf8', '-B', str(GENERATOR), '--check'],
                                cwd=ROOT, capture_output=True, text=True, encoding='utf8')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('"status": "PASS"', result.stdout)

    def test_every_positive_native_template_is_inventoried(self):
        expected = {}
        for kind, template_offset, damage_offset in [('explosion', '96', '4'), ('projectile', '236', '60')]:
            for record_index, native_id, _ in self.settings.table(kind).rows:
                row = self.settings.decode(kind, native_id)
                if row[template_offset] > 0:
                    expected[f'{kind}:{native_id}'] = (record_index, row[template_offset], row[damage_offset])
        rows = self.document['catalogue']
        actual = {row['node']: (row['record_index'], row['fire_template'], row['damage_info_id']) for row in rows}
        self.assertEqual(len(actual), len(rows), 'duplicate native nodes are not extra coverage')
        self.assertEqual(actual, expected, 'no FireTemplate > 0 native row may silently disappear')
        self.assertEqual(Counter(row['kind'] for row in rows), {'explosion': 28, 'projectile': 4})
        self.assertEqual(Counter(row['fire_template'] for row in rows), {1: 1, 2: 5, 3: 10, 4: 14, 5: 2})
        for row in rows:
            if row['fire_template'] == 5:
                self.assertFalse(row['automatic_context'], 'Count is not an enabled fire template')
                self.assertIn('UNREVIEWED_FIRE_TEMPLATE_VALUE', row['blocked_reasons'])
            if row['kind'] == 'projectile':
                self.assertFalse(row['automatic_context'], 'a configured projectile has no observed area position')

    def test_all_configured_component_templates_are_inventoried_without_fake_areas(self):
        expected = {}
        for name in self.tables.component_names():
            component = self.tables.component(name)
            for member in component.members():
                if member.type_name != 'FireTemplate':
                    continue
                for index, owners in component.owner_map().items():
                    value = self.decode(member, component.raw(index))
                    if isinstance(value, int) and value > 0:
                        expected[(name, member.offset, index)] = (value, {f'{owner:016X}' for owner in owners})
        rows = self.document['configured_component_templates']
        actual = {(row['component'], row['field_offset'], row['record_index']):
                  (row['fire_template'], {owner['source_type'] for owner in row['owners']}) for row in rows}
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), len(rows))
        self.assertEqual(len(rows), 22)
        self.assertTrue(all(not row['automatic_context'] for row in rows))
        self.assertTrue(any('fac_bugs/' in owner.get('resource_path', '') or
                            'fac_illuminate/' in owner.get('resource_path', '')
                            for row in rows for owner in row['owners']),
                        'enemy defaults remain visible in the inventory but cannot become player areas')

    def test_enabled_events_have_precise_identity_and_independent_windows(self):
        entries = self.document['entries']
        self.assertEqual(set(entries), set(EXPECTED))
        by_id = {row['native_id']: row for row in self.document['catalogue'] if row['kind'] == 'explosion'}
        names = json.loads((ROOT / 'docs/integration-catalogs.json').read_text(encoding='utf8'))['stat_sources']
        documented, conservative = 0, 0
        for name, entry in entries.items():
            native_id, source, radius, duration = EXPECTED[name]
            with self.subTest(event=name):
                self.assertEqual((entry['explosion_id'], entry['source_type'], entry['radius'],
                                  entry['status_duration']), (native_id, source, radius, duration))
                row = by_id[native_id]
                self.assertTrue(row['automatic_context'])
                self.assertEqual(row['blocked_reasons'], [])
                self.assertIn(name, row['event_names'])
                self.assertEqual(entry['damage_info_id'], row['damage_info_id'])
                self.assertEqual(entry['radius'], row['native_radii']['outer'])
                self.assertIn(entry['fire_template'], (1, 2, 3, 4))
                self.assertEqual(entry['status'], 'fire')
                self.assertTrue(0 < entry['status_duration'] <= 30)
                self.assertIn(source, names)
                self.assertNotIn(names[source]['kind'], ('enemy', 'environment'))
                if entry['window_policy'] == 'documented_area_duration_heuristic':
                    documented += 1
                    self.assertFalse(row['area_duration']['verified_native_lifetime'])
                    self.assertEqual(row['area_duration']['seconds'], duration)
                else:
                    conservative += 1
                    self.assertEqual(entry['window_policy'], 'conservative_area_window')
                    self.assertEqual(entry['conservative_area_window'], 5)
                    self.assertEqual(duration, 5, 'rule windows cannot be passed off as a proven pool lifetime')
                if entry.get('required_event_types'):
                    self.assertEqual(entry['source_scope'], 'exact_event_constrained_named_family')
                    self.assertEqual(set(entry['required_event_types']), {'BF32E12923A9A252', 'E49A5AE078AAD407'})
                    self.assertEqual(set(entry['required_event_types']),
                                     {owner['source_type'] for owner in row['direct_resource_owners']})
                    self.assertTrue(row['native_origin_status']['shared'])
                    self.assertTrue(row['native_origin_status']['unresolved'])
                else:
                    self.assertEqual([source], [item['source_type'] for item in row['sources']])
                    self.assertFalse(row['native_origin_status']['shared'])
                    self.assertFalse(row['native_origin_status']['unresolved'])
        self.assertEqual((documented, conservative), (4, 7))
        self.assertEqual(len({entry['source_type'] for entry in entries.values()}), 9)
        self.assertTrue(all(not row['automatic_context']
                            for row in self.document['fire_status_without_ground_template_chain']))
        self.assertFalse(any('laser' in name for name in entries), 'victim ignition alone is not a ground area')

    def test_all_enabled_events_through_real_built_callback(self):
        with tempfile.TemporaryDirectory(prefix='ledger_ground_fire_066_') as folder:
            config_lua = Path(folder) / 'contexts.lua'
            cases = [dict(name=name, **entry) for name, entry in sorted(self.document['entries'].items())]
            config_lua.write_text('return ' + lua_table(cases) + '\n', encoding='utf8')
            with ZipFile(ROOT / f'dist/HD2-War-Cost-Ledger-{VERSION}.zip') as package:
                self.assertEqual(package.read('docs/ground-fire-contexts-0.4.66.json'), CONFIG.read_bytes())
                resolver_source = package.read('Source/damage-source-resolver.lua')
                self.assertEqual(resolver_source, (ROOT / 'src/damage-source-resolver.lua').read_bytes())
                self.assertEqual(package.read('Source/addon.lua'), (ROOT / 'dist/addon.lua').read_bytes())
            resolver_lua = Path(folder) / 'packaged-damage-source-resolver.lua'
            resolver_lua.write_bytes(resolver_source)
            run_lua(ROOT / 'tests/test_addon_ground_fire_catalog_066.lua', ROOT / 'dist/addon.lua',
                    RUNTIME, ROOT / 'tests/test_integration.lua', ROOT / 'tests/test_target_damage_observer.lua',
                    config_lua, resolver_lua)


if __name__ == '__main__':
    unittest.main()
