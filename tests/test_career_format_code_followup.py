"""Owned Ship/PE fixtures: code capture only, never reads Career values."""
import copy
import importlib.util
import json
from pathlib import Path
import runpy
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))
import test_recon_chat_code_capture as prior
import test_hit_consumer_followup as impact_prior
import recon_chat_code_capture as old_recon
import fire_code_capture as old_fire

OLD_RECON = (old_recon.REVISION, old_recon.TARGET_RVA, old_recon.TARGET_PIN)
OLD_FIRE = (old_fire.REVISION, old_fire.RANGES, old_fire.PINS, old_fire.TOTAL_BYTES)
OLD_IMPACT = (impact_prior.c.REVISION, impact_prior.c.session.reader.TARGET_RVA,
              impact_prior.c.session.reader.TARGET_PIN, impact_prior.c.session.reader.capture,
              impact_prior.c.session.reader.window_capture)
spec = importlib.util.spec_from_file_location(
    'career_format_test', ROOT / 'tools/career-format-code-followup.py')
career = importlib.util.module_from_spec(spec)
spec.loader.exec_module(career)
worker, reader = career.worker, career.worker.session.reader
ship_reader = runpy.run_path(str(ROOT / 'tools/career-cache-capture.py'))


class Memory(prior.Memory):
    context = 0x1011ED90A0

    def __init__(self, state=3, after=3, bad_pin=False):
        previous = prior.sampler
        try:
            prior.sampler = reader
            super().__init__()
        finally:
            prior.sampler = previous
        self.native_state, self.after, self.states = state, after, 0
        self.corrupt, self.closed = bad_pin, False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True

    def query(self, address):
        if self.context <= address < self.context + 0x100000:
            return {'base': self.context, 'size': 0x100000, 'state': 0x1000,
                    'type': 0x20000, 'protect': 4}
        return super().query(address)

    def read(self, address, length):
        rva = address - self.base
        if rva == ship_reader['STATE_GLOBAL']:
            self.reads.append((address, length))
            return struct.pack('<Q', self.context)
        if address == self.context + ship_reader['STATE_OFFSET']:
            self.reads.append((address, length))
            value = self.native_state if not self.states else self.after
            self.states += 1
            return struct.pack('<I', value)
        if rva == 0x12A7A69:
            raise AssertionError('The old impact caller must never be read')
        previous = prior.sampler
        try:
            prior.sampler = reader
            return super().read(address, length)
        finally:
            prior.sampler = previous

    def code_reads(self):
        intervals = self.code_intervals or [(self.begin, self.end)]
        return [(address - self.base, length) for address, length in self.reads
                if any(begin <= address - self.base < end for begin, end in intervals)]


class Scenario:
    def __init__(self, stages=(3,), **options):
        self.stages, self.stage, self.options = stages, 0, options
        self.memories, self.sleeps = [], []
        self.fingerprint_calls = 0

    def processes(self):
        return () if self.stages[self.stage] is None else (61204,)

    def resolve(self, _pid):
        return dict(prior.Memory.identity)

    def fingerprint(self):
        self.fingerprint_calls += 1
        return {}

    def open(self, _pid):
        memory = Memory(state=self.stages[self.stage], **self.options)
        self.memories.append(memory)
        return memory

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.stage += 1
        if self.stage >= len(self.stages):
            raise AssertionError('Unexpected retry after the final fixture stage')

    def dependencies(self):
        return {'fingerprints': self.fingerprint,
                'validate_identity': lambda *_: None, 'game_processes': self.processes,
                'resolve_game': self.resolve, 'Process': self.open,
                'ship_state': ship_reader['ship_state']}

    def run(self, parent, wait=False):
        return worker.run(Path(parent) / 'new', wait, self.dependencies(), self.sleep)


