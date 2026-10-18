"""V4 owned transaction: capture the original SuspendThread failure diagnostic on explicit tool-owned workers and E8 callsites.

All handles, buffers, contexts, byte plans and Win32 pointers are prepared before
the native entry. Between its first SuspendThread and final ResumeThread there
is no Python/Lua callback or allocation. This is not a game installer.
"""
import ctypes

from hit_bridge_owned import _Code

OK, BUSY, SUSPEND_FAILED, ALREADY_SUSPENDED, CONTEXT_FAILED = range(5)
PC_IN_INSTRUCTION, BYTES_CHANGED, PROTECT_FAILED, FLUSH_FAILED, RESTORE_FAILED = range(5, 10)
RESULT_NAMES = ('ok', 'busy', 'suspend_failed', 'already_suspended', 'context_failed',
                'pc_in_instruction', 'bytes_changed', 'protect_failed', 'flush_failed', 'restore_failed')
ENUM_FAILED, THREAD_SET_CHANGED, INVALID_PLAN = 10, 11, 12
RESULT_NAMES += ('enum_failed', 'thread_set_changed', 'invalid_plan')
UNWIND = bytes.fromhex('010f0800 0f52 0bf0 09e0 07d0 05c0 0370 0260 0130')


class ThreadRecord(ctypes.Structure):
    _fields_ = [('handle', ctypes.c_void_p), ('context', ctypes.c_void_p),
                ('rip', ctypes.c_uint64), ('prior', ctypes.c_uint32), ('resumed', ctypes.c_uint32),
                ('thread_id', ctypes.c_uint32), ('seen', ctypes.c_uint32)]


class PatchRecord(ctypes.Structure):
    _fields_ = [('address', ctypes.c_void_p), ('length', ctypes.c_uint32),
                ('expected_protection', ctypes.c_uint32), ('expected', ctypes.c_void_p),
                ('replacement', ctypes.c_void_p), ('prior_protection', ctypes.c_uint32),
                ('scratch_protection', ctypes.c_uint32), ('protection_changed', ctypes.c_uint32),
                ('written', ctypes.c_uint32)]


class Job(ctypes.Structure):
    _fields_ = [('lock', ctypes.c_uint32), ('result', ctypes.c_uint32),
                ('failed_patch', ctypes.c_uint32), ('suspended', ctypes.c_uint32),
                ('patched', ctypes.c_uint32), ('rollback_failures', ctypes.c_uint32),
                ('resume_failures', ctypes.c_uint32), ('thread_count', ctypes.c_uint32),
                ('patch_count', ctypes.c_uint32), ('reserved', ctypes.c_uint32),
                ('threads', ctypes.c_void_p), ('patches', ctypes.c_void_p),
                ('process', ctypes.c_void_p), ('suspend', ctypes.c_void_p),
                ('get_context', ctypes.c_void_p), ('resume', ctypes.c_void_p),
                ('protect', ctypes.c_void_p), ('flush', ctypes.c_void_p),
                ('rollback_restored', ctypes.c_uint32), ('reserved2', ctypes.c_uint32),
                ('installer_tid', ctypes.c_uint32), ('enumerated', ctypes.c_uint32),
                ('enum_status', ctypes.c_uint32), ('enum_failures', ctypes.c_uint32),
                ('nt_get_next_thread', ctypes.c_void_p), ('get_thread_id', ctypes.c_void_p),
                ('close_handle', ctypes.c_void_p), ('enum_cursor', ctypes.c_void_p),
                ('enum_next', ctypes.c_void_p)]


assert ctypes.sizeof(ThreadRecord) == 40 and ctypes.sizeof(PatchRecord) == 48
assert ctypes.sizeof(Job) == 168 and Job.enum_next.offset == 160
assert Job.threads.offset == 40 and Job.suspend.offset == 64 and Job.rollback_restored.offset == 104


class MemoryInformation(ctypes.Structure):
    _fields_ = [('base', ctypes.c_void_p), ('allocation', ctypes.c_void_p),
                ('allocation_protection', ctypes.c_uint32), ('partition', ctypes.c_uint16),
                ('size', ctypes.c_size_t), ('state', ctypes.c_uint32),
                ('protection', ctypes.c_uint32), ('kind', ctypes.c_uint32)]


assert ctypes.sizeof(MemoryInformation) == 48


