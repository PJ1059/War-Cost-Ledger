"""Compile priced, native magazine identities offline; never read a running game.

Build contract: runpy.run_path(path)['build'](prices) returns by_type + evidence.
CLI writes only docs/magazine-pricing-evidence.json, or --check compares that file.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path(os.environ.get('HD2_RUNTIME_SOURCE', 'external/HD2Runtime'))
WORKBOOK = ROOT / 'pricing/HD2-军需价格表-v0.2.xlsx'
OUTPUT = ROOT / 'docs/magazine-pricing-evidence.json'
INPUTS = ('sdk/PlayerWeaponAuthoringCapabilities.json', 'sdk/SupportWeaponCapabilities.json')
MAGAZINE = 'WeaponMagazineComponentData'
ROUNDS = 'WeaponRoundsComponentData'
TORCHER = '4FB0F8C02F55C82B'


def normal(value):
    return f'{int(value, 16):016X}'


def torcher_price(prices):
    """Exact already-reviewed workbook row; no new price assumptions."""
    raw = WORKBOOK.read_bytes()
    if hashlib.sha256(raw).hexdigest() != prices['workbook_sha256']:
        raise ValueError('MAGAZINE_PRICE_WORKBOOK_CHANGED')
    namespace = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(WORKBOOK) as source:
        shared = ET.fromstring(source.read('xl/sharedStrings.xml'))
        strings = [''.join(x.itertext()) for x in shared.findall('s:si', namespace)]
        sheet = ET.fromstring(source.read('xl/worksheets/sheet2.xml'))
    cells = {}
    for cell in sheet.findall("s:sheetData/s:row[@r='59']/s:c", namespace):
        node = cell.find('s:v', namespace)
        if node is not None:
            cells[cell.get('r')] = strings[int(node.text)] if cell.get('t') == 's' else node.text
    if (cells.get('A59') != 'EQ-054' or cells.get('P59') != 'FLAM-66 Torcher'
            or cells.get('E59') != '显示单位' or cells.get('F59') != '0.3'):
        raise ValueError('MAGAZINE_TORCHER_PRICE_ROW_CHANGED')
    return {'id': 'EQ-054', 'name_zh': cells['C59'], 'name_en': cells['P59'],
            'unit_cents': 30, 'source_types': [TORCHER], 'projectiles_per_unit': None,
            'price_evidence': {'sheet': 2, 'row': 59, 'unit': cells['E59'], 'value_mc': cells['F59']}}


def build(prices, runtime=RUNTIME):
    expected = json.loads((ROOT / 'docs/integration-catalogs.json').read_text(encoding='utf8'))['inputs']
    inputs, documents = {}, {}
    for name in INPUTS:
        raw = (runtime / name).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != expected[name]:
            raise ValueError('MAGAZINE_SDK_CHANGED: ' + name)
        inputs[name] = digest
        documents[name] = json.loads(raw)
    players = {w['name']: w for w in documents[INPUTS[0]]['weapons']}
    supports = {w['catalogIdentity']: w for w in documents[INPUTS[1]]['weapons'].values()}
    result, deferred = {}, []
    candidates = list(prices['ammo']) + [torcher_price(prices)]
    for price in candidates:
        name = price['name_en']
        weapon = players.get(name)
        proofs = {}
        if weapon is not None:
            families = weapon['implementationFamilies']
            # A component record proves the feed; a name containing "rifle" does not.
            backing = [f for f in weapon['fields'] if (f.get('backing') or {}).get('component') == MAGAZINE]
            incompatible = [f for f in weapon['fields'] if (f.get('backing') or {}).get('component') == ROUNDS]
            fuel = name == 'FLAM-66 Torcher'
            if (backing and not incompatible and 'rounds_feed' not in families
                    and (families == ['conventional_projectile'] or fuel)):
                for resource in weapon['resources']:
                    proofs[normal(resource)] = {'sdk': INPUTS[0], 'catalog_identity': name,
                        'resource': normal(resource), 'families': families,
                        'native_component': MAGAZINE,
                        'backing': [{'field': f['semanticFieldId'], **f['backing']} for f in backing],
                        'capacity_is_read_live': True}
        else:
            weapon = supports.get(name)
            if weapon and not weapon['backpackDependent'] and not weapon['expendable'] and not weapon['selectableAmmoModes']:
                for feed in weapon['ammoFeedMagazine']:
                    resource, ownership = normal(feed['resourceHash']), feed['ownership']
                    components = [c for c in weapon['weaponComponents'] if normal(c['resourceHash']) == resource]
                    magazine = [c for c in components if c['component'] == MAGAZINE]
                    incompatible = [c for c in components if c['component'] == ROUNDS]
                    capacity = ownership.get('capacity') or {}
                    if (ownership.get('kind') == 'magazine' and magazine and not incompatible
                            and capacity.get('status') == 'RESOLVED'
                            and capacity.get('source') == MAGAZINE + '.Capacity'
                            and isinstance(capacity.get('value'), (int, float)) and capacity['value'] > 0
                            and not feed.get('backpackDependencyCatalogued')
                            and not feed.get('weaponLinkedAmmoComponentOwned')):
                        proofs[resource] = {'sdk': INPUTS[1], 'catalog_identity': name,
                            'resource': resource, 'native_component': MAGAZINE,
                            'components': magazine, 'ammoFeedMagazine': feed,
                            'capacity_is_read_live': True}
        included = []
        for source in price['source_types']:
            resource = normal(source)
            proof = proofs.get(resource)
            if proof is None:
                continue
            if resource in result:
                raise ValueError('MAGAZINE_DUPLICATE_PRICE_RESOURCE: ' + resource)
            result[resource] = {'id': price['id'], 'unit_cents': price['unit_cents'],
                'name_zh': price['name_zh'], 'name_en': name, 'source_type': resource,
                'stock_kind': 'magazine', 'chamber_policy': 'none' if resource == TORCHER else 'separate_round',
                'projectiles_per_unit': price.get('projectiles_per_unit'),
                'inventory_units_are_price_units': True, 'evidence': proof,
                'price_evidence': price.get('price_evidence', {'price_id': price['id'], 'row': price.get('row')})}
            included.append(resource)
        omitted = [normal(s) for s in price['source_types'] if normal(s) not in included]
        if omitted:
            deferred.append({'id': price['id'], 'name_en': name, 'source_types': omitted,
                             'reason': 'No matching native owned magazine feed evidence; keep SHOTS billing.'})
    return {'schema': 1, 'runtime_commit': 'dcd996daca2573443956c07252c55c2d86dd0320',
            'workbook_sha256': prices['workbook_sha256'], 'inputs_sha256': inputs,
            'by_type': dict(sorted(result.items())), 'deferred': deferred,
            'native_guard': {'weapon_flags': {'required': 128, 'excluded': [256, 512]},
                'evidence': 'domains/pelican.lua turretWeapon.weapon; runtime/pelicans.lua weapon_config'},
            'stock_formula': 'spares * actual_capacity + rounds + loaded_projectile_chamber_0_or_1',
            'fuel_formula': 'spares * actual_capacity + rounds',
            'chamber_evidence': ['runtime/pelican_weapon.lua:225-238,815-830,1686',
                'scripts/research_weapon_slot_capacity.py:90: magazine capacity; chambered reported separately'],
            'limits': ['Static type/feed evidence only; no real player ammo snapshot validation.',
                'Capacity/chamber and Weapon flags are read live, not taken from static catalogue.',
                'Do not divide observed magazine cartridges by projectile pellet count.',
                'Inventory-managed prices must not also bill their SHOTS increments.',
                'No authoritative reload phase; consistent rounds/working can still cross a reload boundary.']}


def inventory_prices(ammo, runtime=RUNTIME):
    """Root build contract: preserve each price, limit sources to proven magazines.

    Torcher is added separately by root with its reviewed fuel price. This function
    never writes the evidence JSON and never mutates the supplied price objects.
    """
    prices = {'ammo': list(ammo), 'workbook_sha256': hashlib.sha256(WORKBOOK.read_bytes()).hexdigest()}
    proven = build(prices, runtime)['by_type']
    result = []
    for price in ammo:
        sources = [normal(source) for source in price['source_types']
                   if normal(source) in proven and normal(source) != TORCHER]
        if sources:
            item = dict(price)
            item.update(source_types=sources, inventory_mode='magazine')
            result.append(item)
    return result


def heatsink_prices(rows, cents, runtime=RUNTIME):
    """Separate replacement price: column H, never the pulse/second price F."""
    players=json.loads((runtime/INPUTS[0]).read_text(encoding='utf8'))['weapons']
    by_name={w['name']:w for w in players}
    catalog=json.loads((ROOT/'docs/integration-catalogs.json').read_text(encoding='utf8'))
    out=[]
    for row in rows.values():
        name=row.get('P','')
        if not name.startswith('LAS-') or cents(row.get('H') or '0')<=0:
            continue
        weapon=by_name.get(name)
        if weapon:
            heat=[f for f in weapon['fields'] if f['semanticFieldId']=='heatsink.spare'
                and (f.get('backing') or {}).get('component')=='WeaponHeatComponentData']
            if not heat:continue
            sources=[normal(resource) for resource in weapon['resources']]
        elif name=='LAS-98 Laser Cannon':
            sources=[resource for resource,value in catalog['stat_sources'].items()
                if value.get('name')==name and value.get('kind')=='weapon']
        else:continue
        if not sources:raise ValueError('HEATSINK_NATIVE_RESOURCE_MISSING: '+name)
        out.append({'id':row['A']+'-HEATSINK','parent_price_id':row['A'],'row':row['row'],
            'name_zh':row['C'],'name_en':name,'unit_cents':cents(row['H']),
            'unit':'件','billing_kind':'heatsink','billing_label':'散热片',
            'inventory_mode':'heatsink','source_types':sources,
            'source':row.get('N',''),'price_column':'H'})
    return out

def backpack_fuel_prices(rows,cents,runtime=RUNTIME):
    row=rows['EQ-113']
    if row['P']!='B/FLAM-80 Cremator' or row['E']!='显示单位' or cents(row['F'])!=30:
        raise ValueError('CREMATOR_CONFIRMED_PRICE_CHANGED')
    sdk=json.loads((runtime/'sdk/BackpackAuthoringCapabilities.json').read_text(encoding='utf8'))
    pack=next(p for p in sdk['backpacks'] if p['name']=='B/FLAM-80 Cremator Backpack')
    if (pack['feeds']['supportWeapon']!=row['P'] or pack['feeds']['weaponOwnsMagazine']
        or pack['feeds']['inventorySlot']!='Backpack' or pack['ammo']['capacity']!=500
        or pack['ammo']['refillAmount']!=250):
        raise ValueError('CREMATOR_BACKPACK_NATIVE_UNIT_CHANGED')
    return [{'id':row['A'],'row':row['row'],'name_zh':row['C'],'name_en':row['P'],
        'unit_cents':cents(row['F']),'unit':row['E'],'inventory_mode':'fuel',
        'inventory_storage':'paired_deposit','billing_kind':'fuel','billing_label':'燃料',
        'source_types':['0736BEE2D6328726','78A8185F63A70795'],
        'backpack_type':'43EB1C3C1A1860E0','source':row.get('N','')}]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    prices = json.loads((ROOT / 'dist/confirmed-prices.json').read_text(encoding='utf8'))
    result = build(prices)
    text = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.check:
        if OUTPUT.read_text(encoding='utf8') != text:
            raise ValueError('MAGAZINE_PRICE_EVIDENCE_OUTDATED')
    else:
        OUTPUT.write_text(text, encoding='utf8')
    print(json.dumps({'native_magazine_resources': len(result['by_type']),
                      'priced_items': len({v['id'] for v in result['by_type'].values()}),
                      'deferred_items': len(result['deferred']), 'check': args.check}))


if __name__ == '__main__':
    main()
