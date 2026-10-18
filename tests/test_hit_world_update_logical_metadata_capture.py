"""One owned metadata-only group; no Game or previous suite execution."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import test_hit_world_update_switch_table_capture as previous

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'owned_world_logical_metadata', ROOT / 'tools/hit-world-update-logical-metadata-capture.py')
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)
SOURCE_CHAIN = previous.previous.previous.previous.SOURCE_CHAIN
SOURCE_METADATA = previous.previous.previous.previous.METADATA
Clock = previous.Clock
RESULTS = []


class Memory(previous.Memory):
    def __init__(self, changed_window=False, missing_target=False):
        super().__init__()
        self.changed_window = changed_window
        self.window_reads, self.unknown_reads = [], []
        width = 0x60 if missing_target else 0x80
        first_end = reader.HINT.DECL_END
        records = [reader.HINT.HINT_BYTES]
        self.unknown = {}
        for index in range(1, reader.RECORD_COUNT):
            begin = first_end + (index - 1) * width
            end, unwind = begin + width, 0x2510000 + index * 0x20
            records.append(struct.pack('<III', begin, end, unwind))
            self.unknown[unwind] = bytes.fromhex('21000000')
            self.unknown[unwind + 4] = reader.HINT.HINT_BYTES
        self.window = b''.join(records)
        header = bytearray(self.header)
        section = reader.v1.frozen.PE_OFFSET + 24 + 240 + 40
        struct.pack_into('<II', header, section + 8,
                         reader.UNWIND_END - reader.UNWIND_BEGIN, reader.UNWIND_BEGIN)
        struct.pack_into('<I', header, section + 36, 0x40000040)
        self.header = bytes(header)

    def read(self, address, size):
        rva = address - self.game
        if rva == reader.WINDOW_RVA or rva in self.unknown or rva == reader.switch_private.TABLE_RVA:
            self.reads.append((address, size))
            if self.clock:
                self.clock.value += self.delay
            if rva == reader.WINDOW_RVA:
                assert size == reader.WINDOW_BYTES
                self.window_reads.append((rva, size))
                raw = bytearray(self.window)
                if self.changed_window and len(self.window_reads) > 1:
                    raw[-1] ^= 1
                return bytes(raw)
            if rva in self.unknown:
                raw = self.unknown[rva]
                assert size == len(raw)
                self.unknown_reads.append({'rva': rva, 'length': size, 'raw_hex': raw.hex()})
                return raw
            assert size == 24
            self.table_reads.append((rva, size))
            return reader.SWITCH_PIN
        return super().read(address, size)


class Scenario(previous.Scenario):
    def __init__(self, **options):
        super().__init__()
        self.memory = Memory(**options)


class LogicalMetadataTests(unittest.TestCase):
    def test_owned_window204_shared_source_ancestry_and_fail_closed(self):
        self.assertEqual((reader.WINDOW_RVA, reader.RECORD_COUNT, reader.WINDOW_BYTES),
                         (0x40537DC, 17, 204))
        self.assertEqual(reader.TARGETS, (0xAB62D6, 0xAB6A65))
        self.assertEqual(reader.MAX_UNKNOWN_NODES, 4)
        self.assertEqual(hashlib.sha256(reader.SWITCH_PIN).hexdigest(), reader.SWITCH_BIN_SHA)
        for name, options, reason in (
                ('metadata_success_shared_known_ancestry', {}, None),
                ('window_post_changed', {'changed_window': True}, 'WINDOW_OR_SOURCE_CHANGED_DURING_CAPTURE'),
                ('source_packet_sha', {}, 'COMPLETE_SWITCH_PACKET_CHANGED'),
                ('target_not_in_fixed_window', {'missing_target': True}, 'TARGET_NOT_IN_FIXED_WINDOW'),
                ('insufficient_read_budget', {}, 'BUDGET')):
            with self.subTest(case=name), tempfile.TemporaryDirectory() as parent:
                scenario, folder = Scenario(**options), Path(parent) / 'capture'
                if name == 'source_packet_sha':
                    with patch.object(reader, 'SWITCH_JSON_SHA', '0' * 64):
                        with self.assertRaisesRegex(ValueError, reason):
                            reader.run(folder, scenario.dependencies(), Clock())
                elif name == 'insufficient_read_budget':
                    with patch.object(reader.v1, 'MAX_READS', 24):
                        with self.assertRaisesRegex(ValueError, reason):
                            reader.run(folder, scenario.dependencies(), Clock())
                elif reason:
                    with self.assertRaisesRegex(ValueError, reason):
                        reader.run(folder, scenario.dependencies(), Clock())
                else:
                    status = reader.run(folder, scenario.dependencies(), Clock())
                    meta = json.loads(Path(status['json_path']).read_text('utf8'))
                    self.assertEqual(Path(status['binary_path']).read_bytes(), scenario.memory.window)
                    self.assertEqual(meta['ranges'], [{'name': 'current_and_following_16_exception_records',
                        'module': 'game', 'rva': reader.WINDOW_RVA, 'length': 204, 'binary_offset': 0}])
                    self.assertEqual(scenario.memory.window_reads, [(reader.WINDOW_RVA, 204)] * 2)
                    self.assertEqual(scenario.memory.hint_reads, 0)
                    self.assertEqual(meta['unwind_chain'], SOURCE_CHAIN)
                    self.assertEqual(len(scenario.memory.unwind_reads), 7)
                    self.assertEqual({row['rva']: bytes.fromhex(row['raw_hex'])
                                      for row in scenario.memory.unwind_reads}, SOURCE_METADATA)
                    self.assertEqual(len(scenario.memory.unknown_reads), 4)
                    self.assertEqual(len({row['rva'] for row in scenario.memory.unknown_reads}), 4)
                    self.assertGreaterEqual(meta['metadata_cache_reuses'], 8)
                    self.assertEqual([row['target_rva'] for row in meta['ownership']], list(reader.TARGETS))
                    for row in meta['ownership']:
                        self.assertEqual(row['unknown_node_count'], 1)
                        self.assertEqual(len(row['unwind_chain']), 5)
                        self.assertEqual(row['unwind_chain'][1:], SOURCE_CHAIN)
                        self.assertTrue(row['same_AB5000_primary'])
                        self.assertTrue(row['statement_ownership_only'])
                        self.assertFalse(row['CFG_or_runtime_object_proven'])
                    self.assertEqual(len(meta['exception_records']), 17)
                    self.assertTrue(meta['exception_window_before_after_match'])
                    self.assertTrue(meta['full_source_pins_before_after_match'])
                    self.assertEqual(scenario.memory.root_reads,
                        [(reader.switch_private.suffix_private.prefix_private.root_private.ROOT_BEGIN, 84)] * 2)
                    self.assertEqual(scenario.memory.known_prefix_reads,
                        [(reader.switch_private.suffix_private.prefix_private.BODY_BEGIN, 4000)] * 2)
                    self.assertEqual(scenario.memory.suffix_reads,
                        [(reader.switch_private.suffix_private.SUFFIX_BEGIN, 738)] * 2)
                    self.assertEqual(scenario.memory.table_reads,
                        [(reader.switch_private.TABLE_RVA, 24)] * 2)
                    self.assertEqual((meta['code_bytes'], meta['metadata_bytes'], meta['new_code_body_reads']),
                                     (0, 204, 0))
                    for key in ('code_only', 'logical_function_complete', 'normal_CFG_closed',
                                'contact_argument_source_proven', 'classification_ready',
                                'contract_ready', 'native_called', 'native_written'):
                        self.assertFalse(meta[key])
                    self.assertEqual(meta['handler_or_scope_reads'], 0)
                    self.assertEqual(meta['budget']['read_calls'], len(scenario.memory.reads))
                    self.assertEqual(meta['budget']['query_calls'], len(scenario.memory.queries))
                    self.assertEqual(meta['budget']['bytes_requested'], sum(n for _, n in scenario.memory.reads))
                    self.assertLessEqual(meta['budget']['read_calls'], 32)
                    self.assertLessEqual(meta['budget']['query_calls'], 32)
                    self.assertLessEqual(meta['budget']['bytes_requested'], 24576)
                    self.assertTrue(scenario.memory.closed)
                    RESULTS.append({'case': name, 'status': 'PASS', 'ranges': meta['ranges'],
                        'ownership': meta['ownership'], 'metadata_cache_reuses': meta['metadata_cache_reuses'],
                        'source_unwind_reads': scenario.memory.unwind_reads,
                        'unknown_unwind_reads': scenario.memory.unknown_reads,
                        'budget': meta['budget'], 'new_code_body_reads': 0})
                    continue
                self.assertEqual(list(folder.glob('*.bin')), [])
                meta = json.loads((folder / 'callsite.incomplete.json').read_text('utf8'))
                self.assertFalse(meta['partial_binary_saved'])
                if name == 'source_packet_sha':
                    self.assertEqual(scenario.opens, 0)
                    self.assertEqual(scenario.memory.reads, [])
                else:
                    self.assertTrue(scenario.memory.closed)
                    if name == 'target_not_in_fixed_window':
                        self.assertEqual(scenario.memory.unknown_reads, [])
                    if name == 'insufficient_read_budget':
                        self.assertEqual(scenario.memory.window_reads, [])
                        self.assertLessEqual(meta['budget']['read_calls'], 24)
                RESULTS.append({'case': name, 'status': 'PASS', 'error': meta['error'],
                    'opens': scenario.opens, 'window_reads': scenario.memory.window_reads,
                    'unknown_unwind_reads': scenario.memory.unknown_reads,
                    'binary_saved': False, 'budget': meta.get('budget')})


if __name__ == '__main__':
    unittest.main()