def transaction_code():
    c = _Code()
    # Seven nonvolatile pushes, aligned48B call frame; no XMM use.
    c.emit('53 56 57 41 54 41 55 41 56 41 57 48 83 ec 30 49 89 cc')
    c.emit('31 c0 41 b8 01 00 00 00 f0 45 0f b1 04 24')
    c.branch('0f 85', 'busy')
    for offset in (4, 12, 16, 20, 24, 36, 104, 116, 120, 124):
        c.emit('41 c7 44 24 ' + bytes([offset]).hex() + ' 00 00 00 00')
    c.emit('41 c7 44 24 08 ff ff ff ff 41 c7 44 24 6c ff ff ff ff 49 8b 74 24 28 49 8b 7c 24 30')

    def call(offset):
        c.emit('49 8b 44 24 ' + bytes([offset]).hex() + ' ff d0' if offset < 128 else
               '49 8b 84 24 ' + offset.to_bytes(4, 'little').hex(' ') + ' ff d0')

    def patch_pointer():
        c.emit('4d 6b fe 30 49 01 ff')  # R15=patches+R14*48

    def thread_pointer():
        c.emit('4d 6b fd 28 49 01 f7')  # R15=threads+R13*40

    def failed(reason, target='resume_all'):
        c.emit('41 c7 44 24 04 ' + int(reason).to_bytes(4, 'little').hex(' '))
        c.branch('e9', target)

    def byte_gate(prefix, reset=False):
        c.emit('45 31 f6')
        c.label(prefix + '_patch')
        c.emit('45 3b 74 24 20'); c.branch('0f 83', prefix + '_done')
        patch_pointer()
        if reset:
            c.emit('41 c7 47 28 00 00 00 00 41 c7 47 2c 00 00 00 00')
        c.emit('4d 8b 17 4d 8b 5f 10 31 db')
        c.label(prefix + '_byte')
        c.emit('41 8a 04 1a 41 3a 04 1b'); c.branch('0f 85', 'bytes_failed')
        c.emit('ff c3 41 3b 5f 08'); c.branch('0f 82', prefix + '_byte')
        c.emit('41 ff c6'); c.branch('e9', prefix + '_patch')
        c.label(prefix + '_done')

    # Prepared descriptor limits are checked before any worker suspension.
    c.emit('49 c7 84 24 98 00 00 00 00 00 00 00 49 c7 84 24 a0 00 00 00 00 00 00 00')
    c.emit('41 83 7c 24 1c 01'); c.branch('0f 82', 'invalid_plan')
    c.emit('41 81 7c 24 1c 00 01 00 00'); c.branch('0f 87', 'invalid_plan')
    c.emit('41 83 7c 24 20 01'); c.branch('0f 82', 'invalid_plan')
    c.emit('41 83 7c 24 20 08'); c.branch('0f 87', 'invalid_plan')
    c.emit('49 83 7c 24 38 ff'); c.branch('0f 85', 'invalid_plan')
    c.emit('41 83 7c 24 70 00'); c.branch('0f 84', 'invalid_plan')
    c.emit('45 31 ed')
    c.label('reset_threads')
    c.emit('45 3b 6c 24 1c'); c.branch('0f 83', 'check_lengths')
    thread_pointer()
    c.emit('41 c7 47 18 00 00 00 00 41 c7 47 1c 00 00 00 00 41 c7 47 24 00 00 00 00')
    c.emit('41 ff c5'); c.branch('e9', 'reset_threads')
    c.label('check_lengths'); c.emit('45 31 f6')
    c.label('length_loop')
    c.emit('45 3b 74 24 20'); c.branch('0f 83', 'lengths_done')
    patch_pointer(); c.emit('41 83 7f 08 05'); c.branch('0f 84', 'length_next')
    c.emit('41 83 7f 08 06'); c.branch('0f 85', 'invalid_plan')
    c.label('length_next'); c.emit('41 ff c6'); c.branch('e9', 'length_loop')
    c.label('lengths_done')
    byte_gate('before', reset=True)
    c.emit('45 31 ed')
    c.label('suspend_loop')
    c.emit('45 3b 6c 24 1c'); c.branch('0f 83', 'thread_set_start')
    thread_pointer(); c.emit('49 8b 0f'); call(64)
    c.emit('41 89 47 18 83 f8 ff'); c.branch('0f 84', 'suspend_failed')
    # Every successful SuspendThread adds exactly one increment, including prior>0.
    # Resume once in reverse order; do not remove the pre-existing suspend count.
    c.emit('41 ff 44 24 0c')
    c.emit('41 ff c5'); c.branch('e9', 'suspend_loop')
    c.label('thread_set_start')
    # NtGetNextThread(Process, previous, access, attributes, flags, out):
    # caller shadow32B and arguments5/6 at+32/+40 were reserved in prolog.
    c.label('enum_loop')
    c.emit('49 c7 84 24 a0 00 00 00 00 00 00 00')
    c.emit('49 8b 4c 24 38 49 8b 94 24 98 00 00 00 41 b8 00 08 00 00 45 31 c9')
    c.emit('c7 44 24 20 00 00 00 00 49 8d 84 24 a0 00 00 00 48 89 44 24 28')
    call(128)
    c.emit('41 89 44 24 78 3d 1a 00 00 80'); c.branch('0f 84', 'enum_end')
    c.emit('85 c0'); c.branch('0f 85', 'enum_failed')
    c.emit('49 83 bc 24 a0 00 00 00 00'); c.branch('0f 84', 'enum_failed')
    c.emit('49 8b 8c 24 98 00 00 00 48 85 c9'); c.branch('0f 84', 'enum_accept_handle')
    call(144); c.emit('85 c0'); c.branch('0f 84', 'enum_failed')
    c.label('enum_accept_handle')
    c.emit('49 8b 8c 24 a0 00 00 00 49 89 8c 24 98 00 00 00')
    c.emit('49 c7 84 24 a0 00 00 00 00 00 00 00'); call(136)
    c.emit('85 c0'); c.branch('0f 84', 'enum_failed')
    c.emit('41 ff 44 24 74 89 c3 41 8b 44 24 1c ff c0 41 39 44 24 74')
    c.branch('0f 87', 'thread_set_changed')
    c.emit('41 3b 5c 24 70'); c.branch('0f 85', 'enum_worker_start')
    c.emit('41 83 7c 24 24 00'); c.branch('0f 85', 'thread_set_changed')
    c.emit('41 c7 44 24 24 01 00 00 00'); c.branch('e9', 'enum_loop')
    c.label('enum_worker_start'); c.emit('45 31 ed')
    c.label('enum_worker_loop')
    c.emit('45 3b 6c 24 1c'); c.branch('0f 83', 'thread_set_changed')
    thread_pointer(); c.emit('41 3b 5f 20'); c.branch('0f 85', 'enum_worker_next')
    c.emit('41 83 7f 24 00'); c.branch('0f 85', 'thread_set_changed')
    c.emit('41 c7 47 24 01 00 00 00'); c.branch('e9', 'enum_loop')
    c.label('enum_worker_next'); c.emit('41 ff c5'); c.branch('e9', 'enum_worker_loop')
    c.label('enum_end')
    c.emit('49 83 bc 24 a0 00 00 00 00'); c.branch('0f 85', 'enum_failed')
    c.emit('49 8b 8c 24 98 00 00 00 48 85 c9'); c.branch('0f 84', 'enum_count_check')
    call(144); c.emit('85 c0'); c.branch('0f 84', 'enum_failed')
    c.emit('49 c7 84 24 98 00 00 00 00 00 00 00')
    c.label('enum_count_check')
    c.emit('41 8b 44 24 1c ff c0 41 39 44 24 74'); c.branch('0f 85', 'thread_set_changed')
    c.emit('41 83 7c 24 24 01'); c.branch('0f 85', 'thread_set_changed')
    c.branch('e9', 'context_start')
    c.label('enum_failed'); c.emit('41 ff 44 24 7c'); failed(ENUM_FAILED, 'enum_cleanup')
    c.label('thread_set_changed'); failed(THREAD_SET_CHANGED, 'enum_cleanup')
    c.label('enum_cleanup')
    for offset in (160, 152):
        next_label = 'enum_cleanup_' + str(offset)
        c.emit('49 8b 8c 24 ' + offset.to_bytes(4, 'little').hex(' ') + ' 48 85 c9')
        c.branch('0f 84', next_label)
        call(144); c.emit('85 c0'); c.branch('0f 85', next_label)
        c.emit('41 ff 44 24 7c')
        c.label(next_label)
        c.emit('49 c7 84 24 ' + offset.to_bytes(4, 'little').hex(' ') + ' 00 00 00 00')
    c.branch('e9', 'resume_all')
    c.label('invalid_plan'); failed(INVALID_PLAN)
    c.label('context_start'); c.emit('45 31 ed')
    c.label('context_loop')
    c.emit('45 3b 6c 24 1c'); c.branch('0f 83', 'context_done')
    thread_pointer(); c.emit('49 8b 0f 49 8b 57 08'); call(72)
    c.emit('85 c0'); c.branch('0f 84', 'context_failed')
    c.emit('49 8b 57 08 48 8b 82 f8 00 00 00 49 89 47 10 45 31 f6')
    c.label('pc_patch_loop')
    c.emit('45 3b 74 24 20'); c.branch('0f 83', 'pc_done')
    c.emit('4d 6b de 30 49 01 fb 4d 8b 13 4c 39 d0')
    c.branch('0f 82', 'pc_next')
    c.emit('41 8b 4b 08 4c 01 d1 48 39 c8'); c.branch('0f 82', 'pc_failed')
    c.label('pc_next'); c.emit('41 ff c6'); c.branch('e9', 'pc_patch_loop')
    c.label('pc_done'); c.emit('41 ff c5'); c.branch('e9', 'context_loop')
    c.label('context_done'); byte_gate('after')
    c.emit('45 31 f6')
    c.label('patch_loop')
    c.emit('45 3b 74 24 20'); c.branch('0f 83', 'resume_all')
    patch_pointer()
    c.emit('49 8b 0f 41 8b 57 08 41 b8 40 00 00 00 4d 8d 4f 20'); call(88)
    c.emit('85 c0'); c.branch('0f 84', 'protect_failed')
    c.emit('41 c7 47 28 01 00 00 00 41 8b 47 20 41 3b 47 0c')
    c.branch('0f 85', 'protect_failed')
    c.emit('4d 8b 17 4d 8b 5f 18 31 db')
    c.label('write_byte')
    c.emit('41 8a 04 1b 41 88 04 1a ff c3 41 3b 5f 08')
    c.branch('0f 82', 'write_byte')
    c.emit('41 c7 47 2c 01 00 00 00 41 ff 44 24 10')
    c.emit('49 8b 4c 24 38 49 8b 17 45 8b 47 08'); call(96)
    c.emit('85 c0'); c.branch('0f 84', 'flush_failed')
    c.emit('49 8b 0f 41 8b 57 08 45 8b 47 20 4d 8d 4f 24'); call(88)
    c.emit('85 c0'); c.branch('0f 84', 'restore_failed')
    c.emit('41 c7 47 28 00 00 00 00 41 ff c6'); c.branch('e9', 'patch_loop')
    c.label('bytes_failed'); c.emit('45 89 74 24 08'); failed(BYTES_CHANGED)
    c.label('suspend_failed')
    # Exact body proven from this host's kernel32 GetLastError -> KernelBase.
    # Capture before any Resume/API can change the installing thread's last error.
    c.emit('65 48 8b 04 25 30 00 00 00 8b 40 68 41 89 44 24 78 45 89 6c 24 6c')
    failed(SUSPEND_FAILED)
    c.label('already_suspended'); failed(ALREADY_SUSPENDED)
    c.label('context_failed'); failed(CONTEXT_FAILED)
    c.label('pc_failed'); c.emit('45 89 74 24 08'); failed(PC_IN_INSTRUCTION)
    for name, reason in (('protect_failed', PROTECT_FAILED), ('flush_failed', FLUSH_FAILED), ('restore_failed', RESTORE_FAILED)):
        c.label(name); c.emit('45 89 74 24 08'); failed(reason, 'rollback')

    c.label('rollback'); c.emit('45 8b 74 24 20')
    c.label('rollback_loop')
    c.emit('45 85 f6'); c.branch('0f 84', 'resume_all')
    c.emit('41 ff ce'); patch_pointer()
    c.emit('41 83 7f 28 00'); c.branch('0f 85', 'rollback_page')
    c.emit('41 83 7f 2c 00'); c.branch('0f 84', 'rollback_loop')
    c.label('rollback_page')
    c.emit('49 8b 0f 41 8b 57 08 41 b8 40 00 00 00 4d 8d 4f 24'); call(88)
    c.emit('85 c0'); c.branch('0f 84', 'rollback_page_failed')
    c.emit('41 83 7f 2c 00'); c.branch('0f 84', 'rollback_restore_protection')
    c.emit('4d 8b 17 4d 8b 5f 10 31 db')
    c.label('rollback_byte')
    c.emit('41 8a 04 1b 41 88 04 1a ff c3 41 3b 5f 08')
    c.branch('0f 82', 'rollback_byte')
    c.emit('41 ff 44 24 68 49 8b 4c 24 38 49 8b 17 45 8b 47 08'); call(96)
    c.emit('85 c0'); c.branch('0f 85', 'rollback_restore_protection')
    c.emit('41 ff 44 24 14')
    c.label('rollback_restore_protection')
    c.emit('49 8b 0f 41 8b 57 08 45 8b 47 20 4d 8d 4f 24'); call(88)
    c.emit('85 c0'); c.branch('0f 85', 'rollback_loop')
    c.label('rollback_page_failed'); c.emit('41 ff 44 24 14'); c.branch('e9', 'rollback_loop')
    c.label('resume_all'); c.emit('45 8b 6c 24 0c')
    c.label('resume_loop'); c.emit('45 85 ed'); c.branch('0f 84', 'unlocked')
    c.emit('41 ff cd'); thread_pointer(); c.emit('49 8b 0f'); call(80)
    c.emit('41 89 47 1c 83 f8 ff'); c.branch('0f 85', 'resume_loop')
    c.emit('41 ff 44 24 18'); c.branch('e9', 'resume_loop')
    c.label('unlocked'); c.emit('41 c7 04 24 00 00 00 00 41 8b 44 24 04')
    c.branch('e9', 'return')
    c.label('busy'); c.emit('b8 01 00 00 00')
    c.label('return'); c.emit('48 83 c4 30 41 5f 41 5e 41 5d 41 5c 5f 5e 5b c3')
    return c.finish()


