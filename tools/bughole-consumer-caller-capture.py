"""Capture only the actual declaration containing the indexed destruction drain CALL.

Ship-only PID 7416. This is not a caller search: the sole anchor is the saved
13F7D46 -> 13E1DC0 rel32. At most four unwind nodes, 4 KiB declared code,
8 KiB total reads, 48 reads/queries and 2 seconds including both Ship gates.
48 IO accounts for the fixed exception-table search and declaration rechecks;
the earlier 32 IO wrapper had exhausted its budget at the final Ship gate.
No heap fields, callees, Game execution/writes or background retries.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / 'tools/bughole-local-enqueue-caller-capture.py'
PARENT_SHA = '7246abc419b62881c5f8f53d2c34478f0947bc574459190ec006846281e68911'
CALL_RVA, CALL_HEX, TARGET_RVA = 0x13F7D46, 'e875a0feff', 0x13E1DC0
if hashlib.sha256(PARENT.read_bytes()).hexdigest() != PARENT_SHA:
    raise ValueError('BUGHOLE_CONSUMER_CALLER_PARENT_CHANGED')
spec = importlib.util.spec_from_file_location('_bughole_consumer_caller_private', PARENT)
parent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parent)
matches = [r for r in parent.source['candidates'] if r['rva'] == CALL_RVA]
if (len(matches) != 1 or matches[0]['match_hex'] != CALL_HEX
        or matches[0]['target_rva'] != TARGET_RVA
        or CALL_RVA + 5 + struct.unpack_from('<i', bytes.fromhex(CALL_HEX), 1)[0] != TARGET_RVA):
    raise ValueError('BUGHOLE_CONSUMER_CALLER_EXACT_INDEX_TARGET')
worker, reader = parent.worker, parent.reader
revision = 'bughole_consumer_caller13F7D46_actual_declaration_v1'
worker.REVISION = worker.session.REVISION = reader.REVISION = parent.REVISION = revision
worker.EXPECTED_PID = 7416
worker.MAX_IO = reader.MAX_READS = 48
parent.CALL_RVA, parent.CALL_HEX, parent.TARGET_RVA = CALL_RVA, CALL_HEX, TARGET_RVA
reader.TARGET_RVA, reader.TARGET_PIN = CALL_RVA, CALL_HEX
reader.SOURCE_REFERENCE = ('two-target index SHA' + parent.SOURCE_SHA
    + '; sole consumer CALL13F7D46->13E1DC0; actual declaration only')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(worker.run(args.output), ensure_ascii=False, indent=2))
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + '\n')
