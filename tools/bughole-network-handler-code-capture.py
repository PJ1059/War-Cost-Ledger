"""Prepare one Ship-only actual RF/UW-declared network destruction handler.

Anchor only the cached upstream CALL BBA6EE ->13E15C0. Binary-search the
single containing RF, follow at most four declared UW nodes, then read only
their <=4KiB total declared code. Shared 16KiB/64 read-query/2s process budget
includes both native Ship/context gates. No arbitrary RVA/size/PID CLI,
callee/scope/heap-field follow, retry/wait, native call, or Game write.
Run only after root explicitly confirms the new Game PID27268 is in Ship.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import time

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / 'tools/hit-queue-consumer-code-capture.py'
FROZEN_SHA = '9e807430d0fad375456b20022209d16ea4fe491da0c28e0fd915c06e3b7cca8e'
READER = ROOT / 'tools/recon_chat_code_capture.py'
READER_SHA = '797b5fcb45d391958e99e7e9305b56433efd20a5148645cb72b9993ed16dd675'
SOURCE = ROOT / 'dist/career-stats-source-audit/upstream/domains/event_natives.lua'
SOURCE_SHA = 'ddb3f08f9c81d2894aa394e60056054bf5c85c78e85e7f9089ea007dbd652e97'
REVISION = 'bughole_network_handler_actual_declaration_v1'
ENTRY_RVA, CALL_RVA, CALL_HEX, DESTINATION = 0xBBA520, 0xBBA6EE, 'e8cd6e8200', 0x13E15C0
EXPECTED_PID = 27268
MAX_BYTES, MAX_IO, MAX_SECONDS = 16384, 64, 2.0

for path, expected in ((FROZEN, FROZEN_SHA), (READER, READER_SHA), (SOURCE, SOURCE_SHA)):
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError('BUGHOLE_HANDLER_FROZEN_SOURCE_CHANGED:' + str(path))
source_text = SOURCE.read_text('utf8')
pin_pattern = (r'\{\["label"\]="a peer applies the same destruction",\["rva"\]='
               + str(CALL_RVA) + r',\["hex"\]="' + CALL_HEX + r'",\["module"\]="game"\}')
if not re.search(pin_pattern, source_text):
    raise ValueError('BUGHOLE_HANDLER_UPSTREAM_CALL_PIN_ABSENT')
call_bytes = bytes.fromhex(CALL_HEX)
if call_bytes[0] != 0xE8 or CALL_RVA + 5 + struct.unpack_from('<i', call_bytes, 1)[0] != DESTINATION:
    raise ValueError('BUGHOLE_HANDLER_UPSTREAM_CALL_REL32')
spec = importlib.util.spec_from_file_location('_bughole_network_handler_private_session', FROZEN)
session = importlib.util.module_from_spec(spec)
spec.loader.exec_module(session)
session.REVISION = session.reader.REVISION = REVISION
session.reader.TARGET_RVA, session.reader.TARGET_PIN = CALL_RVA, CALL_HEX
session.reader.MAX_BYTES, session.reader.MAX_READS = MAX_BYTES, MAX_IO
session.reader.SOURCE_REFERENCE = ('cached upstream event_natives SHA' + SOURCE_SHA
    + ' CALL BBA6EE ->13E15C0; official research_event_destruction.py handler candidate BBA520')


class SharedProcess:
    """Delegate only the existing read/query surface, with one total cap."""
    def __init__(self, process, clock=time.perf_counter):
        self.process, self.clock = process, clock
        self.started = clock()
        self.read_calls = self.query_calls = self.bytes = 0

    def time_gate(self):
        if self.clock() - self.started >= MAX_SECONDS:
            raise ValueError('BUGHOLE_HANDLER_SHARED_TIME_BUDGET')

    def query(self, address):
        self.time_gate()
        if self.query_calls >= MAX_IO:
            raise ValueError('BUGHOLE_HANDLER_SHARED_QUERY_BUDGET')
        self.query_calls += 1
        return self.process.query(address)

    def read(self, address, size):
        self.time_gate()
        if (not 0 < size <= 4096 or self.read_calls >= MAX_IO or self.bytes + size > MAX_BYTES):
            raise ValueError('BUGHOLE_HANDLER_SHARED_READ_BUDGET')
        self.read_calls += 1
        self.bytes += size
        raw = self.process.read(address, size)
        if len(raw) != size:
            raise ValueError('BUGHOLE_HANDLER_SHARED_SHORT_READ')
        return raw

    def summary(self):
        return {'reads': self.read_calls, 'queries': self.query_calls, 'bytes': self.bytes,
                'elapsed_ms': (self.clock() - self.started) * 1000,
                'max_bytes': MAX_BYTES, 'max_reads': MAX_IO, 'max_queries': MAX_IO,
                'soft_seconds': MAX_SECONDS}


def capture(process, identity, clock=time.perf_counter, evidence=None):
    reader = session.reader
    reader.validate_module(identity)
    budget, journal, nodes = reader.Budget(process, identity, clock), [], []
    if evidence is not None:
        evidence.update(exception_records=journal, unwind_chain=nodes)
    pins = reader.window_capture((('network_destruction_call_before', CALL_RVA, 5),))
    prefix, _ = pins.capture(budget, identity, sleep=lambda _: None)
    begin, end = reader.find_function(budget, journal)
    reader.unwind_ancestry((begin, end, journal[-1]['unwind_rva']),
                          lambda rva, size: reader.checked_metadata_read(budget, rva, size), nodes)
    # The candidate entry must be an actual declared range, never a guessed
    # extension of the containing call fragment.
    if not any(node['begin'] == ENTRY_RVA for node in nodes):
        raise ValueError('BUGHOLE_HANDLER_CANDIDATE_ENTRY_NOT_IN_ACTUAL_DECLARATIONS')
    ranges = tuple(('network_handler_actual_declared_' + str(i), rva, size)
                   for i, (_, rva, size) in enumerate(reader.ancestry_ranges(nodes)))
    windows = reader.window_capture(ranges)
    body, meta = windows.capture(budget, identity, sleep=lambda _: None)
    after, _ = pins.capture(budget, identity, sleep=lambda _: None)
    if prefix != after:
        raise ValueError('BUGHOLE_HANDLER_CALL_PIN_CHANGED')
    # Revalidate the actual selected RF and every ancestry header/chain; no
    # scope/handler data or callee body is followed.
    selected = journal[-1]
    if reader.checked_metadata_read(budget, selected['rva'], 12).hex() != selected['raw_hex']:
        raise ValueError('BUGHOLE_HANDLER_SELECTED_RF_CHANGED')
    for node in nodes:
        for field, size in (('header', 4), ('chain_entry', 12)):
            if field in node:
                row = node[field]
                if reader.checked_metadata_read(budget, row['rva'], size).hex() != row['raw_hex']:
                    raise ValueError('BUGHOLE_HANDLER_UNWIND_DECLARATION_CHANGED')
    budget.time_gate()
    meta.update(source_revision=REVISION, complete=True, code_only=True,
        classification_ready=False, destruction_credit_proven=False, complete_stream=False,
        logical_function_complete=False, declared_ranges_complete=True,
        boundary_kind='actual_RF_and_bounded_UW_ancestry_not_guessed_length',
        function_begin=begin, function_end=end, exception_records=journal,
        unwind_chain=nodes, selected_ranges=ranges, call_rva=CALL_RVA, call_hex=CALL_HEX,
        called_target_rva=DESTINATION, call_before_after_match=True,
        selected_RF_before_after_match=True, UW_before_after_match=True,
        candidate_entry_rva=ENTRY_RVA, candidate_entry_declared=True,
        source_reference=reader.SOURCE_REFERENCE, source_sha256=SOURCE_SHA,
        source_caller_rel32_recomputed=True, extra_callee_reads=0,
        native_written=False, native_called=False, body_bytes=len(body),
        budget=budget.summary())
    if evidence is not None:
        evidence.update(meta)
    return body, meta


def run(output, dependencies=None):
    deps = dict(dependencies if dependencies is not None else session.tail['load_dependencies']())
    enumerate_game, original_process = deps['game_processes'], deps['Process']
    captures = []
    def expected_game():
        if captures:
            captures[0].time_gate()
        pids = tuple(enumerate_game())
        if pids != (EXPECTED_PID,):
            raise ValueError('BUGHOLE_HANDLER_EXPECTS_NEW_CURRENT_PID:' + str(pids))
        return pids
    class ProcessContext:
        def __init__(self, pid):
            if pid != EXPECTED_PID:
                raise ValueError('BUGHOLE_HANDLER_OLD_PID_FORBIDDEN')
            self.owner = original_process(pid)
        def __enter__(self):
            self.proxy = SharedProcess(self.owner.__enter__())
            captures.append(self.proxy)
            return self.proxy
        def __exit__(self, *args):
            return self.owner.__exit__(*args)
    deps['game_processes'], deps['Process'] = expected_game, ProcessContext
    session.reader.capture = capture
    result = session.run(output, dependencies=deps)
    proxy = captures[0]
    path = Path(result['json_path'])
    meta = json.loads(path.read_text('utf8'))
    meta['shared_process_budget_including_ship_gates'] = proxy.summary()
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', 'utf8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.output), ensure_ascii=False, indent=2))
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + '\n')
