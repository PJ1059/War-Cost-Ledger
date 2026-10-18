"""Inventory configured ground-fire templates and build bounded, reviewed contexts.

Offline only: python -B tools/ground-fire-contexts.py [--check]. The automatic
entries require an exact local explosion, a unique typed named parent, a cited
area duration or explicit five-second association rule, and an owned fatal fire element. A configured
FireTemplate is capability evidence, never proof of an individual fire instance.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'docs/ground-fire-contexts-0.4.66.json'
RUNTIME_DEFAULT = Path(os.environ.get('HD2_RUNTIME_SOURCE', 'external/HD2Runtime'))
BUILD = 'F5FEE03DCFDB'
COMMIT = 'dcd996daca2573443956c07252c55c2d86dd0320'
ENUM_NAMES = {1: 'Small', 2: 'Medium', 3: 'Large', 4: 'Massive'}
# Per observed event, not per template: equal templates do not prove equal fuel
# lifetime. These sources describe the ground pool, not the 3s victim status.
DURATIONS = {
    'throwable/g8_immolation/detonation': {
        'seconds': 27, 'url': 'https://helldivers.wiki.gg/wiki/G-8_Immolation',
        'basis': 'Community field report describes a 27-second ground pool; not a native lifetime field or a local live measurement.'},
    'throwable/g10_incendiary/detonation': {
        'seconds': 20, 'url': 'https://helldivers.wiki.gg/wiki/G-10_Incendiary',
        'basis': 'Community field report describes 20-second lingering ground fire after detonation; not the 3-second victim status.'},
    'throwable/g13_incendiary_impact/detonation': {
        'seconds': 15, 'url': 'https://helldivers.wiki.gg/wiki/G-13_Incendiary_Impact',
        'basis': 'Community field report describes 15-second lingering ground fire after detonation; not the 3-second victim status.'},
    'throwable/g142_pyrotech/detonation': {
        'seconds': 6, 'url': 'https://helldivers.wiki.gg/wiki/G-142_Pyrotech',
        'basis': 'Community field report distinguishes a 4-second pre-detonation spray from 6 seconds of ground fire after detonation. Only the latter begins at this event.'},
}
PENDING_REPORTS = {
    'stratagem/eagle_napalm_airstrike/payload_impact': {
        'url': 'https://helldivers.wiki.gg/wiki/Eagle_Napalm_Airstrike',
        'basis': 'Community page reports a 12-to-20-second location-dependent range with citation needed; no precise current native area lifetime is proven.'},
    'stratagem/orbital_napalm_barrage/shell_impact': {
        'url': 'https://helldivers.wiki.gg/wiki/Orbital_Napalm_Barrage',
        'basis': 'The referenced page documents residual ground fire but no exact ground-pool lifetime. Barrage firing duration is not pool lifetime.'},
    'stratagem/orbital_napalm_barrage/shell_impact_2': {
        'url': 'https://helldivers.wiki.gg/wiki/Orbital_Napalm_Barrage',
        'basis': 'Second native shell branch; no exact per-impact ground-pool lifetime is proven.'},
    'support_weapon/eat700_expendable_napalm/impact': {
        'url': 'https://helldivers.wiki.gg/wiki/EAT-700_Expendable_Napalm',
        'basis': 'The referenced page documents fire pools but no exact pool lifetime. The victim Fire/BurningHeavy durations and bomblet flight lifetime are different values.'},
    'support_weapon/eat700_expendable_napalm/impact/shrapnel_impact': {
        'url': 'https://helldivers.wiki.gg/wiki/EAT-700_Expendable_Napalm',
        'basis': 'Individual bomblet impact has its own observed position; no exact pool lifetime is proven. Do not use the carrier impact as every bomblet position.'},
    'stratagem/mdi4_incendiary_mines/mine': {
        'url': 'https://helldivers.wiki.gg/wiki/MD-I4_Incendiary_Mines',
        'basis': 'The referenced page documents post-detonation ground fire but no exact pool lifetime. Deployed mine lifetime is different.'},
    'throwable/g40k_melta_mine/detonation': {
        'url': 'https://helldivers.wiki.gg/wiki/G/40-K_Melta_Mine',
        'basis': 'Native FireTemplate1 is present; no reviewed exact ground-pool lifetime is available.'},
}
CONSERVATIVE_WINDOW = 5
CONSERVATIVE_EVENTS = set(PENDING_REPORTS)
CONSTRAINED_FAMILIES = {'stratagem/mdi4_incendiary_mines/mine': {
    'canonical_source': 'BF32E12923A9A252',
    'required_event_types': ['BF32E12923A9A252', 'E49A5AE078AAD407'],
    'basis': 'Explosion72 has a named minefield and its incendiary-mine entity as shared native consumers. An exact event may use the minefield label only when its native source_type or owner_type identifies one of these consumers; event name alone is insufficient.'}}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()


def load_module():
    spec = importlib.util.spec_from_file_location('ledger_damage_source_catalog', ROOT / 'tools/damage-source-catalog.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(runtime=None, datalibrary=None):
    runtime = Path(runtime or os.environ.get('HD2_RUNTIME_SOURCE', RUNTIME_DEFAULT)).resolve()
    damage_tool = load_module()
    folder = damage_tool.discover_datalibrary(runtime, datalibrary)
    # Re-derive the graph, including its exact build/file pins, rather than
    # trusting a manually edited source-name list in the generated document.
    damage = damage_tool.build(runtime, folder)
    sys.path.insert(0, str(runtime / 'scripts'))
    from scan.tables import EntityTables, decode
    from scan.settings import SettingsView
    tables = EntityTables(folder)
    settings = SettingsView(tables)
    source_names = json.loads((ROOT / 'docs/integration-catalogs.json').read_text(encoding='utf8'))['stat_sources']
    sdk_files = ('sdk/ExplosionCatalogue.json', 'sdk/PlayerWeaponAuthoringCapabilities.json',
                 'sdk/SupportWeaponCapabilities.json', 'sdk/VehicleWeaponCapabilities.json',
                 'schemas/stratagem_authoring_catalog.json')
    sdk = {name: json.loads((runtime / name).read_text(encoding='utf8')) for name in sdk_files}
    labels = {}

    def label(resource, name, kind, artifact):
        key = f'{int(resource, 16):016X}'
        item = {'name': name, 'kind': kind, 'artifact': artifact}
        if item not in labels.setdefault(key, []):
            labels[key].append(item)

    player = sdk['sdk/PlayerWeaponAuthoringCapabilities.json']
    for weapon in player['weapons'] + player.get('subweapons', []):
        for resource in weapon.get('resources', []):
            label(resource, weapon['name'], 'player_weapon', 'sdk/PlayerWeaponAuthoringCapabilities.json')
    for weapon in sdk['sdk/SupportWeaponCapabilities.json']['weapons'].values():
        for resource in weapon.get('resourceHashes', []):
            label(resource, weapon['catalogIdentity'], 'support_weapon', 'sdk/SupportWeaponCapabilities.json')
    from hd2_archive import resource_hash
    for vehicle in sdk['sdk/VehicleWeaponCapabilities.json']['vehicles']:
        for mount in vehicle.get('mounts', []):
            weapon = mount.get('weapon') or {}
            path = weapon.get('nativePath')
            if path:
                label(f'{resource_hash(path):016X}', weapon['key'], 'mounted_weapon',
                      'sdk/VehicleWeaponCapabilities.json')
    for name, value in sdk['schemas/stratagem_authoring_catalog.json']['stratagems'].items():
        for resource in (value.get('root') or {}).get('payloads', []):
            label(resource, name, 'stratagem_payload', 'schemas/stratagem_authoring_catalog.json')
        resource = (value.get('deployedEntity') or {}).get('resource')
        if resource:
            label(resource, name, 'stratagem_deployed_entity', 'schemas/stratagem_authoring_catalog.json')

    def resource_info(resource):
        known = source_names.get(resource)
        out = {'source_type': resource, 'sdk_names': labels.get(resource, [])}
        if known:
            out.update(name=known['name'], kind=known['kind'],
                       name_basis=known.get('basis', 'reviewed_integration_catalog'))
        path = tables.paths.get(int(resource, 16))
        if path:
            out['resource_path'] = path
        return out

    public = {row['name']: row for row in sdk['sdk/ExplosionCatalogue.json']['explosions']}
    event_names = {}
    for name, native_id in damage['explosion_names'].items():
        event_names.setdefault(native_id, []).append(name)
    catalogue, entries = [], {}
    typed_ground_sources = set()
    for kind, offset, damage_offset in [('explosion', '96', '4'), ('projectile', '236', '60')]:
        for index, native_id, raw in sorted(settings.table(kind).rows, key=lambda item: item[1]):
            row = settings.decode(kind, native_id)
            template = row[offset]
            if not template:
                continue
            source_types = sorted(resource for resource, item in damage['sources'].items()
                                  if native_id in item['types'][kind])
            typed_ground_sources.update(source_types)
            owners = sorted(resource for resource, roots in damage['resource_nodes'].items()
                            if any(root['kind'] == kind and root['id'] == native_id for root in roots))
            names = sorted(event_names.get(native_id, [])) if kind == 'explosion' else []
            canonical_names = [name for name in names if name in public]
            constrained = next((CONSTRAINED_FAMILIES[name] for name in canonical_names
                                if name in CONSTRAINED_FAMILIES), None)
            if constrained:
                assert source_types == [constrained['canonical_source']]
                assert set(owners) == set(constrained['required_event_types']), 'constrained mine family native consumers changed'
            reason = []
            if template not in ENUM_NAMES:
                reason.append('UNREVIEWED_FIRE_TEMPLATE_VALUE')
            if not canonical_names:
                reason.append('NO_EXACT_EXPLOSION_EVENT_NAME')
            if len(source_types) != 1:
                reason.append('NO_UNIQUE_NAMED_TYPED_PARENT')
            reverse = damage['reverse'][kind][str(native_id)]
            if (reverse['unresolved'] or reverse['shared']) and not constrained:
                reason.append('SHARED_OR_UNRESOLVED_NATIVE_ORIGINS')
            duration = next((DURATIONS[name] for name in canonical_names if name in DURATIONS), None)
            rule_window = any(name in CONSERVATIVE_EVENTS for name in canonical_names)
            if duration is None and not rule_window:
                reason.append('NO_REVIEWED_DURATION_OR_EXPLICIT_ASSOCIATION_RULE')
            item = {'node': f'{kind}:{native_id}', 'kind': kind, 'native_id': native_id,
                    'record_index': index, 'fire_template': template,
                    'fire_template_name': ENUM_NAMES.get(template),
                    'template_field_offset': int(offset), 'damage_info_id': row[damage_offset],
                    'event_names': names, 'sources': [resource_info(resource) for resource in source_types],
                    'direct_resource_owners': [resource_info(resource) for resource in owners],
                    'native_origin_status': {'shared': reverse['shared'], 'unresolved': reverse['unresolved']},
                    'automatic_context': not reason, 'blocked_reasons': reason}
            if constrained:
                item['source_scope'] = 'exact_event_constrained_named_family'
                item['source_constraint'] = constrained
            if canonical_names:
                item['event_identity'] = [dict(name=name, family=public[name]['family'],
                                               evidence=public[name]['evidence'], owners=public[name]['owners'])
                                          for name in canonical_names]
            if kind == 'explosion':
                item['native_radii'] = {'inner': row['16'], 'outer': row['20'], 'shockwave': row['24']}
                item['association_radius'] = row['20']
                item['persistent_status_volume'] = row['100']
            else:
                item['impact_explosion_id'], item['expiry_explosion_id'] = row['144'], row['156']
                item['position_gap'] = 'No ground-impact location is reported for this configured projectile by the explosion event unless it produces a separate observed explosion.'
            if duration:
                item['area_duration'] = dict(duration, verified_native_lifetime=False, live_tested=False)
                item['association_window'] = {'seconds': duration['seconds'],
                                              'policy': 'documented_area_duration_heuristic'}
            elif rule_window:
                item['area_duration'] = {'seconds': None, 'verified_native_lifetime': False,
                                         'basis': 'Actual ground-pool lifetime is not closed by reviewed data.'}
                item['association_window'] = {'seconds': CONSERVATIVE_WINDOW,
                    'policy': 'conservative_area_window',
                    'basis': 'Project attribution rule: use only the first5 seconds after this exact observed local detonation. This is not a claim that the ground fire lasts5 seconds.'}
            pending = [PENDING_REPORTS[name] for name in canonical_names if name in PENDING_REPORTS]
            if pending:
                item['pending_duration_reports'] = pending
            if item['automatic_context']:
                for name in canonical_names:
                    entries[name] = {'source_type': source_types[0], 'radius': row['20'],
                                     'status': 'fire', 'status_duration': item['association_window']['seconds'],
                                     'explosion_id': native_id, 'damage_info_id': row['4'],
                                     'fire_template': template,
                                     'window_policy': item['association_window']['policy']}
                    if rule_window and not duration:
                        entries[name]['conservative_area_window'] = CONSERVATIVE_WINDOW
                    if constrained:
                        entries[name]['required_event_types'] = constrained['required_event_types']
                        entries[name]['source_scope'] = 'exact_event_constrained_named_family'
            catalogue.append(item)

    components = []
    for component_name in tables.component_names():
        component = tables.component(component_name)
        for member in component.members():
            if member.type_name != 'FireTemplate':
                continue
            for record, owners in sorted(component.owner_map().items()):
                value = decode(member, component.raw(record))
                if not isinstance(value, int) or value <= 0:
                    continue
                resources = [f'{owner:016X}' for owner in sorted(owners)]
                typed_ground_sources.update(resources)
                components.append({'component': component_name, 'record_index': record,
                    'member': member.path, 'field_offset': member.offset,
                    'fire_template': value, 'fire_template_name': ENUM_NAMES.get(value),
                    'owners': [resource_info(resource) for resource in resources],
                    'automatic_context': False,
                    'blocked_reasons': ['NO_EXACT_GROUND_CREATION_EVENT_OR_POSITION', 'AREA_LIFETIME_NOT_REVIEWED'],
                    'activation_note': 'A configured template may be unused on a branch. Spray/acid/enemy defaults do not prove that a fire pool was created; no area is placed at the shooter or target merely from this field.'})
    components.sort(key=lambda item: (item['component'], item['field_offset'], item['record_index']))
    fire = json.loads((ROOT / 'docs/fire-sources.json').read_text(encoding='utf8'))
    status_only = []
    for source in fire['sources'] + fire.get('optional_excluded_by_policy', []):
        if source['type'] not in typed_ground_sources:
            status_only.append({'source_type': source['type'], 'name': source['name'],
                'automatic_context': False, 'reason': 'NATIVE_FIRE_STATUS_WITHOUT_REVIEWED_GROUND_TEMPLATE_CHAIN',
                'note': 'Igniting a victim is not proof of a ground pool. A code-created ground effect may still exist; its creation event/identity is not closed by this data inventory.'})
    status_only.sort(key=lambda item: item['source_type'])
    document = {'schema': 1, 'build': BUILD, 'runtime_commit': COMMIT,
        'policy': 'reviewed_ground_fire_area_heuristic',
        'entries': dict(sorted(entries.items())), 'catalogue': catalogue,
        'configured_component_templates': components,
        'fire_status_without_ground_template_chain': status_only,
        'template_names': {str(key): value for key, value in ENUM_NAMES.items()},
        'evidence': {
            'native': 'Pinned native ExplosionInfo +96, ProjectileInfo +236, and component members typed FireTemplate; exact explosion names and parent-source graph are re-derived from the pinned SDK and data library.',
            'area_duration_basis': 'Per-event cited community field reports are bounded heuristics, not verified native area-instance lifetimes; equal FireTemplate values do not prove equal durations.',
            'conservative_area_window': {'seconds': CONSERVATIVE_WINDOW,
                'basis': 'For uniquely named native player explosion parents with no reviewed pool lifetime, a5-second association rule limits inference. It does not replace or assert the actual fuel lifetime.'},
            'area_radius_basis': 'Each native explosion outer radius bounds association; it is not a measured ground-fire footprint. Shockwave radius is not substituted.',
            'victim_status': 'Native victim fire status3s is distinct from ground-area duration. Health extension kind/element is reliable only at owned life2, never for live HP loss.',
            'requirements': 'Exact observed local detonation, actual owned target death life2 with native kind2 element1, target position, local creditor or existing native local-kill quota. Direct known sources always win.',
            'shared_family_exception': 'MD-I4 retains shared/unresolved native origin flags. Its exact event additionally requires a native source_type or owner_type in required_event_types; these types are not installed as global weapon aliases.',
            'unverified_templates': 'The pinned Filediver enum names values1..4. Value5 is named Count there, yet2 explosion rows store it; these are inventoried but not automatically attributed.',
            'reviewed_on': '2026-10-19',
            'duration_sources': dict(sorted(DURATIONS.items())),
            'upstream': [f'https://github.com/SkyeShade/HD2Runtime/tree/{COMMIT}',
                         'https://github.com/xypwn/filediver/blob/master/datalibrary/enum/firetemplate.go']},
        'inputs': {'datalibrary': damage['inputs']['datalibrary'],
                   'runtime': {name: sha(runtime / name) for name in sdk_files},
                   'integration_catalogs_sha256': sha(ROOT / 'docs/integration-catalogs.json'),
                   'fire_sources_sha256': sha(ROOT / 'docs/fire-sources.json'),
                   'filediver_fire_enum_sha256': sha(folder / 'enum/firetemplate.go')},
        'summary': {'explosion_template_rows': sum(row['kind'] == 'explosion' for row in catalogue),
                    'projectile_template_rows': sum(row['kind'] == 'projectile' for row in catalogue),
                    'named_explosion_template_rows': sum(bool(row['event_names']) for row in catalogue),
                    'named_player_source_hashes': len({source['source_type'] for row in catalogue for source in row['sources']}),
                    'configured_component_records': len(components),
                    'configured_component_owners': len({owner['source_type'] for row in components for owner in row['owners']}),
                    'automatic_context_events': len(entries),
                    'automatic_context_sources': len({row['source_type'] for row in entries.values()}),
                    'documented_duration_events': sum(row['window_policy'] == 'documented_area_duration_heuristic' for row in entries.values()),
                    'conservative_window_events': sum(row['window_policy'] == 'conservative_area_window' for row in entries.values()),
                    'constrained_family_events': sum('required_event_types' in row for row in entries.values()),
                    'pending_catalogue_rows': sum(not row['automatic_context'] for row in catalogue),
                    'template_values': dict(sorted(Counter(str(row['fire_template']) for row in catalogue).items()))},
        'limitations': ['Configured references prove capability, not activation or a particular player kill.',
            'No live process is read and no game API is called by this generator.',
            'An unavailable/remote explosion event cannot create a local area context.',
            'Native defaults may be changed by other MODs; cited durations may vary.',
            'Spray weapons, drones, flame sentries, vehicle flamers, unowned projectiles and code-created ground effects remain inventoried gaps until a real creation/impact event and bounded lifetime are established.',
            'Enemy/environment templates and unsupported template5 are never promoted into player weapon areas.']}
    validate(document)
    return document


def validate(document):
    assert document['build'] == BUILD
    assert set(document['entries']) == set(DURATIONS) | CONSERVATIVE_EVENTS, 'only reviewed duration or explicit association-window events may be enabled'
    by_node = {row['node']: row for row in document['catalogue']}
    assert len(by_node) == len(document['catalogue'])
    for name, entry in document['entries'].items():
        row = by_node[f"explosion:{entry['explosion_id']}"]
        assert row['automatic_context'] and not row['blocked_reasons']
        assert row['fire_template'] in ENUM_NAMES and name in row['event_names']
        assert len(row['sources']) == 1 and entry['source_type'] == row['sources'][0]['source_type']
        assert entry['radius'] == row['native_radii']['outer'] > 0
        expected = DURATIONS[name]['seconds'] if name in DURATIONS else CONSERVATIVE_WINDOW
        assert entry['status_duration'] == expected and 0 < entry['status_duration'] <= 30
        if name not in DURATIONS:
            assert entry['window_policy'] == 'conservative_area_window' and entry['conservative_area_window'] == CONSERVATIVE_WINDOW
            assert row['area_duration']['seconds'] is None, 'rule window is not a proven fuel lifetime'
        if row['native_origin_status']['shared'] or row['native_origin_status']['unresolved']:
            assert name in CONSTRAINED_FAMILIES and entry['required_event_types'] == CONSTRAINED_FAMILIES[name]['required_event_types']
            assert entry['source_scope'] == 'exact_event_constrained_named_family'
    assert document['entries']['throwable/g8_immolation/detonation']['status_duration'] == 27
    assert document['entries']['throwable/g142_pyrotech/detonation']['status_duration'] == 6, 'do not count the4-second spray twice'
    for row in document['catalogue']:
        if row['kind'] == 'projectile' or row['fire_template'] not in ENUM_NAMES:
            assert not row['automatic_context']
        if row['automatic_context']:
            assert row['kind'] == 'explosion' and row['area_duration']['verified_native_lifetime'] is False
    assert all(not row['automatic_context'] for row in document['configured_component_templates'])
    assert all(not row['automatic_context'] for row in document['fire_status_without_ground_template_chain'])
    assert not any('laser' in name for name in document['entries']), 'a victim ignition is not a ground-area event'
    assert not re.search(r'(?<![A-Za-z])[A-Za-z]:[/\\]', json.dumps(document)), 'personal absolute paths are not public evidence'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', type=Path)
    parser.add_argument('--datalibrary', type=Path)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    document = build(args.runtime_root, args.datalibrary)
    body = json.dumps(document, ensure_ascii=False, indent=2) + '\n'
    if args.check:
        assert OUTPUT.read_text(encoding='utf8') == body, 'ground-fire catalogue differs from pinned inputs/reviewed policy'
    else:
        OUTPUT.write_text(body, encoding='utf8', newline='\n')
    print(json.dumps(dict(status='PASS', mode='check' if args.check else 'generate', **document['summary'])))


if __name__ == '__main__':
    main()
