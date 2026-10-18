"""Extend the frozen living-target producer with two tank mounts and their carrier.

Pure file transformation. No process access, native call, game instruction edit,
ownership fallback, or new observer site. The original profile remains immutable.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'docs/native-hit-living-target-profile-v1.json'
BASE_SHA = '076a538a9a6f5e157174921f8ae6bb279f7396e5d477decfc6a31a98dacbd8d4'
SOURCES = {
    '16474112801385B6': 'TD-220 Bastion MK XVI',
    '1FA1F596769225C2': 'TD-220 Bastion MK XVI / attach_tank_gun',
    '439F9E65C18567DA': 'TD-220 Bastion MK XVI / attach_tank_gun_mg',
}


def package():
    raw = BASE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != BASE_SHA:
        raise ValueError('Frozen living-target profile changed')
    profile = copy.deepcopy(json.loads(raw))
    old = profile['data_tables']['source_types']
    assert len(old) == 91 and not set(old).intersection(SOURCES)
    values = sorted(set(old).union(SOURCES))
    entry = next(e for e in profile['entries'] if e['name'] == 'qualifier_types')
    # The original MOV R8D immediate follows exactly the source table literal.
    reloc = next(r for r in entry['relocations'] if r['address_key'] == 'source_types')
    offset = reloc['offset'] + reloc['width']
    code = bytearray.fromhex(entry['code_hex'])
    assert code[offset:offset + 6] == b'\x41\xb8' + struct.pack('<I', len(old))
    code[offset + 2:offset + 6] = struct.pack('<I', len(values))
    entry['code_hex'] = code.hex()
    profile['data_tables']['source_types'] = values
    profile['qualification_limits']['source_types'] = len(values)
    profile['catalog_evidence']['base_source_count'] = len(old)
    profile['catalog_evidence']['source_count'] = len(values)
    profile['count_contract']['enemy_and_personal_source_required'] = False
    profile['count_contract']['enemy_and_reviewed_projectile_source_required'] = True
    profile['reflection_qualification']['source_personal_catalogue'] = False
    profile['reflection_qualification']['source_reviewed_projectile_catalogue'] = True
    profile['diagnostic_qualification'] = 'full_peer_and_fresh_enemy_reviewed_projectile'
    profile['vehicle_source_extension'] = dict(
        revision=1, base_profile_sha256=BASE_SHA,
        sources=SOURCES, source_count_before=len(old), source_count_after=len(values),
        ownership='exact_hit_creditor_matches_current_local_peer_only',
        ordinary_native_hit_classification_unchanged=True,
        vehicle_owner_or_driver_not_used=True,
        direct_projectiles_only=True, explosion_splash_not_added=True,
        carrier_source_alias='16474112801385B6',
        carrier_contact_source_observed_in_game=False,
        actual_gameplay_verified=False)
    return profile


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    output = parser.parse_args().output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(package(), indent=2) + '\n', encoding='utf8')
    print(output.resolve())
