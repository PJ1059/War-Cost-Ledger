"""Real native transaction on known workers in this test process only."""
import ctypes
import hashlib
import json
from pathlib import Path
import sys
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/native'))
from hit_bridge_owned import OwnedBridge, _Code
from hit_bridge_install_owned import OwnedE8Callsite
from hit_patch_transaction_owned import (OwnedPatchTransaction, transaction_code, UNWIND,
    OK, BUSY, SUSPEND_FAILED, ALREADY_SUSPENDED, CONTEXT_FAILED, PC_IN_INSTRUCTION,
    BYTES_CHANGED, PROTECT_FAILED, FLUSH_FAILED, RESTORE_FAILED)


class Workers:
    """Each known worker remains in a native loop until its owned stop word."""
    def __init__(self, bridge, sites, count=2):
        self.states = [ctypes.create_string_buffer(16) for _ in range(count)]
        self.ids, self.threads = [], []
        self.loop_code = []
        for state in self.states:
            c = _Code(); c.emit('53 48 83 ec 30 48 89 cb c7 43 04 01 00 00 00')
            c.label('loop'); c.emit('83 3b 00'); c.branch('0f 85', 'end')
            for site in sites:
                c.emit('48 8d 4b 08 31 d2 45 31 c0 45 31 c9 48 c7 44 24 20 00 00 00 00')
                c.emit('48 b8 ' + site.address.to_bytes(8, 'little').hex(' ') + ' ff d0')
            c.branch('e9', 'loop'); c.label('end'); c.emit('48 83 c4 30 5b c3')
            code = c.finish(); self.loop_code.append(code)
            loop = bridge._procedure(code, None, ctypes.c_void_p, unwind=bytes.fromhex('01050200 0552 0130'))
            ready = threading.Event()
            def work(loop=loop, state=state, ready=ready):
                self.ids.append(threading.get_native_id()); ready.set(); loop(ctypes.addressof(state))
            thread = threading.Thread(target=work); self.threads.append(thread); thread.start()
            assert ready.wait(1)
        deadline = time.monotonic() + 1
        while not all(ctypes.c_uint32.from_buffer(s, 4).value for s in self.states) and time.monotonic() < deadline:
            time.sleep(.001)
        assert all(ctypes.c_uint32.from_buffer(s, 4).value for s in self.states)

    def progress(self): return [ctypes.c_uint64.from_buffer(state, 8).value for state in self.states]

    def close(self):
        for state in self.states: ctypes.c_uint32.from_buffer(state).value = 1
        for thread in self.threads:
            thread.join(2)
            assert not thread.is_alive(), 'owned native worker was not resumed'

    def __enter__(self): return self
    def __exit__(self, *_): self.close()


def fixture(bridge, count=2):
    original = bridge._procedure(bytes.fromhex('f0 48 ff 01 31 c0 c3'), ctypes.c_uint64)
    sites = [OwnedE8Callsite(bridge, original) for _ in range(count)]
    observed = ctypes.c_uint64()
    observer = bridge._procedure(bytes.fromhex('48 b8') + ctypes.addressof(observed).to_bytes(8, 'little')
        + bytes.fromhex('f0 48 ff 00 ff 25 00 00 00 00')
        + int(ctypes.cast(original, ctypes.c_void_p).value).to_bytes(8, 'little'), ctypes.c_uint64)
    return sites, observer, observed


def fail_nth_native(bridge, api_name, nth, failure=0):
    """Owned native failure stub; never a Python callback during suspension."""
    count = ctypes.c_uint32()
    real = int(ctypes.cast(getattr(bridge.kernel, api_name), ctypes.c_void_p).value)
    c = _Code(); c.emit('48 b8 ' + ctypes.addressof(count).to_bytes(8, 'little').hex(' '))
    c.emit('f0 ff 00 83 38 ' + bytes([nth]).hex()); c.branch('0f 85', 'real')
    c.emit('b8 ' + failure.to_bytes(4, 'little').hex(' ') + ' c3')
    c.label('real'); c.emit('48 b8 ' + real.to_bytes(8, 'little').hex(' ') + ' ff e0')
    stub = bridge._procedure(c.finish(), ctypes.c_uint32)
    bridge._keepalive.append(count)
    return stub


