"""Exact owned fixtures and disk-only cached material; never read the game."""
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
spec = importlib.util.spec_from_file_location('status_setter_capture', ROOT / 'tools/status-setter-code-capture.py')
sampler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sampler)


def fixture():
    return b''.join(bytes.fromhex(raw) for _, raw, _ in sampler.PINS) + bytes(sampler.BODY_BYTES)


class Memory:
    identity = {'game_base': 0x180000000, 'game_size': sampler.IMAGE_SIZE,
                'game_path': 'fixture.dll', 'exe_path': 'fixture.exe'}

    def __init__(self):
        self.reads, self.protect = [], 0x20
        self.corrupt_pin, self.short = False, False

    def query(self, address):
        return {'base': self.identity['game_base'], 'size': sampler.IMAGE_SIZE,
                'protect': self.protect, 'state': 0x1000, 'type': 0x1000000}

    def read(self, address, n):
        rva = address - self.identity['game_base']
        self.reads.append((rva, n))
        for pin_rva, raw, _ in sampler.PINS:
            if rva == pin_rva:
                result = bytes(n) if self.corrupt_pin else bytes.fromhex(raw)
                return result[:-1] if self.short else result
        for _, start, length in sampler.RANGES:
            if start <= rva and rva + n <= start + length:
                return bytes(n - 1 if self.short else n)
        raise AssertionError('read outside fixed PIN/body plan')


class Tests(unittest.TestCase):
    def test_fixed_five_reads_pins_before_bodies_and_short_gate(self):
        memory, delays = Memory(), []
        binary, meta = sampler.capture(memory, memory.identity, sleep=delays.append)
        self.assertEqual(memory.reads, [(0x69A76B, 5), (0x69B31F, 5), (0x692240, 4096),
                                        (0x693240, 1024), (0x6992A0, 592)])
        self.assertEqual(delays, [2, .1, .1, .1, .1])
        self.assertEqual(binary, fixture())
        self.assertEqual(meta['bytes_written'], 5722)
        self.assertEqual(meta['process_access_mask'], 0x410)
        self.assertFalse(meta['success_count_available'])
        self.assertFalse(meta['layout_ready'])
        self.assertEqual([r['binary_offset'] for r in meta['ranges']], [10, 5130])

    def test_bad_fresh_pin_stops_before_any_candidate_read(self):
        memory = Memory(); memory.corrupt_pin = True
        with self.assertRaisesRegex(ValueError, 'CALLSITE_CHANGED'):
            sampler.capture(memory, memory.identity, sleep=lambda _: None)
        self.assertEqual(memory.reads, [(0x69A76B, 5)])

    def test_wrong_exact_image_size_and_guard_protection_prevent_read(self):
        memory = Memory()
        for size in (sampler.IMAGE_SIZE - 1, sampler.IMAGE_SIZE + 1):
            with self.assertRaisesRegex(ValueError, 'MODULE_INVALID'):
                sampler.capture(memory, dict(memory.identity, game_size=size), sleep=lambda _: None)
        self.assertEqual(memory.reads, [])
        memory.protect = 0x120
        with self.assertRaisesRegex(ValueError, 'REGION_UNREADABLE'):
            sampler.capture(memory, memory.identity, sleep=lambda _: None)
        self.assertEqual(memory.reads, [])

    def test_short_read_and_bad_total_length_rejected(self):
        memory = Memory(); memory.short = True
        with self.assertRaisesRegex(ValueError, 'SHORT_READ'):
            sampler.capture(memory, memory.identity, sleep=lambda _: None)
        self.assertEqual(len(memory.reads), 1)
        with self.assertRaisesRegex(ValueError, 'LENGTH_MISMATCH'):
            sampler.verify_pins(fixture() + b'x')

    def test_both_callsite_bytes_come_from_real_immutable_parent_capture(self):
        parent = sampler.verify_parent_material()
        self.assertEqual(parent['binary_sha256'], '9e7cac54cb885139fe6de36a307d78af35c237132a09bb038798e351f1e79f8a')
        self.assertEqual(parent['verified_callsite_rvas'], [0x69A76B, 0x69B31F])

    def test_complete_cache_stops_without_importing_process_adapters(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            binary, meta = sampler.capture(Memory(), Memory.identity, sleep=lambda _: None)
            bin_path, json_path = folder / 'fixture.bin', folder / 'fixture.json'
            bin_path.write_bytes(binary); json_path.write_text(json.dumps(meta), encoding='utf8')
            status = {'status': 'complete', 'binary_path': str(bin_path), 'json_path': str(json_path)}
            sampler.helpers.write_status(folder, status)
            with patch.object(sampler.helpers, 'fingerprints', return_value={}), \
                    patch.dict(sys.modules, {'fire_code_windows': None, 'probe_session': None}):
                self.assertEqual(sampler.once(49832, folder), status)
            bin_path.write_bytes(binary + b'x')
            self.assertIsNone(sampler.saved_complete(folder))

    def test_single_failed_attempt_does_not_retry_or_save_code(self):
        memory = Memory(); memory.corrupt_pin = True
        class Context:
            def __enter__(self):
                return memory
            def __exit__(self, *args):
                return False
        adapter = SimpleNamespace(Process=lambda pid: Context(), resolve_game=lambda pid: dict(memory.identity))
        game = SimpleNamespace(game_processes=lambda: (49832,))
        with tempfile.TemporaryDirectory() as temporary:
            with patch.dict(sys.modules, {'fire_code_windows': adapter, 'probe_session': game}), \
                    patch.object(sampler.helpers, 'fingerprints', return_value={}), \
                    patch.object(sampler.helpers, 'validate_identity'), \
                    patch.object(sampler.time, 'sleep'):
                with self.assertRaisesRegex(ValueError, 'CALLSITE_CHANGED'):
                    sampler.once(49832, Path(temporary))
            self.assertEqual(len(memory.reads), 1)
            self.assertEqual(list(Path(temporary).glob('*.bin')), [])

    def test_check_only_disk_proof_without_process_adapter(self):
        with patch.object(sampler.helpers, 'fingerprints') as fingerprints, \
                patch.object(sampler, 'once', side_effect=AssertionError('live read')), \
                patch.dict(sys.modules, {'fire_code_windows': None, 'probe_session': None}), \
                patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual(sampler.main(['--check']), 0)
        fingerprints.assert_called_once_with()
        meta = json.loads(output.getvalue())
        self.assertEqual(meta['bytes_planned'], 5722)
        self.assertEqual(meta['code_reads'], 5)


if __name__ == '__main__':
    unittest.main()
