"""Owned-fixture checks; never enumerate or read a live game process."""
import re
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
spec = importlib.util.spec_from_file_location('status_code_capture', ROOT / 'tools/status-code-capture.py')
sampler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sampler)


def fixture():
    result = bytearray(sampler.TOTAL_BYTES)
    for window in sampler.range_plan():
        for rva, expected in sampler.PINS:
            raw = bytes.fromhex(expected)
            if window['rva'] <= rva and rva + len(raw) <= window['rva'] + window['length']:
                offset = window['binary_offset'] + rva - window['rva']
                result[offset:offset + len(raw)] = raw
    return bytes(result)


class Memory:
    base = 0x180000000
    identity = {'game_base': base, 'game_size': 0x4000000,
                'game_path': 'owned-fixture.dll', 'exe_path': 'owned-fixture.exe'}

    def __init__(self):
        self.raw, self.reads, self.queries = fixture(), [], []
        self.protection, self.kind, self.state = 0x20, 0x1000000, 0x1000
        self.short, self.corrupt, self.region_size = False, False, 0x4000000

    def query(self, address):
        self.queries.append(address)
        return {'base': self.base, 'size': self.region_size, 'protect': self.protection,
                'type': self.kind, 'state': self.state}

    def read(self, address, length):
        self.reads.append((address, length))
        for window in sampler.range_plan():
            if self.base + window['rva'] <= address < self.base + window['rva'] + window['length']:
                relative = address - self.base - window['rva']
                assert length == min(4096, window['length'] - relative)
                start = window['binary_offset'] + relative
                result = self.raw[start:start + length]
                if self.corrupt:
                    result = bytes(length)
                return result[:-1] if self.short else result
        raise AssertionError('Read outside the six fixed approved windows')


def cache(folder, changes=None):
    memory = Memory()
    binary, meta = sampler.capture(memory, memory.identity, sleep=lambda _: None)
    if changes:
        meta.update(changes)
    binary_path, json_path = folder / 'capture.bin', folder / 'capture.json'
    binary_path.write_bytes(binary)
    json_path.write_text(json.dumps(meta), encoding='utf8')
    status = {'status': 'complete', 'binary_path': str(binary_path), 'json_path': str(json_path)}
    sampler.write_status(folder, status)
    return status, binary_path


