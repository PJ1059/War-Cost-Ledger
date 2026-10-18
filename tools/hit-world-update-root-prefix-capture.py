"""Only the three contiguous AB5000..AB5054 ancestor declarations (84B).

The complete frozen v2 packet pins the containing record and four-node
unwind chain. Freshly read that record/chain, compare it exactly, and read
only their three ancestor declarations, then compare the same 84B again.
Reuse the original PE/CALL-PIN/state/context/PID/module pre/post gates and
24KiB/32RPM-query/2s soft limits. No child body, scan, callee, heap, native
call or write. The prefix alone cannot prove R14 unchanged at the CALL.
Reused output names are callsite.bin/callsite.json within a new folder.
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
HINT_WRAPPER = ROOT / 'tools/hit-world-update-contact-callsite-hint-capture.py'
HINT_WRAPPER_SHA = 'adead4cd720f723421e591d8f5d65d75d7d05573f3c94557e40d92ac2d2adad7'
if hashlib.sha256(HINT_WRAPPER.read_bytes()).hexdigest() != HINT_WRAPPER_SHA:
    raise ValueError('WORLD_ROOT_PREFIX_FROZEN_HINT_WRAPPER_CHANGED')
spec = importlib.util.spec_from_file_location('_world_root_prefix_private_hint', HINT_WRAPPER)
hint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hint)
v1 = hint.v1
REVISION = 'game_world_update_three_ancestor_root_prefix_v1'
SOURCE_PACKET = ROOT / 'dist/hit-world-update-contact-callsite-live-20261013-v2'
PACKET_JSON_SHA = '50cd151b7605b0bc81a0311da9d5cdf116451c546540b0d8c3758ff39960c6d0'
PACKET_BIN_SHA = '3b921467decdef22b29ac25051a2e9423fadf81a80212368f29fe97dbc2478fc'
FRAME_SOURCE = ROOT / 'dist/hit-game-plugin-table-update-live-20261013-v1/plugin-table-update.bin'
FRAME_SOURCE_SHA = '03b3fd1cd3459fb3c3d6eb71e47a806dd2376ccd7f36dbc1f60f606bd446f546'
ROOT_BEGIN, ROOT_END = 0xAB5000, 0xAB5054
ANCESTOR_RANGES = ((0xAB5000, 0xAB502C), (0xAB502C, 0xAB5047), (0xAB5047, 0xAB5054))


def validate_packet(path=SOURCE_PACKET):
    packet = Path(path)
    raw = (packet / 'callsite.json').read_bytes()
    binary = (packet / 'callsite.bin').read_bytes()
    if (hashlib.sha256(raw).hexdigest() != PACKET_JSON_SHA
            or hashlib.sha256(binary).hexdigest() != PACKET_BIN_SHA):
        raise ValueError('WORLD_ROOT_PREFIX_COMPLETE_PACKET_CHANGED')
    meta = json.loads(raw)
    chain = meta.get('unwind_chain', [])
    if (not meta.get('complete') or meta.get('source_revision') != hint.REVISION
            or meta.get('fingerprint') != v1.frozen.profile.FINGERPRINT
            or not meta.get('fresh_gates_verified')
            or not meta.get('fixed_record_verified_before_after')
            or meta.get('sha256') != PACKET_BIN_SHA or len(binary) != 117
            or meta.get('function_begin') != hint.DECL_BEGIN
            or meta.get('function_end') != hint.DECL_END
            or len(chain) != 4
            or tuple((row['begin'], row['end']) for row in reversed(chain[1:])) != ANCESTOR_RANGES
            or chain[0]['unwind_rva'] != hint.UNWIND_RVA
            or binary[89:101].hex() != v1.PIN_HEX
            or meta.get('source', {}).get('sha256') != v1.SOURCE_SHA):
        raise ValueError('WORLD_ROOT_PREFIX_COMPLETE_PACKET_PROFILE')
    # Fresh metadata must equal these source nodes; code is not taken from them.
    return meta


def validate_source():
    source = hint._original_source()
    packet = validate_packet()
    frame = FRAME_SOURCE.read_bytes()
    if (hashlib.sha256(frame).hexdigest() != FRAME_SOURCE_SHA
            or frame[241:246].hex() != 'e812695c00'
            or 0x4EE6E9 + 5 + struct.unpack_from('<i', frame, 242)[0] != ROOT_BEGIN):
        raise ValueError('WORLD_ROOT_PREFIX_FRAME_CALL_SOURCE_CHANGED')
    source.update(complete_packet={'directory': str(SOURCE_PACKET.resolve()),
        'metadata_sha256': PACKET_JSON_SHA, 'binary_sha256': PACKET_BIN_SHA,
        'source_complete': True, 'containing_record_index': hint.HINT_INDEX,
        'unwind_chain': packet['unwind_chain']},
        frame_call_source={'path': str(FRAME_SOURCE.resolve()), 'sha256': FRAME_SOURCE_SHA,
            'call_rva': 0x4EE6E9, 'call_hex': 'e812695c00', 'target_rva': ROOT_BEGIN,
            'on_disk_saved_evidence_only': True},
        root_prefix_wrapper_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        frozen_hint_wrapper_sha256=HINT_WRAPPER_SHA)
    return source


_base_budget = v1.Budget


class Budget(_base_budget):
    def __init__(self, process, identity, clock=time.perf_counter):
        super().__init__(process, identity, clock)
        v1.frozen.DECLARATION_PURPOSES.add('root_prefix_code')


def capture(budget, evidence):
    expected = validate_packet()['unwind_chain']
    reader = v1.frozen.profile.private_reader()  # Private fixed-record fresh reader.
    reader.REVISION, reader.TARGET_RVA, reader.TARGET_PIN = REVISION, v1.TARGET_RVA, v1.CALL_HEX
    reader.IMAGE_SIZE = v1.frozen.IMAGE_SIZE
    reader.EXCEPTION_RVA, reader.EXCEPTION_SIZE = v1.frozen.EXCEPTION_RVA, v1.frozen.EXCEPTION_SIZE
    reader.MAX_FUNCTION_BYTES = v1.frozen.CODE_END - v1.frozen.CODE_BEGIN
    reader.checked_metadata_read = lambda b, rva, size: b.read_module(rva, size,
        'exception_record' if v1.frozen.EXCEPTION_RVA <= rva < v1.frozen.EXCEPTION_RVA + v1.frozen.EXCEPTION_SIZE
        else 'unwind_metadata')
    journal, nodes = [], []
    evidence.update(exception_records=journal, unwind_chain=nodes,
        capture_purpose='STATIC_THREE_CONTIGUOUS_UNWIND_ANCESTOR_ROOT_PREFIX_ONLY',
        target_rva=ROOT_BEGIN, source_callsite_rva=v1.TARGET_RVA,
        binary_search_performed=False, fixed_record_verified_before_after=False,
        child_code_bytes=0, root_prefix_unchanged_at_call_proven=False)
    begin, end = reader.find_function(budget, journal)
    evidence.update(function_begin=begin, function_end=end)
    reader.unwind_ancestry((begin, end, journal[-1]['unwind_rva']),
        lambda rva, size: reader.checked_metadata_read(budget, rva, size), nodes)
    if nodes != expected:
        raise ValueError('WORLD_ROOT_PREFIX_FRESH_UNWIND_CHAIN_CHANGED')
    ordered = [(node['begin'], node['end']) for node in reversed(nodes[1:])]
    if (tuple(ordered) != ANCESTOR_RANGES or ordered[0][0] != ROOT_BEGIN
            or ordered[-1][1] != ROOT_END
            or any(left[1] != right[0] for left, right in zip(ordered, ordered[1:]))
            or sum(hi - lo for lo, hi in ordered) != 84):
        raise ValueError('WORLD_ROOT_PREFIX_ANCESTOR_SCOPE_CHANGED')
    # Two84B reads, record-post12B and the original four post-gate IO calls.
    budget.require_capacity(84 * 2 + 12 + 4096 + 12 + 12, 7)
    if budget.query_calls + 7 > v1.MAX_READS:
        raise ValueError('WORLD_ROOT_PREFIX_POST_QUERY_RESERVATION_BUDGET')
    raw = budget.read_module(ROOT_BEGIN, 84, 'root_prefix_code', True)
    raw_after = budget.read_module(ROOT_BEGIN, 84, 'root_prefix_code', True)
    if raw_after != raw:
        raise ValueError('WORLD_ROOT_PREFIX_CODE_CHANGED_DURING_CAPTURE')
    record_after = budget.read_module(hint.HINT_RVA, 12, 'exception_record')
    evidence['fixed_record_after'] = {'index': hint.HINT_INDEX, 'rva': hint.HINT_RVA,
                                    'raw_hex': record_after.hex()}
    if record_after != hint.HINT_BYTES:
        raise ValueError('WORLD_ROOT_PREFIX_RECORD_CHANGED_DURING_CAPTURE')
    ranges, offset = [], 0
    for lo, hi in ordered:
        ranges.append({'name': 'world_update_root_ancestor_declaration', 'module': 'game',
                       'rva': lo, 'length': hi - lo, 'binary_offset': offset})
        offset += hi - lo
    evidence.update(fixed_record_verified_before_after=True, fresh_unwind_matches_complete_source=True,
        ranges=ranges, code_bytes=len(raw), root_prefix_code_before_after_match=True,
        selected_ancestor_code_complete=True, declared_code_complete=False,
        logical_function_complete=False, all_sibling_fragments_captured=False,
        boundary_kind='three_contiguous_source_pinned_unwind_ancestor_declarations_only',
        unwind_scope_tables_read=False, unwind_full_codes_captured=False,
        instruction_boundary_verified=False, r14_initial_definition_proven=False)
    return raw


# All changes apply only to independently loaded private instances.
v1.REVISION = REVISION
v1.validate_source = validate_source
v1.Budget = Budget
v1.capture = capture


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
