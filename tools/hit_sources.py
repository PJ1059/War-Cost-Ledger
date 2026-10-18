"""Derive projectile-stat coverage from the already installed Runtime SDK."""
import hashlib
import json
import os
from pathlib import Path


def generate(root, *, include_vehicle=False):
    sdk = Path(os.environ.get('HD2_RUNTIME_SDK', str(Path(os.environ['LOCALAPPDATA']) /
        'Temp/hd2-integration-research/HD2Runtime/SkyeShade-HD2Runtime-dcd996d/sdk')))
    files = [sdk / 'PlayerWeaponAuthoringCapabilities.json',
             sdk / 'SupportWeaponAuthoringCapabilities.json', root / 'docs/integration-catalogs.json']
    player, support, catalog = [json.loads(p.read_text(encoding='utf8')) for p in files]
    sources, names = {}, {}
    for item in player['weapons']:
        if 'conventional_projectile' in item['implementationFamilies']:
            names[item['name']] = 'conventional_projectile'
            for value in item['resources']:
                sources[value.removeprefix('0x').upper()] = {'name': item['name'], 'branch': 'Projectile'}
    for item in player['subweapons']:
        if 'ProjectileWeapon' in item['implementationFamilies']:
            for value in item['resources']:
                sources[value.removeprefix('0x').upper()] = {'name': item['name'], 'branch': 'Projectile'}
    for item in support['weapons']:
        if 'Projectile' in item['family']:
            names[item['name']] = 'support_projectile'
    for item in catalog['ammo']:
        if item['name_en'] in names:
            for value in item['source_types']:
                sources[value] = {'name': item['name_en'], 'branch': names[item['name_en']]}
    if include_vehicle:
        proof = root / 'docs/tank-hit-source-evidence.json'
        tanks = json.loads(proof.read_text(encoding='utf8'))
        # Resource hashes are reviewed identities, not semantic-id suffixes.
        # The source's hit creditor must still match the local peer upstream.
        for value, item in tanks['sources'].items():
            assert value == item['resource_hash']
            if item.get('source_resolution') == 'carrier_resource_alias':
                assert value == '16474112801385B6'
                assert set(item['mounted_projectile_resources']) == {'1FA1F596769225C2', '439F9E65C18567DA'}
            else:
                assert value == item['attack_resource_hash'] == item['mount_path_hash']
            assert len(value) == 16 and item['branch'] == 'Projectile'
            sources[value] = {'name': item['name'], 'branch': 'mounted_projectile'}
        files.append(proof)
    return {'schema': 1, 'stat': 'projectiles_hit', 'key': 0x897A5551,
            'runtime_commit': 'dcd996daca2573443956c07252c55c2d86dd0320',
            'policy': ('known_personal_and_exact_tank_projectile_branches_no_spray_beam_arc_or_dot'
                       if include_vehicle else 'known_personal_projectile_weapon_branches_no_spray_beam_arc_or_dot'),
            'sources': dict(sorted(sources.items())),
            'evidence': [{'file': ('HD2Runtime@dcd996daca2573443956c07252c55c2d86dd0320/sdk/' + p.name
                                  if p.parent == sdk else p.relative_to(root).as_posix()),
                          'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in files],
            'limitations': ['No per-hit target, armour or ricochet classification.',
                            ('Only the TD-220 two mounted projectile resources and their exact carrier alias are included; other vehicle/stratagem-only sources remain excluded.'
                             if include_vehicle else 'Unattributed, unknown and vehicle/stratagem-only sources are not added.'),
                            'Counts native projectile hits; enemy-only contact is not independently proven.',
                            'First valid snapshot establishes totals without replaying side notifications.']}
