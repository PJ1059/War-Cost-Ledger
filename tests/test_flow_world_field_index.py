"""Owned small-section stream/context fixtures; no Game process access."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import test_flow_world_reference_capture as fixture

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('owned_world_field_index', ROOT / 'tools/flow-world-field-index.py')
indexer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(indexer)


class Memory(fixture.Memory):
    def __init__(self, exports, payload, profile_changed=False, read_fail_at=None, **options):
        super().__init__(exports, **options)
        self.payload, self.profile_changed, self.read_fail_at = payload, profile_changed, read_fail_at
        self.payload_read_calls = 0

    def read(self, address, n):
        if address == self.exe and n == 4096:
            self.reads.append((address, n))
            raw = bytearray(4096)
            raw[:2] = b'MZ'
            struct.pack_into('<I', raw, 60, 0x1E0)
            raw[0x1E0:0x1E4] = b'PE\0\0'
            struct.pack_into('<H', raw, 0x1E4, 0x8664)
            struct.pack_into('<H', raw, 0x1E6, 19)
            struct.pack_into('<H', raw, 0x1E0 + 20, 240)
            optional = 0x1E0 + 24
            struct.pack_into('<H', raw, optional, 0x20B)
            struct.pack_into('<I', raw, optional + 56, indexer.world.iat.flow.EXE_IMAGE_SIZE)
            first = optional + 240
            struct.pack_into('<II', raw, first + 8, indexer.SECTION['virtual_size'] +
                             (1 if self.profile_changed else 0), 0x1000)
            struct.pack_into('<I', raw, first + 36, 0x60000020)
            return bytes(raw)
        offset = address - self.exe - 0x1000
        if 0 <= offset < offset + n <= len(self.payload):
            self.payload_read_calls += 1
            if self.payload_read_calls == self.read_fail_at:
                raise OSError('OWNED_INJECTED_RPM_FAILURE')
            self.reads.append((address, n))
            return self.payload[offset:offset + n]
        return super().read(address, n)


class Scenario(fixture.Scenario):
    def __init__(self, exports, payload, **options):
        final_change = options.pop('final_change', None)
        super().__init__(exports, final_change=final_change)
        self.memory = Memory(exports, payload, **options)


def payload_with_matches():
    payload = bytearray(256)
    offsets = (0, 33, 63, 125, 250)
    for i, offset in enumerate(offsets):
        payload[offset:offset + 4] = indexer.PATTERNS[i % 2]
    return bytes(payload), offsets


class FieldIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exports = indexer.world.iat.load_lua_file()['exports']['named_exports']

    def small_section(self, payload):
        return {**indexer.SECTION, 'virtual_size': len(payload),
                'end_exclusive': 0x1000 + len(payload), 'owned_fixture_only': True}

    def run_small_fixture(self, scenario, folder):
        # Only owned tests bypass the production hard20MB PE profile, so all
        # stream boundary cases can use small declared memory without Game IO.
        with patch.object(indexer, 'inspect_section', return_value=self.small_section(scenario.memory.payload)):
            with patch.object(indexer, 'CHUNK_BYTES', 64):
                return indexer.run(folder, scenario.dependencies(), clock=fixture.fixture.Clock())

    def test_cross_chunk_last31_full_context_dedup_and_section_tail(self):
        payload, offsets = payload_with_matches()
        scenario = Scenario(self.exports, payload)
        budget = indexer.world.Budget(scenario.memory, scenario.memory.identity, fixture.fixture.Clock())
        with patch.object(indexer, 'CHUNK_BYTES', 64):
            result = indexer.stream_index(budget, self.small_section(payload), {})
        self.assertTrue(result['complete'])
        self.assertEqual(result['payload_reads'], 4)
        self.assertEqual(result['payload_bytes'], len(payload))
        self.assertEqual([row['rva'] for row in result['candidates']], [0x1000 + offset for offset in offsets])
        self.assertEqual(len({row['rva'] for row in result['candidates']}), 5)
        for row, offset in zip(result['candidates'], offsets):
            start, end = max(0, offset - 16), min(len(payload), offset + 36)
            self.assertEqual(row['window_hex'], payload[start:end].hex())
            self.assertEqual(row['window_bytes'], end - start)
            self.assertLessEqual(row['window_bytes'], 52)
        self.assertEqual(result['candidates'][1]['after_bytes'], 32)  # pos33 is last31 of block64
        self.assertEqual(result['candidates'][2]['before_bytes'], 16)  # pattern crosses63/64
        self.assertEqual(result['candidates'][-1]['after_bytes'], 2)
        self.assertTrue(result['candidates'][-1]['section_boundary_truncated'])

    def test_small_owned_end_to_end_checks_ship_world_modules_no_whole_binary(self):
        payload, _ = payload_with_matches()
        scenario = Scenario(self.exports, payload)
        with tempfile.TemporaryDirectory() as parent:
            status = self.run_small_fixture(scenario, Path(parent) / 'capture')
            meta = json.loads(Path(status['json_path']).read_text('utf8'))
            self.assertTrue(meta['source_gates_verified'])
            self.assertEqual(meta['stream']['candidate_count'], 5)
            self.assertEqual(meta['stream']['payload_bytes'], 256)
            self.assertFalse(meta['whole_binary_saved'])
            self.assertEqual(list((Path(parent) / 'capture').glob('*.bin')), [])
            self.assertEqual(scenario.memory.ref_reads, 2)
            self.assertEqual(scenario.resolutions, 2)
            self.assertEqual(meta['ship_before'], meta['ship_after'])
            self.assertFalse(meta['current_world_matches_historical_no_ref'])  # current ref41 is observed, not rejected
            self.assertFalse(meta['consumer_proven'])
            self.assertEqual(meta['registry_reads'], 0)
            self.assertTrue(scenario.memory.closed)

    def test_candidate_cap_stops_with_explicit_incomplete_after_source_gates(self):
        payload = indexer.PATTERNS[0] * 80
        scenario = Scenario(self.exports, payload)
        with tempfile.TemporaryDirectory() as parent:
            status = self.run_small_fixture(scenario, Path(parent) / 'capture')
            meta = json.loads(Path(status['json_path']).read_text('utf8'))
            self.assertEqual(status['status'], 'truncated')
            self.assertTrue(meta['truncated'])
            self.assertFalse(meta['complete'])
            self.assertEqual(meta['reason'], 'CANDIDATE_LIMIT')
            self.assertEqual(len(meta['candidates']), 64)
            self.assertTrue(meta['source_gates_verified'])
            self.assertLessEqual(scenario.memory.payload_read_calls, 5)

    def test_pe_profile_change_or_non_ship_never_scans(self):
        payload, _ = payload_with_matches()
        for options, reason in (({'profile_changed': True}, 'SECTION0_PROFILE_CHANGED'),
                                ({'state': 4}, 'EXPECTS_SHIP')):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as parent:
                scenario = Scenario(self.exports, payload, **options)
                with self.assertRaisesRegex(ValueError, reason):
                    indexer.run(Path(parent) / 'capture', scenario.dependencies(), clock=fixture.fixture.Clock())
                self.assertEqual(scenario.memory.payload_read_calls, 0)
                self.assertEqual(scenario.memory.world_reads, 0)
                self.assertTrue(scenario.memory.closed)
        scenario = Scenario(self.exports, payload)
        budget = indexer.world.Budget(scenario.memory, scenario.memory.identity, fixture.fixture.Clock())
        self.assertEqual(indexer.inspect_section(budget)['virtual_size'], 20919884)

    def test_changed_world_module_or_read_failure_withholds_all_windows(self):
        payload, _ = payload_with_matches()
        for options, reason in (({'change_ref': True}, 'WORLD_OR_REFERENCE_CHANGED'),
                                ({'final_change': ('exe_base', fixture.Memory.exe + 4096)}, 'MODULE_CHANGED'),
                                ({'read_fail_at': 2}, 'INJECTED_RPM_FAILURE')):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as parent:
                scenario = Scenario(self.exports, payload, **options)
                folder = Path(parent) / 'capture'
                with self.assertRaisesRegex((ValueError, OSError), reason):
                    self.run_small_fixture(scenario, folder)
                meta = json.loads((folder / 'field-index.incomplete.json').read_text('utf8'))
                self.assertTrue(meta['results_withheld'])
                self.assertNotIn('candidates', meta)
                self.assertFalse(meta['source_gates_verified'])
                self.assertEqual(list(folder.glob('*.bin')), [])
                self.assertTrue(scenario.memory.closed)

    def test_low_cap_and_frozen_source_change_fail_once(self):
        payload, _ = payload_with_matches()
        with tempfile.TemporaryDirectory() as parent:
            scenario = Scenario(self.exports, payload)
            with patch.object(indexer.world.iat.flow, 'MAX_READS', 10):
                with self.assertRaisesRegex(ValueError, 'BUDGET'):
                    self.run_small_fixture(scenario, Path(parent) / 'low')
            self.assertLessEqual(len(scenario.memory.reads), 10)
            self.assertEqual(scenario.opens, 1)
            scenario = Scenario(self.exports, payload)
            with patch.object(indexer, 'WORLD_SOURCE_SHA', '0' * 64):
                with self.assertRaisesRegex(ValueError, 'WORLD_SOURCE_CHANGED'):
                    self.run_small_fixture(scenario, Path(parent) / 'source')
            self.assertEqual(scenario.opens, 0)


if __name__ == '__main__':
    unittest.main()
