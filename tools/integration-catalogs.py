"""Compile read-only Runtime identities against the user's prices and enemy roles.

No running game access. All unresolved identities/policies remain in the report.
"""
import hashlib
import os
import json
from pathlib import Path
import re
from build import ROOT, workbook_rows, cents

RUNTIME = Path(os.environ.get('HD2_RUNTIME_SOURCE', 'external/HD2Runtime'))
INPUTS = ['domains/event_entities.lua', 'schemas/stratagem_authoring_catalog.json',
          'sdk/PlayerWeaponAuthoringCapabilities.json', 'sdk/SupportWeaponCapabilities.json',
          'sdk/EnemyAuthoringCapabilities.json']
# Reviewed, unambiguous class/resource aliases. Ambiguous tiers, equipment/limbs and
# wiki candidate matches deliberately remain unresolved. A hash may have many instances.
ALIASES = {
    'scavenger_base': 'Scavenger', 'scavenger_tier_1': 'Scavenger',
    'scavenger_tier_1_captive': 'Scavenger', 'scavenger_spitter': 'Bile Spitter',
    'hunter_base': 'Hunter', 'shrieker': 'Shrieker', 'warrior_base': 'Warrior',
    'warrior_tier_1': 'Warrior', 'warrior_tier_1_captive': 'Warrior',
    'warrior_acid': 'Bile Warrior', 'boomer_nurser': 'Nursing Spewer',
    'boomer_nurser_mission': 'Nursing Spewer', 'boomer': 'Bile Spewer',
    'boomer_tier_2': 'Bile Spewer', 'warrior_big': 'Brood Commander',
    'warrior_big_tier2': 'Alpha Commander', 'charger_bull': 'Charger Behemoth',
    'charger_tier2': 'Charger Behemoth', 'dragon': 'Dragonroach',
    'hive_lord': 'Hive Lord', 'scavenger_gloom': 'Spore Burst Scavenger',
    'warrior_burrower': 'Rupture Warrior', 'berserker': 'Berserker',
    'gunship': 'Gunship', 'dropship': 'Dropship', 'siege_engine': 'Vox Engine',
    'corrupted': 'Voteless', 'observer': 'Watcher', 'meatglue': 'Fleshmob',
    'tripod': 'Harvester', 'tripod_tier_2': 'Harvester',
    'illuminate_attack_ship': 'Stingray', 'illuminate_dropship': 'Warp Ship',
    'illuminate_war_machine': 'Leviathan', 'mothership': 'Illuminate Overship',
    'exomech_melee': 'Veracitor', 'exomech_ranged': 'Gatekeeper',
    'bodyhorror_bladed': 'Wretch', 'bodyhorror_helmetguy': 'Crusher',
}
FACTIONS = {'终结族': 'terminids', '机器人': 'automatons', '光能者': 'illuminate'}


def read_json(name):
    return json.loads((RUNTIME / name).read_text(encoding='utf8'))


