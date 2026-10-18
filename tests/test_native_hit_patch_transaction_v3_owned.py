"""Actual Windows x64 v3 transactions on this fixture process only."""
import ctypes
import hashlib
import json
from pathlib import Path
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/native'))
from hit_bridge_owned import OwnedBridge, _Code
from hit_bridge_install_owned import OwnedE8Callsite
from hit_patch_transaction_v3_owned import (OwnedPatchTransactionV3, OwnedSixByteCallsite,
    transaction_code, manifest, UNWIND, Job, ThreadRecord, PatchRecord, OK, BUSY,
    SUSPEND_FAILED, ALREADY_SUSPENDED, CONTEXT_FAILED, PC_IN_INSTRUCTION, BYTES_CHANGED,
    PROTECT_FAILED, FLUSH_FAILED, RESTORE_FAILED, ENUM_FAILED, THREAD_SET_CHANGED, INVALID_PLAN)

EVIDENCE = []


class NativeSleepWorkers:
    """CreateThread workers execute only native Sleep/stop/progress code."""
    def __init__(self, bridge, count=1):
        self.bridge, self.states, self.handles, self.ids = bridge, [], [], []
        k = bridge.kernel
        k.CreateThread.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p,
            ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32)]
        k.CreateThread.restype = ctypes.c_void_p
        k.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        k.WaitForSingleObject.restype = ctypes.c_uint32
        k.CloseHandle.argtypes = [ctypes.c_void_p]; k.CloseHandle.restype = ctypes.c_int
        sleep = int(ctypes.cast(k.Sleep, ctypes.c_void_p).value)
        c = _Code(); c.emit('53 48 83 ec 20 48 89 cb c7 43 04 01 00 00 00')
        c.label('loop'); c.emit('83 3b 00'); c.branch('0f 85', 'end')
        c.emit('48 ff 43 08 b9 01 00 00 00 48 b8 ' + sleep.to_bytes(8, 'little').hex(' ') + ' ff d0')
        c.branch('e9', 'loop'); c.label('end'); c.emit('31 c0 48 83 c4 20 5b c3')
        loop = bridge._procedure(c.finish(), ctypes.c_uint32, ctypes.c_void_p,
            unwind=bytes.fromhex('01050200 0532 0130'))
        try:
            for _ in range(count):
                state, tid = ctypes.create_string_buffer(16), ctypes.c_uint32()
                handle = k.CreateThread(None, 0, ctypes.cast(loop, ctypes.c_void_p),
                    ctypes.addressof(state), 0, ctypes.byref(tid))
                if not handle: raise ctypes.WinError(ctypes.get_last_error())
                self.states.append(state); self.handles.append(handle); self.ids.append(tid.value)
            deadline = time.monotonic() + 2
            while not all(ctypes.c_uint32.from_buffer(s, 4).value for s in self.states):
                if time.monotonic() >= deadline: raise RuntimeError('owned worker startup failed')
                time.sleep(.001)
        except BaseException:
            self.close(); raise

    def progress(self): return [ctypes.c_uint64.from_buffer(s, 8).value for s in self.states]

    def close(self):
        for state in self.states: ctypes.c_uint32.from_buffer(state).value = 1
        failures = []
        for handle in self.handles:
            if self.bridge.kernel.WaitForSingleObject(handle, 2000) != 0: failures.append(handle)
            else: self.bridge.kernel.CloseHandle(handle)
        self.handles = failures
        if failures: raise AssertionError('owned worker still suspended or running')

    def __enter__(self): return self
    def __exit__(self, *_): self.close()


def fixture(bridge, count=1, six=False):
    original = bridge._procedure(bytes.fromhex('b8 17 00 00 00 c3'), ctypes.c_uint64)
    observer = bridge._procedure(bytes.fromhex('b8 2a 00 00 00 c3'), ctypes.c_uint64)
    kind = OwnedSixByteCallsite if six else OwnedE8Callsite
    return [kind(bridge, original) for _ in range(count)], observer


