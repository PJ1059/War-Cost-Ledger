"""One fixed104B declared parent fragment, no metadata search/chain/callee.

Caller13F76D5 and declared .pdata68128 are frozen-source facts. Original
locator snapshots and actual getterPIN/Title2-or-Ship3/PID/module gates
surround caller5/record12/body104/record12/caller5. Shared16KiB/24RPM-query/
2s soft. The single declaration fragment is not a complete logical function.
No native Game call/write,UW/handler/table/heap read,retry/wait or RVA CLI.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import time

ROOT = Path(__file__).resolve().parents[1]
REVISION = 'contact_fixed_parent104_declaration_fragment_v1'
FOLLOWUP = ROOT / 'tools/hit-game-plugin-entry-window-capture.py'
FOLLOWUP_SHA = '1f346fdce4b18d10dbc5bd4a9862eebb6ea6a8a7f5aa75d9ab24baeff851d8d8'
UNWIND_SOURCE = ROOT / 'dist/hit-inline-unwind-20261012-117bef92/drain.json'
UNWIND_SHA = '17b6da0c864f89950026e8ec1934dce0f436053462b46c392fb3a26777e7c839'
FORWARDER_SOURCE = ROOT / 'dist/hit-contact-forwarder-live-20261013-v1'
FORWARDER_SHA = 'ec16ee80d1113343d4725612b2ec296fd0eb4c1cb867ff9a5b7177e56a3f1b03'
FORWARDER_BIN_SHA = '9358990585caedb3082b2ffd9303cc31dac236b80102941c5fa46699a2df7278'
PARENT_RVA, PARENT_END, UNWIND_RVA = 0x13AC1F0, 0x13AC258, 0x25114C0
RECORD_RVA, RECORD_INDEX = 0x409AD8C, 68128
RECORD_HEX = 'f0c13a0158c23a01c0145102'
CALLER_RVA, CALLER_HEX = 0x13F76D5, 'e9164bfbff'


def private_followup():
    if hashlib.sha256(FOLLOWUP.read_bytes()).hexdigest() != FOLLOWUP_SHA:
        raise ValueError('PARENT104_FROZEN_READER_CHANGED')
    spec = importlib.util.spec_from_file_location('_parent104_fixed_read_source', FOLLOWUP)
    followup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(followup)
    return followup


def validate_sources(fingerprint):
    raw = UNWIND_SOURCE.read_bytes()
    forwarder_raw = (FORWARDER_SOURCE / 'forwarder.json').read_bytes()
    binary = (FORWARDER_SOURCE / 'forwarder.bin').read_bytes()
    if (hashlib.sha256(raw).hexdigest() != UNWIND_SHA
            or hashlib.sha256(forwarder_raw).hexdigest() != FORWARDER_SHA
            or len(binary) != 74 or hashlib.sha256(binary).hexdigest() != FORWARDER_BIN_SHA):
        raise ValueError('PARENT104_FIXED_SOURCE_CHANGED')
    meta, forwarder = json.loads(raw), json.loads(forwarder_raw)
    if (not meta.get('complete') or meta.get('fingerprint') != fingerprint
            or not forwarder.get('complete') or forwarder.get('fingerprint') != fingerprint
            or forwarder.get('sha256') != FORWARDER_BIN_SHA
            or forwarder.get('function_begin') != 0x13F7690
            or forwarder.get('function_end') != 0x13F76DA
            or forwarder.get('target_rva') != CALLER_RVA
            or forwarder.get('binary_jmp_offset') != 69 or binary[69:].hex() != CALLER_HEX
            or CALLER_RVA + 5 + struct.unpack_from('<i', binary, 70)[0] != PARENT_RVA):
        raise ValueError('PARENT104_FIXED_SOURCE_PROFILE')
    site = next(row for row in meta['sites'] if row['name'] == 'contact_begin')
    rows = [row for row in site['exception_records'] if row['index'] == RECORD_INDEX]
    if (len(rows) != 1 or rows[0]['rva'] != RECORD_RVA or rows[0]['raw_hex'] != RECORD_HEX
            or tuple(rows[0][k] for k in ('begin', 'end', 'unwind_rva')) != (PARENT_RVA, PARENT_END, UNWIND_RVA)
            or RECORD_RVA != 0x3FD340C + RECORD_INDEX * 12
            or struct.unpack('<III', bytes.fromhex(RECORD_HEX)) != (PARENT_RVA, PARENT_END, UNWIND_RVA)
            or tuple(site['unwind_chain'][-1][k] for k in ('begin', 'end', 'unwind_rva'))
               != (PARENT_RVA, PARENT_END, UNWIND_RVA)):
        raise ValueError('PARENT104_DECLARATION_SOURCE_CHANGED')
    return {'unwind_metadata_path': str(UNWIND_SOURCE.resolve()), 'unwind_metadata_sha256': UNWIND_SHA,
            'forwarder_directory': str(FORWARDER_SOURCE.resolve()), 'forwarder_metadata_sha256': FORWARDER_SHA,
            'forwarder_binary_sha256': FORWARDER_BIN_SHA, 'caller_rva': CALLER_RVA,
            'caller_hex': CALLER_HEX, 'relative_target_rva': PARENT_RVA,
            'declared_begin': PARENT_RVA, 'declared_end': PARENT_END, 'unwind_rva': UNWIND_RVA,
            'record_index': RECORD_INDEX, 'record_rva': RECORD_RVA, 'record_hex': RECORD_HEX,
            'logical_function_complete': False}


def run(output, dependencies=None, clock=time.perf_counter):
    followup = private_followup()
    locator = followup.private_locator()
    reader = locator.private_reader()
    locator.private_reader = lambda: reader
    old_source = locator.validate_source()
    actual_prefix = followup.validate_source(locator)
    source = validate_sources(reader.profile.FINGERPRINT)
    locator.validate_source = lambda: {**source, 'actual_getter_prefix_source': actual_prefix,
                                      'original_export_provenance': old_source,
                                      'frozen_followup_sha256': FOLLOWUP_SHA}
    original_snapshot = locator.snapshot
    captured = {}
    def snapshot_with_parent(budget):
        snapshot = original_snapshot(budget)
        if snapshot[2].hex() != followup.PIN_HEX:
            raise ValueError('PARENT104_ACTUAL_GETTER_PIN_CHANGED')
        if not captured:
            if struct.unpack_from('<II', snapshot[0], 0x110 + 24 + 136) != (0x3FD340C, 0x1BF57C):
                raise ValueError('PARENT104_LOADED_EXCEPTION_DIRECTORY_CHANGED')
            caller = budget.read_module(CALLER_RVA, 5, 'parent_caller_before', True)
            if caller.hex() != CALLER_HEX:
                raise ValueError('PARENT104_FRESH_CALLER_CHANGED')
            record = budget.read_module(RECORD_RVA, 12, 'fixed_parent_record_before')
            if record.hex() != RECORD_HEX:
                raise ValueError('PARENT104_FIXED_RECORD_CHANGED')
            body = budget.read_module(PARENT_RVA, PARENT_END - PARENT_RVA, 'fixed_declared_parent104', True)
            after_record = budget.read_module(RECORD_RVA, 12, 'fixed_parent_record_after')
            after_caller = budget.read_module(CALLER_RVA, 5, 'parent_caller_after', True)
            if record != after_record or caller != after_caller:
                raise ValueError('PARENT104_CALLER_OR_RECORD_CHANGED_AFTER_BODY')
            captured['body'] = body
        return snapshot
    locator.snapshot = snapshot_with_parent
    status = locator.run(output, dependencies=dependencies, clock=clock)
    meta = json.loads(Path(status['json_path']).read_text('utf8'))
    folder = Path(output).resolve()
    binary, report = folder / 'parent104.bin', folder / 'parent104.json'
    raw = captured['body']
    meta.update(source_revision=REVISION, capture_purpose='SINGLE_FIXED_PARENT104_DECLARATION_FRAGMENT',
        named_lookup_only=False, getter_rva=locator.TARGET_RVA, target_rva=PARENT_RVA,
        target_name='declared_chained_parent_fragment_13AC1F0',
        getter_snapshot_prefix_hex=meta['target_prefix_hex'], target_prefix_hex=raw[:16].hex(), body_read=True,
        declared_begin=PARENT_RVA, declared_end=PARENT_END, code_bytes=104,
        record_before_after_match=True, caller_before_after_match=True,
        binary_path=str(binary), sha256=hashlib.sha256(raw).hexdigest(), lookup_json_path=status['json_path'],
        ranges=[{'module': 'game', 'rva': PARENT_RVA, 'length': 104, 'binary_offset': 0}],
        declared_code_complete=True, logical_function_complete=False,
        boundary_kind='single104B_runtime_function_declaration_fragment',
        pdata_search_performed=False, unwind_chain_read=False, handler_scope_read=False, extra_callee_reads=0)
    binary.write_bytes(raw)
    report.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', 'utf8')
    result = {'status': 'complete', 'source_revision': REVISION, 'json_path': str(report),
              'binary_path': str(binary), 'sha256': meta['sha256']}
    reader.profile.tail['write_status'](folder, result)
    return result


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
