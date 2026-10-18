"""Certified contact profile on standalone tool-owned pages. No game access."""
import ctypes
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/native"))
from hit_bridge_owned import OwnedBridge
from hit_contact_context_owned import OwnedContactContext
from hit_bridge_install_owned import OwnedE8Callsite
from hit_entity_resolver_owned import OwnedEntityResolver


class OwnedGameProfileTests(unittest.TestCase):
    @staticmethod
    def fixture(b):
        resolver = OwnedEntityResolver(b)
        resolver.insert(1001, resolver.enemies[0], 0)
        resolver.insert(1002, resolver.sources[0], 1)
        resolver.insert(1003, resolver.sources[-1], 2)
        hit = (ctypes.c_uint8 * 0x118)()
        calculation = (ctypes.c_uint8 * 0x24)()
        final = (ctypes.c_uint8 * 0x24)()
        row = (ctypes.c_uint8 * 0x100)()
        calls = ctypes.c_uint64()
        ctypes.c_uint64.from_buffer(hit, 0x110).value = b.local_peer
        ctypes.c_uint32.from_buffer(hit, 0x20).value = 1001
        ctypes.c_uint32.from_buffer(hit, 0x80).value = 1002
        ctypes.c_float.from_buffer(hit, 0x50).value = 4
        ctx = OwnedContactContext(b, certified_contact_profile=True)
        original = b._procedure(bytes.fromhex("48 ff 01 48 b8 10 32 54 76 98 ba dc fe c3"),
            ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
            ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p)
        observer = ctx.final_wrapper(original, extra_arg_types=(ctypes.c_uint64, ctypes.c_void_p),
            projectile_info_from_entry_rax=True, qualifier=resolver._qualify, entity_manager=resolver.manager)
        caller = OwnedE8Callsite(b, original, projectile_info_from_sixth_arg=True)
        caller.install(observer)
        b._keepalive.extend([hit, calculation, final, row, calls, resolver])
        def finish():
            return caller.invoke(ctypes.addressof(calls), ctypes.addressof(final), ctypes.addressof(hit),
                                 0, 123, ctypes.addressof(row))
        def contact(ap=5, *, custom=False):
            ctx.begin(hit)
            ctx.curve_marker(hit, custom=custom)
            ctx.ap_stage(hit, calculation, selected_ap=ap, armour=4, factor=1)
            ctypes.memmove(final, calculation, 0x24)
        return resolver, ctx, hit, row, calls, contact, finish

    def test_full_chain_source_ap_final_native_qualifier_fifo(self):
        with OwnedBridge() as b:
            resolver, ctx, hit, row, calls, contact, finish = self.fixture(b)
            contact()
            self.assertEqual(b.stats()["accepted"], 0)
            self.assertEqual(finish(), 0xFEDCBA9876543210)
            finish()
            records = b.drain()
            self.assertEqual(len(records), 1)
            record = records[0]
            self.assertEqual((record.source, record.target, record.creditor), (1002, 1001, b.local_peer))
            self.assertEqual((record.capture_flags, record.target_kind, record.native_branch), (0x1FF, 1, 1))
            self.assertEqual((record.ap_delta, record.factor, record.effect_flags), (1, 1, 0))
            self.assertEqual(calls.value, 2)

    def test_each_normal_ap_class_uses_native_delta_and_new_contact(self):
        with OwnedBridge() as b:
            resolver, ctx, hit, row, calls, contact, finish = self.fixture(b)
            for ap in (3, 4, 5):
                contact(ap)
                finish()
            records = b.drain()
            self.assertEqual([r.ap_delta for r in records], [-1, 0, 1])
            self.assertEqual([r.capture_flags for r in records], [0x1FF] * 3)
            self.assertEqual([r.contact_ordinal for r in records], [1, 2, 3])
            self.assertEqual([r.sequence for r in records], [1, 2, 3])

    def test_changed_source_clears_ap_proof_despite_new_source_being_supported(self):
        with OwnedBridge() as b:
            resolver, ctx, hit, row, calls, contact, finish = self.fixture(b)
            contact()
            ctypes.c_uint32.from_buffer(hit, 0x80).value = 1003
            finish()
            record = b.drain()[0]
            self.assertEqual(record.source, 1003)
            self.assertEqual(record.capture_flags, 0x163)
            self.assertEqual(ctx.state()["rejected"], 1)
            self.assertEqual(calls.value, 1)

    def test_unknown_target_or_spray_source_is_transport_without_award_proof(self):
        with OwnedBridge() as b:
            resolver, ctx, hit, row, calls, contact, finish = self.fixture(b)
            ctypes.c_uint32.from_buffer(hit, 0x20).value = 9999
            contact(); finish()
            unknown_target = b.drain()[0]
            self.assertEqual((unknown_target.capture_flags, unknown_target.target_kind), (0x1BF, 0))
            ctypes.c_uint32.from_buffer(hit, 0x20).value = 1001
            resolver.insert(1002, 0xE90F771A36FB441E, 1)  # FLAM-40 spray is not an admitted source
            contact(); finish()
            spray = b.drain()[0]
            self.assertEqual(spray.capture_flags, 0xFF)
            self.assertEqual(spray.capture_flags & 0x100, 0)
            resolver.insert(1002, 0xC12A34F375BD5A87, 1)  # incendiary direct projectile stays supported
            contact(); finish()
            self.assertEqual(b.drain()[0].capture_flags, 0x1FF)

    def test_force_and_custom_paths_explicit_even_with_full_capture(self):
        with OwnedBridge() as b:
            resolver, ctx, hit, row, calls, contact, finish = self.fixture(b)
            for hi_force, projectile_force, custom, expected in [(1, 0, False, 1), (0, 1, False, 2), (0, 0, True, 4)]:
                hit[0x73] = hi_force
                row[0xFC] = projectile_force
                contact(custom=custom); finish()
                record = b.drain()[0]
                self.assertEqual(record.capture_flags, 0x1FF)
                self.assertEqual(record.effect_flags, expected)

    def test_non_local_creditor_remains_native_filtered(self):
        with OwnedBridge() as b:
            resolver, ctx, hit, row, calls, contact, finish = self.fixture(b)
            ctypes.c_uint64.from_buffer(hit, 0x110).value = b.local_peer - 1
            contact(); finish()
            self.assertEqual(b.drain(), [])
            self.assertEqual(b.stats()["filtered"], 1)
            self.assertEqual(calls.value, 1)

    def test_certified_profile_refuses_non_owned_qualifier_or_manager(self):
        with OwnedBridge() as b:
            resolver, ctx, hit, row, calls, contact, finish = self.fixture(b)
            original = b._procedure(bytes.fromhex("c3"), ctypes.c_uint64)
            with self.assertRaises(ValueError):
                ctx.final_wrapper(original, projectile_info_from_entry_rax=True,
                    qualifier=ctypes.c_void_p(1), entity_manager=resolver.manager)
            with self.assertRaises(ValueError):
                ctx.final_wrapper(original, projectile_info_from_entry_rax=True,
                    qualifier=resolver._qualify, entity_manager=1)

    def test_ap_observer_restores_full_mxcsr_and_retains_native_rounding(self):
        with OwnedBridge() as b:
            resolver, ctx, hit, row, calls, contact, finish = self.fixture(b)
            get = b._procedure(bytes.fromhex("48 83 ec 08 0f ae 1c 24 8b 04 24 48 83 c4 08 c3"),
                ctypes.c_uint32, unwind=bytes.fromhex("01040100 0402 0000"))
            set_ = b._procedure(bytes.fromhex("48 83 ec 08 89 0c 24 0f ae 14 24 48 83 c4 08 c3"),
                None, ctypes.c_uint32, unwind=bytes.fromhex("01040100 0402 0000"))
            saved = get()
            try:
                for rounding in (0, 0x2000, 0x4000, 0x6000):
                    ctx.reset_after_owned_calls_return()
                    ctx.begin(hit)
                    ctx.curve_marker(hit, custom=False)
                    chosen = (saved & ~0x603F) | rounding | 0x15
                    set_(chosen)
                    ctx.ap_stage(hit, (ctypes.c_uint8 * 0x24)(), selected_ap=1, armour=2**-26, factor=1)
                    after = get()
                    set_(saved)
                    self.assertEqual(after, chosen)
                    self.assertEqual(ctx.record.ap_delta, 1.0 if rounding in (0, 0x4000) else ctypes.c_float(1-2**-24).value)
            finally:
                set_(saved)

    def test_extra_observer_subss_masks_snan_and_restores_unmasked_invalid_control(self):
        with OwnedBridge() as b:
            resolver, ctx, hit, row, calls, contact, finish = self.fixture(b)
            get = b._procedure(bytes.fromhex("48 83 ec 08 0f ae 1c 24 8b 04 24 48 83 c4 08 c3"),
                ctypes.c_uint32, unwind=bytes.fromhex("01040100 0402 0000"))
            set_ = b._procedure(bytes.fromhex("48 83 ec 08 89 0c 24 0f ae 14 24 48 83 c4 08 c3"),
                None, ctypes.c_uint32, unwind=bytes.fromhex("01040100 0402 0000"))
            floats_bits = (ctypes.c_uint32 * 3)(0x7F800001, 0x40800000, 0x3F800000)
            calculation = (ctypes.c_uint8 * 0x24)()
            ctx.begin(hit)
            ctx.curve_marker(hit, custom=True)
            saved = get()
            chosen = (saved | 0x1F00) & ~0x81  # original invalid exception unmasked, status clear
            try:
                set_(chosen)
                ctx._caller(None, ctypes.addressof(hit), ctypes.addressof(calculation), ctypes.addressof(floats_bits))
                after = get()
            finally:
                set_(saved)
            self.assertEqual(after, chosen)
            delta_bits = ctypes.c_uint32.from_address(ctx.address + 92).value
            self.assertEqual(delta_bits & 0x7FC00000, 0x7FC00000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
