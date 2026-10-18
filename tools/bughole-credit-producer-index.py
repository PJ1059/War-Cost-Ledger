"""One code0 index for the two already decoded, source-forwarding producers.

Only rel32 to 13E1460 or 13E2790. No helper recursion, heap scan or calls.
This obtains a producer candidate carrying the actual damage source; candidate
bytes alone never award a ribbon. Same bounded reader as the prior index.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / 'tools/bughole-code-reference-index.py'
if hashlib.sha256(path.read_bytes()).hexdigest() != 'd59e52484babcd46dd6d5601499dd81f6aa836a32eb1b96276f57c9a8e917bb0':
    raise ValueError('BUGHOLE_CREDIT_INDEX_PARENT_CHANGED')
spec = importlib.util.spec_from_file_location('_bughole_credit_index_private', path)
parent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parent)
parent.REVISION = 'bughole_credit_producer_two_target_index_v1'
parent.TARGETS = {0x13E1460: 'destructible_id_source_producer', 0x13E2790: 'world_record_source_producer'}
parent.PIN_RVA = 0x13E2790
parent.PIN_HEX = '48895c242048894c2408555657415641'


def validate_sources():
    rows = []
    for filename, expected, entry, size in (
        ('bughole-local-enqueue-caller-live-20261013-v2',
         '8121ac45265416933fe8ae78f47e3869dcd9bf1659ddd0640cfd0f0ce80f3ec0', 0x13E1460, 324),
        ('bughole-enqueue-second-caller-live-20261013-v1',
         'f7a13b95a73d3d175f7781aeddc599e652fa0e1a802085f9c3e7427e859f1b77', 0x13E2790, 391)):
        directory = ROOT / 'dist' / filename
        raw = (directory / 'drain.bin').read_bytes()
        meta = json.loads((directory / 'drain.json').read_text('utf8'))
        if (hashlib.sha256(raw).hexdigest() != expected or len(raw) != size
                or not meta['complete'] or meta['ranges'][0]['rva'] != entry):
            raise ValueError('BUGHOLE_CREDIT_INDEX_SOURCE_CHANGED')
        if entry == parent.PIN_RVA and raw[:16].hex() != parent.PIN_HEX:
            raise ValueError('BUGHOLE_CREDIT_INDEX_PIN_CHANGED')
        rows.append({'entry_rva': entry, 'bytes': size, 'sha256': expected,
                     'path': str(directory / 'drain.bin')})
    return {'saved_sources': rows, 'targets': parent.TARGETS,
            'argument_forwarding_proven': True, 'creditor_origin_proven': False}


parent.validate_destruction_sources = validate_sources

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = parent.run(args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result['status'] != 'complete':
        raise SystemExit(2)
