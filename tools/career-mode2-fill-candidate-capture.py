"""Read one actual Armory call's Career-panel callee declaration, not invoke it.

The eight-field-reference index contains LEA RCX,[RBX+4DC08] followed
by CALL1456C32 ->18E5BA0. This is a candidate until its body is explained.
Reuse the bounded Ship-only declared-code reader and immutable source.
"""
from pathlib import Path
import importlib.util
import hashlib
import json
import struct

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'dist/career-armory-panel-reference-live-20261013-v1/references.json'
SOURCE_SHA = '6228fa509e17f36eff834c4b878306730f701a89cb3938362c4bc247db671740'
CALLER, CALL_PIN, CALLEE = 0x1456C32, 'e869ef4800', 0x18E5BA0
raw = SOURCE.read_bytes()
if hashlib.sha256(raw).hexdigest() != SOURCE_SHA:
    raise ValueError('CAREER_MODE2_CANDIDATE_INDEX_CHANGED')
meta = json.loads(raw)
row = next(c for c in meta['candidates'] if c['rva'] == 0x1456C2E)
window, origin = bytes.fromhex(row['window_hex']), row['window_rva']
if (not meta['complete'] or not meta['source_gates_verified'] or meta['native_called']
        or meta['native_written'] or len(meta['candidates']) != 8
        or window[0x1456C2B-origin:CALLER-origin] != bytes.fromhex('488d8b08dc0400')
        or window[CALLER-origin:CALLER-origin+5].hex() != CALL_PIN
        or CALLER+5+struct.unpack_from('<i',window,CALLER-origin+1)[0] != CALLEE):
    raise ValueError('CAREER_MODE2_CANDIDATE_CALL_SOURCE')

spec = importlib.util.spec_from_file_location('_career_mode2_fill_private',
    ROOT / 'tools/career-stat-fill-code-capture.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
worker = probe.worker
worker.REVISION = worker.session.REVISION = worker.session.reader.REVISION = 'career_mode2_fill_candidate_declared_v1'
worker.CALLER, worker.CALL_PIN, worker.CALLEE = CALLER, CALL_PIN, CALLEE
worker.SOURCE_SHA = SOURCE_SHA
worker.session.reader.TARGET_RVA, worker.session.reader.TARGET_PIN = CALLEE, ''
worker.session.reader.SOURCE_REFERENCE = (
    'Actual field reference index SHA'+SOURCE_SHA
    +'; 1456C2B LEA RCX,[RBX+4DC08]; CALL1456C32 ->18E5BA0. '
    +'Candidate body only, no provider/signature/request-ready claim.')
worker.caller_window = worker.window_factory((('impact_consumer_callsite',CALLER,5),))
worker.caller_window.PINS = ((CALLER,CALL_PIN),)

if __name__ == '__main__':
    worker.main()
