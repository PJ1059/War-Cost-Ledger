import ctypes
import importlib.util
import sys
import unittest
from pathlib import Path

folder = Path(__file__).resolve().parents[1] / "tools/native"
sys.path.insert(0, str(folder))
import hit_bridge_owned as bridge
import hit_bridge_install_owned as installation


class OwnedInstallTests(unittest.TestCase):
    @staticmethod
    def fixture(b):
        # Leaf original counts natural calls and returns an opaque full-u64 value.
        original = b._procedure(bytes.fromhex("48 ff 01 48 b8 10 32 54 76 98 ba dc fe c3"),
            ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
            ctypes.c_uint64, ctypes.c_uint64)
        calls = ctypes.c_uint64()
        hit = (ctypes.c_uint8 * 0x118)()
        values = (ctypes.c_uint8 * 0x24)()
        ctypes.c_uint64.from_buffer(hit, 0x110).value = b.local_peer
        context = b.record()
        b._keepalive.extend([calls, hit, values])
        observer = b.owned_normal_wrapper(context, original, extra_arg_types=(ctypes.c_uint64,))
        caller = installation.OwnedE8Callsite(b, original)
        args = (ctypes.addressof(calls), ctypes.addressof(values), ctypes.addressof(hit), 0, 1)
        return calls, context, observer, caller, args

    def test_real_owned_install_invocation_and_restore(self):
        with bridge.OwnedBridge() as b:
            calls, context, observer, caller, args = self.fixture(b)
            self.assertEqual(caller.invoke(*args), 0xFEDCBA9876543210)
            self.assertEqual(b.drain(), [])
            original = ctypes.string_at(caller.call_address, 5)
            caller.install(observer)
            self.assertNotEqual(ctypes.string_at(caller.call_address, 5), original)
            self.assertEqual(caller.invoke(*args), 0xFEDCBA9876543210)
            self.assertEqual(len(b.drain()), 1)
            self.assertTrue(caller.restore())
            self.assertEqual(ctypes.string_at(caller.call_address, 5), original)
            self.assertEqual(caller.invoke(*args), 0xFEDCBA9876543210)
            self.assertEqual(b.drain(), [])
            self.assertEqual(calls.value, 3)
            image, entry = b.unwind_lookup(caller._entry, 4)
            self.assertEqual(image, caller.address)
            self.assertEqual(entry.contents.EndAddress, 24)

    def test_changed_instruction_refuses_install_and_restore(self):
        with bridge.OwnedBridge() as b:
            calls, context, observer, caller, args = self.fixture(b)
            changed = b"\xE8\x01\x00\x00\x00"
            caller.fixture_alter_owned_instruction(changed)
            with self.assertRaises(ValueError): caller.install(observer)
            self.assertEqual(ctypes.string_at(caller.call_address, 5), changed)
            caller.fixture_alter_owned_instruction(caller.original_bytes)
            caller.install(observer)
            installed = caller.installed_bytes
            caller.fixture_alter_owned_instruction(changed)
            with self.assertRaises(ValueError): caller.restore()
            self.assertEqual(ctypes.string_at(caller.call_address, 5), changed)
            caller.fixture_alter_owned_instruction(installed)
            self.assertTrue(caller.restore())

    def test_foreign_or_data_address_and_out_of_range_refused(self):
        with bridge.OwnedBridge() as b:
            calls, context, observer, caller, args = self.fixture(b)
            before = ctypes.string_at(caller.call_address, 5)
            with self.assertRaises(ValueError): caller.install(ctypes.c_void_p(b.base))
            with self.assertRaises(ValueError): caller.install(ctypes.c_void_p(1))
            with self.assertRaises(ValueError): installation.rel32_call(caller.call_address, caller.call_address + 2**31 + 5)
            self.assertEqual(ctypes.string_at(caller.call_address, 5), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
