import ctypes
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/native"))
import hit_bridge_owned as bridge
import hit_contact_context_owned as context
import hit_bridge_install_owned as installation


class OwnedAPFinalTests(unittest.TestCase):
    def assert_unwind(self, b, procedure, *, pc, pushes, frame, popped=(), xmm_saves=()):
        """Synthetic stack/CONTEXT in this tool only, never a thread snapshot."""
        address = int(ctypes.cast(procedure, ctypes.c_void_p).value)
        image, entry = b.unwind_lookup(procedure, pc)
        self.assertEqual(image, address)
        self.assertTrue(entry)
        raw_context = ctypes.create_string_buffer(0x4D0 + 16)
        at = (ctypes.addressof(raw_context) + 15) & ~15
        b.nt.RtlCaptureContext(at)
        stack = ctypes.create_string_buffer(2048 + 16)
        initial = ((ctypes.addressof(stack) + 15) & ~15) + 1024 + 8
        register_offsets = {"rbx": 0x90, "rsi": 0xA8, "rdi": 0xB0}
        values = {name: 0xFEDCBA9876543200 + i for i, name in enumerate(pushes)}
        for i, name in enumerate(pushes, 1):
            ctypes.c_uint64.from_address(initial - i * 8).value = values[name]
            ctypes.c_uint64.from_address(at + register_offsets[name]).value = values[name] if name in popped else 0
        delta = len(pushes) * 8 + frame if not popped else (len(pushes) - len(popped)) * 8
        current = initial - delta
        ctypes.c_uint64.from_address(initial).value = address
        ctypes.c_uint64.from_address(at + 0x98).value = current
        ctypes.c_uint64.from_address(at + 0xF8).value = address + pc
        original_body_rsp = initial - (len(pushes) * 8 + frame)
        expected_xmm = {}
        for index, save_offset in xmm_saves:
            expected_xmm[index] = bytes([index + 1]) * 16
            ctypes.memmove(original_body_rsp + save_offset, expected_xmm[index], 16)
            ctypes.memmove(at + 0x1A0 + index * 16, bytes(16), 16)
        handler, establisher = ctypes.c_void_p(), ctypes.c_uint64()
        b.nt.RtlVirtualUnwind(0, image, address + pc, entry, at,
            ctypes.byref(handler), ctypes.byref(establisher), None)
        self.assertEqual(ctypes.c_uint64.from_address(at + 0x98).value, initial + 8)
        self.assertEqual(ctypes.c_uint64.from_address(at + 0xF8).value, address)
        for name in pushes:
            self.assertEqual(ctypes.c_uint64.from_address(at + register_offsets[name]).value, values[name])
        for index, expected in expected_xmm.items():
            self.assertEqual(ctypes.string_at(at + 0x1A0 + index * 16, 16), expected)

    @staticmethod
    def fixture(b):
        hit = (ctypes.c_uint8 * 0x118)()
        calculation = (ctypes.c_uint8 * 0x24)()
        final = (ctypes.c_uint8 * 0x24)()
        calls = ctypes.c_uint64()
        ctypes.c_uint64.from_buffer(hit, 0x110).value = b.local_peer
        ctypes.c_uint32.from_buffer(hit, 0x20).value = 1001
        ctypes.c_float.from_buffer(hit, 0x50).value = 4.0
        original = b._procedure(bytes.fromhex("48 ff 01 48 b8 10 32 54 76 98 ba dc fe c3"),
            ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint64)
        ctx = context.OwnedContactContext(b)
        callback = ctx.final_wrapper(original)
        b._keepalive.extend([hit, calculation, final, calls])
        def finish():
            return callback(ctypes.addressof(calls), ctypes.addressof(final), ctypes.addressof(hit), 0)
        return ctx, hit, calculation, final, calls, finish

    def test_ap_stage_is_cache_only_and_final_joins_distinct_values_buffer_once(self):
        with bridge.OwnedBridge() as b:
            ctx, hit, calculation, final, calls, finish = self.fixture(b)
            self.assertEqual(ctx.begin(hit), 1)
            ctx.ap_stage(hit, calculation, selected_ap=5, armour=4, factor=0.65)
            self.assertEqual(ctx.state()["phase"], context.STAGED)
            self.assertEqual(b.stats()["accepted"], 0)
            self.assertEqual(b.drain(), [])
            ctypes.memmove(final, calculation, 0x24)
            self.assertNotEqual(ctypes.addressof(final), ctypes.addressof(calculation))
            self.assertEqual(finish(), 0xFEDCBA9876543210)
            self.assertEqual(finish(), 0xFEDCBA9876543210)
            records = b.drain()
            self.assertEqual(len(records), 1)
            self.assertEqual((records[0].selected_ap, records[0].armour, records[0].ap_delta), (5, 4, 1))
            self.assertEqual(records[0].capture_flags, 0x8C)  # no inferred mode/hostile/default/force known
            self.assertEqual(calls.value, 2)

    def test_native_subss_keeps_threshold_rounding_not_python_double(self):
        with bridge.OwnedBridge() as b:
            ctx, hit, calculation, final, calls, finish = self.fixture(b)
            ctx.begin(hit)
            ctypes.c_float.from_buffer(hit, 0x50).value = 2**-26
            ctx.ap_stage(hit, calculation, selected_ap=1.0, armour=2**-26, factor=1.0)
            ctypes.memmove(final, calculation, 0x24)
            ctypes.c_float.from_buffer(hit, 0x50).value = 2**-26
            finish()
            record = b.drain()[0]
            self.assertLess(float(record.selected_ap) - float(record.armour), 1)
            self.assertEqual(record.ap_delta, 1.0)

    def test_same_pointer_new_contact_clears_ap_and_does_not_reuse_old_stage(self):
        with bridge.OwnedBridge() as b:
            ctx, hit, calculation, final, calls, finish = self.fixture(b)
            ctx.begin(hit)
            ctx.ap_stage(hit, calculation, selected_ap=5, armour=4, factor=1)
            ctypes.memmove(final, calculation, 0x24)
            finish()
            self.assertEqual(ctx.begin(hit), 2)
            finish()  # second contact had no verified AP stage, kept unknown
            first, second = b.drain()
            self.assertEqual((first.contact_ordinal, second.contact_ordinal), (1, 2))
            self.assertEqual(first.capture_flags, 0x8C)
            self.assertEqual(second.capture_flags, 0)

    def test_other_thread_cannot_join_or_submit_owner_context(self):
        with bridge.OwnedBridge() as b:
            ctx, hit, calculation, final, calls, finish = self.fixture(b)
            ctx.begin(hit)
            thread = threading.Thread(target=lambda: (ctx.ap_stage(hit, calculation, selected_ap=6, armour=4, factor=1), finish()))
            thread.start(); thread.join()
            self.assertEqual(b.stats()["accepted"], 0)
            self.assertEqual(ctx.record.capture_flags, 0)
            self.assertEqual(calls.value, 1)  # original preserved on rejected observation
            ctx.ap_stage(hit, calculation, selected_ap=5, armour=4, factor=1)
            ctypes.memmove(final, calculation, 0x24)
            finish()
            self.assertEqual(len(b.drain()), 1)

    def test_pending_reentrant_begin_is_ambiguous_not_a_false_pair(self):
        with bridge.OwnedBridge() as b:
            ctx, hit, calculation, final, calls, finish = self.fixture(b)
            ctx.begin(hit)
            self.assertEqual(ctx.begin(hit), 0)
            ctx.ap_stage(hit, calculation, selected_ap=5, armour=4, factor=1)
            finish()
            self.assertEqual(b.drain(), [])
            self.assertEqual(ctx.state()["phase"], context.AMBIGUOUS)
            self.assertGreater(ctx.state()["rejected"], 0)
            ctx.reset_after_owned_calls_return()
            self.assertEqual(ctx.begin(hit), 2)

    def test_unknown_custom_force_hostility_mode_are_not_silently_proved(self):
        with bridge.OwnedBridge() as b:
            ctx, hit, calculation, final, calls, finish = self.fixture(b)
            ctx.begin(hit)
            hit[0x73] = 1
            ctx.ap_stage(hit, calculation, selected_ap=5, armour=4, factor=1)
            ctypes.memmove(final, calculation, 0x24)
            finish()
            record = b.drain()[0]
            self.assertEqual(record.effect_flags & 1, 1)
            self.assertEqual(record.target_kind, 0)
            self.assertEqual(record.capture_flags & (0x10|0x20|0x40|0x100), 0)

    def test_same_pointer_identity_mutation_invalidates_ap_join(self):
        for offset, value in [(0x20, 1002), (0x100, 99), (0, 4), (0x50, 0x40800001)]:
            with self.subTest(offset=offset), bridge.OwnedBridge() as b:
                ctx, hit, calculation, final, calls, finish = self.fixture(b)
                ctx.begin(hit)
                ctx.ap_stage(hit, calculation, selected_ap=5, armour=4, factor=1)
                ctypes.memmove(final, calculation, 0x24)
                ctypes.c_uint32.from_buffer(hit, offset).value = value
                finish()
                record = b.drain()[0]
                self.assertEqual(record.capture_flags, 0)
                self.assertEqual(calls.value, 1)
                self.assertEqual(ctx.state()["rejected"], 1)

    def test_curve_marker_is_same_contact_not_a_factor_guess_or_event(self):
        with bridge.OwnedBridge() as b:
            ctx, hit, calculation, final, calls, finish = self.fixture(b)
            self.assertEqual(ctx.curve_marker(hit, custom=False), 0)
            ctx.begin(hit)
            self.assertEqual(ctx.curve_marker(hit, custom=False), 1)
            ctx.ap_stage(hit, calculation, selected_ap=5, armour=4, factor=1)
            self.assertEqual(b.stats()["accepted"], 0)
            ctypes.memmove(final, calculation, 0x24)
            finish()
            record = b.drain()[0]
            self.assertEqual(record.capture_flags, 0x9C)
            self.assertEqual(record.effect_flags & 4, 0)
            ctx.begin(hit)
            ctx.curve_marker(hit, custom=True)
            ctx.ap_stage(hit, calculation, selected_ap=5, armour=4, factor=1)
            ctypes.memmove(final, calculation, 0x24)
            finish()
            record = b.drain()[0]
            self.assertEqual(record.capture_flags, 0x9C)
            self.assertEqual(record.effect_flags & 4, 4)

    def test_curve_marker_rejects_other_thread_hit_and_conflicting_branches(self):
        with bridge.OwnedBridge() as b:
            ctx, hit, calculation, final, calls, finish = self.fixture(b)
            ctx.begin(hit)
            other = (ctypes.c_uint8 * 0x118)()
            self.assertEqual(ctx.curve_marker(other, custom=False), 0)
            result = []
            thread = threading.Thread(target=lambda: result.append(ctx.curve_marker(hit, custom=False)))
            thread.start(); thread.join()
            self.assertEqual(result, [0])
            self.assertEqual(ctx.record.capture_flags, 0)
            self.assertEqual(ctx.curve_marker(hit, custom=False), 1)
            self.assertEqual(ctx.curve_marker(hit, custom=False), 1)
            self.assertEqual(ctx.curve_marker(hit, custom=True), 0)
            self.assertEqual(ctx.state()["phase"], context.AMBIGUOUS)
            finish()
            self.assertEqual(b.drain(), [])
            self.assertEqual(calls.value, 1)

    def test_certified_e8_caller_retains_projectile_row_and_observes_raw_force(self):
        with bridge.OwnedBridge() as b:
            ctx, hit, calculation, final, calls, finish = self.fixture(b)
            original = b._procedure(bytes.fromhex("48 ff 01 48 b8 10 32 54 76 98 ba dc fe c3"),
                ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p)
            observer = ctx.final_wrapper(original, extra_arg_types=(ctypes.c_uint64, ctypes.c_void_p),
                                         projectile_info_from_entry_rax=True)
            caller = installation.OwnedE8Callsite(b, original, projectile_info_from_sixth_arg=True)
            row = (ctypes.c_uint8 * 0x100)()
            args = (ctypes.addressof(calls), ctypes.addressof(final), ctypes.addressof(hit), 0, 9,
                    ctypes.addressof(row))
            caller.install(observer)
            for force, expected in [(0x80, 0), (1, 2), (0, 1)]:
                ctx.begin(hit)
                ctx.curve_marker(hit, custom=False)
                hit[0x73] = 1 if expected == 1 else 0
                row[0xFC] = force
                ctx.ap_stage(hit, calculation, selected_ap=5, armour=4, factor=1)
                ctypes.memmove(final, calculation, 0x24)
                self.assertEqual(caller.invoke(*args), 0xFEDCBA9876543210)
                record = b.drain()[0]
                self.assertEqual(record.capture_flags, 0xBC)
                self.assertEqual(record.effect_flags, expected)
                self.assertEqual(record.target_kind, 0)
                self.assertEqual(record.capture_flags & (0x40|0x100), 0)
            self.assertTrue(caller.restore())
            self.assertEqual(calls.value, 3)

    def test_standard_ffi_wrapper_does_not_read_entry_rax_as_a_projectile_row(self):
        with bridge.OwnedBridge() as b:
            ctx, hit, calculation, final, calls, finish = self.fixture(b)
            ctx.begin(hit)
            ctx.curve_marker(hit, custom=False)
            ctx.ap_stage(hit, calculation, selected_ap=5, armour=4, factor=1)
            ctypes.memmove(final, calculation, 0x24)
            finish()
            self.assertEqual(b.drain()[0].capture_flags & 0x20, 0)

    def test_new_context_procedures_have_real_unwind_for_body_and_each_epilog_pc(self):
        with bridge.OwnedBridge() as b:
            ctx = context.OwnedContactContext(b)
            for procedure, prolog, frame, pushes, tail_bytes in [
                (ctx._begin, 6, 40, ("rsi", "rdi"), 7),
                (ctx._curve, 7, 32, ("rbx", "rsi", "rdi"), 8),
                (ctx._stage, 9, 296, ("rsi", "rdi"), 10)]:
                size = len(b._procedures[int(ctypes.cast(procedure, ctypes.c_void_p).value)]["code"])
                self.assert_unwind(b, procedure, pc=prolog, pushes=pushes, frame=frame)
                self.assert_unwind(b, procedure, pc=size-tail_bytes, pushes=pushes, frame=frame)
                add_size = 7 if frame == 296 else 4
                for count in range(len(pushes) + 1):
                    popped = tuple(reversed(pushes))[:count]
                    # frame has been restored here, even before the first POP.
                    self.assert_unwind(b, procedure, pc=size-tail_bytes+add_size+count,
                        pushes=pushes, frame=0, popped=popped)
            self.assert_unwind(b, ctx._caller, pc=23, pushes=("rbx", "rdi"), frame=88,
                               xmm_saves=((6, 32), (9, 48), (10, 64)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
