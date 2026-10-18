"""Targeted offline tests; frozen code is decoded, never invoked or mapped RX."""
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('code_copy', ROOT / 'tools/native/hit_world_contact_code_copy.py')
copy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(copy)


class FixedCopyTests(unittest.TestCase):
    BASE = 0x180000000
    LAYOUT = {'frame': BASE + 0x10000000, 'world': BASE + 0x10001000,
              'contact': BASE + 0x10004000}

    def test_actual_sources_call_chain_switch_and_external_targets(self):
        source, _ = copy.load_sources()
        result = copy.build(self.BASE, self.LAYOUT)
        manifest = result['manifest']
        self.assertEqual([len(result['blobs'][n]) for n in copy.REGIONS], [67, 9852, 17266])
        self.assertEqual([r['instruction_count'] for r in manifest['regions']], [14, 2138, 3673])
        by_pc = {r['old_pc'] - self.BASE: r for r in manifest['relocations'] if 'old_pc' in r}
        self.assertEqual(by_pc[0x4EE6E9]['new_target'], self.LAYOUT['world'])
        self.assertEqual(by_pc[0xAB5FEF]['new_target'], self.LAYOUT['contact'])
        # The frame's tail and contact stack helper stay at their original VA.
        self.assertEqual(by_pc[0x4EE6FE]['new_target'], self.BASE + 0x173BAB0)
        self.assertIsNone(by_pc[0x4EE6FE]['destination_region'])
        self.assertEqual(by_pc[0x13AC201]['new_target'], self.BASE + 0x21045C0)
        # World still forms the original Game base for its RVA32 switch scheme.
        self.assertEqual(by_pc[0xAB60A9]['new_target'], self.BASE)
        self.assertEqual(by_pc[0xAB60B0]['new_target'], self.LAYOUT['world'] + 9828)
        expected = tuple(self.LAYOUT['world'] - self.BASE + r - 0xAB5000 for r in copy.SWITCH_TARGETS)
        self.assertEqual(struct.unpack_from('<6I', result['blobs']['world'], 9828), expected)
        self.assertEqual(sum(r['kind'] == 'switch_rva32' for r in manifest['relocations']), 6)

        # Decode every output instruction at its new VA independently. Branch
        # destinations and RIP references must equal the manifest's intended VA.
        md = copy.capstone.Cs(copy.capstone.CS_ARCH_X86, copy.capstone.CS_MODE_64)
        md.detail = True
        decoded = {}
        for name, (_, _, code_length) in copy.REGIONS.items():
            items = list(md.disasm(result['blobs'][name][:code_length], self.LAYOUT[name]))
            self.assertEqual(sum(i.size for i in items), code_length)
            decoded.update((i.address, i) for i in items)
        changed_positions = {name: set() for name in copy.REGIONS}
        for r in manifest['relocations']:
            if r['kind'] == 'switch_rva32':
                at = r['offset']
            else:
                instruction = decoded[r['new_pc']]
                self.assertEqual(instruction.size, r['instruction_size'])
                if r['kind'] == 'relative_branch':
                    self.assertEqual(instruction.operands[0].imm, r['new_target'])
                elif r['kind'] == 'switch_table_disp32':
                    self.assertEqual(self.BASE + instruction.disp, r['new_target'])
                else:
                    self.assertEqual(instruction.address + instruction.size + instruction.disp, r['new_target'])
                old_rva = copy.REGIONS[r['region']][0]
                at = r['old_pc'] - self.BASE - old_rva + r['field_offset']
            changed_positions[r['region']].update(range(at, at + r['width']))
        for name in copy.REGIONS:
            self.assertTrue(all(a == c for i, (a, c) in enumerate(zip(source[name], result['blobs'][name]))
                                if i not in changed_positions[name]))
        with tempfile.TemporaryDirectory() as folder:
            copy.export_build(result, folder)
            self.assertEqual(len((Path(folder) / 'code.bin').read_bytes()), 27185)
            saved = json.loads((Path(folder) / 'relocation-manifest.json').read_text())
            self.assertFalse(saved['Game_or_exception_safety_proven'])
            self.assertFalse(saved['UW_supplied'])

    def test_changed_saved_source_is_rejected(self):
        packet = copy.PACKETS[0]
        _, directory, stem, *_ = packet
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'dist' / directory
            target.mkdir(parents=True)
            for extension in ('bin', 'json'):
                path = ROOT / 'dist' / directory / (stem + '.' + extension)
                (target / path.name).write_bytes(path.read_bytes())
            for extension in ('bin', 'json'):
                with self.subTest(extension=extension):
                    path = target / (stem + '.' + extension)
                    original = path.read_bytes()
                    changed = bytearray(original)
                    changed[-1] ^= 1
                    path.write_bytes(changed)
                    with self.assertRaisesRegex(copy.CopyRejected, 'SOURCE_SHA_MISMATCH:frame'):
                        copy.build(self.BASE, self.LAYOUT, source_root=folder)
                    path.write_bytes(original)

    def test_layout_rva_and_displacement_overflow_are_rejected(self):
        cases = (
            ({**self.LAYOUT, 'frame': self.BASE - 1}, 'RVA32_OUT_OF_RANGE'),
            ({**self.LAYOUT, 'frame': self.BASE + 0xFFFFFFFF - 66}, 'RVA32_OUT_OF_RANGE'),
            ({**self.LAYOUT, 'world': self.LAYOUT['frame'] + 16}, 'LAYOUT_OVERLAP'),
            ({**self.LAYOUT, 'frame': self.BASE + 0x90000000}, 'RIP_DISP32_OVERFLOW'),
            ({**self.LAYOUT, 'world': self.BASE + 0xA0000000}, 'REL32_OVERFLOW'),
        )
        for layout, reason in cases:
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(copy.CopyRejected, reason):
                    copy.build(self.BASE, layout)


if __name__ == '__main__':
    unittest.main(verbosity=2)
