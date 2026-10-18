"""Pure six-region same-offset code relocation, without observers or native APIs.

Reuse the immutable three-region decoder/relocator in a private module instance.
Add actual AP843, dispatcher244 (213 code + NOP3 + seven DWORD table), and
physical1552 source bytes. Only displacement/table fields change; no allocation,
Game access, code execution, registration, Lua or installed MOD changes.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[2]
FROZEN = Path(__file__).with_name('hit_world_contact_code_copy.py')
FROZEN_SHA = '33b32df82d43e00e5d79eec1119b79497e36eaf288932e61294b779b751bac57'
if hashlib.sha256(FROZEN.read_bytes()).hexdigest() != FROZEN_SHA:
    raise ValueError('SIX_REGION_FROZEN_CODE_MAPPER_CHANGED')
_spec = importlib.util.spec_from_file_location('_six_region_private_code_copy', FROZEN)
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)
CopyRejected, capstone = base.CopyRejected, base.capstone
UINT32_MAX, UINT64_MAX = base.UINT32_MAX, base.UINT64_MAX
sha, _rva = base.sha, base._rva
_old_load_sources = base.load_sources

REGIONS = {**base.REGIONS, 'ap': (0x129C9F0, 843, 843),
           'dispatcher': (0x129DC30, 244, 216),
           'physical': (0x13B0BD0, 1552, 1552)}
REGION_SHA = {**base.REGION_SHA,
    'ap': 'c4cd5aeee139cffadf9c4e8e83a3b024a92ffff5ac20025f5b4f346b7a5e3662',
    'dispatcher': 'ea974e4317dd42dd7cf76c02ab409d66c4b49a6ecb2923b1f02ac740ff3cabe8',
    'physical': 'd1f99ab9a04dd4a2cc852bbd9e2e94f1dff54c392ecf832859d1e22beeb541d0'}
DISPATCH_TABLE_RVA = 0x129DD08
DISPATCH_TARGETS = (0x129DC6A, 0x129DC6A, 0x129DC74, 0x129DC7E,
                    0x129DC88, 0x129DC9C, 0x129DC92)
PACKET_DIRECTORY = 'hit-ap-physical-clone-metadata-live-20261013-v1'
PACKET_BIN_SHA = 'c552a232fc96317db47d13e2762f5980138cc18088b9675a7c7ad53c4e6b48ce'
PACKET_JSON_SHA = '4ddefb21a6aac7d94904f66eb84bd61031e0681d34c9df54733956f9eafb20eb'
PACKET_RANGES = (('dispatcher_fixed244', 0x129DC30, 244, 0),
    ('physical_RF7', 0x409AE64, 84, 244), ('physical_UW180', 0x2511668, 180, 328),
    ('dispatcher_actual_RF', 0x408E150, 12, 508),
    ('dispatcher_UW_node_0', 0x24FC4AC, 12, 520))
EXTRA_SOURCES = {
    'A': ('dist/hit-code-capture/hit-classification-code-20261011T103354Z-6ac80883',
          'c062eb498383dd15c9e4c22bdc2668eda732db8e737cf8bee11b7f97076408e4',
          'ed6c6705e7aeb7eec8d1bcde4cd6ce85c56e4d6c6cf99bb0d48de640dca9cb80', 14976),
    'B': ('dist/hit-owner-prefix-20261012/drain',
          '1776ae47d88e6f4dfa95d4b077709e5693f810e72284bbf05be74b08316a4b8a',
          'ed79e3550b29f021aa5757154ff70b2260288441cf133d4b3a2ac08888de24f6', 4396)}


def load_sources(source_root=ROOT):
    if source_root == ROOT and os.environ.get('HD2_RESEARCH_FIXTURES_ROOT'):
        source_root = Path(os.environ['HD2_RESEARCH_FIXTURES_ROOT']).resolve().parent
    regions, evidence = _old_load_sources(source_root)
    saved = {}
    for name, (stem, bin_sha, json_sha, size) in EXTRA_SOURCES.items():
        path = Path(source_root) / stem
        raw = path.with_suffix('.bin').read_bytes()
        encoded = path.with_suffix('.json').read_bytes()
        if sha(raw) != bin_sha or sha(encoded) != json_sha:
            raise CopyRejected('SOURCE_SHA_MISMATCH:' + name)
        meta = json.loads(encoded)
        if (len(raw) != size or meta.get('complete') is not True
                or meta.get('sha256', meta.get('binary_sha256')) != bin_sha):
            raise CopyRejected('SOURCE_PACKET_CONTRACT:' + name)
        saved[name] = raw
        evidence.append({'name': name, 'directory': path.parent.resolve().relative_to(Path(source_root).resolve()).as_posix(),
                         'binary_sha256': bin_sha, 'metadata_sha256': json_sha})
    path = Path(source_root) / 'dist' / PACKET_DIRECTORY
    raw, encoded = (path / 'callsite.bin').read_bytes(), (path / 'callsite.json').read_bytes()
    if sha(raw) != PACKET_BIN_SHA or sha(encoded) != PACKET_JSON_SHA:
        raise CopyRejected('SOURCE_SHA_MISMATCH:AP_physical_actual_metadata')
    meta = json.loads(encoded)
    ranges = tuple((r['name'], r['rva'], r['length'], r['binary_offset']) for r in meta['ranges'])
    gates = ('complete', 'fresh_gates_verified', 'standard_layouts_complete',
             'dispatcher_fixed244_before_after_match', 'dispatcher_known224_before_after_match',
             'dispatcher_selected_RF_and_full_UW_before_after_match',
             'physical_RF_UW_windows_before_after_match',
             'all_known_AP_physical_contact_pins_before_after_match',
             'AP_existing_complete_UW48_only_verified')
    if (len(raw) != 532 or ranges != PACKET_RANGES or meta.get('sha256') != PACKET_BIN_SHA
            or any(meta.get(g) is not True for g in gates)
            or meta['dispatcher']['unknown_layouts'] or meta['physical']['unknown_layouts']
            or struct.unpack_from('<III', raw, 508) != (0x129DC30, 0x129DD24, 0x24FC4AC)):
        raise CopyRejected('SOURCE_PACKET_CONTRACT:AP_physical_actual_metadata')
    A, B = saved['A'], saved['B']
    regions.update(ap=A[560:1403], dispatcher=raw[:244],
                   physical=B[4364:4396] + A[13440:14960])
    if regions['dispatcher'][:224] != A[5232:5456]:
        raise CopyRejected('SOURCE_DISPATCHER_OLD_PREFIX_MISMATCH')
    if (regions['dispatcher'][213:216].hex() != '0f1f00'
            or struct.unpack_from('<7I', regions['dispatcher'], 216) != DISPATCH_TARGETS):
        raise CopyRejected('SOURCE_DISPATCHER_NOP_OR_SWITCH_MISMATCH')
    for name, blob in regions.items():
        if len(blob) != REGIONS[name][1] or sha(blob) != REGION_SHA[name]:
            raise CopyRejected('SOURCE_REGION_MISMATCH:' + name)
    evidence.append({'name': 'AP_physical_actual_metadata', 'directory': path.resolve().relative_to(Path(source_root).resolve()).as_posix(),
                     'binary_sha256': PACKET_BIN_SHA, 'metadata_sha256': PACKET_JSON_SHA,
                     'saved_PIDs_are_not_current_identity': True})
    return regions, evidence


# The old file and other importing modules remain immutable. Its generic branch
# and RIP relocation loop operates on these six regions only in this instance.
base.REGIONS, base.REGION_SHA, base.load_sources = REGIONS, REGION_SHA, load_sources
_layout = base._layout


def build(old_game_base, layout, source_root=ROOT):
    result = base.build(old_game_base, layout, source_root)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    source, _ = load_sources(source_root)
    source_pc = old_game_base + 0x129DC5E
    instruction = next((i for i in md.disasm(source['dispatcher'][:216],
                                           old_game_base + REGIONS['dispatcher'][0])
                        if i.address == source_pc), None)
    if instruction is None or instruction.bytes.hex() != '8b8c8208dd2901' or instruction.disp_size != 4:
        raise CopyRejected('FIXED_DISPATCHER_TABLE_INSTRUCTION')
    raw = bytearray(result['blobs']['dispatcher'])
    table_target = layout['dispatcher'] + 216
    table_rva = _rva(table_target, old_game_base, 'dispatcher_switch_table')
    if table_rva > 0x7FFFFFFF:
        raise CopyRejected('DISPATCHER_TABLE_DISP32_OVERFLOW')
    offset = source_pc - old_game_base - REGIONS['dispatcher'][0]
    at = offset + instruction.disp_offset
    before = bytes(raw[at:at + 4])
    struct.pack_into('<i', raw, at, table_rva)
    relocations = result['manifest']['relocations']
    relocations.append({'region': 'dispatcher', 'kind': 'switch_table_disp32',
        'old_pc': source_pc, 'new_pc': layout['dispatcher'] + offset,
        'instruction_size': instruction.size, 'field_offset': instruction.disp_offset,
        'width': 4, 'old_target': old_game_base + DISPATCH_TABLE_RVA,
        'new_target': table_target, 'destination_region': 'dispatcher',
        'before_hex': before.hex(), 'after_hex': bytes(raw[at:at + 4]).hex()})
    boundaries = {i.address for i in md.disasm(source['dispatcher'][:216],
                                             old_game_base + REGIONS['dispatcher'][0])}
    for index, target in enumerate(DISPATCH_TARGETS):
        if old_game_base + target not in boundaries:
            raise CopyRejected('DISPATCHER_CASE_NOT_INSTRUCTION')
        new_target = layout['dispatcher'] + target - REGIONS['dispatcher'][0]
        new_rva = _rva(new_target, old_game_base, 'dispatcher_switch_case')
        struct.pack_into('<I', raw, 216 + index * 4, new_rva)
        relocations.append({'region': 'dispatcher', 'kind': 'switch_rva32',
            'index': index, 'offset': 216 + index * 4, 'width': 4,
            'old_target': old_game_base + target, 'new_target': new_target,
            'old_rva': target, 'new_rva': new_rva})
    result['blobs']['dispatcher'] = bytes(raw)
    required = {(old_game_base + 0x13AD7C8, layout['dispatcher']),
                (old_game_base + 0x129DC6D, layout['ap']),
                (old_game_base + 0x13AD751, layout['physical'])}
    actual = {(r['old_pc'], r['new_target']) for r in relocations if r['kind'] == 'relative_branch'}
    if not required <= actual:
        raise CopyRejected('AP_DISPATCHER_PHYSICAL_CALL_CHAIN_NOT_REWIRED')
    record = next(r for r in result['manifest']['regions'] if r['name'] == 'dispatcher')
    record.update(copy_sha256=sha(raw), body_code_length=213, alignment_NOP_bytes=3,
                  switch_table_bytes=28)
    record['displacement_counts']['switch_table_disp32'] += 1
    flat = b''.join(result['blobs'][name] for name in REGIONS)
    result['manifest'].update(profile='fixed_six_region_same_semantics_code_copy_v1',
        dispatcher_switch_targets=list(DISPATCH_TARGETS),
        dispatcher_switch_table_rva=DISPATCH_TABLE_RVA,
        dispatcher_switch_table_new_rva=table_rva,
        AP_dispatcher_physical_call_chain_rewired=True, observers_inserted=False,
        source_PIDs_used_as_current_identity=False, classification_ready=False,
        blob_bytes=len(flat), blob_sha256=sha(flat))
    return result


def export_build(result, output):
    base.export_build(result, output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--old-game-base', type=lambda s: int(s, 0), required=True)
    for name in REGIONS:
        parser.add_argument('--' + name, type=lambda s: int(s, 0), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = build(args.old_game_base, {name: getattr(args, name) for name in REGIONS})
    export_build(result, args.output)
    print(json.dumps({'code_only': True, 'blob_bytes': result['manifest']['blob_bytes'],
                      'relocations': len(result['manifest']['relocations']),
                      'output': str(args.output)}))


if __name__ == '__main__':
    main()
