"""Two targeted suffix-only owned methods; no old suites or Game execution."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_hit_world_update_r14_prefix_capture as previous

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'owned_world_r14_suffix_reader', ROOT / 'tools/hit-world-update-r14-suffix-capture.py')
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)
cfg_spec = importlib.util.spec_from_file_location(
    'owned_world_r14_suffix_cfg', ROOT / 'tools/analyze-hit-world-update-r14.py')
analysis = importlib.util.module_from_spec(cfg_spec)
cfg_spec.loader.exec_module(analysis)
SUFFIX_PATTERN = bytes((index * 7 + 1) & 255 for index in range(reader.SUFFIX_BYTES))
Clock = previous.previous.previous.previous.fixture.Clock
RESULTS = []


class Memory(previous.Memory):
    def __init__(self, wrong_prefix=False, changed_suffix=False):
        super().__init__()
        self.wrong_prefix, self.changed_suffix = wrong_prefix, changed_suffix
        self.known_prefix_reads, self.suffix_reads = [], []

    def read(self, address, size):
        rva = address - self.game
        if rva in (reader.prefix_private.BODY_BEGIN, reader.SUFFIX_BEGIN):
            self.reads.append((address, size))
            if self.clock:
                self.clock.value += self.delay
            if rva == reader.prefix_private.BODY_BEGIN:
                assert size == 4000
                self.known_prefix_reads.append((rva, size))
                raw = bytearray(reader.PREFIX_PIN)
                if self.wrong_prefix:
                    raw[0] ^= 1
            else:
                assert size == 738
                self.suffix_reads.append((rva, size))
                raw = bytearray(SUFFIX_PATTERN)
                if self.changed_suffix and len(self.suffix_reads) > 1:
                    raw[0] ^= 1
            return bytes(raw)
        return super().read(address, size)


class Scenario(previous.Scenario):
    def __init__(self, **options):
        super().__init__()
        self.memory = Memory(**options)


class R14SuffixTests(unittest.TestCase):
    def test_reader_known_full_pins_suffix738_post_change_and_packet_sha(self):
        self.assertEqual((reader.SUFFIX_BEGIN, reader.SUFFIX_END, reader.SUFFIX_BYTES),
                         (0xAB5FF4, 0xAB62D6, 738))
        self.assertEqual(hashlib.sha256(reader.PREFIX_PIN).hexdigest(), reader.PREFIX_BIN_SHA)
        for name, options, reason in (
                ('reader_suffix_success', {}, None),
                ('wrong_known_prefix_pin', {'wrong_prefix': True}, 'FRESH_FULL_SOURCE_PIN_CHANGED'),
                ('changed_suffix_post', {'changed_suffix': True}, 'CODE_OR_SOURCE_CHANGED_DURING_CAPTURE'),
                ('prefix_source_json_sha', {}, 'COMPLETE_PREFIX_PACKET_CHANGED')):
            with self.subTest(case=name), tempfile.TemporaryDirectory() as parent:
                scenario, folder = Scenario(**options), Path(parent) / 'capture'
                if name == 'prefix_source_json_sha':
                    with patch.object(reader, 'PREFIX_JSON_SHA', '0' * 64):
                        with self.assertRaisesRegex(ValueError, reason):
                            reader.run(folder, scenario.dependencies(), Clock())
                elif reason:
                    with self.assertRaisesRegex(ValueError, reason):
                        reader.run(folder, scenario.dependencies(), Clock())
                else:
                    status = reader.run(folder, scenario.dependencies(), Clock())
                    meta = json.loads(Path(status['json_path']).read_text('utf8'))
                    raw = Path(status['binary_path']).read_bytes()
                    self.assertEqual(raw, SUFFIX_PATTERN)
                    self.assertEqual(meta['ranges'], [{'name': 'world_update_same_declaration_suffix',
                        'module': 'game', 'rva': reader.SUFFIX_BEGIN, 'length': 738, 'binary_offset': 0}])
                    self.assertEqual(scenario.memory.suffix_reads,
                                     [(reader.SUFFIX_BEGIN, 738), (reader.SUFFIX_BEGIN, 738)])
                    self.assertEqual(scenario.memory.known_prefix_reads,
                                     [(reader.prefix_private.BODY_BEGIN, 4000)] * 2)
                    self.assertEqual(scenario.memory.root_reads,
                                     [(reader.prefix_private.root_private.ROOT_BEGIN, 84)] * 2)
                    self.assertEqual(scenario.memory.hint_reads, 2)
                    self.assertEqual(len(scenario.memory.unwind_reads), 7)
                    self.assertTrue(meta['root_full_source_pin_before_after_match'])
                    self.assertTrue(meta['current_full_prefix_pin_before_after_match'])
                    self.assertTrue(meta['suffix_before_after_match'])
                    self.assertTrue(meta['fixed_record_verified_before_after'])
                    self.assertTrue(meta['offline_CFG_required'])
                    self.assertFalse(meta['whole_world_update_captured'])
                    self.assertFalse(meta['r14_unchanged_to_call_proven'])
                    self.assertFalse(meta['native_called'])
                    self.assertFalse(meta['native_written'])
                    self.assertEqual(meta['budget']['read_calls'], len(scenario.memory.reads))
                    self.assertEqual(meta['budget']['query_calls'], len(scenario.memory.queries))
                    self.assertEqual(meta['budget']['bytes_requested'], sum(n for _, n in scenario.memory.reads))
                    self.assertLessEqual(meta['budget']['read_calls'], 32)
                    self.assertLessEqual(meta['budget']['query_calls'], 32)
                    self.assertLessEqual(meta['budget']['bytes_requested'], 24576)
                    self.assertTrue(scenario.memory.closed)
                    RESULTS.append({'case': name, 'status': 'PASS', 'ranges': meta['ranges'],
                        'root_reads': scenario.memory.root_reads,
                        'known_prefix_reads': scenario.memory.known_prefix_reads,
                        'suffix_reads': scenario.memory.suffix_reads, 'hint_reads': scenario.memory.hint_reads,
                        'budget': meta['budget']})
                    continue
                self.assertEqual(list(folder.glob('*.bin')), [])
                meta = json.loads((folder / 'callsite.incomplete.json').read_text('utf8'))
                self.assertFalse(meta['partial_binary_saved'])
                if name == 'prefix_source_json_sha':
                    self.assertEqual(scenario.opens, 0)
                    self.assertEqual(scenario.memory.reads, [])
                else:
                    self.assertTrue(scenario.memory.closed)
                    self.assertEqual(scenario.memory.suffix_reads, [] if name == 'wrong_known_prefix_pin'
                                     else [(reader.SUFFIX_BEGIN, 738)] * 2)
                RESULTS.append({'case': name, 'status': 'PASS', 'error': meta['error'],
                    'opens': scenario.opens, 'suffix_reads': scenario.memory.suffix_reads,
                    'binary_saved': False, 'budget': meta.get('budget')})

    def test_suffix_cfg_closed_return_r14_backedge_and_outside_jump(self):
        closed = bytearray(b'\x90' * reader.SUFFIX_BYTES)
        closed[0] = 0xC3
        redefined = bytearray(b'\x90' * reader.SUFFIX_BYTES)
        redefined[:3] = bytes.fromhex('4c8bf2')
        displacement = (analysis.CALL_PC - 7) - (reader.SUFFIX_BEGIN + 9)
        redefined[3:9] = b'\x0f\x85' + displacement.to_bytes(4, 'little', signed=True)
        redefined[9] = 0xC3
        outside = bytearray(b'\x90' * reader.SUFFIX_BYTES)
        displacement = reader.SUFFIX_END + 1 - (reader.SUFFIX_BEGIN + 5)
        outside[:5] = b'\xe9' + displacement.to_bytes(4, 'little', signed=True)
        for name, suffix, expected in (
                ('suffix_cfg_closed_return', closed, 'PROVED_CAPTURED_CFG_UNDER_X64_CALL_ABI'),
                ('suffix_cfg_redefined_backedge', redefined, 'WITHHELD_R14_REDEFINED'),
                ('suffix_cfg_outside_jump', outside, 'WITHHELD_CFG_INCOMPLETE')):
            with self.subTest(case=name):
                result = analysis.analyze_code(reader.ROOT_PIN, previous.BODY_PATTERN, bytes(suffix))
                self.assertEqual(result['status'], expected)
                self.assertTrue(result['closed_suffix_mode'])
                self.assertTrue(result['contact_call_fallthrough_walked'])
                self.assertEqual(result['verified_legal_tail_transfer_sites'], [])
                self.assertFalse(result['Game_accessed'])
                self.assertFalse(result['native_called'])
                self.assertFalse(result['classification_ready'])
                self.assertTrue(all(not call['callee_followed'] for call in result['calls_not_followed']))
                if name == 'suffix_cfg_closed_return':
                    self.assertEqual(result['incoming_r14_states_at_call'], ['global_context'])
                    self.assertEqual(result['normal_return_sites'], [reader.SUFFIX_BEGIN])
                    self.assertTrue(result['normal_CFG_closed'])
                    self.assertTrue(result['r14_preserved_on_captured_normal_CFG_to_call'])
                    self.assertTrue(result['contact_argument_source_proven_under_normal_x64_ABI'])
                elif name == 'suffix_cfg_redefined_backedge':
                    self.assertEqual(result['incoming_r14_states_at_call'],
                                     ['global_context', 'redefined_unknown'])
                    self.assertEqual(result['normal_return_sites'], [reader.SUFFIX_BEGIN + 9])
                    self.assertTrue(result['normal_CFG_closed'])
                    self.assertTrue(any(row['rva'] == reader.SUFFIX_BEGIN and row['hex'] == '4c8bf2'
                                        for row in result['r14_definitions']))
                    self.assertFalse(result['r14_preserved_on_captured_normal_CFG_to_call'])
                    self.assertFalse(result['contact_argument_source_proven_under_normal_x64_ABI'])
                else:
                    self.assertEqual(result['normal_return_sites'], [])
                    self.assertTrue(any(row[0] == 'OUTSIDE_CAPTURE_EDGE' for row in result['issues']))
                    self.assertFalse(result['normal_CFG_closed'])
                    self.assertFalse(result['r14_preserved_on_captured_normal_CFG_to_call'])
                    self.assertFalse(result['contact_argument_source_proven_under_normal_x64_ABI'])
                RESULTS.append({'case': name, 'status': 'PASS', 'analysis_status': result['status'],
                    'incoming_r14_states_at_call': result['incoming_r14_states_at_call'],
                    'normal_return_sites': result['normal_return_sites'],
                    'normal_CFG_closed': result['normal_CFG_closed'],
                    'r14_preserved_on_captured_normal_CFG_to_call':
                        result['r14_preserved_on_captured_normal_CFG_to_call'],
                    'contact_argument_source_proven_under_normal_x64_ABI':
                        result['contact_argument_source_proven_under_normal_x64_ABI'],
                    'issues': result['issues'], 'decoder': result['decoder']})


if __name__ == '__main__':
    unittest.main()