class OwnedThreadPauseV2:
    """Open only supplied owned TIDs; no snapshots or foreign process access."""
    def __init__(self, bridge, thread_ids):
        ids = tuple(thread_ids)
        if bridge.closed or not 1 <= len(ids) <= 256 or len(set(ids)) != len(ids):
            raise ValueError('owned v2 requires 1..256 distinct worker IDs')
        self.bridge, self.ids, self.handles, self.contexts = bridge, ids, [], []
        k = bridge.kernel
        k.GetCurrentProcessId.restype = ctypes.c_uint32
        k.GetCurrentThreadId.restype = ctypes.c_uint32
        k.OpenThread.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        k.OpenThread.restype = ctypes.c_void_p
        k.GetProcessIdOfThread.argtypes = [ctypes.c_void_p]
        k.GetProcessIdOfThread.restype = ctypes.c_uint32
        k.GetThreadId.argtypes = [ctypes.c_void_p]; k.GetThreadId.restype = ctypes.c_uint32
        for name in ('SuspendThread', 'ResumeThread'):
            getattr(k, name).argtypes = [ctypes.c_void_p]
            getattr(k, name).restype = ctypes.c_uint32
        k.GetThreadContext.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        k.GetThreadContext.restype = ctypes.c_int
        k.CloseHandle.argtypes = [ctypes.c_void_p]; k.CloseHandle.restype = ctypes.c_int
        own_pid, own_tid = k.GetCurrentProcessId(), k.GetCurrentThreadId()
        try:
            for tid in ids:
                if not isinstance(tid, int) or not 0 < tid < 2**32 or tid == own_tid:
                    raise ValueError('invalid owned worker ID or installer thread')
                handle = k.OpenThread(0x802 | 0x8, False, tid)
                if not handle: raise ctypes.WinError(ctypes.get_last_error())
                self.handles.append(handle)
                if k.GetProcessIdOfThread(handle) != own_pid or k.GetThreadId(handle) != tid:
                    raise ValueError('foreign or reused worker ID refused')
                storage = ctypes.create_string_buffer(0x4D0 + 16)
                aligned = (ctypes.addressof(storage) + 15) & ~15
                ctypes.c_uint32.from_address(aligned + 0x30).value = 0x100001
                self.contexts.append((storage, aligned))
        except BaseException:
            self.close(); raise

    def close(self):
        for handle in reversed(self.handles): self.bridge.kernel.CloseHandle(handle)
        self.handles = []


