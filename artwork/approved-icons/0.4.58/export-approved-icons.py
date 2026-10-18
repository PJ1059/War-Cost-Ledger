"""Export the four finally approved RGB originals to transparent review assets.

No image generation, tracing, anatomical edit, palette replacement or deployment.
The top row of the approved three-skull original supplies M08/M09/M10. The
approved gold/white-swap tank supplies M12. Every export keeps original raster
resolution and is centred on the same square canvas without resampling.
"""
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont
import hashlib
import json
import shutil

HERE = Path(__file__).resolve().parent
SOURCE_MANIFEST = HERE / 'approved-sources-manifest.original.json'
CANVAS = (1536, 1536)
BLACK_CUTOFF = 20
EDGE_RADIUS = 2
ASSETS = [
    {'id': 'M08', 'name': '民主之星', 'source_index': 0,
     'crop': [40, 25, 570, 642], 'file': 'M08-democracy_star.png',
     'semantic_holes': [[267, 438], [346, 438], [307, 466]],
     'role': 'Approved original upper-left skull, tier I. No lower thumbnail or Roman numeral.'},
    {'id': 'M09', 'name': '超级民主之星', 'source_index': 0,
     'crop': [590, 25, 1120, 642], 'file': 'M09-super_democracy_star.png',
     'semantic_holes': [[821, 431], [901, 432], [863, 460]],
     'role': 'Approved original upper-middle skull, tier II. No lower thumbnail or Roman numeral.'},
    {'id': 'M10', 'name': '超级无上民主之星', 'source_index': 0,
     'crop': [1120, 25, 1765, 642], 'file': 'M10-supreme_democracy_star.png',
     'semantic_holes': [[1396, 435], [1473, 435], [1433, 464]],
     'role': 'Approved original upper-right winged skull, tier III. No lower thumbnail or Roman numeral.'},
    {'id': 'M12', 'name': '摧毁暴政减速带', 'source_index': 1,
     'crop': [0, 0, 1330, 1182], 'file': 'M12-tyranny_speed_bump.png',
     'semantic_holes': [[665, 337], [665, 558], [665, 260]],
     'role': 'Approved B tank gold/white swap: original white hull/top plates/shoulders, gold tracks/barrel, original frame/laurels.'},
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preserve_originals():
    data = json.loads(SOURCE_MANIFEST.read_text(encoding='utf8'))
    paths = []
    target = HERE / 'originals'
    target.mkdir(parents=True, exist_ok=True)
    for row in data['items']:
        source = Path(row['path'])
        if sha(source) != row['sha256']:
            raise ValueError('Approved original SHA mismatch: ' + str(source))
        destination = target / source.name
        if destination.exists() and sha(destination) != row['sha256']:
            raise ValueError('Backup identity conflict: ' + str(destination))
        shutil.copy2(source, destination)
        if sha(destination) != row['sha256']:
            raise ValueError('Original byte preservation failed')
        with Image.open(destination) as image:
            if list(image.size) != row['dimensions'] or image.mode != row['mode']:
                raise ValueError('Approved image dimensions/mode mismatch')
        paths.append(destination)
    shutil.copy2(SOURCE_MANIFEST, HERE / 'approved-sources-manifest.original.json')
    return data, paths


def export(spec, source, source_record):
    rgb = Image.open(source).convert('RGB')
    crop = rgb.crop(spec['crop'])
    strength = ImageChops.lighter(ImageChops.lighter(crop.getchannel('R'), crop.getchannel('G')), crop.getchannel('B'))
    support = strength.point(lambda value: 255 if value > BLACK_CUTOFF else 0)
    # Eroding only identifies a narrow existing antialias band. It never alters
    # silhouette support or fills holes. Opaque interiors retain exact source RGB.
    interior = support.filter(ImageFilter.MinFilter(EDGE_RADIUS * 2 + 1))
    raw = bytearray()
    count = {'transparent_pixels': 0, 'opaque_original_rgb_pixels': 0,
             'edge_black_matte_corrected_pixels': 0}
    for pixel, covered, inside in zip(crop.get_flattened_data(), support.get_flattened_data(), interior.get_flattened_data()):
        if not covered:
            raw.extend((0, 0, 0, 0))
            count['transparent_pixels'] += 1
        elif inside or max(pixel) == 255:
            raw.extend((*pixel, 255))
            count['opaque_original_rgb_pixels'] += 1
        else:
            # On the black-composited antialias boundary, max(R,G,B) estimates
            # coverage against a bright white/gold stroke. Unpremultiply only
            # this <=2px boundary, removing black halos without recolouring any
            # opaque interior. Gold and white remain the approved source hues.
            alpha = max(pixel)
            unmatte = tuple(min(255, round(channel * 255 / alpha)) for channel in pixel)
            raw.extend((*unmatte, alpha))
            count['edge_black_matte_corrected_pixels'] += 1
    transparent = Image.frombytes('RGBA', crop.size, bytes(raw))
    local_bbox = transparent.getchannel('A').getbbox()
    if not local_bbox:
        raise ValueError('Empty approved artwork: ' + spec['id'])
    tight = transparent.crop(local_bbox)
    if max(tight.size) > min(CANVAS):
        raise ValueError('Approved artwork does not fit unscaled canvas')
    origin = ((CANVAS[0] - tight.width) // 2, (CANVAS[1] - tight.height) // 2)
    canvas = Image.new('RGBA', CANVAS, (0, 0, 0, 0))
    canvas.paste(tight, origin)  # Direct RGBA copy, no alpha multiplication.
    target = HERE / spec['file']
    canvas.save(target, optimize=True)
    # Keep the alpha mask itself for reproducible auditing of transparent holes.
    mask_target = HERE / 'masks' / (spec['id'] + '-alpha.png')
    mask_target.parent.mkdir(parents=True, exist_ok=True)
    canvas.getchannel('A').save(mask_target, optimize=True)
    source_bbox = [spec['crop'][0] + local_bbox[0], spec['crop'][1] + local_bbox[1],
                   spec['crop'][0] + local_bbox[2], spec['crop'][1] + local_bbox[3]]
    hole_checks = []
    for x, y in spec['semantic_holes']:
        cx, cy = origin[0] + x - source_bbox[0], origin[1] + y - source_bbox[1]
        alpha = canvas.getpixel((cx, cy))[3]
        hole_checks.append({'source_xy': [x, y], 'output_xy': [cx, cy], 'alpha': alpha})
        if alpha:
            raise ValueError('Semantic negative space became opaque: ' + spec['id'] + str((x, y)))
    return {**spec, 'source_original_path': source_record['path'],
        'preserved_original': 'originals/' + source.name, 'source_sha256': sha(source),
        'source_dimensions': list(rgb.size), 'source_selected_region': spec['crop'],
        'source_visible_bbox': source_bbox, 'crop_local_visible_bbox': list(local_bbox),
        'canvas': list(CANVAS), 'unscaled_paste_origin': list(origin),
        'output_alpha_bbox': list(canvas.getchannel('A').getbbox()),
        'output_alpha_bbox_threshold24': list(canvas.getchannel('A').point(lambda a: 255 if a >= 24 else 0).getbbox()),
        'visible_size': list(tight.size), 'visible_width_height_ratio': tight.width / tight.height,
        'output_sha256': sha(target), 'mask_file': str(mask_target.relative_to(HERE)),
        'mask_sha256': sha(mask_target), 'black_cutoff': BLACK_CUTOFF,
        'edge_unmatte_radius': EDGE_RADIUS, 'resampled': False,
        'redrawn': False, 'palette_replaced': False, 'counts': count,
        'semantic_negative_space_checks': hole_checks}


def contacts(items):
    backgrounds = [('dark', '#111414'), ('light', '#deddd5'), ('game-gray', '#414341')]
    font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 20)
    small = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 14)
    combined = Image.new('RGB', (1536, 3 * 420), '#111414')
    for index, (label, colour) in enumerate(backgrounds):
        row = Image.new('RGB', (1536, 420), colour)
        draw = ImageDraw.Draw(row)
        ink = '#282a27' if label == 'light' else '#f2f0e6'
        for column, item in enumerate(items):
            x = column * 384
            image = Image.open(HERE / item['file']).convert('RGBA').crop(item['output_alpha_bbox'])
            image.thumbnail((335, 285), Image.Resampling.LANCZOS)
            row.paste(image, (x + (384 - image.width) // 2, 18), image)
            draw.text((x + 20, 315), item['id'] + ' ' + item['name'], font=font, fill=ink)
            tiny = Image.open(HERE / item['file']).convert('RGBA').crop(item['output_alpha_bbox'])
            tiny.thumbnail((42, 42), Image.Resampling.LANCZOS)
            row.paste(tiny, (x + 22, 358), tiny)
            draw.text((x + 80, 368), '42px / ' + label, font=small, fill=ink)
        row.save(HERE / ('contact-' + label + '.png'))
        combined.paste(row, (0, index * 420))
    combined.save(HERE / 'approved-four-contact-sheet.png')


def main():
    sources, paths = preserve_originals()
    records = [export(spec, paths[spec['source_index']], sources['items'][spec['source_index']]) for spec in ASSETS]
    # No reads/writes to runtime, shared catalogues, build tools or deployment.
    payload = {'schema': 1, 'version': '0.4.58', 'status': 'approved_originals_exported_not_integrated',
        'process': 'Pillow deterministic crop/black-matte transparency/unscaled square placement',
        'script_sha256': sha(Path(__file__)), 'original_manifest_sha256': sha(SOURCE_MANIFEST),
        'source_identity': 'Only the two finally approved exact-SHA originals; no 27ab variant or other drafts.',
        'canvas_policy': '1536 square, original foreground pixels unscaled, fit subsequent HUD rendering by visible alpha bbox.',
        'mask_policy': 'max RGB <=20 transparent everywhere, including semantic eye/nose/muzzle/structure holes; keep source RGB at opaque interiors; black-unmatte only <=2px support boundary.',
        'background_filled': False, 'generated': False, 'runtime_files_written': False, 'items': records}
    (HERE / 'export-manifest.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    catalog = {'schema': 1, 'version': '0.4.58', 'status': 'approved_originals_exported', 'items': []}
    for record in records:
        source_record = sources['items'][record['source_index']]
        key = record['file'][4:-4]
        catalog['items'].append({'id': record['id'], 'key': key, 'name': record['name'],
            'kind': 'medal', 'status': 'approved', 'file': record['file'],
            'sha256': record['output_sha256'], 'width': CANVAS[0], 'height': CANVAS[1],
            'alpha_bbox': record['output_alpha_bbox_threshold24'],
            'body_ratio': record['visible_width_height_ratio'],
            'source_sheet_hash': record['source_sha256'],
            'source_sheet': record['preserved_original'], 'crop': record['source_selected_region'],
            'source_visible_bbox': record['source_visible_bbox'],
            'LibraryID': source_record.get('library_file_id'),
            'method': 'deterministic_approved_original_black_matte_export_no_generation',
            'source_manifest': 'export-manifest.json'})
    (HERE / 'catalog.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    contacts(records)
    print(json.dumps({'status': 'exported', 'output': str(HERE), 'items': [
        {'id': r['id'], 'bbox': r['output_alpha_bbox'], 'sha256': r['output_sha256']} for r in records]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
