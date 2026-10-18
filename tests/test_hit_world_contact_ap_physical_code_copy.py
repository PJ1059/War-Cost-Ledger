"""New six-region relocation tests only; captured instructions are never called."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('six_region_code_copy',
    ROOT / 'tools/native/hit_world_contact_ap_physical_code_copy.py')
copy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(copy)


class CompleteContactCopyTests(unittest.TestCase):
    BASE = 0x180000000
    LAYOUT = {'frame': BASE + 0x10000000, 'world': BASE + 0x10001000,
              'contact': BASE + 0x10004000, 'ap': BASE + 0x10009000,
              'dispatcher': BASE + 0x1000A000, 'physical': BASE + 0x1000B000}

    def test_six_region_actual_instruction_targets_switches_and_same_offsets(self):
        sources, _ = copy.load_sources()
        result = copy.build(self.BASE, self.LAYOUT)
        manifest = result['manifest']
        self.assertEqual([len(result['blobs'][n]) for n in copy.REGIONS],
                         [67, 9852, 17266, 843, 244, 1552])
        self.assertEqual(manifest['blob_bytes'], 29824)
        self.assertFalse(manifest['observers_inserted'])
        self.assertFalse(manifest['new_RX_executed'])
        self.assertFalse(manifest['classification_ready'])
        md = copy.capstone.Cs(copy.capstone.CS_ARCH_X86, copy.capstone.CS_MODE_64)
        md.detail = True

        def mapped(target):
            for name, (rva, size, _) in copy.REGIONS.items():
                if self.BASE + rva <= target < self.BASE + rva + size:
                    return self.LAYOUT[name] + target - self.BASE - rva
            return target

        by_pc = {r['old_pc'] - self.BASE: r for r in manifest['relocations'] if 'old_pc' in r}
        for caller, target in ((0x4EE6E9, 'world'), (0xAB5FEF, 'contact'),
                               (0x13AD7C8, 'dispatcher'), (0x129DC6D, 'ap'),
                               (0x13AD751, 'physical')):
            self.assertEqual(by_pc[caller]['new_target'], self.LAYOUT[target])
        # Each instruction retains its offset/size and its semantic direct/RIP
        # target. This checks the saved inputs, independently of manifest targets.
        for name, (rva, _, code_size) in copy.REGIONS.items():
            old = list(md.disasm(sources[name][:code_size], self.BASE + rva))
            new = list(md.disasm(result['blobs'][name][:code_size], self.LAYOUT[name]))
            self.assertEqual([(i.address - self.BASE - rva, i.size, i.mnemonic) for i in old],
                             [(i.address - self.LAYOUT[name], i.size, i.mnemonic) for i in new])
            self.assertEqual(sum(i.size for i in new), code_size)
            for before, after in zip(old, new):
                if before.group(copy.capstone.CS_GRP_BRANCH_RELATIVE):
                    self.assertEqual(after.operands[0].imm, mapped(before.operands[0].imm))
                for operand in before.operands:
                    if (operand.type == copy.base.X86_OP_MEM
                            and operand.mem.base == copy.base.X86_REG_RIP):
                        self.assertEqual(after.address + after.size + after.disp,
                                         mapped(before.address + before.size + before.disp))
        # Original image-base LEAs stay original, while both SIB disp32 table
        # references and each table's DWORD cases point to their copies.
        self.assertEqual(by_pc[0x129DC57]['new_target'], self.BASE)
        self.assertEqual(by_pc[0xAB60A9]['new_target'], self.BASE)
        self.assertEqual(by_pc[0x129DC5E]['new_target'], self.LAYOUT['dispatcher'] + 216)
        self.assertEqual(struct.unpack_from('<7I', result['blobs']['dispatcher'], 216),
                         tuple(self.LAYOUT['dispatcher'] - self.BASE + r - 0x129DC30
                               for r in copy.DISPATCH_TARGETS))
        self.assertEqual(result['blobs']['dispatcher'][213:216], bytes.fromhex('0f1f00'))
        self.assertEqual(struct.unpack_from('<6I', result['blobs']['world'], 9828),
                         tuple(self.LAYOUT['world'] - self.BASE + r - 0xAB5000
                               for r in copy.base.SWITCH_TARGETS))
        self.assertEqual(sum(r['kind'] == 'switch_rva32' for r in manifest['relocations']), 13)
        for pc, target in ((0x4EE6FE, 0x173BAB0), (0x13AC201, 0x21045C0)):
            self.assertEqual(by_pc[pc]['new_target'], self.BASE + target)
            self.assertIsNone(by_pc[pc]['destination_region'])
        changed = {name: set() for name in copy.REGIONS}
        for r in manifest['relocations']:
            at = (r['offset'] if r['kind'] == 'switch_rva32' else
                  r['old_pc'] - self.BASE - copy.REGIONS[r['region']][0] + r['field_offset'])
            changed[r['region']].update(range(at, at + r['width']))
        for name, source in sources.items():
            self.assertTrue(all(source[i] == result['blobs'][name][i]
                                for i in range(len(source)) if i not in changed[name]))
        with tempfile.TemporaryDirectory() as directory:
            copy.export_build(result, directory)
            self.assertEqual((Path(directory) / 'code.bin').read_bytes(),
                             b''.join(result['blobs'][n] for n in copy.REGIONS))

    def test_new_saved_tail_or_metadata_changes_are_rejected(self):
        # Existing packets are copied solely to supply the new caller's full
        # source_root contract; no old mapper/test suite is executed.
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            paths = []
            for _, parent, stem, *_ in copy.base.PACKETS:
                paths.extend(Path('dist') / parent / (stem + suffix) for suffix in ('.bin', '.json'))
            for stem, *_ in copy.EXTRA_SOURCES.values():
                paths.extend(Path(stem + suffix) for suffix in ('.bin', '.json'))
            paths.extend(Path('dist') / copy.PACKET_DIRECTORY / ('callsite' + suffix)
                         for suffix in ('.bin', '.json'))
            for relative in paths:
                destination = folder / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((ROOT / relative).read_bytes())
            for suffix, offset in (('.bin', 240), ('.json', -1)):
                with self.subTest(extension=suffix):
                    path = folder / 'dist' / copy.PACKET_DIRECTORY / ('callsite' + suffix)
                    original = path.read_bytes()
                    changed = bytearray(original)
                    changed[offset] ^= 1
                    path.write_bytes(changed)
                    with self.assertRaisesRegex(copy.CopyRejected,
                                               'SOURCE_SHA_MISMATCH:AP_physical_actual_metadata'):
                        copy.build(self.BASE, self.LAYOUT, folder)
                    path.write_bytes(original)

    def test_new_region_layout_overlap_and_rel32_overflow_are_rejected(self):
        for layout, reason in (({**self.LAYOUT, 'physical': self.LAYOUT['ap'] + 16}, 'LAYOUT_OVERLAP'),
                               ({**self.LAYOUT, 'dispatcher': self.BASE - 1}, 'RVA32_OUT_OF_RANGE'),
                               ({**self.LAYOUT, 'ap': self.BASE + 0xF0000000}, 'REL32_OVERFLOW')):
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(copy.CopyRejected, reason):
                    copy.build(self.BASE, layout)


if __name__ == '__main__':
    unittest.main(verbosity=2)
