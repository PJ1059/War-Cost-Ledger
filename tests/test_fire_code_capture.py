"""Fixed-window sampler contracts, using owned fake code rather than game memory."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import fire_code_capture as sampler


def fixture():
    result = bytearray(sampler.TOTAL_BYTES)
    offset = 0
    for _, start, length in sampler.RANGES:
        for rva, expected in sampler.PINS:
            if start <= rva < start + length:
                raw = bytes.fromhex(expected)
                result[offset + rva - start:offset + rva - start + len(raw)] = raw
        offset += length
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
        offset = 0
        for _, start, size in sampler.RANGES:
            if self.base + start <= address < self.base + start + size:
                index = offset + address - self.base - start
                result = self.raw[index:index + length]
                if self.corrupt:
                    result = bytes(length)
                return result[:-1] if self.short else result
            offset += size
        raise AssertionError('Read outside approved windows')


class CaptureTests(unittest.TestCase):
    def test_six_bounded_reads_and_no_extra_pin_reads(self):
        memory, waits = Memory(), []
        binary, meta = sampler.capture(memory, memory.identity, sleep=waits.append)
        self.assertEqual(binary, fixture())
        self.assertEqual([length for _, length in memory.reads], [4096, 832, 4096, 4096, 4096, 2112])
        self.assertEqual(len(memory.queries), 6)
        self.assertEqual(sum(n for _, n in memory.reads), 19328)
        self.assertEqual(waits, [0.1] * 5)
        self.assertEqual(len(meta['pins']), 18)
        self.assertTrue(meta['complete'])
        self.assertFalse(meta['atomic'])
        self.assertFalse(meta['native_written'])
        self.assertFalse(meta['native_called'])
        self.assertEqual(meta['binary_sha256'], hashlib.sha256(binary).hexdigest())

    def test_short_read_stops_without_more_windows(self):
        memory = Memory(); memory.short = True
        with self.assertRaisesRegex(ValueError, 'SHORT_READ'):
            sampler.capture(memory, memory.identity, sleep=lambda _: None)
        self.assertEqual(len(memory.reads), 1)

    def test_corrupt_pin_rejects_material(self):
        memory = Memory(); memory.corrupt = True
        with self.assertRaisesRegex(ValueError, 'PIN_MISMATCH'):
            sampler.capture(memory, memory.identity, sleep=lambda _: None)

    def test_guard_nonexecute_private_uncommitted_reject_before_read(self):
        for field, value in (('protection', 0x120), ('protection', 0x04),
                             ('kind', 0x20000), ('state', 0x2000),
                             ('region_size', 0x1000)):
            with self.subTest(field=field, value=value):
                memory = Memory(); setattr(memory, field, value)
                with self.assertRaisesRegex(ValueError, 'REGION_UNREADABLE'):
                    sampler.capture(memory, memory.identity, sleep=lambda _: None)
                self.assertEqual(memory.reads, [])

    def test_invalid_image_rejects_without_query(self):
        for field, value in (('game_base', 0x123), ('game_size', 0x1000)):
            memory = Memory(); identity = dict(memory.identity, **{field: value})
            with self.assertRaisesRegex(ValueError, 'MODULE_INVALID'):
                sampler.capture(memory, identity, sleep=lambda _: None)
            self.assertEqual(memory.queries, [])

    def test_successful_cache_revalidated_and_reused(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder, memory = Path(temporary), Memory()
            binary, meta = sampler.capture(memory, memory.identity, sleep=lambda _: None)
            binary_path, json_path = folder / 'capture.bin', folder / 'capture.json'
            binary_path.write_bytes(binary)
            json_path.write_text(json.dumps(meta), encoding='utf8')
            sampler.write_status(folder, {'status': 'complete', 'binary_path': str(binary_path),
                                         'json_path': str(json_path)})
            self.assertIsNotNone(sampler.saved_complete(folder))
            binary_path.write_bytes(binary + b'X')
            self.assertIsNone(sampler.saved_complete(folder))

    def test_bad_hash_wrong_revision_and_incomplete_not_reused(self):
        for field, value in (('binary_sha256', '0' * 64), ('source_revision', 'other'),
                             ('complete', False), ('dll_sha', 'another build')):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                folder, memory = Path(temporary), Memory()
                binary, meta = sampler.capture(memory, memory.identity, sleep=lambda _: None)
                bin_path, meta_path = folder / 'capture.bin', folder / 'capture.json'
                meta[field] = value
                bin_path.write_bytes(binary)
                meta_path.write_text(json.dumps(meta), encoding='utf8')
                sampler.write_status(folder, {'status': 'complete', 'binary_path': str(bin_path),
                                             'json_path': str(meta_path)})
                self.assertIsNone(sampler.saved_complete(folder))

    def external_context(self, memory):
        class Context:
            def __enter__(self):
                return memory
            def __exit__(self, *args):
                return False
        return SimpleNamespace(Process=lambda pid: Context(), resolve_game=lambda pid: memory.identity)

    def test_waits_beyond_120_seconds_then_saves_once(self):
        memory, delays = Memory(), []
        pids = [()] * 76 + [(111,), (111,)]
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            with patch.dict(sys.modules, {'fire_code_windows': self.external_context(memory)}), \
                    patch('probe_session.game_processes', side_effect=pids), \
                    patch.object(sampler, 'fingerprints', return_value={}), \
                    patch.object(sampler, 'validate_identity'), \
                    patch.object(sampler.time, 'sleep', side_effect=delays.append):
                result = sampler.wait_and_capture(folder)
            self.assertEqual(result['status'], 'complete')
            self.assertEqual(delays.count(2), 76)
            self.assertEqual(len(memory.reads), 6)
            self.assertEqual(sampler.saved_complete(folder), result)
            self.assertEqual(len(list(folder.glob('*.bin'))), 1)

    def test_no_more_than_two_failed_capture_attempts(self):
        memory = Memory(); memory.short = True
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            with patch.dict(sys.modules, {'fire_code_windows': self.external_context(memory)}), \
                    patch('probe_session.game_processes', return_value=(111,)), \
                    patch.object(sampler, 'fingerprints', return_value={}), \
                    patch.object(sampler, 'validate_identity'), \
                    patch.object(sampler.time, 'sleep'):
                with self.assertRaisesRegex(ValueError, 'SHORT_READ'):
                    sampler.wait_and_capture(folder)
            self.assertEqual(len(memory.reads), 2)
            status = json.loads((folder / 'status.json').read_text(encoding='utf8'))
            self.assertEqual(status['attempts'], 2)
            self.assertEqual(status['status'], 'incomplete')
            self.assertIsNone(sampler.saved_complete(folder))


if __name__ == '__main__':
    unittest.main()
