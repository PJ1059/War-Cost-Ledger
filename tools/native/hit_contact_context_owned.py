"""Native AP/final association on owned memory; never a gameplay connector.

One context belongs to one actual Windows thread. AP capture is not an event:
only the final wrapper may publish it. A pending/reentrant begin is rejected
and invalidated; a future game adapter needs a proved per-thread context arena
and contact lifecycle, not this one-context test fixture.
"""
import ctypes

from hit_bridge_owned import Record, NORMAL_UNWIND, _Code

OWNER_THREAD = 96
PHASE = 100
HIT_POINTER = 104
CURVE_STATE = 112
REJECTED = 120
IDLE, BEGUN, STAGED, SPENT, AMBIGUOUS = 0, 1, 2, 3, 4
AP_MASK = 0x8C


def _save(c):
    c.emit("56 57 48 81 ec 28 01 00 00")
    for instruction in ["48 89 84 24 80 00 00 00", "48 89 8c 24 88 00 00 00",
        "48 89 94 24 90 00 00 00", "4c 89 84 24 98 00 00 00", "4c 89 8c 24 a0 00 00 00",
        "4c 89 94 24 a8 00 00 00", "4c 89 9c 24 b0 00 00 00"]:
        c.emit(instruction)
    for xmm in range(6):
        c.emit("0f 29 " + bytes([0x84 + xmm * 8, 0x24]).hex(" ") + " "
               + (192 + 16 * xmm).to_bytes(4, "little").hex(" "))


def _restore(c):
    for xmm in range(6):
        c.emit("0f 28 " + bytes([0x84 + xmm * 8, 0x24]).hex(" ") + " "
               + (192 + 16 * xmm).to_bytes(4, "little").hex(" "))
    for instruction in ["48 8b 84 24 80 00 00 00", "48 8b 8c 24 88 00 00 00",
        "48 8b 94 24 90 00 00 00", "4c 8b 84 24 98 00 00 00", "4c 8b 8c 24 a0 00 00 00",
        "4c 8b 94 24 a8 00 00 00", "4c 8b 9c 24 b0 00 00 00"]:
        c.emit(instruction)
    c.emit("48 81 c4 28 01 00 00 5f 5e c3")


def begin_code(get_thread_id):
    c = _Code()
    c.emit("56 57 48 83 ec 28 48 89 ce 48 89 d7")
    c.emit("48 b8 " + get_thread_id.to_bytes(8, "little").hex(" ") + " ff d0")
    c.emit("3b 46 60")
    c.branch("0f 85", "reject")
    c.emit("83 7e 64 00")
    c.branch("0f 84", "begin")
    c.emit("83 7e 64 03")
    c.branch("0f 84", "begin")
    c.emit("c7 46 64 04 00 00 00")  # same-thread pending begin is ambiguous, not a new valid association
    c.branch("e9", "reject")
    c.label("begin")
    c.emit("48 89 7e 68 ff 46 28 c7 46 58 00 00 00 00 c7 46 38 00 00 00 00")
    c.emit("c7 46 70 00 00 00 00")  # no branch marker for this contact yet
    c.emit("c7 46 54 00 00 00 00")  # target kind unknown, no retained hostility from prior contact
    for offset in (64, 68, 72, 92):
        c.emit("c7 46 " + bytes([offset]).hex() + " 00 00 c0 7f")  # invalid until native stage
    c.emit("c7 46 64 01 00 00 00 8b 46 28")
    c.branch("e9", "return")
    c.label("reject")
    c.emit("f0 ff 46 78 31 c0")
    c.label("return")
    c.emit("48 83 c4 28 5f 5e c3")
    return c.finish()


