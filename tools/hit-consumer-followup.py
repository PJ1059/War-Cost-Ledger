"""One Ship-only read of the impact consumer reached by a proven actual call.

Verify 12A7A69 e8124b69ff -> 93C580 before reading the consumer's declared
exception-table range and bounded unwind ancestry. Code only, not hit records.
Waiting checks Ship every 2s without a deadline; failure is never retried.
Metadata/body <=8192B/32 reads; caller adds5B/1, before/afterShip adds24B/4.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import hashlib
import json
from pathlib import Path
import struct
import time

ROOT = Path(__file__).resolve().parents[1]
REVISION = 'impact_consumer_declared_code_v1'
CALLER, CALL_PIN, CALLEE = 0x12A7A69, 'e8124b69ff', 0x93C580
SOURCE_SHA = '409b7f0dcef3e95a1a975119cb779282b3f6f93f19ea7c837d9c42c559c39206'
spec = importlib.util.spec_from_file_location('impact_consumer_session',
                                            ROOT / 'tools/hit-queue-consumer-code-capture.py')
session = importlib.util.module_from_spec(spec)
spec.loader.exec_module(session)
session.REVISION = session.reader.REVISION = REVISION
session.reader.TARGET_RVA, session.reader.TARGET_PIN = CALLEE, ''
session.reader.SOURCE_REFERENCE = 'Actual Drain body SHA' + SOURCE_SHA + '; call12A7A69 ->93C580'
body_capture = session.reader.capture
window_factory = session.reader.window_capture


def body_window(ranges):
    ranges = tuple(('impact_consumer_declared_' + str(i), rva, n)
                   for i, (_, rva, n) in enumerate(ranges))
    window = window_factory(ranges)
    window.PINS = ()  # Callee bytes unknown; its actual callsite is separately proven first.
    return window


session.reader.window_capture = body_window
caller_window = window_factory((('impact_consumer_callsite', CALLER, 5),))
caller_window.PINS = ((CALLER, CALL_PIN),)


def capture(process, identity, clock=time.perf_counter, evidence=None):
    prefix, pin_meta = caller_window.capture(process, identity, sleep=lambda _: None)
    target = CALLER + 5 + struct.unpack_from('<i', prefix, 1)[0]
    if target != CALLEE:
        raise ValueError('HIT_CONSUMER_CALL_TARGET_CHANGED')
    raw, meta = body_capture(process, identity, clock, evidence)
    # Retain the original body metadata so its declared boundaries can be independently checked.
    body_meta = dict(meta)
    binary = prefix + raw
    meta = dict(meta)
    meta.update(candidate_body=body_meta, source_drain_sha256=SOURCE_SHA,
                caller_rva=CALLER, caller_pin=CALL_PIN, callee_rva=CALLEE,
                caller_bytes_read=5, caller_reads=1, body_binary_offset=5,
                bytes_written=len(binary), binary_sha256=hashlib.sha256(binary).hexdigest(),
                candidate_only=True, logical_function_complete=False,
                complete_stream=False, classification_ready=False,
                pins=pin_meta['pins'])
    meta['ranges'] = pin_meta['ranges'] + [dict(r, binary_offset=r['binary_offset'] + 5)
                                         for r in body_meta['ranges']]
    meta['chunks'] = pin_meta['chunks'] + body_meta['chunks']
    return binary, meta


session.reader.capture = capture


def verify_saved(meta, binary):
    if (meta['source_revision'] != REVISION or meta['callee_rva'] != CALLEE
            or meta['caller_rva'] != CALLER or meta['caller_pin'] != CALL_PIN
            or meta['source_drain_sha256'] != SOURCE_SHA
            or binary[:5] != bytes.fromhex(CALL_PIN)
            or meta['body_binary_offset'] != 5
            or meta['classification_ready'] is not False
            or meta['complete_stream'] is not False
            or meta['native_written'] is not False or meta['native_called'] is not False
            or meta['sha256'] != hashlib.sha256(binary).hexdigest()):
        raise ValueError('HIT_CONSUMER_SAVED_PROFILE')
    session.reader.verify_saved(meta['candidate_body'], binary[5:])
    expected = [{'name': 'impact_consumer_callsite', 'rva': CALLER, 'length': 5, 'binary_offset': 0}]
    expected += [dict(r, binary_offset=r['binary_offset'] + 5)
                 for r in meta['candidate_body']['ranges']]
    if meta['ranges'] != expected:
        raise ValueError('HIT_CONSUMER_SAVED_RANGES')


def run(output, wait_for_ship=False, dependencies=None, sleep=time.sleep):
    folder = Path(output).resolve()
    if folder.exists():
        raise ValueError('HIT_CONSUMER_OUTPUT_EXISTS: use a new evidence folder')
    folder.mkdir(parents=True)
    progress = {'source_revision': REVISION, 'capture_attempted': False,
                'waiting_code_reads': 0, 'ship_wait_polls': 0,
                'ship_wait_bytes_read': 0, 'ship_wait_read_calls': 0,
                'wait_interval_seconds': 2, 'timeout_seconds': None,
                'native_written': False, 'native_called': False,
                'classification_ready': False, 'sampler_pid': __import__('os').getpid()}
    try:
        deps = dependencies if dependencies is not None else session.tail['load_dependencies']()
        stamps = deps['fingerprints']()
        while wait_for_ship:
            pids = tuple(deps['game_processes']())
            if not pids:
                session.tail['write_status'](folder, {**progress, 'status': 'waiting_game'})
                sleep(2)
                continue
            if len(pids) != 1:
                raise ValueError('HIT_CONSUMER_EXPECTS_ONE_GAME')
            try:
                identity = deps['resolve_game'](pids[0])
            except FileNotFoundError:
                session.tail['write_status'](folder, {**progress, 'status': 'waiting_module'})
                sleep(2)
                continue
            deps['validate_identity'](identity, stamps)
            session.reader.validate_module(identity)
            with deps['Process'](pids[0]) as process:
                ready = deps['ship_state'](process, identity)
            progress['ship_wait_polls'] += 1
            progress['ship_wait_bytes_read'] += ready['read_bytes']
            progress['ship_wait_read_calls'] += ready['read_calls']
            if ready['state'] == 3:
                break
            session.tail['write_status'](folder, {**progress, 'status': 'waiting_ship',
                                                'game_pid': pids[0], 'last_native_state': ready['name']})
            sleep(2)
        progress['capture_attempted'] = True
        session.tail['write_status'](folder, {**progress, 'status': 'capturing'})
        # Recheck Ship in a fresh context immediately before the actual capture.
        actual_deps = dict(deps, fingerprints=lambda: stamps)
        status = session.run(folder / 'capture', actual_deps)
        meta = json.loads(Path(status['json_path']).read_text('utf8'))
        raw = Path(status['binary_path']).read_bytes()
        verify_saved(meta, raw)
        result = {**progress, **status, 'completed_at': datetime.now(timezone.utc).isoformat()}
        session.tail['write_status'](folder, result)
        return result
    except Exception as error:
        failure = {**progress, 'status': 'failed', 'complete': False,
                   'failed_at': datetime.now(timezone.utc).isoformat(), 'error': str(error)}
        session.tail['write_status'](folder, failure)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--wait-for-ship', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.output, args.wait_for_ship), ensure_ascii=False, indent=2))
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
