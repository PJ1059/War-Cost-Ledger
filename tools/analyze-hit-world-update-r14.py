"""Offline reachable x64 CFG/R14 def-use for the fixed captured CALL prefix.

Uses the same existing Temp Capstone dependency as tmp/disassemble-fire-code.py.
No capture API imports, Game access, new dependency installation or MOD code.
Calls are not followed. R14 preservation across calls is an explicit x64 ABI
assumption; indirect/out-of-scope branches and decode ambiguity withhold proof.
"""
from __future__ import annotations

import argparse
from collections import deque
import hashlib
import json
from pathlib import Path
import struct
import sys

DECODER_DIR = Path('external/hd2-fire-analysis-deps')
sys.path.insert(0, str(DECODER_DIR))
import capstone
from capstone.x86 import X86_OP_IMM

ENTRY, BODY_BEGIN, CALL_PC, END = 0xAB5000, 0xAB5054, 0xAB5FEF, 0xAB5FF4
ROOT_SHA = '279bbfda6d08a0386022bbc5c7af02ab56f2ff14d15d3074d728d1abb120be89'
ROOT_METADATA_SHA = 'f990919cf354a446f74728942c2236c840f68169e90a6034c3fb13786981f9a3'
ROOT_LOAD, ROOT_LOAD_HEX = 0xAB5025, '4c8b3514138702'
CALL_HEX = 'e8fc618f00'
TAIL_PIN = '498d8e307e4f04' + CALL_HEX
R14_NAMES = {'r14', 'r14d', 'r14w', 'r14b'}
SWITCH_START, SWITCH_PC, CASE_BEGIN, CASE_END = 0xAB609B, 0xAB60BA, 0xAB60BC, 0xAB611A
SWITCH_SOURCE = bytes.fromhex('418b861cc20a00ffc883f8057771488d15509f54ff8b8c826476ab004803caffe1')
REMAINDER_BEGIN, REMAINDER_END = 0xAB62D6, 0xAB7664
LOGICAL_METADATA_SHA = '4a69e090cfdb1c802ee15d0b48266124039ee957f7fa7cdaa3a9963d4c59f13a'
LOGICAL_BIN_SHA = '8faac0b1a1e4095deac343d3fd88c6b7b1fe818a8174d7a0919662d81980d027'
FINGERPRINT = {'exe_sha': 'f5fee03dcfdb2e553a4752c283590950ac13316b376d8196aa556ff0400d5f06',
               'dll_sha': '2e2c3b7c2500646dadd5f2b4c6e0504dbb7e7896139f64cddc0d1813c718f51e'}


