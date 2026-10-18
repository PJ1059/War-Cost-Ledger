"""Derive AP and fire/gas source traits from the pinned SDK, without a game read."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = Path(os.environ.get('HD2_RUNTIME_SOURCE', 'external/HD2Runtime'))
INPUTS = ('sdk/PlayerWeaponAuthoringCapabilities.json', 'sdk/SupportWeaponCapabilities.json',
          'sdk/StatusEffectCatalog.json', 'schemas/stratagem_authoring_catalog.json')


def build(runtime=DEFAULT):
    runtime = Path(runtime)
    docs = {name: json.loads((runtime / name).read_text(encoding='utf-8')) for name in INPUTS}
    integration = json.loads((ROOT / 'docs/integration-catalogs.json').read_text(encoding='utf-8'))
    fire = json.loads((ROOT / 'docs/fire-sources.json').read_text(encoding='utf-8'))
    traits, evidence = {}, {}

    def key(value):
        return f'{int(value, 16):016X}'

    def add(resource, name, ap=None, **flags):
        resource = key(resource)
        row = traits.setdefault(resource, {'name': name})
        if ap is not None:
            row['armor_penetration_max'] = max(row.get('armor_penetration_max', 0), ap)
        for name, value in flags.items():
            if value:
                row[name] = True

    players = docs[INPUTS[0]]['weapons']
    for weapon in players:
        values = [field['currentDefault'] for field in weapon['fields']
                  if any(field['semanticFieldId'].endswith('damage.' + suffix) for suffix in ('ap_direct', 'ap_slight', 'ap_large', 'ap_extreme'))
                  and isinstance(field.get('currentDefault'), int)]
        if not values:
            continue
        for resource in weapon['resources']:
            add(resource, weapon['name'], max(values))
            evidence[key(resource)] = {'artifact': INPUTS[0], 'weapon': weapon['name'], 'ap_values': values,
                                       'basis': 'max_all_native_primary_and_explosion_damage_ap_fields'}
    support = list(docs[INPUTS[1]]['weapons'].values())
    for weapon in support:
        for resource in weapon['resourceHashes']:
            attacks = [attack for attack in weapon.get('runtimeAttacks', [])
                       if key(attack['resourceHash']) == key(resource) and 'ap_direct' in attack.get('resolvedFields', {})]
            values = [attack['resolvedFields']['ap_direct'] for attack in attacks]
            if values:
                add(resource, weapon['catalogIdentity'], max(values))
                evidence[key(resource)] = {'artifact': INPUTS[1], 'weapon': weapon['catalogIdentity'],
                    'attacks': [{'role': attack['role'], 'kind': attack['kind'],
                                 'ap_direct': attack['resolvedFields']['ap_direct']} for attack in attacks],
                    'basis': 'max_all_resolved_native_attack_branches_for_resource'}
    # Actual burning deaths from laser weapons qualify too. The old fire
    # directory excluded them only as a display/counting policy, not a fact.
    for source in fire['sources'] + fire.get('optional_excluded_by_policy', []):
        add(source['type'], source['name'], fire=True)
    native_fire_hashes = {source['type'] for source in fire['sources']}
    native_fire_names = {source['name'] for source in fire['sources']}
    by_name = {}
    for resource, source in integration['stat_sources'].items():
        by_name.setdefault(source.get('name'), []).append(resource)
    gas_objects = {(owner['domain'], owner['object']) for status in docs[INPUTS[2]]['statuses']
                   if status['semanticId'] in ('gas', 'gas_2') and status.get('tickDamage')
                   for owner in status['appliedBy']}
    payload_owners = {}
    for name, stratagem in docs[INPUTS[3]]['stratagems'].items():
        for resource in stratagem.get('root', {}).get('payloads', []):
            payload_owners.setdefault(key(resource), set()).add(name)
    for domain, name in sorted(gas_objects):
        resources = []
        if domain == 'player_weapon_authoring':
            resources = [resource for weapon in players if weapon['name'] == name for resource in weapon['resources']]
        elif domain == 'support_weapon_authoring':
            resources = [resource for weapon in support if weapon['catalogIdentity'] == name for resource in weapon['resourceHashes']]
        elif domain == 'stratagem_authoring':
            strat = docs[INPUTS[3]]['stratagems'][name]
            # The universal empty pod is shared by dozens of unrelated
            # calldowns. It cannot prove a damaging gas payload.
            resources = [resource for resource in strat.get('root', {}).get('payloads', [])
                         if len(payload_owners.get(key(resource), ())) == 1]
        elif domain == 'throwable_authoring':
            resources = [resource for resource in by_name.get(name, [])
                         if integration['stat_sources'][resource].get('kind') == 'throwable']
        resources.extend(resource for resource in by_name.get(name, [])
                         if integration['stat_sources'][resource].get('kind') == 'weapon')
        for resource in resources:
            add(resource, name, poison=True)
    # Preserve exact resource aliases only when a unique SDK weapon identity
    # has the same exact English name. No translated-name/prefix matching.
    by_traits_name = {}
    for resource, row in list(traits.items()):
        by_traits_name.setdefault(row['name'], []).append(row)
    for resource, source in integration['stat_sources'].items():
        # Identically named delivery pods are separate actors; their crush
        # kills do not inherit the delivered gun's AP or elemental attacks.
        if source.get('kind') != 'weapon':
            continue
        rows = by_traits_name.get(source.get('name'), [])
        identities = {(row.get('armor_penetration_max'), row.get('fire', False), row.get('poison', False)) for row in rows}
        if len(identities) == 1:
            ap, burning, poison = next(iter(identities))
            add(resource, source['name'], ap, fire=burning, poison=poison)
    for resource, row in traits.items():
        row.setdefault('fire', False)
        row.setdefault('poison', False)
        source = integration['stat_sources'].get(resource, {})
        row['native_fire'] = resource in native_fire_hashes or (
            row['fire'] and source.get('kind') == 'weapon' and row['name'] in native_fire_names)
        row['native_poison'] = row['poison']
    return {'schema_version': 1, 'version': '0.4.52',
            'policy': 'exact_sdk_resource_max_ap_and_native_damaging_status_sources',
            'source_types': dict(sorted(traits.items())), 'armor_evidence': dict(sorted(evidence.items())),
            'inputs': {name: hashlib.sha256((runtime / name).read_bytes()).hexdigest() for name in INPUTS},
            'summary': {'sources': len(traits), 'ap_le_2': sum(row.get('armor_penetration_max', 99) <= 2 for row in traits.values()),
                        'fire_sources': sum(row['fire'] for row in traits.values()), 'poison_sources': sum(row['poison'] for row in traits.values())},
            'limitations': ['AP is a pinned native default; other mods can change attacks after construction.',
                            'A fire/gas-capable source alone is an approximation; observed final damage element takes precedence.',
                            'No global weapon stat batch is per-victim attribution evidence.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', type=Path, default=DEFAULT)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    result = build(args.runtime_root)
    body = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    target = ROOT / 'docs/kill-source-traits.json'
    if args.check:
        assert target.read_text(encoding='utf-8') == body, 'kill-source-traits.json differs from pinned SDK'
    else:
        target.write_text(body, encoding='utf-8', newline='\n')
    print(json.dumps(result['summary']))
