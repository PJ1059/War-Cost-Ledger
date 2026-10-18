"""Review exact falling hellpod bodies from the pinned native component table.

Offline only. A translated label or a HellpodRack/HellpodPayload component is
not enough: the source must own the falling HellpodComponent and Transport.
This names an observed source; it does not invent ownership or damage events.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
BUILD = 'F5FEE03DCFDB'
RUNTIME_DEFAULT = Path(os.environ.get('HD2_RUNTIME_SOURCE', 'external/HD2Runtime'))
BASE = 'content/fac_helldivers/hellpod/hellpod/'
REVIEWED = {
    'E58163E71928D3E2': ('hellpod_initial_spawn', 'InitialSpawn', 2),
    'EF9EB729A9D6D849': ('hellpod_reinforce', 'Reinforce', 1),
    '73F8498BFFDCF415': ('hellpod_payload', 'Payload', 0),
}
LABELS = {'InitialSpawn': '绝地空投仓（初始投放）', 'Reinforce': '绝地空投仓（增援）', 'Payload': '装备空投仓'}
EXCLUDED = {
    '583ECDE0D7718126': 'generic hellpod base: no reviewed gameplay delivery role',
    '736EDD2093900042': 'extraction-beacon hellpod: not reviewed as a player attack source',
    '3E9409D42D895300': 'deactivated launcher: no falling HellpodComponent',
    '685337C9CCF0E45C': 'launcher: no falling HellpodComponent',
    '788864E7623B9FDB': 'ship delivery system: no falling HellpodComponent',
    'B52BEAAE4F85C391': 'sealed rack: payload/rack only, not the falling outer body',
    '5052EC6A928CCF1A': 'supply rack: payload/rack only, not the falling outer body',
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()


def reviewed_component(tables, resource, expected_variant):
    """Validate actual component ownership; never infer it from the name."""
    pod = tables.component('HellpodComponentData')
    transport = tables.component('TransportComponentData')
    record = pod.record_of(int(resource, 16))
    transport_record = transport.record_of(int(resource, 16))
    if record is None or transport_record is None:
        raise ValueError('source has no falling HellpodComponent and Transport: ' + resource)
    from scan.tables import decode
    members = {member.path: member for member in pod.members()}
    if members['0'].type_name != 'HellpodVariant':
        raise ValueError('hellpod variant is not the reviewed typed enum')
    raw = pod.raw(record)
    variant = decode(members['0'], raw)
    height, velocity = decode(members['8'], raw), decode(members['20'], raw)
    if variant != expected_variant:
        raise ValueError('hellpod gameplay variant differs: ' + resource)
    if height <= 0 or velocity <= 0:
        raise ValueError('hellpod has no positive descent configuration: ' + resource)
    return dict(hellpod_component_record=record, transport_component_record=transport_record,
                hellpod_variant=variant, spawn_height=height, initial_velocity=velocity)


def build_sources(runtime=None, datalibrary=None):
    runtime = Path(runtime or os.environ.get('HD2_RUNTIME_SOURCE', RUNTIME_DEFAULT)).resolve()
    profile_path = runtime/'schemas/build_profile.json'
    profile = json.loads(profile_path.read_text(encoding='utf8'))['builds'][BUILD]['datalibrary']
    if datalibrary is None:
        candidates = [runtime/profile['path'], Path(os.environ.get('HD2_DAMAGE_DATALIBRARY', 'external/datalibrary'))]
        datalibrary = next((path for path in candidates if (path/'generated_entities.dl_bin').is_file()), candidates[-1])
    folder = Path(datalibrary).resolve()
    inputs = {name: sha(folder/name) for name in ('generated_entities.dl_bin', 'dl_library.dl_typelib')}
    if inputs['generated_entities.dl_bin'] != profile['entitiesSha256'].upper() or inputs['dl_library.dl_typelib'] != profile['typelibSha256'].upper():
        raise ValueError('datalibrary fingerprints differ from the pinned game build')
    # Filediver's enum names explain the independently typed native values.
    enum_path = folder/'enum/hellpodvariant.go'
    enum_text = enum_path.read_text(encoding='utf8')
    names = re.findall(r'^\s*HellpodVariant_(\w+)(?:\s+HellpodVariant\s*=\s*iota)?\s*$', enum_text, re.M)
    if names != ['Payload', 'Reinforce', 'InitialSpawn']:
        raise ValueError('HellpodVariant declaration differs from the reviewed enum')
    sys.path.insert(0, str(runtime/'scripts'))
    from hd2_archive import resource_hash
    from scan.tables import EntityTables
    tables = EntityTables(folder)
    sources = {}
    for resource, (suffix, variant_name, variant) in REVIEWED.items():
        path = BASE+suffix
        if f'{resource_hash(path):016X}' != resource:
            raise ValueError('hellpod resource path does not match the full 64-bit identity')
        component = reviewed_component(tables, resource, variant)
        sources[resource] = dict(name='Hellpod ('+variant_name+')', name_zh=LABELS[variant_name],
            kind='hellpod', resource_path=path, variant_name=variant_name,
            basis='exact_resource_path_and_native_falling_hellpod_transport_components',
            **component)
    return dict(schema=1, reviewed_on='2026-10-18', build=BUILD,
        policy='label_exact_observed_falling_hellpod_source_only',
        source_count=len(sources), sources=dict(sorted(sources.items())),
        source_identity_required=True, counts_as_vehicle_crush=False,
        weapon_traits_inferred=False, native_collision_mechanism_proven=False,
        note='73F8498BFFDCF415 is the moving payload outer body, despite the community label Empty Hellpod; equipment racks remain excluded.',
        excluded=dict(sorted(EXCLUDED.items())),
        evidence={'datalibrary':inputs, 'runtime_build_profile_sha256':sha(profile_path),
                  'filediver_hellpodvariant_sha256':sha(enum_path),
                  'filediver_hellpod_component_sha256':sha(folder/'hellpod_component.go')})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', type=Path)
    parser.add_argument('--datalibrary', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT/'docs/hellpod-kill-sources.json')
    args = parser.parse_args()
    data = build_sources(args.runtime_root, args.datalibrary)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    print(json.dumps(dict(source_count=data['source_count'], output=str(args.output.resolve()))))
