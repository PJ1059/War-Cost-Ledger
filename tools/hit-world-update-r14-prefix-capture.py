"""Only current declaration AB5054..AB5FF4 (4000B) through contact CALL.

Full known root84 is a fresh before/after source PIN, not a new code scope.
The fixed containing record/four-node chain, PE/CALL PIN/state/context/PID/
module gates remain. Both unknown4000 snapshots must match; save one body.
24KiB/32RPM-query/2s soft, no whole world-update, callee, heap, call or write.
Offline CFG analysis is separate and uses the existing isolated decoder.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]
FROZEN_ROOT = ROOT / 'tools/hit-world-update-root-prefix-capture.py'
FROZEN_ROOT_SHA = '5502e951a162681e291c77181f0faf579c78ed988e48e1c91c8d20a040286946'
if hashlib.sha256(FROZEN_ROOT.read_bytes()).hexdigest() != FROZEN_ROOT_SHA:
    raise ValueError('R14_PREFIX_FROZEN_ROOT_WRAPPER_CHANGED')
spec = importlib.util.spec_from_file_location('_r14_prefix_private_root', FROZEN_ROOT)
root_private = importlib.util.module_from_spec(spec)
spec.loader.exec_module(root_private)
v1 = root_private.v1
REVISION = 'game_world_update_r14_to_contact_call_prefix_v1'
INITIALIZATION_PACKET = ROOT / 'dist/hit-world-update-root-prefix-live-20261013-v1'
INITIALIZATION_JSON_SHA = 'f990919cf354a446f74728942c2236c840f68169e90a6034c3fb13786981f9a3'
INITIALIZATION_BIN_SHA = '279bbfda6d08a0386022bbc5c7af02ab56f2ff14d15d3074d728d1abb120be89'
BODY_BEGIN, BODY_END = 0xAB5054, 0xAB5FF4
BODY_BYTES = BODY_END - BODY_BEGIN
ROOT_PIN = (INITIALIZATION_PACKET / 'callsite.bin').read_bytes()
if len(ROOT_PIN) != 84 or hashlib.sha256(ROOT_PIN).hexdigest() != INITIALIZATION_BIN_SHA:
    raise ValueError('R14_PREFIX_INITIALIZATION_BINARY_CHANGED')


def validate_initialization_packet():
    raw = (INITIALIZATION_PACKET / 'callsite.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != INITIALIZATION_JSON_SHA:
        raise ValueError('R14_PREFIX_INITIALIZATION_PACKET_CHANGED')
    meta = json.loads(raw)
    if (not meta.get('complete') or meta.get('source_revision') != root_private.REVISION
            or meta.get('fingerprint') != v1.frozen.profile.FINGERPRINT
            or not meta.get('fresh_unwind_matches_complete_source')
            or not meta.get('fixed_record_verified_before_after')
            or not meta.get('root_prefix_code_before_after_match')
            or meta.get('sha256') != INITIALIZATION_BIN_SHA
            or meta.get('child_code_bytes') != 0
            or meta['unwind_chain'] != root_private.validate_packet()['unwind_chain']
            or ROOT_PIN[37:44].hex() != '4c8b3514138702'):
        raise ValueError('R14_PREFIX_INITIALIZATION_PROFILE')
    return meta


def validate_source():
    source = root_private.validate_source()
    validate_initialization_packet()
    source['root_initialization_packet'] = {'directory': str(INITIALIZATION_PACKET.resolve()),
        'metadata_sha256': INITIALIZATION_JSON_SHA, 'binary_sha256': INITIALIZATION_BIN_SHA,
        'source_complete': True, 'root_rva': root_private.ROOT_BEGIN,
        'root_prefix_hex': ROOT_PIN.hex(), 'root_full_pin_before_after_required': True}
    source['r14_prefix_wrapper_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return source


_base_budget = v1.Budget


class Budget(_base_budget):
    def __init__(self, process, identity, clock=time.perf_counter):
        super().__init__(process, identity, clock)
        v1.frozen.DECLARATION_PURPOSES.add('r14_code_prefix')


def capture(budget, evidence):
    expected = validate_initialization_packet()['unwind_chain']
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
        capture_purpose='STATIC_CURRENT_DECLARATION_PREFIX_R14_DEF_USE_TO_CONTACT_CALL',
        source_callsite_rva=v1.TARGET_RVA, binary_search_performed=False,
        fixed_record_verified_before_after=False, whole_world_update_captured=False,
        r14_unchanged_to_call_proven=False, classification_ready=False)
    begin, end = reader.find_function(budget, journal)
    evidence.update(function_begin=begin, function_end=end)
    reader.unwind_ancestry((begin, end, journal[-1]['unwind_rva']),
        lambda rva, size: reader.checked_metadata_read(budget, rva, size), nodes)
    if nodes != expected or not begin == BODY_BEGIN < BODY_END <= end or BODY_BYTES != 4000:
        raise ValueError('R14_PREFIX_FRESH_DECLARATION_CHAIN_CHANGED')
    # Known root84 twice, body4000 twice, record12 and original four post gates.
    budget.require_capacity(84 * 2 + BODY_BYTES * 2 + 12 + 4096 + 12 + 12, 9)
    if budget.query_calls + 9 > v1.MAX_READS:
        raise ValueError('R14_PREFIX_POST_QUERY_RESERVATION_BUDGET')
    root_before = budget.read_module(root_private.ROOT_BEGIN, 84, 'root_full_source_pin', True)
    if root_before != ROOT_PIN:
        raise ValueError('R14_PREFIX_FRESH_ROOT_PIN_CHANGED')
    raw = budget.read_module(BODY_BEGIN, BODY_BYTES, 'r14_code_prefix', True)
    if raw[-12:].hex() != v1.PIN_HEX:
        raise ValueError('R14_PREFIX_BODY_CALL_PIN_CHANGED')
    after = budget.read_module(BODY_BEGIN, BODY_BYTES, 'r14_code_prefix', True)
    root_after = budget.read_module(root_private.ROOT_BEGIN, 84, 'root_full_source_pin', True)
    if after != raw or root_after != root_before:
        raise ValueError('R14_PREFIX_CODE_CHANGED_DURING_CAPTURE')
    record_after = budget.read_module(root_private.hint.HINT_RVA, 12, 'exception_record')
    evidence['fixed_record_after'] = {'index': root_private.hint.HINT_INDEX,
        'rva': root_private.hint.HINT_RVA, 'raw_hex': record_after.hex()}
    if record_after != root_private.hint.HINT_BYTES:
        raise ValueError('R14_PREFIX_RECORD_CHANGED_DURING_CAPTURE')
    evidence.update(fixed_record_verified_before_after=True,
        fresh_unwind_matches_complete_source=True, root_full_source_pin_before_after_match=True,
        code_prefix_before_after_match=True,
        ranges=[{'name': 'world_update_current_declaration_prefix_through_contact_CALL',
            'module': 'game', 'rva': BODY_BEGIN, 'length': BODY_BYTES, 'binary_offset': 0}],
        code_bytes=len(raw), binary_pin_offset=BODY_BYTES-12, binary_call_offset=BODY_BYTES-5,
        declared_code_complete=False, logical_function_complete=False,
        unwind_scope_tables_read=False, unwind_full_codes_captured=False,
        additional_ancestry_code_saved=False, extra_callee_reads=0,
        boundary_kind='one_current_declaration_prefix_plus_known_root_source_pin_only',
        offline_CFG_required=True)
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
