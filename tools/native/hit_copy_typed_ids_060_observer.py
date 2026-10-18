"""Add proved same-contact ProjectileType capture to the existing private gateways.

ABI1 stays96B. Flag2048 makes +32 a ProjectileType; absent that flag it keeps
its legacy meaning. DamageInfo remains +36/flag512. No new hook sites or native
hit qualification are introduced; all source/life/local-credit rules stay.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import hit_copy_damage_id_054_observer as D
import hit_copy_pending_observer as P
import hit_copy_reflection_observer as R

PROJECTILE_FLAG = 2048
PINS = [
    {'rva': 0x13AC22E, 'hex': '4c8bf9', 'meaning': 'R15 is the native ProjectileSystem'},
    {'rva': 0x13AC357, 'hex': '428b843b44700e00', 'meaning': 'current slot comes from a u32 queued contact'},
    {'rva': 0x13AC36F, 'hex': '488945a8', 'meaning': 'slot is saved at parent RBP-0x58'},
    {'rva': 0x13AD7CD, 'hex': '488b7da8', 'meaning': 'RDI only later becomes the current slot'},
    {'rva': 0x13AD834, 'hex': '418b84bf40500e00', 'meaning': 'same-contact native ProjectileType array read'},
]


def contact_begin():
    c = P.RelocCode()
    P.old.prolog(c)
    c.address('48 b9', 'arena'); P.hi_arg(c, 'contact_begin')
    c.emit('4c 8d 84 24 40 01 00 00'); c.call('begin')
    c.emit('48 85 c0'); c.branch('0f 84', 'restore')
    c.emit('41 8b 56 0c 89 50 24 81 48 58 00 02 00 00')
    # The returned arena row remains RAX. Reject only optional projectile
    # metadata: any failure keeps the already-captured DamageInfo and hit path.
    c.emit('81 60 58 ff f7 ff ff c7 40 20 00 00 00 00')
    c.emit('4c 8b 94 24 30 01 00 00 4c 8d 9c 24 40 02 00 00 4d 3b d3')
    c.branch('0f 85', 'typed_done')
    c.emit('4d 8b 5a a8 4c 89 d9 48 c1 e9 20 48 85 c9')
    c.branch('0f 85', 'typed_done')
    c.emit('41 81 fb 00 08 00 00'); c.branch('0f 83', 'typed_done')
    c.emit('4d 85 ff'); c.branch('0f 84', 'typed_done')
    c.emit('49 69 cb c8 00 00 00 49 03 cf 48 81 c1 40 d0 04 00 4c 3b f1')
    c.branch('0f 85', 'typed_done')
    c.emit('43 8b 8c 9f 40 50 0e 00 85 c9'); c.branch('0f 84', 'typed_done')
    c.emit('81 f9 5f 01 00 00'); c.branch('0f 83', 'typed_done')
    c.emit('89 48 20 81 48 58 00 08 00 00')
    c.label('typed_done')
    P.restore(c, 'contact_begin')
    entry = P.entry('contact_begin', c, P.old.GATE_UNWIND)
    entry.update(executable_length=len(bytes.fromhex(entry['code_hex'])) - 8,
                 frame_allocation=P.old.FRAME_BYTES, frame_register='RBP',
                 original_parent_unwind_unchanged=True, captures_direct_damage_info=True,
                 captures_current_projectile_type=True)
    return entry


def reflection():
    original = P.RelocCode
    class TypedCode(original):
        def __init__(self):
            super().__init__()
            self.replacements = set()
        def emit(self, value):
            if value == 'c7 47 58 03 00 00 00 c7 47 38 00 00 00 00':
                value = '81 67 58 00 0a 00 00 83 4f 58 03 c7 47 38 00 00 00 00'
                self.replacements.add('validity')
            if value == '4c 89 57 18 8b 84 24 e8 00 00 00 89 47 20':
                super().emit('4c 89 57 18 f7 47 58 00 08 00 00')
                self.branch('0f 85', 'typed_slot_kept')
                super().emit('8b 84 24 e8 00 00 00 89 47 20')
                self.label('typed_slot_kept')
                self.replacements.add('legacy_slot')
                return
            return super().emit(value)
        def finish(self):
            if self.replacements != {'validity', 'legacy_slot'}:
                raise ValueError('TYPED_REFLECTION_FIXED_SHAPE_CHANGED')
            return super().finish()
    P.RelocCode = TypedCode
    try:
        result = R.reflection_gateway()
    finally:
        P.RelocCode = original
    result.update(retains_current_contact_damage_info_only=True,
                  retains_current_contact_projectile_type_only=True)
    return result


def package(ids, catalog=None):
    source, _ = P.copies.load_sources()
    for pin in PINS:
        at = pin['rva'] - P.copies.REGIONS['contact'][0]
        if source['contact'][at:at + len(bytes.fromhex(pin['hex']))].hex() != pin['hex']:
            raise ValueError('PROJECTILE_TYPE_NATIVE_PIN:' + hex(pin['rva']))
    if source['contact'][:25].hex() != '40554157488dac2478daffffb888260000e8ba83d500482be0':
        raise ValueError('PROJECTILE_TYPE_CONTACT_FRAME_SOURCE')
    if catalog is not None and {int(i) for i in catalog['reverse']['projectile']} != set(range(1,351)):
        raise ValueError('PROJECTILE_TYPE_TABLE_IS_NOT_FIXED_1_TO_350')
    profile = D.package(ids)
    profile['entries'] = [contact_begin() if e['name']=='contact_begin' else
                          reflection() if e['name']=='reflection_writeback' else e
                          for e in profile['entries']]
    profile['projectile_id_extension'] = dict(
        revision=1, record_offset=32, capture_flag=PROJECTILE_FLAG,
        native_table='ProjectileType', native_type_min=1, native_type_bound=351,
        system_register='R15', system_type_array_offset=0xE5040,
        original_parent_rbp_save_offset=0x130, expected_parent_rbp_from_savebase=0x240,
        slot_from_parent_rbp=-0x58, slot_high32_zero=True, slot_bound=2048,
        matching_hit_register='R14', matching_hit_base=0x4D040, matching_hit_stride=0xC8,
        frozen_at='contact_begin', never_uses_begin_rdi=True,
        zero_or_invalid_type_omits_flag=True, failed_metadata_keeps_damage_info=True,
        reflection_preserves_typed_value=True, legacy_slot_requires_absent_flag=True,
        legacy_stride_unchanged=True, new_hook_sites=0, qualifier_unchanged=True,
        native_pins=PINS, actual_gameplay_verified=False)
    return profile


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    catalog=json.loads(args.catalog.read_text(encoding='utf8'))
    profile=package(D.audited_ids(catalog),catalog)
    args.output.write_text(json.dumps(profile,indent=2)+'\n',encoding='utf8')
    print(args.output.resolve())
