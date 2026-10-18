"""Compile approved, read-only HUD artwork into HD2Runtime icon families.

Uses the already installed HD2Runtime 0.30.3 SDK. This is build-time asset
conversion, not raster artwork editing: source PNGs are never overwritten.
White art is the R mask, category colour the G mask, and empty space RGB zero.
The Runtime icon shader uses mask strength rather than texture alpha.
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'artwork/icon-drafts/v18'
ACHIEVEMENTS = ROOT / 'artwork/achievement-icons/v1'
COMBAT = ROOT / 'artwork/combat-icons/v2'
INTEGRATED = ROOT / 'artwork/integration-0.4.58'
APPROVED = ROOT / 'artwork/approved-icons/0.4.58'
METRICS = ROOT / 'artwork/metric-icon-drafts/v1'
INDICATORS = METRICS / 'native-kd-indicators'
SKULL = ROOT / 'artwork/icon-drafts/v17/references/native-round-eye-skull'
OUT = ROOT / 'build/icons'
SDK = Path(os.environ.get('HD2_RUNTIME_SDK', str(Path(os.environ.get('LOCALAPPDATA', '')) /
    'Temp/hd2-integration-research/HD2Runtime/SkyeShade-HD2Runtime-dcd996d/sdk')))
IDS = tuple('R%02d' % i for i in range(1, 11)) + tuple('H%02d' % i for i in range(1, 6)) + tuple('M%02d' % i for i in range(1, 7))
EXTRA_IDS = ('R11', 'M07', 'M08', 'M09', 'M10', 'M11')
COMBAT_ADDITIONS = ('R12',)
OVERRIDE_IDS = ('R05',)
APPROVED_IDS = ('M08', 'M09', 'M10', 'M12')
INTEGRATION_OVERRIDES = ('R05', 'M08', 'M09', 'M10', 'M11')
INTEGRATION_ADDITIONS = ('M12',) + tuple('G%02d' % i for i in range(1, 7)) + tuple('T%02d' % i for i in range(1, 19))
METRIC_IDS = ('U01', 'U02', 'U03', 'U04')
INDICATOR_IDS = ('I01', 'I02')
WHITE = (255, 249, 237)


def _sdk_module(name):
    path = SDK / 'tools' / (name + '.py')
    if not path.is_file():
        raise FileNotFoundError('HD2Runtime SDK module is missing: ' + str(path))
    spec = importlib.util.spec_from_file_location('_ledger_sdk_' + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _rgb(value):
    return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))


def _fit_image(image):
    """Pack a reviewed display box proportionally, without changing its shape."""
    factor = 248 / max(image.size)
    size = tuple(max(1, round(n * factor)) for n in image.size)
    content = image.resize(size, Image.Resampling.LANCZOS)
    fitted = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
    origin = ((256 - size[0]) // 2, (256 - size[1]) // 2)
    fitted.paste(content, origin)
    return fitted, [origin[0], origin[1], origin[0] + size[0], origin[1] + size[1]]


def _rgba(raw):
    with Image.open(io.BytesIO(raw)) as image:
        return image.convert('RGBA')


def _fit_source(source, expected):
    """Use its reviewed alpha bounds, fitting proportionally into a 256 quad."""
    raw = source.read_bytes()
    if _sha(raw) != expected['sha256']:
        raise ValueError('Artwork identity changed: ' + str(source))
    rgba = _rgba(raw)
    # Same alpha >=24 visibility boundary used by prepare-icon-review.py.
    bbox = rgba.getchannel('A').point(lambda value: 255 if value >= 24 else 0).getbbox()
    if bbox is None or list(bbox) != expected['alpha_bbox']:
        raise ValueError('Artwork alpha bounds differ from its review catalogue: ' + str(source))
    cropped = rgba.crop(bbox)
    if expected.get('source_preparation') == 'review_two_ink_preserve_alpha':
        # Same two-ink classification as the accepted review, directly from
        # the full-resolution source. Keep coverage/antialiasing, not its
        # review PNG's 0/255 alpha threshold or an intermediate resize.
        pixels = bytearray()
        for r, g, b, alpha in cropped.get_flattened_data():
            ink = WHITE if b >= r * .8 else _rgb(expected['accent'])
            pixels.extend((*ink, alpha))
        cropped = Image.frombytes('RGBA', cropped.size, bytes(pixels))
    fitted, packed = _fit_image(cropped)
    return raw, fitted, bbox, packed


def _package_source(source_file):
    """Retain distinct award, metric-sheet and native-reference directories."""
    relative = Path(source_file).relative_to('artwork').as_posix()
    return 'Source/Artwork/' + relative


def _native_skull():
    metadata = json.loads((SKULL / 'source.json').read_text(encoding='utf8'))
    raw = (SKULL / 'HD2-native-round-eye-skull.png').read_bytes()
    svg = (SKULL / 'HD2-native-round-eye-skull.svg').read_bytes()
    if (_sha(raw) != metadata['png_sha256'] or
            _sha(svg) != 'c70ee4d8e72c8453e7d9afefbe88a7514e14d0a2a1df9efd3f3ed00626190e1a'):
        raise ValueError('Reviewed native round-eye skull identity changed')
    image = _rgba(raw)
    # This PNG is the exact game Path rendered with a margin. The web SVG uses
    # its tight viewBox; remove only that rendering margin for equivalent fit.
    bbox = image.getchannel('A').getbbox()
    image = image.crop(bbox)
    image.putalpha(image.getchannel('A').point(lambda value: round(value * .88)))
    return raw, image, list(bbox)


def _kd_image(sheet_crop, skull):
    """Build the exact approved metricArtwork CSS layers at source resolution.

    This is an asset-packaging composition, not a new drawing: retain the
    original slash and dog tag pixels, then place the original native skull.
    """
    width, height = sheet_crop.size
    result = Image.new('RGBA', sheet_crop.size, (0, 0, 0, 0))
    for kind in ('slash', 'tag'):
        clip = Image.new('L', sheet_crop.size, 0)
        draw = ImageDraw.Draw(clip)
        if kind == 'slash':
            draw.polygon([(width * .85, 0), (width * .98, 0),
                          (width * .26, height), (width * .13, height)], fill=255)
        else:
            draw.rectangle((width * .56, height * .33, width, height), fill=255)
        layer = sheet_crop.copy()
        layer.putalpha(ImageChops.multiply(layer.getchannel('A'), clip))
        result.alpha_composite(layer)
    # .native-skull { object-fit: contain } inside width50% / height58%.
    box_width, box_height = width * .5, height * .58
    scale = min(box_width / skull.width, box_height / skull.height)
    size = (round(skull.width * scale), round(skull.height * scale))
    placed = skull.resize(size, Image.Resampling.LANCZOS)
    result.alpha_composite(placed, (round((box_width - size[0]) / 2),
                                   round((box_height - size[1]) / 2)))
    return result


def _mask_png(image, accent, image_sdk):
    # SDK's least-squares mask conversion normally puts category in R and white
    # in G. Supply this picture's own category colour instead of the SDK's red,
    # then swap the channels to the ledger's explicit white-R/category-G contract.
    rgba = image.tobytes()
    prepared = image_sdk.icon_masks(rgba, dark=(0, 0, 0), red=_rgb(accent), white=WHITE)
    mask = bytearray(prepared)
    mask[0::4], mask[1::4] = prepared[1::4], prepared[0::4]
    mask[2::4] = bytes(len(mask) // 4)
    mask[3::4] = bytes([255]) * (len(mask) // 4)
    png = image_sdk.write_png(256, 256, bytes(mask))
    # Transparent source pixels must stay black in the shader's mask convention.
    empty = sum(1 for i in range(0, len(mask), 4) if mask[i] == mask[i + 1] == 0)
    return png, {'mask_white_channel': 'R', 'mask_accent_channel': 'G',
        'empty_pixels': empty, 'white_mask_sum': sum(mask[0::4]), 'accent_mask_sum': sum(mask[1::4])}


def _lossless_icon_texture(png, image_sdk):
    """Keep fine two-channel silhouettes exact in the native RGBA8 DDS form.

    HD2's HUD also uses DXGI 28 (SDK hd2_hud_icons.FORMATS). BC1's two
    endpoints cannot preserve white-mask/accent-mask/empty pixels in one
    block, particularly at the 64px and 32px mips of the scissors medal.
    """
    image = _rgba(png)
    assert image.size == (256, 256)
    mips = []
    while True:
        mips.append(image.tobytes())
        if image.size == (1, 1):
            break
        image = image.resize((image.width // 2, image.height // 2), Image.Resampling.BOX)
    return image_sdk.texture_main(256, 256, len(mips), dxgi=28), b''.join(mips)


def _svg_points(path):
    """The reviewed frame uses only absolute M/H/V/Z; refuse other geometry."""
    tokens = re.findall(r'[A-Za-z]|-?\d+(?:\.\d+)?', path)
    points, cursor, command, index = [], (0.0, 0.0), None, 0
    while index < len(tokens):
        if tokens[index].isalpha():
            command = tokens[index]
            index += 1
            if command == 'Z':
                if not points:
                    raise ValueError('Empty frame path')
                points.append(points[0])
                continue
            if command not in ('M', 'H', 'V', 'L'):
                raise ValueError('Unsupported frame SVG command: ' + command)
        if command in ('M', 'L'):
            if index + 1 >= len(tokens):
                raise ValueError('Incomplete frame SVG coordinate')
            cursor = (float(tokens[index]), float(tokens[index + 1]))
            index += 2
            if command == 'M' and points:
                yield points
                points = []
            points.append(cursor)
            command = 'L'
        elif command in ('H', 'V'):
            value = float(tokens[index])
            index += 1
            cursor = (value, cursor[1]) if command == 'H' else (cursor[0], value)
            points.append(cursor)
        elif command == 'Z':
            continue
        else:
            raise ValueError('Unsupported frame SVG path')
    if points:
        yield points


def _frame_image():
    raw = (ART / 'ribbon-frame.svg').read_bytes()
    tree = ET.fromstring(raw)
    generation = json.loads((ART / 'generation.json').read_text(encoding='utf8'))
    if _sha(raw) != generation['style']['frame_sha256']:
        raise ValueError('Reviewed frame identity changed')
    image = Image.new('RGBA', (768, 256), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    scale = 768 / 180
    for path in tree.findall('{http://www.w3.org/2000/svg}path'):
        colour = _rgb(path.attrib['stroke']) + (255,)
        width = max(1, round(float(path.attrib['stroke-width']) * scale))
        for points in _svg_points(path.attrib['d']):
            draw.line([(round(x * scale), round(y * scale)) for x, y in points], fill=colour, width=width)
    # The texture quad is square, the draw box is 3:1; this restores the exact
    # SVG proportions rather than letterboxing the frame into a square bitmap.
    return raw, image.resize((256, 256), Image.Resampling.LANCZOS)


def _indicator_images():
    """Rasterize the game's unchanged 8x4 XAML geometry; no bitmap editing."""
    raw = (INDICATORS / 'arrows.xaml').read_bytes()
    metadata = json.loads((INDICATORS / 'source.json').read_text(encoding='utf8'))
    if _sha(raw) != metadata['fragment_sha256'] or metadata['viewbox'] != [0, 0, 8, 4]:
        raise ValueError('Native KD arrow source changed')
    tree = ET.fromstring(raw)
    paths = {node.attrib['{http://schemas.microsoft.com/winfx/2006/xaml}Key']: node.text
             for node in tree.findall('{http://schemas.microsoft.com/winfx/2006/xaml/presentation}Geometry')}
    expected = {'I01': ('Geometry.UpArrow', 'M0,4L4,0 8,4'),
                'I02': ('Geometry.DownArrow', 'M0,0 L4,4 8,0')}
    for identity in INDICATOR_IDS:
        key, path = expected[identity]
        if paths.get(key) != path or metadata['geometry'][identity] != {'key': key, 'path': path}:
            raise ValueError('Native KD arrow geometry changed')
        polygons = list(_svg_points(path))
        if len(polygons) != 1 or len(polygons[0]) != 3:
            raise ValueError('Native KD arrow must retain its three original vertices')
        vector = Image.new('RGBA', (1024, 512), (0, 0, 0, 0))
        draw = ImageDraw.Draw(vector)
        draw.polygon([(x * 1023 / 8, y * 511 / 4) for x, y in polygons[0]], fill=WHITE+(255,))
        fitted, packed = _fit_image(vector)
        yield identity, raw, fitted, packed, key, path


