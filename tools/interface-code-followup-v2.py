"""Wait for a normal launch, then serially capture three fixed diagnostic profiles.

Only two fixed code profiles plus one small career code/cache diagnostic. No game
launch/stop, gameplay-event scan, native call or write. Successful profile caches
are preserved. Career data is read only after two native Ship samples; module
readiness plus 20 seconds alone does not prove ship state.
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
REVISION = 'interface_code_followup_v2'
PLANNED_BYTES, PLANNED_READS = 3569, 16


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


recon = load('followup_recon_successor', 'recon_chat_successor_capture.py')
tail = load('followup_status_tail', 'status-setter-tail-code-capture.py')
career = load('followup_career_cache', 'career-cache-capture.py')


def cached_recon(folder):
    return (recon.session.saved_complete(folder)
            or recon.session.saved_complete(ROOT / 'dist/interface-code-followup/recon-v3')
            or recon.session.saved_complete(ROOT / 'dist/recon-chat-code-v3'))


def cached_tail(folder):
    return (tail.saved_complete(folder)
            or tail.saved_complete(ROOT / 'dist/interface-code-followup/status-tail')
            or tail.saved_complete(ROOT / 'dist/status-setter-tail-code'))


def cached_career(folder):
    return career.saved_complete(folder) or career.saved_complete(ROOT / 'dist/career-cache-capture')


def local_check():
    if (recon.profile.FINGERPRINT != tail.FINGERPRINT
            or recon.profile.FINGERPRINT != career.FINGERPRINT
            or career.TOTAL_BYTES != 464 or career.MAX_READS != 5):
        raise ValueError('FOLLOWUP_BUILD_PROFILES_DIFFER')
    stamps = recon.profile.fingerprints()
    proof = tail.verify_parent_material()
    return stamps, {'status': 'local_build_and_saved_prefix_match', 'source_revision': REVISION,
                    'planned_bytes': PLANNED_BYTES, 'planned_reads': PLANNED_READS,
                    'planned_bytes_scope': 'fixed_diagnostic_materials_only',
                    'ship_wait_reads_per_poll_max': 2, 'ship_wait_bytes_per_poll_max': 12,
                    'ship_wait_interval_seconds': 2,
                    'ship_recheck_bytes': 24, 'ship_recheck_reads': 4,
                    'recon_revision': recon.REVISION, 'tail_revision': tail.REVISION,
                    'career_revision': career.REVISION, 'career_automatic_kd_ready': False,
                    'tail_parent_sha256': proof['binary_sha256'], 'native_written': False,
                    'native_called': False, 'chat_messages_read': 0,
                    'ship_state_verified': False, 'timeout_seconds': None}


def waiting_pid(stamps, sleep=time.sleep):
    """Used only when earlier stages are cached but an outstanding profile needs the game."""
    from fire_code_windows import resolve_game
    from probe_session import game_processes
    while True:
        pids = tuple(game_processes())
        if not pids:
            sleep(2)
            continue
        if len(pids) != 1:
            raise ValueError('FOLLOWUP_MULTIPLE_GAME_PROCESSES')
        pid = pids[0]
        try:
            initial = resolve_game(pid)
        except FileNotFoundError:
            sleep(2)
            continue
        recon.profile.validate_identity(initial, stamps)
        recon.session.validate_module(initial)
        sleep(20)
        if tuple(game_processes()) != (pid,):
            continue
        final = resolve_game(pid)
        recon.profile.validate_identity(final, stamps)
        if final != initial:
            raise ValueError('FOLLOWUP_MODULE_CHANGED')
        return pid


def run(folder):
    folder.mkdir(parents=True, exist_ok=True)
    recon_folder, tail_folder, career_folder = folder / 'recon-v3', folder / 'status-tail', folder / 'career-cache'
    stamps, checks = local_check()
    stages = {'recon': cached_recon(recon_folder), 'status_tail': cached_tail(tail_folder),
              'career_cache': cached_career(career_folder)}
    base = {**checks, 'sampler_pid': os.getpid(), 'updated_at': recon.profile.utc_now(),
            'stages': stages,
            'readiness': 'code_module_loaded_plus_20_seconds_career_nativeGameState_Ship_twice',
            'career_readiness': 'nativeGameState_Ship_two_consecutive_samples',
            'ship_state_verified': bool(stages['career_cache']),
            'serial': True, 'each_profile_attempts_max': 1}
    if all(stages.values()):
        # Returning existing successful state does not rewrite it or read the game.
        try:
            previous = json.loads((folder / 'status.json').read_text(encoding='utf8'))
            if (previous.get('status') == 'complete' and previous.get('source_revision') == REVISION
                    and previous.get('stages') == stages):
                return previous
        except (OSError, ValueError):
            pass
        result = {**base, 'status': 'complete'}
        recon.profile.write_status(folder, result)
        return result
    recon.profile.write_status(folder, {**base, 'status': 'waiting_game'})
    if not stages['recon']:
        recon_folder.mkdir(parents=True, exist_ok=True)
        # Existing v3 wait includes the sole 20-second startup delay and no retry.
        stages['recon'] = recon.session.wait_and_capture(recon_folder, stamps=stamps)
        recon.profile.write_status(folder, {**base, 'status': 'recon_complete_waiting_tail'})
        pid = stages['recon']['game_pid']
    else:
        pid = None
    if not stages['status_tail']:
        tail_folder.mkdir(parents=True, exist_ok=True)
        pid = waiting_pid(stamps) if pid is None else pid
        stages['status_tail'] = tail.once(pid, tail_folder)
    if not stages['career_cache']:
        career_folder.mkdir(parents=True, exist_ok=True)
        recon.profile.write_status(folder, {**base, 'status': 'earlier_stages_complete_waiting_career'})
        pid = waiting_pid(stamps) if pid is None else pid

        def on_ship_wait(update):
            recon.profile.write_status(folder, {**base, **update, 'status': 'waiting_native_ship'})

        ship = career.wait_for_ship(pid, stamps, on_wait=on_ship_wait)
        if ship.get('ship_state_verified') is not True:
            raise ValueError('FOLLOWUP_CAREER_SHIP_NOT_VERIFIED')
        base.update(ship)
        recon.profile.write_status(folder, {**base, 'status': 'native_ship_ready_for_career'})
        stages['career_cache'] = career.once(pid, career_folder)
    result = {**base, 'status': 'complete', 'updated_at': recon.profile.utc_now()}
    recon.profile.write_status(folder, result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/interface-code-followup-v2')
    parser.add_argument('--check', action='store_true', help='Disk files only; no game enumeration or reads.')
    parser.add_argument('--self-test', action='store_true', help='Isolated fixtures only.')
    args = parser.parse_args(argv)
    if args.self_test:
        import unittest
        tests = load('followup_tests', '../tests/test_interface_code_followup_v2.py')
        result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(tests))
        return 0 if result.wasSuccessful() else 1
    if args.check:
        _, checks = local_check()
        print(json.dumps(checks))
        return 0
    try:
        result = run(args.output)
        print(json.dumps(result))
        return 0
    except KeyboardInterrupt:
        code, status, error = 130, 'cancelled', 'cancelled'
    except Exception as failure:
        code, status, error = 1, 'failed', str(failure)
    args.output.mkdir(parents=True, exist_ok=True)
    stages = {'recon': cached_recon(args.output / 'recon-v3'),
              'status_tail': cached_tail(args.output / 'status-tail'),
              'career_cache': cached_career(args.output / 'career-cache')}
    recon.profile.write_status(args.output, {'status': status, 'source_revision': REVISION,
        'sampler_pid': os.getpid(), 'updated_at': recon.profile.utc_now(), 'error': error,
        'stages': stages, 'native_written': False, 'native_called': False})
    print('Stopped: ' + error, file=sys.stderr)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
