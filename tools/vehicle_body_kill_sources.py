"""Reviewed player-vehicle parent sources for the user's body-kill rule.

The rule deliberately counts a confirmed vehicle-parent stat source as crush;
it does not claim to recover a native collision mechanism. No game access.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re

from resource_hash_labels import runtime_entity_rows

ROOT = Path(__file__).resolve().parents[1]
REVIEWED = {
    'M-103 Supply FRV': '9B2140378640432E',
    'TD-110 Maelstrom': 'B0C9FAF4AF8903F9',
    'M-104 Incinerator FRV': '2D85BFE3D8717FE5',
    'EXO-49 Emancipator Exosuit': 'C2D449ECF7FACAB1',
    'EXO-45 Patriot Exosuit': '79E4B3D2DA5E45E3',
    'M-102 Gunner FRV': 'CC21C7FFD3EBEFB9',
    'TD-220 Bastion MK XVI': '16474112801385B6',
    'EXO-55 Breakthrough Exosuit': '35DBF54F016F3624',
    'EXO-51 Lumberer Exosuit': '7B2326F6FD9C8069',
}
EXCLUDED_WORLD_VEHICLES = {
    'E9CD1D0D118886AF': 'FRV (Super Earth variant)',
    '423FF97D57AB04F5': 'GATER Oil Rig',
}


def build_sources(sdk: Path, *, labels=None):
    sdk = Path(sdk)
    paths = [sdk/'VehicleAuthoringCapabilities.json', sdk/'VehicleWeaponCapabilities.json',
             sdk.parent/'domains/vehicle_weapon_authoring.lua', sdk.parent/'domains/event_entities.lua']
    vehicle, weapon = [json.loads(p.read_text(encoding='utf8')) for p in paths[:2]]
    by_name = {row['name']: row for row in vehicle['vehicles']}
    armed_names = {row['vehicle'] for row in weapon['vehicles']}
    native = runtime_entity_rows(paths[3].read_text(encoding='utf8'))
    # Match the actual mount chain's resource; semanticId suffixes are hashes
    # of the API identity and must never stand in for an entity resource.
    chain_text = paths[2].read_text(encoding='utf8')
    chains = re.findall(r'\["mountChain"\]=\{\["mountPath"\]="0x([0-9A-F]{16})",'
                        r'\["slot"\]=[0-9]+,\["vehicle"\]="([^"]+)",'
                        r'\["vehicleResource"\]="0x([0-9A-F]{16})"\}', chain_text)
    sources = {}
    for name, resource in REVIEWED.items():
        assert name in by_name and name in armed_names, 'Reviewed vehicle missing from SDK: ' + name
        row = by_name[name]
        assert row.get('callInStratagem', {}).get('known') is True, 'Player call-in provenance not established'
        info = native.get(resource, {})
        assert info.get('faction') == 'helldivers' and info.get('kill') is False, 'Not a reviewed friendly vehicle'
        mounts = [(mount, parent) for mount, parent_name, parent in chains if parent_name == name]
        assert mounts and {parent for _, parent in mounts} == {resource}, 'Native vehicle parent differs'
        weapon_hashes = sorted({mount for mount, _ in mounts})
        assert resource not in weapon_hashes
        label = (labels or {}).get(resource, {})
        sources[resource] = dict(name=name, name_zh=label.get('name_zh') or name,
            vehicle_class=row.get('vehicleClass') or 'world_vehicle', kind='vehicle_body',
            basis='sdk_authoring_vehicle_and_exact_native_mountChain_parent',
            native_entity_id=info.get('id'), native_faction=info['faction'],
            known_player_call_in=row.get('callInStratagem', {}).get('known') is True,
            mounted_weapon_hashes=weapon_hashes,
            native_collision_mechanism_proven=False)
    body_hashes = set(sources)
    mounted = {value for row in sources.values() for value in row['mounted_weapon_hashes']}
    assert not body_hashes.intersection(mounted)
    return dict(schema=1, reviewed_on='2026-10-15',
        runtime_commit='dcd996daca2573443956c07252c55c2d86dd0320',
        policy='confirmed_player_vehicle_parent_source_kills_as_crush',
        rule='Count local-player source-stat KILLS growth under an exact reviewed parent body resource as crush.',
        source_count=len(sources), sources=dict(sorted(sources.items())),
        excludes=['mounted_weapon_resource', 'projectile_resource', 'enemy_vehicle', 'backpack_drone',
                  'label_only_or_unknown_type', 'unattributed_source_gap'],
        rule_does_not_claim_native_collision_mechanism=True,
        backfill_missing_source_identity=False,
        excluded_world_vehicles={value:dict(name=name,reason='No SDK player call-in definition; applicability deferred.')
                                 for value,name in EXCLUDED_WORLD_VEHICLES.items()},
        evidence=[dict(path=str(p.relative_to(sdk.parent)).replace('\\','/'),
                       sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, default=Path(os.environ.get('HD2_RUNTIME_SDK',
        str(Path(os.environ['LOCALAPPDATA'])/'Temp/hd2-integration-research/HD2Runtime/SkyeShade-HD2Runtime-dcd996d/sdk'))))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    labels = json.loads((ROOT/'docs/resource-hash-aliases.json').read_text(encoding='utf8'))['aliases']
    result = build_sources(args.sdk, labels=labels)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    print(json.dumps(dict(source_count=result['source_count'], output=str(args.output.resolve()))))
