"""One immediate, read-only Unit.flow_event EXE declared-code capture.

Uses the frozen setter sampler as a private profile, with only the already
observed Unit entry/PIN changed. Limits are unchanged: declared code <=4096B,
all process reads <=8192B/32RPM/32query/2s soft, including both Ship gates.
No Unit event invocation, Game writes, waiting, retries or extra callees.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
CORE_PATH = ROOT / 'tools/flow-exe-entry-code-capture.py'
CORE_SHA = 'e6915df8b097cc7bd40afd303bdd288054b82aa40b98e944afb475ff583ca2c0'
if hashlib.sha256(CORE_PATH.read_bytes()).hexdigest() != CORE_SHA:
    raise ValueError('FLOW_UNIT_FROZEN_CORE_CHANGED')
spec = importlib.util.spec_from_file_location('_flow_unit_event_exe_profile', CORE_PATH)
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)
REVISION = 'flow_exe_unit_event_declared_code_v1'
TARGET_MODULE = 'exe'
TARGET_NAME = 'Unit.flow_event'
TARGET_RVA = 0x413070
TARGET_PIN = '48895c2418574883ec20ba0100000048'
profile.REVISION, profile.TARGET_NAME, profile.TARGET_RVA, profile.TARGET_PIN = (
    REVISION, TARGET_NAME, TARGET_RVA, TARGET_PIN)


def run(output, dependencies=None, clock=time.perf_counter):
    folder = Path(output).resolve()
    if folder.exists():
        raise ValueError('FLOW_UNIT_OUTPUT_EXISTS: use a new evidence folder')
    folder.mkdir(parents=True)
    evidence = {'source_revision': REVISION, 'target_module': TARGET_MODULE,
                'target_name': TARGET_NAME, 'target_rva': TARGET_RVA, 'target_pin': TARGET_PIN,
                'complete': False, 'code_only': True, 'classification_ready': False,
                'contract_ready': False, 'native_written': False, 'native_called': False,
                'capture_attempted': False, 'attempts': 1,
                'sampler_source_sha256': CORE_SHA}
    budget = None
    try:
        evidence['pin_source'] = profile.validate_inventory()
        deps = dependencies if dependencies is not None else profile.load_dependencies()
        stamps = deps['fingerprints']()
        pids = tuple(deps['game_processes']())
        if len(pids) != 1:
            raise ValueError('FLOW_UNIT_EXPECTS_ONE_RUNNING_GAME')
        pid = pids[0]
        identity = deps['resolve_game'](pid)
        deps['validate_identity'](identity, stamps)
        profile.validate_module(identity)
        evidence.update(game_pid=pid, identity=identity, fingerprint=profile.FINGERPRINT)
        with deps['Process'](pid) as process:
            budget = profile.Budget(process, identity, clock)
            before = deps['ship_state'](budget, identity)
            evidence['ship_before'] = before
            if before['state'] != 3:
                raise ValueError('FLOW_UNIT_EXPECTS_SHIP')
            evidence['capture_attempted'] = True
            raw = profile.capture(budget, evidence)
            after = deps['ship_state'](budget, identity)
            evidence['ship_after'] = after
            if before != after:
                raise ValueError('FLOW_UNIT_SHIP_CHANGED')
            budget.time_gate()
        final = deps['resolve_game'](pid)
        deps['validate_identity'](final, stamps)
        if final != identity or tuple(deps['game_processes']()) != (pid,):
            raise ValueError('FLOW_UNIT_MODULE_CHANGED')
        budget.time_gate()
        binary, report = folder / 'unit-event.bin', folder / 'unit-event.json'
        evidence.update(complete=True, captured_at=datetime.now(timezone.utc).isoformat(),
                        ship_reads=4, ship_bytes_read=24, budget=budget.summary(),
                        read_records=budget.records,
                        binary_path=str(binary), sha256=hashlib.sha256(raw).hexdigest())
        binary.write_bytes(raw)
        report.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', 'utf8')
        status = {'status': 'complete', 'source_revision': REVISION,
                  'json_path': str(report), 'binary_path': str(binary), 'sha256': evidence['sha256']}
        profile.tail['write_status'](folder, status)
        return status
    except Exception as error:
        if budget is not None:
            evidence.update(budget=budget.summary(), read_records=budget.records)
        failure = {**evidence, 'status': 'failed', 'complete': False,
                   'error': str(error), 'partial_binary_saved': False,
                   'failed_at': datetime.now(timezone.utc).isoformat()}
        report = folder / 'unit-event.incomplete.json'
        report.write_text(json.dumps(failure, ensure_ascii=False, indent=2) + '\n', 'utf8')
        profile.tail['write_status'](folder, {**failure, 'json_path': str(report)})
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
