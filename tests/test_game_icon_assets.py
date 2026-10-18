"""Build actual SDK resources and verify approved art survives packaging."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('ledger_game_icon_assets', ROOT / 'tools/prepare-game-icons.py')
icons = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(icons)
UNIT_IDS = {f'G{i:02d}' for i in range(1, 7)} | {f'T{i:02d}' for i in range(1, 19)}
NEW_IDS = UNIT_IDS | {'M12'}
REPLACED_IDS = {'R05', 'M08', 'M09', 'M10', 'M11'}
APPROVED_OUTPUTS = {
    'M08': '02e61178ae80389d154720b4547c1d91107b06418e88b64f600eac196dcbe096',
    'M09': '18a2e4b3b72ea4f66e0141a57b8d05a3b583e669de26fd0cb0bf0cddaf6cabf6',
    'M10': '2adc046cb3cb79d6de3d14746df0ce1d4988c3cf4fa9e8a4d8e387a1e944c8f8',
    'M12': '9c0ecc9409d0a6c8a00e3c56d6d5f42692bd4eda1a4af231689d19eb3cd85d6d',
}
APPROVED_SHEETS = {identity: '54fdae1296542575a580329e5dde3d5f0b748ca0f4e47ca76ec292084d339842'
                   for identity in ('M08', 'M09', 'M10')}
APPROVED_SHEETS['M12'] = 'ee653579dd0d82e525231d5dd362e840ecb560d5f26799e48a4a7d36db0bd5da'


class GameIconAssets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='ledger-icon-assets-')
        cls.integration = json.loads((icons.INTEGRATED / 'catalog.json').read_bytes())
        cls.integrated = {item['id']: item for item in cls.integration['items']}
        inputs = {path for directory in (icons.ART, icons.METRICS, icons.SKULL, icons.ACHIEVEMENTS,
                                         icons.COMBAT, icons.INTEGRATED, icons.APPROVED)
                  for path in directory.rglob('*') if path.is_file()}
        inputs.update(ROOT / item['source_file'] for item in cls.integrated.values())
        cls.before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
        with patch.object(icons, 'OUT', Path(cls.temp.name)):
            cls.built = icons.game_icon_resources('mods/hd2_costs/war_cost_ledger')
        cls.manifest = cls.built['manifest']
        cls.records = [*cls.manifest['images'], *cls.manifest['metrics'],
                       *cls.manifest['indicators'], cls.manifest['frame']]
        cls.by_id = {item['id']: item for item in cls.records}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def mask(self, identity):
        raw = self.built['files']['Source/GameIcons/' + self.by_id[identity]['image_id'] + '.png']
        return Image.open(io.BytesIO(raw)).convert('RGBA')

    def test_archive_families_and_separate_metrics(self):
        self.assertEqual(self.manifest['revision'], 'v18')
        self.assertEqual(set(icons.INTEGRATION_ADDITIONS), NEW_IDS)
        self.assertEqual(set(icons.INTEGRATION_OVERRIDES), REPLACED_IDS)
        self.assertEqual({item['id'] for item in self.manifest['images']},
                         set(icons.IDS) | set(icons.EXTRA_IDS) | set(icons.COMBAT_ADDITIONS) | NEW_IDS)
        self.assertEqual(len(self.manifest['images']), 53)
        self.assertEqual([item['id'] for item in self.manifest['metrics']], ['U01', 'U02', 'U03', 'U04'])
        self.assertEqual([item['key'] for item in self.manifest['metrics']], ['kills', 'bill', 'shots', 'kd'])
        self.assertEqual([item['id'] for item in self.manifest['indicators']], ['I01', 'I02'])
        self.assertEqual(len(self.records), 60)
        self.assertEqual(self.manifest['texture_family_count'], len(self.records) + 1)
        self.assertEqual(len(self.built['resources']), self.manifest['texture_family_count'] * 2 + 1)
        self.assertEqual(len(self.built['resources']), 123)
        self.assertEqual(self.manifest['ui_count'], 1)
        sdk = icons._sdk_module('hd2_archive')
        image_sdk = icons._sdk_module('hd2_image')
        archive, gpu = sdk.make_resource_archive(self.built['resources'])
        self.assertEqual(sdk.read_archive(archive, gpu), self.built['resources'])
        for record in self.records:
            name_hash = int(record['resource_hash'], 16)
            self.assertEqual(sdk.resource_hash(record['resource']), name_hash)
            self.assertIn((image_sdk.TEXTURE_TYPE, name_hash), self.built['resources'])
            self.assertIn((image_sdk.MATERIAL_TYPE, name_hash), self.built['resources'])

    def test_career_solid_is_full_mask_with_own_menu_material(self):
        solid = self.manifest['ui']['solid']
        image_sdk = icons._sdk_module('hd2_image')
        sdk = icons._sdk_module('hd2_archive')
        name_hash = int(solid['resource_hash'], 16)
        self.assertEqual(solid['resource'], 'mods/hd2_costs/war_cost_ledger/images/career_solid')
        self.assertEqual(sdk.resource_hash(solid['resource']), name_hash)
        png = self.built['files']['Source/GameIcons/career_solid.png']
        self.assertEqual(image_sdk.read_png(png), (256, 256, bytes((255, 0, 0, 255)) * (256 * 256)))
        self.assertEqual(self.built['resources'][(image_sdk.TEXTURE_TYPE, name_hash)],
                         image_sdk.icon_texture(png, 'raw'))
        self.assertEqual(self.built['resources'][(image_sdk.MATERIAL_TYPE, name_hash)],
                         (image_sdk.icon_material(name_hash), b''))
        self.assertEqual(solid['empty_pixels'], 0)
        self.assertEqual(solid['mask_sha256'], hashlib.sha256(png).hexdigest())
        self.assertEqual(self.built['files'][solid['package_source_file']], Path(icons.__file__).read_bytes())
        image_record, _ = self.built['resources'][(sdk.LUA_TYPE,
            sdk.resource_hash('mods/hd2_costs/war_cost_ledger/hd2runtime_images'))]
        self.assertIn(b'["career_solid"]=', image_record)

    @unittest.skipUnless((ROOT / 'dist/HD2-War-Cost-Ledger-0.4.35.zip').is_file(), '0.4.35 reference package absent')
    def test_previous_families_except_authorized_elbow_replacement_are_byte_identical(self):
        sdk = icons._sdk_module('hd2_archive')
        image_sdk = icons._sdk_module('hd2_image')
        with ZipFile(ROOT / 'dist/HD2-War-Cost-Ledger-0.4.35.zip') as package:
            baseline = sdk.read_archive(package.read('Addon/9ba626afa44a3aa3.patch_0'),
                                        package.read('Addon/9ba626afa44a3aa3.patch_0.gpu_resources'))
        excluded = set(icons.EXTRA_IDS) | set(icons.COMBAT_ADDITIONS) | set(icons.OVERRIDE_IDS) | NEW_IDS
        originals = [record for record in self.records if record['id'] not in excluded]
        self.assertEqual(len(originals), 27)
        for record in originals:
            name_hash = int(record['resource_hash'], 16)
            for kind in (image_sdk.TEXTURE_TYPE, image_sdk.MATERIAL_TYPE):
                key = (kind, name_hash)
                self.assertEqual(self.built['resources'][key], baseline[key], record['id'])

    @unittest.skipUnless((ROOT / 'dist/HD2-War-Cost-Ledger-0.4.57.zip').is_file(), '0.4.57 reference package absent')
    def test_previous057_families_except_five_approved_replacements_are_byte_identical(self):
        sdk = icons._sdk_module('hd2_archive')
        image_sdk = icons._sdk_module('hd2_image')
        with ZipFile(ROOT / 'dist/HD2-War-Cost-Ledger-0.4.57.zip') as package:
            baseline = sdk.read_archive(package.read('Addon/9ba626afa44a3aa3.patch_0'),
                                        package.read('Addon/9ba626afa44a3aa3.patch_0.gpu_resources'))
        unchanged = [record for record in self.records if record['id'] not in REPLACED_IDS | NEW_IDS]
        self.assertEqual(len(unchanged), 30)
        for record in unchanged:
            name_hash = int(record['resource_hash'], 16)
            for kind in (image_sdk.TEXTURE_TYPE, image_sdk.MATERIAL_TYPE):
                self.assertEqual(self.built['resources'][(kind, name_hash)], baseline[(kind, name_hash)], record['id'])

    def test_approved_elbow_and_original_crush_have_distinct_sources(self):
        self.assertEqual(self.by_id['R05']['key'], 'melee')
        self.assertEqual(self.by_id['R12']['key'], 'crush')
        self.assertEqual(self.by_id['R05']['source_file'],
                         'artwork/review-0.4.57-ribbons-v5/compiled/ribbon-melee-elbow.png')
        self.assertEqual(self.by_id['R05']['artwork_form'], 'approved_raster_bitmap')
        self.assertEqual(self.by_id['R05']['symbol_width'], .42)
        self.assertTrue(self.by_id['R12']['source_file'].startswith('artwork/combat-icons/v2/'))
        self.assertEqual(self.by_id['R12']['artwork_form'], 'repo_native_vector_ribbon')
        self.assertNotEqual(self.by_id['R05']['mask_sha256'], self.by_id['R12']['mask_sha256'])
        old = ROOT / 'artwork/icon-drafts/v18/R05-melee.png'
        self.assertNotEqual(self.by_id['R05']['source_sha256'], hashlib.sha256(old.read_bytes()).hexdigest())

    def test_final_four_exact_approved_original_provenance_survives_packaging(self):
        self.assertEqual(set(icons.APPROVED_IDS), set(APPROVED_OUTPUTS))
        exported = json.loads((icons.APPROVED / 'export-manifest.json').read_bytes())
        export_items = {item['id']: item for item in exported['items']}
        for identity, expected in APPROVED_OUTPUTS.items():
            record, integrated, export = self.by_id[identity], self.integrated[identity], export_items[identity]
            self.assertEqual(integrated['sha256'], expected)
            self.assertEqual(record['source_sha256'], expected)
            self.assertEqual(record['source_file'], integrated['source_file'])
            self.assertTrue(record['source_file'].startswith('artwork/approved-icons/0.4.58/'))
            self.assertEqual(export['output_sha256'], expected)
            self.assertEqual(integrated['source_sheet_hash'], APPROVED_SHEETS[identity])
            sheet = (ROOT / integrated['source_sheet']).read_bytes()
            self.assertEqual(hashlib.sha256(sheet).hexdigest(), APPROVED_SHEETS[identity])
            self.assertEqual(export['source_sha256'], APPROVED_SHEETS[identity])
            self.assertFalse(export['resampled'])
            self.assertFalse(export['redrawn'])
            self.assertFalse(export['palette_replaced'])
            composition = record['composition']
            self.assertEqual(composition['type'], 'approved_raster_bitmap')
            self.assertEqual(composition['integration_revision'], self.integration['revision'])
            for key in ('LibraryID', 'source_sheet_hash', 'source_sheet', 'source_crop'):
                self.assertEqual(composition[key], integrated[key])
            self.assertEqual(record['accent'], '#FEE447')
            with Image.open(ROOT / record['source_file']) as source:
                self.assertEqual(source.mode, 'RGBA')
                for hole in export['semantic_negative_space_checks']:
                    self.assertEqual(source.getpixel(tuple(hole['output_xy']))[3], 0)

    def test_all_thirty_integrated_bitmaps_use_the_reviewed_exact_png_paths(self):
        self.assertEqual(set(self.integrated), REPLACED_IDS | NEW_IDS)
        self.assertEqual(self.manifest['integration_revision'], self.integration['revision'])
        for identity, item in self.integrated.items():
            record = self.by_id[identity]
            self.assertEqual(record['source_file'], item['source_file'])
            self.assertEqual(record['source_sha256'], item['sha256'])
            self.assertEqual(record['artwork_form'], 'approved_raster_bitmap')
            self.assertEqual(record['review_fingerprint'], item['review_fingerprint'])
            self.assertEqual(record['source_alpha_bbox'], item['alpha_bbox'])
            self.assertNotIn('source_svg', record.get('composition', {}))
        self.assertTrue(self.by_id['M11']['source_file'].endswith('/medals/other/level-not-problem-scissors.png'))
        for identity in UNIT_IDS:
            record = self.by_id[identity]
            self.assertEqual(record['composition']['unit'], self.integrated[identity]['unit'])
            self.assertEqual(record['composition']['unit_key'], self.integrated[identity]['unit_key'])

    def test_scissors_compiles_original_alpha_into_lossless_mip_chain(self):
        record = self.by_id['M11']
        self.assertEqual(record['source_sha256'],
                         '942574b8f2bfb3eebabf2142f423511f15f2a5c64215c6d6650a4beff2ef8cf8')
        self.assertEqual(record['texture_format'], 'R8G8B8A8_UNORM')
        self.assertEqual(record['source_preparation'], 'review_two_ink_preserve_alpha')
        source = Image.open(ROOT / record['source_file']).convert('RGBA')
        self.assertEqual(source.size, (1179, 1334))
        self.assertGreater(len(set(source.getchannel('A').tobytes())), 2)
        sdk = icons._sdk_module('hd2_image')
        main, gpu = self.built['resources'][(sdk.TEXTURE_TYPE, int(record['resource_hash'], 16))]
        self.assertEqual(struct.unpack_from('<I', main, 192 + 128)[0], 28)
        self.assertEqual(struct.unpack_from('<I', main, 192 + 28)[0], 9)
        self.assertEqual(len(gpu), sum((256 >> level) ** 2 * 4 for level in range(9)))
        expected, offset = self.mask('M11'), 0
        for level in range(9):
            size = 256 >> level
            payload = gpu[offset:offset + size * size * 4]
            # Every mip must retain exact independent white/accent masks; BC1
            # used to turn three-colour boundaries into blocky missing edges.
            self.assertEqual(payload, expected.tobytes(), f'M11 mip {level}')
            offset += len(payload)
            if level < 8:
                expected = expected.resize((size // 2, size // 2), Image.Resampling.BOX)
        decoded = Image.open(io.BytesIO(main[192:] + gpu)).convert('RGBA')
        self.assertEqual(decoded.tobytes(), self.mask('M11').tobytes())

    @unittest.skipUnless((ROOT / 'dist/HD2-War-Cost-Ledger-0.4.63.zip').is_file(), '0.4.63 reference package absent')
    def test_resolution_fix_changes_only_scissors_texture(self):
        sdk, image_sdk = icons._sdk_module('hd2_archive'), icons._sdk_module('hd2_image')
        with ZipFile(ROOT / 'dist/HD2-War-Cost-Ledger-0.4.63.zip') as package:
            baseline = sdk.read_archive(package.read('Addon/9ba626afa44a3aa3.patch_0'),
                                        package.read('Addon/9ba626afa44a3aa3.patch_0.gpu_resources'))
        for record in self.records:
            name_hash = int(record['resource_hash'], 16)
            for kind in (image_sdk.TEXTURE_TYPE, image_sdk.MATERIAL_TYPE):
                if record['id'] == 'M11' and kind == image_sdk.TEXTURE_TYPE:
                    self.assertNotEqual(hashlib.sha256(b''.join(self.built['resources'][(kind, name_hash)])).hexdigest(),
                                        hashlib.sha256(b''.join(baseline[(kind, name_hash)])).hexdigest())
                else:
                    self.assertEqual(self.built['resources'][(kind, name_hash)], baseline[(kind, name_hash)], record['id'])

    def test_source_provenance_and_originals_unchanged(self):
        for record in self.records:
            original = (ROOT / record['source_file']).read_bytes()
            self.assertEqual(self.built['files'][record['package_source_file']], original)
            self.assertEqual(hashlib.sha256(original).hexdigest(), record['source_sha256'])
        for dependency in self.manifest['source_dependencies']:
            original = (ROOT / dependency['source_file']).read_bytes()
            self.assertEqual(self.built['files'][dependency['package_source_file']], original)
            self.assertEqual(hashlib.sha256(original).hexdigest(), dependency['sha256'])
        for path, digest in self.before.items():
            self.assertEqual(hashlib.sha256(Path(path).read_bytes()).hexdigest(), digest)
        self.assertIn(self.by_id['R08']['package_source_file'], list(self.built['files']))
        self.assertTrue(self.by_id['U01']['source_file'].endswith('native-round-eye-skull/HD2-native-round-eye-skull.png'))

    def test_shader_masks_preserve_empty_regions_and_geometry(self):
        for record in self.records:
            image = self.mask(record['id'])
            self.assertEqual(image.size, (256, 256))
            self.assertEqual(image.getchannel('B').getextrema(), (0, 0))
            self.assertEqual(image.getchannel('A').getextrema(), (255, 255))
            self.assertEqual(image.getpixel((0, 0)), (0, 0, 0, 255))
            self.assertGreater(record['white_mask_sum'] + record['accent_mask_sum'], 0)
            if 'packed_bbox' in record:
                left, top, right, bottom = record['packed_bbox']
                if record['id'] in self.integrated:
                    source_left, source_top, source_right, source_bottom = record['source_alpha_bbox']
                    sw, sh = source_right - source_left, source_bottom - source_top
                    factor = 248 / max(sw, sh)
                    # Wide silhouettes can differ by >.01 in ratio after a
                    # half-pixel height rounding. Require the exact proportional
                    # integer dimensions rather than widening every tolerance.
                    self.assertEqual((right - left, bottom - top),
                                     (max(1, round(sw * factor)), max(1, round(sh * factor))))
                    self.assertAlmostEqual(record['body_ratio'], sw / sh, places=12)
                else:
                    self.assertLessEqual(abs((right - left) / (bottom - top) - record['body_ratio']), .01)
        skull = self.mask('U01')
        self.assertEqual(skull.getpixel((78, 143))[:3], (0, 0, 0))
        self.assertEqual(skull.getpixel((177, 143))[:3], (0, 0, 0))
        self.assertGreater(skull.getpixel((128, 30))[0], 180)
        kd = self.mask('U04')
        self.assertEqual(kd.getpixel((43, 88))[:3], (0, 0, 0))
        self.assertEqual(kd.getpixel((89, 88))[:3], (0, 0, 0))
        self.assertGreater(kd.getpixel((154, 106))[0], 100)
        self.assertGreater(kd.getpixel((195, 192))[0] + kd.getpixel((195, 192))[1], 100)

    def test_kd_keeps_original_dog_tag_pixels(self):
        catalog = json.loads((icons.METRICS / 'catalog.json').read_text(encoding='utf8'))
        item = next(item for item in catalog['items'] if item['id'] == 'U04')
        sheet = icons._rgba((icons.METRICS / item['file']).read_bytes()).crop(item['alpha_bbox'])
        _, skull, _ = icons._native_skull()
        result = icons._kd_image(sheet, skull)
        # This region lies below the new skull and outside the clipped slash.
        # Preserve the exact source dog-tag texture/colour rather than redraw it.
        # RGB beneath fully transparent source pixels has no appearance; alpha
        # compositing normalizes those invisible bytes to zero.
        expected = sheet.crop((246, 220, 360, 330))
        actual = result.crop((246, 220, 360, 330))
        expected_pixels, actual_pixels = expected.load(), actual.load()
        mismatches = 0
        for y in range(expected.height):
            for x in range(expected.width):
                original, packed = expected_pixels[x, y], actual_pixels[x, y]
                if original[3] != packed[3] or (original[3] > 0 and original != packed):
                    mismatches += 1
        self.assertEqual(mismatches, 0)

    def test_kd_indicators_use_exact_native_geometry_and_opposite_directions(self):
        expected = {'I01': 'M0,4L4,0 8,4', 'I02': 'M0,0 L4,4 8,0'}
        for identity, path in expected.items():
            record = self.by_id[identity]
            self.assertEqual(record['composition']['path'], path)
            self.assertEqual(record['composition']['viewbox'], [0, 0, 8, 4])
            self.assertEqual(record['quad_content_ratio'], 2)
            self.assertEqual(record['artwork_form'], 'native_indicator')
            mask = self.mask(identity)
            self.assertGreater(mask.getpixel((128, 128))[0], 230)
            left, top, right, bottom = record['packed_bbox']
            # A point near the upper-left is inside only the downward triangle.
            x, y = left + 30, top + 10
            self.assertEqual(mask.getpixel((x, y))[0] > 180, identity == 'I02')
            self.assertEqual(mask.getpixel((x, bottom - 11))[0] > 180, identity == 'I01')
            self.assertLess(record['accent_mask_sum'], record['white_mask_sum'] * .01)

    def test_recon_is_original_native_radar_without_a_backplate(self):
        directory = icons.ART / 'references/native-recon-radar'
        original = ET.fromstring((directory / 'source-template.xml').read_bytes())
        svg = ET.fromstring((directory / 'HD2-native-recon-radar.svg').read_bytes())
        source_paths = [node.attrib['Data'] for node in original.iter()
                        if node.tag.rsplit('}', 1)[-1] == 'Path']
        packaged_paths = [node.attrib['d'] for node in svg
                          if node.tag.rsplit('}', 1)[-1] == 'path']
        self.assertEqual(source_paths, packaged_paths)
        self.assertEqual(len(source_paths), 3)
        self.assertEqual(self.by_id['R10']['key'], 'recon')
        original_png = Image.open(icons.ART / 'R10-recon.png').convert('RGBA')
        self.assertEqual(original_png.getpixel((0, 0))[3], 0)
        self.assertEqual(original_png.getpixel((511, 511))[3], 0)
        self.assertGreater(original_png.getchannel('A').histogram()[0], 512 * 512 * .6)


if __name__ == '__main__':
    unittest.main()
