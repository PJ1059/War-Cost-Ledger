"""Independent one-shot career diagnostic after a normal launch and Ship state.

Reuses the fixed career profile, never recon/status research. A valid disk cache
returns without process access. No game launch/stop, account sync or KD changes.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
REVISION = 'career_cache_followup_v1'
spec = importlib.util.spec_from_file_location('independent_career_capture', ROOT / 'tools/career-cache-capture.py')
career = importlib.util.module_from_spec(spec)
spec.loader.exec_module(career)


def local_check():
    stamps = career.fingerprints()
    return stamps, {'source_revision': REVISION, 'profile_revision': career.REVISION,
        'status': 'local_build_matches', 'planned_fixed_material_bytes': career.TOTAL_BYTES,
        'planned_fixed_material_reads': career.MAX_READS,
        'ship_wait_bytes_per_poll_max': 12, 'ship_wait_reads_per_poll_max': 2,
        'ship_wait_interval_seconds': 2, 'ship_recheck_bytes': 24, 'ship_recheck_reads': 4,
        'career_kd_ready': False, 'diagnostic_only': True, 'timeout_seconds': None,
        'native_written': False, 'native_called': False, 'account_modified': False,
        'capture_attempts_max': 1}


def waiting_pid(stamps, sleep=time.sleep):
    from fire_code_windows import resolve_game
    from probe_session import game_processes
    while True:
        pids = tuple(game_processes())
        if not pids:
            sleep(2)
            continue
        if len(pids) != 1:
            raise ValueError('CAREER_FOLLOWUP_MULTIPLE_GAME_PROCESSES')
        pid = pids[0]
        try:
            initial = resolve_game(pid)
        except FileNotFoundError:
            sleep(2)
            continue
        career.helpers.validate_identity(initial, stamps)
        if initial['game_size'] != career.IMAGE_SIZE:
            raise ValueError('CAREER_FOLLOWUP_MODULE_SIZE')
        sleep(20)
        if tuple(game_processes()) != (pid,):
            continue
        final = resolve_game(pid)
        career.helpers.validate_identity(final, stamps)
        if final != initial:
            raise ValueError('CAREER_FOLLOWUP_MODULE_CHANGED')
        return pid


def run(folder):
    old = career.saved_complete(folder)
    if old:
        return old
    folder.mkdir(parents=True, exist_ok=True)
    stamps, checks = local_check()
    base = {**checks, 'launcher_revision': REVISION, 'sampler_pid': os.getpid(),
            'readiness': 'nativeGameState_Ship_two_consecutive_samples',
            'ship_state_verified': False}
    career.helpers.write_status(folder, {**base, 'status': 'waiting_game'})
    pid = waiting_pid(stamps)
    base['game_pid'] = pid

    def on_wait(update):
        career.helpers.write_status(folder, {**base, **update, 'status': 'waiting_native_ship'})

    ship = career.wait_for_ship(pid, stamps, on_wait=on_wait)
    if ship.get('ship_state_verified') is not True:
        raise ValueError('CAREER_FOLLOWUP_SHIP_NOT_VERIFIED')
    career.helpers.write_status(folder, {**base, **ship, 'status': 'native_ship_ready_for_career'})
    result = {**base, **ship, **career.once(pid, folder)}
    career.helpers.write_status(folder, result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/career-cache-capture')
    parser.add_argument('--check', action='store_true', help='Disk fingerprint only; no process access.')
    parser.add_argument('--self-test', action='store_true', help='Isolated offline fixtures only.')
    args = parser.parse_args(argv)
    if args.self_test:
        import unittest
        test_spec = importlib.util.spec_from_file_location('career_followup_tests', ROOT / 'tests/test_career_cache_followup.py')
        tests = importlib.util.module_from_spec(test_spec)
        test_spec.loader.exec_module(tests)
        result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(tests))
        return 0 if result.wasSuccessful() else 1
    if args.check:
        _, checks = local_check()
        print(json.dumps(checks))
        return 0
    try:
        print(json.dumps(run(args.output)))
        return 0
    except KeyboardInterrupt:
        code, status, error = 130, 'cancelled', 'cancelled'
    except Exception as failure:
        code, status, error = 1, 'failed', str(failure)
    try:
        previous = json.loads((args.output / 'status.json').read_text(encoding='utf8'))
    except (OSError, ValueError):
        previous = None
    args.output.mkdir(parents=True, exist_ok=True)
    career.helpers.write_status(args.output, {'status': status, 'source_revision': REVISION,
        'sampler_pid': os.getpid(), 'updated_at': career.helpers.utc_now(), 'error': error,
        'last_step_status': previous, 'capture_attempts_max': 1, 'career_kd_ready': False,
        'native_written': False, 'native_called': False, 'account_modified': False})
    print('Stopped: ' + error, file=sys.stderr)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