def curve_marker_code(get_thread_id):
    """Native same-contact branch marker, not a hit event or a game hook.

    RCX owned context, RDX HI, R8D 0=default / 1=custom. The real adapter must
    call from the proved mutually exclusive native branch, not infer from factor.
    Conflicting duplicate markers invalidate the pending association.
    """
    c = _Code()
    c.emit("53 56 57 48 83 ec 20 48 89 ce 48 89 d7 44 89 c3")
    c.emit("48 b8 " + get_thread_id.to_bytes(8, "little").hex(" ") + " ff d0")
    c.emit("3b 46 60")
    c.branch("0f 85", "reject")
    c.emit("83 7e 64 01")
    c.branch("0f 84", "phase_ready")
    c.emit("83 7e 64 02")
    c.branch("0f 85", "reject")
    c.label("phase_ready")
    c.emit("48 3b 7e 68")
    c.branch("0f 85", "reject")
    c.emit("83 fb 01")
    c.branch("0f 87", "reject")
    c.emit("8d 53 01 8b 46 70 85 c0")  # encoded unknown0/default1/custom2
    c.branch("0f 84", "set_marker")
    c.emit("39 d0")
    c.branch("0f 84", "set_marker")
    c.emit("c7 46 64 04 00 00 00 c7 46 58 00 00 00 00")
    c.branch("e9", "reject")
    c.label("set_marker")
    c.emit("89 56 70 83 4e 58 10 83 66 38 fb 85 db")
    c.branch("0f 84", "success")
    c.emit("83 4e 38 04")
    c.label("success")
    c.emit("b8 01 00 00 00")
    c.branch("e9", "return")
    c.label("reject")
    c.emit("f0 ff 46 78 31 c0")
    c.label("return")
    c.emit("48 83 c4 20 5f 5e 5b c3")
    return c.finish()


def ap_stage_code(context_address, get_thread_id, *, certified_contact_profile=False):
    """Replay actual 129CB61 bindings: RBX HI, RDI DP, XMM10/9/6 AP/armor/factor."""
    c = _Code()
    _save(c)
    c.emit("0f ae 9c 24 b8 00 00 00")  # save complete original MXCSR before any observer calls/FP work
    c.emit("8b 84 24 b8 00 00 00 0d 80 1f 00 00 89 84 24 bc 00 00 00")
    c.emit("0f ae 94 24 bc 00 00 00")  # mask only extra-observer FP exceptions; retain rounding/DAZ/FTZ
    c.emit("48 b8 " + get_thread_id.to_bytes(8, "little").hex(" ") + " ff d0")
    c.emit("49 ba " + context_address.to_bytes(8, "little").hex(" ") + " 41 3b 42 60")
    c.branch("0f 85", "reject")
    c.emit("41 83 7a 64 01")
    c.branch("0f 85", "reject")
    c.emit("49 3b 5a 68")
    c.branch("0f 85", "reject")
    c.emit("f3 45 0f 11 52 40 f3 45 0f 11 4a 44 f3 41 0f 11 72 48")
    c.emit("48 8b 83 10 01 00 00 49 89 42 10 8b 43 20 41 89 42 2c")
    c.emit("8b 83 00 01 00 00 41 89 42 34 8b 03 41 89 42 50")
    if certified_contact_profile:
        c.emit("8b 83 80 00 00 00 41 89 42 30")
    c.emit("f3 41 0f 10 c2 f3 41 0f 5c c1 f3 41 0f 11 42 5c")  # native SUBSS, not Python/Lua double
    c.emit("41 81 4a 58 8c 00 00 00 41 83 62 38 fe 0f b6 43 73 85 c0")
    c.branch("0f 84", "force_ready")
    c.emit("41 83 4a 38 01")
    c.label("force_ready")
    c.emit("41 c7 42 64 02 00 00 00")
    c.branch("e9", "replay")
    c.label("reject")
    c.emit("f0 41 ff 42 78")
    c.label("replay")
    c.emit("f3 0f 11 77 04")  # original MOVSS [RDI+4],XMM6 occurs even when observation refuses
    c.emit("0f ae 94 24 b8 00 00 00")  # every accepted/rejected path restores original FP environment
    _restore(c)
    return c.finish()


