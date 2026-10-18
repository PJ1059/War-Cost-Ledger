"""One tiny fixed-record owned group; no Game or metadata search."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import test_hit_game_plugin_entry_window_capture as fixture

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('owned_parent104_fragment', ROOT / 'tools/hit-contact-parent-fragment-capture.py')
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


class Memory(fixture.Memory):
    def __init__(self, changed_record=False):
        super().__init__()
        self.changed_record, self.parent_reads = changed_record, 0

    def query(self, address):
        if address in (self.game + capture.PARENT_RVA, self.game + capture.CALLER_RVA):
            self.queries.append(address)
            return {'base': self.game, 'size': fixture.fixture.locator.IMAGE_SIZE,
                    'state': 0x1000, 'type': 0x1000000, 'protect': 0x20}
        return super().query(address)

    def read(self, address, n):
        if address in (self.game + capture.PARENT_RVA, self.game + capture.CALLER_RVA, self.game + capture.RECORD_RVA):
            self.reads.append((address, n))
            if address == self.game + capture.CALLER_RVA:
                assert n == 5
                return bytes.fromhex(capture.CALLER_HEX)
            if address == self.game + capture.RECORD_RVA:
                assert n == 12
                return bytes(n) if self.changed_record else bytes.fromhex(capture.RECORD_HEX)
            assert n == 104
            self.parent_reads += 1
            return b'\x90' * 104
        return super().read(address, n)


class Scenario(fixture.Scenario):
    def __init__(self, **options):
        super().__init__()
        self.memory = Memory(**options)


class Parent104SmokeTests(unittest.TestCase):
    def test_exact_fixed_record_parent_and_changed_record_blocks_body(self):
        with tempfile.TemporaryDirectory() as parent:
            scenario = Scenario()
            result = capture.run(Path(parent) / 'normal', scenario.dependencies(), clock=fixture.fixture.fixture.Clock())
            m = json.loads(Path(result['json_path']).read_text('utf8'))
            self.assertEqual(len(Path(result['binary_path']).read_bytes()), 104)
            self.assertEqual(m['budget']['read_calls'], 15)
            self.assertEqual(m['budget']['query_calls'], 15)
            self.assertEqual(m['budget']['bytes_requested'], 8534)
            self.assertEqual(scenario.memory.parent_reads, 1)
            self.assertTrue(m['declared_code_complete'])
            self.assertFalse(m['logical_function_complete'])
            self.assertFalse(m['pdata_search_performed'])
            self.assertFalse(m['unwind_chain_read'])
            self.assertFalse(m['handler_scope_read'])
            self.assertFalse(m['native_called'])
            self.assertEqual(m['state_before'], m['state_after'])
            scenario = Scenario(changed_record=True)
            folder = Path(parent) / 'bad-record'
            with self.assertRaisesRegex(ValueError, 'FIXED_RECORD_CHANGED'):
                capture.run(folder, scenario.dependencies(), clock=fixture.fixture.fixture.Clock())
            self.assertEqual(scenario.memory.parent_reads, 0)
            self.assertEqual(list(folder.glob('*.bin')), [])
            self.assertTrue(scenario.memory.closed)


if __name__ == '__main__':
    unittest.main()