class OwnedSixByteCallsite:
    """Real full six-byte FF15 call; pointer slots are preallocated owned data."""
    patch_length = 6
    def __init__(self, bridge, original):
        self.bridge, self.installed, self.installed_bytes = bridge, False, None
        self.original_address = int(ctypes.cast(original, ctypes.c_void_p).value)
        if bridge.closed or self.original_address not in bridge._procedures:
            raise ValueError('six-byte call original must be an owned native procedure')
        self._slots = {}
        code = bytes.fromhex('48 83 ec 28 ff 15 00 00 00 00 48 83 c4 28 c3')
        self._entry = bridge._procedure(code, ctypes.c_uint64, ctypes.c_void_p,
            unwind=bytes.fromhex('01040100 0442 0000'))
        self.address = int(ctypes.cast(self._entry, ctypes.c_void_p).value)
        self.call_address = self.address + 4
        self.original_bytes = self.patch_bytes_for_target(self.original_address)
        self.fixture_alter_owned_instruction(self.original_bytes)

    def patch_bytes_for_target(self, target_address):
        if target_address not in self.bridge._procedures:
            raise ValueError('six-byte slot target must be owned')
        if target_address not in self._slots:
            slot = self.bridge._allocate(8, executable=False)
            ctypes.c_uint64.from_address(slot).value = target_address
            self._slots[target_address] = slot
        delta = self._slots[target_address] - (self.call_address + 6)
        if not -(2**31) <= delta < 2**31:
            raise ValueError('owned FF15 pointer slot out of rel32 range')
        return b'\xff\x15' + delta.to_bytes(4, 'little', signed=True)

    def fixture_alter_owned_instruction(self, replacement):
        if len(replacement) != 6 or self.bridge.closed:
            raise ValueError('owned six-byte instruction required')
        old, scratch = ctypes.c_uint32(), ctypes.c_uint32()
        k = self.bridge.kernel
        if not k.VirtualProtect(self.address, 4096, 4, ctypes.byref(old)):
            raise ctypes.WinError(ctypes.get_last_error())
        try: ctypes.memmove(self.call_address, replacement, 6)
        finally:
            if not k.VirtualProtect(self.address, 4096, old.value, ctypes.byref(scratch)):
                raise ctypes.WinError(ctypes.get_last_error())
        if not k.FlushInstructionCache(k.GetCurrentProcess(), self.call_address, 6):
            raise ctypes.WinError(ctypes.get_last_error())

    def invoke(self, pointer): return self._entry(pointer)


