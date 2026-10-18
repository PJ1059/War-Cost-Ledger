"""One external, read-only capture of fixed FIRE death-path code windows.

Waits for the user's normal game launch; never starts or stops the game. It does
not use a DLL hook, update the MOD, or read enemies. Successful material is reused.
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
REVISION = 'fire_death_code_v1'
RANGES = (
    ('set_life_state', 0x91C240, 0x1340),
    ('health_update', 0x920260, 0x1000),
    ('apply_damage', 0x9235F0, 0x2840),
)
PINS = (
    (0x91C277, '4869f9b8010000'), (0x91C28D, '498bb758100000'),
    (0x91C2C8, '3b9c379c010000'), (0x91CF8B, '41899c309c010000'),
    (0x92049B, '448b441f0c'), (0x9204BD, 'e87ebdffff'),
    (0x92087D, '488b5638'), (0x920881, 'c744242002000000'),
    (0x920889, 'e8825a2700'), (0x920CDC, '488b5638'),
    (0x920CE8, 'c744242007000000'), (0x920CF0, 'e81b562700'),
    (0x923747, '496bc01c'), (0x923756, '498b842460100000'),
    (0x923C20, '49894738'), (0x925567, '498b5638'),
    (0x925578, 'e8930d2700'), (0x9256F4, 'e8476bffff'),
)
TOTAL_BYTES = sum(length for _, _, length in RANGES)
MAX_CHUNK = 4096


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def write_status(folder, value):
    pending = folder / ('status.' + uuid.uuid4().hex + '.tmp')
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf8')
    os.replace(pending, folder / 'status.json')


def verify_pins(binary):
    if len(binary) != TOTAL_BYTES:
        raise ValueError('FIRE_CODE_LENGTH_MISMATCH')
    records, offset = [], 0
    for name, start, length in RANGES:
        for rva, expected in PINS:
            wanted = bytes.fromhex(expected)
            if start <= rva and rva + len(wanted) <= start + length:
                actual = binary[offset + rva - start:offset + rva - start + len(wanted)]
                records.append({'rva': rva, 'range': name, 'matched': actual == wanted})
        offset += length
    if len(records) != len(PINS) or not all(pin['matched'] for pin in records):
        failed = ','.join(hex(pin['rva']) for pin in records if not pin['matched'])
        raise ValueError('FIRE_CODE_PIN_MISMATCH: ' + (failed or 'missing pin'))
    return records


def capture(process, identity, sleep=time.sleep):
    """Six reads, exact lengths, then verify PINs in those same captured bytes."""
    base, image_size = identity['game_base'], identity['game_size']
    if base < 65536 or base % 4096 or image_size < max(rva + n for _, rva, n in RANGES):
        raise ValueError('FIRE_CODE_MODULE_INVALID')
    output = bytearray()
    meta = {'source_revision': REVISION, **FINGERPRINT, 'started_at': utc_now(),
            'atomic': False, 'complete': False, 'native_written': False,
            'native_called': False, 'bytes_planned': TOTAL_BYTES,
            'bytes_written': 0, 'identity': dict(identity), 'ranges': [], 'chunks': []}
    for name, rva, length in RANGES:
        meta['ranges'].append({'name': name, 'rva': rva, 'length': length,
                               'binary_offset': len(output)})
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
                raise ValueError(f'FIRE_CODE_REGION_UNREADABLE: rva={rva + offset:#x}, length={n}')
            raw = process.read(address, n)
            if len(raw) != n:
                raise ValueError(f'FIRE_CODE_SHORT_READ: rva={rva + offset:#x}, requested={n}, returned={len(raw)}')
            meta['chunks'].append({'rva': rva + offset, 'length': n,
                                   'read_ms': (time.perf_counter() - started) * 1000})
            output.extend(raw)
            offset += n
            if len(output) < TOTAL_BYTES:
                sleep(0.1)
    binary = bytes(output)
    meta['pins'] = verify_pins(binary)
    meta.update(bytes_written=len(binary), binary_sha256=hashlib.sha256(binary).hexdigest(),
                finished_at=utc_now(), complete=True)
    return binary, meta


def saved_complete(folder):
    """Reuse only matching, complete, independently rechecked stored code."""
    path = folder / 'status.json'
    if not path.is_file():
        return None
    try:
        status = json.loads(path.read_text(encoding='utf8'))
        if status.get('status') != 'complete':
            return None
        meta_path, bin_path = Path(status['json_path']), Path(status['binary_path'])
        if meta_path.parent.resolve() != folder.resolve() or bin_path.parent.resolve() != folder.resolve():
            return None
        meta = json.loads(meta_path.read_text(encoding='utf8'))
        if (not meta.get('complete') or meta.get('source_revision') != REVISION
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
    """Hash before waiting, so this disk work finishes while the game is closed."""
    paths = {'exe_sha': GAME / 'bin/helldivers2.exe', 'dll_sha': GAME / 'data/game/game.dll'}
    stamps = {}
    for key, path in paths.items():
        before = path.stat()
        if sha256(path) != FINGERPRINT[key]:
            raise ValueError('FIRE_CODE_BUILD_MISMATCH: ' + str(path))
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError('FIRE_CODE_BUILD_CHANGED')
        stamps[key] = (path, after.st_size, after.st_mtime_ns)
    return stamps


def validate_identity(identity, stamps):
    for key, field in (('exe_sha', 'exe_path'), ('dll_sha', 'game_path')):
        path, size, modified = stamps[key]
        if Path(identity[field]).resolve() != path.resolve():
            raise ValueError('FIRE_CODE_MODULE_PATH_MISMATCH')
        current = path.stat()
        if (current.st_size, current.st_mtime_ns) != (size, modified):
            raise ValueError('FIRE_CODE_BUILD_CHANGED')


def wait_and_capture(folder):
    from fire_code_windows import Process, resolve_game
    from probe_session import game_processes

    stamps = fingerprints()
    write_status(folder, {'status': 'waiting_game', 'sampler_pid': os.getpid(),
                         'updated_at': utc_now(), 'source_revision': REVISION,
                         'bytes_planned': TOTAL_BYTES, 'timeout_seconds': None})
    attempts = 0
    while True:
        pids = game_processes()
        if not pids:
            time.sleep(2)
            continue
        if len(pids) != 1:
            raise ValueError('FIRE_CODE_MULTIPLE_GAME_PROCESSES')
        pid = pids[0]
        try:
            identity = resolve_game(pid)
        except FileNotFoundError:
            time.sleep(2)
            continue
        validate_identity(identity, stamps)
        write_status(folder, {'status': 'waiting_loaded_code', 'sampler_pid': os.getpid(),
                             'game_pid': pid, 'updated_at': utc_now()})
        time.sleep(20)  # Startup/unpacking; no game reads during this delay.
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
                raise ValueError('FIRE_CODE_MODULE_CHANGED')
            stem = 'fire-code-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
            bin_path, meta_path = folder / (stem + '.bin'), folder / (stem + '.json')
            with bin_path.open('xb') as target:
                target.write(binary)
            meta.update(game_pid=pid, attempts=attempts,
                        source_reference='SkyeShade-HD2Runtime-dcd996d/scripts/research_event_combat.py PINS',
                        binary_path=str(bin_path), json_path=str(meta_path))
            with meta_path.open('x', encoding='utf8') as target:
                json.dump(meta, target, ensure_ascii=False, indent=2)
            result = {'status': 'complete', 'sampler_pid': os.getpid(), 'game_pid': pid,
                      'updated_at': utc_now(), 'binary_path': str(bin_path),
                      'json_path': str(meta_path), 'bytes_written': len(binary)}
            write_status(folder, result)
            return result
        except (OSError, ValueError) as error:
            write_status(folder, {'status': 'incomplete', 'sampler_pid': os.getpid(),
                                 'game_pid': pid, 'attempts': attempts,
                                 'updated_at': utc_now(), 'error': str(error)})
            if attempts >= 2 or pid not in game_processes():
                raise
            time.sleep(10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/fire-code-capture')
    parser.add_argument('--check', action='store_true', help='Verify local build and report; do not wait or read the game.')
    args = parser.parse_args()
    if args.check:
        fingerprints()
        print(json.dumps({'status': 'local_build_matches', 'bytes_planned': TOTAL_BYTES,
                          'chunks': 6, 'pins': len(PINS)}))
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
        write_status(args.output, {'status': 'cancelled', 'updated_at': utc_now()})
        return 130
    except Exception as error:
        write_status(args.output, {'status': 'failed', 'updated_at': utc_now(), 'error': str(error)})
        print('Stopped: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
