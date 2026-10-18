"""Only finite six-DWORD switch table Game AB7664..AB767C, twice (24B).

Known root84/current4000/suffix738 before/after source PINs plus fresh
record/chain/PE/CALL/state/context/PID/modules share24KiB/32RPM-query/2s.
Never follow a table target, callee or heap; never call or write Game.
Unknown mappings are retained as plain RVAs, never guessed from code shape.
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
WRAPPER = ROOT / 'tools/hit-world-update-r14-suffix-capture.py'
WRAPPER_SHA = '7ab73550b252a32b9c8d8b32ee8cedde50ce383c4524ad8c9d327c70fbfe8a8d'
if hashlib.sha256(WRAPPER.read_bytes()).hexdigest() != WRAPPER_SHA:
    raise ValueError('WORLD_SWITCH_FROZEN_SUFFIX_WRAPPER_CHANGED')
spec = importlib.util.spec_from_file_location('_world_switch_private_suffix', WRAPPER)
suffix_private = importlib.util.module_from_spec(spec)
spec.loader.exec_module(suffix_private)
v1 = suffix_private.v1
REVISION = 'game_world_update_finite_state_switch_table_v1'
SUFFIX_PACKET = ROOT / 'dist/hit-world-update-r14-suffix-live-20261013-v1'
SUFFIX_JSON_SHA = '47c7d3f431e5344e1f102bfd34119368081aec3932330e0c7a42c91dd4da5852'
SUFFIX_BIN_SHA = '3310fe6d1739836b6bd1a0ee9b28d3511e4d8ef5f8017334b63282a401db6f84'
SUFFIX_PIN = (SUFFIX_PACKET / 'callsite.bin').read_bytes()
PREFIX_PIN, ROOT_PIN = suffix_private.PREFIX_PIN, suffix_private.ROOT_PIN
TABLE_RVA, TABLE_BYTES = 0xAB7664, 24
SWITCH_RVA = 0xAB609B
SWITCH_BYTES = bytes.fromhex('418b861cc20a00ffc883f8057771488d15509f54ff8b8c826476ab004803caffe1')
if len(SUFFIX_PIN) != 738 or hashlib.sha256(SUFFIX_PIN).hexdigest() != SUFFIX_BIN_SHA:
    raise ValueError('WORLD_SWITCH_COMPLETE_SUFFIX_BINARY_CHANGED')


def validate_suffix_packet():
    raw = (SUFFIX_PACKET / 'callsite.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != SUFFIX_JSON_SHA:
        raise ValueError('WORLD_SWITCH_COMPLETE_SUFFIX_PACKET_CHANGED')
    meta = json.loads(raw)
    at = SWITCH_RVA - suffix_private.SUFFIX_BEGIN
    if (not meta.get('complete') or meta.get('source_revision') != suffix_private.REVISION
            or meta.get('fingerprint') != v1.frozen.profile.FINGERPRINT
            or meta.get('sha256') != SUFFIX_BIN_SHA
            or not meta.get('suffix_before_after_match')
            or not meta.get('current_full_prefix_pin_before_after_match')
            or not meta.get('root_full_source_pin_before_after_match')
            or not meta.get('fixed_record_verified_before_after')
            or meta['unwind_chain'] != suffix_private.validate_prefix_packet()['unwind_chain']
            or SUFFIX_PIN[at:at+len(SWITCH_BYTES)] != SWITCH_BYTES):
        raise ValueError('WORLD_SWITCH_SUFFIX_OR_SWITCH_SOURCE_PROFILE')
    return meta


def validate_source():
    source = suffix_private.validate_source()
    validate_suffix_packet()
    source['complete_suffix_packet'] = {'directory': str(SUFFIX_PACKET.resolve()),
        'metadata_sha256': SUFFIX_JSON_SHA, 'binary_sha256': SUFFIX_BIN_SHA, 'source_complete': True,
        'suffix_rva': suffix_private.SUFFIX_BEGIN, 'suffix_bytes': 738,
        'switch_source_rva': SWITCH_RVA, 'switch_source_hex': SWITCH_BYTES.hex()}
    source['switch_table_wrapper_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return source


_base_budget = v1.Budget


class Budget(_base_budget):
    def __init__(self, process, identity, clock=time.perf_counter):
        super().__init__(process, identity, clock)
        v1.frozen.DECLARATION_PURPOSES.add('finite_switch_table_data')


def capture(budget, evidence):
    expected = validate_suffix_packet()['unwind_chain']
    reader = v1.frozen.profile.private_reader()
    reader.REVISION, reader.TARGET_RVA, reader.TARGET_PIN = REVISION, v1.TARGET_RVA, v1.CALL_HEX
    reader.IMAGE_SIZE = v1.frozen.IMAGE_SIZE
    reader.EXCEPTION_RVA, reader.EXCEPTION_SIZE = v1.frozen.EXCEPTION_RVA, v1.frozen.EXCEPTION_SIZE
    reader.MAX_FUNCTION_BYTES = v1.frozen.CODE_END - v1.frozen.CODE_BEGIN
    reader.checked_metadata_read = lambda b, rva, size: b.read_module(rva, size,
        'exception_record' if v1.frozen.EXCEPTION_RVA <= rva < v1.frozen.EXCEPTION_RVA + v1.frozen.EXCEPTION_SIZE
        else 'unwind_metadata')
    journal, nodes = [], []
    evidence.update(exception_records=journal, unwind_chain=nodes,
        capture_purpose='STATIC_FINITE_SIX_DWORD_RVA_SWITCH_TABLE_ONLY',
        target_rva=TABLE_RVA, source_callsite_rva=v1.TARGET_RVA,
        binary_search_performed=False, new_code_body_reads=0, table_targets_followed=False,
        r14_unchanged_to_call_proven=False, classification_ready=False)
    begin, end = reader.find_function(budget, journal)
    evidence.update(function_begin=begin, function_end=end)
    reader.unwind_ancestry((begin, end, journal[-1]['unwind_rva']),
        lambda rva, size: reader.checked_metadata_read(budget, rva, size), nodes)
    if nodes != expected or not v1.frozen.CODE_BEGIN <= TABLE_RVA < TABLE_RVA+24 <= v1.frozen.CODE_END:
        raise ValueError('WORLD_SWITCH_FRESH_CHAIN_OR_TABLE_SCOPE_CHANGED')
    budget.require_capacity(84*2 + 4000*2 + 738*2 + 24*2 + 12 + 4096 + 12 + 12, 13)
    if budget.query_calls + 13 > v1.MAX_READS:
        raise ValueError('WORLD_SWITCH_POST_QUERY_RESERVATION_BUDGET')
    root_rva = suffix_private.prefix_private.root_private.ROOT_BEGIN
    def source_pins():
        return (budget.read_module(root_rva, 84, 'root_full_source_pin', True),
            budget.read_module(suffix_private.prefix_private.BODY_BEGIN, 4000, 'current_full_prefix_source_pin', True),
            budget.read_module(suffix_private.SUFFIX_BEGIN, 738, 'current_full_suffix_source_pin', True))
    before = source_pins()
    if before != (ROOT_PIN, PREFIX_PIN, SUFFIX_PIN):
        raise ValueError('WORLD_SWITCH_FRESH_FULL_SOURCE_PIN_CHANGED')
    raw = budget.read_module(TABLE_RVA, TABLE_BYTES, 'finite_switch_table_data')
    after = budget.read_module(TABLE_RVA, TABLE_BYTES, 'finite_switch_table_data')
    if after != raw or source_pins() != before:
        raise ValueError('WORLD_SWITCH_TABLE_OR_SOURCE_CHANGED_DURING_CAPTURE')
    hint = suffix_private.prefix_private.root_private.hint
    record = budget.read_module(hint.HINT_RVA, 12, 'exception_record')
    evidence['fixed_record_after'] = {'index': hint.HINT_INDEX, 'rva': hint.HINT_RVA, 'raw_hex': record.hex()}
    if record != hint.HINT_BYTES:
        raise ValueError('WORLD_SWITCH_RECORD_CHANGED_DURING_CAPTURE')
    evidence.update(fixed_record_verified_before_after=True, fresh_unwind_matches_complete_source=True,
        full_source_pins_before_after_match=True, table_before_after_match=True,
        ranges=[{'name': 'six_state_switch_DWORD_RVA_table', 'module': 'game',
            'rva': TABLE_RVA, 'length': TABLE_BYTES, 'binary_offset': 0}],
        code_bytes=0, data_bytes=len(raw), table_entry_count=6,
        table_entry_format='little-endian uint32 module RVA, not absolute pointer',
        table_target_rvas=list(struct.unpack('<6I', raw)), mapping_verified=False,
        declared_code_complete=False, logical_function_complete=False,
        extra_callee_reads=0, unwind_scope_tables_read=False, unwind_full_codes_captured=False,
        boundary_kind='fixed_24B_table_only_no_target_dereference', offline_CFG_required=True)
    return raw


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
