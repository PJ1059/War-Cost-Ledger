"""Build typed native damage-source candidates from the reviewed, pinned data.

This is an offline authoring tool. The addon builds from the checked-in JSON;
neither building the addon nor running its resolver opens the data library.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import os
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DEFAULT = Path(os.environ.get('HD2_RUNTIME_SOURCE', 'external/HD2Runtime'))
DOCUMENT = ROOT / 'docs/damage-source-catalog.json'
BUILD = 'F5FEE03DCFDB'
FILES = ('generated_entities.dl_bin', 'dl_library.dl_typelib',
         'generated_projectile_settings.dl_bin', 'generated_explosion_settings.dl_bin',
         'generated_damage_settings.dl_bin', 'generated_beam_settings.dl_bin',
         'generated_arc_settings.dl_bin')
SDK_FILES = ('schemas/build_profile.json', 'sdk/SupportWeaponCapabilities.json',
             'sdk/PlayerWeaponAuthoringCapabilities.json', 'sdk/ThrowableAuthoringCapabilities.json',
             'sdk/ExplosionCatalogue.json', 'sdk/AttackOutputCapabilities.json',
             'domains/explosion_catalogue.lua')
PINNED_EXPLOSION_DOMAIN_SHA256 = '52106EB01001FA1B0E0DF18CD9BEED0D945127F48C7108463A90973B80C3CC9F'
KINDS = ('projectile', 'explosion', 'damage_info', 'beam', 'arc')
ENUMS = {'ProjectileType': 'projectile', 'ExplosionType': 'explosion', 'DamageInfoType': 'damage_info',
         'BeamType': 'beam', 'ArcType': 'arc'}
PINNED_SETTINGS_SHA256 = {
    'generated_projectile_settings.dl_bin': '50AF7CCCF03697A0EF96B7F9DDEB19279ADC3B887BD95E0F972996844B7221EA',
    'generated_explosion_settings.dl_bin': '1F7C53253250E89CD17A1381BD5A2FEB48AEB336E4A3C97E74311C6FB67D7AF6',
    'generated_damage_settings.dl_bin': '55E2BC4AC209D45363670A5952C3FE5DE045854AA062634A5A2444CB11510C35',
    'generated_beam_settings.dl_bin': 'FDE93701608D12CB1AA4985F11EB9F2BAB8BB6DC4E8F556B7F7B18B171C7017B',
    'generated_arc_settings.dl_bin': '08E1461A8D8EE1C46FBCE72FFAA629B489AE512B8B8253AE187D9DBF78A0F159',
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()


def discover_datalibrary(runtime, explicit=None):
    if explicit is not None:
        choices = [Path(explicit)]
    elif os.environ.get('HD2_DAMAGE_DATALIBRARY'):
        choices = [Path(os.environ['HD2_DAMAGE_DATALIBRARY'])]
    else:
        profile = json.loads((runtime / 'schemas/build_profile.json').read_text(encoding='utf-8'))
        choices = [runtime / profile['builds'][BUILD]['datalibrary']['path'],
                   ROOT.parent / 'spore-map/vendor/filediver/datalibrary']
    for folder in choices:
        if all((folder / name).is_file() for name in FILES):
            return folder.resolve()
    raise FileNotFoundError('Set HD2_DAMAGE_DATALIBRARY or --datalibrary to the pinned extracted Filediver datalibrary')



def lua_fields(table):
    # Read only string-keyed fields of the SDK's generated static Lua tables.
    # Values remain text; nested tables and escaped strings are skipped intact.
    # No Lua code or external runtime is executed by this offline generator.
    if not table.startswith('{') or not table.endswith('}'):
        raise ValueError('expected generated Lua table')
    fields, at = {}, 1
    key_pattern = re.compile(r'\[\s*("(?:\\.|[^"\\])*")\s*\]\s*=\s*')
    while at < len(table) - 1:
        while table[at].isspace() or table[at] == ',':
            at += 1
        if table[at] == '}':
            break
        match = key_pattern.match(table, at)
        if not match:
            raise ValueError('unexpected generated Lua field')
        key, start = json.loads(match[1]), match.end()
        at, depth, quote, escaped = start, 0, False, False
        while at < len(table):
            char = table[at]
            if quote:
                if escaped:
                    escaped = False
                elif char == '\\':
                    escaped = True
                elif char == '"':
                    quote = False
            elif char == '"':
                quote = True
            elif char == '{':
                depth += 1
            elif char == '}':
                if depth == 0:
                    break
                depth -= 1
            elif char == ',' and depth == 0:
                break
            at += 1
        if key in fields:
            raise ValueError('duplicate generated Lua field')
        fields[key] = table[start:at].strip()
    return fields


def unique_explosion_names(rows):
    identities = defaultdict(set)
    for name, native_id, legacy in rows:
        identities[name].add(native_id)
        if legacy:
            identities[legacy].add(native_id)
    return {name: next(iter(ids)) for name, ids in sorted(identities.items()) if len(ids) == 1}


def explosion_names(runtime, settings):
    path = runtime / 'domains/explosion_catalogue.lua'
    if sha(path) != PINNED_EXPLOSION_DOMAIN_SHA256:
        raise ValueError('explosion domain fingerprint does not match the reviewed SDK build')
    table = lua_fields(path.read_text(encoding='utf-8').split('return ', 1)[1].strip())
    if json.loads(table['build']) != BUILD:
        raise ValueError('explosion domain build mismatch')
    native = lua_fields(table['explosions'])
    public = json.loads((runtime / 'sdk/ExplosionCatalogue.json').read_text(encoding='utf-8'))['explosions']
    if set(native) != {row['name'] for row in public}:
        raise ValueError('public and native explosion names differ')
    rows = []
    for item in public:
        entry = lua_fields(native[item['name']])
        native_id = int(entry['type'])
        raw = settings.decode('explosion', native_id)
        if raw is None:
            raise ValueError('named ExplosionType has no native row')
        damage = lua_fields(entry['damage']) if entry['damage'] != 'nil' else None
        if raw['4'] != (int(damage['type']) if damage else 0):
            raise ValueError('named explosion native DamageInfo link differs')
        legacy = lua_fields(entry['legacy']) if entry['legacy'] != 'nil' else None
        legacy_name = json.loads(legacy['name']) if legacy else None
        if item.get('legacyName') != legacy_name:
            raise ValueError('public and native legacy explosion names differ')
        rows.append((item['name'], native_id, legacy_name))
    return unique_explosion_names(rows)


def build(runtime=None, datalibrary=None):
    runtime = Path(runtime or os.environ.get('HD2_RUNTIME_SOURCE', RUNTIME_DEFAULT)).resolve()
    folder = discover_datalibrary(runtime, datalibrary)
    profile = json.loads((runtime / SDK_FILES[0]).read_text(encoding='utf-8'))['builds'][BUILD]
    inputs = {name: sha(folder / name) for name in FILES}
    # Never silently regenerate against another game build's enums or layouts.
    if inputs[FILES[0]] != profile['datalibrary']['entitiesSha256'].upper() or inputs[FILES[1]] != profile['datalibrary']['typelibSha256'].upper():
        raise ValueError('datalibrary entity/type-library fingerprints do not match the reviewed SDK build')
    if any(inputs[name] != expected for name, expected in PINNED_SETTINGS_SHA256.items()):
        raise ValueError('datalibrary settings fingerprints do not match the reviewed native tables')
    sys.path.insert(0, str(runtime / 'scripts'))
    from scan.tables import EntityTables, decode
    from scan.settings import SettingsView

    tables = EntityTables(folder)
    settings = SettingsView(tables)
    available = {kind: {native_id for _, native_id, _ in settings.table('damage' if kind == 'damage_info' else kind).rows}
                 for kind in KINDS}
    source_doc = json.loads((ROOT / 'docs/integration-catalogs.json').read_text(encoding='utf-8'))
    labels = {resource: row for resource, row in source_doc['stat_sources'].items()
              if row.get('kind') in ('weapon', 'throwable', 'stratagem')}
    links = {f'{kind}:{native_id}': [] for kind, ids in available.items() for native_id in ids}
    roots = defaultdict(list)
    direct_origins = defaultdict(set)

    def link(start_kind, start_id, end_kind, end_id, field, **extra):
        if end_id and end_id in available[end_kind]:
            links[f'{start_kind}:{start_id}'].append({'kind': end_kind, 'id': end_id, 'field_offset': field, **extra})

    for _, native_id, _ in settings.table('projectile').rows:
        row = settings.decode('projectile', native_id)
        link('projectile', native_id, 'damage_info', row['60'], 60, role='direct_hit')
        link('projectile', native_id, 'explosion', row['144'], 144, role='impact')
        link('projectile', native_id, 'explosion', row['156'], 156, role='expiry')
    dormant = []
    for _, native_id, _ in settings.table('explosion').rows:
        row = settings.decode('explosion', native_id)
        link('explosion', native_id, 'damage_info', row['4'], 4, role='explosion_damage')
        if row['80'] > 0:
            link('explosion', native_id, 'projectile', row['84'], 84, role='shrapnel', count=row['80'])
        elif row['84']:
            dormant.append({'explosion': native_id, 'projectile': row['84'], 'count': 0})

        link('explosion', native_id, 'arc', row['120'], 120, role='explosion_arc')
    for _, native_id, _ in settings.table('beam').rows:
        row = settings.decode('beam', native_id)
        link('beam', native_id, 'damage_info', row['12'], 12, role='beam_damage')
        link('beam', native_id, 'explosion', row['96'], 96, role='beam_explosion')
    for _, native_id, _ in settings.table('arc').rows:
        row = settings.decode('arc', native_id)
        link('arc', native_id, 'damage_info', row['36'], 36, role='arc_damage')

    # Native typed fields, not translated names or wiki attack branch labels.
    for component_name in tables.component_names():
        component = tables.component(component_name)
        members = [member for member in component.members() if member.type_name in ENUMS]
        if not members:
            continue
        for record, owners in component.owner_map().items():
            raw = component.raw(record)
            for member in members:
                values = decode(member, raw)
                for native_id in values if isinstance(values, list) else [values]:
                    kind = ENUMS[member.type_name]
                    if native_id not in available[kind] or not native_id:
                        continue
                    node = f'{kind}:{native_id}'
                    for owner in owners:
                        resource = f'{owner:016X}'
                        direct_origins[node].add('resource:' + resource)
                        roots[resource].append({'kind': kind, 'id': native_id,
                                                'component': component_name, 'member': member.path})

    incoming = defaultdict(set)
    for node, edges in links.items():
        for edge in edges:
            incoming[f"{edge['kind']}:{edge['id']}"].add(node)
    # An unowned native branch can also feed a shared attack. Retain that
    # uncertainty instead of making the one named consumer look exclusive.
    origins = {node: set(direct_origins[node]) for node in links}
    for node in links:
        if not incoming[node] and not origins[node]:
            origins[node].add('unowned:' + node)
    changed = True
    while changed:
        changed = False
        for node, edges in links.items():
            for edge in edges:
                target = f"{edge['kind']}:{edge['id']}"
                before = len(origins[target])
                origins[target].update(origins[node])
                changed = changed or before != len(origins[target])

    reverse = {kind: {} for kind in KINDS}
    for node in sorted(links, key=lambda value: (value.split(':')[0], int(value.split(':')[1]))):
        kind, native_id = node.split(':')
        candidates = sorted(origin[9:] for origin in origins[node]
                            if origin.startswith('resource:') and origin[9:] in labels)
        unknown = sorted(origin for origin in origins[node]
                         if not origin.startswith('resource:') or origin[9:] not in labels)
        reverse[kind][native_id] = {'candidates': candidates, 'unresolved': bool(unknown) or not origins[node],
                                   'shared': len(origins[node]) > 1}

    def reachable(resource):
        seen, pending = set(), [f"{row['kind']}:{row['id']}" for row in roots[resource]]
        while pending:
            node = pending.pop()
            if node in seen:
                continue
            seen.add(node)
            pending.extend(f"{edge['kind']}:{edge['id']}" for edge in links[node])
        return {kind: sorted(int(node.split(':')[1]) for node in seen if node.startswith(kind + ':')) for kind in KINDS}

    sources = {}
    for resource in sorted(labels):
        row = labels[resource]
        if resource not in roots:
            continue
        sources[resource] = {'name': row['name'], 'name_zh': row.get('name_zh'), 'kind': row['kind'],
                             'evidence': 'parsed_native_typed_references',
                             'roots': sorted(roots[resource], key=lambda item: (item['kind'], item['id'], item['component'], item['member'])),
                             'types': reachable(resource)}
    # The SDK's wiki-to-native attack matching remains useful coverage metadata,
    # but PARTIAL wiki branches do not create any production candidate edge.
    support = json.loads((runtime / 'sdk/SupportWeaponCapabilities.json').read_text(encoding='utf-8'))['weapons']
    for weapon in support.values():
        unresolved = sorted({attack['name'] for attack in weapon.get('attackGraph', []) if attack.get('state') != 'RESOLVED'})
        for raw_resource in weapon.get('resourceHashes', []):
            resource = f'{int(raw_resource, 16):016X}'
            if resource in sources:
                sources[resource]['sdk_branch_coverage'] = 'partial' if unresolved else 'resolved'
                if unresolved:
                    sources[resource]['sdk_unresolved_branch_labels'] = unresolved

    # Keep all native rows and every resource's typed roots. Runtime raw actor
    # hashes can name an unlabelled carrier; discarding its roots here loses
    # evidence, while treating it as a named weapon would invent an identity.
    relevant = set(links)
    named_reachable = {f'{kind}:{native_id}' for source in sources.values()
                       for kind, ids in source['types'].items() for native_id in ids}
    resource_nodes = {}
    for resource, refs in sorted(roots.items()):
        unique = {(row['kind'], row['id'], row['component'], row['member']): row for row in refs}
        resource_nodes[resource] = [unique[key] for key in sorted(unique)]
    source_radius = {}
    for resource, source in sources.items():
        radii = [max(settings.decode('explosion', native_id)[field] for field in ('16', '20', '24'))
                 for native_id in source['types']['explosion']]
        if radii and max(radii) > 0:
            source_radius[resource] = max(radii)
    return {'schema_version': 1, 'build': BUILD,
            'policy': 'native_typed_parent_candidates_preserve_shared_and_unresolved_origins',
            'namespace_note': 'Resource hashes are 64-bit identities. ProjectileType, ExplosionType, DamageInfoType, BeamType and ArcType are distinct u32 enum namespaces.',
            'inputs': {'datalibrary': inputs, 'runtime': {name: sha(runtime / name) for name in SDK_FILES},
                       'integration_catalogs_sha256': sha(ROOT / 'docs/integration-catalogs.json')},
            'sources': sources, 'resource_nodes': resource_nodes,
            'explosion_names': explosion_names(runtime, settings), 'nodes': {node: links[node] for node in sorted(relevant)},
            'reverse': reverse, 'dormant_zero_count_shrapnel': sorted(dormant, key=lambda row: row['explosion']),
            'source_radius': source_radius,
            'source_radius_policy': 'Maximum of native inner/outer/shockwave radii across the source\'s parsed explosion chain; this is not a shrapnel maximum-travel-distance claim.',
            'unresolved_origin_evidence': {node: sorted(origin for origin in origins[node]
                                                       if not origin.startswith('resource:') or origin[9:] not in labels)
                                           for node in sorted(relevant) if reverse[node.split(':')[0]][node.split(':')[1]]['unresolved']},
            'summary': {'sources': len(sources), 'native_nodes': len(relevant), 'named_reachable_nodes': len(named_reachable),
                        'resource_roots': len(resource_nodes),
                        'admitted_damage_info': sum(bool(row['candidates']) for row in reverse['damage_info'].values()),
                        'ambiguous_damage_info': sum(row['shared'] or row['unresolved'] for row in reverse['damage_info'].values())},
            'limitations': ['Pinned native defaults can be replaced by other MODs.',
                            'A configured reference proves capability, not that it was used for an individual kill.',
                            'Shared child damage requires parent-source context; a single shared child ID cannot identify its weapon.',
                            'Unknown resources and unowned branches remain unresolved; wiki-only partial branches create no native edges.',
                            'No status-tick ownership, melee timing, code-literal explosion caller, or runtime kill event is invented by this static catalog.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', type=Path)
    parser.add_argument('--datalibrary', type=Path)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    document = build(args.runtime_root, args.datalibrary)
    body = json.dumps(document, ensure_ascii=False, indent=2) + '\n'
    if args.check:
        assert DOCUMENT.read_text(encoding='utf-8') == body, 'damage-source-catalog.json differs from pinned native data'
    else:
        DOCUMENT.write_text(body, encoding='utf-8', newline='\n')
    print(json.dumps(document['summary']))


if __name__ == '__main__':
    main()
