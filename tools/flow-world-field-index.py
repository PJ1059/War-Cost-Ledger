"""One read-only index of two literal World-field operands in EXE section0.

Only the exact declared executable section [1000,13F464C), no other EXE or
GameDLL section/body/heap/string scan. A 51B in-memory tail defers incomplete
52B candidate windows across chunks; RVAs are deduplicated. Maximum64 rows,
24MiB/256RPM/query/2s soft including source PINs and Ship/World gates.
Matches are candidates only, never a verified callback consumer or event.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
REVISION = 'flow_world_two_field_section0_index_v1'
WORLD_TOOL = ROOT / 'tools/flow-world-reference-capture.py'
WORLD_TOOL_SHA = '191958e00d0f09e805a818f2a487dd3b601d22129721f3f3d6bf4e2ecce70c15'
if hashlib.sha256(WORLD_TOOL.read_bytes()).hexdigest() != WORLD_TOOL_SHA:
    raise ValueError('FLOW_INDEX_FROZEN_SOURCE_CHANGED')
spec = importlib.util.spec_from_file_location('_flow_field_index_world_source', WORLD_TOOL)
world = importlib.util.module_from_spec(spec)
spec.loader.exec_module(world)
world.iat.flow.MAX_BYTES, world.iat.flow.MAX_READS = 24 * 1024 * 1024, 256
world.iat.flow.MAX_CODE_BYTES = 256 * 1024
CHUNK_BYTES = 256 * 1024
TAIL_BYTES = 51
MAX_CANDIDATES = 64
PATTERNS = (bytes.fromhex('d8012300'), bytes.fromhex('e0012300'))
SECTION = {'index': 0, 'rva': 0x1000, 'virtual_size': 20919884,
           'end_exclusive': 0x13F464C, 'characteristics': 0x60000020}
WORLD_SOURCE = ROOT / 'dist/flow-world-reference-live-20261012-v1/world-reference.json'
WORLD_SOURCE_SHA = 'eec0caef67bea94cf6546dbf1907a9d6aab038e660ead424d959beb24a6cd0c3'


def validate_world_source(path=WORLD_SOURCE):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != WORLD_SOURCE_SHA:
        raise ValueError('FLOW_INDEX_WORLD_SOURCE_CHANGED')
    meta = json.loads(raw)
    if (not meta.get('complete') or not meta.get('fields_ready')
            or not meta.get('path_snapshots_match') or meta['observation']['reference_i32'] != -2
            or meta['fingerprint'] != world.iat.flow.FINGERPRINT):
        raise ValueError('FLOW_INDEX_WORLD_SOURCE_PROFILE')
    return {'path': str(Path(path).resolve()), 'sha256': WORLD_SOURCE_SHA,
            'reference_i32_observed': -2, 'historical_only': True,
            'old_l_type_verified': False, 'registry_reads': 0}


def inspect_section(budget):
    raw = budget.read_module(0, 4096, 'exe_header_profile')
    pe = struct.unpack_from('<I', raw, 60)[0]
    if raw[:2] != b'MZ' or pe != 0x1E0 or raw[pe:pe + 4] != b'PE\0\0':
        raise ValueError('FLOW_INDEX_EXE_DOS_NT_PROFILE')
    if (struct.unpack_from('<H', raw, pe + 4)[0] != 0x8664
            or struct.unpack_from('<H', raw, pe + 6)[0] != 19
            or struct.unpack_from('<H', raw, pe + 20)[0] != 240):
        raise ValueError('FLOW_INDEX_EXE_HEADER_PROFILE')
    optional = pe + 24
    if (struct.unpack_from('<H', raw, optional)[0] != 0x20B
            or struct.unpack_from('<I', raw, optional + 56)[0] != world.iat.flow.EXE_IMAGE_SIZE):
        raise ValueError('FLOW_INDEX_EXE_IMAGE_PROFILE')
    first = optional + 240
    virtual_size, rva = struct.unpack_from('<II', raw, first + 8)
    characteristics = struct.unpack_from('<I', raw, first + 36)[0]
    selected = {'index': 0, 'rva': rva, 'virtual_size': virtual_size,
                'end_exclusive': rva + virtual_size, 'characteristics': characteristics}
    if selected != SECTION:
        raise ValueError('FLOW_INDEX_SECTION0_PROFILE_CHANGED')
    return {**selected, 'pe_offset': pe, 'section_count': 19,
            'section_header_hex': raw[first:first + 40].hex(),
            'loaded_header_sha256': hashlib.sha256(raw).hexdigest(),
            'loaded_header_bytes': 4096}


def next_matches(buffer):
    """Merge only the two fixed byte-search streams without collecting all hits."""
    positions = [buffer.find(pattern) for pattern in PATTERNS]
    while any(at >= 0 for at in positions):
        index = min((i for i in range(2) if positions[i] >= 0), key=lambda i: positions[i])
        at = positions[index]
        yield at, PATTERNS[index]
        positions[index] = buffer.find(PATTERNS[index], at + 1)


def stream_index(budget, section, evidence):
    start, end = section['rva'], section['end_exclusive']
    if not (SECTION['rva'] == start < end <= SECTION['end_exclusive']):
        raise ValueError('FLOW_INDEX_OUTSIDE_SECTION0')
    cursor, minimum_new_rva, tail, rows, seen = start, start, b'', [], set()
    payload_bytes = payload_reads = 0
    evidence['stream'] = {'payload_bytes': 0, 'payload_reads': 0, 'candidate_count': 0,
                          'tail_bytes_max': TAIL_BYTES, 'whole_binary_saved': False}
    while cursor < end:
        address = budget.identity['exe_base'] + cursor
        region = budget.query(address)
        protection = region['protect']
        if not (region['state'] == 0x1000 and region['type'] == 0x1000000
                and not protection & 0x100 and protection & 0xFF in (2, 4, 8, 0x20, 0x40, 0x80)
                and region['base'] <= address < region['base'] + region['size']):
            raise ValueError('FLOW_INDEX_SECTION_REGION_UNREADABLE')
        size = min(CHUNK_BYTES, end - cursor, region['base'] + region['size'] - address)
        if size <= 0:
            raise ValueError('FLOW_INDEX_CHUNK_INVALID')
        # Keep enough operations/bytes for max64-item second World+Ship gate.
        budget.require_capacity(size + 572, 1 + 9)
        raw = budget.read(address, size, 'field_index_payload')
        payload_reads += 1
        payload_bytes += len(raw)
        evidence['stream'].update(payload_bytes=payload_bytes, payload_reads=payload_reads)
        buffer = tail + raw
        buffer_rva = cursor - len(tail)
        block_end = cursor + len(raw)
        last = block_end == end
        for at, pattern in next_matches(buffer):
            rva = buffer_rva + at
            if rva < minimum_new_rva or rva in seen:
                continue
            if not last and rva + 4 + 32 > block_end:
                continue  # Defer until 51B tail plus next chunk contains full context.
            if len(rows) == MAX_CANDIDATES:
                evidence['stream'].update(candidate_count=len(rows), truncated=True,
                                          limit_rva=rva, reason='CANDIDATE_LIMIT')
                return {'complete': False, 'truncated': True, 'reason': 'CANDIDATE_LIMIT',
                        'candidates': rows, 'scanned_end_exclusive': block_end,
                        'processed_candidate_start_end_exclusive': rva,
                        'payload_bytes': payload_bytes, 'payload_reads': payload_reads}
            window_start, window_end = max(start, rva - 16), min(end, rva + 4 + 32)
            if not buffer_rva <= window_start < window_end <= block_end:
                raise ValueError('FLOW_INDEX_CONTEXT_WINDOW_UNAVAILABLE')
            window = buffer[window_start - buffer_rva:window_end - buffer_rva]
            rows.append({'rva': rva, 'pattern_hex': pattern.hex(),
                         'window_rva': window_start, 'window_hex': window.hex(),
                         'window_bytes': len(window), 'match_offset': rva - window_start,
                         'before_bytes': rva - window_start,
                         'after_bytes': window_end - rva - 4,
                         'section_boundary_truncated': window_start != rva - 16 or window_end != rva + 36,
                         'semantic_status': 'BYTE_CANDIDATE_ONLY'})
            seen.add(rva)
            evidence['stream']['candidate_count'] = len(rows)
        minimum_new_rva = block_end if last else max(start, block_end - 35)
        tail = buffer[-TAIL_BYTES:]
        cursor = block_end
        budget.time_gate()
    return {'complete': True, 'truncated': False, 'reason': 'FIXED_SECTION_COMPLETE',
            'candidates': rows, 'scanned_end_exclusive': end,
            'processed_candidate_start_end_exclusive': end,
            'payload_bytes': payload_bytes, 'payload_reads': payload_reads}


def run(output, dependencies=None, clock=time.perf_counter):
    folder = Path(output).resolve()
    if folder.exists():
        raise ValueError('FLOW_INDEX_OUTPUT_EXISTS: use a new evidence folder')
    folder.mkdir(parents=True)
    evidence = {'source_revision': REVISION, 'complete': False, 'source_gates_verified': False,
                'classification_ready': False, 'consumer_proven': False, 'native_called': False,
                'native_written': False, 'registry_reads': 0, 'whole_binary_saved': False,
                'scanning_attempted': False, 'attempts': 1,
                'patterns': [pattern.hex() for pattern in PATTERNS],
                'excluded': ['other EXE sections', 'Winlice/boot', 'GameDLL code', 'heap/string scanning', 'Lua registry'],
                'cannot_infer_absence_outside_selected_section': True}
    budget = None
    try:
        evidence['world_source'] = validate_world_source()
        evidence['setter_source'] = world.iat.validate_source()
        evidence['sdk_source'] = world.validate_sdk_source()
        lua = world.iat.load_lua_file()
        deps = dependencies if dependencies is not None else world.iat.load_dependencies()
        stamps = deps['fingerprints']()
        pids = tuple(deps['game_processes']())
        if len(pids) != 1:
            raise ValueError('FLOW_INDEX_EXPECTS_ONE_RUNNING_GAME')
        pid = pids[0]
        identity = deps['resolve_game'](pid)
        world.iat.validate_identity(identity, stamps, lua, deps)
        evidence.update(game_pid=pid, identity=identity, fingerprint=world.iat.flow.FINGERPRINT)
        with deps['Process'](pid) as process:
            budget = world.Budget(process, identity, clock)
            before = deps['ship_state'](budget, identity)
            evidence['ship_before'] = before
            if before['state'] != 3:
                raise ValueError('FLOW_INDEX_EXPECTS_SHIP')
            evidence['pins'] = []
            for rva, pin in ((world.iat.flow.TARGET_RVA, world.iat.flow.TARGET_PIN), *world.WORLD_PINS):
                raw = budget.read_module(rva, len(bytes.fromhex(pin)), 'identity_pin', True)
                evidence['pins'].append({'module': 'exe', 'rva': rva, 'hex': raw.hex(), 'matched': raw.hex() == pin})
                if raw.hex() != pin:
                    raise ValueError('FLOW_INDEX_PIN_MISMATCH')
            section = inspect_section(budget)
            evidence['section'] = section
            first = world.read_snapshot(budget, before['context'])
            evidence['scanning_attempted'] = True
            indexed = stream_index(budget, section, evidence)
            second = world.read_snapshot(budget, before['context'])
            if first != second:
                raise ValueError('FLOW_INDEX_WORLD_OR_REFERENCE_CHANGED')
            after = deps['ship_state'](budget, identity)
            evidence['ship_after'] = after
            if before != after:
                raise ValueError('FLOW_INDEX_SHIP_CHANGED')
            budget.time_gate()
        final = deps['resolve_game'](pid)
        world.iat.validate_identity(final, stamps, lua, deps)
        if final != identity or tuple(deps['game_processes']()) != (pid,):
            raise ValueError('FLOW_INDEX_MODULE_CHANGED')
        world.sdk_stats_unchanged(evidence['sdk_source'])
        budget.time_gate()
        evidence.update(indexed, source_gates_verified=True, current_world_observation=first,
                        current_world_matches_historical_no_ref=first['reference_i32'] == -2,
                        captured_at=datetime.now(timezone.utc).isoformat(),
                        budget=budget.summary(), read_records=budget.records,
                        chunk_bytes_max=CHUNK_BYTES, tail_bytes=TAIL_BYTES,
                        candidate_limit=MAX_CANDIDATES)
        name = 'field-index.json' if indexed['complete'] else 'field-index.truncated.json'
        report = folder / name
        report.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', 'utf8')
        status = {'status': 'complete' if indexed['complete'] else 'truncated',
                  'source_revision': REVISION, 'json_path': str(report),
                  'sha256': hashlib.sha256(report.read_bytes()).hexdigest()}
        world.iat.flow.tail['write_status'](folder, status)
        return status
    except Exception as error:
        if budget is not None:
            evidence.update(budget=budget.summary(), read_records=budget.records)
        failure = {**evidence, 'status': 'failed', 'complete': False, 'source_gates_verified': False,
                   'error': str(error), 'results_withheld': True,
                   'failed_at': datetime.now(timezone.utc).isoformat()}
        # Do not save partial code windows after an IO or source/session failure.
        failure.pop('candidates', None)
        report = folder / 'field-index.incomplete.json'
        report.write_text(json.dumps(failure, ensure_ascii=False, indent=2) + '\n', 'utf8')
        world.iat.flow.tail['write_status'](folder, {**failure, 'json_path': str(report)})
        raise


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
