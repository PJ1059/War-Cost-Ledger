"""Build read-only Career labels from existing exact source/capability catalogs.

No game/process access and no weapon-prefix heuristics. Used by build.py via
build_catalogs(integration, sdk_path)['weapon_catalog']; the wrapper also reports
input SHA-256s and unknown classifications for review.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

TYPES = {
    'Assault Rifle': '突击步枪', 'Energy-Based': '能量武器', 'Explosive': '爆炸武器',
    'Marksman Rifle': '精确射手步枪', 'Melee': '近战武器', 'Pistol': '手枪',
    'Shotgun': '霰弹枪', 'Special': '特殊武器', 'Submachine Gun': '冲锋枪',
    'Anti-Armor Precision': '精确反装甲武器', 'Anti-Tank': '反坦克武器',
    'Heavy Energy-Based': '重型能量武器', 'Heavy Explosive': '重型爆炸武器',
    'Heavy Explosives': '重型爆炸武器', 'Heavy Weapons': '重型武器',
    'Incendiary': '燃烧武器', 'Missiles': '导弹武器', 'Rocket Launcher': '火箭发射器',
    'Shotguns': '霰弹枪', 'Stun • Tesla': '电击武器',
}


def build_catalogs(integration: dict, sdk: Path) -> dict:
    sdk = Path(sdk)
    capabilities, inputs = [], {}
    for filename in ('PlayerWeaponAuthoringCapabilities.json', 'SupportWeaponCapabilities.json'):
        raw = (sdk / filename).read_bytes()
        inputs[filename] = hashlib.sha256(raw).hexdigest()
        document = json.loads(raw)
        records = document['weapons']
        for row in (records.values() if isinstance(records, dict) else records):
            name = row.get('catalogIdentity', row.get('name'))
            slot = row.get('slot')
            hashes = row.get('resourceHashes', row.get('resources', []))
            hashes = [value.removeprefix('0x').upper() for value in hashes]
            if not name or slot not in ('primary', 'secondary', 'support') or not hashes:
                continue
            capabilities.append(dict(name=name, category=slot,
                weapon_type=TYPES.get(row.get('weaponType', row.get('category')), '未知分类'),
                hashes=hashes, id=(row.get('canonicalResourceHash') or hashes[0]).removeprefix('0x').upper()))
    by_hash, by_name = {}, {}
    for row in capabilities:
        by_name.setdefault(row['name'], []).append(row)
        for value in row['hashes']:
            by_hash.setdefault(value, []).append(row)
    result, unknown = {}, []
    for source_hash, source in integration['stat_sources'].items():
        candidates = by_hash.get(source_hash, [])
        if not candidates and source.get('basis') != 'exact_cloud_hash_label_only':
            candidates = by_name.get(source.get('name'), [])
        identities = {(row['id'], row['category'], row['weapon_type']) for row in candidates}
        row = dict(id=source_hash, name=source.get('name_zh') or source.get('name') or source_hash,
                   category='unknown', weapon_type='未知分类', basis='unresolved_source_slot')
        if len(identities) == 1:
            canonical, role, subtype = next(iter(identities))
            row.update(id=canonical, category=role, weapon_type=subtype,
                basis='sdk_resource_identity' if source_hash in by_hash else 'unique_exact_catalog_name')
        elif not candidates and source.get('kind') in ('throwable', 'stratagem'):
            row.update(category=source['kind'], weapon_type='投掷物' if source['kind'] == 'throwable' else '战备效果',
                       basis='runtime_source_catalog_kind')
        else:
            unknown.append(source_hash)
        result[source_hash] = row
    return {'version': 1, 'weapon_catalog': result,
            'inputs': inputs, 'unknown_source_types': unknown,
            'policy': 'exact_resource_or_unique_exact_name_no_prefix_guess'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--integration', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = build_catalogs(json.loads(args.integration.read_text(encoding='utf8')), args.sdk)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'sources': len(result['weapon_catalog']), 'unknown': len(result['unknown_source_types']),
                      'output': str(args.output.resolve())}))
