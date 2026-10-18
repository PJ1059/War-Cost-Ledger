"""Isolated entrypoint fixtures; no game process access or fresh capture."""
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
spec = importlib.util.spec_from_file_location('career_followup_tests_subject', ROOT / 'tools/career-cache-followup.py')
sampler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sampler)


def checks():
    return {}, {'source_revision': sampler.REVISION, 'career_kd_ready': False}


class Tests(unittest.TestCase):
    def test_success_cache_returns_without_enumeration_or_rewrite(self):
        cached = {'status': 'complete', 'career_kd_ready': False}
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(sampler.career, 'saved_complete', return_value=cached), \
                patch.object(sampler, 'local_check', side_effect=AssertionError('fingerprint')), \
                patch.object(sampler, 'waiting_pid', side_effect=AssertionError('enumeration')), \
                patch.object(sampler.career.helpers, 'write_status', side_effect=AssertionError('rewrite')), \
                patch.dict(sys.modules, {'fire_code_windows': None, 'probe_session': None}):
            folder = Path(temporary)
            original = json.dumps(cached).encode()
            (folder / 'status.json').write_bytes(original)
            self.assertEqual(sampler.run(folder), cached)
            self.assertEqual((folder / 'status.json').read_bytes(), original)

    def test_ship_wait_before_once_nonship_progress_does_not_read_cache(self):
        order = []
        def ship(pid, stamps, on_wait):
            for name in ('TitleScreen', 'PrepareShip', 'Mission'):
                order.append(name)
                on_wait({'last_native_state': name, 'career_reads_while_waiting': 0})
                once.assert_not_called()
            return {'ship_state_verified': True, 'last_native_state': 'Ship',
                    'ship_wait_bytes_requested': 48, 'ship_wait_read_calls': 8}
        def once_effect(pid, folder):
            self.assertEqual(pid, 123)
            order.append('once')
            return {'status': 'complete', 'source_revision': sampler.career.REVISION,
                    'career_kd_ready': False, 'game_pid': pid}
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(sampler.career, 'saved_complete', return_value=None), \
                patch.object(sampler, 'local_check', side_effect=checks), \
                patch.object(sampler, 'waiting_pid', return_value=123), \
                patch.object(sampler.career, 'wait_for_ship', side_effect=ship), \
                patch.object(sampler.career, 'once', side_effect=once_effect) as once:
            result = sampler.run(Path(temporary))
        self.assertEqual(order, ['TitleScreen', 'PrepareShip', 'Mission', 'once'])
        once.assert_called_once()
        self.assertEqual(result['ship_wait_bytes_requested'], 48)
        self.assertFalse(result['career_kd_ready'])

    def test_failed_or_unverified_ship_wait_never_calls_once(self):
        for result in (ValueError('CAREER_GAME_EXITED_BEFORE_SHIP'), {'last_native_state': 'Mission'}):
            with self.subTest(result=result), tempfile.TemporaryDirectory() as temporary, \
                    patch.object(sampler.career, 'saved_complete', return_value=None), \
                    patch.object(sampler, 'local_check', side_effect=checks), \
                    patch.object(sampler, 'waiting_pid', return_value=123), \
                    patch.object(sampler.career, 'wait_for_ship',
                        side_effect=result if isinstance(result, Exception) else None,
                        return_value=result), \
                    patch.object(sampler.career, 'once') as once:
                with self.assertRaises(ValueError):
                    sampler.run(Path(temporary))
                once.assert_not_called()

    def test_wait_more_than_120_seconds_and_module_loaded_20_seconds(self):
        periods, state = [], {'polls': 0}
        identity = {'game_base': 0x180000000, 'game_size': sampler.career.IMAGE_SIZE}
        def pids():
            state['polls'] += 1
            return () if state['polls'] <= 70 else (123,)
        adapters = {'probe_session': SimpleNamespace(game_processes=pids),
                    'fire_code_windows': SimpleNamespace(resolve_game=lambda _: dict(identity))}
        with patch.dict(sys.modules, adapters), patch.object(sampler.career.helpers, 'validate_identity'):
            self.assertEqual(sampler.waiting_pid({}, sleep=periods.append), 123)
        self.assertEqual(periods, [2] * 70 + [20])
        # A present game may remain in Mission longer than 120 seconds. Exercise
        # the real inherited Ship wait with isolated state/process adapters.
        class Process:
            def __init__(self, pid):
                self.pid = pid
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
        periods.clear()
        state['polls'] = 0
        def native_state(process, current):
            state['polls'] += 1
            on_ship = state['polls'] > 70
            return {'context': 0x50000, 'state': 3 if on_ship else 4,
                    'name': 'Ship' if on_ship else 'Mission', 'read_calls': 2, 'read_bytes': 12}
        adapters = {'probe_session': SimpleNamespace(game_processes=lambda: (123,)),
                    'fire_code_windows': SimpleNamespace(Process=Process, resolve_game=lambda _: dict(identity))}
        with patch.dict(sys.modules, adapters), patch.object(sampler.career.helpers, 'validate_identity'), \
                patch.object(sampler.career, 'ship_state', side_effect=native_state), \
                patch.object(sampler.career, 'once') as once:
            result = sampler.career.wait_for_ship(123, {}, sleep=periods.append)
        self.assertEqual(periods, [2] * 71)
        self.assertEqual(result['ship_wait_polls'], 72)
        self.assertTrue(result['ship_state_verified'])
        once.assert_not_called()

    def test_main_failure_preserves_last_step_and_attempts_once(self):
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(sampler.career, 'saved_complete', return_value=None), \
                patch.object(sampler, 'local_check', side_effect=checks), \
                patch.object(sampler, 'waiting_pid', return_value=123), \
                patch.object(sampler.career, 'wait_for_ship', return_value={
                    'ship_state_verified': True, 'last_native_state': 'Ship', 'ship_wait_polls': 75}), \
                patch.object(sampler.career, 'once', side_effect=ValueError('CAREER_POINTER_CHANGED')) as once, \
                patch('sys.stderr', new_callable=io.StringIO):
            folder = Path(temporary)
            self.assertEqual(sampler.main(['--output', str(folder)]), 1)
            status = json.loads((folder / 'status.json').read_text(encoding='utf8'))
        once.assert_called_once()
        self.assertEqual(status['error'], 'CAREER_POINTER_CHANGED')
        self.assertEqual(status['last_step_status']['status'], 'native_ship_ready_for_career')
        self.assertEqual(status['last_step_status']['ship_wait_polls'], 75)
        self.assertFalse(status['account_modified'])

    def test_wrong_module_stops_and_disk_check_has_no_process_dependency(self):
        adapters = {'probe_session': SimpleNamespace(game_processes=lambda: (123,)),
                    'fire_code_windows': SimpleNamespace(resolve_game=lambda _: {'game_size': 1})}
        with patch.dict(sys.modules, adapters), patch.object(sampler.career.helpers, 'validate_identity'):
            with self.assertRaisesRegex(ValueError, 'MODULE_SIZE'):
                sampler.waiting_pid({}, sleep=lambda _: self.fail('must not wait/retry mismatch'))
        with patch.dict(sys.modules, {'fire_code_windows': None, 'probe_session': None}), \
                patch.object(sampler.career, 'fingerprints', return_value={}), \
                patch.object(sampler, 'run', side_effect=AssertionError('capture')), \
                patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual(sampler.main(['--check']), 0)
        metadata = json.loads(output.getvalue())
        self.assertEqual(metadata['planned_fixed_material_bytes'], 464)
        self.assertEqual(metadata['planned_fixed_material_reads'], 5)
        self.assertFalse(metadata['career_kd_ready'])


if __name__ == '__main__':
    unittest.main()
