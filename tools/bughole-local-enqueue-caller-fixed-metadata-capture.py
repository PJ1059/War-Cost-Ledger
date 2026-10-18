"""Same CALL13E1592 capture using its just-discovered RF instead of binary search.

The first attempt stopped at the final Ship read's shared32 budget; its code
was not saved. Its selected RF is only a locator, revalidated live along with
the original full bounded ancestry before and after body. No budget increase.
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
if hashlib.sha256(FROZEN.read_bytes()).hexdigest() != FROZEN_SHA:
    raise ValueError('BUGHOLE_FIXED_METADATA_PARENT_CHANGED')
encoded = DISCOVERY.read_bytes()
if hashlib.sha256(encoded).hexdigest() != DISCOVERY_SHA:
    raise ValueError('BUGHOLE_FIXED_METADATA_DISCOVERY_CHANGED')
discovery = json.loads(encoded)
row = discovery['exception_records'][-1]
if (discovery['complete'] or discovery['error'] != 'BUGHOLE_HANDLER_SHARED_QUERY_BUDGET'
        or row['begin'] != 0x13E14AE or row['end'] != 0x13E15A4
        or row['index'] != 68676 or row['unwind_rva'] != 0x2514790):
    raise ValueError('BUGHOLE_FIXED_METADATA_DISCOVERY_CONTRACT')
spec = importlib.util.spec_from_file_location('_bughole_fixed_metadata_private_parent', FROZEN)
parent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parent)
worker, reader = parent.worker, parent.reader
revision = 'bughole_enqueue_caller13E1592_fixed_discovered_RF_v2'
worker.REVISION = worker.session.REVISION = reader.REVISION = parent.REVISION = revision


def fixed_function(budget, journal):
    raw = reader.checked_metadata_read(budget, row['rva'], 12)
    if raw.hex() != row['raw_hex']:
        raise ValueError('BUGHOLE_FIXED_METADATA_SELECTED_RF_CHANGED')
    begin, end, unwind = struct.unpack('<III', raw)
    reader.validate_runtime_entry(begin, end, unwind)
    if not begin <= parent.CALL_RVA < parent.CALL_RVA + 5 <= end:
        raise ValueError('BUGHOLE_FIXED_METADATA_CALL_OUTSIDE_DECLARATION')
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
