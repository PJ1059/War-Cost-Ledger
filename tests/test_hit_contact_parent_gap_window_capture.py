"""One tiny owned fresh-parent/gap fixture; no Game or additional matrix."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import test_hit_contact_parent_fragment_capture as fixture

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('owned_parent_gap168', ROOT / 'tools/hit-contact-parent-gap-window-capture.py')
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)
EXPECTED = (capture.SOURCE / 'parent104.bin').read_bytes()


class Memory(fixture.Memory):
    def __init__(self, changed_parent=False):
        super().__init__()
        self.changed_parent, self.gap_reads = changed_parent, 0

    def query(self, address):
        if address == self.game + capture.GAP_RVA:
            self.queries.append(address)
            return {'base': self.game, 'size': fixture.fixture.fixture.locator.IMAGE_SIZE,
                    'state': 0x1000, 'type': 0x1000000, 'protect': 0x20}
        return super().query(address)

    def read(self, address, n):
        if address == self.game + fixture.capture.PARENT_RVA:
            assert n == 104
            self.reads.append((address, n))
            self.parent_reads += 1
            return bytes(n) if self.changed_parent else EXPECTED
        if address == self.game + capture.GAP_RVA:
            assert n == 168
            self.reads.append((address, n))
            self.gap_reads += 1
            return b'\x90' * 168
        return super().read(address, n)


class Scenario(fixture.Scenario):
    def __init__(self, **options):
        super().__init__()
        self.memory = Memory(**options)


class ParentGapSmokeTests(unittest.TestCase):
    def test_fresh_exact104_allows_one_gap_changed104_blocks_it(self):
        with tempfile.TemporaryDirectory() as parent:
            scenario = Scenario()
            result = capture.run(Path(parent) / 'normal', scenario.dependencies(), clock=fixture.fixture.fixture.fixture.Clock())
            m = json.loads(Path(result['json_path']).read_text('utf8'))
            self.assertEqual(len(Path(result['binary_path']).read_bytes()), 168)
            self.assertEqual(m['budget']['read_calls'], 16)
            self.assertEqual(m['budget']['query_calls'], 16)
            self.assertEqual(m['budget']['bytes_requested'], 8702)
            self.assertEqual((scenario.memory.parent_reads, scenario.memory.gap_reads), (1, 1))
            self.assertTrue(m['fresh_parent104_exact'])
            self.assertFalse(m['declared_code_complete'])
            self.assertFalse(m['logical_function_complete'])
            self.assertEqual(m['state_before'], m['state_after'])
            self.assertFalse(m['pdata_search_performed'])
            self.assertFalse(m['native_called'])
            scenario, folder = Scenario(changed_parent=True), Path(parent) / 'changed'
            with self.assertRaisesRegex(ValueError, 'FRESH_PARENT104_CHANGED'):
                capture.run(folder, scenario.dependencies(), clock=fixture.fixture.fixture.fixture.Clock())
            self.assertEqual(scenario.memory.gap_reads, 0)
            self.assertEqual(list(folder.glob('*.bin')), [])
            self.assertTrue(scenario.memory.closed)


if __name__ == '__main__':
    unittest.main()