def fail_nth_native(bridge, api_name, nth, failure=0, nt=False):
    """Preallocated native fault shim; no Python callback while paused."""
    count = ctypes.c_uint32()
    api = getattr(bridge.nt if nt else bridge.kernel, api_name)
    real = int(ctypes.cast(api, ctypes.c_void_p).value)
    c = _Code(); c.emit('48 b8 ' + ctypes.addressof(count).to_bytes(8, 'little').hex(' '))
    c.emit('f0 ff 00 83 38 ' + bytes([nth]).hex()); c.branch('0f 85', 'real')
    c.emit('b8 ' + failure.to_bytes(4, 'little').hex(' ') + ' c3')
    c.label('real'); c.emit('48 b8 ' + real.to_bytes(8, 'little').hex(' ') + ' ff e0')
    stub = bridge._procedure(c.finish(), ctypes.c_uint32)
    bridge._keepalive.append(count)
    return stub


def context_rip(bridge, rip):
    code = bytes.fromhex('48 b8') + rip.to_bytes(8, 'little')
    code += bytes.fromhex('48 89 82 f8 00 00 00 b8 01 00 00 00 c3')
    return bridge._procedure(code, ctypes.c_int)


def prepared_host_ids(bridge, workers):
    """Prepare the test host's complete set before suspension; never a game PID.

    Explicit CreateThread workers remain separately identified. Other threads
    are labelled own-host background threads rather than fixture workers.
    """
    k, nt = bridge.kernel, bridge.nt
    k.GetCurrentThreadId.restype = ctypes.c_uint32
    k.GetCurrentProcessId.restype = ctypes.c_uint32
    k.GetProcessIdOfThread.argtypes = [ctypes.c_void_p]; k.GetProcessIdOfThread.restype = ctypes.c_uint32
    k.GetThreadId.argtypes = [ctypes.c_void_p]; k.GetThreadId.restype = ctypes.c_uint32
    k.CloseHandle.argtypes = [ctypes.c_void_p]; k.CloseHandle.restype = ctypes.c_int
    nt.NtGetNextThread.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
        ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)]
    nt.NtGetNextThread.restype = ctypes.c_int32
    current, own_tid, own_pid, found = None, k.GetCurrentThreadId(), k.GetCurrentProcessId(), []
    try:
        while True:
            following = ctypes.c_void_p()
            status = nt.NtGetNextThread(k.GetCurrentProcess(), current, 0x800, 0, 0, ctypes.byref(following)) & 0xFFFFFFFF
            if current: k.CloseHandle(current); current = None
            if status == 0x8000001A: break
            if status != 0 or not following.value: raise OSError('owned host enumeration failed: ' + hex(status))
            current = following.value
            if k.GetProcessIdOfThread(current) != own_pid: raise AssertionError('not this test host')
            tid = k.GetThreadId(current)
            if not tid or tid in found: raise AssertionError('invalid or duplicate host TID')
            found.append(tid)
            if len(found) > 257: raise AssertionError('owned host exceeds native v2 bound')
    finally:
        if current: k.CloseHandle(current)
    if own_tid not in found or not set(workers.ids) <= set(found): raise AssertionError('owned fixture workers missing')
    background = [tid for tid in found if tid != own_tid and tid not in workers.ids]
    return list(workers.ids) + background


