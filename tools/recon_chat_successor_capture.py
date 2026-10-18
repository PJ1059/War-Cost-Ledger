"""One bounded read-only successor capture; never reads chat data or calls game code."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
REVISION = 'recon_chat_history_successor_v4'
MAX_BYTES, MAX_READS, MAX_SECONDS = 4096, 10, 2.0
CODE_BEGIN, CODE_END = 0x10979C0, 0x1097C74
ENTRIES = (
    (54625, 0x10979C0, 0x10979E3, 0x24DB604),
    (54626, 0x10979E3, 0x1097A88, 0x24DB610),
    (54627, 0x1097A88, 0x1097C74, 0x24DB62C),
)
V2_BINARY_SHA = '25b38d68fd00733867fbb54e47f93de4744a979df3396b5b51127f84a5160037'
# The retained v3 metadata proves successor -> target -> root. Every parent is
# already one of these three fixed records; this does not follow another range.
PARENT_POSITIONS = {1: 0, 2: 1}

# A private module instance reuses the tested wait/RPM/PIN machinery without
# changing the v2 tool or the original FIRE tool's globals.
_spec = importlib.util.spec_from_file_location('recon_successor_session',
                                               ROOT / 'tools/recon_chat_code_capture.py')
session = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(session)
session.REVISION = REVISION
session.MAX_BYTES, session.MAX_READS, session.MAX_SECONDS = MAX_BYTES, MAX_READS, MAX_SECONDS
profile = session.profile


def verify_metadata(table_records, nodes):
    if len(table_records) != 3 or len(nodes) != 3:
        raise ValueError('RECON_SUCCESSOR_METADATA_COUNT')
    for position, (index, begin, end, unwind) in enumerate(ENTRIES):
        entry, node = table_records[position], nodes[position]
        expected_rva = session.EXCEPTION_RVA + index * session.ENTRY_SIZE
        if (entry['index'] != index or entry['rva'] != expected_rva
                or (entry['begin'], entry['end'], entry['unwind_rva']) != (begin, end, unwind)
                or bytes.fromhex(entry['raw_hex']) != struct.pack('<III', begin, end, unwind)):
            raise ValueError('RECON_SUCCESSOR_TABLE_CHANGED')
        if (node['begin'], node['end'], node['unwind_rva']) != (begin, end, unwind):
            raise ValueError('RECON_SUCCESSOR_BOUNDARY_CHANGED')
        header = node['header']
        raw = bytes.fromhex(header['raw_hex'])
        if header['rva'] != unwind:
            raise ValueError('RECON_SUCCESSOR_HEADER_ADDRESS')
        flags = session.check_unwind_header(raw)
        if position == 0:
            if raw != bytes.fromhex('010a0400') or 'chain_entry' in node:
                raise ValueError('RECON_SUCCESSOR_ROOT_CHANGED')
        else:
            if flags != 4 or raw[3] != 0:
                raise ValueError('RECON_SUCCESSOR_CHAIN_INVALID')
            if position == 1 and raw != bytes.fromhex('210f0600'):
                raise ValueError('RECON_SUCCESSOR_TARGET_CHANGED')
            chain = node['chain_entry']
            chain_rva = unwind + 4 + 2 * ((raw[2] + 1) & ~1)
            if (chain['rva'] != chain_rva or chain_rva % 4
                    or not 0 < chain_rva <= session.IMAGE_SIZE - 12
                    or bytes.fromhex(chain['raw_hex']) != struct.pack('<III', *ENTRIES[PARENT_POSITIONS[position]][1:])):
                raise ValueError('RECON_SUCCESSOR_NOT_KNOWN_PARENT')


def capture(process, identity, clock=time.perf_counter, evidence=None):
    session.validate_module(identity)
    budget = session.Budget(process, identity, clock)
    records, nodes = [], []
    evidence = evidence if evidence is not None else {}
    evidence.update(source_revision=REVISION, exception_records=records, unwind_chain=nodes,
                    native_written=False, native_called=False)
    try:
        for index, begin, end, unwind in ENTRIES:
            raw = session.table_read(budget, index)
            records.append({'index': index,
                            'rva': session.EXCEPTION_RVA + index * session.ENTRY_SIZE,
                            'raw_hex': raw.hex(), 'begin': begin, 'end': end,
                            'unwind_rva': unwind})
            if raw != struct.pack('<III', begin, end, unwind):
                raise ValueError('RECON_SUCCESSOR_TABLE_CHANGED')
        for position, (_, begin, end, unwind) in enumerate(ENTRIES):
            header = session.checked_metadata_read(budget, unwind, 4)
            flags = session.check_unwind_header(header)
            node = {'begin': begin, 'end': end, 'unwind_rva': unwind,
                    'header': {'rva': unwind, 'raw_hex': header.hex()}}
            nodes.append(node)
            if position == 0:
                if header != bytes.fromhex('010a0400'):
                    raise ValueError('RECON_SUCCESSOR_ROOT_CHANGED')
            else:
                if flags != 4 or header[3] != 0:
                    raise ValueError('RECON_SUCCESSOR_CHAIN_INVALID')
                if position == 1 and header != bytes.fromhex('210f0600'):
                    raise ValueError('RECON_SUCCESSOR_TARGET_CHANGED')
                chain_rva = unwind + 4 + 2 * ((header[2] + 1) & ~1)
                if chain_rva % 4 or not 0 < chain_rva <= session.IMAGE_SIZE - 12:
                    raise ValueError('RECON_SUCCESSOR_CHAIN_ADDRESS')
                raw = session.checked_metadata_read(budget, chain_rva, 12)
                node['chain_entry'] = {'rva': chain_rva, 'raw_hex': raw.hex()}
                if raw != struct.pack('<III', *ENTRIES[PARENT_POSITIONS[position]][1:]):
                    raise ValueError('RECON_SUCCESSOR_NOT_KNOWN_PARENT')
        verify_metadata(records, nodes)
        reader = session.window_capture((('chat_history_known_successor', CODE_BEGIN,
                                          CODE_END - CODE_BEGIN),))
        binary, meta = reader.capture(budget, identity)
        meta.update(exception_records=records, unwind_chain=nodes,
                    boundary_kind='three_fixed_adjacent_runtime_function_ranges',
                    proven_predecessor_binary_sha256=V2_BINARY_SHA,
                    all_sibling_fragments_captured=False, logical_function_complete=False,
                    diagnostic_only=True, chat_messages_read=0, recon_events_emitted=0,
                    target_rva=session.TARGET_RVA, budget=budget.summary())
        verify_saved(meta, binary)
        return binary, meta
    finally:
        evidence['budget'] = budget.summary()


def verify_saved(meta, binary):
    if meta['source_revision'] != REVISION or any(meta[k] != v for k, v in profile.FINGERPRINT.items()):
        raise ValueError('RECON_SUCCESSOR_CACHE_BUILD')
    verify_metadata(meta['exception_records'], meta['unwind_chain'])
    expected = [{'name': 'chat_history_known_successor', 'rva': CODE_BEGIN,
                 'length': CODE_END - CODE_BEGIN, 'binary_offset': 0}]
    if meta['ranges'] != expected or len(binary) != CODE_END - CODE_BEGIN:
        raise ValueError('RECON_SUCCESSOR_CACHE_RANGE')
    reader = session.window_capture((('chat_history_known_successor', CODE_BEGIN,
                                      CODE_END - CODE_BEGIN),))
    reader.verify_pins(binary)
    if hashlib.sha256(binary).hexdigest() != meta['binary_sha256']:
        raise ValueError('RECON_SUCCESSOR_CACHE_HASH')
    if (meta['budget']['read_calls'] > MAX_READS or meta['budget']['query_calls'] > MAX_READS
            or meta['budget']['bytes_requested'] > MAX_BYTES):
        raise ValueError('RECON_SUCCESSOR_CACHE_BUDGET')


session.capture, session.verify_saved = capture, verify_saved


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/recon-chat-code-v4')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        stamps = profile.fingerprints()
        if args.check:
            print(json.dumps({'status': 'local_build_matches', 'max_bytes': MAX_BYTES,
                              'max_reads': MAX_READS, 'code_bytes': CODE_END - CODE_BEGIN,
                              'planned_reads': 9, 'planned_bytes': 764}))
            return 0
        args.output.mkdir(parents=True, exist_ok=True)
        old = session.saved_complete(args.output)
        if old:
            print('Already complete: ' + old['json_path'])
            return 0
        result = session.wait_and_capture(args.output, stamps=stamps)
        print('Complete: ' + result['json_path'])
        return 0
    except KeyboardInterrupt:
        profile.write_status(args.output, {'status': 'cancelled', 'updated_at': profile.utc_now()})
        return 130
    except Exception as error:
        args.output.mkdir(parents=True, exist_ok=True)
        try:
            previous = json.loads((args.output / 'status.json').read_text(encoding='utf8'))
        except (OSError, ValueError):
            previous = {}
        if not (previous.get('status') == 'failed' and previous.get('sampler_pid') == os.getpid()
                and previous.get('error') == str(error)):
            profile.write_status(args.output, {'status': 'failed', 'updated_at': profile.utc_now(),
                                                'error': str(error)})
        print('Stopped: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
