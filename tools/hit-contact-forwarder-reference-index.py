"""One fixed entry13F7690 reference index via a private frozen index instance.

Only the previously captured74B declaration establishes the target entry.
The original source bundle is checked BEFORE changing the private target.
The two fixed sections,48MiB/256RPM-query/2s,64candidate windows and all
header/PIN/real Title2-or-Ship3/generation/protection gates are unchanged.
Byte candidates never establish registration or full hit classification.
No arbitrary RVA CLI, calls, writes, heap/registry/strings, retry or waiting.
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
REVISION = 'game_contact_forwarder_entry_reference_index_v1'
INDEX = ROOT / 'tools/hit-contact-registration-index.py'
INDEX_SHA = '3cf85cbf1ebac30dc3d7c7fd0518eb8ea0ba8f5637898c331e6403d7430a5598'
SOURCE = ROOT / 'dist/hit-contact-forwarder-live-20261013-v1'
SOURCE_SHA = 'ec16ee80d1113343d4725612b2ec296fd0eb4c1cb867ff9a5b7177e56a3f1b03'
BINARY_SHA = '9358990585caedb3082b2ffd9303cc31dac236b80102941c5fa46699a2df7278'
TARGET_RVA, END_RVA, UNWIND_RVA = 0x13F7690, 0x13F76DA, 0x25161AC
PIN_HEX = '40534883ec20488bd94881c1d898c700'
JMP_RVA, JMP_HEX, JMP_DESTINATION = 0x13F76D5, 'e9164bfbff', 0x13AC1F0


def validate_source(fingerprint, folder=SOURCE):
    raw = (Path(folder) / 'forwarder.json').read_bytes()
    binary = (Path(folder) / 'forwarder.bin').read_bytes()
    if (hashlib.sha256(raw).hexdigest() != SOURCE_SHA or len(binary) != 74
            or hashlib.sha256(binary).hexdigest() != BINARY_SHA):
        raise ValueError('FORWARDER_INDEX_CAPTURE_SOURCE_CHANGED')
    meta = json.loads(raw)
    if (not meta.get('complete') or not meta.get('fresh_gates_verified')
            or not meta.get('declared_code_complete') or meta.get('logical_function_complete') is not False
            or meta.get('target_module') != 'game' or meta.get('target_rva') != JMP_RVA
            or meta.get('jmp_destination_rva') != JMP_DESTINATION or meta.get('fingerprint') != fingerprint
            or (meta['function_begin'], meta['function_end']) != (TARGET_RVA, END_RVA)
            or meta.get('sha256') != BINARY_SHA or meta.get('code_bytes') != 74
            or len(meta['ranges']) != 1 or meta['ranges'][0]['module'] != 'game'
            or (meta['ranges'][0]['rva'], meta['ranges'][0]['length'], meta['ranges'][0]['binary_offset'])
               != (TARGET_RVA, 74, 0) or binary[:16].hex() != PIN_HEX):
        raise ValueError('FORWARDER_INDEX_CAPTURE_SOURCE_PROFILE')
    final = meta['exception_records'][-1]
    record = bytes.fromhex(final['raw_hex'])
    if (final['index'] != 69085 or final['rva'] != 0x3FD340C + 69085 * 12
            or len(record) != 12 or struct.unpack('<III', record) != (TARGET_RVA, END_RVA, UNWIND_RVA)
            or tuple(final[k] for k in ('begin', 'end', 'unwind_rva')) != (TARGET_RVA, END_RVA, UNWIND_RVA)
            or len(meta['unwind_chain']) != 1
            or tuple(meta['unwind_chain'][0][k] for k in ('begin', 'end', 'unwind_rva'))
               != (TARGET_RVA, END_RVA, UNWIND_RVA)
            or meta['unwind_chain'][0]['header'] != {'rva': UNWIND_RVA, 'raw_hex': '01060200'}):
        raise ValueError('FORWARDER_INDEX_CAPTURE_DECLARATION_CHANGED')
    at = JMP_RVA - TARGET_RVA
    if (at != 69 or meta.get('binary_jmp_offset') != at or binary[at:].hex() != JMP_HEX
            or binary[at] != 0xE9 or JMP_RVA + 5 + struct.unpack_from('<i', binary, at + 1)[0] != JMP_DESTINATION):
        raise ValueError('FORWARDER_INDEX_CAPTURE_TAIL_JMP_CHANGED')
    return {'directory': str(Path(folder).resolve()), 'metadata_sha256': SOURCE_SHA,
            'binary_sha256': BINARY_SHA, 'target_module': 'game', 'target_rva': TARGET_RVA,
            'declared_begin': TARGET_RVA, 'declared_end': END_RVA, 'unwind_rva': UNWIND_RVA,
            'entry_pin_hex': PIN_HEX, 'tail_jmp_rva': JMP_RVA, 'tail_jmp_hex': JMP_HEX,
            'tail_jmp_destination_rva': JMP_DESTINATION, 'logical_function_complete': False,
            'registered_callback_proven': False}


def private_index():
    if hashlib.sha256(INDEX.read_bytes()).hexdigest() != INDEX_SHA:
        raise ValueError('FORWARDER_INDEX_FROZEN_INDEX_CHANGED')
    spec = importlib.util.spec_from_file_location('_fixed_forwarder_private_index', INDEX)
    index = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(index)
    # The original parent/PIN/source contracts are checked with their original
    # globals, before overriding anything in this private instance.
    old_source = index.validate_sources()
    new_source = validate_source(index.profile.FINGERPRINT)
    index.REVISION = REVISION
    index.TARGET_RVA, index.PIN_RVA, index.PIN_HEX = TARGET_RVA, TARGET_RVA, PIN_HEX
    index.validate_sources = lambda: {**new_source, 'frozen_index_sha256': INDEX_SHA,
        'old_parent_source_validated_before_target_override': True,
        'old_parent_provenance': old_source,
        'new_target_is_forwarder_declared_entry': True}
    return index


def run(output, dependencies=None, clock=time.perf_counter):
    index = private_index()
    return index.run(output, dependencies=dependencies, clock=clock, allow_title_screen=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result['status'] != 'complete':
            raise SystemExit(2)
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
