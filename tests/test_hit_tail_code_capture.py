import importlib.util
import copy
import json
from pathlib import Path
import runpy
import struct
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('hit_tail', ROOT / 'tools/hit-tail-code-capture.py')
tail = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tail)
ship_reader = runpy.run_path(str(ROOT / 'tools/career-cache-capture.py'))


class Memory:
    def __init__(self):
        self.reads = []; self.bad_pin = False; self.short = False; self.protect = 0x20
    def query(self, address):
        return {'base': 0x180000000, 'size': 0x4744000, 'state': 0x1000,
                'type': 0x1000000, 'protect': self.protect}
    def read(self, address, length):
        self.reads.append((address - 0x180000000, length))
        for rva, raw in tail.PINS:
            if address == 0x180000000 + rva:
                return bytes(length) if self.bad_pin else raw
        return bytes(length - (1 if self.short else 0))


class ShipMemory(Memory):
    """Use the real Ship reader's fixed global/pointer/state layout."""
    context = 0x1011ED90A0
    def __init__(self, state=3, after=3, bad_pin=False):
        super().__init__()
        self.state, self.after, self.state_reads = state, after, 0
        self.bad_pin = bad_pin
        self.closed = False
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
        if address == 0x180000000 + ship_reader['STATE_GLOBAL']:
            self.reads.append((address - 0x180000000, length))
            return struct.pack('<Q', self.context)
        if address == self.context + ship_reader['STATE_OFFSET']:
            self.reads.append((address - 0x180000000, length))
            value = self.state if self.state_reads == 0 else self.after
            self.state_reads += 1
            return struct.pack('<I', value)
        return super().read(address, length)


class Scenario:
    identity = {'game_base': 0x180000000, 'game_size': tail.IMAGE_SIZE,
                'game_path': 'fixture/game.dll', 'exe_path': 'fixture/helldivers2.exe'}
    def __init__(self, stages, after=3, bad_pin=False):
        self.stages, self.stage = stages, 0
        self.after, self.bad_pin = after, bad_pin
        self.sleeps, self.memories = [], []
        self.enumerations, self.resolutions, self.fingerprint_calls = 0, 0, 0
    def processes(self):
        self.enumerations += 1
        return () if self.stages[self.stage] is None else (61204,)
    def resolve(self, pid):
        assert pid == 61204
        self.resolutions += 1
        if self.stages[self.stage] == 'loading':
            raise FileNotFoundError('game.dll not yet loaded')
        return dict(self.identity)
    def fingerprint(self):
        self.fingerprint_calls += 1
        # The production function returns disk path/size/time stamps, not SHA strings.
        return {'exe_sha': ('fixture/exe', 1, 2), 'dll_sha': ('fixture/dll', 3, 4)}
    def open(self, pid):
        assert pid == 61204
        memory = ShipMemory(self.stages[self.stage], self.after, self.bad_pin)
        self.memories.append(memory)
        return memory
    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.stage += 1
        if self.stage >= len(self.stages):
            raise AssertionError('Unexpected retry/wait after final fixture stage')
    def dependencies(self):
        return {'fingerprints': self.fingerprint,
                'validate_identity': lambda identity, stamps: None,
                'game_processes': self.processes, 'resolve_game': self.resolve,
                'Process': self.open, 'ship_state': ship_reader['ship_state']}
    def code_reads(self):
        expected = {r for r, _ in tail.PINS} | {tail.TAIL}
        return [(rva, size) for m in self.memories for rva, size in m.reads if rva in expected]


