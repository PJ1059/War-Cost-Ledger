"""Owned-process x64 queue experiment, not a game connector.

Only VirtualAlloc/VirtualProtect/FlushInstructionCache on this Python process.
No process lookup, external reads/writes, hook installation or DLL injection.
The two leaf procedures implement a bounded try-lock queue. Contention drops
are reported, so success here never implies a complete gameplay event stream.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import platform
import struct
from pathlib import Path

ABI = 1
RECORD_SIZE = 96
HEADER_SIZE = 64
MAX_CAPACITY = 1024
MAX_DRAIN = 64
PUSH_SI_DI_UNWIND = bytes.fromhex("01020200 0270 0160")
NORMAL_UNWIND = bytes.fromhex("01090400 09012500 0270 0160")


class RuntimeFunction(ctypes.Structure):
    _fields_ = [("BeginAddress", ctypes.c_uint32), ("EndAddress", ctypes.c_uint32),
                ("UnwindData", ctypes.c_uint32)]


assert ctypes.sizeof(RuntimeFunction) == 12


class Record(ctypes.Structure):
    _fields_ = [
        ("sequence", ctypes.c_uint64),
        ("epoch", ctypes.c_uint64),
        ("creditor", ctypes.c_uint64),
        ("projectile_context", ctypes.c_uint64),
        ("projectile_slot", ctypes.c_uint32),
        ("projectile_generation", ctypes.c_uint32),
        ("contact_ordinal", ctypes.c_uint32),
        ("target", ctypes.c_uint32),
        ("source", ctypes.c_uint32),
        ("owner", ctypes.c_uint32),
        ("effect_flags", ctypes.c_uint32),
        ("native_branch", ctypes.c_uint32),
        ("selected_ap", ctypes.c_float),
        ("armour", ctypes.c_float),
        ("factor", ctypes.c_float),
        ("damage", ctypes.c_float),
        ("attack_kind", ctypes.c_uint32),
        ("target_kind", ctypes.c_uint32),
        ("capture_flags", ctypes.c_uint32),
        ("ap_delta", ctypes.c_float),
    ]


assert ctypes.sizeof(Record) == RECORD_SIZE
assert Record.creditor.offset == 16 and Record.selected_ap.offset == 64


class _Code:
    def __init__(self):
        self.code = bytearray()
        self.labels = {}
        self.fixups = []

    def emit(self, hex_bytes):
        self.code.extend(bytes.fromhex(hex_bytes))

    def label(self, name):
        assert name not in self.labels
        self.labels[name] = len(self.code)

    def branch(self, opcode, target):
        self.emit(opcode)
        self.fixups.append((len(self.code), target))
        self.code.extend(b"\0" * 4)

    def finish(self):
        for at, target in self.fixups:
            struct.pack_into("<i", self.code, at, self.labels[target] - (at + 4))
        return bytes(self.code)


def publish_code():
    """uint32 publish(header RCX, record RDX): 1 accepted, 2 filtered, 0 drop."""
    c = _Code()
    c.emit("56 57")                 # preserve RSI/RDI; no nested calls
    c.emit("48 8b 42 10 48 3b 41 10")  # record.creditor == header.local_peer, full u64
    c.branch("0f 85", "filtered")
    c.emit("31 c0 41 b8 01 00 00 00 f0 44 0f b1 41 18")  # one lock cmpxchg
    c.branch("0f 85", "dropped")
    c.emit("48 8b 42 08 48 3b 41 08")  # record epoch matches active header epoch
    c.branch("0f 85", "stale")
    c.emit("8b 41 1c 3b 41 04")       # count < capacity
    c.branch("0f 83", "full")
    c.emit("44 8b 41 24 4d 6b c0 60")  # R8 = tail * 96
    c.emit("4a 8d 7c 01 40 48 89 d6 49 89 c9")  # dest=header+64+R8, source=RDX, save RCX
    c.emit("b9 0c 00 00 00 fc f3 48 a5 4c 89 c9")  # fixed 12 qwords; restore header
    c.emit("48 ff 41 28 48 8b 41 28 4a 89 44 01 40")  # ++accepted, publish sequence into copied slot
    c.emit("8b 41 24 ff c0 3b 41 04")
    c.branch("0f 82", "tail_ready")
    c.emit("31 c0")
    c.label("tail_ready")
    c.emit("89 41 24 ff 41 1c c7 41 18 00 00 00 00 b8 01 00 00 00")
    c.branch("e9", "return")
    c.label("stale")
    c.emit("c7 41 18 00 00 00 00")
    c.label("filtered")
    c.emit("f0 48 ff 41 38 b8 02 00 00 00")
    c.branch("e9", "return")
    c.label("full")
    c.emit("c7 41 18 00 00 00 00")
    c.label("dropped")
    c.emit("f0 48 ff 41 30 31 c0")
    c.label("return")
    c.emit("5f 5e c3")
    return c.finish()


def drain_code():
    """uint32 drain(header RCX, owned output RDX, requested R8D), <=64 records."""
    c = _Code()
    c.emit("56 57")
    c.emit("45 85 c0")
    c.branch("0f 84", "empty")
    c.emit("41 83 f8 40")
    c.branch("0f 86", "bounded")
    c.emit("41 b8 40 00 00 00")
    c.label("bounded")
    c.emit("31 c0 41 ba 01 00 00 00 f0 44 0f b1 51 18")
    c.branch("0f 85", "empty")
    c.emit("44 8b 51 1c 45 3b c2")
    c.branch("0f 86", "count_ready")
    c.emit("45 89 d0")
    c.label("count_ready")
    c.emit("45 31 db 45 85 c0")
    c.branch("0f 84", "unlock")
    c.emit("49 89 c9")               # R9 is header across REP MOVSQ
    c.label("loop")
    c.emit("8b 41 20 48 6b c0 60 48 8d 74 01 40 48 89 d7")
    c.emit("b9 0c 00 00 00 fc f3 48 a5 4c 89 c9 48 83 c2 60")
    c.emit("8b 41 20 ff c0 3b 41 04")
    c.branch("0f 82", "head_ready")
    c.emit("31 c0")
    c.label("head_ready")
    c.emit("89 41 20 41 ff c3 41 ff c8")
    c.branch("0f 85", "loop")
    c.emit("44 29 59 1c")             # count -= number copied
    c.label("unlock")
    c.emit("c7 41 18 00 00 00 00 44 89 d8")
    c.branch("e9", "return")
    c.label("empty")
    c.emit("31 c0")
    c.label("return")
    c.emit("5f 5e c3")
    return c.finish()


def normal_snapshot_tail_code(*, bridge_address, publisher_address, template_address, original_address,
                              context_guard=False, get_thread_id_address=None,
                              projectile_info_from_entry_rax=False, certified_contact_profile=False,
                              qualifier_address=None, entity_manager_address=None):
    """Owned fixture for the observed normal-final four register arguments.

    RCX is opaque original arg1, RDX final DamageValues, R8 HitInfo, R9 arg4.
    Snapshot before original call, then restore incoming stack/registers
    and tail-jump to the owned original. No return type or extra stack arguments
    are guessed. This function emits no game connection/patching instructions.
    Selected AP/custom/hostility validity must come from a proved contact context;
    the wrapper does not infer them from factor or target ID.
    """
    c = _Code()
    # Canonical Windows unwindable prolog/epilog; no POPFQ in the epilog.
    # Incoming arithmetic flags are caller-clobbered at a normal CALL. The
    # actual original callee itself SUBs its stack before using any condition.
    c.emit("56 57 48 81 ec 28 01 00 00")
    saved = ["48 89 84 24 80 00 00 00", "48 89 8c 24 88 00 00 00",
             "48 89 94 24 90 00 00 00", "4c 89 84 24 98 00 00 00",
             "4c 89 8c 24 a0 00 00 00", "4c 89 94 24 a8 00 00 00",
             "4c 89 9c 24 b0 00 00 00"]
    for instruction in saved:
        c.emit(instruction)
    for xmm in range(6):
        c.emit("0f 29 " + bytes([0x84 + xmm * 8, 0x24]).hex(" ")
               + " " + (192 + 16 * xmm).to_bytes(4, "little").hex(" "))
    if context_guard:
        if not get_thread_id_address:
            raise ValueError("context replay requires the real owned-process thread identity getter")
        c.emit("48 b8 " + get_thread_id_address.to_bytes(8, "little").hex(" ") + " ff d0")
        c.emit("49 ba " + template_address.to_bytes(8, "little").hex(" "))
        c.emit("41 3b 42 60")  # context.owner_thread (u32), immutable
        c.branch("0f 85", "restore_original")
        c.emit("41 83 7a 64 01")
        c.branch("0f 84", "pointer_ready")  # no AP seen: preserve unknown fields, not an AP result
        c.emit("41 83 7a 64 02")
        c.branch("0f 85", "restore_original")
        c.label("pointer_ready")
        c.emit("4c 8b 9c 24 98 00 00 00 4d 3b 5a 68")
        c.branch("0f 85", "restore_original")
        c.emit("41 83 7a 64 01")
        c.branch("0f 84", "phase_ready")
        c.emit("49 8b 83 10 01 00 00 49 3b 42 10")  # AP-stage peer identity still matches
        c.branch("0f 85", "invalidate_stage")
        for load, compare in [("41 8b 43 20", "41 3b 42 2c"),
                              ("41 8b 83 00 01 00 00", "41 3b 42 34"),
                              ("41 8b 03", "41 3b 42 50"),
                              ("41 8b 43 50", "41 3b 42 44")]:
            c.emit(load + " " + compare)
            c.branch("0f 85", "invalidate_stage")
        if certified_contact_profile:
            c.emit("41 8b 83 80 00 00 00 41 3b 42 30")
            c.branch("0f 85", "invalidate_stage")
        c.branch("e9", "phase_ready")
        c.label("invalidate_stage")
        c.emit("41 c7 42 58 00 00 00 00 f0 41 ff 42 78")
        c.label("phase_ready")
        c.emit("41 c7 42 64 03 00 00 00")  # spend contact before publishing, never double-submit
    c.emit("48 be " + template_address.to_bytes(8, "little").hex(" "))
    c.emit("48 8d 7c 24 20 b9 0c 00 00 00 fc f3 48 a5")
    c.emit("4c 8b 94 24 98 00 00 00 4c 8b 9c 24 90 00 00 00")  # original R8/RDX
    c.emit("49 8b 82 10 01 00 00 48 89 44 24 30")  # creditor=HitInfo+110
    c.emit("41 8b 42 20 89 44 24 4c")              # target=HitInfo+20
    if certified_contact_profile:
        c.emit("41 8b 82 80 00 00 00 89 44 24 50")  # same native HI source entity, never stat hash
        c.emit("83 4c 24 78 03")  # exact certified caller profile supplies direct/full-peer proof
    c.emit("41 8b 82 00 01 00 00 89 44 24 54")     # owner=HitInfo+100
    c.emit("41 8b 02 89 44 24 70")                 # attack kind=HitInfo+00, not R9
    c.emit("41 8b 42 50 89 44 24 64")              # armour bits=HitInfo+50
    c.emit("41 8b 43 04 89 44 24 68")              # final factor=DamageValues+04
    c.emit("41 8b 03 89 44 24 6c")                 # final damage=DamageValues+00
    c.emit("83 64 24 58 fe 41 0f b6 42 73 85 c0")  # replace raw force bit, never reuse prior value
    c.branch("0f 84", "force_ready")
    c.emit("83 4c 24 58 01")                       # raw HitInfo-force bit; no AP conclusion
    c.label("force_ready")
    if projectile_info_from_entry_rax:
        # Certified 13AD88B caller profile only: its live RAX still points at
        # the ProjectileInfo row checked at 13AD858. A normal FFI call does NOT
        # have this invariant, so the general wrapper never enables it.
        c.emit("48 8b 84 24 80 00 00 00 83 64 24 58 fd f6 80 fc 00 00 00 01")
        c.branch("0f 84", "projectile_force_ready")
        c.emit("83 4c 24 58 02")
        c.label("projectile_force_ready")
        c.emit("83 4c 24 78 20")  # both raw force inputs observed at final
    c.emit("c7 44 24 5c 01 00 00 00")              # proposal marker: normal-final snapshot
    if certified_contact_profile:
        if not qualifier_address or not entity_manager_address:
            raise ValueError("certified owned profile requires the native owned entity qualifier")
        c.emit("48 b9 " + entity_manager_address.to_bytes(8, "little").hex(" "))
        c.emit("48 8d 54 24 20 48 b8 " + qualifier_address.to_bytes(8, "little").hex(" ") + " ff d0")
    c.emit("48 b9 " + bridge_address.to_bytes(8, "little").hex(" "))
    c.emit("48 8d 54 24 20 48 b8 " + publisher_address.to_bytes(8, "little").hex(" ") + " ff d0")
    c.label("restore_original")
    for xmm in range(6):
        c.emit("0f 28 " + bytes([0x84 + xmm * 8, 0x24]).hex(" ")
               + " " + (192 + 16 * xmm).to_bytes(4, "little").hex(" "))
    for instruction in ["48 8b 84 24 80 00 00 00", "48 8b 8c 24 88 00 00 00",
                        "48 8b 94 24 90 00 00 00", "4c 8b 84 24 98 00 00 00",
                        "4c 8b 8c 24 a0 00 00 00", "4c 8b 94 24 a8 00 00 00",
                        "4c 8b 9c 24 b0 00 00 00"]:
        c.emit(instruction)
    c.emit("48 81 c4 28 01 00 00 5f 5e")
    c.emit("ff 25 00 00 00 00 " + original_address.to_bytes(8, "little").hex(" "))
    return c.finish()


class OwnedBridge:
    """A queue and two code pages owned exclusively by this test process."""
    def __init__(self, *, capacity=32, epoch=1, local_peer=0xFEDCBA9876543210):
        if platform.system() != "Windows" or ctypes.sizeof(ctypes.c_void_p) != 8:
            raise RuntimeError("owned native experiment requires Windows x64")
        if not 1 <= capacity <= MAX_CAPACITY or not 0 < epoch < 2**64 or not 0 < local_peer < 2**64:
            raise ValueError("invalid immutable queue identity or capacity")
        self.capacity, self.epoch, self.local_peer = capacity, epoch, local_peer
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        k = self.kernel
        k.VirtualAlloc.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_uint32]
        k.VirtualAlloc.restype = ctypes.c_void_p
        k.VirtualProtect.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32)]
        k.VirtualProtect.restype = ctypes.c_int
        k.FlushInstructionCache.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
        k.FlushInstructionCache.restype = ctypes.c_int
        k.GetCurrentProcess.restype = ctypes.c_void_p
        k.VirtualFree.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32]
        k.VirtualFree.restype = ctypes.c_int
        self.nt = ctypes.WinDLL("ntdll")
        self.nt.RtlAddFunctionTable.argtypes = [ctypes.POINTER(RuntimeFunction), ctypes.c_uint32, ctypes.c_uint64]
        self.nt.RtlAddFunctionTable.restype = ctypes.c_ubyte
        self.nt.RtlDeleteFunctionTable.argtypes = [ctypes.POINTER(RuntimeFunction)]
        self.nt.RtlDeleteFunctionTable.restype = ctypes.c_ubyte
        self.nt.RtlLookupFunctionEntry.argtypes = [ctypes.c_uint64, ctypes.POINTER(ctypes.c_uint64), ctypes.c_void_p]
        self.nt.RtlLookupFunctionEntry.restype = ctypes.POINTER(RuntimeFunction)
        self.nt.RtlCaptureContext.argtypes = [ctypes.c_void_p]
        self.nt.RtlCaptureContext.restype = None
        self.nt.RtlVirtualUnwind.argtypes = [ctypes.c_uint32, ctypes.c_uint64, ctypes.c_uint64,
            ctypes.POINTER(RuntimeFunction), ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_uint64), ctypes.c_void_p]
        self.nt.RtlVirtualUnwind.restype = ctypes.c_void_p
        self._allocations = []
        self._allocation_sizes = {}
        self._keepalive = []
        self._function_tables = []
        self._procedures = {}
        self.base = self._allocate(HEADER_SIZE + capacity * RECORD_SIZE, executable=False)
        ctypes.memmove(self.base, struct.pack("<IIQQ", ABI, capacity, epoch, local_peer), 24)
        self.publisher = self._procedure(publish_code(), ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p,
                                         unwind=PUSH_SI_DI_UNWIND)
        self.consumer = self._procedure(drain_code(), ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
                                        unwind=PUSH_SI_DI_UNWIND)
        self.closed = False

    def _allocate(self, size, *, executable):
        address = self.kernel.VirtualAlloc(None, size, 0x3000, 4)
        if not address:
            raise ctypes.WinError(ctypes.get_last_error())
        self._allocations.append(address)
        self._allocation_sizes[address] = size
        return address

    def _procedure(self, code, result, *arguments, unwind=None, executable_length=None):
        if not code or len(code) >= 0x800:
            raise ValueError("owned procedure must fit below its unwind metadata")
        address = self._allocate(4096, executable=True)
        ctypes.memmove(address, code, len(code))
        if unwind:
            ctypes.memmove(address + 0x800, unwind, len(unwind))
        previous = ctypes.c_uint32()
        if not self.kernel.VirtualProtect(address, 4096, 0x20, ctypes.byref(previous)):
            raise ctypes.WinError(ctypes.get_last_error())
        if not self.kernel.FlushInstructionCache(self.kernel.GetCurrentProcess(), address, len(code)):
            raise ctypes.WinError(ctypes.get_last_error())
        if unwind:
            entry = RuntimeFunction(0, executable_length or len(code), 0x800)
            if not self.nt.RtlAddFunctionTable(ctypes.byref(entry), 1, address):
                raise RuntimeError("owned dynamic unwind registration failed")
            self._function_tables.append((address, entry))
        self._procedures[address] = {"code": code, "unwind": unwind,
                                     "executable_length": executable_length or len(code)}
        return ctypes.WINFUNCTYPE(result, *arguments)(address)

    def record(self, **values):
        out = Record(epoch=self.epoch, creditor=self.local_peer)
        for name, value in values.items():
            if name not in dict(Record._fields_):
                raise ValueError("unknown record field: " + name)
            setattr(out, name, value)
        return out

    def owned_normal_wrapper(self, context, original, *, result_type=ctypes.c_uint64, extra_arg_types=(),
                             context_guard=False, projectile_info_from_entry_rax=False,
                             certified_contact_profile=False, qualifier=None, entity_manager=None):
        """Never accept a game/external callback address: original must be owned."""
        original_address = int(ctypes.cast(original, ctypes.c_void_p).value)
        if self.closed or not isinstance(context, Record) or original_address not in self._procedures:
            raise ValueError("normal replay requires an owned context and owned original procedure")
        context_address = ctypes.addressof(context)
        if context_guard and not any(base <= context_address and context_address + 128 <= base + size
                for base, size in self._allocation_sizes.items()):
            raise ValueError("guarded context must reside in an owned allocation")
        if projectile_info_from_entry_rax and not context_guard:
            raise ValueError("certified ProjectileInfo caller profile requires a guarded owned contact")
        qualifier_address = int(ctypes.cast(qualifier, ctypes.c_void_p).value or 0) if qualifier else 0
        if certified_contact_profile and (not context_guard or not projectile_info_from_entry_rax
                or qualifier_address not in self._procedures or entity_manager not in self._allocations):
            raise ValueError("certified profile needs guarded contact, exact row caller and live owned native qualifier/map")
        self._keepalive.extend([context, original])
        code = normal_snapshot_tail_code(bridge_address=self.base,
            publisher_address=int(ctypes.cast(self.publisher, ctypes.c_void_p).value),
            template_address=ctypes.addressof(context), original_address=original_address,
            context_guard=context_guard,
            projectile_info_from_entry_rax=projectile_info_from_entry_rax,
            certified_contact_profile=certified_contact_profile,
            qualifier_address=qualifier_address, entity_manager_address=entity_manager,
            get_thread_id_address=int(ctypes.cast(self.kernel.GetCurrentThreadId, ctypes.c_void_p).value)
                                 if context_guard else None)
        return self._procedure(code, result_type, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                               ctypes.c_uint64, *extra_arg_types,
                               unwind=NORMAL_UNWIND, executable_length=len(code)-8)

    def unwind_lookup(self, procedure, offset):
        if self.closed:
            raise ValueError("closed bridge")
        address = int(ctypes.cast(procedure, ctypes.c_void_p).value)
        if address not in self._procedures:
            raise ValueError("unwind lookup requires owned code")
        image = ctypes.c_uint64()
        entry = self.nt.RtlLookupFunctionEntry(address + offset, ctypes.byref(image), None)
        return image.value, entry

    def unwind_fixture(self, procedure, offset, *, stack_delta, restored_rdi=False, restored_rsi=False):
        """Synthetic OWNED stack/CONTEXT only; no running-thread context read."""
        image, entry = self.unwind_lookup(procedure, offset)
        if not entry:
            raise ValueError("owned procedure has no dynamic unwind registration")
        address = int(ctypes.cast(procedure, ctypes.c_void_p).value)
        context = ctypes.create_string_buffer(0x4D0 + 16)
        context_address = (ctypes.addressof(context) + 15) & ~15
        self.nt.RtlCaptureContext(context_address)
        stack = ctypes.create_string_buffer(4096 + 16)
        aligned_stack = (ctypes.addressof(stack) + 15) & ~15
        initial_rsp = aligned_stack + 0x100 + (8 - stack_delta) % 16
        saved_rdi, saved_rsi, return_address = 0xFEDCBA9876543210, 0xABCDEF1234567890, address
        for at, value in [(stack_delta - 16, saved_rdi), (stack_delta - 8, saved_rsi), (stack_delta, return_address)]:
            ctypes.c_uint64.from_address(initial_rsp + at).value = value
        for at, value in [(0x98, initial_rsp), (0xA8, saved_rsi if restored_rsi else 0),
                          (0xB0, saved_rdi if restored_rdi else 0), (0xF8, address + offset)]:
            ctypes.c_uint64.from_address(context_address + at).value = value
        handler, establisher = ctypes.c_void_p(), ctypes.c_uint64()
        self.nt.RtlVirtualUnwind(0, image, address + offset, entry, context_address,
                                ctypes.byref(handler), ctypes.byref(establisher), None)
        return {"rsp": ctypes.c_uint64.from_address(context_address + 0x98).value,
                "rsi": ctypes.c_uint64.from_address(context_address + 0xA8).value,
                "rdi": ctypes.c_uint64.from_address(context_address + 0xB0).value,
                "rip": ctypes.c_uint64.from_address(context_address + 0xF8).value,
                "expected_rsp": initial_rsp + stack_delta + 8,
                "expected_rsi": saved_rsi, "expected_rdi": saved_rdi,
                "expected_rip": return_address}

    def publish(self, record):
        if self.closed or not isinstance(record, Record):
            raise ValueError("closed bridge or invalid record")
        return int(self.publisher(self.base, ctypes.addressof(record)))

    def drain(self, requested=MAX_DRAIN):
        if self.closed or not 0 <= requested < 2**32:
            raise ValueError("closed bridge or invalid drain bound")
        output = (Record * MAX_DRAIN)()
        count = int(self.consumer(self.base, ctypes.addressof(output), requested))
        assert count <= MAX_DRAIN
        return [Record.from_buffer_copy(output[i]) for i in range(count)]

    def stats(self):
        if self.closed:
            raise ValueError("closed bridge")
        raw = ctypes.string_at(self.base, HEADER_SIZE)
        _, capacity, epoch, peer, lock, count, head, tail, accepted, dropped, filtered = struct.unpack("<IIQQIIIIQQQ", raw)
        return dict(capacity=capacity, epoch=epoch, local_peer=peer, lock=lock, count=count,
                    head=head, tail=tail, accepted=accepted, dropped=dropped, filtered=filtered)

    def close(self):
        # Only after every owned-process producer/consumer thread has joined.
        if not self.closed:
            self.closed = True
            self.publisher = self.consumer = None
            for _, entry in reversed(self._function_tables):
                if not self.nt.RtlDeleteFunctionTable(ctypes.byref(entry)):
                    raise RuntimeError("owned unwind unregister failed; keep code allocations")
            for address in reversed(self._allocations):
                if not self.kernel.VirtualFree(address, 0, 0x8000):
                    raise ctypes.WinError(ctypes.get_last_error())

    def __enter__(self):
        return self

    def __exit__(self, *exception):
        self.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emit", type=Path, help="save owned prototype bytes/ABI, never load a game")
    args = parser.parse_args()
    if args.emit:
        args.emit.mkdir(parents=True, exist_ok=True)
        for name, code in [("publish", publish_code()), ("drain", drain_code())]:
            (args.emit / (name + ".bin")).write_bytes(code)
        (args.emit / "abi.json").write_text(json.dumps({"abi": ABI, "record_size": RECORD_SIZE,
            "header_size": HEADER_SIZE, "max_capacity": MAX_CAPACITY, "max_drain": MAX_DRAIN,
            "prototype_only": True, "game_connector": False,
            "fields": {name: {"offset": getattr(Record, name).offset, "size": ctypes.sizeof(kind)}
                       for name, kind in Record._fields_}}, indent=2) + "\n", encoding="utf-8")
        print(args.emit)


if __name__ == "__main__":
    main()