def catalogs():
    raw = (RUNTIME / INPUTS[0]).read_text(encoding='utf8')
    health, sources = {}, {}
    for match in re.finditer(r'\["([0-9A-F]{16})"\]=\{([^{}]*)\}', raw):
        value = json.loads('{' + re.sub(r'\["([^"\]]+)"\]=', r'"\1":', match[2]) + '}')
        (health if 'kill' in value else sources)[match[1]] = value
    assert len(health) == 501 and len(sources) == 218
    roster = json.loads((ROOT / 'docs/enemy-catalog/units.json').read_text(encoding='utf8'))['units']
    roles = {unit['name_en']: unit for unit in roster}
    cloud = json.loads((ROOT / 'docs/enemy-hash-evidence.json').read_text(encoding='utf8'))
    cloud_rows = {row[1]: row for row in cloud['rows'] if row[3]}
    entities, unresolved = {}, []
    for h, value in health.items():
        semantic = value.get('id', '')
        cls = semantic.rsplit('/', 1)[-1]
        name = value.get('display')
        basis = 'runtime_wiki_anatomy' if name in roles else 'reviewed_resource_alias'
        if name not in roles:
            name = ALIASES.get(cls)
        cloud_row = cloud_rows.get(h)
        if cloud_row:
            name, basis = cloud_row[3], 'cloud_cells_and_runtime_health_type'
        unit = roles.get(name)
        faction = value.get('faction') or (semantic.split('/')[2] if semantic.startswith('enemy/v1/') else None)
        if unit and cloud_row and faction is None:
            faction = FACTIONS[unit['faction']]
        asset = cls.startswith('spawner_factory_conscript_') or cls == 'landed_dropship'
        if value.get('kill') and name in ('Dropship', 'Warp Ship'):
            asset = True
        if not unit and not asset:
            if value.get('kill') and faction in FACTIONS.values():
                unresolved.append({'type': h, 'native_name': value.get('name'), 'semantic_id': semantic})
            continue
        if unit and faction != FACTIONS[unit['faction']]:
            raise ValueError('Enemy faction mismatch: ' + h)
        if unit and value.get('kind') == 'enemy' and not value.get('kill'):
            continue  # body parts do not become another enemy
        if not unit and asset:
            name = '机器人构造者' if cls.startswith('spawner_factory') else '停泊运输舰'
        entities[h] = {'key': name, 'name_zh': unit['name_zh'] if unit else name,
                       'name_en': name, 'class': unit['display_class'] if unit else '资产',
                       'faction': faction, 'air': bool(unit and '飞行' in unit['tags']),
                       'kill': bool(value['kill']), 'asset': asset,
                       'illuminate_ship': name == 'Warp Ship', 'basis': basis,
                       'semantic_id': semantic, 'cloud_row': cloud_row[0] if cloud_row else None}

    workbook = workbook_rows((2, 3, 4))
    native_calls = read_json(INPUTS[1])['stratagems']
    shell_rows = {'ST-002': 'A_ORB_GATLING', 'ST-004': 'A_ORB_120_HE',
                  'ST-005': 'A_ORB_AIRBURST', 'ST-008': 'A_ORB_380_HE',
                  'ST-009': 'A_ORB_380_HE', 'ST-011': 'A_ORB_NAPALM'}
    calls = []
    for row in workbook[3].values():
        if not row['A'].startswith('ST-') or row.get('P') not in native_calls:
            continue
        root = native_calls[row['P']]['root']
        total, transport, equipment, payload = [cents(row[c]) for c in ('G', 'D', 'E', 'F')]
        assert total == transport + equipment + payload
        calls.append({'key': {'ST-021': 'mg43', 'ST-022': 'm105'}.get(row['A'], row['A']),
                      'id': row['A'], 'row': row['row'], 'name_zh': row['C'], 'name_en': row['P'],
                      'native_id': root['id'], 'total_cents': total, 'transport_cents': transport,
                      'equipment_cents': equipment, 'prepaid_ammo_cents': payload, 'policy': row['L'],
                      'source': row.get('N', '')})
        if row['A'] in shell_rows:
            shell = workbook[4][shell_rows[row['A']]]
            assert row['L'] == '逐发计费' and len(root['payloads']) == 1
            calls[-1]['shell_cents'] = cents(shell['D'])
            calls[-1]['payload'] = f"{int(root['payloads'][0], 16):016X}"
            calls[-1]['shell_price_id'] = shell['A']
    calls.sort(key=lambda x: (x['id'] not in ('ST-021', 'ST-022'), x['id']))
    assert len(calls) == 94 and len({c['native_id'] for c in calls}) == 94
    players = {w['name']: w for w in read_json(INPUTS[2])['weapons']}
    supports = {w['catalogIdentity']: w for w in read_json(INPUTS[3])['weapons'].values()}
    ammo, pending = [], []
    for row in workbook[2].values():
        if not row['A'].startswith('EQ-') or not row.get('P'):
            continue
        name = row['P']
        matches = [h for h, v in sources.items() if v['name'] == name and v['kind'] == 'weapon']
        if row.get('G') not in ('消耗时计费', '场景拾取；消耗时计费') or row.get('E') not in ('发', '次', '枚', '支'):
            if cents(row.get('F') or '0') > 0:
                pending.append({'id': row['A'], 'name_zh': row.get('C'), 'reason': '计价单位或调用包干政策不适用于来源发射量'})
            continue
        pellet = None
        if name in players:
            fields = {f['semanticFieldId']: f['currentDefault'] for f in players[name]['fields']}
            alternate = fields.get('function_ammo.projectile') or {}
            if fields.get('projectile.alternate.type') or alternate.get('projectileType'):
                pending.append({'id': row['A'], 'name_zh': row['C'], 'reason': '同一来源具有可切换弹药，尚无逐次弹种区分'})
                continue
            pellet = fields.get('projectile.pellet_count')
        elif name in supports:
            # Every mother round is charged once at the confirmed parent price.
            # Source SHOTS does not distinguish programmed HE/flak selections;
            # do not drop the complete AC-8/GR-8/RL-77 feed because of that gap.
            values = {a.get('resolvedFields', {}).get('pellet_count') for a in supports[name]['runtimeAttacks']
                      if a['kind'] == 'Projectile' and 'parentRole' not in a}
            if len(values) == 1:
                pellet = values.pop()
        if not matches or not isinstance(pellet, (int, float)) or pellet < 1 or int(pellet) != pellet:
            pending.append({'id': row['A'], 'name_zh': row['C'], 'reason': '未证明按发/次消费的原生来源与投射物数量'})
            continue
        ammo.append({'id': row['A'], 'row': row['row'], 'name_zh': row['C'], 'name_en': name,
                     'unit_cents': cents(row['F']), 'source_types': matches,
                     'projectiles_per_unit': int(pellet), 'source': row.get('N', '')})
        if name.startswith('LAS-'):
            ammo[-1].update(billing_kind='maintenance',billing_label='武器维护折旧费')
        if name in supports and supports[name]['backpackDependent']:
            ammo[-1].update(backpack_ammo=True,pricing_policy='standard_parent_round',
                billing_kind='ammunition',billing_label='弹药')

    # Keep unknown and deferred costs visible; do not substitute estimates into bills.
    call_pending = [{'id': row['A'], 'name_zh': row['C'], 'reason': row.get('L')}
                    for row in workbook[3].values() if row['A'].startswith('ST-') and row.get('P') not in native_calls]
    translations = {row.get('P'): row.get('C') for sheet in (2, 3) for row in workbook[sheet].values()}
    for item in sources.values():
        item['name_zh'] = translations.get(item['name'])
    result = {'runtime_version': '0.30.3', 'runtime_commit': 'dcd996daca2573443956c07252c55c2d86dd0320',
            'inputs': {name: hashlib.sha256((RUNTIME / name).read_bytes()).hexdigest() for name in INPUTS},
            'roster_sha256': hashlib.sha256((ROOT / 'docs/enemy-catalog/units.json').read_bytes()).hexdigest(),
            'entities': entities, 'unresolved_enemies': unresolved,
            'unmapped_roster': [name for name in roles if name not in {v['name_en'] for v in entities.values()}],
            'cloud_rows_not_bound': [row for row in cloud['rows'] if row[1] not in entities],
            'stat_sources': sources, 'calls': calls, 'ammo': ammo,
            'deferred_ammo': pending, 'deferred_calls': call_pending,
            'live_new_readers_verified': False}
    # Price regeneration must retain the exact-hash labels already reviewed in
    # .47/.49, including Runtime kill records whose optional kind is missing.
    from resource_hash_labels import apply_labels, runtime_entity_rows
    labels = json.loads((ROOT / 'docs/resource-hash-aliases.json').read_text(encoding='utf8'))
    result, _ = apply_labels(result, labels, runtime_entity_rows(raw))
    # These mounted sources were independently proved in the .47 vehicle
    # contract. Cloud labels alone must not downgrade their known category.
    result['stat_sources'].update({
        '16474112801385B6': {'name': 'TD-220 Bastion MK XVI', 'name_zh': 'TD-220 堡垒 MK XVI',
            'kind': 'stratagem', 'basis': 'exact_sdk_mounted_projectile_carrier_resource', 'cloud_row': 106},
        '1FA1F596769225C2': {'name': 'TD-220 Bastion MK XVI / attach_tank_gun',
            'name_zh': 'TD-220 堡垒 · 主炮', 'kind': 'stratagem'},
        '439F9E65C18567DA': {'name': 'TD-220 Bastion MK XVI / attach_tank_gun_mg',
            'name_zh': 'TD-220 堡垒 · 同轴机枪', 'kind': 'stratagem'},
    })
    return result


if __name__ == '__main__':
    result = catalogs()
    path = ROOT / 'docs/integration-catalogs.json'
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(f'{len(result["entities"])} enemy/asset hashes, {len(result["unmapped_roster"])} roster identities pending; '
          f'{len(result["calls"])} call prices, {len(result["ammo"])} ammunition prices.')
