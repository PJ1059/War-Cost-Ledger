"""Offline, fixed-source frame/World/contact code copies; no native execution.

Only displacement fields and the saved six-entry switch table are rewritten.
Function sizes and instruction offsets stay fixed. This module supplies no
RUNTIME_FUNCTION/UNWIND_INFO and performs no allocation, registration or slot write.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys

DECODER_DIR = Path('external/hd2-fire-analysis-deps')
sys.path.insert(0, str(DECODER_DIR))
import capstone
from capstone.x86 import X86_OP_MEM, X86_REG_RIP, X86_REG_EIP

ROOT = Path(__file__).resolve().parents[2]
UINT32_MAX = 0xFFFFFFFF
UINT64_MAX = 0xFFFFFFFFFFFFFFFF
REGIONS = {'frame': (0x4EE6C0, 67, 67),
           'world': (0xAB5000, 9852, 9828),
           'contact': (0x13AC1F0, 17266, 17266)}
REGION_SHA = {
    'frame': '3da812c76a7c4cd5ade12e2a5567ec97b70e74bbea74114de50686a13afee9d7',
    'world': '96db8e734d30cc117d5a4cfa01b25caf03ee02e2d32249cc5a73cc745bac28c7',
    'contact': '4ab318e231a62b61db540c7e8b3d7fa7159d97839edbf9c1a7fa34b963daaafb',
}
# name, folder, stem, BIN SHA, JSON SHA, exact saved ranges (RVA, length, offset)
PACKETS = (
    ('frame', 'hit-game-plugin-table-update-live-20261013-v1', 'plugin-table-update',
     '03b3fd1cd3459fb3c3d6eb71e47a806dd2376ccd7f36dbc1f60f606bd446f546',
     '2386a698c1385069a8d4328f86b1f2fb11813580883a43ad8424790006878494',
     ((0x37CEB10, 200, 0), (0x4EE6C0, 80, 200))),
    ('root', 'hit-world-update-root-prefix-live-20261013-v1', 'callsite',
     '279bbfda6d08a0386022bbc5c7af02ab56f2ff14d15d3074d728d1abb120be89',
     'f990919cf354a446f74728942c2236c840f68169e90a6034c3fb13786981f9a3',
     ((0xAB5000, 44, 0), (0xAB502C, 27, 44), (0xAB5047, 13, 71))),
    ('prefix', 'hit-world-update-r14-prefix-live-20261013-v1', 'callsite',
     '81c9895e3b79ee97a3a393480f2feb69b00117da988fdcad760c158930503510',
     '95322aa15bc813672c98e507db0cbde27302892e23a08a36713187ac6d3f52fe',
     ((0xAB5054, 4000, 0),)),
    ('suffix', 'hit-world-update-r14-suffix-live-20261013-v1', 'callsite',
     '3310fe6d1739836b6bd1a0ee9b28d3511e4d8ef5f8017334b63282a401db6f84',
     '47c7d3f431e5344e1f102bfd34119368081aec3932330e0c7a42c91dd4da5852',
     ((0xAB5FF4, 738, 0),)),
    ('remainder', 'hit-world-update-r14-remainder-live-20261013-v1', 'callsite',
     'ad362eee2ebcd08df4a557490d8b6049d9a5e84ab436e3e2e60a473d67a42b16',
     'd104f8b137f5644da6a774fcc7d3283958926da6077a8f16c9b9b36aea44e83b',
     ((0xAB62D6, 5006, 0),)),
    ('table', 'hit-world-update-switch-table-live-20261013-v1', 'callsite',
     '112a1fab7a620ab94143358f3ff3b505ec7b5a88694308d0a8da60b1ef0a290e',
     'aa0a746902e8c244599d15e00627d13470418e97be4b2f9ac5fa88fbc5fe2838',
     ((0xAB7664, 24, 0),)),
    ('contact', 'hit-contact-whole-envelope-live-20261013-v1', 'callsite',
     '4ab318e231a62b61db540c7e8b3d7fa7159d97839edbf9c1a7fa34b963daaafb',
     '6539a0d848537754a029fa5bb10be580c220d13f4d0ad25dff7f8c778a8c3d7f',
     ((0x13AC1F0, 17266, 0),)),
)
SWITCH_RVA = 0xAB7664
SWITCH_TARGETS = (0xAB60BC, 0xAB60CD, 0xAB60DE, 0xAB60EF, 0xAB6100, 0xAB610E)


class CopyRejected(ValueError):
    pass


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load_sources(source_root=ROOT):
    if source_root == ROOT and os.environ.get('HD2_RESEARCH_FIXTURES_ROOT'):
        source_root = Path(os.environ['HD2_RESEARCH_FIXTURES_ROOT']).resolve().parent
    """Read only the seven named, byte-exact saved packets."""
    parts, evidence = {}, []
    for name, folder, stem, bin_sha, json_sha, expected_ranges in PACKETS:
        parent = Path(source_root) / 'dist' / folder
        raw = (parent / (stem + '.bin')).read_bytes()
        metadata = (parent / (stem + '.json')).read_bytes()
        if sha(raw) != bin_sha or sha(metadata) != json_sha:
            raise CopyRejected('SOURCE_SHA_MISMATCH:' + name)
        meta = json.loads(metadata)
        ranges = tuple((r['rva'], r['length'], r['binary_offset']) for r in meta['ranges'])
        if meta.get('complete') is not True or meta.get('sha256') != bin_sha or ranges != expected_ranges:
            raise CopyRejected('SOURCE_PACKET_CONTRACT:' + name)
        parts[name] = raw
        evidence.append({'name': name, 'directory': parent.resolve().relative_to(Path(source_root).resolve()).as_posix(),
                         'binary_sha256': bin_sha, 'metadata_sha256': json_sha})
    regions = {'frame': parts['frame'][200:267],
               'world': b''.join(parts[n] for n in ('root', 'prefix', 'suffix', 'remainder', 'table')),
               'contact': parts['contact']}
    for name, raw in regions.items():
        if len(raw) != REGIONS[name][1] or sha(raw) != REGION_SHA[name]:
            raise CopyRejected('SOURCE_REGION_MISMATCH:' + name)
    if struct.unpack('<6I', parts['table']) != SWITCH_TARGETS:
        raise CopyRejected('SOURCE_SWITCH_MISMATCH')
    return regions, evidence


def _rva(address, base, purpose):
    value = address - base
    if not 0 <= value <= UINT32_MAX:
        raise CopyRejected('RVA32_OUT_OF_RANGE:' + purpose)
    return value


def _layout(old_game_base, layout):
    if type(old_game_base) is not int or not 0 <= old_game_base <= UINT64_MAX:
        raise CopyRejected('OLD_GAME_BASE')
    if not isinstance(layout, dict) or set(layout) != set(REGIONS):
        raise CopyRejected('FIXED_LAYOUT_KEYS')
    spans = []
    for name, (rva, size, _) in REGIONS.items():
        at = layout[name]
        if type(at) is not int or not 0 <= at <= UINT64_MAX or at + size > UINT64_MAX:
            raise CopyRejected('LAYOUT_ADDRESS:' + name)
        _rva(at, old_game_base, name + ':begin')
        _rva(at + size, old_game_base, name + ':end')
        if old_game_base + rva + size > UINT64_MAX:
            raise CopyRejected('OLD_REGION_ADDRESS:' + name)
        spans.append((at, at + size, name))
    spans.sort()
    if any(a[1] > c[0] for a, c in zip(spans, spans[1:])):
        raise CopyRejected('LAYOUT_OVERLAP')


def build(old_game_base, layout, source_root=ROOT):
    """Return {blobs, manifest} for absolute destination VAs; execute nothing."""
    _layout(old_game_base, layout)
    source, evidence = load_sources(source_root)
    decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    decoder.detail = True
    instructions, boundaries = {}, set()
    for name, (rva, _, code_size) in REGIONS.items():
        old_begin = old_game_base + rva
        items = list(decoder.disasm(source[name][:code_size], old_begin))
        if not items or sum(i.size for i in items) != code_size:
            raise CopyRejected('SOURCE_DECODE_INCOMPLETE:' + name)
        instructions[name] = items
        boundaries.update(i.address for i in items)

    def mapped(target):
        _rva(target, old_game_base, 'source_target')
        for name, (rva, size, _) in REGIONS.items():
            offset = target - (old_game_base + rva)
            if 0 <= offset < size:
                result = layout[name] + offset
                _rva(result, old_game_base, 'mapped_target')
                return result, name
        return target, None

    blobs, relocations, region_records = {}, [], []
    flat_offset = 0
    for name, (rva, size, code_size) in REGIONS.items():
        raw = bytearray(source[name])
        old_begin = old_game_base + rva
        region_count = {'relative_branch': 0, 'rip_relative': 0, 'switch_table_disp32': 0}
        for insn in instructions[name]:
            offset = insn.address - old_begin
            new_pc = layout[name] + offset
            fields = []
            if insn.group(capstone.CS_GRP_BRANCH_RELATIVE):
                fields.append(('relative_branch', insn.imm_offset, insn.imm_size))
            memory = [o for o in insn.operands if o.type == X86_OP_MEM]
            if any(o.mem.base == X86_REG_EIP for o in memory):
                raise CopyRejected('EIP_RELATIVE_UNSUPPORTED:' + hex(insn.address))
            if any(o.mem.base == X86_REG_RIP for o in memory):
                fields.append(('rip_relative', insn.disp_offset, insn.disp_size))
            for kind, field_offset, width in fields:
                if width not in (1, 4) or field_offset <= 0 or field_offset + width > insn.size:
                    raise CopyRejected('DISPLACEMENT_ENCODING:' + hex(insn.address))
                at = offset + field_offset
                before = bytes(raw[at:at + width])
                displacement = int.from_bytes(before, 'little', signed=True)
                old_target = insn.address + insn.size + displacement
                new_target, destination_region = mapped(old_target)
                if kind == 'relative_branch' and destination_region and old_target not in boundaries:
                    raise CopyRejected('INTERNAL_BRANCH_NOT_INSTRUCTION:' + hex(insn.address))
                replacement = new_target - (new_pc + insn.size)
                if not -(1 << (width * 8 - 1)) <= replacement < (1 << (width * 8 - 1)):
                    label = 'REL' if kind == 'relative_branch' else 'RIP_DISP'
                    raise CopyRejected(f'{label}{width * 8}_OVERFLOW:{insn.address:#x}')
                after = replacement.to_bytes(width, 'little', signed=True)
                raw[at:at + width] = after
                relocations.append({'region': name, 'kind': kind, 'old_pc': insn.address,
                                    'new_pc': new_pc, 'instruction_size': insn.size,
                                    'field_offset': field_offset, 'width': width,
                                    'old_target': old_target, 'new_target': new_target,
                                    'destination_region': destination_region,
                                    'before_hex': before.hex(), 'after_hex': after.hex()})
                region_count[kind] += 1
            # The fixed switch loads DWORD RVAs through the original Game base,
            # not RIP: mov ecx,[rdx+rax*4+AB7664]. Move that table reference too.
            if name == 'world' and insn.address == old_game_base + 0xAB60B0:
                if insn.bytes.hex() != '8b8c826476ab00' or insn.disp_size != 4:
                    raise CopyRejected('FIXED_SWITCH_TABLE_INSTRUCTION')
                table_target = layout['world'] + SWITCH_RVA - REGIONS['world'][0]
                table_rva = _rva(table_target, old_game_base, 'switch_table')
                if table_rva > 0x7FFFFFFF:
                    raise CopyRejected('SWITCH_TABLE_DISP32_OVERFLOW')
                at = offset + insn.disp_offset
                before = bytes(raw[at:at + 4])
                struct.pack_into('<i', raw, at, table_rva)
                relocations.append({'region': name, 'kind': 'switch_table_disp32',
                                    'old_pc': insn.address, 'new_pc': new_pc,
                                    'instruction_size': insn.size, 'field_offset': insn.disp_offset,
                                    'width': 4, 'old_target': old_game_base + SWITCH_RVA,
                                    'new_target': table_target, 'destination_region': 'world',
                                    'before_hex': before.hex(), 'after_hex': bytes(raw[at:at + 4]).hex()})
                region_count['switch_table_disp32'] += 1
        if name == 'world':
            table_offset = SWITCH_RVA - rva
            for index, target_rva in enumerate(SWITCH_TARGETS):
                old_target = old_game_base + target_rva
                new_target, destination_region = mapped(old_target)
                if destination_region != 'world' or old_target not in boundaries:
                    raise CopyRejected('SWITCH_CASE_NOT_INSTRUCTION')
                value = _rva(new_target, old_game_base, 'switch_case')
                struct.pack_into('<I', raw, table_offset + index * 4, value)
                relocations.append({'region': name, 'kind': 'switch_rva32', 'index': index,
                                    'offset': table_offset + index * 4, 'width': 4,
                                    'old_target': old_target, 'new_target': new_target,
                                    'old_rva': target_rva, 'new_rva': value})
        blobs[name] = bytes(raw)
        region_records.append({'name': name, 'source_rva': rva, 'old_begin': old_begin,
                               'new_begin': layout[name], 'new_rva': layout[name] - old_game_base,
                               'length': size, 'code_length': code_size, 'blob_offset': flat_offset,
                               'instruction_count': len(instructions[name]),
                               'source_sha256': REGION_SHA[name], 'copy_sha256': sha(raw),
                               'displacement_counts': region_count})
        flat_offset += size

    required = {(old_game_base + 0x4EE6E9, layout['world']),
                (old_game_base + 0xAB5FEF, layout['contact'])}
    actual = {(r['old_pc'], r['new_target']) for r in relocations if r['kind'] == 'relative_branch'}
    if not required <= actual:
        raise CopyRejected('FIXED_CALL_CHAIN_NOT_REWIRED')
    flat = b''.join(blobs[name] for name in REGIONS)
    manifest = {'profile': 'fixed_frame_world_contact_code_copy_v1', 'code_only': True,
                'game_accessed': False, 'new_RX_executed': False, 'native_registered': False,
                'UW_supplied': False, 'instruction_offsets_preserved': True,
                'Game_or_exception_safety_proven': False, 'old_game_base': old_game_base,
                'decoder_version': capstone.__version__, 'sources': evidence,
                'regions': region_records, 'relocations': relocations,
                'switch_table_rva': SWITCH_RVA,
                'switch_table_new_rva': layout['world'] - old_game_base + SWITCH_RVA - REGIONS['world'][0],
                'external_targets_preserved': True, 'blob_bytes': len(flat), 'blob_sha256': sha(flat)}
    return {'blobs': blobs, 'manifest': manifest}


def export_build(result, output):
    """Write only the offline artifact; blob offsets do not imply VA adjacency."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    flat = b''.join(result['blobs'][name] for name in REGIONS)
    (output / 'code.bin').write_bytes(flat)
    (output / 'relocation-manifest.json').write_text(
        json.dumps(result['manifest'], indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--old-game-base', type=lambda s: int(s, 0), required=True)
    for name in REGIONS:
        parser.add_argument('--' + name, type=lambda s: int(s, 0), required=True,
                            help='absolute destination VA (offline only)')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = build(args.old_game_base, {name: getattr(args, name) for name in REGIONS})
    export_build(result, args.output)
    print(json.dumps({'code_only': True, 'blob_bytes': result['manifest']['blob_bytes'],
                      'relocations': len(result['manifest']['relocations']),
                      'output': str(args.output)}))


if __name__ == '__main__':
    main()
