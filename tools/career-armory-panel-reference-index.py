"""One Ship-only raw field-displacement index in the fixed Game code section.

Find only little-endian 4B 0x4DAF8 / 0x4DC08 candidates; these are field
displacements, never function RVAs or verified instructions. Keep the frozen
index's 48MiB/256-read/query/2s limits, <=64 windows, source/header/PIN and
before/after identity gates. No data-section/heap scan or candidate follow-up.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import heapq
import importlib.util
import json
from pathlib import Path
import struct
import time

ROOT = Path(__file__).resolve().parents[1]
REVISION = 'career_armory_panel_field_displacement_index_v1'
INDEX = ROOT / 'tools/hit-contact-registration-index.py'
INDEX_SHA = '3cf85cbf1ebac30dc3d7c7fd0518eb8ea0ba8f5637898c331e6403d7430a5598'
ASSOCIATION = ROOT / 'tools/career-provider-association.py'
ASSOCIATION_SHA = 'a619470122d7e27d02550ff7cceaeb9f59f295ecb0f429dcba9881646972f26d'
FIELDS = (0x4DAF8, 0x4DC08)
PIN_RVA = 0x1456522


def validate_career_source():
    raw = ASSOCIATION.read_bytes()
    if hashlib.sha256(raw).hexdigest() != ASSOCIATION_SHA:
        raise ValueError('CAREER_FIELD_INDEX_ASSOCIATION_SOURCE_CHANGED')
    tree = ast.parse(raw, filename=str(ASSOCIATION))
    sources = next(ast.literal_eval(node.value) for node in tree.body
                   if isinstance(node, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == 'SOURCES' for t in node.targets))[:3]
    if tuple(row[2:] for row in sources) != ((0x1455C30, 2855, 5),
            (0x18EDCA0, 597, 5), (0x18E52B0, 2139, 5)):
        raise ValueError('CAREER_FIELD_INDEX_SAVED_RANGE_CHANGED')
    bodies = []
    for path, expected, begin, length, offset in sources:
        binary = (ROOT / path).read_bytes()
        if hashlib.sha256(binary).hexdigest() != expected or offset + length > len(binary):
            raise ValueError('CAREER_FIELD_INDEX_SAVED_BINARY_CHANGED')
        bodies.append(binary[offset:offset + length])
    init, panel, listing = bodies
    pin = init[PIN_RVA - 0x1455C30:PIN_RVA - 0x1455C30 + 16]
    if (pin != bytes.fromhex('498d8ff8da0400e872774900498d97f8')
            or panel[0xE0:0xE7] != bytes.fromhex('488d8f10010000')
            or panel[0x12A:0x12F] != bytes.fromhex('e8e174ffff')
            or 0x18EDDCA + 5 + struct.unpack_from('<i', panel, 0x12B)[0] != 0x18E52B0
            or listing[:16] != bytes.fromhex('488bc448895808488970104889781855')
            or FIELDS[1] != FIELDS[0] + 0x110):
        raise ValueError('CAREER_FIELD_INDEX_LAYOUT_PIN_CHANGED')
    return pin.hex(), {'association_path': str(ASSOCIATION),
        'association_sha256': ASSOCIATION_SHA,
        'saved_sources': [{'path': path, 'sha256': sha, 'rva': begin,
                           'length': length, 'binary_offset': offset}
                          for path, sha, begin, length, offset in sources],
        'armory_inline_field_displacement': FIELDS[0],
        'panel_child_displacement': 0x110,
        'armory_panel_inline_field_displacement': FIELDS[1],
        'panel_init_call_rva': 0x18EDDCA, 'panel_list_init_rva': 0x18E52B0,
        'field_layout_source_verified': True, 'automatic_career_request_proven': False}


def byte_matches(buffer, buffer_rva, kind, absolute):
    """Raw 4B matches only; no opcode, absolute pointer or rel32 matching."""
    if kind != 'code':
        raise ValueError('CAREER_FIELD_INDEX_CODE_ONLY')
    def matches(value):
        needle = struct.pack('<I', value)
        at = buffer.find(needle)
        while at >= 0:
            yield at, 4, f'byte_field_displacement_{value:#x}'
            at = buffer.find(needle, at + 1)
    return heapq.merge(*(matches(value) for value in FIELDS))


def private_index():
    if hashlib.sha256(INDEX.read_bytes()).hexdigest() != INDEX_SHA:
        raise ValueError('CAREER_FIELD_INDEX_FROZEN_INDEX_CHANGED')
    spec = importlib.util.spec_from_file_location('_career_field_private_index', INDEX)
    index = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(index)
    old_source = index.validate_sources()  # Original globals, before private overrides.
    pin, source = validate_career_source()
    frozen_stream = index.stream_index
    index.REVISION = REVISION
    index.SECTIONS = index.SECTIONS[:1]
    index.PIN_RVA, index.PIN_HEX = PIN_RVA, pin
    # Only the old stream's unused absolute argument needs an integer. Zero is
    # a compatibility sentinel, not a function target; remove it before scan.
    index.TARGET_RVA = 0
    index.byte_matches = byte_matches
    index.validate_sources = lambda: {**source, 'frozen_index_sha256': INDEX_SHA,
        'old_parent_source_validated_before_private_override': True,
        'old_parent_provenance': old_source,
        'target_kind': 'FIELD_DISPLACEMENT_BYTES_ONLY',
        'field_displacements': list(FIELDS), 'function_target_verified': False}

    def stream(budget, sections, evidence):
        evidence.pop('target_rva', None)
        evidence.update(capture_purpose='STATIC_CODE_FIELD_DISPLACEMENT_INDEX_ONLY',
                        target_kind='FIELD_DISPLACEMENT_BYTES_ONLY',
                        field_displacements=list(FIELDS), function_target_verified=False,
                        automatic_career_request_proven=False,
                        excluded=['EXE scanning', 'other GameDLL sections',
                                  'data/heap/registry/string scanning', 'candidate follow-up'])
        result = frozen_stream(budget, sections, evidence)
        for row in result['candidates']:
            row.pop('target_rva', None)
            row['field_displacement'] = struct.unpack('<I', bytes.fromhex(row['match_hex']))[0]
            row['field_displacement_hex'] = f"{row['field_displacement']:#x}"
            row['function_target_verified'] = False
        if result['complete']:
            result['reason'] = 'SINGLE_FIXED_CODE_SECTION_COMPLETE'
        return result
    index.stream_index = stream
    return index


def run(output, dependencies=None, clock=time.perf_counter):
    return private_index().run(output, dependencies=dependencies, clock=clock)


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
