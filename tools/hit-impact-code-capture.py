"""Read one fixed impact candidate once, only in Ship; never install a hook.

The actual tail captured 13AE4D3 -> 13B2BE0. Verify that five-byte call,
then read the 1824-byte candidate window. This is code, not hit events.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import runpy
import sys
from types import FunctionType
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
REVISION = 'impact_candidate_v1'
PIN_RVA, PIN = 0x13AE4D3, bytes.fromhex('e808470000')
BODY_RVA, BODY_LENGTH = 0x13B2BE0, 0x720
TOTAL = len(PIN) + BODY_LENGTH
SOURCE_SHA = '97c623597ef5c32e992a04d6daae808e6500b01705076029452a02dc787157e9'
PROFILE = runpy.run_path(str(ROOT / 'tools/hit-tail-code-capture.py'))
FINGERPRINT = PROFILE['FINGERPRINT']
EXPECTED_CHUNKS = [{'rva': PIN_RVA, 'length': len(PIN)},
                   {'rva': BODY_RVA, 'length': BODY_LENGTH}]
# Reuse its already tested page/range/PIN/short-read checks with a fixed profile.
# Do not reuse the tail runner: its metadata/cache describes a different window.
_globals = dict(PROFILE['capture'].__globals__, PINS=((PIN_RVA, PIN),),
                TAIL=BODY_RVA, SIZE=BODY_LENGTH)
capture = FunctionType(PROFILE['capture'].__code__, _globals)


def saved_complete(folder):
    folder = Path(folder).resolve()
    try:
        status = json.loads((folder / 'status.json').read_text('utf8'))
        report, binary = Path(status['json_path']), Path(status['binary_path'])
        if (status['status'] != 'complete' or status['source_revision'] != REVISION
                or report.parent.resolve() != folder or binary.parent.resolve() != folder):
            return None
        meta = json.loads(report.read_text('utf8'))
        with binary.open('rb') as stream:
            raw = stream.read(TOTAL + 1)
        if (len(raw) != TOTAL or raw[:len(PIN)] != PIN
                or hashlib.sha256(raw).hexdigest() != status['sha256']
                or meta['sha256'] != status['sha256'] or meta['source_revision'] != REVISION
                or meta['fingerprint'] != FINGERPRINT or meta['complete'] is not True
                or meta['native_written'] is not False or meta['native_called'] is not False
                or meta['classification_ready'] is not False or meta['code_only'] is not True
                or meta['chunks'] != EXPECTED_CHUNKS or meta['code_bytes_read'] != TOTAL
                or meta['code_reads'] != 2 or meta['ship_bytes_read'] != 24
                or meta['ship_reads'] != 4 or meta['body_rva'] != BODY_RVA
                or meta['body_offset'] != len(PIN) or meta['body_length'] != BODY_LENGTH
                or meta['ship_before'] != meta['ship_after']
                or meta['ship_before']['state'] != 3 or not meta['ship_before']['context']
                or meta['identity']['game_size'] != PROFILE['IMAGE_SIZE']):
            return None
        return {**status, 'cached': True}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def run(output, dependencies=None):
    folder = Path(output).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    cached = saved_complete(folder)
    if cached:
        return cached
    meta = {'source_revision': REVISION, 'complete': False, 'code_only': True,
            'classification_ready': False, 'native_written': False, 'native_called': False,
            'capture_attempted': False, 'source_tail_sha256': SOURCE_SHA,
            'candidate_only': True, 'complete_function': False, 'complete_stream': False}
    try:
        deps = dependencies if dependencies is not None else PROFILE['load_dependencies']()
        stamps = deps['fingerprints']()
        pids = tuple(deps['game_processes']())
        if len(pids) != 1:
            raise ValueError('HIT_IMPACT_EXPECTS_ONE_RUNNING_GAME')
        pid = pids[0]
        identity = deps['resolve_game'](pid)
        deps['validate_identity'](identity, stamps)
        if identity['game_size'] != PROFILE['IMAGE_SIZE']:
            raise ValueError('HIT_IMPACT_MODULE_INVALID')
        with deps['Process'](pid) as process:
            before = deps['ship_state'](process, identity)
            if before['state'] != 3:
                raise ValueError('HIT_IMPACT_EXPECTS_SHIP')
            meta.update(capture_attempted=True, game_pid=pid, identity=identity)
            raw, chunks = capture(process, identity)
            after = deps['ship_state'](process, identity)
            if before != after:
                raise ValueError('HIT_IMPACT_SHIP_CHANGED')
        final = deps['resolve_game'](pid)
        deps['validate_identity'](final, stamps)
        if final != identity or tuple(deps['game_processes']()) != (pid,):
            raise ValueError('HIT_IMPACT_MODULE_CHANGED')
        stem = 'hit-impact-' + uuid.uuid4().hex
        binary, report = folder / (stem + '.bin'), folder / (stem + '.json')
        binary.write_bytes(raw)
        meta.update(complete=True, captured_at=datetime.now(timezone.utc).isoformat(),
                    fingerprint=FINGERPRINT, ship_before=before, ship_after=after,
                    code_bytes_read=len(raw), code_reads=len(chunks),
                    ship_bytes_read=24, ship_reads=4, chunks=chunks,
                    body_rva=BODY_RVA, body_length=BODY_LENGTH, body_offset=len(PIN),
                    binary_path=str(binary), sha256=hashlib.sha256(raw).hexdigest())
        report.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', 'utf8')
        status = {'status': 'complete', 'source_revision': REVISION, 'json_path': str(report),
                  'binary_path': str(binary), 'sha256': meta['sha256']}
        PROFILE['write_status'](folder, status)
        return {**status, 'cached': False}
    except Exception as error:
        failure = {**meta, 'status': 'failed', 'error': str(error),
                   'failed_at': datetime.now(timezone.utc).isoformat(),
                   'partial_binary_saved': False}
        report = folder / ('hit-impact-' + uuid.uuid4().hex + '.incomplete.json')
        report.write_text(json.dumps(failure, ensure_ascii=False, indent=2) + '\n', 'utf8')
        PROFILE['write_status'](folder, {**failure, 'json_path': str(report)})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/hit-impact-code-capture')
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.output), ensure_ascii=False, indent=2))
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