class OwnedPatchTransactionV4:
    """Prepare every allocation/API before one native call on owned workers."""
    def __init__(self, bridge, thread_ids, changes, *, fault_functions=None):
        if bridge.closed or not 1 <= len(changes) <= 8:
            raise ValueError('live owned bridge and 1..8 full instruction changes required')
        self.bridge, self.closed, self.buffers, self.changes = bridge, False, [], []
        self.pause = OwnedThreadPauseV2(bridge, thread_ids)
        try:
            self.threads = (ThreadRecord * len(self.pause.ids))()
            for i, (tid, handle, (_, context)) in enumerate(zip(self.pause.ids,
                    self.pause.handles, self.pause.contexts)):
                self.threads[i] = ThreadRecord(handle=handle, context=context, thread_id=tid)
            self.patches = (PatchRecord * len(changes))()
            addresses = set()
            k = bridge.kernel
            k.VirtualQuery.argtypes = [ctypes.c_void_p, ctypes.POINTER(MemoryInformation), ctypes.c_size_t]
            k.VirtualQuery.restype = ctypes.c_size_t
            for i, (site, target) in enumerate(changes):
                if site.bridge is not bridge or site.address not in bridge._procedures:
                    raise ValueError('callsite must belong to this live owned bridge')
                address, length = site.call_address, getattr(site, 'patch_length', 5)
                proc = bridge._procedures[site.address]
                if length not in (5, 6) or (address, length) in addresses or not site.address <= address < address + length <= site.address + len(proc['code']):
                    raise ValueError('distinct full owned instruction span required')
                if any(address < other + size and other < address + length for other, size in addresses):
                    raise ValueError('owned instruction spans cannot overlap')
                addresses.add((address, length))
                target_address = site.original_address if target is None else int(ctypes.cast(target, ctypes.c_void_p).value)
                if target_address not in bridge._procedures:
                    raise ValueError('replacement target must be an owned native procedure')
                expected = ctypes.string_at(address, length)
                if length == 5:
                    if expected[:1] != b'\xe8': raise ValueError('owned E8 instruction required')
                    delta = target_address - (address + 5)
                    if not -(2**31) <= delta < 2**31: raise ValueError('owned E8 target out of range')
                    replacement = b'\xe8' + delta.to_bytes(4, 'little', signed=True)
                else:
                    if not isinstance(site, OwnedSixByteCallsite) or expected[:2] != b'\xff\x15':
                        raise ValueError('owned whole six-byte FF15 instruction required')
                    replacement = site.patch_bytes_for_target(target_address)
                region = MemoryInformation()
                if (k.VirtualQuery(address, ctypes.byref(region), ctypes.sizeof(region)) != ctypes.sizeof(region)
                        or region.state != 0x1000 or region.kind != 0x20000
                        or region.protection & 0x100 or region.protection & 0xff not in (0x20, 0x40, 0x80)
                        or not region.base <= address < address + length <= region.base + region.size):
                    raise ValueError('owned instruction page protection/range could not be prepared')
                old, new = ctypes.create_string_buffer(expected), ctypes.create_string_buffer(replacement)
                self.buffers.extend((old, new))
                self.patches[i] = PatchRecord(address, length, region.protection, ctypes.addressof(old), ctypes.addressof(new))
                self.changes.append((site, target_address, replacement))
            nt = bridge.nt
            nt.NtGetNextThread.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
                ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)]
            nt.NtGetNextThread.restype = ctypes.c_int32
            functions = {name: int(ctypes.cast(getattr(k, api), ctypes.c_void_p).value)
                for name, api in (('suspend', 'SuspendThread'), ('get_context', 'GetThreadContext'),
                    ('resume', 'ResumeThread'), ('protect', 'VirtualProtect'),
                    ('flush', 'FlushInstructionCache'), ('get_thread_id', 'GetThreadId'),
                    ('close_handle', 'CloseHandle'))}
            functions['nt_get_next_thread'] = int(ctypes.cast(nt.NtGetNextThread, ctypes.c_void_p).value)
            for name, procedure in (fault_functions or {}).items():
                address = int(ctypes.cast(procedure, ctypes.c_void_p).value)
                if name not in functions or address not in bridge._procedures:
                    raise ValueError('fault fixture must be a known owned native procedure')
                functions[name] = address
            self.job = Job(thread_count=len(self.threads), patch_count=len(self.patches),
                threads=ctypes.addressof(self.threads), patches=ctypes.addressof(self.patches),
                process=k.GetCurrentProcess(), installer_tid=k.GetCurrentThreadId(), **functions)
            self.entry = bridge._procedure(transaction_code(), ctypes.c_uint32, ctypes.c_void_p, unwind=UNWIND)
            bridge._keepalive.append(self)
        except BaseException:
            self.pause.close(); raise

    def execute(self):
        if self.closed or self.bridge.closed or self.bridge.kernel.GetCurrentThreadId() != self.job.installer_tid:
            raise ValueError('closed transaction or caller differs from prepared installer')
        returned = int(self.entry(ctypes.addressof(self.job)))
        successful = returned == OK and self.job.rollback_failures == 0 and self.job.resume_failures == 0 and self.job.enum_failures == 0
        if successful:
            for site, target, replacement in self.changes:
                site.installed = target != site.original_address
                site.installed_bytes = replacement if site.installed else None
        primary = RESULT_NAMES[returned]
        reason = ('resume_failed' if self.job.resume_failures else 'rollback_failed' if self.job.rollback_failures
                  else 'enum_failed' if self.job.enum_failures else primary)
        return {'returned': returned, 'reason': reason, 'primary_reason': primary, 'complete': successful,
                'suspended': self.job.suspended, 'patched': self.job.patched,
                'rollback_restored': self.job.rollback_restored,
                'rollback_failures': self.job.rollback_failures, 'resume_failures': self.job.resume_failures,
                'failed_patch': self.job.failed_patch, 'worker_pcs': [t.rip for t in self.threads],
                'resume_counts': [t.resumed for t in self.threads], 'lock': self.job.lock,
                'enumerated': self.job.enumerated, 'enum_status': self.job.enum_status,
                'enum_failures': self.job.enum_failures, 'seen': [t.seen for t in self.threads],
                'failed_thread_index': self.job.reserved2,
                'failed_thread_id': self.threads[self.job.reserved2].thread_id
                    if returned == SUSPEND_FAILED and self.job.reserved2 < len(self.threads) else None,
                'suspend_last_error': self.job.enum_status if returned == SUSPEND_FAILED else None,
                'enum_handles_released': not self.job.enum_cursor and not self.job.enum_next,
                'python_or_lua_during_pause': False, 'game_access': False}

    def close(self):
        if not self.closed: self.pause.close(); self.closed = True

    def __enter__(self): return self
    def __exit__(self, *_): self.close()


