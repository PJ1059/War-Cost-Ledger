"""Pure, fixed-source 19-record RF/UW relocation; no allocation or native calls.

The existing code builder preserves instruction offsets. This module copies
the actual Frame/World/contact UNWIND_INFO and only rewrites CHAININFO triples.
Handler RVAs, code slots, padding and the two GS data DWORDs stay byte-exact.
All addresses are absolute VAs expressed as nonnegative DWORD RVAs relative to
the supplied original Game base. Returned buffers are offline artifacts only.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    'fixed_hit_code_copy', Path(__file__).with_name('hit_world_contact_code_copy.py'))
code_copy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(code_copy)

SOURCE_DIRECTORY = 'hit-clone-complete-unwind-metadata-live-20261013-v1'
SOURCE_BIN_SHA = 'c0e2fa0924d2e4ad989cf8616f048558141354a3a0976cc4d283a8977a3e4361'
SOURCE_JSON_SHA = '4d472fa6cf976afb0fb7dd3c2add6b296a983571b74f6561eb8a160cb82c3bcf'
SOURCE_RANGES = (
    ('world_RF9', 0x40537B8, 108, 0),
    ('contact_RF9', 0x409AD8C, 108, 108),
    ('world_UW224', 0x24A6DE8, 224, 216),
    ('contact_UW256', 0x25114C0, 256, 440),
    ('frame_actual_RF', 0x3FF188C, 12, 696),
    ('frame_UW_node_0', 0x2404FAC, 12, 708),
)
UW_BLOCKS = {'frame': (0x2404FAC, 12, 708, 0),
             'world': (0x24A6DE8, 224, 216, 12),
             'contact': (0x25114C0, 256, 440, 236)}
UW_BYTES = 492
RF_COUNT = 19
RF_BYTES = RF_COUNT * 12
GS_HANDLER_RVA = 0x21044A0
GS_COOKIES = {'world': 0x6D0, 'contact': 0x25C0}


class UnwindRejected(ValueError):
    pass


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load_sources(source_root=ROOT):
    """Read only the named immutable metadata packet; derive records from BIN."""
    parent = Path(source_root) / 'dist' / SOURCE_DIRECTORY
    raw = (parent / 'callsite.bin').read_bytes()
    encoded = (parent / 'callsite.json').read_bytes()
    if sha(raw) != SOURCE_BIN_SHA or sha(encoded) != SOURCE_JSON_SHA:
        raise UnwindRejected('SOURCE_SHA_MISMATCH:unwind')
    meta = json.loads(encoded)
    ranges = tuple((r['name'], r['rva'], r['length'], r['binary_offset'])
                   for r in meta['ranges'])
    gates = ('complete', 'fresh_gates_verified', 'standard_layouts_complete',
             'fixed_RF_before_after_match', 'fixed_UW_before_after_match',
             'contact_known_full_chain_and_25C0_match',
             'all_four_code_pins_before_after_match',
             'frame_captured_UW_bytes_before_after_match',
             'frame_full_standard_UW_ancestry_captured')
    if (len(raw) != 720 or ranges != SOURCE_RANGES
            or meta.get('sha256') != SOURCE_BIN_SHA
            or any(meta.get(g) is not True for g in gates)
            or meta.get('unknown_handler_formats') != []):
        raise UnwindRejected('SOURCE_PACKET_CONTRACT')
    families = {f['name']: f for f in meta['families']}
    if set(families) != {'world', 'contact'}:
        raise UnwindRejected('SOURCE_FAMILY_CONTRACT')
    records, nodes = {}, {}
    for name, rf_offset, count in (('frame', 696, 1), ('world', 0, 9), ('contact', 108, 9)):
        items = [struct.unpack_from('<III', raw, rf_offset + i * 12) for i in range(count)]
        json_records = ([meta['frame']['selected_record']] if name == 'frame'
                        else meta[name + '_RF_records'])
        if items != [(r['begin'], r['end'], r['unwind_rva']) for r in json_records]:
            raise UnwindRejected('SOURCE_RF_FIELDS:' + name)
        begin, size, _ = code_copy.REGIONS[name]
        if (items[0][0] != begin or items[-1][1] != begin + size
                or any(a[1] != b[0] for a, b in zip(items, items[1:]))):
            raise UnwindRejected('SOURCE_RF_COVERAGE:' + name)
        source_nodes = (meta['frame']['unwind_nodes'] if name == 'frame'
                        else families[name]['nodes'])
        if name != 'frame' and any(families[name][k] for k in
                                  ('unknown_layouts', 'unknown_handler_formats', 'unresolved_chain_targets')):
            raise UnwindRejected('SOURCE_UW_UNRESOLVED:' + name)
        block_rva, block_size, source_offset, _ = UW_BLOCKS[name]
        nodes[name] = []
        for n in source_nodes:
            at = n['unwind_rva'] - block_rva
            saved = bytes.fromhex(n['raw_hex'])
            if not 0 <= at < block_size or at + len(saved) > block_size:
                raise UnwindRejected('SOURCE_UW_BLOCK_BOUND:' + name)
            if raw[source_offset + at:source_offset + at + len(saved)] != saved:
                raise UnwindRejected('SOURCE_UW_BYTES:' + name)
            if len(saved) < 4 or saved[0] & 7 != 1 or saved[0] >> 3 not in (0, 3, 4):
                raise UnwindRejected('SOURCE_UW_FORMAT:' + name)
            tail = 4 + ((saved[2] + 1) & ~1) * 2
            flags = saved[0] >> 3
            standard = tail + (12 if flags == 4 else 4 if flags == 3 else 0)
            expected_length = standard + (4 if flags == 3 else 0)
            if len(saved) != expected_length or saved[3] != 0:
                raise UnwindRejected('SOURCE_UW_LAYOUT:' + name)
            node = {'rva': n['unwind_rva'], 'offset': at, 'raw': saved,
                    'tail_offset': tail, 'flags': flags, 'region': name}
            if flags == 4:
                node['chain'] = struct.unpack_from('<III', saved, tail)
                if node['chain'] not in items:
                    raise UnwindRejected('SOURCE_CHAIN_NOT_FAMILY_RF:' + name)
            elif flags == 3:
                handler, cookie = struct.unpack_from('<II', saved, tail)
                if (name not in GS_COOKIES or handler != GS_HANDLER_RVA
                        or cookie != GS_COOKIES[name] or cookie & 4):
                    raise UnwindRejected('SOURCE_GS_CONTRACT:' + name)
            nodes[name].append(node)
        by_uw = {n['rva']: n for n in nodes[name]}
        if len(by_uw) != count or set(by_uw) != {r[2] for r in items}:
            raise UnwindRejected('SOURCE_UW_RF_PAIRING:' + name)
        for record in items:
            seen, current = set(), record
            while by_uw[current[2]]['flags'] == 4:
                if current in seen:
                    raise UnwindRejected('SOURCE_CHAIN_CYCLE:' + name)
                seen.add(current)
                current = by_uw[current[2]]['chain']
            if current != items[0]:
                raise UnwindRejected('SOURCE_CHAIN_PRIMARY:' + name)
        records[name] = items
    return {'raw': raw, 'metadata': meta, 'records': records, 'nodes': nodes,
            'evidence': {'directory': str(parent.resolve()), 'binary_sha256': SOURCE_BIN_SHA,
                         'metadata_sha256': SOURCE_JSON_SHA}}


def _span(address, size, base, label, alignment=1):
    if (type(address) is not int or not 0 <= address <= code_copy.UINT64_MAX
            or address + size > code_copy.UINT64_MAX or address % alignment):
        raise UnwindRejected('ADDRESS_OR_ALIGNMENT:' + label)
    if not 0 <= address - base <= code_copy.UINT32_MAX or not 0 <= address + size - base <= code_copy.UINT32_MAX:
        raise UnwindRejected('RVA32_OUT_OF_RANGE:' + label)
    return address, address + size, label


def build(old_game_base, code_layout, unwind_address, table_address, source_root=ROOT):
    """Return code/UW/RF buffers and their absolute placements; execute nothing.

    code_layout has absolute frame/world/contact destinations. unwind_address
    reserves 492 bytes and table_address reserves 228 bytes; both are aligned4.
    RFs are sorted by new BeginAddress even if code_layout has another ordering.
    """
    code_copy._layout(old_game_base, code_layout)
    spans = [_span(code_layout[n], v[1], old_game_base, 'code:' + n)
             for n, v in code_copy.REGIONS.items()]
    spans += [_span(unwind_address, UW_BYTES, old_game_base, 'unwind', 4),
              _span(table_address, RF_BYTES, old_game_base, 'runtime_table', 4)]
    ordered = sorted(spans)
    if any(a[1] > b[0] for a, b in zip(ordered, ordered[1:])):
        raise UnwindRejected('LAYOUT_OVERLAP')
    source = load_sources(source_root)
    code = code_copy.build(old_game_base, code_layout, source_root)
    uw = bytearray(UW_BYTES)
    for name, (_, size, source_offset, destination_offset) in UW_BLOCKS.items():
        uw[destination_offset:destination_offset + size] = source['raw'][source_offset:source_offset + size]

    def map_code(name, rva):
        old_begin, size, _ = code_copy.REGIONS[name]
        if not old_begin <= rva <= old_begin + size:
            raise UnwindRejected('RF_CODE_BOUND:' + name)
        return code_layout[name] - old_game_base + rva - old_begin

    def map_uw(name, rva):
        old_begin, size, _, new_offset = UW_BLOCKS[name]
        if not old_begin <= rva < old_begin + size:
            raise UnwindRejected('UW_REGION_BOUND:' + name)
        return unwind_address - old_game_base + new_offset + rva - old_begin

    mapped_rf, node_manifest, rewrites = [], [], []
    for name in code_copy.REGIONS:
        _, _, _, block_offset = UW_BLOCKS[name]
        for old_record in source['records'][name]:
            new_record = (map_code(name, old_record[0]), map_code(name, old_record[1]),
                          map_uw(name, old_record[2]))
            mapped_rf.append({'region': name, 'old': old_record, 'new': new_record})
        for node in source['nodes'][name]:
            at = block_offset + node['offset']
            if node['flags'] == 4:
                old_chain = node['chain']
                new_chain = (map_code(name, old_chain[0]), map_code(name, old_chain[1]),
                             map_uw(name, old_chain[2]))
                struct.pack_into('<III', uw, at + node['tail_offset'], *new_chain)
                rewrites.append({'region': name, 'old_unwind_rva': node['rva'],
                                 'new_unwind_rva': map_uw(name, node['rva']),
                                 'blob_offset': at + node['tail_offset'],
                                 'old_chain': old_chain, 'new_chain': new_chain})
            changed = bytes(uw[at:at + len(node['raw'])])
            if changed[:node['tail_offset']] != node['raw'][:node['tail_offset']]:
                raise UnwindRejected('HEADER_OR_SLOTS_CHANGED')
            if node['flags'] != 4 and changed != node['raw']:
                raise UnwindRejected('HANDLER_OR_GS_BYTES_CHANGED')
            node_manifest.append({'region': name, 'old_unwind_rva': node['rva'],
                                  'new_unwind_rva': map_uw(name, node['rva']),
                                  'blob_offset': at, 'length': len(changed), 'flags': node['flags'],
                                  'source_hex': node['raw'].hex(), 'copy_hex': changed.hex()})
    mapped_rf.sort(key=lambda r: r['new'][0])
    if (len(mapped_rf) != RF_COUNT or len(rewrites) != 16
            or any(a['new'][1] > b['new'][0] for a, b in zip(mapped_rf, mapped_rf[1:]))):
        raise UnwindRejected('RELOCATED_RF_TABLE_CONTRACT')
    table = b''.join(struct.pack('<III', *r['new']) for r in mapped_rf)
    manifest = {'profile': 'fixed_frame_world_contact_RF_UW_relocation_v1',
                'old_game_base': old_game_base, 'code_layout': dict(code_layout),
                'unwind_address': unwind_address, 'runtime_table_address': table_address,
                'runtime_function_count': RF_COUNT, 'runtime_table_bytes': RF_BYTES,
                'unwind_bytes': UW_BYTES, 'runtime_records': mapped_rf, 'unwind_nodes': node_manifest,
                'chain_rewrites': rewrites, 'source': source['evidence'],
                'unwind_sha256': sha(uw), 'runtime_table_sha256': sha(table),
                'instruction_offsets_preserved': True, 'headers_slots_GS_data_preserved': True,
                'handler_rvas_preserved': True, 'RF_sorted_nonoverlapping': True,
                'native_registered': False, 'native_called': False, 'Game_accessed': False,
                'new_RX_executed': False, 'owned_unwind_parity_proven': False,
                'Game_or_exception_safety_proven': False, 'classification_ready': False}
    return {'code': code, 'unwind_blob': bytes(uw), 'runtime_table_blob': table, 'manifest': manifest}


def export_build(result, output):
    output = Path(output)
    code_copy.export_build(result['code'], output)
    (output / 'unwind.bin').write_bytes(result['unwind_blob'])
    (output / 'runtime-function-table.bin').write_bytes(result['runtime_table_blob'])
    (output / 'unwind-relocation.json').write_text(json.dumps(result['manifest'], indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('old-game-base', 'frame', 'world', 'contact', 'unwind', 'table'):
        parser.add_argument('--' + name, type=lambda s: int(s, 0), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = build(args.old_game_base, {n: getattr(args, n) for n in code_copy.REGIONS},
                   args.unwind, args.table)
    export_build(result, args.output)
    print(json.dumps({'RF_count': RF_COUNT, 'UW_bytes': UW_BYTES,
                      'chain_rewrites': len(result['manifest']['chain_rewrites']),
                      'native_called': False, 'output': str(args.output)}))


if __name__ == '__main__':
    main()
