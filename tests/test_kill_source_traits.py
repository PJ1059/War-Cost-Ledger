import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SourceTraitsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = json.loads((ROOT / 'docs/kill-source-traits.json').read_text(encoding='utf-8'))
        cls.rows = cls.document['source_types']

    def test_known_light_medium_heavy_native_defaults(self):
        self.assertEqual(self.rows['968211C0033DCE64']['armor_penetration_max'], 2)
        self.assertEqual(self.rows['A6A735ACCB4A327F']['armor_penetration_max'], 2)
        self.assertEqual(self.rows['11C27D3BABB38956']['armor_penetration_max'], 3)
        self.assertEqual(self.rows['A8CFFB316F0B5C5F']['armor_penetration_max'], 4)

    def test_explosion_ap_prevents_low_ap_primary_misclassification(self):
        by_name = {row['name']: row for row in self.rows.values()}
        for name in ('PLAS-1 Scorcher', 'SG-8P Punisher Plasma', 'PLAS-15 Loyalist'):
            self.assertEqual(by_name[name]['armor_penetration_max'], 3, name)

    def test_damaging_gas_sources_include_native_secondary_variants(self):
        for key in ('0416984F4922757B', '88F61AFFF48AC8A4', '0B882808C6F498E8',
                    'A9982969137F3D77', '05F3C83A91075766'):
            self.assertTrue(self.rows[key]['poison'], key)
        self.assertFalse(self.rows['968211C0033DCE64']['poison'])

    def test_fire_sources_include_g8_and_burning_lasers(self):
        for key in ('5C14F27759DD3BE0', '4FB0F8C02F55C82B', '27EE1ED8F6FB6356'):
            self.assertTrue(self.rows[key]['fire'])
        self.assertFalse(self.rows['A8CFFB316F0B5C5F']['fire'])
        self.assertFalse(self.rows['D54B9505C0F72873']['native_fire'], 'LAS98 beam kills alone do not prove burning deaths')
        for row in self.rows.values():
            if row['name'] == 'B/FLAM-80 Cremator':
                self.assertTrue(row['native_fire'])

    def test_delivery_and_shared_empty_pods_never_inherit_weapon_ap_or_elements(self):
        for key in ('E90F771A36FB441E', 'BBD57DF3E5B15ED8', '5CAF553BA7EA1429', '73F8498BFFDCF415', '31C4DD88C1450282'):
            row = self.rows.get(key, {})
            self.assertNotIn('armor_penetration_max', row, key)
            for field in ('fire', 'poison', 'native_fire', 'native_poison'):
                self.assertFalse(row.get(field, False), f'{key}:{field}')
        self.assertTrue(self.rows['39AB99895147A3BF']['native_fire'], 'the actual FLAM40 weapon remains a fire source')

    def test_catalog_is_reproducible_from_pinned_inputs(self):
        spec = importlib.util.spec_from_file_location('ledger_kill_source_traits', ROOT / 'tools/kill-source-traits.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.build(), self.document)


if __name__ == '__main__':
    unittest.main()