FFI_CDEF = '''
typedef struct LedgerPatchThreadV2 {
    void *handle; void *context; uint64_t rip; uint32_t prior; uint32_t resumed;
    uint32_t thread_id; uint32_t seen;
} LedgerPatchThreadV2;
typedef struct LedgerPatchRowV2 {
    void *address; uint32_t length; uint32_t expected_protection;
    void *expected; void *replacement; uint32_t prior_protection;
    uint32_t scratch_protection; uint32_t protection_changed; uint32_t written;
} LedgerPatchRowV2;
typedef struct LedgerPatchJobV2 {
    uint32_t lock; uint32_t result; uint32_t failed_patch; uint32_t suspended;
    uint32_t patched; uint32_t rollback_failures; uint32_t resume_failures;
    uint32_t thread_count; uint32_t patch_count; uint32_t reserved;
    void *threads; void *patches; void *process;
    void *suspend; void *get_context; void *resume; void *protect; void *flush;
    uint32_t rollback_restored; uint32_t reserved2;
    uint32_t installer_tid; uint32_t enumerated; uint32_t enum_status; uint32_t enum_failures;
    void *nt_get_next_thread; void *get_thread_id; void *close_handle;
    void *enum_cursor; void *enum_next;
} LedgerPatchJobV2;
'''