class TransactionTests(unittest.TestCase):
    def retry_pc_only_after_native_has_resumed(self, transaction):
        for _ in range(50):
            result = transaction.execute()
            if result['returned'] != PC_IN_INSTRUCTION: return result
            self.assertEqual(result['resume_failures'], 0)
            time.sleep(.001)  # Runs only after the native transaction returned.
        self.fail('owned workers did not leave the5-byte instruction')

    def test_two_real_native_workers_install_and_restore_two_whole_callsites(self):
        with OwnedBridge() as bridge:
            sites, observer, observed = fixture(bridge)
            with Workers(bridge, sites) as workers:
                original = [ctypes.string_at(site.call_address, 5) for site in sites]
                with OwnedPatchTransaction(bridge, workers.ids, [(s, observer) for s in sites]) as transaction:
                    installed = self.retry_pc_only_after_native_has_resumed(transaction)
                    self.assertTrue(installed['complete']); self.assertEqual(installed['suspended'], 2)
                    self.assertEqual(installed['patched'], 2); self.assertEqual(installed['resume_counts'], [1, 1])
                    self.assertEqual(installed['lock'], 0)
                    self.assertTrue(all(s.installed for s in sites))
                before = workers.progress(); time.sleep(.005)
                self.assertTrue(all(a > b for a, b in zip(workers.progress(), before)))
                self.assertGreater(observed.value, 0)
                with OwnedPatchTransaction(bridge, workers.ids, [(s, None) for s in sites]) as transaction:
                    restored = self.retry_pc_only_after_native_has_resumed(transaction)
                    self.assertTrue(restored['complete']); self.assertEqual(restored['patched'], 2)
                self.assertEqual([ctypes.string_at(s.call_address, 5) for s in sites], original)
                sample = observed.value; time.sleep(.005); self.assertEqual(observed.value, sample)
                self.assertTrue(all(not s.installed for s in sites))

    def test_byte_gate_before_suspend_and_busy_cas_never_touch_workers(self):
        with OwnedBridge() as bridge:
            sites, observer, _ = fixture(bridge, 1)
            # The worker spins in separate owned code for this mismatch case;
            # changing the fixture callsite cannot race an executing E8.
            with Workers(bridge, [], 1) as workers:
                with OwnedPatchTransaction(bridge, workers.ids, [(sites[0], observer)]) as transaction:
                    transaction.job.lock = 1
                    result = transaction.execute(); self.assertEqual(result['returned'], BUSY)
                    self.assertEqual(result['suspended'], 0); transaction.job.lock = 0
                    expected = ctypes.string_at(sites[0].call_address, 5)
                    target = int(ctypes.cast(observer, ctypes.c_void_p).value)
                    changed = b'\xe8' + (target - (sites[0].call_address + 5)).to_bytes(4, 'little', signed=True)
                    sites[0].fixture_alter_owned_instruction(changed)
                    result = transaction.execute()
                    self.assertEqual(result['returned'], BYTES_CHANGED); self.assertEqual(result['suspended'], 0)
                    sites[0].fixture_alter_owned_instruction(expected)

    def test_full_instruction_pc_interval_rejection_resumes_real_worker(self):
        with OwnedBridge() as bridge:
            sites, observer, _ = fixture(bridge, 1)
            with Workers(bridge, sites, 1) as workers:
                for offset in range(5):
                    # Synthetic returned CONTROL.Rip, while Suspend/Resume are
                    # real and the worker's actual execution context is untouched.
                    code = bytes.fromhex('48 b8') + (sites[0].call_address + offset).to_bytes(8, 'little')
                    code += bytes.fromhex('48 89 82 f8 00 00 00 b8 01 00 00 00 c3')
                    get_context = bridge._procedure(code, ctypes.c_int)
                    with OwnedPatchTransaction(bridge, workers.ids, [(sites[0], observer)],
                                               fault_functions={'get_context': get_context}) as transaction:
                        result = transaction.execute(); self.assertEqual(result['returned'], PC_IN_INSTRUCTION)
                        self.assertEqual(result['patched'], 0); self.assertEqual(result['resume_counts'], [1])
                before = workers.progress(); time.sleep(.002)
                self.assertGreater(workers.progress()[0], before[0])

    def test_context_api_failure_resumes_suspended_worker(self):
        with OwnedBridge() as bridge:
            sites, observer, _ = fixture(bridge, 1)
            failed = bridge._procedure(bytes.fromhex('31 c0 c3'), ctypes.c_int)
            with Workers(bridge, sites, 1) as workers:
                with OwnedPatchTransaction(bridge, workers.ids, [(sites[0], observer)],
                                           fault_functions={'get_context': failed}) as transaction:
                    result = transaction.execute()
                    self.assertEqual(result['returned'], CONTEXT_FAILED); self.assertEqual(result['resume_counts'], [1])
                    self.assertEqual(result['patched'], 0)

    def test_partial_suspend_failure_restores_only_successfully_suspended_workers(self):
        with OwnedBridge() as bridge:
            sites, observer, _ = fixture(bridge, 1)
            stub = fail_nth_native(bridge, 'SuspendThread', 2, failure=0xFFFFFFFF)
            with Workers(bridge, sites) as workers:
                with OwnedPatchTransaction(bridge, workers.ids, [(sites[0], observer)],
                                           fault_functions={'suspend': stub}) as transaction:
                    result = transaction.execute()
                    self.assertEqual(result['returned'], SUSPEND_FAILED)
                    self.assertEqual(result['suspended'], 1)
                    self.assertEqual(result['resume_counts'], [1, 0])
                    self.assertEqual(result['patched'], 0)
                before = workers.progress(); time.sleep(.002)
                self.assertTrue(all(a > b for a, b in zip(workers.progress(), before)))

    def test_already_suspended_worker_keeps_its_prior_suspend_count(self):
        with OwnedBridge() as bridge:
            sites, observer, _ = fixture(bridge, 1)
            with Workers(bridge, sites) as workers:
                with OwnedPatchTransaction(bridge, workers.ids, [(sites[0], observer)]) as transaction:
                    handle = transaction.pause.handles[1]
                    self.assertEqual(bridge.kernel.SuspendThread(handle), 0)
                    try:
                        result = transaction.execute()
                        self.assertEqual(result['returned'], ALREADY_SUSPENDED)
                        self.assertEqual(result['suspended'], 2)
                        self.assertEqual(result['resume_counts'], [1, 2])
                        self.assertEqual(result['patched'], 0)
                    finally:
                        self.assertEqual(bridge.kernel.ResumeThread(handle), 1)

    def test_post_suspend_byte_gate_refuses_changed_expected_buffer(self):
        with OwnedBridge() as bridge:
            sites, observer, _ = fixture(bridge, 1)
            with Workers(bridge, sites, 1) as workers:
                with OwnedPatchTransaction(bridge, workers.ids, [(sites[0], observer)]) as transaction:
                    # Only owned writable fixture memory changes. The worker's
                    # actual context/instruction remains untouched. Real Suspend
                    # and Resume bracket this synthetic CONTROL/byte-plan fault.
                    code = bytes.fromhex('48 b8') + transaction.patches[0].expected.to_bytes(8, 'little')
                    code += bytes.fromhex('c6 00 90 48 c7 82 f8 00 00 00 00 00 00 00 b8 01 00 00 00 c3')
                    stub = bridge._procedure(code, ctypes.c_int)
                    transaction.job.get_context = ctypes.cast(stub, ctypes.c_void_p).value
                    result = transaction.execute()
                    self.assertEqual(result['returned'], BYTES_CHANGED)
                    self.assertEqual(result['suspended'], 1)
                    self.assertEqual(result['patched'], 0)
                    self.assertEqual(result['resume_counts'], [1])

    def test_native_flush_and_protection_failures_rollback_before_resume(self):
        for function, nth, reason, wrote in (('flush', 2, FLUSH_FAILED, 2),
                                            ('protect', 3, PROTECT_FAILED, 1),
                                            ('protect', 2, RESTORE_FAILED, 1)):
            with self.subTest(function=function, nth=nth), OwnedBridge() as bridge:
                sites, observer, _ = fixture(bridge)
                original = [ctypes.string_at(s.call_address, 5) for s in sites]
                stub = fail_nth_native(bridge, 'FlushInstructionCache' if function == 'flush' else 'VirtualProtect', nth)
                with Workers(bridge, sites) as workers:
                    with OwnedPatchTransaction(bridge, workers.ids, [(s, observer) for s in sites],
                                               fault_functions={function: stub}) as transaction:
                        result = self.retry_pc_only_after_native_has_resumed(transaction)
                        self.assertEqual(result['returned'], reason)
                        self.assertEqual(result['patched'], wrote)
                        self.assertEqual(result['rollback_restored'], wrote)
                        self.assertEqual((result['rollback_failures'], result['resume_failures']), (0, 0))
                        self.assertEqual(result['resume_counts'], [1, 1])
                    self.assertEqual([ctypes.string_at(s.call_address, 5) for s in sites], original)
                    before = workers.progress(); time.sleep(.002)
                    self.assertTrue(all(a > b for a, b in zip(workers.progress(), before)))

    def test_self_foreign_code_and_closed_bridge_refused_before_native_entry(self):
        with OwnedBridge() as bridge:
            sites, observer, _ = fixture(bridge, 1)
            with self.assertRaises(ValueError):
                OwnedPatchTransaction(bridge, [threading.get_native_id()], [(sites[0], observer)])
            with Workers(bridge, sites, 1) as workers:
                with self.assertRaises(ValueError):
                    OwnedPatchTransaction(bridge, workers.ids, [(sites[0], ctypes.c_void_p(1))])
                transaction = OwnedPatchTransaction(bridge, workers.ids, [(sites[0], observer)])
                transaction.close()
                with self.assertRaises(ValueError): transaction.execute()

    def test_registered_unwind_seven_nonvolatile_registers_and_every_epilog_pc(self):
        with OwnedBridge() as bridge:
            entry = bridge._procedure(transaction_code(), ctypes.c_uint32, ctypes.c_void_p, unwind=UNWIND)
            address = int(ctypes.cast(entry, ctypes.c_void_p).value); size = len(transaction_code())
            order = [('rbx', 0x90), ('rsi', 0xA8), ('rdi', 0xB0), ('r12', 0xD8), ('r13', 0xE0), ('r14', 0xE8), ('r15', 0xF0)]
            positions = [(18, 32, 0), (size - 16, 32, 0), (size - 12, 0, 0)]
            positions += [(size - 12 + 2 * n, 0, n) for n in range(1, 5)]
            positions += [(size - 3, 0, 5), (size - 2, 0, 6), (size - 1, 0, 7)]
            for pc, frame, popped in positions:
                image, runtime = bridge.unwind_lookup(entry, pc)
                context = ctypes.create_string_buffer(0x4D0 + 16); at = (ctypes.addressof(context) + 15) & ~15
                bridge.nt.RtlCaptureContext(at)
                stack = ctypes.create_string_buffer(4096); initial = ((ctypes.addressof(stack) + 15) & ~15) + 1024 + 8
                expected = {}
                for i, (name, offset) in enumerate(order, 1):
                    expected[offset] = 0xFEDCBA9876543200 + i
                    ctypes.c_uint64.from_address(initial - 8 * i).value = expected[offset]
                    ctypes.c_uint64.from_address(at + offset).value = expected[offset] if i > 7 - popped else 0
                ctypes.c_uint64.from_address(initial).value = address
                ctypes.c_uint64.from_address(at + 0x98).value = initial - (7 - popped) * 8 - frame
                ctypes.c_uint64.from_address(at + 0xF8).value = address + pc
                handler, establisher = ctypes.c_void_p(), ctypes.c_uint64()
                bridge.nt.RtlVirtualUnwind(0, image, address + pc, runtime, at,
                    ctypes.byref(handler), ctypes.byref(establisher), None)
                self.assertEqual(ctypes.c_uint64.from_address(at + 0x98).value, initial + 8)
                self.assertEqual(ctypes.c_uint64.from_address(at + 0xF8).value, address)
                for offset, value in expected.items():
                    self.assertEqual(ctypes.c_uint64.from_address(at + offset).value, value)


if __name__ == '__main__':
    unittest.main(verbosity=2)
