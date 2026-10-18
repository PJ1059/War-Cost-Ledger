"""One immediate read-only8B snippet at the proven EDX==-2 branch target.

Fresh field-to-call18B and the entire frozen24B prologue must match first.
Only8B at EXE+2D478E follow, with before/afterShip and EXE/Game source gates.
128B/16RPM/query/2s soft, no pdata search, nonnil body, target identity claim,
heap/registry/arguments/native calls/writes, waiting, retries or expansion.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
REVISION = 'flow_field_candidate_minus2_branch_snippet_v1'
HELPER_TOOL = ROOT / 'tools/flow-world-ref-consumer-code-capture.py'
HELPER_TOOL_SHA = 'c014cfab80346b3d815dc75084805dbe1268f5b4309c9067662b69e07ce86d11'
if hashlib.sha256(HELPER_TOOL.read_bytes()).hexdigest() != HELPER_TOOL_SHA:
    raise ValueError('FLOW_NOREF_FROZEN_HELPER_CHANGED')
spec = importlib.util.spec_from_file_location('_flow_noref_source', HELPER_TOOL)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
helper.profile.MAX_BYTES, helper.profile.MAX_READS = 128, 16
SOURCE = ROOT / 'dist/flow-world-ref-consumer-live-20261013-v1'
SOURCE_BIN_SHA = '230dc0afb9d547afceb7c458a9ff17d50b6c5371154195c7bd81489bef72c657'
SOURCE_META_SHA = '5fa88a03d2a213b103f983a5fb33e7c16bc1fc3450d4e7606cd38fd86daf4bbd'
PROLOGUE_RVA = 0x2D4640
BRANCH_FROM_RVA = 0x2D4643
BRANCH_TARGET_RVA = 0x2D478E
SNIPPET_BYTES = 8


def validate_source(folder=SOURCE):
    folder = Path(folder)
    raw, meta_raw = (folder / 'consumer.bin').read_bytes(), (folder / 'consumer.json').read_bytes()
    if (hashlib.sha256(raw).hexdigest() != SOURCE_BIN_SHA
            or hashlib.sha256(meta_raw).hexdigest() != SOURCE_META_SHA):
        raise ValueError('FLOW_NOREF_SOURCE_CHANGED')
    meta = json.loads(meta_raw)
    if (len(raw) != 24 or not meta.get('complete') or meta.get('target_module') != 'exe'
            or meta.get('fingerprint') != helper.profile.FINGERPRINT
            or (meta.get('function_begin'), meta.get('function_end')) != (PROLOGUE_RVA, PROLOGUE_RVA + 24)
            or meta.get('fresh_source_sequence', {}).get('hex') != helper.SOURCE_SEQUENCE_HEX
            or not meta.get('fresh_source_sequence', {}).get('matched')
            or meta.get('logical_function_complete') is not False):
        raise ValueError('FLOW_NOREF_SOURCE_PROFILE')
    branch_at = BRANCH_FROM_RVA - PROLOGUE_RVA
    if (raw[:3] != bytes.fromhex('83fafe')
            or raw[branch_at:branch_at + 2] != b'\x0f\x84'
            or BRANCH_FROM_RVA + 6 + struct.unpack_from('<i', raw, branch_at + 2)[0] != BRANCH_TARGET_RVA):
        raise ValueError('FLOW_NOREF_SOURCE_RELATIVE_BRANCH')
    return raw, {'binary_path': str((folder / 'consumer.bin').resolve()), 'binary_sha256': SOURCE_BIN_SHA,
                 'metadata_path': str((folder / 'consumer.json').resolve()), 'metadata_sha256': SOURCE_META_SHA,
                 'prologue_rva': PROLOGUE_RVA, 'prologue_bytes': 24, 'prologue_hex': raw.hex(),
                 'condition': 'EDX == -2', 'branch_rva': BRANCH_FROM_RVA,
                 'branch_hex': raw[branch_at:branch_at + 6].hex(), 'branch_target_rva': BRANCH_TARGET_RVA,
                 'logical_function_complete': False, 'callback_consumer_proven': False}


def run(output, dependencies=None, clock=time.perf_counter):
    folder = Path(output).resolve()
    if folder.exists():
        raise ValueError('FLOW_NOREF_OUTPUT_EXISTS: use a new evidence folder')
    folder.mkdir(parents=True)
    evidence = {'source_revision': REVISION, 'target_module': 'exe', 'target_rva': BRANCH_TARGET_RVA,
                'snippet_bytes': SNIPPET_BYTES, 'complete': False, 'code_only': True,
                'function_identity_claimed': False, 'logical_function_complete': False,
                'callback_consumer_proven': False, 'classification_ready': False,
                'native_called': False, 'native_written': False, 'registry_reads': 0,
                'nonnil_body_read': False, 'extra_callee_reads': 0,
                'capture_attempted': False, 'attempts': 1}
    budget = None
    try:
        source_raw, evidence['source'] = validate_source()
        deps = dependencies if dependencies is not None else helper.profile.load_dependencies()
        stamps = deps['fingerprints']()
        pids = tuple(deps['game_processes']())
        if len(pids) != 1:
            raise ValueError('FLOW_NOREF_EXPECTS_ONE_RUNNING_GAME')
        pid = pids[0]
        identity = deps['resolve_game'](pid)
        deps['validate_identity'](identity, stamps)
        helper.profile.validate_module(identity)
        evidence.update(game_pid=pid, identity=identity, fingerprint=helper.profile.FINGERPRINT)
        with deps['Process'](pid) as process:
            budget = helper.profile.Budget(process, identity, clock)
            before = deps['ship_state'](budget, identity)
            evidence['ship_before'] = before
            if before['state'] != 3:
                raise ValueError('FLOW_NOREF_EXPECTS_SHIP')
            caller = budget.read_module(helper.SOURCE_SEQUENCE_RVA, 18, 'fresh_field_to_call_sequence', True)
            evidence['fresh_source_sequence'] = {'rva': helper.SOURCE_SEQUENCE_RVA,
                                                 'hex': caller.hex(), 'matched': caller.hex() == helper.SOURCE_SEQUENCE_HEX}
            if caller.hex() != helper.SOURCE_SEQUENCE_HEX:
                raise ValueError('FLOW_NOREF_FRESH_CALLER_CHANGED')
            prologue = budget.read_module(PROLOGUE_RVA, 24, 'fresh_whole24B_prologue', True)
            evidence['fresh_whole_prologue'] = {'rva': PROLOGUE_RVA, 'hex': prologue.hex(),
                                                 'matched': prologue == source_raw}
            if prologue != source_raw:
                raise ValueError('FLOW_NOREF_FRESH_PROLOGUE_CHANGED')
            budget.require_capacity(SNIPPET_BYTES + 12, 1 + 2)
            evidence['capture_attempted'] = True
            snippet = budget.read_module(BRANCH_TARGET_RVA, SNIPPET_BYTES, 'minus2_branch_snippet', True)
            after = deps['ship_state'](budget, identity)
            evidence['ship_after'] = after
            if before != after:
                raise ValueError('FLOW_NOREF_SHIP_CHANGED')
            budget.time_gate()
        final = deps['resolve_game'](pid)
        deps['validate_identity'](final, stamps)
        if final != identity or tuple(deps['game_processes']()) != (pid,):
            raise ValueError('FLOW_NOREF_MODULE_CHANGED')
        budget.time_gate()
        binary, report = folder / 'no-ref.bin', folder / 'no-ref.json'
        evidence.update(complete=True, budget=budget.summary(), read_records=budget.records,
                        captured_at=datetime.now(timezone.utc).isoformat(),
                        ranges=[{'module': 'exe', 'rva': BRANCH_TARGET_RVA, 'length': 8, 'binary_offset': 0}],
                        binary_path=str(binary), sha256=hashlib.sha256(snippet).hexdigest(),
                        decoded=False, terminator_or_return_semantics='NOT_YET_DECODED')
        binary.write_bytes(snippet)
        report.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', 'utf8')
        status = {'status': 'complete', 'source_revision': REVISION, 'json_path': str(report),
                  'binary_path': str(binary), 'sha256': evidence['sha256']}
        helper.profile.tail['write_status'](folder, status)
        return status
    except Exception as error:
        if budget is not None:
            evidence.update(budget=budget.summary(), read_records=budget.records)
        failure = {**evidence, 'status': 'failed', 'complete': False,
                   'error': str(error), 'partial_binary_saved': False,
                   'failed_at': datetime.now(timezone.utc).isoformat()}
        report = folder / 'no-ref.incomplete.json'
        report.write_text(json.dumps(failure, ensure_ascii=False, indent=2) + '\n', 'utf8')
        helper.profile.tail['write_status'](folder, {**failure, 'json_path': str(report)})
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
