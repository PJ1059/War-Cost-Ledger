"""One actual declared destruction-update body anchored by the stage writer.

Private reuse of the prepared Ship-only 16KiB/64IO/2s bounded capture session.
Only13E2037 store PIN and actual RF/UW containing it, <=4 ancestry nodes,
<=4KiB total declared code. Oversize keeps metadata and stops; no guessed
window, sibling expansion, queue/heap values, callee/handler scope or Game calls.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import time

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / 'tools/bughole-network-handler-code-capture.py'
FROZEN_SHA = 'a586d762f3939dfc55b1f06215131928bb95463e5f6b286a34b40eb57eb075f1'
REVISION = 'bughole_destruction_update_actual_declaration_v1'
ENTRY_RVA, PIN_RVA, PIN_HEX = 0x13E1DC0, 0x13E2037, '41884707'
if hashlib.sha256(FROZEN.read_bytes()).hexdigest() != FROZEN_SHA:
    raise ValueError('BUGHOLE_UPDATE_FROZEN_READER_CHANGED')
spec = importlib.util.spec_from_file_location('_bughole_update_private_handler_session', FROZEN)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
pattern = (r'\{\["label"\]="destruction update writes the stage",\["rva"\]='
           + str(PIN_RVA) + r',\["hex"\]="' + PIN_HEX + r'",\["module"\]="game"\}')
if not re.search(pattern, worker.source_text):
    raise ValueError('BUGHOLE_UPDATE_SOURCE_STAGE_PIN_ABSENT')
worker.REVISION = worker.session.REVISION = worker.session.reader.REVISION = REVISION
worker.session.reader.TARGET_RVA, worker.session.reader.TARGET_PIN = PIN_RVA, PIN_HEX
worker.session.reader.SOURCE_REFERENCE = ('official research_event_destruction.py entry13E1DC0; '
    'cached event_natives SHA' + worker.SOURCE_SHA + ' stage writer13E2037=41884707')


def capture(process, identity, clock=time.perf_counter, evidence=None):
    reader = worker.session.reader
    reader.validate_module(identity)
    budget, journal, nodes = reader.Budget(process, identity, clock), [], []
    if evidence is not None:
        evidence.update(exception_records=journal, unwind_chain=nodes,
            candidate_entry_rva=ENTRY_RVA, source_pin_rva=PIN_RVA, source_pin_hex=PIN_HEX,
            body_limit=4096, metadata_only_if_oversize=True)
    pins = reader.window_capture((('destruction_stage_writer_before', PIN_RVA, 4),))
    prefix, _ = pins.capture(budget, identity, sleep=lambda _: None)
    # Existing binary search enforces the 4096B body cap. An oversized actual
    # declaration is retained in evidence['exception_records'] by the old runner.
    begin, end = reader.find_function(budget, journal)
    reader.unwind_ancestry((begin, end, journal[-1]['unwind_rva']),
                          lambda rva, size: reader.checked_metadata_read(budget, rva, size), nodes)
    if not any(node['begin'] == ENTRY_RVA for node in nodes):
        raise ValueError('BUGHOLE_UPDATE_ENTRY_NOT_IN_ACTUAL_DECLARATIONS')
    ranges = tuple(('destruction_update_actual_declared_' + str(i), rva, size)
                   for i, (_, rva, size) in enumerate(reader.ancestry_ranges(nodes)))
    windows = reader.window_capture(ranges)
    body, meta = windows.capture(budget, identity, sleep=lambda _: None)
    after, _ = pins.capture(budget, identity, sleep=lambda _: None)
    if prefix != after:
        raise ValueError('BUGHOLE_UPDATE_STAGE_PIN_CHANGED')
    selected = journal[-1]
    if reader.checked_metadata_read(budget, selected['rva'], 12).hex() != selected['raw_hex']:
        raise ValueError('BUGHOLE_UPDATE_RF_CHANGED')
    for node in nodes:
        for field, size in (('header', 4), ('chain_entry', 12)):
            if field in node:
                row = node[field]
                if reader.checked_metadata_read(budget, row['rva'], size).hex() != row['raw_hex']:
                    raise ValueError('BUGHOLE_UPDATE_UW_CHANGED')
    budget.time_gate()
    meta.update(source_revision=REVISION, complete=True, code_only=True,
        destruction_credit_proven=False, classification_ready=False, complete_stream=False,
        logical_function_complete=False, declared_ranges_complete=True,
        boundary_kind='actual_RF_and_bounded_UW_ancestry_not_guessed_length',
        function_begin=begin, function_end=end, exception_records=journal, unwind_chain=nodes,
        selected_ranges=ranges, source_pin_rva=PIN_RVA, source_pin_hex=PIN_HEX,
        source_pin_before_after_match=True, selected_RF_before_after_match=True,
        UW_before_after_match=True, candidate_entry_rva=ENTRY_RVA,
        candidate_entry_declared=True, source_sha256=worker.SOURCE_SHA,
        source_reference=reader.SOURCE_REFERENCE, native_written=False, native_called=False,
        extra_callee_reads=0, handler_scope_reads=0, body_bytes=len(body), budget=budget.summary())
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
