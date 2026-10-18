"""One immediate read-only declaration capture of the field-candidate helper.

Source: two exact windows in the frozen section0 index. Fresh18B field-to-call
sequence names only EXE+2D4640 as its relative-call destination. The target's
fresh16B is unknown identity, checked again inside its <=4096B declared body.
All reads share8192B/40RPM/query/2s soft including PE/pdata/unwind/Ship. No
index rescan, heap/registry/argument read, native call, extra callee or retry.
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
REVISION = 'flow_field_candidate_shared_helper_declared_code_v1'
CORE = ROOT / 'tools/flow-exe-entry-code-capture.py'
CORE_SHA = 'e6915df8b097cc7bd40afd303bdd288054b82aa40b98e944afb475ff583ca2c0'
if hashlib.sha256(CORE.read_bytes()).hexdigest() != CORE_SHA:
    raise ValueError('FLOW_CONSUMER_FROZEN_CORE_CHANGED')
spec = importlib.util.spec_from_file_location('_flow_ref_shared_helper_profile', CORE)
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)
profile.MAX_READS = 40
SOURCE = ROOT / 'dist/flow-world-field-index-live-20261012-v1/field-index.json'
SOURCE_SHA = 'bf01525275432c93c0cc17a197b03b510afd42fd2cffb0b4dfd13949727d2415'
TARGET_RVA = 0x2D4640
TARGET_NAME = 'EXE_2D4640_field_candidate_shared_helper'
CALL_RVA = 0x3A9DC5
CALL_HEX = 'e876a8f2ff'
SOURCE_SEQUENCE_RVA = 0x3A9DB8
SOURCE_SEQUENCE_HEX = '8b91e0012300488b89d8012300e876a8f2ff'
profile.REVISION, profile.TARGET_RVA, profile.TARGET_NAME = REVISION, TARGET_RVA, TARGET_NAME


def validate_source(path=SOURCE):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA:
        raise ValueError('FLOW_CONSUMER_INDEX_SOURCE_CHANGED')
    meta = json.loads(raw)
    selected = [(0x3A9DBA, 'e0012300'), (0x3A9DC1, 'd8012300')]
    if (not meta.get('complete') or meta.get('truncated') or not meta.get('source_gates_verified')
            or meta.get('fingerprint') != profile.FINGERPRINT
            or (meta['section']['index'], meta['section']['rva'], meta['section']['virtual_size'],
                meta['section']['characteristics']) != (0, 0x1000, 20919884, 0x60000020)):
        raise ValueError('FLOW_CONSUMER_INDEX_SOURCE_PROFILE')
    windows = []
    for rva, pattern in selected:
        rows = [row for row in meta['candidates'] if row['rva'] == rva]
        if len(rows) != 1 or rows[0]['pattern_hex'] != pattern:
            raise ValueError('FLOW_CONSUMER_SOURCE_CANDIDATE')
        row = rows[0]
        window = bytes.fromhex(row['window_hex'])
        match_at = rva - row['window_rva']
        sequence_at = SOURCE_SEQUENCE_RVA - row['window_rva']
        call_at = CALL_RVA - row['window_rva']
        if (len(window) != row['window_bytes'] or row['match_offset'] != match_at
                or window[match_at:match_at + 4].hex() != pattern
                or sequence_at < 0
                or window[sequence_at:sequence_at + 18].hex() != SOURCE_SEQUENCE_HEX
                or window[call_at:call_at + 5].hex() != CALL_HEX
                or window[call_at] != 0xE8
                or CALL_RVA + 5 + struct.unpack_from('<i', window, call_at + 1)[0] != TARGET_RVA):
            raise ValueError('FLOW_CONSUMER_SOURCE_OPCODE_RELATIVE_CALL')
        windows.append({'candidate_rva': rva, 'pattern_hex': pattern,
                        'window_rva': row['window_rva'], 'window_hex': row['window_hex']})
    return {'path': str(Path(path).resolve()), 'sha256': SOURCE_SHA, 'windows': windows,
            'source_sequence_rva': SOURCE_SEQUENCE_RVA, 'source_sequence_hex': SOURCE_SEQUENCE_HEX,
            'call_rva': CALL_RVA, 'call_hex': CALL_HEX, 'relative_target_rva': TARGET_RVA,
            'world_provenance': 'UNKNOWN', 'callback_consumer_proven': False}


def capture(budget, evidence):
    caller = budget.read_module(SOURCE_SEQUENCE_RVA, 18, 'fresh_field_to_call_sequence', True)
    evidence['fresh_source_sequence'] = {'module': 'exe', 'rva': SOURCE_SEQUENCE_RVA,
                                         'hex': caller.hex(), 'matched': caller.hex() == SOURCE_SEQUENCE_HEX}
    if caller.hex() != SOURCE_SEQUENCE_HEX:
        raise ValueError('FLOW_CONSUMER_FRESH_SOURCE_SEQUENCE_CHANGED')
    evidence['pe_declaration'] = profile.read_pe_declaration(budget)
    fresh = budget.read_module(TARGET_RVA, 16, 'fresh_unknown_helper_entry', True)
    evidence['fresh_entry_prefix'] = {'module': 'exe', 'rva': TARGET_RVA, 'hex': fresh.hex(),
                                      'api_identity_verified': False}
    # Private metadata profile: unknown prefix is a same-attempt consistency
    # check, never an invented target PIN or a public API identity.
    reader = profile.private_reader()
    reader.TARGET_PIN = fresh.hex()
    journal, nodes = [], []
    evidence.update(exception_records=journal, unwind_chain=nodes)
    begin, end = reader.find_function(budget, journal)
    evidence.update(function_begin=begin, function_end=end)
    reader.unwind_ancestry((begin, end, journal[-1]['unwind_rva']),
                          lambda rva, size: reader.checked_metadata_read(budget, rva, size), nodes)
    selected = reader.ancestry_ranges(nodes)
    budget.require_capacity(sum(length for _, _, length in selected) + 12, len(selected) + 2)
    ranges, chunks, offset = [], [], 0
    for i, (_, rva, length) in enumerate(selected):
        name = TARGET_NAME if rva <= TARGET_RVA < rva + length else 'declared_unwind_parent_' + str(i)
        chunks.append(budget.read_module(rva, length, 'declared_shared_helper_code', True))
        ranges.append({'name': name, 'module': 'exe', 'rva': rva,
                       'length': length, 'binary_offset': offset})
        offset += length
    raw = b''.join(chunks)
    target = next(row for row in ranges if row['rva'] <= TARGET_RVA < row['rva'] + row['length'])
    entry_offset = target['binary_offset'] + TARGET_RVA - target['rva']
    if raw[entry_offset:entry_offset + 16] != fresh:
        raise ValueError('FLOW_CONSUMER_ENTRY_BODY_CHANGED')
    evidence.update(ranges=ranges, binary_entry_offset=entry_offset, code_bytes=len(raw),
                    entry_body_consistent=True, declared_code_complete=True,
                    logical_function_complete=False, all_sibling_fragments_captured=False,
                    boundary_kind='target_range_plus_bounded_unwind_ancestry')
    return raw


def run(output, dependencies=None, clock=time.perf_counter):
    folder = Path(output).resolve()
    if folder.exists():
        raise ValueError('FLOW_CONSUMER_OUTPUT_EXISTS: use a new evidence folder')
    folder.mkdir(parents=True)
    evidence = {'source_revision': REVISION, 'target_module': 'exe', 'target_rva': TARGET_RVA,
                'target_name': TARGET_NAME, 'complete': False, 'code_only': True,
                'api_identity_verified': False, 'callback_consumer_proven': False,
                'classification_ready': False, 'contract_ready': False,
                'native_called': False, 'native_written': False,
                'registry_reads': 0, 'index_rescanned': False, 'extra_callee_reads': 0,
                'capture_attempted': False, 'attempts': 1, 'sampler_source_sha256': CORE_SHA}
    budget = None
    try:
        evidence['source'] = validate_source()
        deps = dependencies if dependencies is not None else profile.load_dependencies()
        stamps = deps['fingerprints']()
        pids = tuple(deps['game_processes']())
        if len(pids) != 1:
            raise ValueError('FLOW_CONSUMER_EXPECTS_ONE_RUNNING_GAME')
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
                raise ValueError('FLOW_CONSUMER_EXPECTS_SHIP')
            evidence['capture_attempted'] = True
            raw = capture(budget, evidence)
            after = deps['ship_state'](budget, identity)
            evidence['ship_after'] = after
            if before != after:
                raise ValueError('FLOW_CONSUMER_SHIP_CHANGED')
            budget.time_gate()
        final = deps['resolve_game'](pid)
        deps['validate_identity'](final, stamps)
        if final != identity or tuple(deps['game_processes']()) != (pid,):
            raise ValueError('FLOW_CONSUMER_MODULE_CHANGED')
        budget.time_gate()
        binary, report = folder / 'consumer.bin', folder / 'consumer.json'
        evidence.update(complete=True, budget=budget.summary(), read_records=budget.records,
                        captured_at=datetime.now(timezone.utc).isoformat(),
                        ship_reads=4, ship_bytes_read=24,
                        binary_path=str(binary), sha256=hashlib.sha256(raw).hexdigest())
        binary.write_bytes(raw)
        report.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', 'utf8')
        status = {'status': 'complete', 'source_revision': REVISION, 'json_path': str(report),
                  'binary_path': str(binary), 'sha256': evidence['sha256']}
        profile.tail['write_status'](folder, status)
        return status
    except Exception as error:
        if budget is not None:
            evidence.update(budget=budget.summary(), read_records=budget.records)
        failure = {**evidence, 'status': 'failed', 'complete': False,
                   'error': str(error), 'partial_binary_saved': False,
                   'failed_at': datetime.now(timezone.utc).isoformat()}
        report = folder / 'consumer.incomplete.json'
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
