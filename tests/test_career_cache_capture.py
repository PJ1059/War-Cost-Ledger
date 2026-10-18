"""Owned synthetic buffers only; do not read the actual game or user account."""
import importlib.util
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('career_capture_fixture', ROOT / 'tools/career-cache-capture.py')
sampler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sampler)


class Memory:
    identity = {'game_base': 0x180000000, 'game_size': sampler.IMAGE_SIZE}
    pointer = 0x200000000
    game_context = 0x300000000

    def __init__(self):
        self.reads, self.queries = [], []
        self.code = bytearray(sampler.CODE_BYTES)
        for rva, expected in sampler.PINS:
            at = rva - sampler.CODE_RVA
            self.code[at:at + len(bytes.fromhex(expected))] = bytes.fromhex(expected)
        self.head = bytearray(sampler.HEAD_BYTES)
        struct.pack_into('<I', self.head, 0x14, 351849)
        struct.pack_into('<I', self.head, 0x18, 4633)  # Deliberate tempting wrong field.
        self.protect, self.short, self.swap = 4, False, False
        self.states = [3]

    def query(self, address):
        self.queries.append(address)
        if address == self.pointer or address == self.game_context + sampler.STATE_OFFSET:
            return {'base': address, 'size': 4096, 'state': 0x1000, 'type': 0x20000, 'protect': self.protect}
        return {'base': self.identity['game_base'], 'size': sampler.IMAGE_SIZE,
                'state': 0x1000, 'type': 0x1000000, 'protect': 0x20}

    def read(self, address, length):
        self.reads.append((address, length))
        if address == self.identity['game_base'] + sampler.STATE_GLOBAL:
            raw = struct.pack('<Q', self.game_context)
        elif address == self.game_context + sampler.STATE_OFFSET:
            value = self.states.pop(0) if len(self.states) > 1 else self.states[0]
            raw = struct.pack('<I', value)
        elif address == self.identity['game_base'] + sampler.CODE_RVA:
            raw = bytes(self.code)
        elif address == self.identity['game_base'] + sampler.GLOBAL_RVA:
            raw = struct.pack('<Q', self.pointer + (8 if self.swap and len(self.reads) > 2 else 0))
        elif address == self.pointer:
            raw = bytes(self.head)
        else:
            raise AssertionError('outside fixed plan')
        assert len(raw) == length
        return raw[:-1] if self.short else raw


