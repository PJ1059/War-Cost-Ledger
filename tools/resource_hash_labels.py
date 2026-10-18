"""Review exact 64-bit resource labels from the user's public Tencent sheet.

Decimal IDs are parsed as Python integers, never floats. Labels identify a
resource, not its damage ownership, fatal weapon, class, or player account.
Sheet notes are excluded and never interpreted as commands.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re

SOURCE = 'https://docs.qq.com/sheet/DQ3Rya0VudGd3WWtv?tab=000001'
REVIEWED_ENEMIES = {
    # Runtime confirms this resource counts as a kill but leaves its kind and
    # faction unresolved. Exact public-sheet/BFV identities agree; the user
    # confirmed the local roster class on 2026-10-15.
    'D1E990BAF22D5A52': dict(key='Predator Stalker',name_zh='掠食追踪虫',
        name_en='Predator Stalker',faction='terminids',**{'class':'中型精英'},
        class_basis='user_confirmed_2026-10-15',
        identity_basis='exact_cloud_hash_and_runtime_kill_and_bfv17_type_identity'),
    # The remaining entries have the same missing-kind defect. Exact Runtime
    # kill resource + QQ identity + BFV 1.7 manual identity agree. BFV feedback
    # tiers are not silently substituted for the user's own roster classes.
    '089833D2880D9E06': dict(key='Incendiary MG Raider',name_zh='机枪奇袭者（炽灼部队）',
        name_en='Incendiary MG Raider',faction='automatons',bfv_source_line=1589),
    '09DFB04B2E578BC3': dict(key='Incendiary Rocket Trooper',name_zh='激光装甲兵',
        name_en='Incendiary Rocket Trooper',faction='automatons',bfv_source_line=1587),
    '1B5B9AC4F96B36E5': dict(key='Incendiary Commissar',name_zh='机械统帅（炽灼部队）',
        name_en='Incendiary Commissar',faction='automatons',bfv_source_line=1591),
    '2A12104F2853AE16': dict(key='Rocket Raider',name_zh='火箭奇袭者',
        name_en='Rocket Raider',faction='automatons',**{'class':'轻型'},
        class_basis='reviewed_roster_exact_identity',bfv_source_line=1560),
    '34DFD23365472E9E': dict(key='Obtruder',name_zh='突入者',
        name_en='Obtruder',faction='illuminate',air=True,**{'class':'轻型'},
        class_basis='reviewed_roster_exact_identity',bfv_source_line=1621),
    '9076EEED17FCEE35': dict(key='Reinforced Scout Strider',name_zh='强化侦察纵步者',
        name_en='Reinforced Scout Strider',faction='automatons',**{'class':'中型'},
        class_basis='reviewed_roster_exact_identity',bfv_source_line=1573),
    '91EBD77931110AFC': dict(key='Heavy Devastator MK3',name_zh='重型蹂躏者 MK3',
        name_en='Heavy Devastator MK3',faction='automatons',bfv_source_line=1571),
    '98152772A72F7838': dict(key='Dropship',name_zh='运输舰',
        name_en='Dropship',faction='automatons',air=True,asset=True,**{'class':'重型'},
        class_basis='reviewed_roster_exact_identity',bfv_source_line=1585),
    'A4552F97033392F4': dict(key='Jet Brigade MG Raider',name_zh='喷气旅机枪奇袭者',
        name_en='Jet Brigade MG Raider',faction='automatons',**{'class':'轻型'},
        class_basis='reviewed_roster_exact_identity',bfv_source_line=1602),
    'B4ED319B39F5457B': dict(key='MG Raider',name_zh='机枪奇袭者',
        name_en='MG Raider',faction='automatons',**{'class':'轻型'},
        class_basis='reviewed_roster_exact_identity',bfv_source_line=1561),
    'FC8DEC78BE8AB47D': dict(key='Devastator MK2 Spawn',name_zh='蹂躏者 MK2 移动工厂生产',
        name_en='Devastator MK2 Spawn',faction='automatons',bfv_source_line=1565),
    # QQ's enemy-group headings are explicit. These two exact resources are
    # native kill identities, although BFV's manual identity table omits them.
    # The labels do not establish their feedback tier or combat availability.
    '52018DEB9AB6827E': dict(key='Jet Brigade Trooper (Crash)',name_zh='喷气装甲兵（崩溃）',
        name_en='Jet Brigade Trooper (Crash)',faction='automatons',
        identity_basis='exact_cloud_hash_runtime_kill_and_cloud_enemy_group'),
    'B056F8FC74ABA02D': dict(key='Cannon Trooper',name_zh='激光炮装甲兵（废案）',
        name_en='Cannon Trooper',faction='automatons',
        identity_basis='exact_cloud_hash_runtime_kill_and_cloud_enemy_group'),
}


def hex_id(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not re.fullmatch(r'[0-9]{1,20}', value):
        return None
    number = int(value, 10)
    return f'{number:016X}' if 0 < number < 2**64 else None


def build_labels(cells, *, source=SOURCE):
    grid = {(v['row'], v['col']): v['text'] for v in cells
            if isinstance(v, dict) and isinstance(v.get('row'), int) and isinstance(v.get('col'), int)
            and isinstance(v.get('text'), str)}
    columns = {col for (row, col), value in grid.items() if row == 4 and value.strip() == '哈希值'}
    assert columns, 'Expected reviewed hash-value header row'
    aliases, conflicts = {}, {}
    for (row, col), value in sorted(grid.items()):
        if row <= 4 or col not in columns:
            continue
        resource = hex_id(value)
        if not resource:
            continue
        zh = grid.get((row, col + 1), '').strip()
        en = grid.get((row, col + 2), '').strip()
        if not zh and not en:
            continue
        if any(len(v) > 128 or re.search(r'[\x00-\x1f\x7f]', v) for v in (zh, en)):
            continue
        label = dict(name_zh=zh or en, name_en=en or zh,
                     decimal=value.strip(), sheet='000001', row=row + 1, column=col + 1)
        previous = aliases.get(resource)
        if previous and (previous['name_zh'], previous['name_en']) != (label['name_zh'], label['name_en']):
            conflicts.setdefault(resource, [previous]).append(label)
        else:
            aliases.setdefault(resource, label)
    for resource in conflicts:
        aliases.pop(resource, None)
    return dict(version=1, source=source, observed_on='2026-10-15',
                encoding='full_u64_decimal_string_to_16_upper_hex_no_float',
                policy='labels_only_not_weapon_victim_pairing_or_size_or_ownership',
                aliases=dict(sorted(aliases.items())), conflicts=conflicts)


def runtime_entity_rows(text):
    # The upstream generated entity dictionaries contain only scalar fields.
    # Do not match the separate source-stat catalog that follows them.
    text = text.split('["sources"]=', 1)[0]
    result = {}
    for resource, body in re.findall(r'\["([0-9A-F]{16})"\]=\{([^{}]*)\}', text):
        values = dict(re.findall(r'\["([^"]+)"\]="([^"]*)"', body))
        values['kill'] = '["kill"]=true' in body
        result[resource] = values
    return result


def apply_labels(integration, labels, runtime):
    out = copy.deepcopy(integration)
    added, labelled_sources = [], []
    # Only these reviewed variants inherit a class from the already-reviewed
    # same enemy family. Other new exact enemy labels retain unknown size.
    families = {'32541FC4EC7C9CDC': 'Warrior', '9A8A3AAE287B230C': 'Scavenger',
                'B2A6FA1E4284C7E6': 'Warrior'}
    for resource, label in labels['aliases'].items():
        native = runtime.get(resource, {})
        reviewed = REVIEWED_ENEMIES.get(resource)
        if reviewed:
            assert label['name_en'] == reviewed['name_en'], 'Reviewed enemy identity changed'
        if resource not in out['entities'] and native.get('kill') and (native.get('kind') == 'enemy' or reviewed):
            family = next((v for v in integration['entities'].values()
                           if v.get('key') == families.get(resource)), None)
            row = dict(key=label['name_en'], name_zh=label['name_zh'], name_en=label['name_en'],
                       faction=native.get('faction', 'unknown'), kill=True, asset=False,
                       air=family.get('air', False) if family else False,
                       **{'class': family['class'] if family else '未知体型'},
                       basis='exact_cloud_hash_and_runtime_enemy_type', semantic_id=native.get('id'),
                       cloud_row=label['row'], cloud_column=label['column'])
            if family:
                row['class_basis'] = 'reviewed_same_enemy_family_variant'
                row['class_family'] = families[resource]
            if reviewed:
                row.update(reviewed)
                row['basis']='reviewed_exact_hash_runtime_unresolved_enemy'
                row.setdefault('identity_basis','exact_cloud_hash_and_runtime_kill_and_bfv17_type_identity')
            out['entities'][resource] = row
            added.append(resource)
        # A stat source is not necessarily a player-held weapon. Preserve the
        # independent category, even for enemies and explosive scenery.
        if resource not in out['stat_sources']:
            out['stat_sources'][resource] = dict(name=label['name_en'], name_zh=label['name_zh'],
                kind='unknown', basis='exact_cloud_hash_label_only', cloud_row=label['row'])
            labelled_sources.append(resource)
    return out, dict(enemy_types_added=added, source_labels_added=labelled_sources,
                     source_labels_do_not_prove_player_weapon=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cells', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--integration', type=Path)
    parser.add_argument('--runtime-entities', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    raw = args.cells.read_bytes()
    labels = build_labels(json.loads(raw))
    labels['decoded_cells_sha256'] = hashlib.sha256(raw).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(labels, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    report = dict(aliases=len(labels['aliases']), conflicts=len(labels['conflicts']))
    if args.apply:
        assert args.integration and args.runtime_entities
        integration, changes = apply_labels(json.loads(args.integration.read_text(encoding='utf8')), labels,
                                            runtime_entity_rows(args.runtime_entities.read_text(encoding='utf8')))
        args.integration.write_text(json.dumps(integration, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
        report.update(changes)
    print(json.dumps(report))