class CareerFormatTests(unittest.TestCase):
    def assert_profiles_unchanged(self):
        self.assertEqual(OLD_RECON, (old_recon.REVISION, old_recon.TARGET_RVA, old_recon.TARGET_PIN))
        self.assertEqual(OLD_FIRE, (old_fire.REVISION, old_fire.RANGES, old_fire.PINS, old_fire.TOTAL_BYTES))
        self.assertEqual(OLD_IMPACT, (impact_prior.c.REVISION, impact_prior.c.session.reader.TARGET_RVA,
                                   impact_prior.c.session.reader.TARGET_PIN,
                                   impact_prior.c.session.reader.capture,
                                   impact_prior.c.session.reader.window_capture))
        self.assertIsNot(worker, impact_prior.c)
        self.assertIsNot(reader, impact_prior.c.session.reader)
        self.assertIs(reader.capture, worker.body_capture)
        self.assertIs(reader.window_capture, worker.window_factory)
        self.assertIs(worker.verify_saved, career.verify_saved)

    def test_named_native_pin_in_declared_body_without_impact_prefix(self):
        scenario = Scenario()
        with tempfile.TemporaryDirectory() as parent:
            status = scenario.run(parent)
            meta = json.loads(Path(status['json_path']).read_text('utf8'))
            raw = Path(status['binary_path']).read_bytes()
            career.verify_saved(meta, raw)
            self.assertEqual(reader.TARGET_RVA, 0x143C950)
            self.assertEqual(reader.TARGET_PIN, '40534883ec20488bd94881c110010000')
            self.assertEqual(raw[0x50:0x60], bytes.fromhex(career.TARGET_PIN))
            self.assertEqual(meta['target_rva'], 0x143C950)
            self.assertEqual(meta['source_revision'], career.REVISION)
            self.assertEqual(meta['bytes_written'], 256)
            self.assertNotIn('caller_rva', meta)
            self.assertNotIn('candidate_body', meta)
            self.assertEqual(meta['pins'], [{'rva': 0x143C950,
                                            'range': 'chat_history_consumer', 'matched': True}])
            memory = scenario.memories[-1]
            self.assertEqual(memory.code_reads(), [(memory.begin, 256)])
            self.assertEqual(len(memory.reads), meta['budget']['read_calls'] + 4)
            self.assertEqual(sum(n for _, n in memory.reads), meta['budget']['bytes_requested'] + 24)
            self.assertLessEqual(meta['budget']['read_calls'], 32)
            self.assertLessEqual(meta['budget']['bytes_requested'], 8192)
            self.assertTrue(memory.closed)
            self.assertFalse(meta['classification_ready'])
            self.assertFalse(meta['native_written'])
            self.assertFalse(meta['native_called'])
            self.assert_profiles_unchanged()

    def test_non_ship_once_performs_only_twelve_byte_state_read(self):
        for state in (2, 4, 5):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as parent:
                scenario = Scenario((state,))
                with patch.object(reader, 'capture', side_effect=AssertionError('no code capture')):
                    with self.assertRaisesRegex(ValueError, 'EXPECTS_SHIP'):
                        scenario.run(parent)
                self.assertEqual(scenario.memories[0].code_reads(), [])
                self.assertEqual(len(scenario.memories[0].reads), 2)
                self.assertEqual(sum(n for _, n in scenario.memories[0].reads), 12)
                self.assertEqual(scenario.sleeps, [])

    def test_wait_stages_have_no_code_then_one_capture(self):
        scenario = Scenario([None] * 66 + [2, 4, 5, 3])
        with tempfile.TemporaryDirectory() as parent:
            result = scenario.run(parent, True)
            self.assertGreater(sum(scenario.sleeps), 120)
            self.assertTrue(all(n == 2 for n in scenario.sleeps))
            self.assertEqual(result['waiting_code_reads'], 0)
            self.assertEqual(result['ship_wait_polls'], 4)  # Includes successful readiness check.
            self.assertEqual(result['ship_wait_bytes_read'], 48)
            self.assertEqual(result['ship_wait_read_calls'], 8)
            for memory in scenario.memories[:-1]:
                self.assertEqual(memory.code_reads(), [])
                self.assertEqual(sum(n for _, n in memory.reads), 12)
            self.assertEqual(len(scenario.memories[-1].code_reads()), 1)
            self.assertTrue(all(m.closed for m in scenario.memories))

    def test_same_body_pin_failure_never_saved_or_retried(self):
        scenario = Scenario(bad_pin=True)
        with tempfile.TemporaryDirectory() as parent:
            with self.assertRaisesRegex(ValueError, 'PIN_MISMATCH'):
                scenario.run(parent)
            self.assertEqual(len(scenario.memories), 1)
            self.assertEqual(scenario.sleeps, [])
            self.assertEqual(len(scenario.memories[0].code_reads()), 1)
            self.assertFalse(list(Path(parent).rglob('*.bin')))

    def test_declared_boundaries_and_non_numeric_semantics(self):
        memory = Memory()
        nodes = memory.configure_chain(1)
        raw, meta = reader.capture(memory, memory.identity)
        meta['classification_ready'] = False
        career.verify_saved(meta, raw)
        self.assertEqual(memory.code_reads(), [(nodes[1][0], 128), (nodes[0][0], 256)])
        self.assertFalse(meta['logical_function_complete'])
        self.assertFalse(meta['all_sibling_fragments_captured'])
        self.assertTrue(meta['diagnostic_only'])
        self.assertEqual(meta['chat_messages_read'], 0)
        self.assertEqual(meta['recon_events_emitted'], 0)
        self.assertNotIn('career_kills', meta)
        self.assertNotIn('career_deaths', meta)
        changed = copy.deepcopy(meta)
        changed['function_begin'] += 1
        with self.assertRaises(ValueError):
            career.verify_saved(changed, raw)
        memory = Memory()
        memory.end = memory.begin + 4097
        with self.assertRaisesRegex(ValueError, 'FUNCTION_TOO_LARGE'):
            reader.capture(memory, memory.identity)
        self.assertEqual(memory.code_reads(), [])

    def test_ship_change_discards_code(self):
        scenario = Scenario(after=4)
        with tempfile.TemporaryDirectory() as parent:
            with self.assertRaisesRegex(ValueError, 'SHIP_CHANGED'):
                scenario.run(parent)
            self.assertFalse(list(Path(parent).rglob('*.bin')))
            self.assertTrue(scenario.memories[0].closed)

    def test_existing_folder_refuses_before_dependencies(self):
        with tempfile.TemporaryDirectory() as parent:
            with patch.dict(worker.session.tail, {'load_dependencies': lambda: self.fail('no adapter load')}):
                with self.assertRaisesRegex(ValueError, 'OUTPUT_EXISTS'):
                    worker.run(parent, True)
            self.assertEqual(list(Path(parent).iterdir()), [])
        self.assert_profiles_unchanged()


if __name__ == '__main__':
    unittest.main()
