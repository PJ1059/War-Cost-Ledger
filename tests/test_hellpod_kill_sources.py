"""Exact native falling bodies, variant boundaries and source-only labels."""
from pathlib import Path
import json
import os
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from hellpod_kill_sources import EXCLUDED, LABELS, REVIEWED, RUNTIME_DEFAULT, build_sources, reviewed_component


class HellpodSources(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = build_sources()
        sys.path.insert(0, str(RUNTIME_DEFAULT/'scripts'))
        from scan.tables import EntityTables
        cls.tables = EntityTables(Path(os.environ.get('HD2_DAMAGE_DATALIBRARY', 'external/datalibrary')))

    def test_exact_initial_reinforce_and_payload_bodies_rebuild(self):
        saved = json.loads((ROOT/'docs/hellpod-kill-sources.json').read_text(encoding='utf8'))
        self.assertEqual(self.data, saved)
        self.assertEqual(set(self.data['sources']), set(REVIEWED))
        self.assertEqual(self.data['source_count'], 3)
        for row in self.data['sources'].values():
            self.assertEqual(row['name_zh'], LABELS[row['variant_name']])
            self.assertEqual(row['kind'], 'hellpod')
            self.assertGreater(row['spawn_height'], 0)
            self.assertGreater(row['initial_velocity'], 0)

    def test_community_empty_label_is_actual_falling_payload_body(self):
        row = self.data['sources']['73F8498BFFDCF415']
        self.assertEqual(row['variant_name'], 'Payload')
        self.assertEqual(row['hellpod_variant'], 0)
        self.assertTrue(row['resource_path'].endswith('/hellpod_payload'))

    def test_racks_launchers_and_generic_base_are_not_sources(self):
        self.assertFalse(set(EXCLUDED).intersection(self.data['sources']))
        for resource in ('B52BEAAE4F85C391', '5052EC6A928CCF1A', '685337C9CCF0E45C'):
            with self.assertRaisesRegex(ValueError, 'no falling HellpodComponent'):
                reviewed_component(self.tables, resource, 0)

    def test_variant_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'gameplay variant differs'):
            reviewed_component(self.tables, 'E58163E71928D3E2', 0)

    def test_labels_do_not_assert_owner_damage_type_or_vehicle_awards(self):
        self.assertTrue(self.data['source_identity_required'])
        self.assertFalse(self.data['counts_as_vehicle_crush'])
        self.assertFalse(self.data['weapon_traits_inferred'])
        self.assertFalse(self.data['native_collision_mechanism_proven'])
        for row in self.data['sources'].values():
            self.assertNotIn('traits', row)
            self.assertNotIn('owner', row)


if __name__ == '__main__':
    unittest.main()