class HitTailTests(unittest.TestCase):
    identity = {'game_base': 0x180000000, 'game_size': 0x4744000}
    def test_fixed_total(self):
        memory = Memory(); data, chunks = tail.capture(memory, self.identity)
        self.assertEqual(len(data), 778)
        self.assertEqual(memory.reads, [(r, len(b)) for r, b in tail.PINS] + [(tail.TAIL, 768)])
        self.assertEqual(len(chunks), 3)
    def test_pin_mismatch_before_tail(self):
        memory = Memory(); memory.bad_pin = True
        with self.assertRaisesRegex(ValueError, 'PIN_MISMATCH'):
            tail.capture(memory, self.identity)
        self.assertEqual(len(memory.reads), 1)
    def test_unreadable_no_read(self):
        memory = Memory(); memory.protect = 0x120
        with self.assertRaisesRegex(ValueError, 'CODE_UNREADABLE'):
            tail.capture(memory, self.identity)
        self.assertEqual(memory.reads, [])
    def test_short_tail_rejected(self):
        memory = Memory(); memory.short = True
        with self.assertRaisesRegex(ValueError, 'SHORT_READ'):
            tail.capture(memory, self.identity)

    def test_wait_longer_than_120_seconds_then_one_capture(self):
        scenario = Scenario([None] * 66 + ['loading', 2, 4, 5, 3])
        with tempfile.TemporaryDirectory() as folder:
            status = tail.run(folder, True, scenario.dependencies(), scenario.sleep)
            self.assertEqual(status['status'], 'complete')
            meta = json.loads(Path(status['json_path']).read_text('utf8'))
            self.assertGreater(sum(scenario.sleeps), 120)
            self.assertTrue(all(s == 2 for s in scenario.sleeps))
            self.assertEqual(scenario.code_reads(), [(r, len(b)) for r, b in tail.PINS] + [(tail.TAIL, 768)])
            self.assertEqual(meta['ship_wait_polls'], 3)
            self.assertEqual(meta['ship_wait_bytes_read'], 36)
            self.assertEqual(meta['ship_wait_read_calls'], 6)
            self.assertEqual(meta['code_bytes_read'], 778)
            self.assertEqual(meta['code_reads'], 3)
            self.assertEqual(meta['ship_bytes_read'], 24)
            self.assertTrue(all(m.closed for m in scenario.memories))
            self.assertFalse(meta['native_written'])
            self.assertFalse(meta['native_called'])

    def test_non_ship_stages_have_zero_code_reads(self):
        scenario = Scenario([2, 4, 5, 3])
        with tempfile.TemporaryDirectory() as folder:
            tail.run(folder, True, scenario.dependencies(), scenario.sleep)
            for memory in scenario.memories[:3]:
                self.assertEqual(len(memory.reads), 2)
                self.assertEqual(sum(n for _, n in memory.reads), 12)
                self.assertEqual([r for r, _ in memory.reads if r in {r for r, _ in tail.PINS} | {tail.TAIL}], [])

    def test_default_once_does_not_wait_for_mission(self):
        scenario = Scenario([4])
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, 'EXPECTS_SHIP'):
                tail.run(folder, False, scenario.dependencies(), scenario.sleep)
            self.assertEqual(scenario.sleeps, [])
            self.assertEqual(scenario.code_reads(), [])
            self.assertEqual(json.loads((Path(folder) / 'status.json').read_text())['status'], 'failed')

    def test_failure_is_retained_and_never_retried(self):
        scenario = Scenario([3], bad_pin=True)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, 'PIN_MISMATCH'):
                tail.run(folder, True, scenario.dependencies(), scenario.sleep)
            self.assertEqual(scenario.sleeps, [])
            self.assertEqual(len(scenario.memories), 1)
            self.assertEqual(scenario.code_reads(), [(tail.PINS[0][0], 5)])
            status = json.loads((Path(folder) / 'status.json').read_text())
            self.assertEqual(status['status'], 'failed')
            self.assertTrue(status['capture_attempted'])
            self.assertFalse(status['complete'])
            self.assertTrue(Path(status['json_path']).name.endswith('.incomplete.json'))
            self.assertEqual(list(Path(folder).glob('*.bin')), [])

    def test_ship_changes_after_capture_not_saved_as_success(self):
        scenario = Scenario([3], after=4)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, 'SHIP_CHANGED'):
                tail.run(folder, True, scenario.dependencies(), scenario.sleep)
            self.assertEqual(len(scenario.code_reads()), 3)
            self.assertEqual(scenario.sleeps, [])
            self.assertEqual(list(Path(folder).glob('*.bin')), [])

    def test_verified_cache_calls_no_process_or_fingerprint_api(self):
        scenario = Scenario([3])
        with tempfile.TemporaryDirectory() as folder:
            status = tail.run(folder, False, scenario.dependencies(), scenario.sleep)
            with patch.object(tail, 'load_dependencies', side_effect=AssertionError('must not load live adapter')):
                cached = tail.run(folder, True)
            self.assertTrue(cached['cached'])
            self.assertEqual(cached['json_path'], status['json_path'])
            self.assertEqual(scenario.enumerations, 2)
            self.assertEqual(scenario.fingerprint_calls, 1)

    def test_cache_sha_pin_and_ranges_rechecked(self):
        scenario = Scenario([3])
        with tempfile.TemporaryDirectory() as folder:
            status = tail.run(folder, False, scenario.dependencies(), scenario.sleep)
            report, binary = Path(status['json_path']), Path(status['binary_path'])
            original_meta, original_binary = json.loads(report.read_text('utf8')), binary.read_bytes()
            binary.write_bytes(original_binary[:-1] + b'\x01')
            self.assertIsNone(tail.saved_complete(folder))
            binary.write_bytes(original_binary)
            changed = copy.deepcopy(original_meta); changed['chunks'][-1]['rva'] += 1
            report.write_text(json.dumps(changed), 'utf8')
            self.assertIsNone(tail.saved_complete(folder))
            report.write_text(json.dumps(original_meta), 'utf8')
            bad_pin = b'\x00' + original_binary[1:]
            binary.write_bytes(bad_pin)
            changed = copy.deepcopy(original_meta)
            changed['sha256'] = tail.hashlib.sha256(bad_pin).hexdigest()
            report.write_text(json.dumps(changed), 'utf8')
            cached_status = {**status, 'sha256': changed['sha256']}
            tail.write_status(Path(folder), cached_status)
            self.assertIsNone(tail.saved_complete(folder))

    def test_initial_module_missing_waits_without_memory_reads(self):
        scenario = Scenario(['loading', 'loading', 3])
        with tempfile.TemporaryDirectory() as folder:
            tail.run(folder, True, scenario.dependencies(), scenario.sleep)
            self.assertEqual(scenario.sleeps, [2, 2])
            self.assertEqual(len(scenario.memories), 1)


if __name__ == '__main__':
    unittest.main()
