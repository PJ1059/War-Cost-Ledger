"""One focused owned fixed-record hint group; does not run the v1 suite."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_hit_world_update_contact_callsite_capture as previous

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'owned_contact_callsite_hint', ROOT / 'tools/hit-world-update-contact-callsite-hint-capture.py')
hint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hint)
RESULTS = []


class Memory(previous.Memory):
    def __init__(self, wrong_record=False, changed_after=False):
        super().__init__()
        self.begin, self.end = hint.DECL_BEGIN, hint.DECL_END
        self.wrong_record, self.changed_after = wrong_record, changed_after
        self.hint_reads = 0

    def read(self, address, size):
        rva = address - self.game
        if rva in (hint.HINT_RVA, hint.UNWIND_RVA):
            self.reads.append((address, size))
            if self.clock:
                self.clock.value += self.delay
            if rva == hint.UNWIND_RVA:
                assert size == 4
                return bytes((1, 0, 0, 0))  # Fresh synthetic v1/no-chain header.
            assert size == 12
            self.hint_reads += 1
            raw = bytearray(hint.HINT_BYTES)
            if self.wrong_record or (self.changed_after and self.hint_reads > 1):
                raw[0] ^= 1
            return bytes(raw)
        if (hint.v1.frozen.EXCEPTION_RVA <= rva <
                hint.v1.frozen.EXCEPTION_RVA + hint.v1.frozen.EXCEPTION_SIZE):
            raise AssertionError('Fixed hint must not search any other exception record')
        return super().read(address, size)


class Scenario(previous.fixture.Scenario):
    def __init__(self, **options):
        super().__init__()
        self.memory = Memory(**options)


class HintTests(unittest.TestCase):
    def test_fixed_hint_fresh_record_post_record_and_partial_source_contract(self):
        self.assertEqual(hint.HINT_INDEX, 43772)
        self.assertEqual(hint.HINT_RVA, hint.v1.frozen.EXCEPTION_RVA + 43772 * 12)
        self.assertEqual(hint.HINT_BYTES.hex(), '5450ab00d662ab003c6e4a02')
        self.assertEqual((hint.DECL_BEGIN, hint.DECL_END, hint.UNWIND_RVA),
                         (0xAB5054, 0xAB62D6, 0x24A6E3C))
        self.assertEqual(hashlib.sha256(hint.HINT.read_bytes()).hexdigest(), hint.HINT_SHA)
        for name, options, reason in (
                ('correct_hint', {}, None),
                ('wrong_fresh_record', {'wrong_record': True}, 'FRESH_RECORD_CHANGED'),
                ('changed_post_record', {'changed_after': True}, 'RECORD_CHANGED_DURING_CAPTURE'),
                ('partial_source_sha', {}, 'PARTIAL_SOURCE_CHANGED')):
            with self.subTest(case=name), tempfile.TemporaryDirectory() as parent:
                scenario, folder = Scenario(**options), Path(parent) / 'capture'
                if name == 'partial_source_sha':
                    with patch.object(hint, 'HINT_SHA', '0' * 64):
                        with self.assertRaisesRegex(ValueError, reason):
                            hint.run(folder, scenario.dependencies(), previous.fixture.Clock())
                elif reason:
                    with self.assertRaisesRegex(ValueError, reason):
                        hint.run(folder, scenario.dependencies(), previous.fixture.Clock())
                else:
                    result = hint.run(folder, scenario.dependencies(), previous.fixture.Clock())
                    meta = json.loads(Path(result['json_path']).read_text('utf8'))
                    raw = Path(result['binary_path']).read_bytes()
                    self.assertTrue(meta['complete'])
                    self.assertFalse(meta['binary_search_performed'])
                    self.assertTrue(meta['record_hint_only'])
                    self.assertTrue(meta['fixed_record_verified_before_after'])
                    self.assertEqual(meta['exception_records'], [{
                        'index': hint.HINT_INDEX, 'rva': hint.HINT_RVA,
                        'raw_hex': hint.HINT_BYTES.hex(), 'begin': hint.DECL_BEGIN,
                        'end': hint.DECL_END, 'unwind_rva': hint.UNWIND_RVA,
                        'selection': 'fresh_fixed_record_from_partial_location_hint'}])
                    self.assertEqual(meta['fixed_record_after']['raw_hex'], hint.HINT_BYTES.hex())
                    self.assertEqual(scenario.memory.hint_reads, 2)
                    self.assertEqual([(a - scenario.memory.game, n) for a, n in scenario.memory.reads
                                      if a == scenario.memory.game + hint.UNWIND_RVA],
                                     [(hint.UNWIND_RVA, 4)])
                    self.assertEqual(scenario.memory.payload_reads,
                                     [(hint.DECL_BEGIN, 64), (hint.v1.TARGET_RVA - 32, 53)])
                    self.assertEqual(len(raw), 117)
                    self.assertEqual(raw[meta['binary_pin_offset']:meta['binary_pin_offset'] + 12].hex(),
                                     hint.v1.PIN_HEX)
                    self.assertEqual(meta['budget']['read_calls'], len(scenario.memory.reads))
                    self.assertEqual(meta['budget']['query_calls'], len(scenario.memory.queries))
                    self.assertEqual(meta['budget']['bytes_requested'], sum(n for _, n in scenario.memory.reads))
                    self.assertLessEqual(meta['budget']['read_calls'], 32)
                    self.assertLessEqual(meta['budget']['query_calls'], 32)
                    self.assertLessEqual(meta['budget']['bytes_requested'], 24576)
                    for key in ('caller_entry_proven', 'global_context_argument_proven',
                                'instruction_boundary_verified', 'registered_callback_proven',
                                'native_called', 'native_written'):
                        self.assertFalse(meta[key])
                    self.assertTrue(scenario.memory.closed)
                    RESULTS.append({'case': name, 'status': 'PASS', 'ranges': meta['ranges'],
                        'code_bytes': len(raw), 'budget': meta['budget'],
                        'hint_record_reads': scenario.memory.hint_reads,
                        'unwind_reads': [{'rva': hint.UNWIND_RVA, 'length': 4}],
                        'binary_search_performed': meta['binary_search_performed']})
                    continue
                self.assertEqual(list(folder.glob('*.bin')), [])
                meta = json.loads((folder / 'callsite.incomplete.json').read_text('utf8'))
                self.assertFalse(meta['complete'])
                self.assertFalse(meta['partial_binary_saved'])
                if name == 'partial_source_sha':
                    self.assertEqual(scenario.opens, 0)
                    self.assertEqual(scenario.memory.reads, [])
                else:
                    self.assertTrue(scenario.memory.closed)
                    self.assertEqual(scenario.memory.hint_reads,
                                     1 if name == 'wrong_fresh_record' else 2)
                    self.assertEqual(scenario.memory.payload_reads,
                                     [] if name == 'wrong_fresh_record'
                                     else [(hint.DECL_BEGIN, 64), (hint.v1.TARGET_RVA - 32, 53)])
                RESULTS.append({'case': name, 'status': 'PASS', 'error': meta['error'],
                    'binary_saved': False, 'partial_binary_saved': False,
                    'opens': scenario.opens, 'hint_record_reads': scenario.memory.hint_reads,
                    'payload_reads': scenario.memory.payload_reads,
                    'budget': meta.get('budget')})


if __name__ == '__main__':
    unittest.main()
