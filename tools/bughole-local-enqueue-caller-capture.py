"""Read the RF/UW-declared caller containing exactly CALL13E1592 once on Ship.

Source: the successful two-target code0 index. No caller name/entry guessed.
At most four ancestry nodes, 4KiB declared code, shared 8KiB/32IO/2s including
Ship gates. No siblings, gaps, callees, heap values, Game calls, or writes.
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
FROZEN = ROOT / 'tools/bughole-network-handler-code-capture.py'
FROZEN_SHA = 'a586d762f3939dfc55b1f06215131928bb95463e5f6b286a34b40eb57eb075f1'
SOURCE = ROOT / 'dist/bughole-two-target-references-live-20261013-v1/references.json'
SOURCE_SHA = '1a29a7c4a95d405e36a66647951488f026683fac93754722ba2068fb8ba297f6'
REVISION = 'bughole_enqueue_caller13E1592_actual_declaration_v1'
CALL_RVA, CALL_HEX, TARGET_RVA = 0x13E1592, 'e829000000', 0x13E15C0
if hashlib.sha256(FROZEN.read_bytes()).hexdigest() != FROZEN_SHA:
    raise ValueError('BUGHOLE_CALLER_FROZEN_READER_CHANGED')
encoded = SOURCE.read_bytes()
if hashlib.sha256(encoded).hexdigest() != SOURCE_SHA:
    raise ValueError('BUGHOLE_CALLER_INDEX_CHANGED')
source = json.loads(encoded)
matches = [r for r in source['candidates'] if r['rva'] == CALL_RVA]
if (not source['complete'] or source['game_pid'] != 36452 or len(matches) != 1
        or matches[0]['match_hex'] != CALL_HEX or matches[0]['target_rva'] != TARGET_RVA
        or CALL_RVA + 5 + struct.unpack_from('<i', bytes.fromhex(CALL_HEX), 1)[0] != TARGET_RVA):
    raise ValueError('BUGHOLE_CALLER_INDEX_CONTRACT')
spec = importlib.util.spec_from_file_location('_bughole_caller_private_handler', FROZEN)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
worker.EXPECTED_PID = 36452
worker.MAX_BYTES, worker.MAX_IO = 8192, 32
reader = worker.session.reader
reader.MAX_BYTES, reader.MAX_READS = 8192, 32
worker.REVISION = worker.session.REVISION = reader.REVISION = REVISION
reader.TARGET_RVA, reader.TARGET_PIN = CALL_RVA, CALL_HEX
reader.SOURCE_REFERENCE = 'two-target exact code reference index SHA' + SOURCE_SHA + ' CALL13E1592->13E15C0'


def capture(process, identity, clock=time.perf_counter, evidence=None):
    reader.validate_module(identity)
    budget, journal, nodes = reader.Budget(process, identity, clock), [], []
    if evidence is not None:
        evidence.update(exception_records=journal, unwind_chain=nodes,
                        source_index_sha256=SOURCE_SHA, source_call_rva=CALL_RVA,
                        max_body_bytes=4096, metadata_only_if_oversize=True)
    pin = reader.window_capture((('actual_caller_call_pin', CALL_RVA, 5),))
    before, _ = pin.capture(budget, identity, sleep=lambda _: None)
    begin, end = reader.find_function(budget, journal)
    reader.unwind_ancestry((begin, end, journal[-1]['unwind_rva']),
                          lambda rva, size: reader.checked_metadata_read(budget, rva, size), nodes)
    ranges = tuple(('actual_enqueue_caller_' + str(i), rva, size)
                   for i, (_, rva, size) in enumerate(reader.ancestry_ranges(nodes)))
    body, meta = reader.window_capture(ranges).capture(budget, identity, sleep=lambda _: None)
    after, _ = pin.capture(budget, identity, sleep=lambda _: None)
    if before != after:
        raise ValueError('BUGHOLE_CALLER_CALL_PIN_CHANGED')
    selected = journal[-1]
    if reader.checked_metadata_read(budget, selected['rva'], 12).hex() != selected['raw_hex']:
        raise ValueError('BUGHOLE_CALLER_RF_CHANGED')
    for node in nodes:
        for field, size in (('header', 4), ('chain_entry', 12)):
            if field in node:
                row = node[field]
                if reader.checked_metadata_read(budget, row['rva'], size).hex() != row['raw_hex']:
                    raise ValueError('BUGHOLE_CALLER_UW_CHANGED')
    budget.time_gate()
    meta.update(source_revision=REVISION, complete=True, code_only=True,
                destruction_credit_proven=False, logical_function_complete=False,
                declared_ranges_complete=True, selected_ranges=ranges,
                function_begin=begin, function_end=end, exception_records=journal, unwind_chain=nodes,
                call_rva=CALL_RVA, call_hex=CALL_HEX, called_target_rva=TARGET_RVA,
                call_before_after_match=True, selected_RF_before_after_match=True,
                UW_before_after_match=True, source_index_sha256=SOURCE_SHA,
                native_written=False, native_called=False, extra_callee_reads=0,
                sibling_reads=0, gap_reads=0, body_bytes=len(body), budget=budget.summary())
    if evidence is not None:
        evidence.update(meta)
    return body, meta


worker.capture = capture

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(worker.run(args.output), ensure_ascii=False, indent=2))
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + '\n')
