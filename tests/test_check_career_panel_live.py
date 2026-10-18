"""Owned saved headers and local Lua VM only; never resolves or opens Game."""
import importlib.util
import json
from pathlib import Path
import re
import struct
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('career_panel_live_owned_test', ROOT / 'tools/check-career-panel-live.py')
target = importlib.util.module_from_spec(spec)
spec.loader.exec_module(target)


class Memory:
    def __init__(self):
        source = (ROOT / 'tests/fixtures/career-parent-headers.lua').read_text('utf8')
        game = int(re.search(r'\bgame=(\d+)', source)[1])
        self.identity = {'game_base': game, 'game_size': target.parent.layout.IMAGE_SIZE,
                         'game_path': 'owned.dll', 'exe_path': 'owned.exe'}
        self.controller = int(re.search(r'\bcontroller=(\d+)', source)[1])
        self.records = [(int(at), bytes.fromhex(raw)) for at, raw in re.findall(r'\{(\d+),"([0-9a-f]+)"\}', source)]
        self.local_user, self.entered, self.calls = 0x300000000, 0, []
        self.records += [(game + 0x347CEF0, struct.pack('<Q', self.local_user)),
                         (self.local_user + 0xB398, bytes.fromhex('0102030405060708')[::-1])]
        self.guard = None

    def read(self, at, size):
        self.calls.append((at, size))
        for start, raw in self.records:
            if start <= at and at + size <= start + len(raw):
                return raw[at - start:at - start + size]
        raise ValueError('OWNED_UNREADABLE')

    def query(self, at):
        return {'base': 65536, 'size': 0x800000000000 - 65536, 'state': 0x1000,
                'type': 0x20000, 'protect': 0x104 if at == self.guard else 4}

    def __enter__(self):
        self.entered += 1;return self

    def __exit__(self, *args):
        return False


def deps(memory, pids=(123,)):
    return {'fingerprints': lambda: {}, 'validate_identity': lambda *_: None,
            'game_processes': lambda: pids, 'resolve_game': lambda _: dict(memory.identity),
            'Process': lambda _: memory}


@unittest.skipUnless(target.LUA.is_file(), 'installed Lua DLL is needed for local owned VM tests')
class Tests(unittest.TestCase):
    def test_real_reader_returns_owned_saved_geometry_and_replay_bytes(self):
        memory = Memory();result = target.capture(memory, memory.identity)
        self.assertEqual(result['status'], 'complete')
        snapshots = [row['snapshot'] for row in result['attempts'] if row.get('snapshot')]
        self.assertTrue(snapshots, result)
        self.assertEqual(snapshots[-1]['position'], [732, -237])
        self.assertEqual([snapshots[-1]['width'], snapshots[-1]['height']], [420, 747])
        self.assertEqual(result['local_peer'], '0102030405060708')
        self.assertLessEqual(result['active_read_calls'], 98)
        self.assertLess(result['active_read_bytes'], 16384)
        self.assertEqual(len(result['read_records']), result['active_read_calls'])
        self.assertTrue(all(len(bytes.fromhex(r['raw_hex'])) == r['length'] for r in result['read_records']))
        self.assertFalse(result['native_written']);self.assertFalse(result['native_called'])
        self.assertFalse(result['Game_lua_injected'])

    def test_callback_failure_is_a_lua_error_not_ctypes_longjmp(self):
        def rejected(at, size):
            raise ValueError('OWNED_CALLBACK_REJECTION')
        out = target.run_reader(rejected, 0x180000000, '0102030405060708', frozen_clock=True)
        self.assertTrue(out['reader_call_ok'])
        self.assertIn('OWNED_CALLBACK_REJECTION', out['reason'])
        self.assertFalse(out['diagnostics']['ready'])

    def test_frozen_clock_replay_matches_saved_geometry_without_any_process(self):
        memory = Memory();raw_peer = '0102030405060708'
        out = target.run_reader(memory.read, memory.identity['game_base'], raw_peer, frozen_clock=True)
        self.assertTrue(out['diagnostics']['ready'], out)
        self.assertEqual(out['clock_policy'], 'frozen_diagnostic_only')
        self.assertEqual(out['snapshot']['width'], 420)

    def test_guard_and_budgets_stop_before_memory_read(self):
        memory = Memory();budget = target.ReadBudget(memory)
        address = memory.identity['game_base'] + 0x347CEF0
        memory.guard = address
        with self.assertRaisesRegex(ValueError, 'UNREADABLE'):
            budget.read(address, 8)
        self.assertEqual(memory.calls, [])
        self.assertEqual(budget.records[0]['address'], address)
        self.assertIn('UNREADABLE', budget.records[0]['error'])
        memory.guard = None
        for attribute, value in [('reads', target.MAX_READS), ('bytes', target.MAX_BYTES)]:
            budget = target.ReadBudget(memory);setattr(budget, attribute, value)
            with self.assertRaisesRegex(ValueError, 'BUDGET'):
                budget.read(address, 8)
        self.assertEqual(memory.calls, [])

    def test_timeout_preserves_failure_and_labels_diagnostic_retry(self):
        memory = Memory()
        calls = []
        def reader(*args, **options):
            calls.append(options.get('frozen_clock', False))
            return {'reason': 'visible' if calls[-1] else 'CAREER_PANEL_TIME_BUDGET',
                    'clock_policy': 'frozen_diagnostic_only' if calls[-1] else 'production_os_clock_external_vm'}
        with patch.object(target, 'run_reader', side_effect=reader):
            result = target.capture(memory, memory.identity)
        self.assertEqual(calls, [False, True])
        self.assertEqual(result['attempts'][0]['reason'], 'CAREER_PANEL_TIME_BUDGET')
        self.assertEqual(result['attempts'][1]['clock_policy'], 'frozen_diagnostic_only')

    def test_no_game_and_wrong_pid_never_open_a_process(self):
        for pids in [(), (124,), (123, 124)]:
            memory = Memory()
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / 'capture'
                out = target.run(path, pid=123, deps=deps(memory, pids))
                self.assertEqual(out['status'], 'failed')
                self.assertIn('EXPECTS_ONE_GAME_PID', out['error'])
                self.assertEqual(json.loads((path / 'status.json').read_text('utf8'))['status'], 'failed')
                self.assertEqual(memory.entered, 0)

    def test_single_attempt_saved_and_existing_output_not_overwritten(self):
        memory = Memory()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'capture'
            out = target.run(path, pid=123, deps=deps(memory))
            self.assertEqual(out['status'], 'complete', out)
            self.assertEqual(memory.entered, 1)
            self.assertTrue((path / 'career-panel-reader.json').is_file())
            with self.assertRaisesRegex(ValueError, 'OUTPUT_EXISTS'):
                target.run(path, pid=123, deps=deps(memory))
            self.assertEqual(memory.entered, 1)


if __name__ == '__main__':
    unittest.main()
