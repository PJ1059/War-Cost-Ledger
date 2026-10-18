"""One Ship-only read of the proven damage-system drain, within unwind bounds.

Find only the RUNTIME_FUNCTION containing its six-byte queue0 count PIN.
Reuse the existing tested metadata search, <=4KiB declared code ranges.
Metadata/code budget: <=8192 bytes/32 reads/2s soft; Ship adds 24B/4 reads.
No battle data or native writes/calls.
The purpose is to locate the newly proven 0x50 impact queue consumer.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
REVISION = 'impact_queue_drain_code_v1'
TARGET_RVA, TARGET_PIN = 0x12A6F17, '8b8120112000'
spec = importlib.util.spec_from_file_location('impact_queue_drain_metadata',
                                            ROOT / 'tools/recon_chat_code_capture.py')
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)
reader.REVISION, reader.TARGET_RVA, reader.TARGET_PIN = REVISION, TARGET_RVA, TARGET_PIN
reader.SOURCE_REFERENCE = 'HD2Runtime dcd996d research_event_combat.py queue_drain PINs'
tail = runpy.run_path(str(ROOT / 'tools/hit-tail-code-capture.py'))


def run(output, dependencies=None):
    folder = Path(output).resolve()
    if folder.exists():
        raise ValueError('HIT_DRAIN_OUTPUT_EXISTS: use a new evidence folder')
    folder.mkdir(parents=True)
    evidence = {'source_revision': REVISION, 'complete': False,
                'code_only': True, 'classification_ready': False,
                'native_written': False, 'native_called': False, 'capture_attempted': False}
    try:
        deps = dependencies if dependencies is not None else tail['load_dependencies']()
        stamps = deps['fingerprints']()
        pids = tuple(deps['game_processes']())
        if len(pids) != 1:
            raise ValueError('HIT_DRAIN_EXPECTS_ONE_RUNNING_GAME')
        pid = pids[0]
        identity = deps['resolve_game'](pid)
        deps['validate_identity'](identity, stamps)
        reader.validate_module(identity)
        with deps['Process'](pid) as process:
            before = deps['ship_state'](process, identity)
            if before['state'] != 3:
                raise ValueError('HIT_DRAIN_EXPECTS_SHIP')
            evidence.update(capture_attempted=True, game_pid=pid, identity=identity)
            raw, metadata = reader.capture(process, identity, evidence=evidence)
            after = deps['ship_state'](process, identity)
            if before != after:
                raise ValueError('HIT_DRAIN_SHIP_CHANGED')
        final = deps['resolve_game'](pid)
        deps['validate_identity'](final, stamps)
        if final != identity or tuple(deps['game_processes']()) != (pid,):
            raise ValueError('HIT_DRAIN_MODULE_CHANGED')
        binary, report = folder / 'drain.bin', folder / 'drain.json'
        binary.write_bytes(raw)
        evidence.update(metadata, complete=True, code_only=True, classification_ready=False,
                        captured_at=datetime.now(timezone.utc).isoformat(),
                        game_pid=pid, identity=identity, fingerprint=tail['FINGERPRINT'],
                        ship_before=before, ship_after=after, ship_bytes_read=24, ship_reads=4,
                        binary_path=str(binary), sha256=hashlib.sha256(raw).hexdigest())
        report.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', 'utf8')
        status = {'status': 'complete', 'source_revision': REVISION,
                  'json_path': str(report), 'binary_path': str(binary), 'sha256': evidence['sha256']}
        tail['write_status'](folder, status)
        return status
    except Exception as error:
        failure = {**evidence, 'status': 'failed', 'complete': False, 'error': str(error),
                   'failed_at': datetime.now(timezone.utc).isoformat(), 'partial_binary_saved': False}
        report = folder / 'drain.incomplete.json'
        report.write_text(json.dumps(failure, ensure_ascii=False, indent=2) + '\n', 'utf8')
        tail['write_status'](folder, {**failure, 'json_path': str(report)})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.output), ensure_ascii=False, indent=2))
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
