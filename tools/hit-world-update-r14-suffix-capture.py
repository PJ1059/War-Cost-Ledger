"""Only remaining same-declaration suffix AB5FF4..AB62D6 (738B).

Root84 and complete current4000 are known source PINs before/after; only
unknown738 is saved. Fresh containing record/chain and original PE/CALL/
state/context/PID/module gates remain. 24KiB/32RPM-query/2s soft, no callee,
other declaration code, heap, native call, write or cloned executable code.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]
PREFIX_WRAPPER = ROOT / 'tools/hit-world-update-r14-prefix-capture.py'
PREFIX_WRAPPER_SHA = '648b84bdacf35efb13e23829a9169c51b10b42a1275ee31abe7e0fcb0ffa4500'
if hashlib.sha256(PREFIX_WRAPPER.read_bytes()).hexdigest() != PREFIX_WRAPPER_SHA:
    raise ValueError('R14_SUFFIX_FROZEN_PREFIX_WRAPPER_CHANGED')
spec = importlib.util.spec_from_file_location('_r14_suffix_private_prefix', PREFIX_WRAPPER)
prefix_private = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prefix_private)
v1 = prefix_private.v1
REVISION = 'game_world_update_r14_same_declaration_suffix_v1'
PREFIX_PACKET = ROOT / 'dist/hit-world-update-r14-prefix-live-20261013-v1'
PREFIX_JSON_SHA = '95322aa15bc813672c98e507db0cbde27302892e23a08a36713187ac6d3f52fe'
PREFIX_BIN_SHA = '81c9895e3b79ee97a3a393480f2feb69b00117da988fdcad760c158930503510'
PREFIX_PIN = (PREFIX_PACKET / 'callsite.bin').read_bytes()
ROOT_PIN = prefix_private.ROOT_PIN
SUFFIX_BEGIN, SUFFIX_END = 0xAB5FF4, 0xAB62D6
SUFFIX_BYTES = SUFFIX_END - SUFFIX_BEGIN
if len(PREFIX_PIN) != 4000 or hashlib.sha256(PREFIX_PIN).hexdigest() != PREFIX_BIN_SHA:
    raise ValueError('R14_SUFFIX_COMPLETE_PREFIX_BINARY_CHANGED')


def validate_prefix_packet():
    raw = (PREFIX_PACKET / 'callsite.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != PREFIX_JSON_SHA:
        raise ValueError('R14_SUFFIX_COMPLETE_PREFIX_PACKET_CHANGED')
    meta = json.loads(raw)
    if (not meta.get('complete') or meta.get('source_revision') != prefix_private.REVISION
            or meta.get('fingerprint') != v1.frozen.profile.FINGERPRINT
            or not meta.get('code_prefix_before_after_match')
            or not meta.get('root_full_source_pin_before_after_match')
            or not meta.get('fixed_record_verified_before_after')
            or not meta.get('fresh_unwind_matches_complete_source')
            or meta.get('sha256') != PREFIX_BIN_SHA
            or meta['unwind_chain'] != prefix_private.validate_initialization_packet()['unwind_chain']
            or meta.get('function_begin') != prefix_private.BODY_BEGIN
            or meta.get('function_end') != SUFFIX_END):
        raise ValueError('R14_SUFFIX_COMPLETE_PREFIX_PROFILE')
    return meta


def validate_source():
    source = prefix_private.validate_source()
    validate_prefix_packet()
    source['complete_current_prefix_packet'] = {'directory': str(PREFIX_PACKET.resolve()),
        'metadata_sha256': PREFIX_JSON_SHA, 'binary_sha256': PREFIX_BIN_SHA,
        'source_complete': True, 'prefix_rva': prefix_private.BODY_BEGIN,
        'prefix_bytes': 4000, 'full_prefix_pin_before_after_required': True}
    source['r14_suffix_wrapper_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return source


_base_budget = v1.Budget


class Budget(_base_budget):
    def __init__(self, process, identity, clock=time.perf_counter):
        super().__init__(process, identity, clock)
        # Known source4000 uses the total IO budget, not unknown-code subbudget.
        v1.frozen.DECLARATION_PURPOSES.add('r14_suffix_code')


def capture(budget, evidence):
    expected = validate_prefix_packet()['unwind_chain']
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
        capture_purpose='STATIC_SAME_DECLARATION_REMAINING_SUFFIX_ONLY',
        binary_search_performed=False, whole_world_update_captured=False,
        r14_unchanged_to_call_proven=False, classification_ready=False)
    begin, end = reader.find_function(budget, journal)
    evidence.update(function_begin=begin, function_end=end)
    reader.unwind_ancestry((begin, end, journal[-1]['unwind_rva']),
        lambda rva, size: reader.checked_metadata_read(budget, rva, size), nodes)
    if nodes != expected or not begin == prefix_private.BODY_BEGIN < SUFFIX_BEGIN < end == SUFFIX_END:
        raise ValueError('R14_SUFFIX_FRESH_DECLARATION_CHAIN_CHANGED')
    # Six source/code reads plus record-post and original four post gates.
    budget.require_capacity(84*2 + 4000*2 + SUFFIX_BYTES*2 + 12 + 4096 + 12 + 12, 11)
    if budget.query_calls + 11 > v1.MAX_READS:
        raise ValueError('R14_SUFFIX_POST_QUERY_RESERVATION_BUDGET')
    root_before = budget.read_module(prefix_private.root_private.ROOT_BEGIN, 84, 'root_full_source_pin', True)
    prefix_before = budget.read_module(prefix_private.BODY_BEGIN, 4000, 'current_full_prefix_source_pin', True)
    if root_before != ROOT_PIN or prefix_before != PREFIX_PIN:
        raise ValueError('R14_SUFFIX_FRESH_FULL_SOURCE_PIN_CHANGED')
    raw = budget.read_module(SUFFIX_BEGIN, SUFFIX_BYTES, 'r14_suffix_code', True)
    after = budget.read_module(SUFFIX_BEGIN, SUFFIX_BYTES, 'r14_suffix_code', True)
    prefix_after = budget.read_module(prefix_private.BODY_BEGIN, 4000, 'current_full_prefix_source_pin', True)
    root_after = budget.read_module(prefix_private.root_private.ROOT_BEGIN, 84, 'root_full_source_pin', True)
    if after != raw or prefix_after != prefix_before or root_after != root_before:
        raise ValueError('R14_SUFFIX_CODE_OR_SOURCE_CHANGED_DURING_CAPTURE')
    record_after = budget.read_module(prefix_private.root_private.hint.HINT_RVA, 12, 'exception_record')
    evidence['fixed_record_after'] = {'index': prefix_private.root_private.hint.HINT_INDEX,
        'rva': prefix_private.root_private.hint.HINT_RVA, 'raw_hex': record_after.hex()}
    if record_after != prefix_private.root_private.hint.HINT_BYTES:
        raise ValueError('R14_SUFFIX_RECORD_CHANGED_DURING_CAPTURE')
    evidence.update(fixed_record_verified_before_after=True, fresh_unwind_matches_complete_source=True,
        root_full_source_pin_before_after_match=True, current_full_prefix_pin_before_after_match=True,
        suffix_before_after_match=True,
        ranges=[{'name': 'world_update_same_declaration_suffix', 'module': 'game',
            'rva': SUFFIX_BEGIN, 'length': SUFFIX_BYTES, 'binary_offset': 0}],
        code_bytes=len(raw), declared_code_complete=False, logical_function_complete=False,
        extra_callee_reads=0, additional_ancestry_code_saved=False,
        unwind_scope_tables_read=False, unwind_full_codes_captured=False,
        boundary_kind='remaining_738B_same_declaration_only', offline_CFG_required=True)
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