def analyze_code(root_prefix, body, suffix=None, switch_table=None, remainder=None):
    if (len(root_prefix) != 84 or len(body) != 4000
            or hashlib.sha256(root_prefix).hexdigest() != ROOT_SHA
            or body[-12:].hex() != TAIL_PIN):
        raise ValueError('R14_CFG_FIXED_CODE_PROFILE')
    closed_mode = suffix is not None
    if closed_mode and len(suffix) != 738:
        raise ValueError('R14_CFG_FIXED_SUFFIX_PROFILE')
    if remainder is not None and (not closed_mode or switch_table is None
            or len(remainder) != REMAINDER_END - REMAINDER_BEGIN):
        raise ValueError('R14_CFG_FIXED_REMAINDER_PROFILE')
    binary = root_prefix + body + (suffix or b'') + (remainder or b'')
    end = END + (len(suffix) if closed_mode else 0) + (len(remainder) if remainder is not None else 0)
    decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    decoder.detail = True
    switch_targets = None
    switch_validation = None
    if switch_table is not None:
        if not closed_mode or len(switch_table) != 24:
            raise ValueError('R14_CFG_FIXED_SWITCH_TABLE_PROFILE')
        source_at = SWITCH_START - ENTRY
        cases = list(decoder.disasm(binary[CASE_BEGIN-ENTRY:CASE_END-ENTRY], CASE_BEGIN))
        case_bytes = sum(item.size for item in cases)
        boundaries = {item.address for item in cases} | {CASE_END}
        targets = list(struct.unpack('<6I', switch_table))
        valid = (binary[source_at:source_at+len(SWITCH_SOURCE)] == SWITCH_SOURCE
            and case_bytes == CASE_END-CASE_BEGIN and all(target in boundaries for target in targets))
        switch_validation = {'table_bytes': 24, 'table_rva': 0xAB7664,
            'target_rvas': targets, 'valid_in_saved_case_instruction_boundaries': valid,
            'candidate_case_scope': [CASE_BEGIN, CASE_END], 'targets_dereferenced_from_Game': False}
        if valid:
            switch_targets = targets
    queue, seen = deque([(ENTRY, 'incoming_unknown')]), set()
    nodes, edges, issues, calls, definitions, at_call, returns = {}, set(), set(), {}, {}, set(), set()
    while queue:
        pc, state = queue.popleft()
        if (pc, state) in seen:
            continue
        seen.add((pc, state))
        if not ENTRY <= pc < end:
            issues.add(('OUTSIDE_CAPTURE_EDGE', pc))
            continue
        if pc not in nodes:
            decoded = list(decoder.disasm(binary[pc-ENTRY:pc-ENTRY+15], pc, count=1))
            if not decoded or decoded[0].address != pc or decoded[0].address + decoded[0].size > end:
                issues.add(('DECODE_INCOMPLETE', pc))
                continue
            instruction = decoded[0]
            try:
                _, writes = instruction.regs_access()
            except capstone.CsError:
                issues.add(('REGISTER_EFFECT_UNKNOWN', pc))
                continue
            nodes[pc] = {'rva': pc, 'hex': instruction.bytes.hex(), 'size': instruction.size,
                'mnemonic': instruction.mnemonic, 'operands': instruction.op_str,
                'writes_r14': bool({instruction.reg_name(reg) for reg in writes} & R14_NAMES),
                'groups': list(instruction.groups),
                'immediate_target': (instruction.operands[0].imm if instruction.operands
                    and instruction.operands[0].type == X86_OP_IMM else None)}
        node = nodes[pc]
        if pc == CALL_PC:
            if node['hex'] != CALL_HEX or node['mnemonic'] != 'call' or node['immediate_target'] != 0x13AC1F0:
                issues.add(('CONTACT_CALL_BOUNDARY_MISMATCH', pc))
            else:
                at_call.add(state)
            if not closed_mode:
                continue  # Prefix mode stops before calling; suffix mode walks its return continuation.
        if node['writes_r14']:
            if pc == ROOT_LOAD and node['hex'] == ROOT_LOAD_HEX:
                outgoing = 'global_context'
            else:
                outgoing = 'redefined_unknown'
            definitions[pc] = {'rva': pc, 'hex': node['hex'],
                'instruction': node['mnemonic'] + ' ' + node['operands'], 'output_state': outgoing}
        else:
            outgoing = state
        mnemonic, groups = node['mnemonic'], node['groups']
        next_pc = pc + node['size']
        if capstone.CS_GRP_RET in groups:
            returns.add(pc)
            continue
        if (capstone.CS_GRP_IRET in groups or capstone.CS_GRP_INT in groups
                or mnemonic in ('ud2', 'hlt', 'syscall', 'sysenter')):
            issues.add(('UNMODELED_CONTROL_TRANSFER', pc))
            continue
        jump = capstone.CS_GRP_JUMP in groups or mnemonic.startswith('loop')
        if jump:
            target = node['immediate_target']
            if pc == SWITCH_PC and target is None and switch_targets is not None:
                for selected in switch_targets:
                    edges.add((pc, selected));queue.append((selected, outgoing))
            elif pc == SWITCH_PC and switch_table is not None:
                issues.add(('SWITCH_TABLE_NOT_IN_SAVED_CASE_BOUNDARIES', pc))
            elif target is None:
                issues.add(('INDIRECT_BRANCH', pc))
            elif not ENTRY <= target < end:
                issues.add(('OUTSIDE_CAPTURE_EDGE', pc, target))
            else:
                edges.add((pc, target))
                queue.append((target, outgoing))
            if mnemonic not in ('jmp', 'ljmp'):
                edges.add((pc, next_pc));queue.append((next_pc, outgoing))
            continue
        if capstone.CS_GRP_CALL in groups:
            calls[pc] = {'rva': pc, 'hex': node['hex'], 'target': node['immediate_target'],
                         'operands': node['operands'], 'callee_followed': False}
        edges.add((pc, next_pc));queue.append((next_pc, outgoing))
    # Two reachable instruction streams must not decode overlapping bytes.
    owner = {}
    for pc, node in sorted(nodes.items()):
        for address in range(pc, pc + node['size']):
            if address in owner and owner[address] != pc:
                issues.add(('OVERLAPPING_REACHABLE_INSTRUCTIONS', owner[address], pc))
            owner[address] = pc
    if closed_mode and not returns:
        issues.add(('NO_PROVEN_NORMAL_RETURN_OR_TAIL', end))
    call_predecessors = sorted({start for start, target in edges if target == CALL_PC})
    argument_lea = nodes.get(CALL_PC - 7, {})
    projection = (call_predecessors == [CALL_PC - 7]
        and argument_lea.get('hex') == TAIL_PIN[:14])
    r14_preserved = not issues and at_call == {'global_context'}
    if issues:
        status = 'WITHHELD_CFG_INCOMPLETE'
    elif at_call != {'global_context'}:
        status = 'WITHHELD_R14_REDEFINED' if 'redefined_unknown' in at_call else 'WITHHELD_CALL_NOT_REACHED_ORIGIN_UNKNOWN'
    elif not projection:
        status = 'WITHHELD_CONTACT_ARGUMENT_LEA_NOT_DOMINATING'
    else:
        status = 'PROVED_CAPTURED_CFG_UNDER_X64_CALL_ABI'
    ready = status == 'PROVED_CAPTURED_CFG_UNDER_X64_CALL_ABI'
    return {'status': status, 'root_entry_rva': ENTRY, 'target_call_rva': CALL_PC,
        'captured_end_exclusive': end, 'closed_suffix_mode': closed_mode,
        'fixed_remainder_mode': remainder is not None,
        'switch_data_or_next_declaration_decoded': False,
        'later_three_declarations_ownership_assumed': False,
        'contact_call_fallthrough_walked': closed_mode,
        'normal_return_sites': sorted(returns), 'verified_legal_tail_transfer_sites': [],
        'normal_CFG_closed': closed_mode and not issues and bool(returns),
        'finite_switch_table': switch_validation,
        'decoder': {'name': 'capstone', 'version': capstone.__version__,
            'directory': str(DECODER_DIR), 'mode': 'x64 detail, reachable instructions only'},
        'reachable_instruction_count': len(nodes), 'reachable_edge_count': len(edges),
        'incoming_r14_states_at_call': sorted(at_call),
        'call_predecessors': call_predecessors,
        'immediate_rcx_lea_dominates_captured_call': projection,
        'r14_definitions': [definitions[k] for k in sorted(definitions)],
        'issues': [list(item) for item in sorted(issues)],
        'calls_not_followed': [calls[k] for k in sorted(calls)],
        'call_preservation_assumption': 'Ordinary Microsoft x64 call ABI: R14 is nonvolatile; callees are not decoded.',
        'exception_handler_routes_analyzed': False,
        'r14_preserved_on_captured_normal_CFG_to_call': r14_preserved,
        'contact_argument_source_proven_under_normal_x64_ABI': ready,
        'unconditional_whole_function_or_runtime_pointer_proven': False,
        'contact_argument_if_proved': 'qword[GameBase+0x3326340]+0x44F7E30' if ready else None,
        'interface_next_step': ('Static source supports a separately bounded live contact-input object read; '
            'contact/result/peer persistence and four classes remain unproved.' if ready else
            'Withhold context+0x44F7E30 input reads; resolve reported R14 definition or CFG edge first.'),
        'classification_ready': False, 'native_called': False, 'Game_accessed': False,
        'instructions': [nodes[k] for k in sorted(nodes)], 'edges': [list(edge) for edge in sorted(edges)]}


