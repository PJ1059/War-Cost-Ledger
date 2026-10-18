"""One tiny owned table/update smoke group; no Game/old suites."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

import test_hit_game_plugin_entry_window_capture as fixture

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('owned_plugin_table_update', ROOT / 'tools/hit-game-plugin-table-update-capture.py')
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


class Memory(fixture.Memory):
    def __init__(self, changed_slot=False, state=2):
        super().__init__()
        self.state = self.after = state
        self.code_reads = self.table_reads = 0
        source = capture.validate_source(fixture.window.private_locator().private_reader().profile.FINGERPRINT)
        raw = bytearray(b'\x42' * capture.TABLE_BYTES)
        for row in source['stores']:
            struct.pack_into('<Q', raw, row['offset_from_return'], self.game + row['value_rva'])
        if changed_slot:
            struct.pack_into('<Q', raw, capture.UPDATE_SLOT, self.game + capture.UPDATE_RVA + 16)
        self.table = bytes(raw)

    def query(self, address):
        if address == self.game + capture.UPDATE_RVA:
            self.queries.append(address)
            return {'base': self.game, 'size': fixture.fixture.locator.IMAGE_SIZE,
                    'state': 0x1000, 'type': 0x1000000, 'protect': 0x20}
        return super().query(address)

    def read(self, address, n):
        if address == self.game + capture.TABLE_RVA:
            assert n == 200
            self.reads.append((address, n))
            self.table_reads += 1
            return self.table
        if address == self.game + capture.UPDATE_RVA:
            assert n == 80
            self.reads.append((address, n))
            self.code_reads += 1
            return b'\x90' * 80
        return super().read(address, n)


class Scenario(fixture.Scenario):
    def __init__(self, **options):
        super().__init__()
        self.memory = Memory(**options)


class PluginTableSmokeTests(unittest.TestCase):
    def test_arithmetic_table_double_read_known_slot_gate_and_phase(self):
        with tempfile.TemporaryDirectory() as parent:
            scenario = Scenario()
            result = capture.run(Path(parent) / 'normal', scenario.dependencies(), clock=fixture.fixture.fixture.Clock())
            meta = json.loads(Path(result['json_path']).read_text('utf8'))
            self.assertEqual(len(Path(result['binary_path']).read_bytes()), 280)
            self.assertEqual(meta['budget']['read_calls'], 13)
            self.assertEqual(meta['budget']['query_calls'], 13)
            self.assertEqual(meta['budget']['bytes_requested'], 8876)
            self.assertEqual((scenario.memory.table_reads, scenario.memory.code_reads), (2, 1))
            self.assertEqual(meta['source']['stores'][1]['offset_from_return'], 0x68)
            self.assertEqual(meta['source']['stores'][1]['value_rva'], 0x4EE6C0)
            self.assertEqual(len(meta['table_qword_hex']), 25)
            self.assertEqual(meta['table_qword_hex'][0], '4242424242424242')
            self.assertFalse(meta['unknown_table_words_followed'])
            self.assertFalse(meta['declared_code_complete'])
            self.assertFalse(meta['logical_function_complete'])
            self.assertFalse(meta['plugin_table_contract_proven'])
            self.assertFalse(meta['native_called'])
            for opts, reason in (({'changed_slot': True}, 'KNOWN_SLOT_CHANGED'),
                                 ({'state': 4}, 'EXPECTS_STATIC')):
                scenario, folder = Scenario(**opts), Path(parent) / reason
                with self.assertRaisesRegex(ValueError, reason):
                    capture.run(folder, scenario.dependencies(), clock=fixture.fixture.fixture.Clock())
                self.assertEqual(scenario.memory.code_reads, 0)
                self.assertEqual(list(folder.glob('*.bin')), [])
                self.assertTrue(scenario.memory.closed)


if __name__ == '__main__':
    unittest.main()
