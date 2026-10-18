"""One proven destruction-update CALL target, actual declaration only.

Question: how13D8B10 uses its eighth u64 parameter. Reuse Ship27268 gates,
16KiB/64 read-query/2s shared cap, actual RF/UW<=4nodes, <=4KiB code. Fresh
parent CALL before/after plus actual target prefix and RF/UW verification.
No queue/heap values, extra callee, handler scope, calls, writes or retry.
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
SOURCE = ROOT / 'dist/bughole-destruction-update-live-20261013-v1'
META_SHA = 'ceeeebb4b21595449d2b2e2227496a3f4cc4d004628500df5b0f6f8bb3015512'
BIN_SHA = '66318f9835ff3c79c694964601b12f3e5927297740c869da737b93f1ed487614'
REVISION = 'bughole_destruction_dispatch_u64_actual_declaration_v1'
CALL_RVA, CALL_HEX, TARGET_RVA = 0x13E2097, 'e8746affff', 0x13D8B10
if hashlib.sha256(FROZEN.read_bytes()).hexdigest() != FROZEN_SHA:
    raise ValueError('BUGHOLE_DISPATCH_FROZEN_READER_CHANGED')
encoded, saved = (SOURCE / 'drain.json').read_bytes(), (SOURCE / 'drain.bin').read_bytes()
if hashlib.sha256(encoded).hexdigest() != META_SHA or hashlib.sha256(saved).hexdigest() != BIN_SHA:
    raise ValueError('BUGHOLE_DISPATCH_PARENT_SOURCE_CHANGED')
meta = json.loads(encoded)
if (not meta.get('complete') or not meta.get('source_pin_before_after_match')
        or not meta.get('selected_RF_before_after_match') or not meta.get('UW_before_after_match')
        or not meta.get('candidate_entry_declared') or meta.get('body_bytes') != 796
        or meta.get('native_written') is not False or meta.get('native_called') is not False
        or meta.get('ship_before') != meta.get('ship_after') or meta['ship_before']['state'] != 3):
    raise ValueError('BUGHOLE_DISPATCH_PARENT_CONTRACT')
found = [r for r in meta['ranges'] if r['rva'] <= CALL_RVA < CALL_RVA + 5 <= r['rva'] + r['length']]
if len(found) != 1:
    raise ValueError('BUGHOLE_DISPATCH_PARENT_CALL_RANGE')
row = found[0]
offset = row['binary_offset'] + CALL_RVA - row['rva']
pin = saved[offset:offset + 5]
if pin.hex() != CALL_HEX or pin[0] != 0xE8 or CALL_RVA + 5 + struct.unpack_from('<i', pin, 1)[0] != TARGET_RVA:
    raise ValueError('BUGHOLE_DISPATCH_PARENT_REL32')
spec = importlib.util.spec_from_file_location('_bughole_dispatch_private_handler_session', FROZEN)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
if meta.get('fingerprint') != worker.session.tail['FINGERPRINT']:
    raise ValueError('BUGHOLE_DISPATCH_PARENT_BUILD')
worker.REVISION = worker.session.REVISION = worker.session.reader.REVISION = REVISION
worker.session.reader.TARGET_RVA, worker.session.reader.TARGET_PIN = TARGET_RVA, ''
worker.session.reader.SOURCE_REFERENCE = 'actual verified update796B SHA' + BIN_SHA + ' CALL13E2097->13D8B10'


def capture(process, identity, clock=time.perf_counter, evidence=None):
    reader = worker.session.reader
    reader.validate_module(identity)
    budget, journal, nodes = reader.Budget(process, identity, clock), [], []
    if evidence is not None:
        evidence.update(exception_records=journal, unwind_chain=nodes,
            target_rva=TARGET_RVA, parent_CALL_rva=CALL_RVA, parent_CALL_hex=CALL_HEX,
            body_limit=4096, metadata_only_if_oversize=True)
    calls = reader.window_capture((('actual_destruction_update_CALL_before', CALL_RVA, 5),))
    calls.PINS = ((CALL_RVA, CALL_HEX),)
    first, _ = calls.capture(budget, identity, sleep=lambda _: None)
    begin, end = reader.find_function(budget, journal)
    reader.unwind_ancestry((begin, end, journal[-1]['unwind_rva']),
                          lambda rva, size: reader.checked_metadata_read(budget, rva, size), nodes)
    if not any(node['begin'] == TARGET_RVA for node in nodes):
        raise ValueError('BUGHOLE_DISPATCH_TARGET_ENTRY_NOT_DECLARED')
    ranges = tuple(('destruction_dispatch_actual_declared_' + str(i), rva, size)
                   for i, (_, rva, size) in enumerate(reader.ancestry_ranges(nodes)))
    windows = reader.window_capture(ranges)
    windows.PINS = ()  # Target prologue was unknown; parent CALL is the source authority.
    body, result = windows.capture(budget, identity, sleep=lambda _: None)
    range_row = next(r for r in result['ranges'] if r['rva'] <= TARGET_RVA < TARGET_RVA + 16 <= r['rva'] + r['length'])
    at = range_row['binary_offset'] + TARGET_RVA - range_row['rva']
    entry_pin = body[at:at + 16]
    prefix = reader.window_capture((('actual_declared_dispatch_prefix_after', TARGET_RVA, 16),))
    prefix.PINS = ((TARGET_RVA, entry_pin.hex()),)
    prefix.capture(budget, identity, sleep=lambda _: None)
    last, _ = calls.capture(budget, identity, sleep=lambda _: None)
    if first != last:
        raise ValueError('BUGHOLE_DISPATCH_PARENT_CALL_CHANGED')
    selected = journal[-1]
    if reader.checked_metadata_read(budget, selected['rva'], 12).hex() != selected['raw_hex']:
        raise ValueError('BUGHOLE_DISPATCH_RF_CHANGED')
    for node in nodes:
        for field, size in (('header', 4), ('chain_entry', 12)):
            if field in node:
                item = node[field]
                if reader.checked_metadata_read(budget, item['rva'], size).hex() != item['raw_hex']:
                    raise ValueError('BUGHOLE_DISPATCH_UW_CHANGED')
    budget.time_gate()
    result.update(source_revision=REVISION, complete=True, code_only=True,
        native_written=False, native_called=False, destruction_credit_proven=False,
        classification_ready=False, complete_stream=False, logical_function_complete=False,
        declared_ranges_complete=True, boundary_kind='actual_RF_UW_target_of_verified_parent_CALL',
        function_begin=begin, function_end=end, exception_records=journal, unwind_chain=nodes,
        selected_ranges=ranges, parent_CALL_rva=CALL_RVA, parent_CALL_hex=CALL_HEX,
        parent_CALL_before_after_match=True, called_target_rva=TARGET_RVA,
        target_entry_declared=True, target_prefix_hex=entry_pin.hex(),
        target_prefix_matches_actual_declared_body=True, selected_RF_before_after_match=True,
        UW_before_after_match=True, parent_source_binary_sha256=BIN_SHA,
        parent_source_json_sha256=META_SHA, source_reference=reader.SOURCE_REFERENCE,
        extra_callee_reads=0, handler_scope_reads=0, body_bytes=len(body), budget=budget.summary())
    if evidence is not None:
        evidence.update(result)
    return body, result


worker.capture = capture

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(worker.run(args.output), ensure_ascii=False, indent=2))
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + '\n')