class CaptureTests(unittest.TestCase):
    def external_context(self, memory):
        class Context:
            def __enter__(self):
                return memory
            def __exit__(self, *args):
                return False
        return SimpleNamespace(Process=lambda pid: Context(), resolve_game=lambda pid: dict(memory.identity))

    def test_seven_bounded_reads_and_correct_status_metadata(self):
        memory, delays = Memory(), []
        binary, meta = sampler.capture(memory, memory.identity, sleep=delays.append)
        self.assertEqual([(address - memory.base, n) for address, n in memory.reads],
                         [(0x6994F0, 2384), (0x699E40, 4096), (0x69AE40, 128),
                          (0x69AEC0, 816), (0x69B1F0, 1792), (0x129F170, 304), (0x129F2A0, 768)])
        self.assertEqual(len(memory.queries), 7)
        self.assertEqual(sum(n for _, n in memory.reads), 10288)
        self.assertEqual(delays, [0.1] * 6)
        self.assertEqual(binary, fixture())
        self.assertEqual(len(meta['pins']), 1)
        self.assertEqual([window['pin_count'] for window in meta['ranges']], [0, 0, 0, 0, 1, 0])
        self.assertEqual(meta['binary_sha256'], hashlib.sha256(binary).hexdigest())
        self.assertTrue(meta['code_only'])
        self.assertTrue(meta['complete'])
        for key in ('atomic', 'native_written', 'native_called', 'ship_state_verified'):
            self.assertFalse(meta[key])
        self.assertNotIn('asset_score', json.dumps(meta).lower())
        self.assertFalse(meta['layout_ready'])
        self.assertFalse(meta['success_count_available'])

    def test_short_read_and_pin_mismatch_are_rejected(self):
        memory = Memory(); memory.short = True
        with self.assertRaisesRegex(ValueError, 'STATUS_CODE_SHORT_READ'):
            sampler.capture(memory, memory.identity, sleep=lambda _: None)
        self.assertEqual(len(memory.reads), 1)
        memory = Memory(); memory.corrupt = True
        with self.assertRaisesRegex(ValueError, 'STATUS_CODE_PIN_MISMATCH'):
            sampler.capture(memory, memory.identity, sleep=lambda _: None)
        self.assertEqual(len(memory.reads), 7)
        with self.assertRaisesRegex(ValueError, 'LENGTH_MISMATCH'):
            sampler.verify_pins(fixture() + b'x')

    def test_regions_and_image_reject_before_code_read(self):
        for field, value in (('protection', 0x120), ('protection', 0x04),
                             ('kind', 0x20000), ('state', 0x2000), ('region_size', 0x1000)):
            with self.subTest(field=field, value=value):
                memory = Memory(); setattr(memory, field, value)
                with self.assertRaisesRegex(ValueError, 'REGION_UNREADABLE'):
                    sampler.capture(memory, memory.identity, sleep=lambda _: None)
                self.assertEqual(memory.reads, [])
        for field, value in (('game_base', 0x123), ('game_size', 0x1000)):
            memory = Memory()
            with self.assertRaisesRegex(ValueError, 'MODULE_INVALID'):
                sampler.capture(memory, dict(memory.identity, **{field: value}), sleep=lambda _: None)
            self.assertEqual(memory.queries, [])

    def test_cache_reused_without_process_adapter_or_fingerprints(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            expected, _ = cache(folder)
            with patch.object(sampler, 'fingerprints', side_effect=AssertionError('Disk build reread')), \
                    patch.dict(sys.modules, {'fire_code_windows': None, 'probe_session': None}):
                self.assertEqual(sampler.wait_and_capture(folder), expected)
            self.assertEqual(len(list(folder.glob('*.bin'))), 1)

    def test_cache_corruption_revision_plan_and_hash_rejected(self):
        changes = ({'complete': False}, {'source_revision': 'fire_death_code_v1'},
                   {'dll_sha': 'wrong'}, {'binary_sha256': '0' * 64}, {'ranges': []})
        for changed in changes:
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as temporary:
                folder = Path(temporary)
                cache(folder, changed)
                self.assertIsNone(sampler.saved_complete(folder))
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            _, binary = cache(folder)
            binary.write_bytes(fixture() + b'x')
            self.assertIsNone(sampler.saved_complete(folder))

    def test_waits_beyond_120_seconds_then_stops_at_one_success(self):
        memory, delays = Memory(), []
        game = SimpleNamespace(game_processes=unittest.mock.Mock(side_effect=[()] * 76 + [(111,), (111,)]))
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            with patch.dict(sys.modules, {'fire_code_windows': self.external_context(memory), 'probe_session': game}), \
                    patch.object(sampler, 'fingerprints', return_value={}), \
                    patch.object(sampler, 'validate_identity'), \
                    patch.object(sampler.time, 'sleep', side_effect=delays.append):
                result = sampler.wait_and_capture(folder)
            self.assertEqual(result['status'], 'complete')
            self.assertEqual(delays.count(2), 76)
            self.assertIn(20, delays)
            self.assertEqual(len(memory.reads), 7)
            self.assertEqual(sampler.saved_complete(folder), result)
            self.assertEqual(len(list(folder.glob('*.bin'))), 1)
            meta = json.loads(Path(result['json_path']).read_text(encoding='utf8'))
            self.assertEqual(meta['attempts'], 1)
            self.assertEqual(meta['bytes_written'], 10288)

    def test_only_two_failed_capture_attempts(self):
        memory = Memory(); memory.short = True
        game = SimpleNamespace(game_processes=lambda: (111,))
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            with patch.dict(sys.modules, {'fire_code_windows': self.external_context(memory), 'probe_session': game}), \
                    patch.object(sampler, 'fingerprints', return_value={}), \
                    patch.object(sampler, 'validate_identity'), \
                    patch.object(sampler.time, 'sleep'):
                with self.assertRaisesRegex(ValueError, 'SHORT_READ'):
                    sampler.wait_and_capture(folder)
            self.assertEqual(len(memory.reads), 2)
            status = json.loads((folder / 'status.json').read_text(encoding='utf8'))
            self.assertEqual(status['attempts'], 2)
            self.assertEqual(status['status'], 'incomplete')
            self.assertEqual(list(folder.glob('*.bin')), [])

    def test_check_only_calls_disk_fingerprints(self):
        with patch.object(sampler, 'fingerprints') as fingerprint, \
                patch.object(sampler, 'wait_and_capture', side_effect=AssertionError('Memory capture')), \
                patch.dict(sys.modules, {'fire_code_windows': None, 'probe_session': None}), \
                patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual(sampler.main(['--check']), 0)
        fingerprint.assert_called_once_with()
        meta = json.loads(output.getvalue())
        self.assertEqual(meta['code_reads'], 7)
        self.assertEqual(meta['bytes_planned'], 10288)
        self.assertEqual(meta['pins'], 1)
        self.assertFalse(meta['layout_ready'])
        self.assertFalse(meta['success_count_available'])

    def test_identity_and_disk_fingerprint_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            exe, dll = folder / 'bin/helldivers2.exe', folder / 'data/game/game.dll'
            exe.parent.mkdir(parents=True); dll.parent.mkdir(parents=True)
            exe.write_bytes(b'owned exe'); dll.write_bytes(b'owned dll')
            hashes = {'exe_sha': sampler.sha256(exe), 'dll_sha': sampler.sha256(dll)}
            with patch.object(sampler, 'GAME', folder), patch.object(sampler, 'FINGERPRINT', hashes):
                stamps = sampler.fingerprints()
                identity = dict(Memory.identity, exe_path=str(exe), game_path=str(dll))
                sampler.validate_identity(identity, stamps)
                with self.assertRaisesRegex(ValueError, 'PATH_MISMATCH'):
                    sampler.validate_identity(dict(identity, exe_path=str(folder / 'wrong.exe')), stamps)
                dll.write_bytes(b'changed dll size')
                with self.assertRaisesRegex(ValueError, 'BUILD_CHANGED'):
                    sampler.validate_identity(identity, stamps)
                with self.assertRaisesRegex(ValueError, 'BUILD_MISMATCH'):
                    sampler.fingerprints()

    def test_pins_and_six_windows_match_actual_runtime_and_local_reader(self):
        native = Path('external/HD2Runtime'
                      'SkyeShade-HD2Runtime-dcd996d/domains/event_natives.lua')
        if not native.is_file():
            self.skipTest('Local Runtime native source is unavailable')
        match = re.search(r'\["status"\]=\{\["rva"\]=(\d+),\["prologue"\]="([0-9a-f]+)"',
                          native.read_text(encoding='utf8'))
        self.assertIsNotNone(match)
        self.assertEqual(sampler.PINS, ((int(match.group(1)), match.group(2)),))
        reader = (ROOT / 'src/native-status-reader.lua').read_text(encoding='utf8')
        windows = re.findall(r"label = '([^']+)', rva = (0x[0-9A-Fa-f]+), size = (0x[0-9A-Fa-f]+)", reader)
        self.assertEqual(sampler.RANGES, tuple((label, int(rva, 16), int(n, 16)) for label, rva, n in windows))
        self.assertEqual(sampler.TOTAL_BYTES, 10288)
        self.assertEqual(sampler.REVISION, 'status_layout_code_v1')


if __name__ == '__main__':
    unittest.main()
