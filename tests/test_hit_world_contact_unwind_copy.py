"""New structural slice only; no native API or Game code execution."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('unwind_copy', ROOT / 'tools/native/hit_world_contact_unwind_copy.py')
copy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(copy)


class FixedUnwindCopyTests(unittest.TestCase):
    BASE = 0x180000000
    LAYOUT = {'frame': BASE + 0x10000000, 'world': BASE + 0x10001000,
              'contact': BASE + 0x10004000}
    UW = BASE + 0x10010000
    TABLE = BASE + 0x10011000

    def test_actual_19_records_all_chains_slots_GS_and_exclusive_ends(self):
        source = copy.load_sources()
        result = copy.build(self.BASE, self.LAYOUT, self.UW, self.TABLE)
        table = list(struct.iter_unpack('<III', result['runtime_table_blob']))
        self.assertEqual(len(table), 19)
        self.assertEqual(table, sorted(table))
        self.assertEqual(len(result['unwind_blob']), 492)
        self.assertEqual(len(result['manifest']['chain_rewrites']), 16)
        # Derive all expected RF triples from original offsets independently.
        expected_records = []
        expected_uw = source['raw'][708:720] + source['raw'][216:440] + source['raw'][440:696]
        changed = set()
        for name, records in source['records'].items():
            begin, size, _ = copy.code_copy.REGIONS[name]
            uw_start, _, _, block = copy.UW_BLOCKS[name]
            for old_begin, old_end, old_uw in records:
                expected_records.append((self.LAYOUT[name] - self.BASE + old_begin - begin,
                                         self.LAYOUT[name] - self.BASE + old_end - begin,
                                         self.UW - self.BASE + block + old_uw - uw_start))
            self.assertEqual(max(r[1] for r in expected_records
                                 if self.LAYOUT[name] - self.BASE <= r[0] < self.LAYOUT[name] - self.BASE + size),
                             self.LAYOUT[name] - self.BASE + size)
            for node in source['nodes'][name]:
                at = block + node['offset']
                original = node['raw']
                actual = result['unwind_blob'][at:at + len(original)]
                self.assertEqual(actual[:node['tail_offset']], original[:node['tail_offset']])
                if node['flags'] == 4:
                    copied_parent = struct.unpack_from('<III', actual, node['tail_offset'])
                    old_parent = node['chain']
                    expected_parent = (self.LAYOUT[name] - self.BASE + old_parent[0] - begin,
                                       self.LAYOUT[name] - self.BASE + old_parent[1] - begin,
                                       self.UW - self.BASE + block + old_parent[2] - uw_start)
                    self.assertEqual(copied_parent, expected_parent)
                    changed.update(range(at + node['tail_offset'], at + node['tail_offset'] + 12))
                else:
                    self.assertEqual(actual, original)
                    if node['flags'] == 3:
                        self.assertEqual(struct.unpack_from('<II', actual, node['tail_offset']),
                                         (0x21044A0, {'world': 0x6D0, 'contact': 0x25C0}[name]))
        self.assertEqual(table, sorted(expected_records))
        for r in result['manifest']['chain_rewrites']:
            self.assertIn(tuple(r['new_chain']), table)
        self.assertTrue(all(a == b for i, (a, b) in enumerate(zip(expected_uw, result['unwind_blob']))
                            if i not in changed))
        for n in ('frame', 'world', 'contact'):
            self.assertEqual(len(result['code']['blobs'][n]), copy.code_copy.REGIONS[n][1])
        self.assertFalse(result['manifest']['native_registered'])
        self.assertFalse(result['manifest']['owned_unwind_parity_proven'])
        with tempfile.TemporaryDirectory() as folder:
            copy.export_build(result, folder)
            self.assertEqual((Path(folder) / 'unwind.bin').read_bytes(), result['unwind_blob'])
            self.assertEqual((Path(folder) / 'runtime-function-table.bin').read_bytes(), result['runtime_table_blob'])
            saved = json.loads((Path(folder) / 'unwind-relocation.json').read_text())
            self.assertFalse(saved['Game_or_exception_safety_proven'])

    def test_nonadjacent_permuted_code_addresses_sort_RF_without_changing_offsets(self):
        layout = {'contact': self.BASE + 0x10000000,
                  'frame': self.BASE + 0x11000000, 'world': self.BASE + 0x12000000}
        result = copy.build(self.BASE, layout, self.UW, self.TABLE)
        manifest = result['manifest']
        self.assertEqual([r['region'] for r in manifest['runtime_records']],
                         ['contact'] * 9 + ['frame'] + ['world'] * 9)
        for r in manifest['runtime_records']:
            self.assertEqual(r['new'][1] - r['new'][0], r['old'][1] - r['old'][0])
        targets = {tuple(r['new']) for r in manifest['runtime_records']}
        self.assertTrue(all(tuple(r['new_chain']) in targets for r in manifest['chain_rewrites']))

    def test_metadata_addresses_alignment_RVA32_and_overlap_rejected(self):
        cases = ((self.UW + 1, self.TABLE, 'ADDRESS_OR_ALIGNMENT'),
                 (self.UW, self.TABLE + 1, 'ADDRESS_OR_ALIGNMENT'),
                 (self.BASE - 4, self.TABLE, 'RVA32_OUT_OF_RANGE'),
                 (self.BASE + 0xFFFFFF00, self.TABLE, 'RVA32_OUT_OF_RANGE'),
                 (self.UW, self.BASE + 0xFFFFFF80, 'RVA32_OUT_OF_RANGE'),
                 (self.LAYOUT['world'], self.TABLE, 'LAYOUT_OVERLAP'),
                 (self.UW, self.UW + 480, 'LAYOUT_OVERLAP'))
        for unwind, table, reason in cases:
            with self.subTest(reason=reason, unwind=unwind, table=table):
                with self.assertRaisesRegex(copy.UnwindRejected, reason):
                    copy.build(self.BASE, self.LAYOUT, unwind, table)

    def test_changed_frozen_binary_or_JSON_rejected_before_code_build(self):
        source = ROOT / 'dist' / copy.SOURCE_DIRECTORY
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'dist' / copy.SOURCE_DIRECTORY
            target.mkdir(parents=True)
            for extension in ('bin', 'json'):
                (target / ('callsite.' + extension)).write_bytes((source / ('callsite.' + extension)).read_bytes())
            for extension in ('bin', 'json'):
                with self.subTest(extension=extension):
                    path = target / ('callsite.' + extension)
                    raw = path.read_bytes()
                    changed = bytearray(raw)
                    changed[-1] ^= 1
                    path.write_bytes(changed)
                    with self.assertRaisesRegex(copy.UnwindRejected, 'SOURCE_SHA_MISMATCH:unwind'):
                        copy.build(self.BASE, self.LAYOUT, self.UW, self.TABLE, source_root=folder)
                    path.write_bytes(raw)


if __name__ == '__main__':
    unittest.main()