class TransactionV3Tests(unittest.TestCase):
    def observe(self, name, result, **more):
        EVIDENCE.append({'case': name, 'result': result, **more})
        self.assertEqual(result['lock'], 0)
        self.assertTrue(result['enum_handles_released'])

    def test_seventeen_sleep_native_workers_install_and_restore_eight_calls(self):
        with OwnedBridge() as bridge:
            sites, observer = fixture(bridge, 8)
            original = [ctypes.string_at(s.call_address, 5) for s in sites]
            with NativeSleepWorkers(bridge, 17) as workers:
                with OwnedPatchTransactionV3(bridge, prepared_host_ids(bridge, workers), [(s, observer) for s in sites]) as tx:
                    result = tx.execute(); self.observe('17-workers-8-patches-install', result, explicit_native_workers=17, own_host_background_threads=len(tx.threads)-17)
                    self.assertTrue(result['complete']); self.assertEqual(result['returned'], OK)
                    self.assertEqual(result['suspended'], len(tx.threads)); self.assertEqual(result['enumerated'], len(tx.threads) + 1)
                    self.assertEqual(len(workers.ids), 17)
                    self.assertEqual(result['seen'], [1] * len(tx.threads)); self.assertEqual(result['patched'], 8)
                    self.assertEqual(result['resume_counts'], [1] * len(tx.threads))
                    self.assertEqual(result['enum_status'], 0x8000001A)
                self.assertEqual([s.invoke(None, None, None, 0, 0) for s in sites], [42] * 8)
                before = workers.progress(); time.sleep(.04)
                self.assertTrue(all(a > b for a, b in zip(workers.progress(), before)))
                with OwnedPatchTransactionV3(bridge, prepared_host_ids(bridge, workers), [(s, None) for s in sites]) as tx:
                    result = tx.execute(); self.observe('17-workers-8-patches-restore', result, explicit_native_workers=17, own_host_background_threads=len(tx.threads)-17)
                    self.assertTrue(result['complete'])
                self.assertEqual([ctypes.string_at(s.call_address, 5) for s in sites], original)
                self.assertEqual([s.invoke(None, None, None, 0, 0) for s in sites], [23] * 8)

    def test_actual_six_byte_ff15_patch_and_entire_pc_span(self):
        with OwnedBridge() as bridge:
            sites, observer = fixture(bridge, six=True)
            site = sites[0]; original = ctypes.string_at(site.call_address, 6)
            self.assertEqual(original[:2], b'\xff\x15'); self.assertEqual(site.invoke(None), 23)
            with NativeSleepWorkers(bridge) as workers:
                for offset in range(7):
                    stub = context_rip(bridge, site.call_address + offset)
                    with OwnedPatchTransactionV3(bridge, prepared_host_ids(bridge, workers), [(site, observer)],
                            fault_functions={'get_context': stub}) as tx:
                        result = tx.execute()
                        self.observe('six-byte-pc-offset-' + str(offset), result, pc_is_synthetic=True,
                            instruction_is_actual_six_byte_ff15=True, pause_and_resume_are_real=True)
                        self.assertEqual(tx.patches[0].length, 6)
                        if offset < 6:
                            self.assertEqual(result['returned'], PC_IN_INSTRUCTION)
                            self.assertEqual(result['patched'], 0)
                            self.assertEqual(ctypes.string_at(site.call_address, 6), original)
                        else:
                            self.assertTrue(result['complete']); self.assertEqual(site.invoke(None), 42)
                        self.assertEqual(result['resume_counts'], [1] * len(tx.threads))
                with OwnedPatchTransactionV3(bridge, prepared_host_ids(bridge, workers), [(site, None)]) as tx:
                    result = tx.execute(); self.observe('six-byte-restore', result)
                    self.assertTrue(result['complete'])
                self.assertEqual(ctypes.string_at(site.call_address, 6), original)
                self.assertEqual(site.invoke(None), 23)

    def test_unprepared_new_owned_thread_rejected_without_write(self):
        with OwnedBridge() as bridge:
            sites, observer = fixture(bridge)
            original = ctypes.string_at(sites[0].call_address, 5)
            with NativeSleepWorkers(bridge) as prepared:
                with OwnedPatchTransactionV3(bridge, prepared_host_ids(bridge, prepared), [(sites[0], observer)]) as tx:
                    with NativeSleepWorkers(bridge) as late:
                        result = tx.execute(); self.observe('new-owned-thread-after-prepare', result,
                            late_thread_was_explicitly_owned=True)
                        self.assertEqual(result['returned'], THREAD_SET_CHANGED)
                        self.assertEqual(result['patched'], 0); self.assertEqual(result['suspended'], len(tx.threads))
                        self.assertEqual(result['resume_counts'], [1] * len(tx.threads))
                        self.assertEqual(ctypes.string_at(sites[0].call_address, 5), original)
                        before = prepared.progress() + late.progress(); time.sleep(.04)
                        after = prepared.progress() + late.progress()
                        self.assertTrue(all(a > b for a, b in zip(after, before)))

    def test_enum_api_failure_and_truncated_count_reverse_resume_no_write(self):
        for nth, status, reason in ((1, 0xC0000001, ENUM_FAILED),
                (2, 0xC0000001, ENUM_FAILED), (1, 0x8000001A, THREAD_SET_CHANGED)):
            with self.subTest(nth=nth, status=status), OwnedBridge() as bridge:
                sites, observer = fixture(bridge)
                stub = fail_nth_native(bridge, 'NtGetNextThread', nth, status, nt=True)
                original = ctypes.string_at(sites[0].call_address, 5)
                with NativeSleepWorkers(bridge, 2) as workers:
                    with OwnedPatchTransactionV3(bridge, prepared_host_ids(bridge, workers), [(sites[0], observer)],
                            fault_functions={'nt_get_next_thread': stub}) as tx:
                        result = tx.execute(); self.observe('enum-native-fault', result, nth=nth, status=status)
                        self.assertEqual(result['returned'], reason); self.assertFalse(result['complete'])
                        self.assertEqual(result['resume_counts'], [1] * len(tx.threads)); self.assertEqual(result['patched'], 0)
                        self.assertEqual(result['enum_status'], status)
                        self.assertEqual(ctypes.string_at(sites[0].call_address, 5), original)

    def test_thread_identity_zero_unknown_and_duplicate_refused(self):
        for tid, reason in ((0, ENUM_FAILED), (0xDEADFEED, THREAD_SET_CHANGED), ('installer', THREAD_SET_CHANGED)):
            with self.subTest(tid=tid), OwnedBridge() as bridge:
                sites, observer = fixture(bridge)
                identity = bridge.kernel.GetCurrentThreadId() if tid == 'installer' else tid
                stub = bridge._procedure(b'\xb8' + identity.to_bytes(4, 'little') + b'\xc3', ctypes.c_uint32)
                with NativeSleepWorkers(bridge) as workers:
                    with OwnedPatchTransactionV3(bridge, prepared_host_ids(bridge, workers), [(sites[0], observer)],
                            fault_functions={'get_thread_id': stub}) as tx:
                        result = tx.execute(); self.observe('native-thread-ID-fault', result, identity=identity)
                        self.assertEqual(result['returned'], reason); self.assertEqual(result['patched'], 0)
                        self.assertEqual(result['resume_counts'], [1] * len(tx.threads)); self.assertFalse(result['complete'])

    def test_byte_busy_context_and_partial_suspend_gates(self):
        with OwnedBridge() as bridge:
            sites, observer = fixture(bridge)
            with NativeSleepWorkers(bridge, 2) as workers:
                with OwnedPatchTransactionV3(bridge, prepared_host_ids(bridge, workers), [(sites[0], observer)]) as tx:
                    tx.job.lock = 1
                    result = tx.execute(); self.assertEqual(result['returned'], BUSY)
                    self.assertEqual(result['suspended'], 0); tx.job.lock = 0
                    expected = ctypes.string_at(sites[0].call_address, 5)
                    sites[0].fixture_alter_owned_instruction(b'\xe8\0\0\0\0')
                    result = tx.execute(); self.observe('pre-suspend-byte-gate', result)
                    self.assertEqual(result['returned'], BYTES_CHANGED); self.assertEqual(result['suspended'], 0)
                    sites[0].fixture_alter_owned_instruction(expected)
                for key, stub, reason, counts in (
                        ('get_context', bridge._procedure(bytes.fromhex('31 c0 c3'), ctypes.c_int), CONTEXT_FAILED, [1, 1]),
                        ('suspend', fail_nth_native(bridge, 'SuspendThread', 2, 0xFFFFFFFF), SUSPEND_FAILED, [1, 0])):
                    with OwnedPatchTransactionV3(bridge, prepared_host_ids(bridge, workers), [(sites[0], observer)],
                            fault_functions={key: stub}) as tx:
                        result = tx.execute(); self.observe('native-' + key + '-failure', result)
                        self.assertEqual(result['returned'], reason); self.assertEqual(result['resume_counts'], ([1] * len(tx.threads) if key == 'get_context' else [1] + [0] * (len(tx.threads) - 1)))
                        self.assertEqual(result['patched'], 0)

    def assert_existing_prior(self, bridge, handles, expected):
        observed = []
        for handle, prior in zip(handles, expected):
            value = bridge.kernel.SuspendThread(handle)
            observed.append(value)
            self.assertEqual(bridge.kernel.ResumeThread(handle), value + 1)
            self.assertEqual(value, prior)
        return observed

    def test_pre_suspended_worker_installs_and_preserves_prior_suspend_count(self):
        with OwnedBridge() as bridge:
            sites, observer = fixture(bridge)
            with NativeSleepWorkers(bridge, 2) as workers:
                with OwnedPatchTransactionV3(bridge, prepared_host_ids(bridge, workers), [(sites[0], observer)]) as tx:
                    handle = tx.pause.handles[1]
                    self.assertEqual(bridge.kernel.SuspendThread(handle), 0)
                    try:
                        result = tx.execute()
                        observed = self.assert_existing_prior(bridge, [handle], [1])
                        self.observe('prior-suspend-count-install-success', result,
                            prior_suspend_count=1, transaction_resume_return=2,
                            observed_remaining_prior=observed, original_suspend_not_removed=True)
                        self.assertTrue(result['complete']); self.assertEqual(result['returned'], OK)
                        self.assertEqual(result['resume_counts'], [1, 2] + [1] * (len(tx.threads) - 2))
                        self.assertEqual(result['patched'], 1)
                        self.assertEqual(sites[0].invoke(None, None, None, 0, 0), 42)
                        prior = workers.progress()[1]; time.sleep(.04)
                        self.assertEqual(workers.progress()[1], prior, 'existing suspend count must still hold worker')
                    finally: self.assertEqual(bridge.kernel.ResumeThread(handle), 1)

    def test_pre_suspended_worker_pc_gate_five_and_six_byte_spans_preserves_prior(self):
        for six in (False, True):
            for offset in (0, 5 if six else 4):
                with self.subTest(six=six, offset=offset), OwnedBridge() as bridge:
                    sites, observer = fixture(bridge, six=six)
                    site, length = sites[0], 6 if six else 5
                    original = ctypes.string_at(site.call_address, length)
                    stub = context_rip(bridge, site.call_address + offset)
                    with NativeSleepWorkers(bridge) as workers:
                        with OwnedPatchTransactionV3(bridge, prepared_host_ids(bridge, workers), [(site, observer)],
                                fault_functions={'get_context': stub}) as tx:
                            handle = tx.pause.handles[0]
                            self.assertEqual(bridge.kernel.SuspendThread(handle), 0)
                            try:
                                result = tx.execute()
                                observed = self.assert_existing_prior(bridge, [handle], [1])
                                self.observe('prior-suspend-PC-reject', result, instruction_bytes=length,
                                    offset=offset, pc_is_synthetic=True, prior_suspend_count=1,
                                    observed_remaining_prior=observed)
                                self.assertEqual(result['returned'], PC_IN_INSTRUCTION)
                                self.assertEqual(result['patched'], 0)
                                self.assertEqual(result['resume_counts'], [2] + [1] * (len(tx.threads) - 1))
                                self.assertEqual(ctypes.string_at(site.call_address, length), original)
                            finally: self.assertEqual(bridge.kernel.ResumeThread(handle), 1)

    def test_pre_suspended_workers_failure_paths_preserve_each_original_prior(self):
        for failure in ('partial_suspend', 'bytes_after_suspend', 'protect'):
            with self.subTest(failure=failure), OwnedBridge() as bridge:
                sites, observer = fixture(bridge, 2)
                original = [ctypes.string_at(site.call_address, 5) for site in sites]
                with NativeSleepWorkers(bridge, 2) as workers:
                    with OwnedPatchTransactionV3(bridge, prepared_host_ids(bridge, workers), [(s, observer) for s in sites]) as tx:
                        handles = tx.pause.handles[:2]
                        self.assertEqual(bridge.kernel.SuspendThread(handles[0]), 0)
                        self.assertEqual(bridge.kernel.SuspendThread(handles[1]), 0)
                        self.assertEqual(bridge.kernel.SuspendThread(handles[1]), 1)
                        if failure == 'partial_suspend':
                            stub = fail_nth_native(bridge, 'SuspendThread', 2, 0xFFFFFFFF)
                            tx.job.suspend = ctypes.cast(stub, ctypes.c_void_p).value
                            expected_reason, expected_written = SUSPEND_FAILED, 0
                            expected_resumes = [2] + [0] * (len(tx.threads) - 1)
                        elif failure == 'bytes_after_suspend':
                            code = bytes.fromhex('48 b8') + tx.patches[0].expected.to_bytes(8, 'little')
                            code += bytes.fromhex('c6 00 90 48 c7 82 f8 00 00 00 00 00 00 00 b8 01 00 00 00 c3')
                            stub = bridge._procedure(code, ctypes.c_int)
                            tx.job.get_context = ctypes.cast(stub, ctypes.c_void_p).value
                            expected_reason, expected_written = BYTES_CHANGED, 0
                            expected_resumes = [2, 3] + [1] * (len(tx.threads) - 2)
                        else:
                            stub = fail_nth_native(bridge, 'VirtualProtect', 3)
                            tx.job.protect = ctypes.cast(stub, ctypes.c_void_p).value
                            expected_reason, expected_written = PROTECT_FAILED, 1
                            expected_resumes = [2, 3] + [1] * (len(tx.threads) - 2)
                        try:
                            result = tx.execute()
                            observed = self.assert_existing_prior(bridge, handles, [1, 2])
                            self.observe('prior-suspend-failure-' + failure, result,
                                prior_suspend_counts=[1, 2], observed_remaining_prior=observed)
                            self.assertEqual(result['returned'], expected_reason)
                            self.assertEqual(result['patched'], expected_written)
                            self.assertEqual(result['resume_counts'], expected_resumes)
                            self.assertEqual((result['rollback_failures'], result['resume_failures']), (0, 0))
                            if expected_written: self.assertEqual(result['rollback_restored'], 1)
                            self.assertEqual([ctypes.string_at(s.call_address, 5) for s in sites], original)
                        finally:
                            self.assertEqual(bridge.kernel.ResumeThread(handles[0]), 1)
                            self.assertEqual(bridge.kernel.ResumeThread(handles[1]), 2)
                            self.assertEqual(bridge.kernel.ResumeThread(handles[1]), 1)

    def test_reverse_native_resume_order(self):
        with OwnedBridge() as bridge:
            sites, observer = fixture(bridge)
            with NativeSleepWorkers(bridge, 3) as workers:
                with OwnedPatchTransactionV3(bridge, prepared_host_ids(bridge, workers), [(sites[0], observer)]) as tx:
                    count = ctypes.c_uint32()
                    calls = (ctypes.c_uint64 * len(tx.threads))()
                    real = int(ctypes.cast(bridge.kernel.ResumeThread, ctypes.c_void_p).value)
                    c = _Code()
                    c.emit('48 b8 ' + ctypes.addressof(count).to_bytes(8, 'little').hex(' '))
                    c.emit('44 8b 10 ff 00 49 bb ' + ctypes.addressof(calls).to_bytes(8, 'little').hex(' '))
                    c.emit('4b 89 0c d3 48 b8 ' + real.to_bytes(8, 'little').hex(' ') + ' ff e0')
                    shim = bridge._procedure(c.finish(), ctypes.c_uint32)
                    tx.job.resume = ctypes.cast(shim, ctypes.c_void_p).value
                    result = tx.execute()
                    self.observe('native-reverse-resume-order', result,
                        expected_handles=list(reversed(tx.pause.handles)), observed_handles=list(calls))
                    self.assertTrue(result['complete']); self.assertEqual(count.value, len(tx.threads))
                    self.assertEqual(list(calls), list(reversed(tx.pause.handles)))

    def test_flush_protect_restore_failures_rollback_before_resume(self):
        for key, api, nth, reason, wrote in (('flush', 'FlushInstructionCache', 2, FLUSH_FAILED, 2),
                ('protect', 'VirtualProtect', 3, PROTECT_FAILED, 1),
                ('protect', 'VirtualProtect', 2, RESTORE_FAILED, 1)):
            with self.subTest(key=key, nth=nth), OwnedBridge() as bridge:
                sites, observer = fixture(bridge, 2)
                original = [ctypes.string_at(s.call_address, 5) for s in sites]
                stub = fail_nth_native(bridge, api, nth)
                with NativeSleepWorkers(bridge, 2) as workers:
                    with OwnedPatchTransactionV3(bridge, prepared_host_ids(bridge, workers), [(s, observer) for s in sites],
                            fault_functions={key: stub}) as tx:
                        result = tx.execute(); self.observe('rollback-' + key, result, nth=nth)
                        self.assertEqual(result['returned'], reason); self.assertEqual(result['patched'], wrote)
                        self.assertEqual(result['rollback_restored'], wrote)
                        self.assertEqual((result['rollback_failures'], result['resume_failures']), (0, 0))
                        self.assertEqual(result['resume_counts'], [1] * len(tx.threads))
                    self.assertEqual([ctypes.string_at(s.call_address, 5) for s in sites], original)

    def test_success_requires_zero_rollback_and_resume_failures(self):
        with OwnedBridge() as bridge:
            sites, observer = fixture(bridge)
            # Resume for real inside the native shim, then report failure. This
            # verifies result accounting without returning to Python with host
            # background threads left suspended by a deliberate test fault.
            real = int(ctypes.cast(bridge.kernel.ResumeThread, ctypes.c_void_p).value)
            shim = bytes.fromhex('48 83 ec 28 48 b8') + real.to_bytes(8, 'little')
            shim += bytes.fromhex('ff d0 b8 ff ff ff ff 48 83 c4 28 c3')
            fail_resume = bridge._procedure(shim, ctypes.c_uint32,
                unwind=bytes.fromhex('01040100 0442 0000'))
            with NativeSleepWorkers(bridge) as workers:
                with OwnedPatchTransactionV3(bridge, prepared_host_ids(bridge, workers), [(sites[0], observer)],
                        fault_functions={'resume': fail_resume}) as tx:
                    result = tx.execute(); self.observe('return-zero-resume-failure', result,
                        real_native_resume_performed_before_synthetic_failure=True)
                    self.assertEqual(result['returned'], OK); self.assertEqual(result['resume_failures'], len(tx.threads))
                    self.assertFalse(result['complete']); self.assertFalse(sites[0].installed)
        with OwnedBridge() as bridge:
            sites, observer = fixture(bridge)
            failed_flush = bridge._procedure(bytes.fromhex('31 c0 c3'), ctypes.c_int)
            with NativeSleepWorkers(bridge) as workers:
                with OwnedPatchTransactionV3(bridge, prepared_host_ids(bridge, workers), [(sites[0], observer)],
                        fault_functions={'flush': failed_flush}) as tx:
                    result = tx.execute(); self.observe('rollback-flush-failure', result)
                    self.assertEqual(result['returned'], FLUSH_FAILED); self.assertEqual(result['rollback_failures'], 1)
                    self.assertFalse(result['complete']); self.assertFalse(sites[0].installed)

    def test_native_plan_limits_and_owned_host_refusals(self):
        with OwnedBridge() as bridge:
            sites, observer = fixture(bridge)
            with self.assertRaises(ValueError):
                OwnedPatchTransactionV3(bridge, [bridge.kernel.GetCurrentThreadId()], [(sites[0], observer)])
            with NativeSleepWorkers(bridge) as workers:
                with self.assertRaises(ValueError):
                    OwnedPatchTransactionV3(bridge, prepared_host_ids(bridge, workers), [(sites[0], ctypes.c_void_p(1))])
                with self.assertRaises(ValueError):
                    OwnedPatchTransactionV3(bridge, prepared_host_ids(bridge, workers), [(sites[0], observer), (sites[0], observer)])
                for field, value in (('thread_count', 0), ('thread_count', 257), ('patch_count', 0),
                        ('patch_count', 9), ('process', 1), ('installer_tid', 0)):
                    with OwnedPatchTransactionV3(bridge, prepared_host_ids(bridge, workers), [(sites[0], observer)]) as tx:
                        setattr(tx.job, field, value)
                        result = tx.execute() if field != 'installer_tid' else None
                        if result:
                            self.observe('native-plan-' + field, result, invalid=value)
                            self.assertEqual(result['returned'], INVALID_PLAN); self.assertEqual(result['suspended'], 0)
                        else:
                            with self.assertRaises(ValueError): tx.execute()
                with OwnedPatchTransactionV3(bridge, prepared_host_ids(bridge, workers), [(sites[0], observer)]) as tx:
                    tx.patches[0].length = 4
                    result = tx.execute(); self.observe('native-length-bound', result)
                    self.assertEqual(result['returned'], INVALID_PLAN); self.assertEqual(result['suspended'], 0)

    def test_manifest_code_job_functions_and_exact_abi(self):
        data = manifest()
        self.assertEqual((ctypes.sizeof(Job), ctypes.sizeof(ThreadRecord), ctypes.sizeof(PatchRecord)), (168, 40, 48))
        self.assertEqual(len(data['entries']), 1); self.assertEqual(data['entries'][0]['relocations'], [])
        self.assertEqual(data['layouts']['job']['fields'][-1]['offset'], 160)
        self.assertEqual(data['limits']['threads_max'], 256)
        # No movabs addresses occur in the relocatable core; all eight CALLs load
        # function pointers from the prepared RCX job. Fixture shims may use own addresses.
        import capstone
        decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        decoded = list(decoder.disasm(transaction_code(), 0))
        self.assertEqual(sum(i.size for i in decoded), len(transaction_code()))
        self.assertFalse(any(i.mnemonic == 'movabs' for i in decoded))
        for index, insn in enumerate(decoded):
            if insn.mnemonic == 'call':
                self.assertEqual(insn.op_str, 'rax')
                self.assertEqual(decoded[index - 1].mnemonic, 'mov')
                self.assertIn('qword ptr [r12 +', decoded[index - 1].op_str)
        EVIDENCE.append({'case': 'pure-manifest', 'code_bytes': len(transaction_code()),
            'code_sha256': hashlib.sha256(transaction_code()).hexdigest(),
            'entry_count': 1, 'absolute_code_pointers': 0, 'abi': [168, 40, 48]})

    def test_registered_unwind_nonvolatile_registers_and_every_epilog_pc(self):
        with OwnedBridge() as bridge:
            entry = bridge._procedure(transaction_code(), ctypes.c_uint32, ctypes.c_void_p, unwind=UNWIND)
            address = int(ctypes.cast(entry, ctypes.c_void_p).value); size = len(transaction_code())
            order = [('rbx', 0x90), ('rsi', 0xA8), ('rdi', 0xB0), ('r12', 0xD8), ('r13', 0xE0), ('r14', 0xE8), ('r15', 0xF0)]
            positions = [(18, 48, 0), (size - 16, 48, 0), (size - 12, 0, 0)]
            positions += [(size - 12 + 2 * n, 0, n) for n in range(1, 5)]
            positions += [(size - 3, 0, 5), (size - 2, 0, 6), (size - 1, 0, 7)]
            for pc, frame, popped in positions:
                image, runtime = bridge.unwind_lookup(entry, pc)
                context = ctypes.create_string_buffer(0x4D0 + 16); at = (ctypes.addressof(context) + 15) & ~15
                bridge.nt.RtlCaptureContext(at)
                stack = ctypes.create_string_buffer(4096)
                initial = ((ctypes.addressof(stack) + 15) & ~15) + 1024 + 8
                expected = {}
                for i, (_, offset) in enumerate(order, 1):
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
            EVIDENCE.append({'case': 'unwind-body-and-epilog', 'actual_native_virtual_unwind': True,
                'positions': len(positions), 'nonvolatile_registers': 7, 'stack_bytes': 48})


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path)
    args, remaining = parser.parse_known_args()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TransactionV3Tests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps({'passed': result.wasSuccessful(), 'tests_run': result.testsRun,
            'failures': len(result.failures), 'errors': len(result.errors), 'evidence': EVIDENCE,
            'game_access': False, 'game_connected': False,
            'six_byte_span_actual_tested': result.wasSuccessful(),
            'new_thread_barrier_proven': False}, indent=2) + '\n', encoding='utf8')
    sys.exit(0 if result.wasSuccessful() else 1)
