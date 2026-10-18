"""One external read-only capture of four fixed hit-classification research windows.

Wait for the user's normal launch and the loaded game.dll, then read 14976 code
bytes once. Module readiness does not establish that the player is on the ship.
No hit events, enemy data, game state, native calls, hooks, or game writes are used.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
GAME = Path(r'G:\SteamLibrary\steamapps\common\Helldivers 2')
FINGERPRINT = {
    'exe_sha': 'f5fee03dcfdb2e553a4752c283590950ac13316b376d8196aa556ff0400d5f06',
    'dll_sha': '2e2c3b7c2500646dadd5f2b4c6e0504dbb7e7896139f64cddc0d1813c718f51e',
}
REVISION = 'hit_classification_code_v1'
RANGES = (
    ('selected_ap_and_armour_multiplier_candidates', 0x129C7C0, 0x1550),
    ('hit_info_initialisation', 0x12A15E0, 0x1030),
    ('direct_projectile_contact_candidate', 0x13AD400, 0xF00),
    ('physical_ricochet_candidate', 0x13B0BF0, 0x600),
)
# Nine exact bytes/RVAs from the pinned Runtime research_event_combat.py hit_init.
# The other three windows have source-described candidate bounds, not byte PINs.
PINS = (
    (0x12A1C29, '8b4324'),
    (0x12A23FD, '488d0dbc3c5202'),
    (0x12A2408, '8b4128'),
    (0x12A240E, '41894604'),
    (0x12A2479, '660f6e5904'),
    (0x12A247E, '660f6e4908'),
    (0x12A2516, '41898684000000'),
    (0x12A2549, '41898604010000'),
    (0x12A2592, '49898610010000'),
)
MAX_CHUNK = 4096
TOTAL_BYTES = sum(length for _, _, length in RANGES)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def write_status(folder, value):
    pending = folder / ('status.' + uuid.uuid4().hex + '.tmp')
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf8')
    os.replace(pending, folder / 'status.json')


def range_plan():
    offset, result = 0, []
    for name, start, length in RANGES:
        result.append({'name': name, 'rva': start, 'length': length,
                       'binary_offset': offset,
                       'pin_count': sum(start <= rva and rva + len(bytes.fromhex(raw)) <= start + length
                                        for rva, raw in PINS)})
        offset += length
    return result


def verify_pins(binary):
    if len(binary) != TOTAL_BYTES:
        raise ValueError('HIT_CODE_LENGTH_MISMATCH')
    records = []
    for window in range_plan():
        start, length, offset = window['rva'], window['length'], window['binary_offset']
        for rva, expected in PINS:
            raw = bytes.fromhex(expected)
            if start <= rva and rva + len(raw) <= start + length:
                actual = binary[offset + rva - start:offset + rva - start + len(raw)]
                records.append({'rva': rva, 'range': window['name'], 'matched': actual == raw})
    if len(records) != len(PINS) or not all(pin['matched'] for pin in records):
        failed = ','.join(hex(pin['rva']) for pin in records if not pin['matched'])
        raise ValueError('HIT_CODE_PIN_MISMATCH: ' + (failed or 'missing pin'))
    return records


def capture(process, identity, sleep=time.sleep):
    """Six bounded code reads; PIN checked in the same captured material."""
    base, image_size = identity['game_base'], identity['game_size']
    if base < 65536 or base % 4096 or image_size < max(rva + n for _, rva, n in RANGES):
        raise ValueError('HIT_CODE_MODULE_INVALID')
    output = bytearray()
    meta = {'source_revision': REVISION, **FINGERPRINT, 'started_at': utc_now(),
            'purpose': 'projectile_ap_armour_and_physical_ricochet_code_diagnosis', 'code_only': True,
            'classification_ready': False, 'complete_stream': False,
            'atomic': False, 'complete': False, 'native_written': False,
            'native_called': False, 'ship_state_verified': False,
            'readiness': 'game.dll_loaded_with_20_second_startup_delay',
            'bytes_planned': TOTAL_BYTES, 'bytes_written': 0,
            'identity': dict(identity), 'ranges': range_plan(), 'chunks': [],
            'source_reference': {
                'byte_pins': 'SkyeShade-HD2Runtime-dcd996d/scripts/research_event_combat.py hit_init',
                'window_bounds': 'Runtime research_direct_hit_damage.py/research_projectile_ballistics.py; fixed candidate windows',
            },
            'limitations': [
                'Only HitInfo initialisation has nine upstream byte PINs; the other three fixed windows remain code candidates.',
                'This code-only capture contains no per-contact events and cannot establish a classified or complete hit stream.',
                'Module readiness does not prove ship or mission state.',
            ]}
    for name, rva, length in RANGES:
        offset = 0
        while offset < length:
            n = min(MAX_CHUNK, length - offset)
            address = base + rva + offset
            started = time.perf_counter()
            region = process.query(address)
            protection = region['protect']
            if not (region['state'] == 0x1000 and region['type'] == 0x1000000
                    and region['base'] <= address
                    and address + n <= region['base'] + region['size']
                    and not protection & 0x100
                    and protection & 0xff in (0x20, 0x40, 0x80)):
                raise ValueError(f'HIT_CODE_REGION_UNREADABLE: rva={rva + offset:#x}, length={n}')
            raw = process.read(address, n)
            if len(raw) != n:
                raise ValueError(f'HIT_CODE_SHORT_READ: rva={rva + offset:#x}, requested={n}, returned={len(raw)}')
            output.extend(raw)
            meta['chunks'].append({'name': name, 'rva': rva + offset, 'length': n,
                                   'read_ms': (time.perf_counter() - started) * 1000})
            offset += n
            if len(output) < TOTAL_BYTES:
                sleep(0.1)
    binary = bytes(output)
    meta['pins'] = verify_pins(binary)
    meta.update(bytes_written=len(binary), binary_sha256=hashlib.sha256(binary).hexdigest(),
                finished_at=utc_now(), complete=True)
    return binary, meta


def saved_complete(folder):
    """Reuse a verified successful cache without opening or reading the game."""
    try:
        status = json.loads((folder / 'status.json').read_text(encoding='utf8'))
        if status.get('status') != 'complete':
            return None
        meta_path, bin_path = Path(status['json_path']), Path(status['binary_path'])
        if meta_path.parent.resolve() != folder.resolve() or bin_path.parent.resolve() != folder.resolve():
            return None
        meta = json.loads(meta_path.read_text(encoding='utf8'))
        if (not meta.get('complete') or meta.get('source_revision') != REVISION
                or meta.get('ranges') != range_plan()
                or any(meta.get(k) != v for k, v in FINGERPRINT.items())):
            return None
        with bin_path.open('rb') as source:
            binary = source.read(TOTAL_BYTES + 1)
        verify_pins(binary)
        if hashlib.sha256(binary).hexdigest() != meta.get('binary_sha256'):
            return None
        return status
    except (OSError, ValueError, KeyError, TypeError):
        return None


def fingerprints():
    """Validate disk files only, before waiting or importing the process adapter."""
    paths = {'exe_sha': GAME / 'bin/helldivers2.exe', 'dll_sha': GAME / 'data/game/game.dll'}
    stamps = {}
    for key, path in paths.items():
        before = path.stat()
        if sha256(path) != FINGERPRINT[key]:
            raise ValueError('HIT_CODE_BUILD_MISMATCH: ' + str(path))
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError('HIT_CODE_BUILD_CHANGED')
        stamps[key] = (path, after.st_size, after.st_mtime_ns)
    return stamps


def validate_identity(identity, stamps):
    for key, field in (('exe_sha', 'exe_path'), ('dll_sha', 'game_path')):
        path, size, modified = stamps[key]
        if Path(identity[field]).resolve() != path.resolve():
            raise ValueError('HIT_CODE_MODULE_PATH_MISMATCH')
        current = path.stat()
        if (current.st_size, current.st_mtime_ns) != (size, modified):
            raise ValueError('HIT_CODE_BUILD_CHANGED')


def wait_and_capture(folder):
    old = saved_complete(folder)
    if old:
        return old
    stamps = fingerprints()
    from fire_code_windows import Process, resolve_game
    from probe_session import game_processes

    write_status(folder, {'status': 'waiting_game', 'sampler_pid': os.getpid(),
                         'updated_at': utc_now(), 'source_revision': REVISION,
                         'bytes_planned': TOTAL_BYTES, 'timeout_seconds': None,
                         'ship_state_verified': False})
    attempts = 0
    while True:
        pids = game_processes()
        if not pids:
            time.sleep(2)
            continue
        if len(pids) != 1:
            raise ValueError('HIT_CODE_MULTIPLE_GAME_PROCESSES')
        pid = pids[0]
        try:
            identity = resolve_game(pid)
        except FileNotFoundError:
            time.sleep(2)
            continue
        validate_identity(identity, stamps)
        write_status(folder, {'status': 'waiting_loaded_code', 'sampler_pid': os.getpid(),
                             'source_revision': REVISION, 'game_pid': pid,
                             'updated_at': utc_now(), 'bytes_planned': TOTAL_BYTES,
                             'ship_state_verified': False})
        time.sleep(20)  # DLL startup delay only, with no memory reads.
        if pid not in game_processes():
            continue
        attempts += 1
        try:
            current = resolve_game(pid)
            validate_identity(current, stamps)
            with Process(pid) as process:
                binary, meta = capture(process, current)
            final = resolve_game(pid)
            validate_identity(final, stamps)
            if current != final:
                raise ValueError('HIT_CODE_MODULE_CHANGED')
            stem = 'hit-classification-code-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
            bin_path, meta_path = folder / (stem + '.bin'), folder / (stem + '.json')
            with bin_path.open('xb') as target:
                target.write(binary)
            meta.update(game_pid=pid, attempts=attempts,
                        binary_path=str(bin_path), json_path=str(meta_path))
            with meta_path.open('x', encoding='utf8') as target:
                json.dump(meta, target, ensure_ascii=False, indent=2)
            result = {'status': 'complete', 'sampler_pid': os.getpid(), 'game_pid': pid,
                      'source_revision': REVISION, 'updated_at': utc_now(),
                      'binary_path': str(bin_path), 'json_path': str(meta_path),
                      'bytes_written': len(binary), 'code_reads': sum((n + MAX_CHUNK - 1) // MAX_CHUNK for _, _, n in RANGES),
                      'ship_state_verified': False}
            write_status(folder, result)
            return result
        except (OSError, ValueError) as error:
            write_status(folder, {'status': 'incomplete', 'sampler_pid': os.getpid(),
                                 'source_revision': REVISION, 'game_pid': pid,
                                 'attempts': attempts, 'updated_at': utc_now(),
                                 'error': str(error)})
            if attempts >= 2 or pid not in game_processes():
                raise
            time.sleep(10)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/hit-code-capture')
    parser.add_argument('--check', action='store_true', help='Validate disk build only; no game read or wait.')
    args = parser.parse_args(argv)
    if args.check:
        fingerprints()
        print(json.dumps({'status': 'local_build_matches', 'source_revision': REVISION,
                          'bytes_planned': TOTAL_BYTES, 'code_reads': sum((n + MAX_CHUNK - 1) // MAX_CHUNK for _, _, n in RANGES),
                          'pins': len(PINS), 'ranges': range_plan(),
                          'classification_ready': False, 'complete_stream': False,
                          'ship_state_verified': False}))
        return 0
    args.output.mkdir(parents=True, exist_ok=True)
    old = saved_complete(args.output)
    if old:
        print('Already complete: ' + old['json_path'])
        return 0
    try:
        result = wait_and_capture(args.output)
        print('Complete: ' + result['json_path'])
        return 0
    except KeyboardInterrupt:
        write_status(args.output, {'status': 'cancelled', 'source_revision': REVISION,
                                  'updated_at': utc_now()})
        return 130
    except Exception as error:
        write_status(args.output, {'status': 'failed', 'source_revision': REVISION,
                                  'updated_at': utc_now(), 'error': str(error)})
        print('Stopped: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