def analyze_capture(folder, suffix_folder=None, switch_folder=None, remainder_folder=None):
    folder = Path(folder)
    raw = (folder / 'callsite.bin').read_bytes()
    metadata_raw = (folder / 'callsite.json').read_bytes()
    meta = json.loads(metadata_raw)
    root = meta.get('source', {}).get('root_initialization_packet', {})
    if (not meta.get('complete')
            or meta.get('source_revision') != 'game_world_update_r14_to_contact_call_prefix_v1'
            or meta.get('fingerprint') != FINGERPRINT
            or meta.get('sha256') != hashlib.sha256(raw).hexdigest()
            or meta.get('code_bytes') != 4000
            or meta.get('ranges') != [{'name': 'world_update_current_declaration_prefix_through_contact_CALL',
                'module': 'game', 'rva': BODY_BEGIN, 'length': 4000, 'binary_offset': 0}]
            or not meta.get('code_prefix_before_after_match')
            or not meta.get('root_full_source_pin_before_after_match')
            or not meta.get('fixed_record_verified_before_after')
            or not meta.get('fresh_unwind_matches_complete_source')
            or meta.get('function_begin') != BODY_BEGIN or meta.get('function_end') != 0xAB62D6
            or root.get('binary_sha256') != ROOT_SHA or root.get('metadata_sha256') != ROOT_METADATA_SHA):
        raise ValueError('R14_CFG_CAPTURE_PROFILE')
    suffix = None
    suffix_source = None
    if suffix_folder is not None:
        suffix_folder = Path(suffix_folder)
        suffix_raw = (suffix_folder / 'callsite.bin').read_bytes()
        suffix_metadata_raw = (suffix_folder / 'callsite.json').read_bytes()
        smeta = json.loads(suffix_metadata_raw)
        prefix_source = smeta.get('source', {}).get('complete_current_prefix_packet', {})
        if (not smeta.get('complete')
                or smeta.get('source_revision') != 'game_world_update_r14_same_declaration_suffix_v1'
                or smeta.get('fingerprint') != FINGERPRINT
                or len(suffix_raw) != 738 or smeta.get('sha256') != hashlib.sha256(suffix_raw).hexdigest()
                or not smeta.get('suffix_before_after_match')
                or not smeta.get('current_full_prefix_pin_before_after_match')
                or not smeta.get('root_full_source_pin_before_after_match')
                or not smeta.get('fixed_record_verified_before_after')
                or not smeta.get('fresh_unwind_matches_complete_source')
                or smeta.get('ranges') != [{'name': 'world_update_same_declaration_suffix',
                    'module': 'game', 'rva': END, 'length': 738, 'binary_offset': 0}]
                or prefix_source.get('metadata_sha256') != hashlib.sha256(metadata_raw).hexdigest()
                or prefix_source.get('binary_sha256') != hashlib.sha256(raw).hexdigest()):
            raise ValueError('R14_CFG_SUFFIX_CAPTURE_PROFILE')
        suffix = suffix_raw
        suffix_source = {'directory': str(suffix_folder.resolve()),
            'binary_sha256': hashlib.sha256(suffix_raw).hexdigest(),
            'metadata_sha256': hashlib.sha256(suffix_metadata_raw).hexdigest()}
    switch_table = None
    switch_source = None
    if switch_folder is not None:
        if suffix_folder is None:
            raise ValueError('R14_CFG_SWITCH_REQUIRES_COMPLETE_SUFFIX')
        switch_folder = Path(switch_folder)
        table_raw = (switch_folder / 'callsite.bin').read_bytes()
        table_meta_raw = (switch_folder / 'callsite.json').read_bytes()
        tmeta = json.loads(table_meta_raw)
        previous = tmeta.get('source', {}).get('complete_suffix_packet', {})
        if (not tmeta.get('complete')
                or tmeta.get('source_revision') != 'game_world_update_finite_state_switch_table_v1'
                or tmeta.get('fingerprint') != FINGERPRINT
                or len(table_raw) != 24 or tmeta.get('sha256') != hashlib.sha256(table_raw).hexdigest()
                or not tmeta.get('table_before_after_match')
                or not tmeta.get('full_source_pins_before_after_match')
                or not tmeta.get('fixed_record_verified_before_after')
                or not tmeta.get('fresh_unwind_matches_complete_source')
                or tmeta.get('ranges') != [{'name': 'six_state_switch_DWORD_RVA_table',
                    'module': 'game', 'rva': 0xAB7664, 'length': 24, 'binary_offset': 0}]
                or previous.get('metadata_sha256') != hashlib.sha256(suffix_metadata_raw).hexdigest()
                or previous.get('binary_sha256') != hashlib.sha256(suffix_raw).hexdigest()):
            raise ValueError('R14_CFG_SWITCH_CAPTURE_PROFILE')
        switch_table = table_raw
        switch_source = {'directory': str(switch_folder.resolve()),
            'binary_sha256': hashlib.sha256(table_raw).hexdigest(),
            'metadata_sha256': hashlib.sha256(table_meta_raw).hexdigest()}
    remainder = None
    remainder_source = None
    if remainder_folder is not None:
        if switch_folder is None or suffix_folder is None:
            raise ValueError('R14_CFG_REMAINDER_REQUIRES_COMPLETE_SUFFIX_AND_SWITCH')
        remainder_folder = Path(remainder_folder)
        remainder_raw = (remainder_folder / 'callsite.bin').read_bytes()
        remainder_meta_raw = (remainder_folder / 'callsite.json').read_bytes()
        rmeta = json.loads(remainder_meta_raw)
        logical_ref = rmeta.get('source', {}).get('complete_logical_metadata_packet', {})
        switch_ref = rmeta.get('source', {}).get('complete_switch_mapping_packet', {})
        logical_dir = Path(__file__).resolve().parents[1] / 'dist/hit-world-update-logical-metadata-live-20261013-v1'
        logical_json, logical_bin = (logical_dir / 'callsite.json').read_bytes(), (logical_dir / 'callsite.bin').read_bytes()
        if (hashlib.sha256(logical_json).hexdigest() != LOGICAL_METADATA_SHA
                or hashlib.sha256(logical_bin).hexdigest() != LOGICAL_BIN_SHA):
            raise ValueError('R14_CFG_REMAINDER_LOGICAL_SOURCE_CHANGED')
        lmeta = json.loads(logical_json)
        if (not rmeta.get('complete')
                or rmeta.get('source_revision') != 'game_world_update_r14_remaining_to_switch_data_v1'
                or rmeta.get('fingerprint') != FINGERPRINT
                or len(remainder_raw) != 5006 or rmeta.get('sha256') != hashlib.sha256(remainder_raw).hexdigest()
                or not rmeta.get('remainder_before_after_match')
                or not rmeta.get('full_source_pins_before_after_match')
                or not rmeta.get('full_metadata_window_matches_frozen_source')
                or not rmeta.get('source_UW_matches_frozen_before_body')
                or not rmeta.get('fresh_gates_verified')
                or not rmeta.get('fixed_record_verified_before_after')
                or rmeta.get('ownership') != lmeta.get('ownership')
                or rmeta.get('later_three_declarations_ownership_proven') is not False
                or rmeta.get('ranges') != [{'name': 'world_update_fixed_remainder_before_switch_data',
                    'module': 'game', 'rva': REMAINDER_BEGIN, 'length': 5006, 'binary_offset': 0}]
                or logical_ref.get('metadata_sha256') != LOGICAL_METADATA_SHA
                or logical_ref.get('binary_sha256') != LOGICAL_BIN_SHA
                or switch_ref.get('metadata_sha256') != switch_source['metadata_sha256']
                or switch_ref.get('binary_sha256') != switch_source['binary_sha256']):
            raise ValueError('R14_CFG_REMAINDER_CAPTURE_PROFILE')
        remainder = remainder_raw
        remainder_source = {'directory': str(remainder_folder.resolve()),
            'binary_sha256': hashlib.sha256(remainder_raw).hexdigest(),
            'metadata_sha256': hashlib.sha256(remainder_meta_raw).hexdigest(),
            'logical_metadata_source_sha256': LOGICAL_METADATA_SHA,
            'metadata_ownership_only_for_prior_targets': [REMAINDER_BEGIN, 0xAB6A65]}
    result = analyze_code(bytes.fromhex(root['root_prefix_hex']), raw, suffix, switch_table, remainder)
    result['source'] = {'directory': str(folder.resolve()),
        'binary_sha256': hashlib.sha256(raw).hexdigest(),
        'metadata_sha256': hashlib.sha256(metadata_raw).hexdigest(),
        'root_binary_sha256': ROOT_SHA, 'root_metadata_sha256': ROOT_METADATA_SHA}
    if suffix_source is not None:
        result['source']['suffix'] = suffix_source
    if switch_source is not None:
        result['source']['switch_table'] = switch_source
    if remainder_source is not None:
        result['source']['remainder'] = remainder_source
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--suffix', type=Path)
    parser.add_argument('--switch', type=Path)
    parser.add_argument('--remainder', type=Path)
    args = parser.parse_args()
    result = analyze_capture(args.capture, args.suffix, args.switch, args.remainder)
    output_folder = args.remainder or args.switch or args.suffix or args.capture
    output = output_folder / 'r14-analysis.json'
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', 'utf8')
    asm = '\n'.join(f'{node["rva"]:08X} {node["hex"]:32} {node["mnemonic"]} {node["operands"]}'
                    for node in result['instructions'])
    (output_folder / 'r14-reachable.asm').write_text(asm + '\n', 'utf8')
    print(json.dumps({key: result[key] for key in ('status', 'reachable_instruction_count',
        'incoming_r14_states_at_call', 'r14_definitions', 'issues', 'interface_next_step')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
