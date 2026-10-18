"""Assemble display-only English names from the project's reviewed catalogs.

The handwritten exact strings/patterns live in docs/localization-en.json. This
tool adds existing bilingual identities, never guesses from a model prefix and
never changes a saved record. Run this tool after updating a source catalog.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
HAN = re.compile(r'[\u3400-\u9fff]')
INPUTS = (
    'docs/integration-catalogs.json',
    'docs/hellpod-kill-sources.json',
    'docs/vehicle-body-kill-sources.json',
    'docs/damage-source-catalog.json',
    'docs/enemy-catalog/units.json',
)
# The active exact-hash integration roster wins over an older unbound roster.
# These are documented conflicts, not silently selected arbitrary synonyms.
RESOLVED = {
    '霸王虫': ('Hive Lord', 'Current exact-hash enemy roster; Hivelord is an older source-label spelling.'),
    '特攻奇袭者': ('Jet Brigade Raider', 'Current exact-hash entity 856E9710E45E760F; unbound roster still says Assault Raider.'),
    'M-102 快速侦查载具': ('M-102 Fast Recon Vehicle', 'Current exact-hash source CC21C7FFD3EBEFB9; Gunner FRV is a catalog role alias.'),
}


def bilingual_rows(value):
    if isinstance(value, dict):
        zh = value.get('name_zh')
        en = value.get('name_en') or value.get('name')
        if isinstance(zh, str) and isinstance(en, str) and HAN.search(zh) and not HAN.search(en) and en.strip():
            yield zh, en
        for child in value.values():
            yield from bilingual_rows(child)
    elif isinstance(value, list):
        for child in value:
            yield from bilingual_rows(child)


def workbook_pairs(path):
    ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with ZipFile(path) as archive:
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            strings = [''.join(row.itertext()) for row in ET.fromstring(archive.read('xl/sharedStrings.xml'))]
        for index in (2, 3):
            sheet = ET.fromstring(archive.read(f'xl/worksheets/sheet{index}.xml'))
            for row in sheet.findall('.//s:row', ns):
                cells = {}
                for cell in row.findall('s:c', ns):
                    cached = cell.find('s:v', ns)
                    text = cached.text if cached is not None else ''
                    if cell.get('t') == 's':
                        text = strings[int(text)]
                    elif cell.get('t') == 'inlineStr':
                        text = ''.join(cell.find('s:is', ns).itertext())
                    cells[re.sub(r'\d+', '', cell.get('r'))] = text
                zh, en = cells.get('C'), cells.get('P')
                if isinstance(zh, str) and isinstance(en, str) and HAN.search(zh) and en and not HAN.search(en):
                    yield zh, en


def build_catalog(root=ROOT, prices=None):
    root = Path(root)
    document = json.loads((root / 'docs/localization-en.json').read_text(encoding='utf8'))
    catalog = {key: dict(document.get(key, {})) for key in ('exact', 'fragments')}
    catalog['patterns'] = list(document.get('patterns', []))
    candidates, inputs = {}, {}

    def add(zh, en, origin):
        candidates.setdefault(zh, {}).setdefault(en, set()).add(origin)

    for filename in INPUTS:
        raw = (root / filename).read_bytes()
        inputs[filename] = hashlib.sha256(raw).hexdigest()
        for zh, en in bilingual_rows(json.loads(raw)):
            add(zh, en, filename)
    if prices is not None:
        for zh, en in bilingual_rows(prices):
            add(zh, en, 'confirmed_prices')
    workbook = root / 'pricing/HD2-军需价格表-v0.2.xlsx'
    if not workbook.is_file():
        workbook = root.parent / 'pricing/HD2-军需价格表-v0.2.xlsx'
    if workbook.is_file():
        inputs['pricing/HD2-军需价格表-v0.2.xlsx'] = hashlib.sha256(workbook.read_bytes()).hexdigest()
        for zh, en in workbook_pairs(workbook):
            add(zh, en, 'confirmed_price_workbook')

    conflicts = []
    for zh, variants in sorted(candidates.items()):
        if len(variants) == 1:
            en = next(iter(variants))
        else:
            if zh not in RESOLVED:
                raise ValueError(f'Unreviewed bilingual name conflict: {zh}: {sorted(variants)}')
            en, basis = RESOLVED[zh]
            assert en in variants, (zh, en)
            conflicts.append({'zh': zh, 'variants': {key: sorted(value) for key, value in sorted(variants.items())},
                              'selected': en, 'basis': basis})
        catalog['exact'][zh] = en
        catalog['fragments'][zh] = en

    # Specific enemy-ribbon conditions come from the approved English unit keys.
    battle = (root / 'src/battle-hud.lua').read_text(encoding='utf8')
    conditions = 0
    for en, zh, sentence in re.findall(r"unit_key = '([^']+)', unit = '([^']+)', condition = '([^']+)'", battle):
        assert sentence == f'击杀1个{zh}。'
        catalog['exact'][sentence] = f'Kill 1 {en}.'
        conditions += 1
    catalog['exact']['关闭面板'] = 'Close'
    catalog['exact']['虫洞（爆炸关联推测）'] = 'Bug Hole'
    catalog['fragments']['虫洞（爆炸关联推测）'] = 'Bug Hole'
    catalog['schema_version'] = 1
    catalog['language'] = 'en'
    catalog['policy'] = 'Display only; do not translate player names, identifiers, saved keys or source records.'
    catalog['inputs'] = inputs
    catalog['conflicts'] = conflicts
    catalog['counts'] = {'bilingual_names': len(candidates), 'unit_conditions': conditions,
                         'exact': len(catalog['exact']), 'fragments': len(catalog['fragments']),
                         'patterns': len(catalog['patterns'])}
    return catalog


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/localization-en.json')
    args = parser.parse_args()
    result = build_catalog()
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(result['counts']))
