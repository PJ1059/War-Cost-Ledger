"""Bounded native contact lifecycle in this Python process's owned pages.

No process enumeration, game read/write, patching, callbacks into Python, or
allocation on a contact path. This is not a gameplay hook. A game adapter must
enter begin only at the certified new-iteration callsite and end at its proved
iteration barrier; stack bounds alone do not certify either condition.
"""
import ctypes

from hit_bridge_owned import Record, _Code

HEADER_SIZE = 64
ROW_SIZE = 640  # compatible 128-byte contact cache + 512-byte inline save area
PROBES = 8
OWNER = 96
PHASE = 100
HIT = 104
FRAME = 624  # reserved beyond GP/XMM save range, not inferred from HI or TEB
UNWIND = bytes.fromhex("01030300 0370 0260 0130 0000")


def arena_code(operation):
    """RCX arena, RDX HI, R8 certified caller-frame token (begin/end)."""
    if operation not in {"begin", "lookup", "end"}:
        raise ValueError("unknown contact operation")
    c = _Code()
    c.emit("53 56 57 48 89 ce 48 89 d7")
    c.emit("83 7e 28 01")  # explicitly enabled header; no inferred mission state
    c.branch("0f 85", "reject")
    c.emit("48 85 ff")
    c.branch("0f 84", "reject")
    if operation != 'lookup':
        c.emit('4d 85 c0')
        c.branch('0f 84', 'reject')
    # Inlined current-tool Windows x64 thread identity, no nested CALL.
    c.emit("65 48 8b 04 25 30 00 00 00 44 8b 48 48")
    c.emit("44 89 cb 8b 06 ff c8 21 c3 41 ba 08 00 00 00")
    c.label("probe")
    c.emit("4c 69 db 80 02 00 00 4c 03 5e 30 41 8b 43 60 44 39 c8")
    c.branch("0f 84", "found")
    c.emit("85 c0")
    if operation == "begin":
        c.branch("0f 85", "next")
        c.emit("f0 45 0f b1 4b 60")  # claim owner 0 -> thread; failed CAS returns observed owner
        c.branch("0f 84", "found")
        c.emit("44 39 c8")
        c.branch("0f 84", "found")
    else:
        c.branch("0f 84", "reject")  # immutable owner slots: first empty means absent
    c.label("next")
    c.emit("ff c3 8b 06 ff c8 21 c3 41 ff ca")
    c.branch("0f 85", "probe")
    c.branch("e9", "reject")
    c.label("found")
    if operation == "begin":
        c.emit("41 8b 43 64 85 c0")
        c.branch("0f 84", "fresh")
        c.emit("83 f8 03")
        c.branch("0f 84", "fresh")
        c.emit("49 3b 7b 68")
        c.branch("0f 85", "reject")  # nested different HI preserves pending outer contact
        c.emit('4d 3b 83 70 02 00 00')
        c.branch('0f 85', 'reject')  # same HI in another caller frame is not a new iteration
        c.label("fresh")
        c.emit('4d 89 83 70 02 00 00')
        c.emit('41 c7 43 64 00 00 00 00 41 c7 43 58 00 00 00 00')
        c.emit("b8 01 00 00 00 f0 48 0f c1 46 18 48 ff c0")
        c.emit("49 89 c0 48 c1 e8 20 48 85 c0")
        c.branch("0f 85", "reject")  # contact ordinal must not wrap u32
        # Clear only the record, not stable thread ownership or inline scratch.
        for offset in range(0, 96, 8):
            c.emit("49 c7 43 " + bytes([offset]).hex() + " 00 00 00 00")
        c.emit("48 8b 46 08 49 89 43 08 4d 89 43 28")  # ordinal low32 + target0
        c.emit("49 89 7b 18 49 89 7b 68 41 c7 43 70 00 00 00 00")
        for offset in (64, 68, 72, 92):
            c.emit("41 c7 43 " + bytes([offset]).hex() + " 00 00 c0 7f")
        c.emit("41 c7 43 64 01 00 00 00 4c 89 d8")
    else:
        c.emit("49 3b 7b 68")
        c.branch("0f 85", "reject")
        if operation == "lookup":
            c.emit("41 8b 43 64 83 f8 01")
            c.branch("0f 84", "lookup_ready")
            c.emit("83 f8 02")
            c.branch("0f 85", "reject")
            c.label("lookup_ready")
            c.emit("4c 89 d8")
        else:
            c.emit('4d 3b 83 70 02 00 00')
            c.branch('0f 85', 'reject')
            c.emit("41 c7 43 64 00 00 00 00 49 c7 43 68 00 00 00 00")
            c.emit("41 c7 43 58 00 00 00 00 b8 01 00 00 00")
    c.branch("e9", "return")
    c.label("reject")
    c.emit("f0 48 ff 46 20 31 c0")
    c.label("return")
    c.emit("5f 5e 5b c3")
    return c.finish()


class OwnedContactArena:
    def __init__(self, bridge, *, capacity=32):
        if bridge.closed or not isinstance(capacity, int) or not 8 <= capacity <= 128 or capacity & (capacity - 1):
            raise ValueError("live owned bridge and bounded power-of-two capacity required")
        self.bridge, self.capacity = bridge, capacity
        self.address = bridge._allocate(HEADER_SIZE, executable=False)
        self.rows = bridge._allocate(capacity * ROW_SIZE, executable=False)
        ctypes.c_uint32.from_address(self.address).value = capacity
        ctypes.c_uint32.from_address(self.address + 4).value = ROW_SIZE
        ctypes.c_uint64.from_address(self.address + 8).value = bridge.epoch
        ctypes.c_uint64.from_address(self.address + 16).value = bridge.local_peer
        ctypes.c_uint32.from_address(self.address + 40).value = 1
        ctypes.c_uint64.from_address(self.address + 48).value = self.rows
        self._calls = {name: bridge._procedure(arena_code(name), ctypes.c_void_p,
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint64, unwind=UNWIND) for name in ("begin", "lookup", "end")}
        bridge._keepalive.append(self)

    def invoke(self, operation, hit, *, frame=None):
        if self.bridge.closed:
            raise ValueError("closed bridge")
        pointer = ctypes.addressof(hit) if not isinstance(hit, int) else hit
        # Fixture default is the owned HI allocation's address as a scope token.
        # A certified game adapter instead supplies original parent RSP.
        token = pointer if frame is None else frame
        return int(self._calls[operation](self.address, pointer, token) or 0)

    def record(self, address):
        if self.bridge.closed or not self.rows <= address < self.rows + self.capacity * ROW_SIZE or (address-self.rows) % ROW_SIZE:
            raise ValueError("record must be an owned arena row")
        return Record.from_address(address)

    def stats(self):
        if self.bridge.closed:
            raise ValueError("closed bridge")
        return {"contact_counter": ctypes.c_uint64.from_address(self.address + 24).value,
                "rejected": ctypes.c_uint64.from_address(self.address + 32).value,
                "capacity": self.capacity, "probe_limit": PROBES}

    def reset_after_owned_calls_return(self, *, enabled=True):
        """Fixture's explicitly quiescent reset; never runs on a contact path."""
        if self.bridge.closed:
            raise ValueError("closed bridge")
        ctypes.memset(self.rows, 0, self.capacity * ROW_SIZE)
        ctypes.c_uint64.from_address(self.address + 8).value = self.bridge.epoch
        ctypes.c_uint32.from_address(self.address + 40).value = int(bool(enabled))
