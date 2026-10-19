"""Freeze unit-ribbon identity/order against reviewed art and exact enemy hashes."""
from pathlib import Path
import importlib.util
import json
import re
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class UnitRibbonCatalog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = json.loads((ROOT / 'docs/unit-ribbon-icons.json').read_text(encoding='utf8'))['items']
        cls.review = json.loads((ROOT / 'artwork/review-0.4.57-ribbons-v5/review-catalog.json').read_text(encoding='utf8'))['items']
        cls.entities = json.loads((ROOT / 'docs/integration-catalogs.json').read_text(encoding='utf8'))['entities']
        source = (ROOT / 'src/battle-hud.lua').read_text(encoding='utf8')
        cls.icons = {}
        for record in re.findall(r'\{id\s*=\s*\x27[^}]+\}', source):
            fields = dict(re.findall(r'(\w+)\s*=\s*\x27([^\x27]*)\x27', record))
            cls.icons[fields['id']] = fields

    def test_reviewed_group_order_fixes_ids_keys_and_units(self):
        self.assertEqual(len(self.rows), 24)
        expected = [r for r in self.review if r['group'] in ('巨型', '重型')]
        counts = {'巨型': 0, '重型': 0}
        for row, reviewed in zip(self.rows, expected):
            group = reviewed['group']; counts[group] += 1
            prefix = 'giant' if group == '巨型' else 'heavy'
            self.assertEqual(row['id'], ('G' if group == '巨型' else 'T') + f'{counts[group]:02}')
            self.assertEqual(row['key'], Path(reviewed['file']).stem.replace('-', '_'))
            self.assertTrue(row['key'].startswith(prefix + '_'))
            self.assertEqual((row['name'], row['unit'], row['condition']),
                             (reviewed['name'], reviewed['unit'], reviewed['condition']))
        self.assertEqual(counts, {'巨型': 6, '重型': 18})

    def test_all_twenty_nine_exact_hash_aliases_match_current_kill_roles(self):
        hashes = set()
        for row in self.rows:
            expected = {h for h, role in self.entities.items() if role.get('key') == row['enemy_key']
                        and role.get('kill') is True and role.get('asset') is not True}
            self.assertEqual(set(row['hashes']), expected)
            for value in row['hashes']:
                self.assertNotIn(value, hashes); hashes.add(value)
                self.assertRegex(value, r'^[0-9A-F]{16}$')
                role = self.entities[value]
                self.assertEqual((role['class'], role['name_zh'], role['faction']),
                                 (row['unit_class'], row['unit'], row['faction']))
            self.assertEqual({r['hash'] for r in row['bindings']}, expected)
        self.assertEqual(len(hashes), 29)

    def test_every_known_heavy_or_giant_body_has_a_specific_ribbon(self):
        expected = {role['key'] for role in self.entities.values()
                    if role.get('kill') is True and not role.get('asset')
                    and role.get('class') in ('重型', '巨型')}
        self.assertEqual({row['enemy_key'] for row in self.rows}, expected)
        impaler = next(row for row in self.rows if row['enemy_key'] == 'Impaler')
        self.assertEqual(set(impaler['hashes']), {'AE57FCDB49F74E98', 'DCF8E74212FBEE3B'})
        self.assertNotIn('672F7DA17F3BA34A', self.entities, 'a tentacle is not another full enemy')
        body = self.entities['DCF8E74212FBEE3B']
        self.assertEqual(body['resource_path'], 'content/fac_bugs/cha_impaler/cha_impaler')
        self.assertEqual(body['basis'], 'reviewed_full_enemy_body_resource')
        self.assertFalse(body['runtime_kill_flag'], 'retain the upstream discrepancy for review')

    def test_full_body_exception_requires_the_exact_pinned_sdk_identity(self):
        sys.path.insert(0, str(ROOT / 'tools'))
        spec = importlib.util.spec_from_file_location('ribbon_enemy_body_catalog', ROOT / 'tools/integration-catalogs.py')
        generator = importlib.util.module_from_spec(spec); spec.loader.exec_module(generator)
        original = generator.read_json
        def wrong_body(name):
            value = original(name)
            if name == 'sdk/EnemyAuthoringCapabilities.json':
                body = next(row for row in value['classes'] if row['semanticId'] == 'enemy/v1/terminids/impaler')
                body['identity']['path'] = 'content/fac_bugs/cha_impaler/cha_impaler_tentacle'
            return value
        with patch.object(generator, 'read_json', side_effect=wrong_body):
            with self.assertRaisesRegex(AssertionError, 'complete enemy body identity changed'):
                generator.catalogs()

    def test_production_icons_share_the_documented_identity_and_condition(self):
        self.assertEqual(len(self.icons), 52)
        for row in self.rows:
            icon = self.icons[row['id']]
            self.assertEqual((icon['key'], icon['unit_key'], icon['unit'], icon['condition']),
                             (row['key'], row['enemy_key'], row['unit'], row['condition']))
            self.assertEqual(icon['kind'], 'ribbon')
            self.assertTrue((ROOT / 'docs' / row['file']).resolve().is_file())

    def test_legacy_generic_awards_and_m12_keep_separate_stable_keys(self):
        self.assertEqual(self.icons['R02']['key'], 'heavy')
        self.assertEqual(self.icons['R03']['key'], 'giant')
        self.assertEqual(self.icons['M12']['key'], 'tyranny_speed_bump')
        self.assertEqual(self.icons['M12']['name'], '摧毁暴政减速带')
        self.assertEqual(len({row['key'] for row in self.rows}), 24)
        self.assertNotIn('heavy', {row['key'] for row in self.rows})
        self.assertNotIn('giant', {row['key'] for row in self.rows})


if __name__ == '__main__':
    unittest.main()
