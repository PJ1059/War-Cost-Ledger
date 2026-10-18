"""One fixed, read-only career-cache diagnostic; never synchronises the account.

The existing research proves only the career-kills consumer. Deaths, backend
readiness and account ownership remain unknown, even if a raw integer matches
the user's screenshot. This tool captures evidence, not an automatic KD reader.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('career_capture_helpers', ROOT / 'tools/status-code-capture.py')
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)
FINGERPRINT = helpers.FINGERPRINT
REVISION = 'career_cache_diagnostic_ship_v1'
IMAGE_SIZE = 0x4744000
CODE_RVA, CODE_BYTES, GLOBAL_RVA, HEAD_BYTES = 0x17B4680, 320, 0x346D570, 64
TOTAL_BYTES, MAX_READS, MAX_SECONDS = 464, 5, 2.0
PINS = ((0x17B46CA, '488b059f8ecb01'), (0x17B46F2, '448b4814'))
STATE_GLOBAL, STATE_OFFSET, SHIP_STATE = 53633856, 705052, 3
STATE_NAMES = ('None', 'Splash', 'TitleScreen', 'Ship', 'Mission', 'PrepareShip',
               'PrepareMission', 'PrepareTestLevel', 'PrepareDebugMission')
fingerprints = helpers.fingerprints


def valid_pointer(pointer):
    return 65536 <= pointer < 0x800000000000 and pointer % 8 == 0


def ship_state(process, identity):
    """Same fixed game-state layout as Runtime game_state; at most 12B/2 reads."""
    def read(address, length, image=False):
        region = process.query(address)
        if (region['state'] != 0x1000 or region['protect'] & 0x100
                or region['protect'] & 0xff not in (2, 4, 8, 0x20, 0x40, 0x80)
                or image and region['type'] != 0x1000000
                or not region['base'] <= address < address + length <= region['base'] + region['size']):
            raise ValueError('CAREER_SHIP_STATE_UNREADABLE')
        raw = process.read(address, length)
        if len(raw) != length:
            raise ValueError('CAREER_SHIP_STATE_SHORT_READ')
        return raw
    pointer = struct.unpack('<Q', read(identity['game_base'] + STATE_GLOBAL, 8, True))[0]
    if not pointer:
        return {'context': 0, 'state': None, 'name': None, 'read_calls': 1, 'read_bytes': 8}
    if not valid_pointer(pointer):
        raise ValueError('CAREER_SHIP_STATE_POINTER_INVALID')
    value = struct.unpack('<I', read(pointer + STATE_OFFSET, 4))[0]
    if value >= len(STATE_NAMES):
        raise ValueError('CAREER_SHIP_STATE_UNKNOWN')
    return {'context': pointer, 'state': value, 'name': STATE_NAMES[value],
            'read_calls': 2, 'read_bytes': 12}


def wait_for_ship(pid, stamps, on_wait=None, sleep=time.sleep):
    """Wait for two positive Ship samples. No career object reads while waiting."""
    from fire_code_windows import Process, resolve_game
    from probe_session import game_processes
    initial = resolve_game(pid)
    helpers.validate_identity(initial, stamps)
    if initial['game_size'] != IMAGE_SIZE:
        raise ValueError('CAREER_MODULE_INVALID')
    polls, stable, previous, read_calls, read_bytes = 0, 0, None, 0, 0
    with Process(pid) as process:
        while tuple(game_processes()) == (pid,):
            sample = ship_state(process, initial)
            polls += 1
            read_calls += sample['read_calls']
            read_bytes += sample['read_bytes']
            if sample and sample['state'] == SHIP_STATE:
                stable = stable + 1 if previous == sample['context'] else 1
                previous = sample['context']
            else:
                stable, previous = 0, None
            update = {'ship_wait_polls': polls, 'last_native_state': sample and sample['name'],
                      'ship_stable_samples': stable, 'ship_wait_bytes_per_poll_max': 12,
                      'ship_wait_reads_per_poll_max': 2, 'ship_wait_interval_seconds': 2,
                      'ship_wait_read_calls': read_calls, 'ship_wait_bytes_requested': read_bytes,
                      'career_reads_while_waiting': 0}
            if on_wait:
                on_wait(update)
            if stable >= 2:
                final = resolve_game(pid)
                helpers.validate_identity(final, stamps)
                if final != initial or tuple(game_processes()) != (pid,):
                    raise ValueError('CAREER_MODULE_OR_PROCESS_CHANGED')
                return {**update, 'ship_state_verified': True}
            sleep(2)
    raise ValueError('CAREER_GAME_EXITED_BEFORE_SHIP')


def verify_binary(binary):
    if len(binary) != TOTAL_BYTES:
        raise ValueError('CAREER_CAPTURE_LENGTH')
    for rva, expected in PINS:
        at = rva - CODE_RVA
        if binary[at:at + len(bytes.fromhex(expected))] != bytes.fromhex(expected):
            raise ValueError('CAREER_CODE_PIN_CHANGED:' + hex(rva))
    instruction = binary[PINS[0][0] - CODE_RVA:PINS[0][0] - CODE_RVA + 7]
    if PINS[0][0] + 7 + struct.unpack_from('<i', instruction, 3)[0] != GLOBAL_RVA:
        raise ValueError('CAREER_GLOBAL_REFERENCE_CHANGED')
    first = struct.unpack_from('<Q', binary, CODE_BYTES)[0]
    second = struct.unpack_from('<Q', binary, CODE_BYTES + 8 + HEAD_BYTES)[0]
    if not valid_pointer(first) or first != second:
        raise ValueError('CAREER_POINTER_CHANGED_OR_INVALID')
    return first


def capture(process, identity, sleep=time.sleep, clock=time.perf_counter):
    base = identity['game_base']
    if base < 65536 or base % 4096 or identity['game_size'] != IMAGE_SIZE:
        raise ValueError('CAREER_MODULE_INVALID')
    chunks, binary = [], bytearray()
    started = clock()

    def read(address, length, name, image=False, executable=False):
        if len(chunks) >= MAX_READS or len(binary) + length > TOTAL_BYTES or clock() - started > MAX_SECONDS:
            raise ValueError('CAREER_READ_BUDGET')
        if chunks:
            sleep(.1)
        if clock() - started > MAX_SECONDS:
            raise ValueError('CAREER_READ_BUDGET')
        region = process.query(address)
        protect = region['protect'] & 0xff
        allowed = (0x20, 0x40, 0x80) if executable else (2, 4, 8, 0x20, 0x40, 0x80)
        if (region['state'] != 0x1000 or region['protect'] & 0x100 or protect not in allowed
                or image and region['type'] != 0x1000000
                or not region['base'] <= address < address + length <= region['base'] + region['size']):
            raise ValueError('CAREER_REGION_UNREADABLE:' + name)
        raw = process.read(address, length)
        if len(raw) != length:
            raise ValueError('CAREER_SHORT_READ:' + name)
        chunks.append({'name': name, 'address': address, 'length': length, 'binary_offset': len(binary)})
        binary.extend(raw)
        return raw

    code = read(base + CODE_RVA, CODE_BYTES, 'known_debug_career_consumer_fragment', True, True)
    for rva, expected in PINS:
        at = rva - CODE_RVA
        if code[at:at + len(bytes.fromhex(expected))] != bytes.fromhex(expected):
            raise ValueError('CAREER_CODE_PIN_CHANGED:' + hex(rva))
    pointer = struct.unpack('<Q', read(base + GLOBAL_RVA, 8, 'career_pointer_before', True))[0]
    if not valid_pointer(pointer):
        raise ValueError('CAREER_CACHE_NOT_READY')
    before = read(pointer, HEAD_BYTES, 'unlabelled_cache_head_before')
    pointer_after = struct.unpack('<Q', read(base + GLOBAL_RVA, 8, 'career_pointer_after', True))[0]
    if pointer_after != pointer:
        raise ValueError('CAREER_POINTER_CHANGED_OR_INVALID')
    after = read(pointer, HEAD_BYTES, 'unlabelled_cache_head_after')
    raw = bytes(binary)
    verify_binary(raw)
    return raw, {'source_revision': REVISION, **FINGERPRINT, 'identity': identity,
        'complete': True, 'diagnostic_only': True, 'atomic': False,
        'function_extent_verified': False, 'code_rva': CODE_RVA, 'code_bytes': CODE_BYTES,
        'global_rva': GLOBAL_RVA, 'head_bytes': HEAD_BYTES, 'chunks': chunks,
        'bytes_written': len(raw), 'read_calls': len(chunks), 'elapsed_seconds': clock() - started,
        'cache_head_stable': before == after, 'career_kills_field_offset_from_upstream': 0x14,
        'candidate_career_kills_before': struct.unpack_from('<I', before, 0x14)[0],
        'candidate_career_kills_after': struct.unpack_from('<I', after, 0x14)[0],
        'death_field_verified': False, 'backend_ready_verified': False,
        'persistent_account_identity_verified': False, 'career_kd_ready': False,
        'native_written': False, 'native_called': False, 'account_modified': False,
        'process_access_mask': 0x410, 'binary_sha256': hashlib.sha256(raw).hexdigest()}


def saved_complete(folder):
    try:
        status = json.loads((folder / 'status.json').read_text('utf8'))
        meta_path, binary_path = Path(status['json_path']), Path(status['binary_path'])
        if (status['status'] != 'complete' or meta_path.parent.resolve() != folder.resolve()
                or binary_path.parent.resolve() != folder.resolve()):
            return None
        meta = json.loads(meta_path.read_text('utf8'))
        with binary_path.open('rb') as source:
            raw = source.read(TOTAL_BYTES + 1)
        verify_binary(raw)
        if (meta['source_revision'] != REVISION or not meta['complete']
                or any(meta[k] != v for k, v in FINGERPRINT.items())
                or hashlib.sha256(raw).hexdigest() != meta['binary_sha256']
                or meta['bytes_written'] != TOTAL_BYTES or meta['read_calls'] != MAX_READS
                or meta['career_kd_ready'] or meta['account_modified']
                or meta.get('ship_state_verified') is not True
                or meta.get('ship_context', {}).get('state') != SHIP_STATE):
            return None
        return status
    except (OSError, ValueError, KeyError, TypeError, struct.error):
        return None


def once(pid, folder):
    folder.mkdir(parents=True, exist_ok=True)
    old = saved_complete(folder)
    if old:
        return old
    from fire_code_windows import Process, resolve_game
    from probe_session import game_processes
    if type(pid) is not int or pid <= 0 or tuple(game_processes()) != (pid,):
        raise ValueError('CAREER_EXACT_PID_REQUIRED')
    stamps, identity = fingerprints(), resolve_game(pid)
    helpers.validate_identity(identity, stamps)
    with Process(pid) as process:
        before = ship_state(process, identity)
        if not before or before['state'] != SHIP_STATE:
            raise ValueError('CAREER_NOT_ON_SHIP')
        raw, meta = capture(process, identity)
        after = ship_state(process, identity)
        if after != before:
            raise ValueError('CAREER_SHIP_CHANGED_DURING_CAPTURE')
    final = resolve_game(pid)
    helpers.validate_identity(final, stamps)
    if final != identity or tuple(game_processes()) != (pid,):
        raise ValueError('CAREER_MODULE_OR_PROCESS_CHANGED')
    stem = 'career-cache-' + helpers.utc_now().replace(':', '').replace('.', '-') + '-' + uuid.uuid4().hex[:8]
    binary_path, meta_path = folder / (stem + '.bin'), folder / (stem + '.json')
    meta.update(game_pid=pid, collected_at=helpers.utc_now(), ship_state_verified=True,
                ship_context=before, ship_recheck_bytes=24, ship_recheck_reads=4)
    with binary_path.open('xb') as target:
        target.write(raw)
    with meta_path.open('x', encoding='utf8') as target:
        json.dump(meta, target, ensure_ascii=False, indent=2)
    result = {'status': 'complete', 'source_revision': REVISION, 'game_pid': pid,
        'binary_path': str(binary_path), 'json_path': str(meta_path),
        'bytes_written': TOTAL_BYTES, 'read_calls': MAX_READS, 'career_kd_ready': False}
    helpers.write_status(folder, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/career-cache-capture')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        import unittest
        tests_spec = importlib.util.spec_from_file_location('career_capture_tests', ROOT / 'tests/test_career_cache_capture.py')
        tests = importlib.util.module_from_spec(tests_spec)
        tests_spec.loader.exec_module(tests)
        result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(tests))
        return 0 if result.wasSuccessful() else 1
    if args.check:
        fingerprints()
        print(json.dumps({'status': 'local_build_matches', 'bytes': TOTAL_BYTES,
            'read_calls': MAX_READS, 'diagnostic_only': True, 'career_kd_ready': False,
            'ship_state': SHIP_STATE, 'ship_wait_bytes_per_poll_max': 12,
            'ship_wait_reads_per_poll_max': 2, 'ship_wait_interval_seconds': 2,
            'ship_recheck_bytes': 24, 'ship_recheck_reads': 4}))
        return 0
    if args.pid is None:
        parser.error('--pid is required for a capture; the serial launcher supplies it')
    try:
        print(json.dumps(once(args.pid, args.output)))
        return 0
    except Exception as failure:
        args.output.mkdir(parents=True, exist_ok=True)
        helpers.write_status(args.output, {'status': 'failed', 'source_revision': REVISION,
            'updated_at': helpers.utc_now(), 'sampler_pid': os.getpid(), 'error': str(failure),
            'native_written': False, 'native_called': False, 'career_kd_ready': False})
        print('Stopped: ' + str(failure), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
