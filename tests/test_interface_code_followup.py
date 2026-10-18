"""Offline ordering/wait/cache fixtures; never inspect or read the game."""
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
spec = importlib.util.spec_from_file_location('interface_followup', ROOT / 'tools/interface-code-followup.py')
sampler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sampler)


def checks():
    return ({}, {'source_revision': sampler.REVISION, 'planned_bytes': 3105, 'planned_reads': 11})


class Tests(unittest.TestCase):
    def test_plans_are_only_two_frozen_profiles(self):
        self.assertEqual(sampler.recon.REVISION, 'recon_chat_history_successor_v3')
        self.assertEqual(sampler.tail.REVISION, 'status_setter_tail_code_v1')
        self.assertEqual(sampler.recon.CODE_END - sampler.recon.CODE_BEGIN, 692)
        self.assertEqual(sampler.tail.TOTAL_BYTES, 2341)
        self.assertEqual(36 + 12 + 24 + 692 + 2341, sampler.PLANNED_BYTES)
        self.assertEqual(3 + 3 + 2 + 1 + 2, sampler.PLANNED_READS)

    def test_serial_recon_then_tail_and_isolated_outputs(self):
        order = []
        def first(folder, stamps=None):
            order.append(('recon', folder.name))
            return {'status': 'complete', 'game_pid': 123}
        def second(pid, folder):
            self.assertEqual(order, [('recon', 'recon-v3')])
            order.append(('tail', folder.name))
            self.assertEqual(pid, 123)
            return {'status': 'complete', 'game_pid': 123}
        with tempfile.TemporaryDirectory() as temporary, patch.object(sampler, 'local_check', side_effect=checks), \
                patch.object(sampler, 'cached_recon', return_value=None), patch.object(sampler, 'cached_tail', return_value=None), \
                patch.object(sampler.recon.session, 'wait_and_capture', side_effect=first), \
                patch.object(sampler.tail, 'once', side_effect=second), \
                patch.object(sampler, 'waiting_pid', side_effect=AssertionError('extra startup wait')):
            result = sampler.run(Path(temporary))
        self.assertEqual(order, [('recon', 'recon-v3'), ('tail', 'status-tail')])
        self.assertEqual(result['status'], 'complete')

    def test_recon_failure_never_runs_tail_or_retries(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(sampler, 'local_check', side_effect=checks), \
                patch.object(sampler, 'cached_recon', return_value=None), patch.object(sampler, 'cached_tail', return_value=None), \
                patch.object(sampler.recon.session, 'wait_and_capture', side_effect=ValueError('PIN_CHANGED')) as first, \
                patch.object(sampler.tail, 'once') as second:
            with self.assertRaisesRegex(ValueError, 'PIN_CHANGED'):
                sampler.run(Path(temporary))
        self.assertEqual(first.call_count, 1)
        second.assert_not_called()

    def test_tail_failure_preserves_successful_recon_stage(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(sampler, 'local_check', side_effect=checks), \
                patch.object(sampler, 'cached_recon', return_value=None), patch.object(sampler, 'cached_tail', return_value=None), \
                patch.object(sampler.recon.session, 'wait_and_capture', return_value={'status': 'complete', 'game_pid': 123}) as first, \
                patch.object(sampler.tail, 'once', side_effect=ValueError('SHORT_READ')) as second:
            folder = Path(temporary)
            with self.assertRaisesRegex(ValueError, 'SHORT_READ'):
                sampler.run(folder)
            status = json.loads((folder / 'status.json').read_text(encoding='utf8'))
        self.assertEqual(first.call_count, 1)
        self.assertEqual(second.call_count, 1)
        self.assertEqual(status['stages']['recon']['status'], 'complete')
        self.assertIsNone(status['stages']['status_tail'])

    def test_success_cache_exits_without_process_modules_or_rewrite(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(sampler, 'local_check', side_effect=checks), \
                patch.object(sampler, 'cached_recon', return_value={'status': 'complete'}), \
                patch.object(sampler, 'cached_tail', return_value={'status': 'complete'}), \
                patch.object(sampler.recon.session, 'wait_and_capture', side_effect=AssertionError('fresh reads')), \
                patch.object(sampler.tail, 'once', side_effect=AssertionError('fresh reads')), \
                patch.dict(sys.modules, {'fire_code_windows': None, 'probe_session': None}):
            folder = Path(temporary)
            saved = {'status': 'complete', 'source_revision': sampler.REVISION,
                     'stages': {'recon': {'status': 'complete'}, 'status_tail': {'status': 'complete'}}}
            raw = json.dumps(saved).encode()
            (folder / 'status.json').write_bytes(raw)
            self.assertEqual(sampler.run(folder), saved)
            self.assertEqual((folder / 'status.json').read_bytes(), raw)

    def test_cached_recon_missing_tail_uses_loaded_twenty_second_wait(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(sampler, 'local_check', side_effect=checks), \
                patch.object(sampler, 'cached_recon', return_value={'status': 'complete', 'game_pid': 99}), \
                patch.object(sampler, 'cached_tail', return_value=None), \
                patch.object(sampler, 'waiting_pid', return_value=123) as wait, \
                patch.object(sampler.recon.session, 'wait_and_capture', side_effect=AssertionError('recapture')), \
                patch.object(sampler.tail, 'once', return_value={'status': 'complete'}) as tail:
            result = sampler.run(Path(temporary))
        wait.assert_called_once()
        self.assertEqual(tail.call_args.args[0], 123)
        self.assertEqual(result['status'], 'complete')

    def test_wait_has_no_one_hundred_twenty_second_timeout(self):
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

    def test_check_does_not_enumerate_or_read_game(self):
        with patch.object(sampler.recon.profile, 'fingerprints', return_value={}) as disk, \
                patch.object(sampler, 'run', side_effect=AssertionError('capture')), \
                patch.dict(sys.modules, {'fire_code_windows': None, 'probe_session': None}), \
                patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual(sampler.main(['--check']), 0)
        disk.assert_called_once()
        self.assertEqual(json.loads(output.getvalue())['planned_reads'], 11)


if __name__ == '__main__':
    unittest.main()
