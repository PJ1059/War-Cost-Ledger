"""Run only in this Python process; never resolve/read/write game processes."""
import ctypes
import importlib.util
import platform
import sys
import threading
import unittest
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "tools/native/hit_bridge_owned.py"
spec = importlib.util.spec_from_file_location("ledger_owned_hit_bridge", path)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)


@unittest.skipUnless(platform.system() == "Windows" and ctypes.sizeof(ctypes.c_void_p) == 8, "Windows x64 owned pages")
class NativeOwnedQueueTests(unittest.TestCase):
    @staticmethod
    def _normal_fixture(b, *, peer=None):
        hit = (ctypes.c_uint8 * 0x118)()
        values = (ctypes.c_uint8 * 0x24)()
        for at, n in [(0, 4), (0x20, 0xF123ABCD), (0x100, 0x99887766)]:
            ctypes.c_uint32.from_buffer(hit, at).value = n
        ctypes.c_uint64.from_buffer(hit, 0x110).value = b.local_peer if peer is None else peer
        ctypes.c_float.from_buffer(hit, 0x50).value = 5.0
        hit[0x73] = 1
        ctypes.c_float.from_buffer(values, 0).value = 120.0
        ctypes.c_float.from_buffer(values, 4).value = 0.65
        calls = (ctypes.c_uint64 * 5)()
        # Original fixture mutates factor after observing exact arguments and returns
        # opaque RAX plus XMM0=5.25. Fifth argument is read from the original stack.
        code = bytes.fromhex("48 ff 01 48 89 51 08 4c 89 41 10 4c 89 49 18 "
            "48 8b 44 24 28 48 89 41 20 c7 42 04 00 00 00 40 "
            "b8 00 00 a8 40 66 0f 6e c0 0f 5a c0 "
            "48 b8 10 32 54 76 98 ba dc fe c3")
        original = b._procedure(code, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p,
                                ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint64)
        return hit, values, calls, original

    def test_all_fields_roundtrip_and_native_sequence(self):
        with bridge.OwnedBridge(capacity=3) as b:
            src = b.record(sequence=0xDEADBEEF, projectile_context=0xDEADBEEF12345678,
                projectile_slot=812, projectile_generation=7, contact_ordinal=3,
                target=0xF102ABCD, source=50, owner=51, effect_flags=9,
                native_branch=4, selected_ap=5.0, armour=4.0, factor=1.0,
                damage=123.5, attack_kind=2, target_kind=6, capture_flags=0xAABBCCDD)
            self.assertEqual(b.publish(src), 1)
            got = b.drain()[0]
            self.assertEqual(got.sequence, 1)
            self.assertEqual(bytes(got)[8:], bytes(src)[8:])
            self.assertEqual(b.stats()["accepted"], 1)

    def test_exact_u64_peer_filter_above_lua_precision(self):
        with bridge.OwnedBridge(local_peer=2**63 + 123) as b:
            self.assertEqual(b.publish(b.record(creditor=2**63 + 124)), 2)
            self.assertEqual(b.publish(b.record(creditor=2**63 + 123)), 1)
            self.assertEqual(len(b.drain()), 1)
            self.assertEqual(b.stats()["filtered"], 1)

    def test_repeated_target_is_not_deduplicated(self):
        with bridge.OwnedBridge(capacity=4) as b:
            for contact in (1, 2, 3):
                self.assertEqual(b.publish(b.record(target=101, contact_ordinal=contact)), 1)
            records = b.drain()
            self.assertEqual([r.target for r in records], [101, 101, 101])
            self.assertEqual([r.contact_ordinal for r in records], [1, 2, 3])

    def test_native_leaf_preserves_nonvolatile_registers_it_uses(self):
        with bridge.OwnedBridge() as b:
            # Own x64 caller supplies normal 32B shadow space and stack alignment.
            # The publisher uses RSI/RDI; prove both survive the native call.
            c = bridge._Code()
            c.emit("56 57 48 83 ec 28")
            c.emit("48 be 88 77 66 55 44 33 22 11")
            c.emit("48 bf 10 32 54 76 98 ba dc fe")
            target = int(ctypes.cast(b.publisher, ctypes.c_void_p).value)
            c.emit("48 b8 " + target.to_bytes(8, "little").hex(" ") + " ff d0")
            c.emit("49 ba 88 77 66 55 44 33 22 11 4c 39 d6")
            c.branch("0f 85", "bad")
            c.emit("49 ba 10 32 54 76 98 ba dc fe 4c 39 d7")
            c.branch("0f 85", "bad")
            c.emit("b8 01 00 00 00")
            c.branch("e9", "return")
            c.label("bad")
            c.emit("31 c0")
            c.label("return")
            c.emit("48 83 c4 28 5f 5e c3")
            probe = b._procedure(c.finish(), ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p,
                                 unwind=bytes.fromhex("01060300 0642 0270 0160 0000"))
            record = b.record()
            self.assertEqual(probe(b.base, ctypes.addressof(record)), 1)
            self.assertEqual(len(b.drain()), 1)

    def test_native_queue_dynamic_unwind_lookup_and_stack(self):
        with bridge.OwnedBridge() as b:
            for function, code in [(b.publisher, bridge.publish_code()), (b.consumer, bridge.drain_code())]:
                image, entry = b.unwind_lookup(function, 2)
                self.assertEqual(image, ctypes.cast(function, ctypes.c_void_p).value)
                self.assertEqual((entry.contents.BeginAddress, entry.contents.EndAddress, entry.contents.UnwindData),
                                 (0, len(code), 0x800))
                for offset, delta, rdi, rsi in [(2,16,False,False), (len(code)-3,16,False,False),
                                               (len(code)-2,8,True,False), (len(code)-1,0,True,True)]:
                    context = b.unwind_fixture(function, offset, stack_delta=delta,
                                               restored_rdi=rdi, restored_rsi=rsi)
                    for register in ("rsp", "rsi", "rdi", "rip"):
                        self.assertEqual(context[register], context["expected_" + register])

    def test_normal_dynamic_unwind_body_and_legal_epilog(self):
        with bridge.OwnedBridge() as b:
            hit, values, calls, original = self._normal_fixture(b)
            context = b.record()
            function = b.owned_normal_wrapper(context, original, extra_arg_types=(ctypes.c_uint64,))
            code = bridge.normal_snapshot_tail_code(bridge_address=b.base,
                publisher_address=ctypes.cast(b.publisher, ctypes.c_void_p).value,
                template_address=ctypes.addressof(context), original_address=ctypes.cast(original, ctypes.c_void_p).value)
            for offset, delta, rdi, rsi in [(9,312,False,False), (len(code)-23,312,False,False),
                (len(code)-16,16,False,False), (len(code)-15,8,True,False), (len(code)-14,0,True,True)]:
                image, entry = b.unwind_lookup(function, offset)
                self.assertEqual(entry.contents.EndAddress, len(code) - 8)
                registers = b.unwind_fixture(function, offset, stack_delta=delta,
                                             restored_rdi=rdi, restored_rsi=rsi)
                for register in ("rsp", "rsi", "rdi", "rip"):
                    self.assertEqual(registers[register], registers["expected_" + register])

    def test_stale_epoch_does_not_join_current_mission(self):
        with bridge.OwnedBridge(epoch=7) as b:
            self.assertEqual(b.publish(b.record(epoch=6)), 2)
            self.assertEqual(b.stats()["lock"], 0)
            self.assertEqual(b.drain(), [])
            self.assertEqual(b.publish(b.record()), 1)

    def test_full_queue_drops_without_overwrite_and_wraps(self):
        with bridge.OwnedBridge(capacity=3) as b:
            for i in range(3): self.assertEqual(b.publish(b.record(target=i + 1)), 1)
            self.assertEqual(b.publish(b.record(target=999)), 0)
            self.assertEqual([r.target for r in b.drain(2)], [1, 2])
            for i in range(2): self.assertEqual(b.publish(b.record(target=i + 4)), 1)
            got = b.drain()
            self.assertEqual([r.target for r in got], [3, 4, 5])
            self.assertEqual([r.sequence for r in got], [3, 4, 5])
            self.assertEqual(b.stats()["dropped"], 1)
            self.assertEqual(b.stats()["count"], 0)

    def test_drain_has_native_64_record_ceiling(self):
        with bridge.OwnedBridge(capacity=80) as b:
            for i in range(80): b.publish(b.record(target=i))
            self.assertEqual(b.drain(0), [])
            self.assertEqual(len(b.drain(2**32 - 1)), 64)
            self.assertEqual(len(b.drain()), 16)

    def test_one_try_lock_contention_is_explicit_and_nonblocking(self):
        with bridge.OwnedBridge() as b:
            ctypes.c_uint32.from_address(b.base + 24).value = 1
            self.assertEqual(b.publish(b.record()), 0)
            self.assertEqual(b.drain(), [])
            self.assertEqual(b.stats()["dropped"], 1)
            self.assertEqual(b.stats()["lock"], 1)
            ctypes.c_uint32.from_address(b.base + 24).value = 0
            self.assertEqual(b.publish(b.record()), 1)

    def test_parallel_producers_unique_records_or_reported_drops(self):
        with bridge.OwnedBridge(capacity=1024) as b:
            accepted = []
            result_lock = threading.Lock()
            def producer(start):
                local = []
                for n in range(80):
                    target = start + n
                    if b.publish(b.record(target=target)) == 1: local.append(target)
                with result_lock: accepted.extend(local)
            threads = [threading.Thread(target=producer, args=(i * 1000,)) for i in range(4)]
            for t in threads: t.start()
            for t in threads: t.join()
            got = []
            while b.stats()["count"]: got.extend(b.drain())
            self.assertEqual(sorted(r.target for r in got), sorted(accepted))
            self.assertEqual([r.sequence for r in got], list(range(1, len(got) + 1)))
            self.assertEqual(b.stats()["accepted"] + b.stats()["dropped"], 320)

    def test_new_epoch_separate_queue_and_close_refuse_calls(self):
        b = bridge.OwnedBridge(epoch=8)
        b.publish(b.record())
        b.close()
        with self.assertRaises(ValueError): b.publish(bridge.Record())
        with self.assertRaises(ValueError): b.drain()
        with self.assertRaises(ValueError): b.stats()
        with bridge.OwnedBridge(epoch=9) as new:
            self.assertEqual(new.drain(), [])
            self.assertEqual(new.publish(new.record()), 1)
            self.assertEqual(new.drain()[0].sequence, 1)

    def test_normal_snapshot_tail_preserves_original_arguments_and_returns(self):
        with bridge.OwnedBridge() as b:
            hit, values, calls, original = self._normal_fixture(b)
            context = b.record(source=123, selected_ap=7.25, capture_flags=0xC001)
            wrapper = b.owned_normal_wrapper(context, original, extra_arg_types=(ctypes.c_uint64,))
            result = wrapper(ctypes.addressof(calls), ctypes.addressof(values), ctypes.addressof(hit),
                             0x12345678, 0xABCDEF9876543210)
            self.assertEqual(result, 0xFEDCBA9876543210)
            self.assertEqual(list(calls), [1, ctypes.addressof(values), ctypes.addressof(hit),
                                         0x12345678, 0xABCDEF9876543210])
            self.assertEqual(ctypes.c_float.from_buffer(values, 4).value, 2.0)
            record = b.drain()[0]
            self.assertAlmostEqual(record.factor, 0.65, places=6)
            self.assertEqual((record.creditor, record.target, record.owner, record.attack_kind),
                             (b.local_peer, 0xF123ABCD, 0x99887766, 4))
            self.assertEqual((record.armour, record.damage, record.source, record.selected_ap), (5.0, 120.0, 123, 7.25))
            self.assertEqual(record.effect_flags & 1, 1)
            self.assertEqual(record.capture_flags, 0xC001)  # no invented proof/hostility
            hit[0x73] = 0
            context.effect_flags = 1  # prior template force must not leak into new snapshot
            float_wrapper = b.owned_normal_wrapper(context, original, result_type=ctypes.c_double,
                                                   extra_arg_types=(ctypes.c_uint64,))
            self.assertEqual(float_wrapper(ctypes.addressof(calls), ctypes.addressof(values),
                                          ctypes.addressof(hit), 0, 1), 5.25)
            self.assertEqual(calls[0], 2)
            self.assertEqual(b.drain()[0].effect_flags & 1, 0)

    def test_normal_filter_or_overflow_never_blocks_original_call(self):
        with bridge.OwnedBridge(capacity=1) as b:
            hit, values, calls, original = self._normal_fixture(b, peer=b.local_peer - 1)
            wrapper = b.owned_normal_wrapper(b.record(), original, extra_arg_types=(ctypes.c_uint64,))
            args = (ctypes.addressof(calls), ctypes.addressof(values), ctypes.addressof(hit), 0, 1)
            self.assertEqual(wrapper(*args), 0xFEDCBA9876543210)
            self.assertEqual((calls[0], b.stats()["filtered"], b.stats()["count"]), (1, 1, 0))
            ctypes.c_uint64.from_buffer(hit, 0x110).value = b.local_peer
            wrapper(*args)
            wrapper(*args)
            self.assertEqual((calls[0], b.stats()["dropped"], b.stats()["count"]), (3, 1, 1))


if __name__ == "__main__":
    unittest.main(verbosity=2)
