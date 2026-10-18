"""Close only the known per-frame tail's contiguous branch declarations.

The first capture proves head95377 and next95378. Read those and the two
adjacent declarations needed by the head's explicit173BB14/173BB1E edges.
No callees, UI data, native calls, writes, retries or waiting.
"""
from pathlib import Path
import hashlib
import importlib.util
import struct
import time

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'dist/career-plugin-update-tail-live-20261013-v1/capture/drain.bin'
SOURCE_SHA = 'e23e64d4d951d7e90ae9c1cd8140a7b2c78ee332a7b2f13949cbe77a8e8c4c73'
source = SOURCE.read_bytes()
if len(source) != 31 or hashlib.sha256(source).hexdigest() != SOURCE_SHA:
    raise ValueError('CAREER_PLUGIN_TAIL_HEAD_SOURCE_CHANGED')

spec = importlib.util.spec_from_file_location('_career_plugin_tail_remainder',
    ROOT / 'tools/hit-queue-consumer-code-capture.py')
session = importlib.util.module_from_spec(spec)
spec.loader.exec_module(session)
reader = session.reader
REVISION = 'career_plugin_update_tail_branch_declarations_v1'
session.REVISION = reader.REVISION = REVISION
FIRST_INDEX, FIRST_RVA = 95377, 0x3FD340C + 95377 * 12

def capture(process, identity, clock=time.perf_counter, evidence=None):
    budget = reader.Budget(process, identity, clock)
    prefix = reader.checked_metadata_read(budget, 0x4EE6FE, 5)
    head = reader.checked_metadata_read(budget, 0x173BAB0, 26)
    if prefix + head != source:
        raise ValueError('CAREER_PLUGIN_TAIL_HEAD_PIN_CHANGED')
    records = reader.checked_metadata_read(budget, FIRST_RVA, 48)
    candidates = [struct.unpack_from('<III', records, i * 12) for i in range(4)]
    if evidence is not None:
        evidence.update(adjacent_record_rva=FIRST_RVA, adjacent_records_hex=records.hex())
    containing = [i for i, (a, b, _) in enumerate(candidates)
                  if a <= 0x173BB1E < b]
    if len(containing) != 1 or containing[0] not in (2, 3):
        raise ValueError('CAREER_PLUGIN_TAIL_BRANCH_DECLARATION_UNKNOWN')
    entries = candidates[:containing[0] + 1]
    if (entries[0] != (0x173BAB0, 0x173BACA, 0x2568F84)
            or entries[1] != (0x173BACA, 0x173BB14, 0x2568F8C)
            or entries[2][0] != 0x173BB14
            or any(a[1] != b[0] for a, b in zip(entries, entries[1:]))
            or entries[-1][1] - entries[0][0] > 256):
        raise ValueError('CAREER_PLUGIN_TAIL_ADJACENT_DECLARATIONS_CHANGED')
    nodes = []
    for entry in entries:
        reader.unwind_ancestry(entry,
            lambda rva, n: reader.checked_metadata_read(budget, rva, n), nodes)
    length = entries[-1][1] - entries[0][0]
    window = reader.window_capture((('registered_perframe_tail_branch_envelope', 0x173BAB0, length),))
    window.PINS = ((0x173BAB0, head.hex()),)
    binary, meta = window.capture(budget, identity, sleep=lambda _: None)
    if (reader.checked_metadata_read(budget, 0x4EE6FE, 5) != prefix
            or reader.checked_metadata_read(budget, FIRST_RVA, 48) != records):
        raise ValueError('CAREER_PLUGIN_TAIL_SOURCE_CHANGED_DURING_CAPTURE')
    meta.update(source_revision=REVISION, source_sha256=SOURCE_SHA,
        registered_caller_rva=0x4EE6FE, caller_pin=prefix.hex(),
        declarations=[{'index': FIRST_INDEX+i, 'begin': a, 'end': b, 'unwind_rva': u}
                      for i,(a,b,u) in enumerate(entries)], unwind_chain=nodes,
        complete_declared_branch_envelope=True, logical_function_complete=False,
        native_called=False, native_written=False, code_only=True,
        budget=budget.summary())
    return binary, meta

session.reader.capture = capture

if __name__ == '__main__':
    session.main()