def manifest():
    """Pure no-runtime export: no handles are opened and no native API called."""
    def shape(structure, name):
        return {'name': name, 'size': ctypes.sizeof(structure), 'alignment': ctypes.alignment(structure),
            'fields': [{'name': field, 'offset': getattr(structure, field).offset, 'bytes': ctypes.sizeof(kind),
                'type': 'void*' if kind is ctypes.c_void_p else 'uint64_t' if kind is ctypes.c_uint64 else 'uint32_t'}
                for field, kind in structure._fields_]}
    code = transaction_code()
    return {'revision': 'owned_native_patch_transaction_manifest_v4', 'abi': 2,
        'entries': [{'name': 'patch_transaction_v2', 'code_hex': code.hex(), 'entry_offset': 0,
            'executable_length': len(code), 'unwind_hex': UNWIND.hex(), 'relocations': []}],
        'signature': 'uint32_t (*)(LedgerPatchJobV2 *job)', 'argument_register': 'RCX',
        'ffi_cdef': FFI_CDEF,
        'layouts': {'job': shape(Job, 'LedgerPatchJobV2'), 'thread': shape(ThreadRecord, 'LedgerPatchThreadV2'),
                    'patch': shape(PatchRecord, 'LedgerPatchRowV2')},
        'limits': {'threads_min': 1, 'threads_max': 256, 'patches_min': 1, 'patches_max': 8,
            'trusted_profile_patch_lengths': [5, 6], 'actual_owned_fixture_lengths': [5, 6],
            'native_rejects_invalid_descriptor_bounds': 'counts and instruction lengths only'},
        'context': {'bytes_min': 0x4D0, 'alignment': 16, 'flags_offset': 0x30,
                    'flags_value': 0x100001, 'rip_offset': 0xF8},
        'win32_functions': {
            'suspend': 'uint32_t SuspendThread(void *thread)',
            'get_context': 'int GetThreadContext(void *thread, void *aligned_context)',
            'resume': 'uint32_t ResumeThread(void *thread)',
            'protect': 'int VirtualProtect(void *address, size_t length, uint32_t protect, uint32_t *old)',
            'flush': 'int FlushInstructionCache(void *current_process, void *address, size_t length)',
            'nt_get_next_thread': 'int32_t NtGetNextThread(void *current_process, void *previous_thread, uint32_t desired_access, uint32_t attributes, uint32_t flags, void **next_thread)',
            'get_thread_id': 'uint32_t GetThreadId(void *thread)',
            'close_handle': 'int CloseHandle(void *handle)'},
        'enumeration': {'current_process_pseudo_handle': '-1', 'desired_access': 0x800,
            'attributes': 0, 'flags': 0, 'status_no_more_entries': 0x8000001A,
            'required_ids': 'exact distinct prepared worker thread IDs plus installer_tid',
            'required_count': 'thread_count+1', 'handle_equality_is_identity': False,
            'post_suspend_check': True, 'failures_write_nothing': True,
            'resumption_order': 'reverse prepared order'},
        'host_initialization': [
            'Allocate zeroed Job168B/Thread40B/Patch48B; retain every buffer and process-life code/unwind table.',
            'Open explicit owned worker handles before entry; verify current PID and TID and exclude installer.',
            'Allocate each CONTROL context at16B alignment, >=1232B; store uint32 0x100001 at+0x30.',
            'Fill worker handle/context/thread_id; all IDs distinct. Native entry clears seen/prior/resumed.',
            'Validate complete owned 5/6-byte instruction spans, bytes, ownership, page protections, no overlaps.',
            'Resolve all eight native function pointers before suspension and fill job. No absolute API addresses in code.',
            'Set job.process to current-process pseudo HANDLE -1 with exact pointer/intptr cast, and installer_tid to current TID.',
            'Call entry once with RCX job pointer; no Lua/Python/GC/heap allocation/snapshot API during suspension.',
            'Native NtGetNextThread uses six arguments and only current process; close all temporary enumeration handles.',
            'Success requires returned0 AND rollback_failures0 AND resume_failures0 AND enum_failures0.',
            'Busy return1 does not provide a fresh job result; preserve the in-progress job and do not infer worker state.'],
        'result_codes': {name: number for number, name in enumerate(RESULT_NAMES)},
        'game_connected': False, 'game_access': False, 'game_thread_set_complete': False,
        'new_thread_barrier_proven': False, 'unexpected_seh_cleanup_handler': False,
        'six_byte_span_actual_tested': True,
        'six_byte_span_fixture': 'actual owned FF15 instruction; synthetic CONTROL.Rip offsets0..5 and exclusive end6; real SuspendThread/ResumeThread',
        'owned_verification_report': 'verification.json',
        'suspend_failure_diagnostic': {'result': 2, 'last_error_field': 'enum_status',
            'last_error_offset': 120, 'failed_index_field': 'reserved2', 'failed_index_offset': 108,
            'failed_index_base': 0, 'index_not_failed': 0xFFFFFFFF,
            'thread_id': 'threads[reserved2].thread_id; valid only on result2',
            'capture': 'immediate inline exact GetLastError body before any cleanup call',
            'get_last_error_body_hex': '65488b0425300000008b4068c3',
            'kernel32_export_pin_hex': '48ff2539e40600',
            'observed_kernelbase_target_rva': 0x253A0,
            'enum_status_meaning': 'Win32 last error when result2; otherwise NtGetNextThread status'},
        'prior_suspend_counts': {'accepted': True, 'suspend_failure': 0xFFFFFFFF,
            'owned_increment_per_success': 1, 'resume_calls_per_added_increment': 1,
            'expected_resume_return': 'prior+1', 'pre_existing_suspend_count_preserved': True}}


if __name__ == '__main__':
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description='Pure v2 native transaction export; no process access.')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest(), indent=2) + '\n', encoding='utf8')
    print(args.output.resolve())


