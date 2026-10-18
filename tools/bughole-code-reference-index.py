"""One Ship-only static code0 index for two proven destruction entry points.

Accept only E8/E9 rel32 bytes resolving exactly to 13E15C0 (enqueue) or
13E1DC0 (consumer). Candidates do not establish instruction boundaries or
creditor semantics. Preserve the frozen reader's 48MiB/256IO/2s limits and
64 short-window cap. No data/heap scan, target follow-up, call, or write.
"""
from __future__ import annotations

import argparse
import hashlib
import heapq
import importlib.util
import json
from pathlib import Path
import struct
import time

ROOT = Path(__file__).resolve().parents[1]
REVISION = 'bughole_enqueue_consumer_two_target_code_reference_index_v1'
INDEX = ROOT / 'tools/hit-contact-registration-index.py'
INDEX_SHA = '3cf85cbf1ebac30dc3d7c7fd0518eb8ea0ba8f5637898c331e6403d7430a5598'
TARGETS = {0x13E15C0: 'destruction_enqueue', 0x13E1DC0: 'destruction_consumer'}
PIN_RVA = 0x13E15C0
PIN_HEX = '488974241057418bf8498bf14c8bd948'
SOURCES = (
    ('dist/bughole-enqueue-live-20261013-v1/drain.bin',
     'abfa74081e6f9f89ab8b78dd61867b89a244db386963642d614c2765f7795cf3',
     0x13E15C0, 6, 352),
    ('dist/bughole-destruction-update-live-20261013-v1/drain.bin',
     '66318f9835ff3c79c694964601b12f3e5927297740c869da737b93f1ed487614',
     0x13E1DC0, 0, 796),
)


def validate_destruction_sources():
    rows = []
    for name, expected, rva, offset, size in SOURCES:
        raw = (ROOT / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected or len(raw) < offset + size:
            raise ValueError('BUGHOLE_REFERENCE_SOURCE_CHANGED:' + name)
        if rva == PIN_RVA and raw[offset:offset + 16].hex() != PIN_HEX:
            raise ValueError('BUGHOLE_REFERENCE_ENQUEUE_PIN_CHANGED')
        rows.append({'path': name, 'sha256': expected, 'entry_rva': rva,
                     'body_binary_offset': offset, 'body_bytes': size})
    meta_path = ROOT / 'dist/bughole-destruction-update-live-20261013-v1/drain.json'
    encoded = meta_path.read_bytes()
    if hashlib.sha256(encoded).hexdigest() != 'ceeeebb4b21595449d2b2e2227496a3f4cc4d004628500df5b0f6f8bb3015512':
        raise ValueError('BUGHOLE_REFERENCE_CONSUMER_METADATA_CHANGED')
    meta = json.loads(encoded)
    if (not meta['complete'] or meta['native_written'] or meta['native_called']
            or meta['ranges'] != [{'name': 'destruction_update_actual_declared_0',
                                  'rva': 0x13E1DC0, 'length': 796, 'binary_offset': 0}]):
        raise ValueError('BUGHOLE_REFERENCE_CONSUMER_ENTRY_UNPROVEN')
    return {'saved_sources': rows, 'targets': TARGETS,
            'producer_entry_existing_source': True,
            'consumer_entry_actual_declaration': True,
            'source_owner_proven': False, 'consumer_caller_proven': False}


def byte_matches(buffer, buffer_rva, kind, absolute):
    if kind != 'code':
        raise ValueError('BUGHOLE_REFERENCE_CODE_ONLY')

    def matches(opcode, label):
        at = buffer.find(opcode)
        while at >= 0:
            if at + 5 <= len(buffer):
                target = buffer_rva + at + 5 + struct.unpack_from('<i', buffer, at + 1)[0]
                if target in TARGETS:
                    yield at, 5, label + '_' + TARGETS[target]
            at = buffer.find(opcode, at + 1)

    return heapq.merge(matches(b'\xe8', 'byte_call_rel32'), matches(b'\xe9', 'byte_jmp_rel32'))


def private_index():
    if hashlib.sha256(INDEX.read_bytes()).hexdigest() != INDEX_SHA:
        raise ValueError('BUGHOLE_REFERENCE_FROZEN_INDEX_CHANGED')
    spec = importlib.util.spec_from_file_location('_bughole_two_target_private_index', INDEX)
    index = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(index)
    old_source = index.validate_sources()
    source = validate_destruction_sources()
    original_stream = index.stream_index
    index.REVISION, index.SECTIONS = REVISION, index.SECTIONS[:1]
    index.PIN_RVA, index.PIN_HEX = PIN_RVA, PIN_HEX
    index.TARGET_RVA = 0  # The old stream computes an unused absolute sentinel.
    index.byte_matches = byte_matches
    index.validate_sources = lambda: {**source, 'frozen_index_sha256': INDEX_SHA,
        'old_parent_source_validated_before_private_override': True,
        'old_parent_provenance': old_source}

    def stream(budget, sections, evidence):
        evidence.pop('target_rva', None)
        evidence.update(capture_purpose='STATIC_DESTRUCTION_TWO_TARGET_CALLER_INDEX_ONLY',
                        target_rvas=list(TARGETS), creditor_proven=False,
                        consumer_timing_proven=False,
                        excluded=['EXE scanning', 'other GameDLL sections',
                                  'data/heap/registry/string scanning', 'candidate follow-up',
                                  'indirect pointers', 'RIP-LEA matching'])
        result = original_stream(budget, sections, evidence)
        for row in result['candidates']:
            raw = bytes.fromhex(row['match_hex'])
            target = row['rva'] + 5 + struct.unpack_from('<i', raw, 1)[0]
            if target not in TARGETS:
                raise ValueError('BUGHOLE_REFERENCE_CANDIDATE_TARGET_CHANGED')
            row['target_rva'], row['target_name'] = target, TARGETS[target]
        if result['complete']:
            result['reason'] = 'SINGLE_FIXED_CODE_SECTION_COMPLETE'
        return result
    index.stream_index = stream
    return index


def run(output, dependencies=None, clock=time.perf_counter):
    return private_index().run(output, dependencies=dependencies, clock=clock)


if __name__ == '__main__':
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