class Tests(unittest.TestCase):
    def test_exact_five_read_plan_does_not_guess_deaths(self):
        memory, sleeps = Memory(), []
        raw, meta = sampler.capture(memory, memory.identity, sleep=sleeps.append)
        self.assertEqual(len(raw), 464)
        self.assertEqual(len(memory.reads), 5)
        self.assertEqual(sleeps, [.1] * 4)
        self.assertEqual(meta['candidate_career_kills_before'], 351849)
        self.assertTrue(meta['cache_head_stable'])
        for key in ('career_kd_ready', 'death_field_verified', 'backend_ready_verified',
                    'persistent_account_identity_verified', 'native_called', 'native_written', 'account_modified'):
            self.assertFalse(meta[key])
        self.assertNotIn('deaths', meta)
        self.assertFalse(meta['function_extent_verified'])

    def test_changed_pin_stops_before_pointer_or_cache(self):
        memory = Memory(); memory.code[0x4a] ^= 1
        with self.assertRaisesRegex(ValueError, 'PIN_CHANGED'):
            sampler.capture(memory, memory.identity, sleep=lambda _: None)
        self.assertEqual(len(memory.reads), 1)

    def test_null_pointer_is_not_zero_career(self):
        memory = Memory(); memory.pointer = 0
        with self.assertRaisesRegex(ValueError, 'NOT_READY'):
            sampler.capture(memory, memory.identity, sleep=lambda _: None)
        self.assertEqual(len(memory.reads), 2)

    def test_pointer_replaced_stops_before_second_cache_read(self):
        memory = Memory(); memory.swap = True
        with self.assertRaisesRegex(ValueError, 'POINTER_CHANGED'):
            sampler.capture(memory, memory.identity, sleep=lambda _: None)
        self.assertEqual(len(memory.reads), 4)

    def test_unreadable_heap_and_short_io_stop(self):
        for mode in ('guard', 'short'):
            memory = Memory()
            if mode == 'guard':memory.protect = 0x104
            else:memory.short = True
            with self.assertRaisesRegex(ValueError, 'UNREADABLE|SHORT_READ'):
                sampler.capture(memory, memory.identity, sleep=lambda _: None)

    def test_slow_previous_io_stops_before_next(self):
        memory = Memory(); ticks = iter([0, 0, 0, 3])
        with self.assertRaisesRegex(ValueError, 'BUDGET'):
            sampler.capture(memory, memory.identity, sleep=lambda _: None, clock=lambda: next(ticks))
        self.assertEqual(len(memory.reads), 1)

    def test_saved_cache_validates_bytes_and_does_not_reopen_game(self):
        memory = Memory()
        raw, meta = sampler.capture(memory, memory.identity, sleep=lambda _: None)
        meta['ship_state_verified'] = True
        meta['ship_context'] = {'state': 3}
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary);binary_path, meta_path = folder / 'sample.bin', folder / 'sample.json'
            binary_path.write_bytes(raw);meta_path.write_text(json.dumps(meta), 'utf8')
            status = {'status': 'complete', 'json_path': str(meta_path), 'binary_path': str(binary_path)}
            (folder / 'status.json').write_text(json.dumps(status), 'utf8')
            with patch.dict(sys.modules, {'fire_code_windows': None, 'probe_session': None}):
                self.assertEqual(sampler.once(None, folder), status)
            binary_path.write_bytes(raw[:-1])
            self.assertIsNone(sampler.saved_complete(folder))

    def test_disk_check_does_not_enumerate_processes(self):
        with patch.object(sampler, 'fingerprints', return_value={}), \
                patch.dict(sys.modules, {'fire_code_windows': None, 'probe_session': None}), \
                patch.object(sys, 'argv', ['career-cache-capture.py', '--check']), \
                patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual(sampler.main(), 0)
        self.assertFalse(json.loads(output.getvalue())['career_kd_ready'])

    def test_ship_gate_excludes_loading_title_and_mission_without_reading_career(self):
        memory = Memory();memory.states = [2, 5, 4, 3, 5, 3, 3]
        contexts = {'fire_code_windows': SimpleNamespace(Process=lambda _: Context(memory),
                resolve_game=lambda _: dict(memory.identity)),
            'probe_session': SimpleNamespace(game_processes=lambda: (123,))}
        waits, updates = [], []
        with patch.dict(sys.modules, contexts), patch.object(sampler.helpers, 'validate_identity'):
            result = sampler.wait_for_ship(123, {}, on_wait=updates.append, sleep=waits.append)
        self.assertEqual(waits, [2] * 6)
        self.assertEqual(result['ship_stable_samples'], 2)
        self.assertEqual(result['career_reads_while_waiting'], 0)
        self.assertEqual([item['last_native_state'] for item in updates],
                         ['TitleScreen', 'PrepareShip', 'Mission', 'Ship', 'PrepareShip', 'Ship', 'Ship'])
        self.assertEqual(len(memory.reads), 14)
        self.assertEqual(result['ship_wait_read_calls'], 14)
        self.assertEqual(result['ship_wait_bytes_requested'], 84)
        self.assertTrue(all(n in (8, 4) for _, n in memory.reads))
        self.assertTrue(all(at != memory.identity['game_base'] + sampler.GLOBAL_RVA for at, _ in memory.reads))

    def test_direct_capture_rejects_mission_before_career_reads(self):
        memory = Memory();memory.states = [4]
        contexts = {'fire_code_windows': SimpleNamespace(Process=lambda _: Context(memory),
                resolve_game=lambda _: dict(memory.identity)),
            'probe_session': SimpleNamespace(game_processes=lambda: (123,))}
        with tempfile.TemporaryDirectory() as temporary, patch.dict(sys.modules, contexts), \
                patch.object(sampler, 'fingerprints', return_value={}), \
                patch.object(sampler.helpers, 'validate_identity'):
            with self.assertRaisesRegex(ValueError, 'NOT_ON_SHIP'):
                sampler.once(123, Path(temporary))
            self.assertFalse(list(Path(temporary).glob('*.bin')))
        self.assertEqual(len(memory.reads), 2)

    def test_ship_exit_during_capture_discards_output(self):
        memory = Memory();memory.states = [3, 4]
        contexts = {'fire_code_windows': SimpleNamespace(Process=lambda _: Context(memory),
                resolve_game=lambda _: dict(memory.identity)),
            'probe_session': SimpleNamespace(game_processes=lambda: (123,))}
        original_capture = sampler.capture
        with tempfile.TemporaryDirectory() as temporary, patch.dict(sys.modules, contexts), \
                patch.object(sampler, 'fingerprints', return_value={}), \
                patch.object(sampler.helpers, 'validate_identity'), \
                patch.object(sampler, 'capture', side_effect=lambda p, i: original_capture(p, i, sleep=lambda _: None)):
            with self.assertRaisesRegex(ValueError, 'SHIP_CHANGED'):
                sampler.once(123, Path(temporary))
            self.assertFalse(list(Path(temporary).glob('*.bin')))

    def test_actual_once_saves_only_diagnostic_and_cached_result_avoids_new_reads(self):
        memory = Memory()
        contexts = {'fire_code_windows': SimpleNamespace(Process=lambda _: Context(memory),
                resolve_game=lambda _: dict(memory.identity)),
            'probe_session': SimpleNamespace(game_processes=lambda: (123,))}
        original_capture = sampler.capture
        with tempfile.TemporaryDirectory() as temporary, patch.dict(sys.modules, contexts), \
                patch.object(sampler, 'fingerprints', return_value={}), \
                patch.object(sampler.helpers, 'validate_identity'), \
                patch.object(sampler, 'capture', side_effect=lambda p, i: original_capture(p, i, sleep=lambda _: None)):
            result = sampler.once(123, Path(temporary))
            meta = json.loads(Path(result['json_path']).read_text('utf8'))
            self.assertEqual(len(memory.reads), 9)  # 5 fixed + 4 Ship rechecks, 488B.
            self.assertTrue(meta['ship_state_verified'])
            self.assertFalse(meta['career_kd_ready'])
            self.assertEqual(sampler.once(None, Path(temporary)), result)
            self.assertEqual(len(memory.reads), 9)


class Context:
    def __init__(self, memory):self.memory = memory
    def __enter__(self):return self.memory
    def __exit__(self, *_):pass


if __name__ == '__main__':
    unittest.main()