def _record_lua(entries):
    lines = ['-- Ledger image compilation record; HD2Runtime reads this once per handle.',
        'return {format=1,images={']
    for item in entries:
        fields = {'source': item['source_file'], 'sha256': item['source_sha256'],
            'prepared': item.get('prepared', 'reviewed art derived to white-R/category-G icon masks'),
            'build': item.get('build', 'compiled from approved v18 awards and metric/native reference artwork'),
            'resource': item['resource']}
        body = ','.join(k + '=' + json.dumps(v, ensure_ascii=False) for k, v in fields.items())
        lines.append('[' + json.dumps(item['image_id']) + ']={' + body + '},')
    return ('\n'.join(lines) + '\n}}\n').encode('utf8')


def game_icon_resources(resource):
    """Return {'resources', 'manifest', 'files'} for the existing build merger.

    resources: SDK archive input {(type hash, name hash): (main bytes, GPU bytes)}.
    files: editable source references and derived masks, outside deployed Addon/.
    Frame draw uses its three-to-one box; symbol draw uses a square quad and its
    reviewed symbol_width/display_scale. No original artwork is overwritten.
    """
    if not re.fullmatch(r'mods/[a-z0-9_]+/[a-z0-9_]+', resource):
        raise ValueError('Unexpected mod resource identity')
    image_sdk = _sdk_module('hd2_image')
    archive_sdk = _sdk_module('hd2_archive')
    catalog_raw = (ART / 'catalog.json').read_bytes()
    catalog = json.loads(catalog_raw)
    items = {item['id']: item for item in catalog['items']}
    integration_raw = (INTEGRATED / 'catalog.json').read_bytes()
    integration = json.loads(integration_raw)
    integrated = {item['id']: item for item in integration['items']}
    if set(integrated) != set(INTEGRATION_OVERRIDES) | set(INTEGRATION_ADDITIONS):
        raise ValueError('Unexpected integrated artwork identities')
    combat_items = {item['id']: item for item in json.loads((COMBAT / 'catalog.json').read_bytes())['items']}
    if set(combat_items) != set(COMBAT_ADDITIONS) | set(OVERRIDE_IDS):
        raise ValueError('Unexpected combat artwork identities')
    OUT.mkdir(parents=True, exist_ok=True)
    resources, entries, files = {}, [], {}

    def add(image_id, image, source_raw, source_file, item, extra):
        png, masks = _mask_png(image, item['accent'], image_sdk)
        name = image_sdk.image_name(resource, image_id)
        name_hash = archive_sdk.resource_hash(name)
        if item.get('texture_format') == 'R8G8B8A8_UNORM':
            families = {image_sdk.TEXTURE_TYPE: _lossless_icon_texture(png, image_sdk),
                        image_sdk.MATERIAL_TYPE: (image_sdk.icon_material(name_hash), b'')}
        else:
            families = image_sdk.icon_family(png, name_hash, 'auto')
        for kind, parts in families.items():
            resources[(kind, name_hash)] = parts
        (OUT / (image_id + '.png')).write_bytes(png)
        files[_package_source(source_file)] = source_raw
        files['Source/GameIcons/' + image_id + '.png'] = png
        record = {'id': item['id'], 'key': item.get('key', 'ribbon_frame'),
            'image_id': image_id, 'resource': name, 'resource_hash': f'{name_hash:016x}',
            'source_file': source_file, 'package_source_file': _package_source(source_file),
            'source_sha256': _sha(source_raw), 'mask_sha256': _sha(png),
            'accent': item['accent'], 'symbol_width': item.get('symbol_width', 0.34),
            'display_scale': item.get('display_scale', 1),
            'artwork_form': item.get('artwork_form', 'ribbon_frame'),
            'texture_size': [256, 256], 'texture_mips': 9,
            'main_bytes': len(families[image_sdk.TEXTURE_TYPE][0]),
            'gpu_bytes': len(families[image_sdk.TEXTURE_TYPE][1]),
            **{key: item[key] for key in ('texture_format', 'source_preparation') if key in item},
            **extra, **masks}
        entries.append(record)

    for identity in IDS:
        item = integrated[identity] if identity in integrated else combat_items[identity] if identity in OVERRIDE_IDS else items[identity]
        source_file = item['source_file'] if identity in integrated else ((COMBAT / item['file']).relative_to(ROOT).as_posix() if identity in OVERRIDE_IDS
                       else 'artwork/icon-drafts/v18/' + item['file'])
        if identity not in integrated and identity in OVERRIDE_IDS and _sha((COMBAT / item['source_svg']).read_bytes()) != item['source_svg_sha256']:
            raise ValueError('Combat SVG identity changed: ' + identity)
        raw, fitted, bbox, packed_bbox = _fit_source(ROOT / source_file, item)
        add(identity.lower(), fitted, raw, source_file, item,
            {'source_alpha_bbox': list(bbox), 'packed_bbox': packed_bbox,
             'body_ratio': item['body_ratio'], 'alpha_bbox_threshold': 24,
             'quad_content_ratio': (packed_bbox[2] - packed_bbox[0]) / (packed_bbox[3] - packed_bbox[1]),
             'review_fingerprint': item['review_fingerprint'],
             **({'composition': {'type': 'approved_raster_bitmap',
                  'integration_revision': integration['revision']}} if identity in integrated else {})})
    # Editable vectors extend the catalogue. R05 intentionally uses the new
    # elbow source; its old v18 PNG remains unchanged on disk.
    additions_raw = (ACHIEVEMENTS / 'catalog.json').read_bytes()
    additions = json.loads(additions_raw)
    extra_items = {item['id']: item for item in additions['items']}
    if set(extra_items) != set(EXTRA_IDS):
        raise ValueError('Unexpected achievement extension identities')
    for identity in (*EXTRA_IDS, *COMBAT_ADDITIONS):
        item = integrated[identity] if identity in integrated else combat_items[identity] if identity in COMBAT_ADDITIONS else extra_items[identity]
        directory = COMBAT if identity in COMBAT_ADDITIONS else ACHIEVEMENTS
        source_file = item['source_file'] if identity in integrated else (directory / item['file']).relative_to(ROOT).as_posix()
        if identity in integrated:
            composition = {'type': 'approved_raster_bitmap', 'integration_revision': integration['revision'],
                **{key: item[key] for key in ('LibraryID', 'source_sheet_hash', 'source_sheet', 'source_crop') if key in item}}
        else:
            vector = directory / item['source_svg']
            if _sha(vector.read_bytes()) != item['source_svg_sha256']:
                raise ValueError('Achievement SVG identity changed: ' + identity)
            composition = {'type': 'repo_native_vector', 'source_svg': vector.relative_to(ROOT).as_posix(),
                'source_svg_sha256': item['source_svg_sha256'],
                **{key: item[key] for key in ('native_skull_source', 'native_skull_sha256') if key in item}}
        raw, fitted, bbox, packed_bbox = _fit_source(ROOT / source_file, item)
        add(identity.lower(), fitted, raw, source_file, item,
            {'source_alpha_bbox': list(bbox), 'packed_bbox': packed_bbox,
             'body_ratio': item['body_ratio'], 'alpha_bbox_threshold': 24,
             'quad_content_ratio': (packed_bbox[2] - packed_bbox[0]) / (packed_bbox[3] - packed_bbox[1]),
             'review_fingerprint': item['review_fingerprint'],
             'composition': composition})
    for identity in INTEGRATION_ADDITIONS:
        item = integrated[identity]
        source_file = item['source_file']
        raw, fitted, bbox, packed_bbox = _fit_source(ROOT / source_file, item)
        add(identity.lower(), fitted, raw, source_file, item,
            {'source_alpha_bbox': list(bbox), 'packed_bbox': packed_bbox,
             'body_ratio': item['body_ratio'], 'alpha_bbox_threshold': 24,
             'quad_content_ratio': (packed_bbox[2] - packed_bbox[0]) / (packed_bbox[3] - packed_bbox[1]),
             'review_fingerprint': item['review_fingerprint'],
             'composition': {'type': 'approved_raster_bitmap', 'integration_revision': integration['revision'],
                **{key: item[key] for key in ('LibraryID', 'source_sheet_hash', 'source_sheet', 'source_crop', 'unit', 'unit_key') if key in item}}})
    files['Source/Tools/prepare-achievement-icons.py'] = (ROOT / 'tools/prepare-achievement-icons.py').read_bytes()
    files['Source/Tools/prepare-combat-icons.py'] = (ROOT / 'tools/prepare-combat-icons.py').read_bytes()
    files['Source/Tools/prepare-integrated-icons.py'] = (ROOT / 'tools/prepare-integrated-icons.py').read_bytes()
    files['docs/unit-ribbon-icons.json'] = (ROOT / 'docs/unit-ribbon-icons.json').read_bytes()
    award_entries = entries.copy()

    metric_catalog_raw = (METRICS / 'catalog.json').read_bytes()
    metric_catalog = json.loads(metric_catalog_raw)
    metric_items = {item['id']: item for item in metric_catalog['items']}
    skull_raw, skull, skull_bbox = _native_skull()
    skull_source = (SKULL / 'HD2-native-round-eye-skull.png').relative_to(ROOT).as_posix()
    dependencies = []
    for path in [ART / 'catalog.json', ART / 'generation.json', METRICS / 'catalog.json',
                 ACHIEVEMENTS / 'catalog.json', *sorted(ACHIEVEMENTS.glob('*.svg')),
                 COMBAT / 'catalog.json', *sorted(COMBAT.glob('*.svg')),
                 INTEGRATED / 'catalog.json', APPROVED / 'catalog.json', APPROVED / 'export-manifest.json',
                 APPROVED / 'verification.json', APPROVED / 'export-approved-icons.py',
                 APPROVED / 'approved-sources-manifest.original.json', *sorted((APPROVED / 'originals').glob('*.png')),
                 SKULL / 'HD2-native-round-eye-skull.png', SKULL / 'HD2-native-round-eye-skull.svg',
                 SKULL / 'source.json', SKULL / 'source-path.xml', SKULL / 'source-svg_ui_elements.xaml',
                 INDICATORS / 'source.json', INDICATORS / 'arrows.xaml',
                 *sorted((ART / 'references/native-recon-radar').glob('*'))]:
        source_file = path.relative_to(ROOT).as_posix()
        raw = path.read_bytes()
        files[_package_source(source_file)] = raw
        dependencies.append({'source_file': source_file, 'package_source_file': _package_source(source_file),
                             'sha256': _sha(raw)})
    metric_entries = []
    for identity in METRIC_IDS:
        item = metric_items[identity]
        source_file = 'artwork/metric-icon-drafts/v1/' + item['file']
        raw = (ROOT / source_file).read_bytes()
        if _sha(raw) != metric_catalog['sheet_sha256']:
            raise ValueError('Reviewed metric sheet identity changed')
        bbox = item['alpha_bbox']
        image = _rgba(raw)
        if image.size != (item['width'], item['height']):
            raise ValueError('Reviewed metric sheet dimensions changed')
        image = image.crop(bbox)
        composition = {'type': 'sheet_crop', 'sheet_sha256': metric_catalog['sheet_sha256'],
                       'sheet_bbox': bbox}
        if identity == 'U01':
            raw, image, bbox, source_file = skull_raw, skull, skull_bbox, skull_source
            composition = {'type': 'native_round_eye_skull', 'opacity': .88,
                           'template': 'DataTemplate_UI_Skull_Icon'}
        elif identity == 'U04':
            image = _kd_image(image, skull)
            composition.update({'type': 'layered_composition',
                'slash_clip': 'polygon(85% 0,98% 0,26% 100%,13% 100%)',
                'tag_clip': 'inset(33% 0 0 56%)',
                'native_skull_box': 'left0 top0 width50% height58%', 'native_skull_opacity': .88,
                'native_skull_source': skull_source, 'native_skull_sha256': _sha(skull_raw)})
        fitted, packed_bbox = _fit_image(image)
        add(identity.lower(), fitted, raw, source_file,
            {**item, 'artwork_form': 'metric_symbol'},
            {'source_alpha_bbox': list(bbox), 'packed_bbox': packed_bbox,
             'body_ratio': image.width / image.height,
             'quad_content_ratio': (packed_bbox[2] - packed_bbox[0]) / (packed_bbox[3] - packed_bbox[1]),
             'composition': composition})
        metric_entries.append(entries[-1])
    indicator_entries = []
    for identity, raw, image, packed, key, path in _indicator_images():
        add(identity.lower(), image, raw, (INDICATORS / 'arrows.xaml').relative_to(ROOT).as_posix(),
            {'id': identity, 'key': 'trend_up' if identity == 'I01' else 'trend_down',
             'accent': '#E7D46A', 'artwork_form': 'native_indicator'},
            {'packed_bbox': packed, 'source_alpha_bbox': [0, 0, 8, 4], 'body_ratio': 2,
             'quad_content_ratio': 2, 'composition': {'type': 'native_xaml_geometry',
                'geometry_key': key, 'path': path, 'viewbox': [0, 0, 8, 4]}})
        indicator_entries.append(entries[-1])
    frame_raw, frame = _frame_image()
    add('ribbon_frame', frame, frame_raw, 'artwork/icon-drafts/v18/ribbon-frame.svg',
        {'id': 'ribbon_frame', 'accent': '#E7D46A'},
        {'draw_ratio': 3, 'texture_stretched_for_draw_ratio': True,
         'frame_viewbox': [0, 0, 180, 60], 'inner_box': [9, 9, 171, 51],
         'normalized_inner_box': [0.05, 0.15, 0.95, 0.85]})
    frame_entry = entries[-1]
    # A single exact mask fills any native Career rectangle. No artwork fitting
    # or transparent margin: stretching this full-R image preserves all edges.
    solid_png = image_sdk.write_png(256, 256, bytes((255, 0, 0, 255)) * (256 * 256))
    solid_name = image_sdk.image_name(resource, 'career_solid')
    solid_hash = archive_sdk.resource_hash(solid_name)
    solid_family = image_sdk.icon_family(solid_png, solid_hash, 'raw')
    for kind, parts in solid_family.items():
        resources[(kind, solid_hash)] = parts
    solid_source = Path(__file__).read_bytes()
    solid = {'id': 'career_solid', 'key': 'career_solid', 'image_id': 'career_solid',
        'resource': solid_name, 'resource_hash': f'{solid_hash:016x}',
        'source_file': 'tools/prepare-game-icons.py',
        'package_source_file': 'Source/Tools/prepare-game-icons.py',
        'source_sha256': _sha(solid_source), 'mask_sha256': _sha(solid_png),
        'prepared': 'exact full-R mask; no crop, border or artwork conversion',
        'build': 'native Career rectangle primitive; raw SDK icon family',
        'texture_size': [256, 256], 'texture_mips': 9,
        'main_bytes': len(solid_family[image_sdk.TEXTURE_TYPE][0]),
        'gpu_bytes': len(solid_family[image_sdk.TEXTURE_TYPE][1]),
        'mask_white_channel': 'R', 'empty_pixels': 0,
        'white_mask_sum': 255 * 256 * 256, 'accent_mask_sum': 0}
    entries.append(solid)
    (OUT / 'career_solid.png').write_bytes(solid_png)
    files['Source/GameIcons/career_solid.png'] = solid_png
    files[solid['package_source_file']] = solid_source
    record_name = resource + '/hd2runtime_images'
    resources[(archive_sdk.LUA_TYPE, archive_sdk.resource_hash(record_name))] = (
        archive_sdk.lua_resource(_record_lua(entries)), b'')
    manifest = {'schema': 1, 'revision': 'v18', 'source_catalog_sha256': _sha(catalog_raw),
        'integration_catalog_sha256': _sha(integration_raw), 'integration_revision': integration['revision'],
        'integrated_image_count': len(integrated),
        'achievement_catalog_sha256': _sha(additions_raw),
        'achievement_revision': additions['revision'],
        'metric_catalog_sha256': _sha(metric_catalog_raw),
        'metric_sheet_sha256': metric_catalog['sheet_sha256'],
        'sdk_path': 'HD2Runtime@dcd996daca2573443956c07252c55c2d86dd0320/sdk',
        'sdk_image_sha256': _sha((SDK / 'tools/hd2_image.py').read_bytes()),
        'sdk_archive_sha256': _sha((SDK / 'tools/hd2_archive.py').read_bytes()),
        'compile_rule': 'approved-bitmap-overrides-and-unit-ribbons-alpha-crop-fit248-sdk-whiteR-categoryG-v4',
        'original_image_count': len(IDS), 'achievement_image_count': len(EXTRA_IDS),
        'image_count': len(award_entries), 'metric_count': len(METRIC_IDS),
        'indicator_count': len(INDICATOR_IDS),
        'ui_count': 1,
        'texture_family_count': len(entries), 'resource_count': len(resources),
        'draw_colours': {'r': '#FFF9ED', 'g': 'per-image accent', 'b': [0, 0, 0, 0]},
        'shader_alpha': 'source alpha is baked into RGB masks; empty RGB=0; c3 stays zero',
        'images': award_entries, 'metrics': metric_entries, 'indicators': indicator_entries, 'frame': frame_entry,
        'ui': {'solid': solid},
        'source_dependencies': dependencies,
        'source_artwork_unchanged': True, 'game_launched': False, 'deployed': False}
    serialized = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf8')
    (OUT / 'manifest.json').write_bytes(serialized)
    files['Source/GameIcons/manifest.json'] = serialized
    return {'resources': resources, 'manifest': manifest, 'files': files}


if __name__ == '__main__':
    result = game_icon_resources('mods/hd2_costs/war_cost_ledger')
    manifest = result['manifest']
    print('Compiled %d awards, %d metrics, %d indicators, one hollow frame and one Career solid into %d SDK resources.' %
        (manifest['image_count'], manifest['metric_count'], manifest['indicator_count'], manifest['resource_count']))
    print('Build-only derivatives: ' + str(OUT))
