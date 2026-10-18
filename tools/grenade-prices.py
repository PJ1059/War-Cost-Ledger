"""Join the confirmed throwable prices to Runtime's pinned native resource names."""
from __future__ import annotations
import hashlib
import os
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path(os.environ.get('HD2_RUNTIME_SOURCE', 'external/HD2Runtime'))
DOMAIN_SHA = '413f61776e94aea78917a20ebe76d7558090346b3af60a9b6329be109c2079ad'


def build(rows, cents, runtime=RUNTIME):
    raw = (runtime / 'domains/player_equipment.lua').read_bytes()
    if hashlib.sha256(raw).hexdigest() != DOMAIN_SHA:
        raise ValueError('GRENADE_EQUIPMENT_DOMAIN_CHANGED')
    native = {}
    for resource, name in re.findall(r'\["([0-9A-F]{16})"\]=\{\["name"\]="([^"]+)",\["kind"\]="throwable"', raw.decode('utf8')):
        if name in native:
            raise ValueError('GRENADE_AMBIGUOUS_NATIVE_NAME')
        native[name] = resource
    prices, deferred = [], []
    for row in rows.values():
        if row.get('B') != '投掷物':
            continue
        name = row['P']
        if name not in native:
            raise ValueError('GRENADE_UNMAPPED_PRICE: ' + name)
        if row['G'] != '消耗时计费':
            deferred.append({'id': row['A'], 'name_en': name, 'reason': row['M']})
            continue
        if row['E'] != '枚' or cents(row['F']) <= 0:
            raise ValueError('GRENADE_UNIT_POLICY_CHANGED')
        prices.append({'id': row['A'], 'row': row['row'], 'name_zh': row['C'], 'name_en': name,
                       'unit_cents': cents(row['F']), 'unit': row['E'], 'policy': row['M'],
                       'source_types': [native[name]], 'source': row['N']})
    if len(prices) != 22 or len(deferred) != 1 or deferred[0]['id'] != 'EQ-126':
        raise ValueError('GRENADE_CATALOG_COVERAGE_CHANGED')
    return {'revision': 'native_throwable_inventory_v1', 'domain_sha256': DOMAIN_SHA,
            'runtime_commit': 'dcd996daca2573443956c07252c55c2d86dd0320',
            'read_contract': 'inventory.throwable +0x28; inventory.counts +0x58; count stride8 +0',
            'prices': prices, 'deferred': deferred}


if __name__ == '__main__':
    from build import workbook_rows, cents
    output = build(workbook_rows((2,))[2], cents)
    path = ROOT / 'docs/grenade-pricing-evidence.json'
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print('22 native disposable throwable prices; recoverable knife deferred')
