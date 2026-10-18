"""Offline contract checks; these fixtures never open a game process."""
import copy
import importlib.util
import json
from pathlib import Path
import runpy
import struct
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'hit_impact', ROOT / 'tools/hit-impact-code-capture.py')
impact = importlib.util.module_from_spec(spec)
spec.loader.exec_module(impact)
ship_reader = runpy.run_path(str(ROOT / 'tools/career-cache-capture.py'))
BASE = 0x180000000


class Memory:
    """Exact real layout for Ship; fixed code windows only for the fixture."""
    context = 0x1011ED90A0

    def __init__(self, state=3, after=3, *, bad_pin=False,
                 short_rva=None, guard_rva=None, region_end=None):
        self.state, self.after, self.state_reads = state, after, 0
        self.bad_pin, self.short_rva = bad_pin, short_rva
        self.guard_rva, self.region_end = guard_rva, region_end
        self.reads, self.closed = [], False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True

    def query(self, address):
        if self.context <= address < self.context + 0x100000:
            return {'base': self.context, 'size': 0x100000, 'state': 0x1000,
                    'type': 0x20000, 'protect': 4}
        rva = address - BASE
        return {'base': BASE,
                'size': self.region_end if self.region_end is not None else impact.PROFILE['IMAGE_SIZE'],
                'state': 0x1000, 'type': 0x1000000,
                'protect': 0x120 if rva == self.guard_rva else 0x20}

    def read(self, address, length):
        rva = address - BASE
        self.reads.append((rva, length))
        if rva == ship_reader['STATE_GLOBAL']:
            raw = struct.pack('<Q', self.context)
        elif address == self.context + ship_reader['STATE_OFFSET']:
            value = self.state if self.state_reads == 0 else self.after
            self.state_reads += 1
            raw = struct.pack('<I', value)
        elif rva == impact.PIN_RVA:
            raw = bytes(length) if self.bad_pin else impact.PIN
        elif rva == impact.BODY_RVA:
            raw = bytes(length)
        else:
            raise AssertionError('Fixture does not allow any other read')
        return raw[:-1] if rva == self.short_rva else raw

    def code_reads(self):
        return [(rva, length) for rva, length in self.reads
                if rva in (impact.PIN_RVA, impact.BODY_RVA)]


class Scenario:
    identity = {'game_base': BASE, 'game_size': impact.PROFILE['IMAGE_SIZE'],
                'game_path': 'fixture/game.dll', 'exe_path': 'fixture/helldivers2.exe'}

    def __init__(self, **memory_options):
        self.memory = Memory(**memory_options)
        self.enumerations = self.resolutions = self.fingerprint_calls = 0
        self.opens = 0

    def processes(self):
        self.enumerations += 1
        return (61204,)

    def resolve(self, pid):
        self.assert_pid(pid)
        self.resolutions += 1
        return dict(self.identity)

    @staticmethod
    def assert_pid(pid):
        if pid != 61204:
            raise AssertionError('Unexpected fixture PID')

    def fingerprint(self):
        self.fingerprint_calls += 1
        # Real fingerprints() validates hashes and returns disk stat stamps.
        return {'exe_sha': ('fixture/exe', 1, 2),
                'dll_sha': ('fixture/dll', 3, 4)}

    def open(self, pid):
        self.assert_pid(pid)
        self.opens += 1
        return self.memory

    def dependencies(self):
        return {'fingerprints': self.fingerprint,
                'validate_identity': lambda identity, stamps: None,
                'game_processes': self.processes, 'resolve_game': self.resolve,
                'Process': self.open, 'ship_state': ship_reader['ship_state']}


