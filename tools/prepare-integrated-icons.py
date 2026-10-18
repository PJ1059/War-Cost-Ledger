"""Bind approved PNGs to stable HUD identities; never redraw source artwork."""
from pathlib import Path
import hashlib
import json
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artwork/integration-0.4.58'
APPROVED = ROOT / 'artwork/approved-icons/0.4.58'
APPROVED_IDS = ('M08', 'M09', 'M10', 'M12')
EXPECTED_SHEETS = {
    'M08': '54fdae1296542575a580329e5dde3d5f0b748ca0f4e47ca76ec292084d339842',
    'M09': '54fdae1296542575a580329e5dde3d5f0b748ca0f4e47ca76ec292084d339842',
    'M10': '54fdae1296542575a580329e5dde3d5f0b748ca0f4e47ca76ec292084d339842',
    'M12': 'ee653579dd0d82e525231d5dd362e840ecb560d5f26799e48a4a7d36db0bd5da',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bitmap(identity, key, name, kind, source, **extra):
    image = Image.open(source).convert('RGBA')
    bbox = image.getchannel('A').point(lambda v: 255 if v >= 24 else 0).getbbox()
    if not bbox:
        raise ValueError('Empty integration artwork: ' + str(source))
    return {'id': identity, 'key': key, 'name': name, 'kind': kind,
            'source_file': source.relative_to(ROOT).as_posix(), 'sha256': sha(source),
            'width': image.width, 'height': image.height, 'alpha_bbox': list(bbox),
            'body_ratio': (bbox[2] - bbox[0]) / (bbox[3] - bbox[1]),
            'accent': '#C7B980', 'symbol_width': .34, 'display_scale': 1,
            'artwork_form': 'approved_raster_bitmap', 'review_fingerprint': sha(source), **extra}


def build():
    approved = json.loads((APPROVED / 'catalog.json').read_text(encoding='utf8'))
    approved_items = {item['id']: item for item in approved['items']}
    assert set(approved_items) == set(APPROVED_IDS)
    items = []
    for identity in APPROVED_IDS:
        row = approved_items[identity]
        assert row['source_sheet_hash'] == EXPECTED_SHEETS[identity]
        assert sha(APPROVED / row['source_sheet']) == EXPECTED_SHEETS[identity]
        source = APPROVED / row['file']
        assert sha(source) == row['sha256']
        items.append(bitmap(identity, row['key'], row['name'], 'medal', source,
            accent='#FEE447', LibraryID=row['LibraryID'], source_sheet_hash=row['source_sheet_hash'],
            source_sheet='artwork/approved-icons/0.4.58/' + row['source_sheet'],
            source_crop=row['crop'], source_generation=False,
            approval='exact_original_four_approved_by_user'))
    v5 = ROOT / 'artwork/review-0.4.57-ribbons-v5'
    # Compile the accepted original once. The review-only PNG had already
    # resized it and hard-thresholded alpha, losing the fine scissors edges.
    items.append(bitmap('M11', 'level_not_problem', '等级不是问题', 'medal',
                        v5 / 'medals/other/level-not-problem-scissors.png',
                        source_preparation='review_two_ink_preserve_alpha',
                        texture_format='R8G8B8A8_UNORM'))
    items.append(bitmap('R05', 'melee', '近战杀敌', 'ribbon', v5 / 'compiled/ribbon-melee-elbow.png',
                        symbol_width=.42))
    units = json.loads((ROOT / 'docs/unit-ribbon-icons.json').read_text(encoding='utf8'))
    assert len(units['items']) == 24
    for row in units['items']:
        source = (ROOT / 'docs' / row['file']).resolve()
        items.append(bitmap(row['id'], row['key'], row['name'], 'ribbon', source,
                            unit=row['unit'], unit_key=row['enemy_key'], source_generation=False))
    assert len(items) == 30 and len({r['id'] for r in items}) == 30
    result = {'schema': 1, 'version': '0.4.58', 'revision': 'approved-icons-and-unit-ribbons-058',
              'approval': 'four_exact_final_originals_plus_user_approved_previous_outcomes',
              'approved_original_ids': list(APPROVED_IDS),
              'replacements': ['R05', 'M08', 'M09', 'M10', 'M11'],
              'additions': ['M12'] + [r['id'] for r in units['items']], 'items': items}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'catalog.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print('Prepared 5 image replacements and 25 additions from approved existing PNGs.')
    return result


if __name__ == '__main__':
    build()
