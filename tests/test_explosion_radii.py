"""Independent SDK-derived radius policies; no game process or BFV code."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / 'tools' / 'explosion-radii.py'
SPEC = importlib.util.spec_from_file_location('ledger_explosion_radii', MODULE_PATH)
RADII = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RADII)


def explosion(name='throwable/example/detonation', outer=7, shockwave=8,
              demolition=30, legacy=None):
    return {'name': name, 'legacyName': legacy,
            'stats': {'outerRadius': outer, 'shockwaveRadius': shockwave,
                      'damage': {'demolition': demolition}}}


class ExplosionRadiiTests(unittest.TestCase):
    def build(self, *items):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'ExplosionCatalogue.json'
            raw = json.dumps({'build': 'TEST-BUILD', 'explosions': items}).encode('utf-8')
            path.write_bytes(raw)
            return RADII.build(directory), raw

    def test_candidate_uses_damage_outer_and_competitor_uses_shockwave(self):
        result, raw = self.build(explosion(legacy='Example weapon'))
        expected = {'radius': 8.5, 'conflict_radius': 9.5, 'eligible': True}
        self.assertEqual(result['by_name']['throwable/example/detonation'], expected)
        self.assertEqual(result['by_name']['Example weapon'], expected)
        self.assertEqual(result['source_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(result['source_build'], 'TEST-BUILD')

    def test_alias_collision_restricts_candidate_and_expands_conflict(self):
        result, _ = self.build(explosion(name='one', outer=20, shockwave=30, legacy='shared'),
                               explosion(name='two', outer=4, shockwave=50,
                                         demolition=0, legacy='shared'))
        self.assertEqual(result['by_name']['shared'],
                         {'radius': 5.5, 'conflict_radius': 46.5, 'eligible': False})
        self.assertTrue(result['by_name']['one']['eligible'])
        self.assertFalse(result['by_name']['two']['eligible'])

    def test_both_radii_are_capped_and_zero_demolition_cannot_award(self):
        result, _ = self.build(explosion(outer=100, shockwave=150, demolition=0))
        self.assertEqual(result['by_name']['throwable/example/detonation'],
                         {'radius': 46.5, 'conflict_radius': 46.5, 'eligible': False})

    def test_no_damage_link_is_not_a_demolition_candidate(self):
        item = explosion(name='throwable/smoke/detonation')
        item['stats']['damage'] = None
        result, _ = self.build(item)
        self.assertFalse(result['by_name'][item['name']]['eligible'])

    def test_invalid_numeric_radius_or_demolition_fails_generation(self):
        for invalid in [-1, float('nan'), float('inf'), True, '8']:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    self.build(explosion(outer=invalid))
                with self.assertRaises(ValueError):
                    self.build(explosion(shockwave=invalid))
                with self.assertRaises(ValueError):
                    self.build(explosion(demolition=invalid))


if __name__ == '__main__':
    unittest.main()
