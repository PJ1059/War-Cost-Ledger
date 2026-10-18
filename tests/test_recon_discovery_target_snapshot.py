"""Real descriptor/localization cross-check plus owned native row fixtures."""
from pathlib import Path
import importlib.util
import json
import os
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'tests')]
import test_recon_discovery_row_source_snapshot as prior
spec = importlib.util.spec_from_file_location('recon_target_snapshot', ROOT / 'tools/recon-discovery-target-snapshot.py')
tool = importlib.util.module_from_spec(spec); spec.loader.exec_module(tool)


class Memory(prior.Memory):
    def __init__(self, discoveries=1, key=0xDD55D46A, upper=16):
        super().__init__(discoveries)
        for i, raw in enumerate(self.composites.values()):
            if i >= discoveries: break
            struct.pack_into('<II', raw, tool.source.child.CHILD + 272 + 48, key, upper)


class TargetTests(unittest.TestCase):
    def snapshot(self, memory): return tool.snapshot(memory, memory.module, clock=lambda: 0)

    def test_saved_real_discovery_resolves_exact_locale_key(self):
        names = tool.locale_names()
        live = Path(os.environ.get('HD2_RESEARCH_FIXTURES_ROOT', str(ROOT/'dist')))/'recon-target-live-20261016-v1/rows.json'
        # Live artifacts remain outside the distributable source repository.
        # Use the frozen first real descriptor as the portable regression input.
        raw = bytes.fromhex('581a87920000000011771f34010000002ccea610100000000000000000000000817b23380a00000000000000000000002ea2661100000000')
        descriptor = tool.source.child.reader.descriptor(raw + bytes(344 - len(raw)) + bytes([2]))
        target = tool.target_info(descriptor, names)
        self.assertEqual(target['locale_key_hex'], '1166A22E')
        self.assertEqual(target['names']['en'], 'Light Nest')
        self.assertEqual(target['names']['zh'], '轻型巢穴')
        self.assertFalse(target['point_of_interest'])
        if live.is_file():
            row = json.loads(live.read_text('utf8'))['rows'][0]
            self.assertEqual(tool.target_info(row['descriptor'], names)['locale_key'], 0x1166A22E)

    def test_all_64_targets_inside_original_budget_no_tail_pointer_reads(self):
        memory = Memory(64); result = self.snapshot(memory)
        self.assertEqual(result['names_attempted'], 4)
        self.assertEqual(result['target_keys_parsed'], 64)
        self.assertEqual(sum('discovery_target' in r for r in result['rows']), 64)
        self.assertLessEqual(result['read_bytes'], 65536)
        self.assertLessEqual(result['read_calls'], 256)
        self.assertTrue(all(r['discovery_target']['point_of_interest'] for r in result['rows']))
        self.assertEqual(result['candidate_pointers_followed'], 0)
        self.assertNotIn(16 * 4294967296 + 0xDD55D46A, [at for at, _ in memory.reads])
        print('locale-key diagnostic worst case:', result['read_bytes'], 'bytes /', result['read_calls'], 'reads')

    def test_upper_tail_is_not_locale_identity(self):
        a = self.snapshot(Memory(key=0x1166A22E, upper=0))['rows'][0]['discovery_target']
        b = self.snapshot(Memory(key=0x1166A22E, upper=16))['rows'][0]['discovery_target']
        self.assertEqual(a['names'], b['names'])
        self.assertEqual(a['locale_key'], b['locale_key'])
        self.assertNotEqual(a['ignored_upper_u32'], b['ignored_upper_u32'])

    def test_unknown_key_stays_eligible_and_unfollowed(self):
        memory = Memory(key=0x12345678)
        row = self.snapshot(memory)['rows'][0]
        self.assertFalse(row['discovery_target']['point_of_interest'])
        self.assertIsNone(row['discovery_target']['names']['en'])
        self.assertTrue(row['discovery_source']['local_player'])
        self.assertNotIn(0x12345678, [at for at, _ in memory.reads])
        self.assertEqual(row['discovery_target']['candidate_pointers_followed'], 0)

    def test_non_type10_never_guesses_key(self):
        memory = Memory()
        struct.pack_into('<I', next(iter(memory.composites.values())), tool.source.child.CHILD + 272 + 36, 1)
        self.assertNotIn('discovery_target', self.snapshot(memory)['rows'][0])

    def test_three_poi_keys_exist_in_all_15_locales(self):
        folder = Path(os.environ.get('HD2_RESEARCH_FIXTURES_ROOT', str(ROOT/'dist')))/'mod-research/task-layout/full-ui-20261011/strings'
        locales = []
        for file in folder.glob('*.json'):
            values = {row['Key']: row['Value'] for row in json.loads(file.read_text('utf8')).get('Items', [])
                      if row['Key'] in tool.POI_KEYS}
            if values:
                self.assertEqual(set(values), tool.POI_KEYS)
                locales.append(values)
        self.assertEqual(len(locales), 15)
        self.assertEqual(tool.locale_names()['en'][0x01F261DE], 'Major Place of Interest')
        self.assertEqual(tool.locale_names()['en'][0xDD55D46A], 'Minor Place of Interest')


if __name__ == '__main__': unittest.main()
