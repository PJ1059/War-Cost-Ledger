"""Read one remaining indexed enqueue producer's actual declaration on Ship.

The sole anchor is 13E311E ->13E15C0 from the original saved index. Uses the
same <=4 KiB declared body/8 KiB total/48 IO/2s limits as consumer capture.
No caller recursion, heap observation or Game execution/write.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / 'tools/bughole-local-enqueue-caller-capture.py'
if hashlib.sha256(path.read_bytes()).hexdigest() != '7246abc419b62881c5f8f53d2c34478f0947bc574459190ec006846281e68911':
    raise ValueError('BUGHOLE_FINAL_PRODUCER_PARENT_CHANGED')
spec = importlib.util.spec_from_file_location('_bughole_final_producer_private', path)
parent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parent)
CALL_RVA, CALL_HEX, TARGET_RVA = 0x13E311E, 'e89de4ffff', 0x13E15C0
rows = [r for r in parent.source['candidates'] if r['rva'] == CALL_RVA]
if (len(rows) != 1 or rows[0]['match_hex'] != CALL_HEX
        or rows[0]['target_rva'] != TARGET_RVA
        or CALL_RVA + 5 + struct.unpack_from('<i', bytes.fromhex(CALL_HEX), 1)[0] != TARGET_RVA):
    raise ValueError('BUGHOLE_FINAL_PRODUCER_INDEX_CHANGED')
worker, reader = parent.worker, parent.reader
revision = 'bughole_final_producer13E311E_actual_declaration_v1'
worker.REVISION = worker.session.REVISION = reader.REVISION = parent.REVISION = revision
worker.EXPECTED_PID = 7416
worker.MAX_IO = reader.MAX_READS = 48
parent.CALL_RVA, parent.CALL_HEX, parent.TARGET_RVA = CALL_RVA, CALL_HEX, TARGET_RVA
reader.TARGET_RVA, reader.TARGET_PIN = CALL_RVA, CALL_HEX
reader.SOURCE_REFERENCE = 'saved enqueue index13E311E->13E15C0 SHA' + parent.SOURCE_SHA

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(worker.run(args.output), ensure_ascii=False, indent=2))
