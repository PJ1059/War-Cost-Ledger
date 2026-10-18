"""Derive a concrete DamageInfo capture from the immutable vehicle producer.

Only private copy gateways change. ABI 1 remains 96 bytes: optional flag 512
names the formerly unused generation word at +36 as a concrete DamageInfo ID.
Unknown source contacts with an audited ID may pass as attribution-only (1024),
with no hit-count award. All original peer, living-target and branch gates stay.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import hit_copy_pending_observer as P
import hit_copy_reflection_observer as R

BASE = ROOT / 'docs/native-hit-vehicle-source-profile-v1.json'
BASE_SHA = 'e091b550ee1ffcacd308d9256270fa1cfc698a7afd5925b86a3794a6202d9bb1'
NATIVE_PINS = [
    dict(rva=0x13AC3BC, hex='4869c2c8000000', meaning='projectile hit slot stride 0xC8'),
    dict(rva=0x13AC3D0, hex='4c03f0', meaning='R14 is the current projectile hit pool record'),
    dict(rva=0x13AD29B, hex='418b460c', meaning='current direct DamageInfoType is hit record +0x0C'),
]


def contact_begin():
    c = P.RelocCode()
    P.old.prolog(c)
    c.address('48 b9', 'arena'); P.hi_arg(c, 'contact_begin')
    c.emit('4c 8d 84 24 40 01 00 00'); c.call('begin')
    c.emit('48 85 c0'); c.branch('0f 84', 'restore')
    # R14 is nonvolatile and unchanged by the gateway/arena. Its same pool
    # record was already read by the caller at 13AD29B before this site.
    c.emit('41 8b 56 0c 89 50 24 81 48 58 00 02 00 00')
    P.restore(c, 'contact_begin')
    e = P.entry('contact_begin', c, P.old.GATE_UNWIND)
    e.update(executable_length=len(bytes.fromhex(e['code_hex'])) - 8,
             frame_allocation=P.old.FRAME_BYTES, frame_register='RBP',
             original_parent_unwind_unchanged=True, captures_direct_damage_info=True)
    return e


def reflection():
    # Regenerate the frozen reflection body with only its fresh-proof reset
    # retaining the current begin's ID validity. Internal branch/reloc offsets
    # are recomputed by the original assembler, never byte-spliced.
    original = P.RelocCode
    class ExtendedCode(original):
        replaced = False
        def emit(self, value):
            old = 'c7 47 58 03 00 00 00 c7 47 38 00 00 00 00'
            if value == old:
                value = '81 67 58 00 02 00 00 83 4f 58 03 c7 47 38 00 00 00 00'
                self.replaced = True
            return super().emit(value)
    P.RelocCode = ExtendedCode
    try:
        result = R.reflection_gateway()
    finally:
        P.RelocCode = original
    result['retains_current_contact_damage_info_only'] = True
    return result


def qualifier(count):
    c = P.RelocCode()
    c.emit('56 57 48 83 ec 28 48 89 d6 81 66 58 ff fb ff ff')
    c.call('qualifier_prior')
    c.emit('a9 00 01 00 00'); c.branch('0f 85', 'return')
    c.emit('8b 46 58 25 43 02 00 00 3d 43 02 00 00'); c.branch('0f 85', 'return')
    c.emit('83 7e 54 01'); c.branch('0f 85', 'return')
    c.address('48 b9', 'damage_info_types'); c.emit('8b 56 24 41 b8 ' + struct.pack('<I', count).hex(' '))
    c.call('allow'); c.emit('85 c0'); c.branch('0f 84', 'return')
    c.emit('81 4e 58 00 05 00 00')
    c.label('return'); c.emit('8b 46 58 48 83 c4 28 5f 5e c3')
    return P.entry('qualifier', c, bytes.fromhex('010603000642027001600000'))


def package(ids):
    raw = BASE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != BASE_SHA:
        raise ValueError('DAMAGE_ID_FROZEN_VEHICLE_PROFILE_CHANGED')
    ids = sorted(set(ids))
    if not ids or len(ids) > 1024 or any(type(i) is not int or not 0 < i < 4096 for i in ids):
        raise ValueError('AUDITED_DAMAGE_INFO_IDS_REQUIRED')
    source, _ = P.copies.load_sources()
    for pin in NATIVE_PINS:
        at = pin['rva'] - P.copies.REGIONS['contact'][0]
        if source['contact'][at:at + len(bytes.fromhex(pin['hex']))].hex() != pin['hex']:
            raise ValueError('DAMAGE_INFO_NATIVE_PIN:' + hex(pin['rva']))
    profile = copy.deepcopy(json.loads(raw))
    for e in profile['entries']:
        if e['name'] == 'qualifier':
            e['name'] = 'qualifier_prior'
    profile['entries'] = [contact_begin() if e['name'] == 'contact_begin' else
                          reflection() if e['name'] == 'reflection_writeback' else e
                          for e in profile['entries']]
    profile['entries'].append(qualifier(len(ids)))
    profile['data_tables']['damage_info_types'] = [f'{i:016X}' for i in ids]
    profile['damage_id_extension'] = dict(
        revision=1, base_profile_sha256=BASE_SHA, record_offset=36, capture_flag=512,
        attribution_only_flag=1024, damage_table='DamageInfoType', concrete_hit_offset=12,
        concrete_hit_stride=200, native_pins=NATIVE_PINS, damage_info_count=len(ids),
        unknown_source_requires_audited_damage_info=True, legacy_stride_unchanged=True,
        legacy_generation_producer_was_zero=True, historical_profiles_unchanged=True,
        attribution_only_hit_count=0, no_native_parent_weapon_guess=True,
        actual_gameplay_verified=False)
    return profile


def audited_ids(catalog):
    return sorted(int(key) for key, row in catalog['reverse']['damage_info'].items()
                  if row.get('candidates'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--damage-info-ids', help='Comma separated audited positive DamageInfoType IDs')
    inputs.add_argument('--catalog', type=Path, help='Reviewed typed damage-source catalog')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    ids = audited_ids(json.loads(args.catalog.read_text(encoding='utf8'))) if args.catalog else [int(i) for i in args.damage_info_ids.split(',')]
    output.write_text(json.dumps(package(ids), indent=2) + '\n', encoding='utf8')
    print(output.resolve())
