"""One bounded read of a missing projectile contact exit; no event/hook writes.

Exactly two previously captured call PINs (10 bytes) and one 768-byte code tail.
The code tail is read only after the PINs match. Ship gates use 24 bytes total.
The optional wait mode checks Ship every two seconds until one capture succeeds
or fails; it has no 120-second deadline and never retries a failed capture.
This diagnoses control flow; it never establishes a classified hit stream.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import runpy
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
PINS = ((0x13AE275, bytes.fromhex('e8b6e627ff')),
        (0x13AE28E, bytes.fromhex('e8ede927ff')))
TAIL = 0x13AE300
SIZE = 0x300
REVISION = 'direct_contact_tail_v1'
IMAGE_SIZE = 0x4744000
TOTAL_BYTES = 10 + SIZE
FINGERPRINT = {
    'exe_sha': 'f5fee03dcfdb2e553a4752c283590950ac13316b376d8196aa556ff0400d5f06',
    'dll_sha': '2e2c3b7c2500646dadd5f2b4c6e0504dbb7e7896139f64cddc0d1813c718f51e',
}


def capture(process, identity):
    base = identity['game_base']
    chunks = []
    def read(rva, length):
        at = base + rva
        if not (0 <= rva < rva + length <= identity['game_size']):
            raise ValueError('HIT_TAIL_RANGE_INVALID')
        region = process.query(at)
        if not (region['state'] == 0x1000 and region['type'] == 0x1000000
                and region['base'] <= at and at + length <= region['base'] + region['size']
                and not region['protect'] & 0x100 and region['protect'] & 0xff in (0x20, 0x40, 0x80)):
            raise ValueError('HIT_TAIL_CODE_UNREADABLE')
        raw = process.read(at, length)
        if len(raw) != length:
            raise ValueError('HIT_TAIL_SHORT_READ')
        chunks.append({'rva': rva, 'length': length})
        return raw
    pin_bytes = []
    for rva, expected in PINS:
        actual = read(rva, len(expected))
        if actual != expected:
            raise ValueError('HIT_TAIL_PIN_MISMATCH:' + hex(rva))
        pin_bytes.append(actual)
    tail = read(TAIL, SIZE)
    return b''.join(pin_bytes) + tail, chunks


def write_status(folder, value):
    pending = folder / ('status.' + uuid.uuid4().hex + '.tmp')
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', 'utf8')
    os.replace(pending, folder / 'status.json')


def saved_complete(folder):
    """Validate only local evidence, before any process enumeration or RPM."""
    folder = Path(folder).resolve()
    try:
        status = json.loads((folder / 'status.json').read_text('utf8'))
        report, binary = Path(status['json_path']), Path(status['binary_path'])
        if (status['status'] != 'complete' or status['source_revision'] != REVISION
                or report.parent.resolve() != folder
                or binary.parent.resolve() != folder):
            return None
        meta = json.loads(report.read_text('utf8'))
        with binary.open('rb') as stream:
            raw = stream.read(TOTAL_BYTES + 1)
        expected_chunks = [{'rva': rva, 'length': len(pin)} for rva, pin in PINS]
        expected_chunks.append({'rva': TAIL, 'length': SIZE})
        if (len(raw) != TOTAL_BYTES or meta['source_revision'] != REVISION
                or meta['complete'] is not True or meta['fingerprint'] != FINGERPRINT
                or meta['code_only'] is not True or meta['classification_ready'] is not False
                or meta['complete_stream'] is not False or meta['native_written'] is not False
                or meta['native_called'] is not False or meta['chunks'] != expected_chunks
                or meta['code_bytes_read'] != TOTAL_BYTES or meta['code_reads'] != 3
                or meta['ship_bytes_read'] != 24 or meta['ship_reads'] != 4
                or meta['tail_rva'] != TAIL or meta['tail_offset'] != 10
                or meta['tail_length'] != SIZE
                or Path(meta['binary_path']).resolve() != binary.resolve()
                or meta['sha256'] != hashlib.sha256(raw).hexdigest()
                or status['sha256'] != meta['sha256']
                or meta['ship_before'] != meta['ship_after']
                or meta['ship_before']['state'] != 3
                or not meta['ship_before']['context']
                or meta['identity']['game_size'] != IMAGE_SIZE
                or meta['identity']['game_base'] < 65536
                or meta['identity']['game_base'] % 4096):
            return None
        offset = 0
        for rva, pin in PINS:
            if not 0 <= rva < rva + len(pin) <= IMAGE_SIZE or raw[offset:offset + len(pin)] != pin:
                return None
            offset += len(pin)
        if not 0 <= TAIL < TAIL + SIZE <= IMAGE_SIZE:
            return None
        return {**status, 'cached': True}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def load_dependencies():
    original = runpy.run_path(str(ROOT / 'tools/hit-code-capture.py'))
    if original['FINGERPRINT'] != FINGERPRINT:
        raise ValueError('HIT_TAIL_BUILD_PROFILE_CHANGED')
    career = runpy.run_path(str(ROOT / 'tools/career-cache-capture.py'))
    from fire_code_windows import Process, resolve_game
    from probe_session import game_processes
    return {'fingerprints': original['fingerprints'], 'validate_identity': original['validate_identity'],
            'Process': Process, 'resolve_game': resolve_game, 'game_processes': game_processes,
            'ship_state': career['ship_state']}


def run(output, wait_for_ship=False, dependencies=None, sleep=time.sleep):
    """One success or failure, with optional low-rate readiness waiting only."""
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    cached = saved_complete(output)
    if cached:
        return cached
    progress = {'source_revision': REVISION, 'complete': False, 'code_only': True,
                'classification_ready': False, 'complete_stream': False,
                'native_written': False, 'native_called': False, 'wait_for_ship': bool(wait_for_ship),
                'capture_attempted': False, 'waiting_code_reads': 0,
                'ship_wait_polls': 0, 'ship_wait_read_calls': 0, 'ship_wait_bytes_read': 0,
                'wait_interval_seconds': 2, 'ship_wait_reads_per_poll_max': 2,
                'ship_wait_bytes_per_poll_max': 12}
    try:
        deps = dependencies if dependencies is not None else load_dependencies()
        stamps = deps['fingerprints']()
        while True:
            pids = tuple(deps['game_processes']())
            if not pids and wait_for_ship:
                write_status(output, {**progress, 'status': 'waiting_game'})
                sleep(2)
                continue
            if len(pids) != 1:
                raise ValueError('HIT_TAIL_EXPECTS_ONE_RUNNING_GAME')
            pid = pids[0]
            try:
                identity = deps['resolve_game'](pid)
            except FileNotFoundError:
                if not wait_for_ship:
                    raise
                write_status(output, {**progress, 'status': 'waiting_module', 'game_pid': pid})
                sleep(2)
                continue
            deps['validate_identity'](identity, stamps)
            if identity['game_size'] != IMAGE_SIZE:
                raise ValueError('HIT_TAIL_MODULE_INVALID')
            with deps['Process'](pid) as process:
                before = deps['ship_state'](process, identity)
                if before['state'] != 3:
                    if not wait_for_ship:
                        raise ValueError('HIT_TAIL_EXPECTS_SHIP')
                    progress['ship_wait_polls'] += 1
                    progress['ship_wait_read_calls'] += before['read_calls']
                    progress['ship_wait_bytes_read'] += before['read_bytes']
                    write_status(output, {**progress, 'status': 'waiting_ship', 'game_pid': pid,
                                          'last_native_state': before['name']})
                else:
                    # Reuse this sample as the capture's before gate: no extra Ship read.
                    progress.update(capture_attempted=True, game_pid=pid, identity=identity)
                    write_status(output, {**progress, 'status': 'capturing'})
                    binary, chunks = capture(process, identity)
                    after = deps['ship_state'](process, identity)
                    if after != before:
                        raise ValueError('HIT_TAIL_SHIP_CHANGED')
            if before['state'] != 3:
                sleep(2)
                continue
            final = deps['resolve_game'](pid)
            deps['validate_identity'](final, stamps)
            if final != identity or tuple(deps['game_processes']()) != (pid,):
                raise ValueError('HIT_TAIL_MODULE_CHANGED')
            name = 'hit-tail-' + uuid.uuid4().hex
            path = output / (name + '.bin')
            path.write_bytes(binary)
            result = {**progress, 'complete': True, 'captured_at': datetime.now(timezone.utc).isoformat(),
                      'game_pid': pid, 'identity': identity, 'fingerprint': FINGERPRINT,
                      'ship_before': before, 'ship_after': after, 'code_bytes_read': len(binary),
                      'ship_bytes_read': 24, 'code_reads': len(chunks), 'ship_reads': 4,
                      'chunks': chunks, 'tail_rva': TAIL, 'tail_offset': 10, 'tail_length': SIZE,
                      'binary_path': str(path), 'sha256': hashlib.sha256(binary).hexdigest(),
                      'pin_source': 'actual hit-classification-code-20261011T103354Z-6ac80883.bin'}
            report = output / (name + '.json')
            report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', 'utf8')
            status = {'status': 'complete', 'source_revision': REVISION,
                      'json_path': str(report), 'binary_path': str(path), 'sha256': result['sha256']}
            write_status(output, status)
            return {**status, 'cached': False}
    except Exception as error:
        failure = {**progress, 'status': 'failed', 'complete': False,
                   'failed_at': datetime.now(timezone.utc).isoformat(),
                   'error': str(error), 'partial_binary_saved': False}
        # Preserve the failed attempt separately; never relabel it as a complete BIN.
        report = output / ('hit-tail-' + uuid.uuid4().hex + '.incomplete.json')
        report.write_text(json.dumps(failure, ensure_ascii=False, indent=2) + '\n', 'utf8')
        write_status(output, {**failure, 'json_path': str(report)})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/hit-tail-code-capture')
    parser.add_argument('--wait-for-ship', action='store_true',
                        help='Wait every 2 seconds for a normal launch and Ship, then capture once and exit.')
    args = parser.parse_args()
    print(json.dumps(run(args.output, args.wait_for_ship), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
