"""One fixed RF68705 caller containing CALL13E2902, same Ship/read-only budget.

The locator was discovered during the earlier bounded metadata search and is
rechecked live. Only its actual <=4-node ancestry and <=4KiB declared body;
no guessed sibling, callee, heap, native call/write or repeated code index.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / 'tools/bughole-local-enqueue-caller-capture.py'
FROZEN_SHA = '7246abc419b62881c5f8f53d2c34478f0947bc574459190ec006846281e68911'
DISCOVERY = ROOT / 'dist/bughole-local-enqueue-caller-live-20261013-v1/drain.incomplete.json'
DISCOVERY_SHA = 'aa25569af7ce00bde55937fb1214af7245797991c5d0fa4ed2b8cc4160510f7f'
CALL_RVA, CALL_HEX, TARGET_RVA = 0x13E2902, 'e8b9ecffff', 0x13E15C0
if hashlib.sha256(FROZEN.read_bytes()).hexdigest() != FROZEN_SHA:
    raise ValueError('BUGHOLE_SECOND_CALLER_PARENT_CHANGED')
encoded = DISCOVERY.read_bytes()
if hashlib.sha256(encoded).hexdigest() != DISCOVERY_SHA:
    raise ValueError('BUGHOLE_SECOND_CALLER_DISCOVERY_CHANGED')
discovery = json.loads(encoded)
rows = [r for r in discovery['exception_records'] if r['index'] == 68705]
if (len(rows) != 1 or rows[0]['begin'] != 0x13E27E4 or rows[0]['end'] != 0x13E2917
        or rows[0]['unwind_rva'] != 0x25149C0):
    raise ValueError('BUGHOLE_SECOND_CALLER_RF_LOCATOR')
row = rows[0]
spec = importlib.util.spec_from_file_location('_bughole_second_caller_private_parent', FROZEN)
parent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parent)
matches = [r for r in parent.source['candidates'] if r['rva'] == CALL_RVA]
if (len(matches) != 1 or matches[0]['match_hex'] != CALL_HEX
        or CALL_RVA + 5 + struct.unpack_from('<i', bytes.fromhex(CALL_HEX), 1)[0] != TARGET_RVA):
    raise ValueError('BUGHOLE_SECOND_CALLER_EXACT_INDEX_TARGET')
worker, reader = parent.worker, parent.reader
revision = 'bughole_enqueue_caller13E2902_fixed_discovered_RF_v1'
worker.REVISION = worker.session.REVISION = reader.REVISION = parent.REVISION = revision
parent.CALL_RVA, parent.CALL_HEX = CALL_RVA, CALL_HEX
reader.TARGET_RVA, reader.TARGET_PIN = CALL_RVA, CALL_HEX
reader.SOURCE_REFERENCE = 'two-target index SHA' + parent.SOURCE_SHA + '; actual RF68705 locator; CALL13E2902->13E15C0'


def fixed_function(budget, journal):
    raw = reader.checked_metadata_read(budget, row['rva'], 12)
    if raw.hex() != row['raw_hex']:
        raise ValueError('BUGHOLE_SECOND_CALLER_SELECTED_RF_CHANGED')
    begin, end, unwind = struct.unpack('<III', raw)
    reader.validate_runtime_entry(begin, end, unwind)
    if not begin <= CALL_RVA < CALL_RVA + 5 <= end:
        raise ValueError('BUGHOLE_SECOND_CALLER_CALL_OUTSIDE_DECLARATION')
    journal.append(dict(row))
    return begin, end


reader.find_function = fixed_function

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(worker.run(args.output), ensure_ascii=False, indent=2))
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + '\n')
