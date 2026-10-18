"""Reversible E8 experiment on OwnedBridge pages only; no game installer.

The fixture owns every invocation and serializes invocation/mutation itself.
This is NOT evidence that a running game can be patched without thread safety.
"""
import ctypes
import struct
import threading


def rel32_call(call_address, target_address):
    delta = target_address - (call_address + 5)
    if not -(2**31) <= delta < 2**31:
        raise ValueError("owned call target is outside rel32 range")
    return b"\xE8" + struct.pack("<i", delta)


class OwnedE8Callsite:
    def __init__(self, bridge, original, *, projectile_info_from_sixth_arg=False):
        self.bridge = bridge
        self.original_address = int(ctypes.cast(original, ctypes.c_void_p).value)
        if bridge.closed or self.original_address not in bridge._procedures:
            raise ValueError("original must be a live owned procedure")
        self._gate = threading.Lock()
        self.installed = False
        self.patch_offset = 19 if projectile_info_from_sixth_arg else 14
        # Normal caller frame, including forwarding of a fifth stack argument.
        prefix = "48 83 ec 28 48 8b 44 24 50 48 89 44 24 20"
        if projectile_info_from_sixth_arg:
            prefix += " 48 8b 44 24 58"  # actual caller invariant: owned row survives in RAX at E8
        body = bytes.fromhex(prefix + " e8 00 00 00 00 48 83 c4 28 c3")
        extra_types = (ctypes.c_void_p,) if projectile_info_from_sixth_arg else ()
        self._entry = bridge._procedure(body, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p,
            ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint64, *extra_types,
            unwind=bytes.fromhex("01040100 0442 0000"))
        self.address = int(ctypes.cast(self._entry, ctypes.c_void_p).value)
        self.call_address = self.address + self.patch_offset
        self.original_bytes = rel32_call(self.call_address, self.original_address)
        self.installed_bytes = None
        self._write_exact(b"\xE8" + b"\0" * 4, self.original_bytes)

    def _write_exact(self, expected, replacement):
        b = self.bridge
        if b.closed or self.address not in b._procedures or len(expected) != 5 or len(replacement) != 5:
            raise ValueError("only the owned whole E8 instruction may be changed")
        if ctypes.string_at(self.call_address, 5) != expected:
            raise ValueError("owned instruction mismatch; no write")
        previous = ctypes.c_uint32()
        if not b.kernel.VirtualProtect(self.address, 4096, 4, ctypes.byref(previous)):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            ctypes.memmove(self.call_address, replacement, 5)
            if ctypes.string_at(self.call_address, 5) != replacement:
                ctypes.memmove(self.call_address, expected, 5)
                raise RuntimeError("owned call write did not read back")
        finally:
            old = ctypes.c_uint32()
            if not b.kernel.VirtualProtect(self.address, 4096, previous.value, ctypes.byref(old)):
                raise ctypes.WinError(ctypes.get_last_error())
        if not b.kernel.FlushInstructionCache(b.kernel.GetCurrentProcess(), self.call_address, 5):
            raise ctypes.WinError(ctypes.get_last_error())

    def invoke(self, *arguments):
        with self._gate:
            if self.bridge.closed:
                raise ValueError("closed bridge")
            return self._entry(*arguments)

    def install(self, observer):
        address = int(ctypes.cast(observer, ctypes.c_void_p).value)
        with self._gate:
            if self.installed or address not in self.bridge._procedures:
                raise ValueError("already installed or observer not owned")
            replacement = rel32_call(self.call_address, address)
            self._write_exact(self.original_bytes, replacement)
            self.installed_bytes = replacement
            self.installed = True

    def restore(self):
        with self._gate:
            if not self.installed:
                return False
            # A third party's changed bytes must never be overwritten.
            self._write_exact(self.installed_bytes, self.original_bytes)
            self.installed = False
            return True

    def fixture_alter_owned_instruction(self, replacement):
        """Only an owned test simulating another writer, never a live API."""
        with self._gate:
            current = ctypes.string_at(self.call_address, 5)
            self._write_exact(current, replacement)