def ap_call_fixture_code(stage_address):
    """C ABI test caller creates the actual AP-stage register state, not a game hook."""
    c = _Code()
    c.emit("53 57 48 83 ec 58 0f 29 74 24 20 44 0f 29 4c 24 30 44 0f 29 54 24 40")
    c.emit("48 89 d3 4c 89 c7 f3 45 0f 10 11 f3 45 0f 10 49 04 f3 41 0f 10 71 08")
    c.emit("48 b8 " + stage_address.to_bytes(8, "little").hex(" ") + " ff d0")
    c.emit("0f 28 74 24 20 44 0f 28 4c 24 30 44 0f 28 54 24 40 48 83 c4 58 5f 5b c3")
    return c.finish()


class OwnedContactContext:
    def __init__(self, bridge, *, certified_contact_profile=False):
        self.bridge = bridge
        self.certified_contact_profile = certified_contact_profile
        bridge.kernel.GetCurrentThreadId.argtypes = []
        bridge.kernel.GetCurrentThreadId.restype = ctypes.c_uint32
        self.get_thread_id = int(ctypes.cast(bridge.kernel.GetCurrentThreadId, ctypes.c_void_p).value)
        self.address = bridge._allocate(128, executable=False)
        self.record = Record.from_address(self.address)
        ctypes.memmove(self.address, bytes(bridge.record()), 96)
        ctypes.c_uint32.from_address(self.address + OWNER_THREAD).value = bridge.kernel.GetCurrentThreadId()
        self._begin = bridge._procedure(begin_code(self.get_thread_id), ctypes.c_uint32,
            ctypes.c_void_p, ctypes.c_void_p, unwind=bytes.fromhex("01060300 0642 0270 0160 0000"))
        self._curve = bridge._procedure(curve_marker_code(self.get_thread_id), ctypes.c_uint32,
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
            unwind=bytes.fromhex("01070400 0732 0370 0260 0130"))
        self._stage = bridge._procedure(ap_stage_code(self.address, self.get_thread_id,
            certified_contact_profile=certified_contact_profile), None, unwind=NORMAL_UNWIND)
        stage_address = int(ctypes.cast(self._stage, ctypes.c_void_p).value)
        self._caller = bridge._procedure(ap_call_fixture_code(stage_address), None,
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
            unwind=bytes.fromhex("01170900 17a80400 11980300 0b680200 06a2 0270 0130 0000"))
        bridge._keepalive.extend([self.record, self])

    def begin(self, hit):
        if self.bridge.closed:
            raise ValueError("closed bridge")
        return int(self._begin(self.address, ctypes.addressof(hit)))

    def ap_stage(self, hit, calculation_values, *, selected_ap, armour, factor):
        if self.bridge.closed:
            raise ValueError("closed bridge")
        floats = (ctypes.c_float * 3)(selected_ap, armour, factor)
        self._caller(None, ctypes.addressof(hit), ctypes.addressof(calculation_values), ctypes.addressof(floats))

    def curve_marker(self, hit, *, custom):
        if self.bridge.closed:
            raise ValueError("closed bridge")
        return int(self._curve(self.address, ctypes.addressof(hit), int(bool(custom))))

    def final_wrapper(self, original, *, extra_arg_types=(), projectile_info_from_entry_rax=False,
                      qualifier=None, entity_manager=None):
        return self.bridge.owned_normal_wrapper(self.record, original, extra_arg_types=extra_arg_types,
            context_guard=True, projectile_info_from_entry_rax=projectile_info_from_entry_rax,
            certified_contact_profile=self.certified_contact_profile,
            qualifier=qualifier, entity_manager=entity_manager)

    def state(self):
        if self.bridge.closed:
            raise ValueError("closed bridge")
        return {"phase": ctypes.c_uint32.from_address(self.address + PHASE).value,
                "rejected": ctypes.c_uint32.from_address(self.address + REJECTED).value,
                "owner_thread": ctypes.c_uint32.from_address(self.address + OWNER_THREAD).value,
                "hit_pointer": ctypes.c_uint64.from_address(self.address + HIT_POINTER).value,
                "contact_ordinal": self.record.contact_ordinal}

    def reset_after_owned_calls_return(self):
        """Tool's explicit quiescent reset; game lifecycle/end callback remains unproved."""
        if self.bridge.closed:
            raise ValueError("closed bridge")
        ctypes.c_uint32.from_address(self.address + PHASE).value = IDLE
        self.record.capture_flags = 0

