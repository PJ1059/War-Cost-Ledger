"""Offline three-stage ordering/cache fixtures; no live process access."""
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
spec = importlib.util.spec_from_file_location('interface_followup_v2', ROOT / 'tools/interface-code-followup-v2.py')
sampler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sampler)


def checks():
    return ({}, {'source_revision': sampler.REVISION, 'planned_bytes': 3569, 'planned_reads': 16})


def empty_caches():
    return [patch.object(sampler, name, return_value=None)
            for name in ('cached_recon', 'cached_tail', 'cached_career')]


class Tests(unittest.TestCase):
    def setUp(self):
        waiter = patch.object(sampler.career, 'wait_for_ship', return_value={
            'ship_state_verified': True, 'ship_wait_polls': 2,
            'ship_wait_read_calls': 4, 'ship_wait_bytes_requested': 24,
            'last_native_state': 'Ship', 'ship_stable_samples': 2})
        self.ship_wait = waiter.start()
        self.addCleanup(waiter.stop)

    def test_only_three_fixed_profiles_and_new_default(self):
        self.assertEqual(sampler.REVISION, 'interface_code_followup_v2')
        self.assertEqual(sampler.recon.REVISION, 'recon_chat_history_successor_v3')
        self.assertEqual(sampler.tail.REVISION, 'status_setter_tail_code_v1')
        self.assertEqual(sampler.career.TOTAL_BYTES, 464)
        self.assertEqual(sampler.career.MAX_READS, 5)
        self.assertEqual(764 + 2341 + 464, sampler.PLANNED_BYTES)
        self.assertEqual(9 + 2 + 5, sampler.PLANNED_READS)
        with patch.object(sampler, 'local_check', side_effect=checks), \
                patch('sys.stdout', new_callable=io.StringIO):
            self.assertEqual(sampler.main(['--check']), 0)

    def test_serial_order_same_pid_isolated_folders_no_extra_wait(self):
        order = []
        def first(folder, stamps=None):
            order.append(('recon', folder.name))
            return {'status': 'complete', 'game_pid': 123}
        def second(pid, folder):
            self.assertEqual(order, [('recon', 'recon-v3')])
            self.assertEqual(pid, 123)
            order.append(('tail', folder.name))
            return {'status': 'complete', 'game_pid': 123}
        def third(pid, folder):
            self.assertEqual(order, [('recon', 'recon-v3'), ('tail', 'status-tail'), ('ship', 123)])
            self.assertEqual(pid, 123)
            order.append(('career', folder.name))
            return {'status': 'complete', 'game_pid': 123}
        def ship(pid, stamps, on_wait):
            self.assertEqual(order, [('recon', 'recon-v3'), ('tail', 'status-tail')])
            order.append(('ship', pid))
            on_wait({'last_native_state': 'Mission', 'career_reads_while_waiting': 0})
            return {'ship_state_verified': True, 'last_native_state': 'Ship'}
        caches = empty_caches()
        with tempfile.TemporaryDirectory() as temporary, patch.object(sampler, 'local_check', side_effect=checks), \
                caches[0], caches[1], caches[2], \
                patch.object(sampler.recon.session, 'wait_and_capture', side_effect=first), \
                patch.object(sampler.tail, 'once', side_effect=second), \
                patch.object(sampler.career, 'wait_for_ship', side_effect=ship), \
                patch.object(sampler.career, 'once', side_effect=third), \
                patch.object(sampler, 'waiting_pid', side_effect=AssertionError('extra wait')):
            result = sampler.run(Path(temporary))
        self.assertEqual(order[-1], ('career', 'career-cache'))
        self.assertEqual(result['status'], 'complete')
        self.assertTrue(result['ship_state_verified'])
        self.assertEqual(result['last_native_state'], 'Ship')

    def test_recon_failure_does_not_run_later_stages(self):
        caches = empty_caches()
        with tempfile.TemporaryDirectory() as temporary, patch.object(sampler, 'local_check', side_effect=checks), \
                caches[0], caches[1], caches[2], \
                patch.object(sampler.recon.session, 'wait_and_capture', side_effect=ValueError('PIN_CHANGED')) as first, \
                patch.object(sampler.tail, 'once') as second, patch.object(sampler.career, 'once') as third:
            with self.assertRaisesRegex(ValueError, 'PIN_CHANGED'):
                sampler.run(Path(temporary))
        self.assertEqual(first.call_count, 1)
        second.assert_not_called(); third.assert_not_called()
        self.ship_wait.assert_not_called()

    def test_tail_failure_preserves_recon_and_stops_career(self):
        caches = empty_caches()
        with tempfile.TemporaryDirectory() as temporary, patch.object(sampler, 'local_check', side_effect=checks), \
                caches[0], caches[1], caches[2], \
                patch.object(sampler.recon.session, 'wait_and_capture', return_value={'status': 'complete', 'game_pid': 123}), \
                patch.object(sampler.tail, 'once', side_effect=ValueError('SHORT_READ')) as second, \
                patch.object(sampler.career, 'once') as third:
            folder = Path(temporary)
            with self.assertRaisesRegex(ValueError, 'SHORT_READ'):
                sampler.run(folder)
            status = json.loads((folder / 'status.json').read_text(encoding='utf8'))
        self.assertEqual(second.call_count, 1); third.assert_not_called()
        self.ship_wait.assert_not_called()
        self.assertEqual(status['stages']['recon']['status'], 'complete')
        self.assertIsNone(status['stages']['status_tail']); self.assertIsNone(status['stages']['career_cache'])

    def test_career_failure_preserves_two_successes_without_retry(self):
        caches = empty_caches()
        with tempfile.TemporaryDirectory() as temporary, patch.object(sampler, 'local_check', side_effect=checks), \
                caches[0], caches[1], caches[2], \
                patch.object(sampler.recon.session, 'wait_and_capture', return_value={'status': 'complete', 'game_pid': 123}), \
                patch.object(sampler.tail, 'once', return_value={'status': 'complete'}), \
                patch.object(sampler.career, 'once', side_effect=ValueError('POINTER_CHANGED')) as third:
            folder = Path(temporary)
            with self.assertRaisesRegex(ValueError, 'POINTER_CHANGED'):
                sampler.run(folder)
            status = json.loads((folder / 'status.json').read_text(encoding='utf8'))
        self.assertEqual(third.call_count, 1)
        self.assertEqual(status['stages']['recon']['status'], 'complete')
        self.assertEqual(status['stages']['status_tail']['status'], 'complete')
        self.assertIsNone(status['stages']['career_cache'])

    def test_all_cache_success_returns_without_rewrite_or_process_modules(self):
        caches = {key: {'status': 'complete'} for key in ('recon', 'status_tail', 'career_cache')}
        with tempfile.TemporaryDirectory() as temporary, patch.object(sampler, 'local_check', side_effect=checks), \
                patch.object(sampler, 'cached_recon', return_value=caches['recon']), \
                patch.object(sampler, 'cached_tail', return_value=caches['status_tail']), \
                patch.object(sampler, 'cached_career', return_value=caches['career_cache']), \
                patch.object(sampler.recon.session, 'wait_and_capture', side_effect=AssertionError('read')), \
                patch.object(sampler.tail, 'once', side_effect=AssertionError('read')), \
                patch.object(sampler.career, 'once', side_effect=AssertionError('read')), \
                patch.dict(sys.modules, {'fire_code_windows': None, 'probe_session': None}):
            folder = Path(temporary)
            saved = {'status': 'complete', 'source_revision': sampler.REVISION, 'stages': caches}
            raw = json.dumps(saved).encode(); (folder / 'status.json').write_bytes(raw)
            self.assertEqual(sampler.run(folder), saved)
            self.assertEqual((folder / 'status.json').read_bytes(), raw)
        self.ship_wait.assert_not_called()

    def test_first_two_cached_only_career_waits_and_uses_current_pid(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(sampler, 'local_check', side_effect=checks), \
                patch.object(sampler, 'cached_recon', return_value={'status': 'complete', 'game_pid': 99}), \
                patch.object(sampler, 'cached_tail', return_value={'status': 'complete', 'game_pid': 99}), \
                patch.object(sampler, 'cached_career', return_value=None), \
                patch.object(sampler, 'waiting_pid', return_value=123) as wait, \
                patch.object(sampler.recon.session, 'wait_and_capture', side_effect=AssertionError('recapture')), \
                patch.object(sampler.tail, 'once', side_effect=AssertionError('recapture')), \
                patch.object(sampler.career, 'once', return_value={'status': 'complete'}) as third:
            result = sampler.run(Path(temporary))
        wait.assert_called_once(); self.assertEqual(third.call_args.args[0], 123)
        self.assertEqual(self.ship_wait.call_args.args, (123, {}))
        self.assertEqual(result['status'], 'complete')

    def test_ship_wait_failure_preserves_code_stages_and_never_reads_career(self):
        caches = empty_caches()
        def not_on_ship(pid, stamps, on_wait):
            on_wait({'last_native_state': 'PrepareShip', 'ship_wait_polls': 71,
                     'ship_stable_samples': 0, 'career_reads_while_waiting': 0})
            raise ValueError('CAREER_GAME_EXITED_BEFORE_SHIP')
        with tempfile.TemporaryDirectory() as temporary, patch.object(sampler, 'local_check', side_effect=checks), \
                caches[0], caches[1], caches[2], \
                patch.object(sampler.recon.session, 'wait_and_capture', return_value={'status': 'complete', 'game_pid': 123}), \
                patch.object(sampler.tail, 'once', return_value={'status': 'complete'}), \
                patch.object(sampler.career, 'wait_for_ship', side_effect=not_on_ship) as ship, \
                patch.object(sampler.career, 'once') as data:
            folder = Path(temporary)
            with self.assertRaisesRegex(ValueError, 'CAREER_GAME_EXITED_BEFORE_SHIP'):
                sampler.run(folder)
            status = json.loads((folder / 'status.json').read_text(encoding='utf8'))
        ship.assert_called_once(); data.assert_not_called()
        self.assertEqual(status['status'], 'waiting_native_ship')
        self.assertEqual(status['last_native_state'], 'PrepareShip')
        self.assertEqual(status['career_reads_while_waiting'], 0)
        self.assertEqual(status['stages']['recon']['status'], 'complete')
        self.assertEqual(status['stages']['status_tail']['status'], 'complete')
        self.assertIsNone(status['stages']['career_cache'])

    def test_unverified_wait_return_does_not_read_career(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(sampler, 'local_check', side_effect=checks), \
                patch.object(sampler, 'cached_recon', return_value={'status': 'complete'}), \
                patch.object(sampler, 'cached_tail', return_value={'status': 'complete'}), \
                patch.object(sampler, 'cached_career', return_value=None), \
                patch.object(sampler, 'waiting_pid', return_value=123), \
                patch.object(sampler.career, 'wait_for_ship', return_value={'last_native_state': 'Mission'}), \
                patch.object(sampler.career, 'once') as data:
            with self.assertRaisesRegex(ValueError, 'SHIP_NOT_VERIFIED'):
                sampler.run(Path(temporary))
        data.assert_not_called()

    def test_old_v1_code_stage_caches_are_preserved_and_reused(self):
        old = {'status': 'complete', 'game_pid': 99}
        with patch.object(sampler.recon.session, 'saved_complete', side_effect=[None, old]) as recon_cache, \
                patch.object(sampler.tail, 'saved_complete', side_effect=[None, old]) as tail_cache:
            self.assertEqual(sampler.cached_recon(Path('new/recon-v3')), old)
            self.assertEqual(sampler.cached_tail(Path('new/status-tail')), old)
        self.assertEqual(recon_cache.call_args_list[1].args[0], sampler.ROOT / 'dist/interface-code-followup/recon-v3')
        self.assertEqual(tail_cache.call_args_list[1].args[0], sampler.ROOT / 'dist/interface-code-followup/status-tail')

    def test_cached_recon_only_outstanding_tail_and_career_share_one_wait(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(sampler, 'local_check', side_effect=checks), \
                patch.object(sampler, 'cached_recon', return_value={'status': 'complete', 'game_pid': 99}), \
                patch.object(sampler, 'cached_tail', return_value=None), patch.object(sampler, 'cached_career', return_value=None), \
                patch.object(sampler, 'waiting_pid', return_value=123) as wait, \
                patch.object(sampler.recon.session, 'wait_and_capture', side_effect=AssertionError('recapture')), \
                patch.object(sampler.tail, 'once', return_value={'status': 'complete'}) as second, \
                patch.object(sampler.career, 'once', return_value={'status': 'complete'}) as third:
            result = sampler.run(Path(temporary))
        wait.assert_called_once(); self.assertEqual(second.call_args.args[0], third.call_args.args[0])
        self.assertEqual(result['status'], 'complete')

    def test_wait_has_no_one_hundred_twenty_second_deadline(self):
        periods, state = [], {'polls': 0}
        identity = {'game_base': 0x180000000, 'game_size': sampler.tail.IMAGE_SIZE}
        def pids():
            state['polls'] += 1
            return () if state['polls'] <= 70 else (123,)
        adapters = {'fire_code_windows': SimpleNamespace(resolve_game=lambda _: dict(identity)),
                    'probe_session': SimpleNamespace(game_processes=pids)}
        with patch.dict(sys.modules, adapters), patch.object(sampler.recon.profile, 'validate_identity'), \
                patch.object(sampler.recon.session, 'validate_module'):
            self.assertEqual(sampler.waiting_pid({}, sleep=periods.append), 123)
        self.assertEqual(periods, [2] * 70 + [20])

    def test_check_is_disk_only(self):
        with patch.object(sampler.recon.profile, 'fingerprints', return_value={}) as disk, \
                patch.object(sampler, 'run', side_effect=AssertionError('capture')), \
                patch.dict(sys.modules, {'fire_code_windows': None, 'probe_session': None}), \
                patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual(sampler.main(['--check']), 0)
        disk.assert_called_once()
        self.assertEqual(json.loads(output.getvalue())['planned_reads'], 16)
        metadata = json.loads(output.getvalue())
        self.assertEqual(metadata['planned_bytes_scope'], 'fixed_diagnostic_materials_only')
        self.assertEqual(metadata['ship_wait_reads_per_poll_max'], 2)
        self.assertEqual(metadata['ship_wait_bytes_per_poll_max'], 12)
        self.assertEqual(metadata['ship_wait_interval_seconds'], 2)
        self.assertEqual(metadata['ship_recheck_bytes'], 24)
        self.assertEqual(metadata['ship_recheck_reads'], 4)


if __name__ == '__main__':
    unittest.main()
