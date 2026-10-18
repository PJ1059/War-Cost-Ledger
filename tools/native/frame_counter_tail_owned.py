"""Tiny Windows x64 frame-counter tail wrapper, owned process only.

14B wrapper: LOCK INC qword[RIP+ownedCounter]; JMP qword[RIP+ownedOriginal].
No GP/XMM/RSP/MXCSR instruction; arithmetic flags are ABI-volatile. An owned
simulated API slot is changed/restored by aligned native LOCK CMPXCHG owner
checks. Only this process's newly allocated8192B pages are touched. They are
retained until process exit, including after slot restoration/owner change.
No Game lookup/address/API/VirtualProtect, MOD integration or hit payload.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import struct

REVISION = 'owned_frame_counter_tail14_v1'
PAGE = 4096
WRAPPER, ORIGINAL, CAS, THIRD_PARTY = 0, 64, 128, 192
COUNTER, ORIGINAL_TARGET, SLOT, ORIGINAL_CALLS, FLOAT_CONSTANT = PAGE, PAGE + 8, PAGE + 16, PAGE + 24, PAGE + 32
_RETAINED = []


def rip_instruction(prefix, at, target):
    return bytes.fromhex(prefix) + struct.pack('<i', target - (at + len(bytes.fromhex(prefix)) + 4))


def wrapper_code():
    return rip_instruction('f048ff05', WRAPPER, COUNTER) + rip_instruction('ff25', WRAPPER + 8, ORIGINAL_TARGET)


def original_code():
    return (rip_instruction('f048ff05', ORIGINAL, ORIGINAL_CALLS)
            + rip_instruction('f30f5805', ORIGINAL + 8, FLOAT_CONSTANT) + b'\xc3')


class OwnedTail:
    """No caller-supplied address: all procedures/data belong to one allocation."""
    def __init__(self):
        if os.name != 'nt' or ctypes.sizeof(ctypes.c_void_p) != 8 or platform.machine().lower() not in ('amd64', 'x86_64'):
            raise RuntimeError('requires owned Windows x64 process')
        # Same alloc/protect/flush pattern as hit_bridge_owned.py, without its
        # queue/producers/contexts/unwind infrastructure.
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        k = self.kernel
        k.VirtualAlloc.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_uint32]
        k.VirtualAlloc.restype = ctypes.c_void_p
        k.VirtualProtect.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32)]
        k.VirtualProtect.restype = ctypes.c_int
        k.FlushInstructionCache.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
        k.FlushInstructionCache.restype = ctypes.c_int
        k.GetCurrentProcess.argtypes = []
        k.GetCurrentProcess.restype = ctypes.c_void_p
        self.base = k.VirtualAlloc(None, PAGE * 2, 0x3000, 4)
        if not self.base:
            raise ctypes.WinError(ctypes.get_last_error())
        self._native_entries = {self.base + x for x in (WRAPPER, ORIGINAL, CAS, THIRD_PARTY)}
        self.counter = ctypes.c_uint64.from_address(self.base + COUNTER)
        self.original_target = ctypes.c_uint64.from_address(self.base + ORIGINAL_TARGET)
        self.slot = ctypes.c_uint64.from_address(self.base + SLOT)
        self.original_calls = ctypes.c_uint64.from_address(self.base + ORIGINAL_CALLS)
        self.original_target.value = self.slot.value = self.base + ORIGINAL
        ctypes.c_float.from_address(self.base + FLOAT_CONSTANT).value = 1.25
        for offset, code in ((WRAPPER, wrapper_code()), (ORIGINAL, original_code()),
                             (CAS, bytes.fromhex('4c89c0f0480fb111c3')), (THIRD_PARTY, b'\xc3')):
            ctypes.memmove(self.base + offset, code, len(code))
        previous = ctypes.c_uint32()
        if not k.VirtualProtect(self.base, PAGE, 0x20, ctypes.byref(previous)):
            raise ctypes.WinError(ctypes.get_last_error())
        if not k.FlushInstructionCache(k.GetCurrentProcess(), self.base, PAGE):
            raise ctypes.WinError(ctypes.get_last_error())
        assert self.base % PAGE == 0 and (self.base + SLOT) % 8 == 0
        self._cas = ctypes.WINFUNCTYPE(ctypes.c_uint64, ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint64)(self.base + CAS)
        self._float_type = ctypes.WINFUNCTYPE(ctypes.c_float, ctypes.c_float)
        _RETAINED.append(self)  # No VirtualFree/reuse; potential cached entry remains valid until exit.

    def compare_exchange(self, expected_offset, replacement_offset):
        expected, replacement = self.base + expected_offset, self.base + replacement_offset
        if expected not in self._native_entries or replacement not in self._native_entries:
            raise ValueError('CAS values must be explicitly owned native entries')
        return int(self._cas(self.base + SLOT, replacement, expected))

    def invoke_slot(self, value):
        if self.slot.value not in self._native_entries:
            raise ValueError('slot target must remain an explicitly owned native entry')
        return float(self._float_type(self.slot.value)(value))

    def invoke_cached_wrapper(self, value):
        return float(self._float_type(self.base + WRAPPER)(value))


def run_owned():
    host = OwnedTail()
    inputs, expected = [0.5, 2.0, 3.5], [1.75, 3.25, 4.75]
    baseline = [host.invoke_slot(x) for x in inputs]
    if host.compare_exchange(ORIGINAL, WRAPPER) != host.base + ORIGINAL:
        raise AssertionError('owned install CAS lost original ownership')
    wrapped = [host.invoke_slot(x) for x in inputs]
    installed_counts = {'counter': host.counter.value, 'original_calls': host.original_calls.value}
    if host.compare_exchange(WRAPPER, ORIGINAL) != host.base + WRAPPER:
        raise AssertionError('owned restore CAS lost wrapper ownership')
    restored = [host.invoke_slot(x) for x in inputs]
    restored_counts = {'counter': host.counter.value, 'original_calls': host.original_calls.value}
    assert baseline == wrapped == restored == expected
    assert installed_counts == {'counter': 3, 'original_calls': 6}
    assert restored_counts == {'counter': 3, 'original_calls': 9}
    # A third-party owner takes the simulated slot. Our owner-checked restore
    # must fail without overwriting it; one retained cached wrapper remains safe.
    assert host.compare_exchange(ORIGINAL, WRAPPER) == host.base + ORIGINAL
    assert host.compare_exchange(WRAPPER, THIRD_PARTY) == host.base + WRAPPER
    returned = host.compare_exchange(WRAPPER, ORIGINAL)
    preserved = host.slot.value == host.base + THIRD_PARTY
    assert returned == host.base + THIRD_PARTY and preserved
    cached = host.invoke_cached_wrapper(0.5)
    assert cached == 1.75 and host.counter.value == 4 and host.original_calls.value == 10
    code = wrapper_code()
    return {'status': 'PASS', 'source_revision': REVISION, 'owned_pid': os.getpid(),
        'native_actual_run': True, 'wrapper_bytes': len(code), 'wrapper_hex': code.hex(),
        'wrapper_sha256': hashlib.sha256(code).hexdigest(),
        'instructions': ['lock inc qword ptr [rip+owned_counter]', 'jmp qword ptr [rip+owned_original_target]'],
        'code_page': 'PAGE_EXECUTE_READ', 'counter_and_slot_page': 'PAGE_READWRITE',
        'allocation_bytes': PAGE * 2, 'allocation_retained_until_process_exit': True,
        'slot_aligned_bytes': 8, 'cas_helper_hex': '4c89c0f0480fb111c3',
        'inputs': inputs, 'baseline_float_xmm0': baseline, 'wrapped_float_xmm0': wrapped,
        'restored_float_xmm0': restored, 'installed_counts': installed_counts, 'restored_counts': restored_counts,
        'original_callback_call_count_preserved': True, 'third_party_slot_preserved': preserved,
        'owner_checked_restore_success_after_third_party': False,
        'late_cached_wrapper_float': cached, 'final_counter': host.counter.value,
        'final_original_calls': host.original_calls.value, 'gp_xmm_rsp_mxcsr_preservation_basis': 'two exact wrapper instructions; no full register matrix',
        'wrapper_arithmetic_flags_volatile': True, 'game_accessed': False,
        'game_calls': 0, 'game_writes': 0, 'game_virtual_protect': 0,
        'mod_integrated': False, 'game_slot_replacement_proven': False,
        'game_live_table_dispatch_proven': False, 'hit_payload_proven': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    folder = args.output.resolve()
    if folder.exists():
        parser.exit(1, 'use a new owned evidence folder\n')
    result = run_owned()
    folder.mkdir(parents=True)
    (folder / 'wrapper.bin').write_bytes(wrapper_code())
    (folder / 'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', 'utf8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
