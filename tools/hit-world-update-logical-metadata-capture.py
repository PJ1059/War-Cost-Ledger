"""Only 17 adjacent loaded exception records and two finite UW ownership chains.

Unknown table range [40537DC,40538A8), 204B twice. Per target at most four
unknown UW nodes; already freshly verified source ancestry is reused free
of that node limit. Cache metadata within this one capture, never scan or
read code bodies/handlers/heap/callees. Original known source PINs plus
PE/CALL/static Title-or-Ship/PID/context/modules share24KiB/32IO/2s soft.
Statement ownership is metadata only, never logical CFG/source proof.
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
WRAPPER = ROOT / 'tools/hit-world-update-switch-table-capture.py'
WRAPPER_SHA = 'e795f264094fe00a162e3b10839c159f6a3d0e5cf2aa3cdb60647b26b63ea5ca'
if hashlib.sha256(WRAPPER.read_bytes()).hexdigest() != WRAPPER_SHA:
    raise ValueError('WORLD_LOGICAL_FROZEN_SWITCH_WRAPPER_CHANGED')
spec = importlib.util.spec_from_file_location('_world_logical_private_switch', WRAPPER)
switch_private = importlib.util.module_from_spec(spec)
spec.loader.exec_module(switch_private)
v1 = switch_private.v1
REVISION = 'game_world_update_adjacent_exception_ownership_metadata_v1'
SWITCH_PACKET = ROOT / 'dist/hit-world-update-switch-table-live-20261013-v1'
SWITCH_JSON_SHA = 'aa0a746902e8c244599d15e00627d13470418e97be4b2f9ac5fa88fbc5fe2838'
SWITCH_BIN_SHA = '112a1fab7a620ab94143358f3ff3b505ec7b5a88694308d0a8da60b1ef0a290e'
SWITCH_PIN = (SWITCH_PACKET / 'callsite.bin').read_bytes()
HINT = switch_private.suffix_private.prefix_private.root_private.hint
WINDOW_RVA, RECORD_COUNT = HINT.HINT_RVA, 17
WINDOW_BYTES = RECORD_COUNT * 12
TARGETS = (0xAB62D6, 0xAB6A65)
MAX_UNKNOWN_NODES = 4
UNWIND_BEGIN, UNWIND_END = 0x2111000, 0x263BA0C
if len(SWITCH_PIN) != 24 or hashlib.sha256(SWITCH_PIN).hexdigest() != SWITCH_BIN_SHA:
    raise ValueError('WORLD_LOGICAL_COMPLETE_SWITCH_BINARY_CHANGED')


def validate_switch_packet():
    raw = (SWITCH_PACKET / 'callsite.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != SWITCH_JSON_SHA:
        raise ValueError('WORLD_LOGICAL_COMPLETE_SWITCH_PACKET_CHANGED')
    meta = json.loads(raw)
    expected = switch_private.validate_suffix_packet()['unwind_chain']
    if (not meta.get('complete') or meta.get('source_revision') != switch_private.REVISION
            or meta.get('fingerprint') != v1.frozen.profile.FINGERPRINT
            or meta.get('sha256') != SWITCH_BIN_SHA
            or not meta.get('full_source_pins_before_after_match')
            or not meta.get('table_before_after_match')
            or not meta.get('fresh_gates_verified')
            or not meta.get('fixed_record_verified_before_after')
            or meta.get('unwind_chain') != expected
            or tuple(struct.unpack('<6I', SWITCH_PIN)) !=
                (0xAB60BC, 0xAB60CD, 0xAB60DE, 0xAB60EF, 0xAB6100, 0xAB610E)):
        raise ValueError('WORLD_LOGICAL_COMPLETE_SWITCH_PROFILE')
    return meta


def validate_source():
    source = switch_private.validate_source()
    validate_switch_packet()
    source['complete_switch_mapping_packet'] = {
        'directory': str(SWITCH_PACKET.resolve()), 'metadata_sha256': SWITCH_JSON_SHA,
        'binary_sha256': SWITCH_BIN_SHA, 'source_complete': True,
        'table_rva': switch_private.TABLE_RVA, 'table_bytes': 24,
        'known_record_index': HINT.HINT_INDEX, 'known_record_rva': HINT.HINT_RVA,
        'known_record_hex': HINT.HINT_BYTES.hex()}
    source['logical_metadata_wrapper_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return source


_base_budget = v1.Budget


class Budget(_base_budget):
    def __init__(self, process, identity, clock=time.perf_counter):
        super().__init__(process, identity, clock)
        v1.frozen.DECLARATION_PURPOSES.add('logical_exception_window')


_original_header = v1.frozen.inspect_header


def inspect_header(budget):
    raw = _original_header(budget)
    section = v1.frozen.PE_OFFSET + 24 + 240 + 40
    if (struct.unpack_from('<II', raw, section + 8) != (UNWIND_END - UNWIND_BEGIN, UNWIND_BEGIN)
            or struct.unpack_from('<I', raw, section + 36)[0] != 0x40000040):
        raise ValueError('WORLD_LOGICAL_KNOWN_RODATA_SECTION_CHANGED')
    return raw


def capture(budget, evidence):
    expected = validate_switch_packet()['unwind_chain']
    reader = v1.frozen.profile.private_reader()
    reader.IMAGE_SIZE = v1.frozen.IMAGE_SIZE
    reader.MAX_FUNCTION_BYTES = v1.frozen.CODE_END - v1.frozen.CODE_BEGIN
    source_known = {tuple(node[key] for key in ('begin', 'end', 'unwind_rva')): i
                    for i, node in enumerate(expected)}
    metadata_cache, node_cache = {}, {}
    evidence.update(capture_purpose='STATIC_ADJACENT_EXCEPTION_AND_FINITE_UW_OWNERSHIP_ONLY',
        target_rva=WINDOW_RVA, source_callsite_rva=v1.TARGET_RVA, code_only=False,
        metadata_only=True, new_code_body_reads=0, binary_search_performed=False,
        unwind_chain=[], ownership=[], classification_ready=False, contract_ready=False,
        logical_function_complete=False, normal_CFG_closed=False,
        contact_argument_source_proven=False, handler_or_scope_reads=0,
        metadata_cache_reuses=0, all_sibling_fragments_captured=False)
    # Original post gates: header4096, CALL12, state8+4. Reserve them and
    # source-post four reads plus the exact204B window-post before each new UW IO.
    POST_BYTES, POST_CALLS = 84 + 4000 + 738 + 24 + WINDOW_BYTES + 4096 + 12 + 12, 9

    def reserve(size=0, calls=0):
        budget.require_capacity(POST_BYTES + size, POST_CALLS + calls)
        if budget.query_calls + POST_CALLS + calls > v1.MAX_READS:
            raise ValueError('WORLD_LOGICAL_POST_QUERY_RESERVATION_BUDGET')

    def source_pins():
        return (budget.read_module(switch_private.suffix_private.prefix_private.root_private.ROOT_BEGIN,
                    84, 'root_full_source_pin', True),
            budget.read_module(switch_private.suffix_private.prefix_private.BODY_BEGIN,
                    4000, 'current_full_prefix_source_pin', True),
            budget.read_module(switch_private.suffix_private.SUFFIX_BEGIN,
                    738, 'current_full_suffix_source_pin', True),
            budget.read_module(switch_private.TABLE_RVA, 24, 'finite_switch_table_data'))

    # Baseline includes source pre, both windows, seven source UW reads and all post gates.
    budget.require_capacity(2 * (84 + 4000 + 738 + 24) + 2 * WINDOW_BYTES + 52 + 4120, 21)
    if budget.query_calls + 21 > v1.MAX_READS:
        raise ValueError('WORLD_LOGICAL_BASELINE_QUERY_BUDGET')
    before = source_pins()
    if before != (switch_private.ROOT_PIN, switch_private.PREFIX_PIN,
                  switch_private.SUFFIX_PIN, SWITCH_PIN):
        raise ValueError('WORLD_LOGICAL_FRESH_SOURCE_PIN_CHANGED')
    raw = budget.read_module(WINDOW_RVA, WINDOW_BYTES, 'logical_exception_window')
    if raw[:12] != HINT.HINT_BYTES:
        raise ValueError('WORLD_LOGICAL_FRESH_FIRST_RECORD_CHANGED')
    records = []
    for i in range(RECORD_COUNT):
        begin, end, unwind = struct.unpack_from('<III', raw, i * 12)
        reader.validate_runtime_entry(begin, end, unwind)
        if not v1.frozen.CODE_BEGIN <= begin < end <= v1.frozen.CODE_END:
            raise ValueError('WORLD_LOGICAL_RECORD_OUTSIDE_CODE_SECTION')
        if records and records[-1]['end'] > begin:
            raise ValueError('WORLD_LOGICAL_RECORD_WINDOW_NOT_ORDERED')
        records.append({'index': HINT.HINT_INDEX + i, 'rva': WINDOW_RVA + i * 12,
            'raw_hex': raw[i*12:(i+1)*12].hex(), 'begin': begin, 'end': end,
            'unwind_rva': unwind})
    evidence['exception_records'] = records

    def metadata(rva, size):
        if not UNWIND_BEGIN <= rva < rva + size <= UNWIND_END:
            raise ValueError('WORLD_LOGICAL_UW_OUTSIDE_KNOWN_RODATA')
        key = rva, size
        if key in metadata_cache:
            evidence['metadata_cache_reuses'] += 1
            return metadata_cache[key]
        reserve(size, 1)
        data = budget.read_module(rva, size, 'unwind_metadata')
        metadata_cache[key] = data
        return data

    nodes = []
    reader.unwind_ancestry((records[0]['begin'], records[0]['end'], records[0]['unwind_rva']),
        metadata, nodes)
    evidence['unwind_chain'] = nodes
    if nodes != expected:
        raise ValueError('WORLD_LOGICAL_FRESH_SOURCE_CHAIN_CHANGED')
    for node in nodes:
        node_cache[tuple(node[key] for key in ('begin', 'end', 'unwind_rva'))] = node

    selected = []
    for target in TARGETS:
        hits = [row for row in records if row['begin'] <= target < row['end']]
        if len(hits) != 1:
            raise ValueError('WORLD_LOGICAL_TARGET_NOT_IN_FIXED_WINDOW: ' + hex(target))
        selected.append((target, hits[0]))

    for target, row in selected:
        current = row['begin'], row['end'], row['unwind_rva']
        chain, seen, seen_unwind, unknown, frame = [], set(), set(), 0, None
        while True:
            reader.validate_runtime_entry(*current)
            if not v1.frozen.CODE_BEGIN <= current[0] < current[1] <= v1.frozen.CODE_END:
                raise ValueError('WORLD_LOGICAL_CHAIN_DECLARATION_OUTSIDE_CODE_SECTION')
            if current in seen or current[2] in seen_unwind:
                raise ValueError('WORLD_LOGICAL_UW_CYCLE')
            seen.add(current); seen_unwind.add(current[2])
            if current in source_known:
                tail = nodes[source_known[current]:]
                if frame is not None and any(bytes.fromhex(n['header']['raw_hex'])[3] != frame for n in tail):
                    raise ValueError('WORLD_LOGICAL_UW_FRAME_MISMATCH')
                chain.extend(tail)
                evidence['metadata_cache_reuses'] += len(tail)
                break
            unknown += 1
            if unknown > MAX_UNKNOWN_NODES:
                raise ValueError('WORLD_LOGICAL_UNKNOWN_UW_NODE_LIMIT')
            if current in node_cache:
                node = node_cache[current]
                evidence['metadata_cache_reuses'] += 1
            else:
                begin, end, unwind = current
                header = metadata(unwind, 4)
                flags = reader.check_unwind_header(header)
                node = {'begin': begin, 'end': end, 'unwind_rva': unwind,
                        'header': {'rva': unwind, 'raw_hex': header.hex()}}
                if flags & 4:
                    chain_rva = unwind + 4 + 2 * ((header[2] + 1) & ~1)
                    chained = metadata(chain_rva, 12)
                    node['chain_entry'] = {'rva': chain_rva, 'raw_hex': chained.hex()}
                node_cache[current] = node
            header = bytes.fromhex(node['header']['raw_hex'])
            if frame is not None and header[3] != frame:
                raise ValueError('WORLD_LOGICAL_UW_FRAME_MISMATCH')
            frame = header[3]
            chain.append(node)
            if 'chain_entry' not in node:
                break
            current = struct.unpack('<III', bytes.fromhex(node['chain_entry']['raw_hex']))
        terminal = tuple(chain[-1][key] for key in ('begin', 'end', 'unwind_rva'))
        primary = tuple(nodes[-1][key] for key in ('begin', 'end', 'unwind_rva'))
        evidence['ownership'].append({'target_rva': target, 'record_index': row['index'],
            'declaration_begin': row['begin'], 'declaration_end': row['end'],
            'unwind_chain': chain, 'unknown_node_count': unknown,
            'same_AB5000_primary': terminal == primary, 'terminal_primary': list(terminal),
            'statement_ownership_only': True, 'CFG_or_runtime_object_proven': False})
    after = budget.read_module(WINDOW_RVA, WINDOW_BYTES, 'logical_exception_window')
    if after != raw or source_pins() != before:
        raise ValueError('WORLD_LOGICAL_WINDOW_OR_SOURCE_CHANGED_DURING_CAPTURE')
    evidence.update(fixed_record_verified_before_after=True,
        fresh_unwind_matches_complete_source=True, full_source_pins_before_after_match=True,
        exception_window_before_after_match=True, statement_ownership_metadata_complete=True,
        max_unknown_UW_nodes_per_target=MAX_UNKNOWN_NODES,
        fixed_record_after={'index': HINT.HINT_INDEX, 'rva': HINT.HINT_RVA, 'raw_hex': after[:12].hex()},
        ranges=[{'name': 'current_and_following_16_exception_records', 'module': 'game',
                 'rva': WINDOW_RVA, 'length': WINDOW_BYTES, 'binary_offset': 0}],
        code_bytes=0, metadata_bytes=WINDOW_BYTES, new_code_body_reads=0,
        declared_code_complete=False, logical_function_complete=False,
        unwind_scope_tables_read=False, unwind_full_codes_captured=False,
        boundary_kind='statement_ownership_metadata_only_not_logical_CFG_end')
    return raw


v1.REVISION, v1.validate_source, v1.Budget, v1.capture = REVISION, validate_source, Budget, capture
v1.frozen.inspect_header = inspect_header


def run(output, dependencies=None, clock=time.perf_counter):
    return v1.run(output, dependencies, clock)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.output), ensure_ascii=False, indent=2))
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