class HitImpactTests(unittest.TestCase):
    def test_fixed_profile_copies_without_mutating_tail_capture(self):
        self.assertEqual(impact.TOTAL, 1829)
        self.assertEqual(impact.PIN_RVA + 5 + struct.unpack('<i', impact.PIN[1:])[0],
                         impact.BODY_RVA)
        original = impact.PROFILE['capture'].__globals__
        self.assertEqual(original['PINS'], impact.PROFILE['PINS'])
        self.assertEqual(original['TAIL'], 0x13AE300)
        self.assertEqual(original['SIZE'], 768)
        self.assertIsNot(impact.capture.__globals__, original)

    def test_ship_success_is_1853_bytes_six_reads_once(self):
        scenario = Scenario()
        with tempfile.TemporaryDirectory() as folder:
            status = impact.run(folder, scenario.dependencies())
            meta = json.loads(Path(status['json_path']).read_text('utf8'))
            self.assertEqual(meta['code_bytes_read'], 1829)
            self.assertEqual(meta['code_reads'], 2)
            self.assertEqual(meta['ship_bytes_read'], 24)
            self.assertEqual(meta['ship_reads'], 4)
            self.assertEqual(len(scenario.memory.reads), 6)
            self.assertEqual(sum(n for _, n in scenario.memory.reads), 1853)
            self.assertEqual(scenario.memory.code_reads(),
                             [(impact.PIN_RVA, 5), (impact.BODY_RVA, 1824)])
            self.assertEqual(scenario.opens, 1)
            self.assertEqual(scenario.enumerations, 2)
            self.assertEqual(scenario.resolutions, 2)
            self.assertTrue(scenario.memory.closed)
            self.assertEqual(meta['ship_before'], meta['ship_after'])
            self.assertEqual(meta['source_tail_sha256'], impact.SOURCE_SHA)
            self.assertFalse(meta['classification_ready'])
            self.assertFalse(meta['complete_function'])
            self.assertFalse(meta['complete_stream'])
            self.assertFalse(meta['native_written'])
            self.assertFalse(meta['native_called'])
            self.assertEqual(len(Path(status['binary_path']).read_bytes()), 1829)

    def test_non_ship_has_no_code_reads(self):
        for state in (2, 4, 5):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as folder:
                scenario = Scenario(state=state)
                with self.assertRaisesRegex(ValueError, 'EXPECTS_SHIP'):
                    impact.run(folder, scenario.dependencies())
                self.assertEqual(scenario.memory.code_reads(), [])
                self.assertEqual(len(scenario.memory.reads), 2)
                self.assertEqual(sum(n for _, n in scenario.memory.reads), 12)
                self.assertEqual(scenario.opens, 1)
                self.assertTrue(scenario.memory.closed)
                failure = json.loads((Path(folder) / 'status.json').read_text('utf8'))
                self.assertFalse(failure['capture_attempted'])
                self.assertFalse(failure['partial_binary_saved'])
                self.assertEqual(list(Path(folder).glob('*.bin')), [])

    def test_pin_failure_never_reads_body_or_retries(self):
        scenario = Scenario(bad_pin=True)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, 'PIN_MISMATCH'):
                impact.run(folder, scenario.dependencies())
            self.assertEqual(scenario.memory.code_reads(), [(impact.PIN_RVA, 5)])
            self.assertEqual(scenario.opens, 1)
            status = json.loads((Path(folder) / 'status.json').read_text('utf8'))
            self.assertEqual(status['status'], 'failed')
            self.assertTrue(Path(status['json_path']).name.endswith('.incomplete.json'))
            self.assertEqual(list(Path(folder).glob('*.bin')), [])

    def test_guard_rejects_before_guarded_read(self):
        for guarded in (impact.PIN_RVA, impact.BODY_RVA):
            with self.subTest(guarded=guarded):
                memory = Memory(guard_rva=guarded)
                with self.assertRaisesRegex(ValueError, 'CODE_UNREADABLE'):
                    impact.capture(memory, Scenario.identity)
                expected = [] if guarded == impact.PIN_RVA else [(impact.PIN_RVA, 5)]
                self.assertEqual(memory.code_reads(), expected)

    def test_short_reads_rejected(self):
        for short in (impact.PIN_RVA, impact.BODY_RVA):
            with self.subTest(short=short):
                memory = Memory(short_rva=short)
                with self.assertRaisesRegex(ValueError, 'SHORT_READ'):
                    impact.capture(memory, Scenario.identity)
                if short == impact.PIN_RVA:
                    self.assertEqual(memory.code_reads(), [(impact.PIN_RVA, 5)])

    def test_body_range_must_fit_whole_page_region(self):
        memory = Memory(region_end=impact.BODY_RVA + impact.BODY_LENGTH - 1)
        with self.assertRaisesRegex(ValueError, 'CODE_UNREADABLE'):
            impact.capture(memory, Scenario.identity)
        self.assertEqual(memory.code_reads(), [(impact.PIN_RVA, 5)])

    def test_ship_change_discards_complete_code_buffer(self):
        scenario = Scenario(after=4)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, 'SHIP_CHANGED'):
                impact.run(folder, scenario.dependencies())
            self.assertEqual(len(scenario.memory.reads), 6)
            self.assertTrue(scenario.memory.closed)
            self.assertEqual(list(Path(folder).glob('*.bin')), [])

    def test_verified_cache_uses_zero_dependencies(self):
        scenario = Scenario()
        with tempfile.TemporaryDirectory() as folder:
            status = impact.run(folder, scenario.dependencies())
            calls = (scenario.enumerations, scenario.resolutions,
                     scenario.fingerprint_calls, scenario.opens, len(scenario.memory.reads))
            with patch.dict(impact.PROFILE, {'load_dependencies': lambda: self.fail('No adapter load')}):
                cached = impact.run(folder)
            self.assertTrue(cached['cached'])
            self.assertEqual(cached['json_path'], status['json_path'])
            self.assertEqual(calls, (scenario.enumerations, scenario.resolutions,
                                    scenario.fingerprint_calls, scenario.opens,
                                    len(scenario.memory.reads)))

    def test_cache_sha_pin_and_chunks_are_rechecked(self):
        scenario = Scenario()
        with tempfile.TemporaryDirectory() as folder:
            status = impact.run(folder, scenario.dependencies())
            report, binary = Path(status['json_path']), Path(status['binary_path'])
            original_meta = json.loads(report.read_text('utf8'))
            original_raw = binary.read_bytes()
            binary.write_bytes(original_raw[:-1] + b'\x01')
            self.assertIsNone(impact.saved_complete(folder))
            binary.write_bytes(original_raw)
            changed = copy.deepcopy(original_meta)
            changed['chunks'][1]['rva'] += 1
            report.write_text(json.dumps(changed), 'utf8')
            self.assertIsNone(impact.saved_complete(folder))
            report.write_text(json.dumps(original_meta), 'utf8')
            bad_pin = b'\0' + original_raw[1:]
            binary.write_bytes(bad_pin)
            changed = copy.deepcopy(original_meta)
            changed['sha256'] = impact.hashlib.sha256(bad_pin).hexdigest()
            report.write_text(json.dumps(changed), 'utf8')
            impact.PROFILE['write_status'](Path(folder), {**status, 'sha256': changed['sha256']})
            self.assertIsNone(impact.saved_complete(folder))


if __name__ == '__main__':
    unittest.main()
