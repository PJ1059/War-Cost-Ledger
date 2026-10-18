"""Only new finite table owned reader and incremental switch CFG cases."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import test_hit_world_update_r14_suffix_capture as previous

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'owned_world_switch_table_reader', ROOT / 'tools/hit-world-update-switch-table-capture.py')
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)
cfg_spec = importlib.util.spec_from_file_location(
    'owned_world_switch_table_cfg', ROOT / 'tools/analyze-hit-world-update-r14.py')
analysis = importlib.util.module_from_spec(cfg_spec)
cfg_spec.loader.exec_module(analysis)
TABLE_PATTERN = struct.pack('<6I', *([0xAB60BC] * 6))
Clock = previous.Clock
RESULTS = []


class Memory(previous.Memory):
    def __init__(self, wrong_suffix=False, changed_table=False):
        super().__init__()
        self.wrong_suffix, self.changed_table = wrong_suffix, changed_table
        self.table_reads = []

    def read(self, address, size):
        rva = address - self.game
        if rva in (reader.suffix_private.SUFFIX_BEGIN, reader.TABLE_RVA):
            self.reads.append((address, size))
            if self.clock:
                self.clock.value += self.delay
            if rva == reader.suffix_private.SUFFIX_BEGIN:
                assert size == 738
                self.suffix_reads.append((rva, size))
                raw = bytearray(reader.SUFFIX_PIN)
                if self.wrong_suffix:
                    raw[0] ^= 1
            else:
                assert size == 24
                self.table_reads.append((rva, size))
                raw = bytearray(TABLE_PATTERN)
                if self.changed_table and len(self.table_reads) > 1:
                    raw[0] ^= 1
            return bytes(raw)
        return super().read(address, size)


class Scenario(previous.Scenario):
    def __init__(self, **options):
        super().__init__()
        self.memory = Memory(**options)


class SwitchTableTests(unittest.TestCase):
    def test_reader_table24_source_pins_post_change_and_packet_sha(self):
        self.assertEqual((reader.TABLE_RVA, reader.TABLE_BYTES), (0xAB7664, 24))
        self.assertEqual(hashlib.sha256(reader.SUFFIX_PIN).hexdigest(), reader.SUFFIX_BIN_SHA)
        for name, options, reason in (
                ('reader_table_success', {}, None),
                ('wrong_known_suffix_pin', {'wrong_suffix': True}, 'FRESH_FULL_SOURCE_PIN_CHANGED'),
                ('changed_table_post', {'changed_table': True}, 'TABLE_OR_SOURCE_CHANGED_DURING_CAPTURE'),
                ('suffix_source_json_sha', {}, 'COMPLETE_SUFFIX_PACKET_CHANGED')):
            with self.subTest(case=name), tempfile.TemporaryDirectory() as parent:
                scenario, folder = Scenario(**options), Path(parent) / 'capture'
                if name == 'suffix_source_json_sha':
                    with patch.object(reader, 'SUFFIX_JSON_SHA', '0' * 64):
                        with self.assertRaisesRegex(ValueError, reason):
                            reader.run(folder, scenario.dependencies(), Clock())
                elif reason:
                    with self.assertRaisesRegex(ValueError, reason):
                        reader.run(folder, scenario.dependencies(), Clock())
                else:
                    status = reader.run(folder, scenario.dependencies(), Clock())
                    meta = json.loads(Path(status['json_path']).read_text('utf8'))
                    self.assertEqual(Path(status['binary_path']).read_bytes(), TABLE_PATTERN)
                    self.assertEqual(meta['ranges'], [{'name': 'six_state_switch_DWORD_RVA_table',
                        'module': 'game', 'rva': reader.TABLE_RVA, 'length': 24, 'binary_offset': 0}])
                    self.assertEqual(scenario.memory.table_reads, [(reader.TABLE_RVA, 24)] * 2)
                    self.assertEqual(scenario.memory.suffix_reads,
                                     [(reader.suffix_private.SUFFIX_BEGIN, 738)] * 2)
                    self.assertEqual(scenario.memory.known_prefix_reads,
                                     [(reader.suffix_private.prefix_private.BODY_BEGIN, 4000)] * 2)
                    self.assertEqual(scenario.memory.root_reads,
                                     [(reader.suffix_private.prefix_private.root_private.ROOT_BEGIN, 84)] * 2)
                    self.assertEqual(scenario.memory.hint_reads, 2)
                    self.assertEqual(len(scenario.memory.unwind_reads), 7)
                    self.assertTrue(meta['full_source_pins_before_after_match'])
                    self.assertTrue(meta['table_before_after_match'])
                    self.assertTrue(meta['fixed_record_verified_before_after'])
                    self.assertFalse(meta['table_targets_followed'])
                    self.assertFalse(meta['mapping_verified'])
                    self.assertEqual(meta['table_target_rvas'], [0xAB60BC] * 6)
                    self.assertEqual((meta['code_bytes'], meta['data_bytes']), (0, 24))
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
                        'suffix_reads': scenario.memory.suffix_reads,
                        'table_reads': scenario.memory.table_reads, 'budget': meta['budget']})
                    continue
                self.assertEqual(list(folder.glob('*.bin')), [])
                meta = json.loads((folder / 'callsite.incomplete.json').read_text('utf8'))
                self.assertFalse(meta['partial_binary_saved'])
                if name == 'suffix_source_json_sha':
                    self.assertEqual(scenario.opens, 0)
                    self.assertEqual(scenario.memory.reads, [])
                else:
                    self.assertTrue(scenario.memory.closed)
                    self.assertEqual(scenario.memory.table_reads, [] if name == 'wrong_known_suffix_pin'
                                     else [(reader.TABLE_RVA, 24)] * 2)
                RESULTS.append({'case': name, 'status': 'PASS', 'error': meta['error'],
                    'opens': scenario.opens, 'table_reads': scenario.memory.table_reads,
                    'binary_saved': False, 'budget': meta.get('budget')})

    def test_cfg_saved_case_table_and_rejected_outside_item(self):
        suffix = bytearray(b'\x90' * 738)
        base = reader.suffix_private.SUFFIX_BEGIN
        switch_at = analysis.SWITCH_START - base
        case_at, case_end = analysis.CASE_BEGIN - base, analysis.CASE_END - base
        suffix[switch_at:switch_at + len(analysis.SWITCH_SOURCE)] = analysis.SWITCH_SOURCE
        suffix[case_at:case_end] = reader.SUFFIX_PIN[case_at:case_end]
        suffix[case_end] = 0xC3
        targets = [0xAB60BC, 0xAB60CD, 0xAB60DE, 0xAB60EF, 0xAB6100, 0xAB610E]
        invalid_targets = targets.copy()
        invalid_targets[2] = 0xAB6A65
        for name, selected, expected in (
                ('cfg_six_saved_cases', targets, 'PROVED_CAPTURED_CFG_UNDER_X64_CALL_ABI'),
                ('cfg_reject_outside_table_item', invalid_targets, 'WITHHELD_CFG_INCOMPLETE')):
            with self.subTest(case=name):
                table = struct.pack('<6I', *selected)
                result = analysis.analyze_code(reader.ROOT_PIN, previous.previous.BODY_PATTERN,
                                               bytes(suffix), table)
                self.assertEqual(result['status'], expected)
                self.assertEqual(result['incoming_r14_states_at_call'], ['global_context'])
                self.assertFalse(result['finite_switch_table']['targets_dereferenced_from_Game'])
                self.assertEqual(result['finite_switch_table']['target_rvas'], selected)
                self.assertFalse(result['Game_accessed'])
                self.assertFalse(result['native_called'])
                self.assertFalse(result['classification_ready'])
                self.assertTrue(all(not call['callee_followed'] for call in result['calls_not_followed']))
                if name == 'cfg_six_saved_cases':
                    self.assertTrue(result['finite_switch_table']['valid_in_saved_case_instruction_boundaries'])
                    self.assertEqual(result['normal_return_sites'], [analysis.CASE_END])
                    self.assertTrue(result['normal_CFG_closed'])
                    self.assertTrue(result['r14_preserved_on_captured_normal_CFG_to_call'])
                    self.assertTrue(result['contact_argument_source_proven_under_normal_x64_ABI'])
                    self.assertTrue(all([analysis.SWITCH_PC, target] in result['edges']
                                        for target in targets))
                else:
                    self.assertFalse(result['finite_switch_table']['valid_in_saved_case_instruction_boundaries'])
                    self.assertTrue(any(row[0] == 'SWITCH_TABLE_NOT_IN_SAVED_CASE_BOUNDARIES'
                                        for row in result['issues']))
                    self.assertFalse(result['normal_CFG_closed'])
                    self.assertFalse(result['contact_argument_source_proven_under_normal_x64_ABI'])
                    self.assertFalse(any(node['rva'] == 0xAB6A65 for node in result['instructions']))
                RESULTS.append({'case': name, 'status': 'PASS', 'analysis_status': result['status'],
                    'finite_switch_table': result['finite_switch_table'],
                    'incoming_r14_states_at_call': result['incoming_r14_states_at_call'],
                    'normal_return_sites': result['normal_return_sites'],
                    'normal_CFG_closed': result['normal_CFG_closed'],
                    'contact_argument_source_proven_under_normal_x64_ABI':
                        result['contact_argument_source_proven_under_normal_x64_ABI'],
                    'issues': result['issues'], 'decoder': result['decoder']})


if __name__ == '__main__':
    unittest.main()
