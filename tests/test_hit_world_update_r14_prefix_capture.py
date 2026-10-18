"""Two tiny owned reader/CFG methods; never executes Game code or old suites."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_hit_world_update_root_prefix_capture as previous

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'owned_world_r14_reader', ROOT / 'tools/hit-world-update-r14-prefix-capture.py')
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)
analysis_spec = importlib.util.spec_from_file_location(
    'owned_world_r14_cfg', ROOT / 'tools/analyze-hit-world-update-r14.py')
analysis = importlib.util.module_from_spec(analysis_spec)
analysis_spec.loader.exec_module(analysis)
BODY_PATTERN = b'\x90' * (reader.BODY_BYTES - 12) + bytes.fromhex(reader.v1.PIN_HEX)
RESULTS = []


class Memory(previous.Memory):
    def __init__(self, wrong_root=False, changed_body=False):
        super().__init__()
        self.wrong_root, self.changed_body = wrong_root, changed_body
        self.body_reads = []

    def read(self, address, size):
        rva = address - self.game
        if rva in (reader.root_private.ROOT_BEGIN, reader.BODY_BEGIN):
            self.reads.append((address, size))
            if self.clock:
                self.clock.value += self.delay
            if rva == reader.root_private.ROOT_BEGIN:
                assert size == 84
                self.root_reads.append((rva, size))
                raw = bytearray(reader.ROOT_PIN)  # Frozen real bytes, data only.
                if self.wrong_root:
                    raw[0] ^= 1
            else:
                assert size == 4000
                self.body_reads.append((rva, size))
                raw = bytearray(BODY_PATTERN)
                if self.changed_body and len(self.body_reads) > 1:
                    raw[0] ^= 1
            return bytes(raw)
        return super().read(address, size)


class Scenario(previous.previous.previous.fixture.Scenario):
    def __init__(self, **options):
        super().__init__()
        self.memory = Memory(**options)


class R14PrefixTests(unittest.TestCase):
    def test_cfg_global_origin_redefinition_and_outside_capture_withhold(self):
        redefined = bytearray(BODY_PATTERN)
        redefined[:3] = bytes.fromhex('4c8bf2')  # mov r14, rdx; bytes only.
        outside = bytearray(BODY_PATTERN)
        outside[:5] = b'\xe9' + (analysis.ENTRY - 1 - reader.BODY_BEGIN - 5).to_bytes(4, 'little', signed=True)
        bypasses_lea = bytearray(BODY_PATTERN)
        bypasses_lea[:5] = b'\xe9' + (analysis.CALL_PC - reader.BODY_BEGIN - 5).to_bytes(4, 'little', signed=True)
        for name, body, expected_status, expected_states in (
                ('cfg_global_only', BODY_PATTERN, 'PROVED_CAPTURED_CFG_UNDER_X64_CALL_ABI', ['global_context']),
                ('cfg_r14_redefined', bytes(redefined), 'WITHHELD_R14_REDEFINED', ['redefined_unknown']),
                ('cfg_outside_capture', bytes(outside), 'WITHHELD_CFG_INCOMPLETE', []),
                ('cfg_bypasses_rcx_lea', bytes(bypasses_lea),
                 'WITHHELD_CONTACT_ARGUMENT_LEA_NOT_DOMINATING', ['global_context'])):
            with self.subTest(case=name):
                result = analysis.analyze_code(reader.ROOT_PIN, body)
                self.assertEqual(result['status'], expected_status)
                self.assertEqual(result['incoming_r14_states_at_call'], expected_states)
                self.assertEqual(result['r14_preserved_on_captured_normal_CFG_to_call'],
                                 name in ('cfg_global_only', 'cfg_bypasses_rcx_lea'))
                self.assertEqual(result['contact_argument_source_proven_under_normal_x64_ABI'],
                                 name == 'cfg_global_only')
                if name == 'cfg_global_only':
                    self.assertEqual(result['issues'], [])
                    self.assertEqual(result['r14_definitions'][0]['rva'], 0xAB5025)
                    self.assertEqual(result['r14_definitions'][0]['output_state'], 'global_context')
                    self.assertIn('nonvolatile', result['call_preservation_assumption'])
                elif name == 'cfg_r14_redefined':
                    self.assertTrue(any(row['rva'] == reader.BODY_BEGIN
                                        and row['hex'] == '4c8bf2'
                                        and row['output_state'] == 'redefined_unknown'
                                        for row in result['r14_definitions']))
                    self.assertIsNone(result['contact_argument_if_proved'])
                elif name == 'cfg_bypasses_rcx_lea':
                    self.assertEqual(result['issues'], [])
                    self.assertEqual(result['call_predecessors'], [reader.BODY_BEGIN])
                    self.assertFalse(result['immediate_rcx_lea_dominates_captured_call'])
                    self.assertIsNone(result['contact_argument_if_proved'])
                else:
                    self.assertTrue(any(row[0] == 'OUTSIDE_CAPTURE_EDGE' for row in result['issues']))
                    self.assertIsNone(result['contact_argument_if_proved'])
                self.assertFalse(result['unconditional_whole_function_or_runtime_pointer_proven'])
                self.assertFalse(result['classification_ready'])
                self.assertFalse(result['native_called'])
                self.assertFalse(result['Game_accessed'])
                self.assertFalse(result['exception_handler_routes_analyzed'])
                RESULTS.append({'case': name, 'status': 'PASS', 'analysis_status': result['status'],
                    'incoming_r14_states_at_call': result['incoming_r14_states_at_call'],
                    'r14_preserved_on_captured_normal_CFG_to_call':
                        result['r14_preserved_on_captured_normal_CFG_to_call'],
                    'contact_argument_source_proven_under_normal_x64_ABI':
                        result['contact_argument_source_proven_under_normal_x64_ABI'],
                    'call_predecessors': result['call_predecessors'],
                    'immediate_rcx_lea_dominates_captured_call':
                        result['immediate_rcx_lea_dominates_captured_call'],
                    'r14_definitions': result['r14_definitions'], 'issues': result['issues'],
                    'reachable_instruction_count': result['reachable_instruction_count'],
                    'decoder': result['decoder'],
                    'call_preservation_assumption': result['call_preservation_assumption']})

    def test_reader_root_source_pin_body4000_post_change_and_packet_sha(self):
        self.assertEqual((reader.BODY_BEGIN, reader.BODY_END, reader.BODY_BYTES),
                         (0xAB5054, 0xAB5FF4, 4000))
        self.assertEqual(hashlib.sha256(reader.ROOT_PIN).hexdigest(), reader.INITIALIZATION_BIN_SHA)
        for name, options, reason in (
                ('reader_success', {}, None),
                ('wrong_root_full_pin', {'wrong_root': True}, 'FRESH_ROOT_PIN_CHANGED'),
                ('changed_body_post', {'changed_body': True}, 'CODE_CHANGED_DURING_CAPTURE'),
                ('initialization_source_sha', {}, 'INITIALIZATION_PACKET_CHANGED')):
            with self.subTest(case=name), tempfile.TemporaryDirectory() as parent:
                scenario, folder = Scenario(**options), Path(parent) / 'capture'
                clock = previous.previous.previous.fixture.Clock()
                if name == 'initialization_source_sha':
                    with patch.object(reader, 'INITIALIZATION_JSON_SHA', '0' * 64):
                        with self.assertRaisesRegex(ValueError, reason):
                            reader.run(folder, scenario.dependencies(), clock)
                elif reason:
                    with self.assertRaisesRegex(ValueError, reason):
                        reader.run(folder, scenario.dependencies(), clock)
                else:
                    status = reader.run(folder, scenario.dependencies(), clock)
                    meta = json.loads(Path(status['json_path']).read_text('utf8'))
                    raw = Path(status['binary_path']).read_bytes()
                    self.assertEqual(raw, BODY_PATTERN)
                    self.assertEqual(meta['ranges'], [{
                        'name': 'world_update_current_declaration_prefix_through_contact_CALL',
                        'module': 'game', 'rva': reader.BODY_BEGIN, 'length': 4000,
                        'binary_offset': 0}])
                    self.assertEqual(scenario.memory.body_reads,
                                     [(reader.BODY_BEGIN, 4000), (reader.BODY_BEGIN, 4000)])
                    self.assertEqual(scenario.memory.root_reads,
                        [(reader.root_private.ROOT_BEGIN, 84), (reader.root_private.ROOT_BEGIN, 84)])
                    self.assertEqual(scenario.memory.hint_reads, 2)
                    self.assertEqual(len(scenario.memory.unwind_reads), 7)
                    self.assertEqual(meta['unwind_chain'], previous.SOURCE_CHAIN)
                    self.assertTrue(meta['root_full_source_pin_before_after_match'])
                    self.assertTrue(meta['code_prefix_before_after_match'])
                    self.assertTrue(meta['offline_CFG_required'])
                    self.assertFalse(meta['r14_unchanged_to_call_proven'])
                    self.assertFalse(meta['whole_world_update_captured'])
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
                        'root_reads': scenario.memory.root_reads, 'body_reads': scenario.memory.body_reads,
                        'hint_reads': scenario.memory.hint_reads, 'budget': meta['budget']})
                    continue
                self.assertEqual(list(folder.glob('*.bin')), [])
                meta = json.loads((folder / 'callsite.incomplete.json').read_text('utf8'))
                self.assertFalse(meta['partial_binary_saved'])
                if name == 'initialization_source_sha':
                    self.assertEqual(scenario.opens, 0)
                    self.assertEqual(scenario.memory.reads, [])
                else:
                    self.assertTrue(scenario.memory.closed)
                    self.assertEqual(scenario.memory.body_reads, [] if name == 'wrong_root_full_pin'
                                     else [(reader.BODY_BEGIN, 4000), (reader.BODY_BEGIN, 4000)])
                RESULTS.append({'case': name, 'status': 'PASS', 'error': meta['error'],
                    'opens': scenario.opens, 'body_reads': scenario.memory.body_reads,
                    'binary_saved': False, 'budget': meta.get('budget')})


if __name__ == '__main__':
    unittest.main()
