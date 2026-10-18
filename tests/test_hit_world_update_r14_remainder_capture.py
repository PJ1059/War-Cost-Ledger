"""One fixed-remainder owned group; no old tests or Game execution."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import test_hit_world_update_logical_metadata_capture as previous

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'owned_world_remainder', ROOT / 'tools/hit-world-update-r14-remainder-capture.py')
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)
cfg_spec = importlib.util.spec_from_file_location(
    'owned_world_remainder_cfg', ROOT / 'tools/analyze-hit-world-update-r14.py')
analysis = importlib.util.module_from_spec(cfg_spec)
cfg_spec.loader.exec_module(analysis)
SOURCE = reader.validate_metadata_packet()
Clock = previous.Clock
BODY_PATTERN = b'\xC3' + b'\x90' * (reader.BODY_BYTES - 1)
RESULTS = []


def old_limits():
    return (previous.reader.v1.MAX_BYTES, previous.reader.v1.MAX_READS,
            previous.reader.v1.frozen.MAX_BYTES,
            previous.reader.v1.frozen.MAX_DECLARATION_BYTES)


class Memory(previous.Memory):
    def __init__(self, changed_body=False, changed_source=False):
        super().__init__()
        self.changed_body, self.changed_source = changed_body, changed_source
        self.body_reads = []
        self.window = reader.METADATA_PIN
        self.unknown = {node[key]['rva']: bytes.fromhex(node[key]['raw_hex'])
            for row in SOURCE['ownership'] for node in row['unwind_chain'][:1]
            for key in ('header', 'chain_entry') if key in node}

    def query(self, address):
        if self.game + reader.BODY_BEGIN <= address < self.game + reader.BODY_END:
            self.queries.append(address)
            if self.clock:
                self.clock.value += self.delay
            return {'base': self.game, 'size': reader.v1.frozen.IMAGE_SIZE,
                    'state': 0x1000, 'type': 0x1000000, 'protect': 0x20}
        return super().query(address)

    def read(self, address, size):
        rva = address - self.game
        if rva == reader.BODY_BEGIN:
            assert size == 5006
            self.reads.append((address, size))
            self.body_reads.append((rva, size))
            if self.clock:
                self.clock.value += self.delay
            raw = bytearray(BODY_PATTERN)
            if self.changed_body and len(self.body_reads) > 1:
                raw[-1] ^= 1
            return bytes(raw)
        raw = super().read(address, size)
        source_begin = reader.metadata_private.switch_private.suffix_private.SUFFIX_BEGIN
        if self.changed_source and rva == source_begin and len(self.suffix_reads) > 1:
            raw = raw[:-1] + bytes((raw[-1] ^ 1,))
        return raw


class Scenario(previous.Scenario):
    def __init__(self, **options):
        super().__init__()
        self.memory = Memory(**options)


class R14RemainderTests(unittest.TestCase):
    def test_fixed_scope_private_budget_post_gates_and_remainder_cfg(self):
        self.assertEqual((reader.BODY_BEGIN, reader.BODY_END, reader.BODY_BYTES),
                         (0xAB62D6, 0xAB7664, 5006))
        original_limits = old_limits()
        self.assertEqual(original_limits[:2], (24576, 32))
        self.assertEqual(original_limits[3], 8192)
        for name, options, reason in (
                ('reader_fixed5006_success', {}, None),
                ('remainder_post_changed', {'changed_body': True}, 'CODE_CHANGED_DURING_CAPTURE'),
                ('known_suffix_post_changed', {'changed_source': True}, 'WINDOW_OR_SOURCE_CHANGED_DURING_CAPTURE')):
            with self.subTest(case=name), tempfile.TemporaryDirectory() as parent:
                scenario, folder = Scenario(**options), Path(parent) / 'capture'
                if reason:
                    with self.assertRaisesRegex(ValueError, reason):
                        reader.run(folder, scenario.dependencies(), Clock())
                    self.assertEqual(list(folder.glob('*.bin')), [])
                    meta = json.loads((folder / 'callsite.incomplete.json').read_text('utf8'))
                    self.assertFalse(meta['partial_binary_saved'])
                    self.assertEqual(meta['new_code_body_reads'], 2)
                    self.assertEqual(meta['unknown_code_bytes_returned'], 10012)
                    RESULTS.append({'case': name, 'status': 'PASS', 'error': meta['error'],
                        'binary_saved': False, 'body_reads': scenario.memory.body_reads,
                        'budget': meta['budget']})
                else:
                    status = reader.run(folder, scenario.dependencies(), Clock())
                    meta = json.loads(Path(status['json_path']).read_text('utf8'))
                    self.assertEqual(Path(status['binary_path']).read_bytes(), BODY_PATTERN)
                    self.assertEqual(meta['ranges'], [{'name': 'world_update_fixed_remainder_before_switch_data',
                        'module': 'game', 'rva': reader.BODY_BEGIN, 'length': 5006, 'binary_offset': 0}])
                    self.assertEqual(meta['ownership'], SOURCE['ownership'])
                    self.assertEqual(meta['exception_records'], SOURCE['exception_records'])
                    self.assertTrue(meta['remainder_before_after_match'])
                    self.assertTrue(meta['full_metadata_window_matches_frozen_source'])
                    self.assertTrue(meta['source_UW_matches_frozen_before_body'])
                    self.assertTrue(meta['full_source_pins_before_after_match'])
                    self.assertEqual(scenario.memory.window_reads,
                                     [(reader.metadata_private.WINDOW_RVA, 204)] * 2)
                    self.assertEqual(len(scenario.memory.unwind_reads), 7)
                    self.assertEqual(len(scenario.memory.unknown_reads), 4)
                    self.assertEqual(meta['code_bytes'], 5006)
                    self.assertEqual(meta['new_code_body_reads'], 2)
                    self.assertEqual(meta['budget']['max_bytes'], 32768)
                    self.assertEqual(meta['budget']['max_declaration_bytes'], 12288)
                    self.assertEqual(meta['budget']['read_calls'], len(scenario.memory.reads))
                    self.assertEqual(meta['budget']['query_calls'], len(scenario.memory.queries))
                    self.assertEqual(meta['budget']['bytes_requested'], sum(n for _, n in scenario.memory.reads))
                    self.assertLessEqual(meta['budget']['read_calls'], 32)
                    self.assertLessEqual(meta['budget']['query_calls'], 32)
                    self.assertLessEqual(meta['budget']['bytes_requested'], 32768)
                    self.assertLessEqual(meta['budget']['declaration_bytes_requested'], 12288)
                    for key in ('later_three_declarations_ownership_proven', 'logical_function_complete',
                                'normal_CFG_closed', 'native_called', 'native_written'):
                        self.assertFalse(meta[key])
                    RESULTS.append({'case': name, 'status': 'PASS', 'ranges': meta['ranges'],
                        'body_reads': scenario.memory.body_reads, 'budget': meta['budget'],
                        'source_UW_reads': scenario.memory.unwind_reads,
                        'target_UW_reads': scenario.memory.unknown_reads,
                        'metadata_ownership_only': True,
                        'old_limits_before': original_limits, 'old_limits_after': old_limits()})
                self.assertEqual(scenario.memory.body_reads, [(reader.BODY_BEGIN, 5006)] * 2)
                self.assertTrue(scenario.memory.closed)
                self.assertEqual(old_limits(), original_limits)

        switch = reader.metadata_private.switch_private
        suffix = bytearray(b'\x90' * 738)
        suffix_base = switch.suffix_private.SUFFIX_BEGIN
        start = analysis.SWITCH_START - suffix_base
        begin, end = analysis.CASE_BEGIN - suffix_base, analysis.CASE_END - suffix_base
        suffix[start:start + len(analysis.SWITCH_SOURCE)] = analysis.SWITCH_SOURCE
        suffix[begin:end] = switch.SUFFIX_PIN[begin:end]
        redefined = bytearray(b'\x90' * 5006)
        redefined[:3] = bytes.fromhex('4c8bf2')
        displacement = analysis.CALL_PC - 7 - (reader.BODY_BEGIN + 9)
        redefined[3:9] = b'\x0f\x85' + displacement.to_bytes(4, 'little', signed=True)
        redefined[9] = 0xC3
        prefix_pattern = previous.previous.previous.previous.BODY_PATTERN
        for name, remainder, expected in (
                ('cfg_forward_to_remainder_ret', BODY_PATTERN, 'PROVED_CAPTURED_CFG_UNDER_X64_CALL_ABI'),
                ('cfg_remainder_rebind_back_to_call', bytes(redefined), 'WITHHELD_R14_REDEFINED')):
            with self.subTest(case=name):
                result = analysis.analyze_code(switch.ROOT_PIN, prefix_pattern, bytes(suffix),
                                               reader.metadata_private.SWITCH_PIN, remainder)
                self.assertEqual(result['status'], expected)
                self.assertTrue(result['fixed_remainder_mode'])
                self.assertTrue(result['normal_CFG_closed'])
                self.assertFalse(result['later_three_declarations_ownership_assumed'])
                self.assertFalse(result['switch_data_or_next_declaration_decoded'])
                self.assertFalse(result['Game_accessed'])
                self.assertFalse(result['native_called'])
                self.assertTrue(all(not call['callee_followed'] for call in result['calls_not_followed']))
                if name == 'cfg_forward_to_remainder_ret':
                    self.assertEqual(result['incoming_r14_states_at_call'], ['global_context'])
                    self.assertEqual(result['normal_return_sites'], [reader.BODY_BEGIN])
                    self.assertTrue(result['contact_argument_source_proven_under_normal_x64_ABI'])
                else:
                    self.assertEqual(result['incoming_r14_states_at_call'],
                                     ['global_context', 'redefined_unknown'])
                    self.assertEqual(result['normal_return_sites'], [reader.BODY_BEGIN + 9])
                    self.assertFalse(result['contact_argument_source_proven_under_normal_x64_ABI'])
                RESULTS.append({'case': name, 'status': 'PASS', 'analysis_status': result['status'],
                    'incoming_r14_states_at_call': result['incoming_r14_states_at_call'],
                    'normal_return_sites': result['normal_return_sites'],
                    'normal_CFG_closed': result['normal_CFG_closed'],
                    'contact_argument_source_proven_under_normal_x64_ABI':
                        result['contact_argument_source_proven_under_normal_x64_ABI'],
                    'later_three_declarations_ownership_assumed': False, 'decoder': result['decoder']})
        self.assertEqual(old_limits(), original_limits)


if __name__ == '__main__':
    unittest.main()
