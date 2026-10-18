"""One native transaction on explicit tool-owned workers and E8 callsites.

All handles, buffers, contexts, byte plans and Win32 pointers are prepared before
the native entry. Between its first SuspendThread and final ResumeThread there
is no Python/Lua callback or allocation. This is not a game installer.
"""
import ctypes

from hit_bridge_owned import _Code
from hit_patch_threads_owned import OwnedThreadPause

OK, BUSY, SUSPEND_FAILED, ALREADY_SUSPENDED, CONTEXT_FAILED = range(5)
PC_IN_INSTRUCTION, BYTES_CHANGED, PROTECT_FAILED, FLUSH_FAILED, RESTORE_FAILED = range(5, 10)
RESULT_NAMES = ('ok', 'busy', 'suspend_failed', 'already_suspended', 'context_failed',
                'pc_in_instruction', 'bytes_changed', 'protect_failed', 'flush_failed', 'restore_failed')
UNWIND = bytes.fromhex('010f0800 0f32 0bf0 09e0 07d0 05c0 0370 0260 0130')


class ThreadRecord(ctypes.Structure):
    _fields_ = [('handle', ctypes.c_void_p), ('context', ctypes.c_void_p),
                ('rip', ctypes.c_uint64), ('prior', ctypes.c_uint32), ('resumed', ctypes.c_uint32)]


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
                ('rollback_restored', ctypes.c_uint32), ('reserved2', ctypes.c_uint32)]


assert ctypes.sizeof(ThreadRecord) == 32 and ctypes.sizeof(PatchRecord) == 48
assert Job.threads.offset == 40 and Job.suspend.offset == 64 and Job.rollback_restored.offset == 104


class MemoryInformation(ctypes.Structure):
    _fields_ = [('base', ctypes.c_void_p), ('allocation', ctypes.c_void_p),
                ('allocation_protection', ctypes.c_uint32), ('partition', ctypes.c_uint16),
                ('size', ctypes.c_size_t), ('state', ctypes.c_uint32),
                ('protection', ctypes.c_uint32), ('kind', ctypes.c_uint32)]


assert ctypes.sizeof(MemoryInformation) == 48


def transaction_code():
    c = _Code()
    # Seven nonvolatile pushes, aligned32B shadow space; no XMM use.
    c.emit('53 56 57 41 54 41 55 41 56 41 57 48 83 ec 20 49 89 cc')
    c.emit('31 c0 41 b8 01 00 00 00 f0 45 0f b1 04 24')
    c.branch('0f 85', 'busy')
    for offset in (4, 12, 16, 20, 24, 104):
        c.emit('41 c7 44 24 ' + bytes([offset]).hex() + ' 00 00 00 00')
    c.emit('41 c7 44 24 08 ff ff ff ff 49 8b 74 24 28 49 8b 7c 24 30')

    def call(offset):
        c.emit('49 8b 44 24 ' + bytes([offset]).hex() + ' ff d0')

    def patch_pointer():
        c.emit('4d 6b fe 30 49 01 ff')  # R15=patches+R14*48

    def thread_pointer():
        c.emit('4d 6b fd 20 49 01 f7')  # R15=threads+R13*32

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

    byte_gate('before', reset=True)
    c.emit('45 31 ed')
    c.label('suspend_loop')
    c.emit('45 3b 6c 24 1c'); c.branch('0f 83', 'context_start')
    thread_pointer(); c.emit('49 8b 0f'); call(64)
    c.emit('41 89 47 18 83 f8 ff'); c.branch('0f 84', 'suspend_failed')
    c.emit('41 ff 44 24 0c 85 c0'); c.branch('0f 85', 'already_suspended')
    c.emit('41 ff c5'); c.branch('e9', 'suspend_loop')
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
    c.label('suspend_failed'); failed(SUSPEND_FAILED)
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
    c.label('return'); c.emit('48 83 c4 20 41 5f 41 5e 41 5d 41 5c 5f 5e 5b c3')
    return c.finish()


class OwnedPatchTransaction:
    """Prepare first, then call exactly one owned native transaction entry.

    changes=(OwnedE8Callsite, target-or-None); None restores its original target.
    Explicit thread IDs must name the fixture's known native workers. No thread
    enumeration is done or a claim made that arbitrary process threads are safe.
    """
    def __init__(self, bridge, thread_ids, changes, *, fault_functions=None):
        if bridge.closed or not changes or len(changes) > 8:
            raise ValueError('live owned bridge and1..8 E8 changes required')
        self.bridge, self.closed = bridge, False
        self.pause = OwnedThreadPause(bridge, thread_ids)
        self.buffers, self.changes = [], []
        try:
            self.threads = (ThreadRecord * len(self.pause.handles))()
            for i, (handle, (_, context)) in enumerate(zip(self.pause.handles, self.pause.contexts)):
                self.threads[i] = ThreadRecord(handle, context)
            self.patches = (PatchRecord * len(changes))()
            addresses = set()
            for i, (site, target) in enumerate(changes):
                if site.bridge is not bridge or site.address not in bridge._procedures:
                    raise ValueError('callsite must belong to this live owned bridge')
                address = site.call_address
                proc = bridge._procedures[site.address]
                if address in addresses or not site.address <= address < address + 5 <= site.address + len(proc['code']):
                    raise ValueError('distinct full owned E8 instruction required')
                addresses.add(address)
                target_address = site.original_address if target is None else int(ctypes.cast(target, ctypes.c_void_p).value)
                if target_address not in bridge._procedures:
                    raise ValueError('replacement target must be an owned native procedure')
                delta = target_address - (address + 5)
                if not -(2**31) <= delta < 2**31:
                    raise ValueError('owned E8 target out of rel32 range')
                expected = ctypes.string_at(address, 5)
                if expected[:1] != b'\xe8':
                    raise ValueError('the actual owned instruction is not E8')
                replacement = b'\xe8' + delta.to_bytes(4, 'little', signed=True)
                k = bridge.kernel
                k.VirtualQuery.argtypes = [ctypes.c_void_p, ctypes.POINTER(MemoryInformation), ctypes.c_size_t]
                k.VirtualQuery.restype = ctypes.c_size_t
                region = MemoryInformation()
                if (k.VirtualQuery(address, ctypes.byref(region), ctypes.sizeof(region)) != ctypes.sizeof(region)
                        or region.state != 0x1000 or region.kind != 0x20000
                        or region.protection & 0x100 or region.protection & 0xff not in (0x20, 0x40, 0x80)
                        or not region.base <= address < address + 5 <= region.base + region.size):
                    raise ValueError('owned E8 page protection/range could not be prepared')
                old, new = ctypes.create_string_buffer(expected), ctypes.create_string_buffer(replacement)
                self.buffers.extend((old, new))
                self.patches[i] = PatchRecord(address, 5, region.protection, ctypes.addressof(old), ctypes.addressof(new))
                self.changes.append((site, target_address, replacement))
            k = bridge.kernel
            functions = {name: int(ctypes.cast(getattr(k, api), ctypes.c_void_p).value)
                         for name, api in (('suspend', 'SuspendThread'), ('get_context', 'GetThreadContext'),
                                           ('resume', 'ResumeThread'), ('protect', 'VirtualProtect'),
                                           ('flush', 'FlushInstructionCache'))}
            for name, procedure in (fault_functions or {}).items():
                address = int(ctypes.cast(procedure, ctypes.c_void_p).value)
                if name not in functions or address not in bridge._procedures:
                    raise ValueError('fault fixture must be a known owned native procedure')
                functions[name] = address
            self.job = Job(thread_count=len(self.threads), patch_count=len(self.patches),
                           threads=ctypes.addressof(self.threads), patches=ctypes.addressof(self.patches),
                           process=k.GetCurrentProcess(), **functions)
            self.entry = bridge._procedure(transaction_code(), ctypes.c_uint32, ctypes.c_void_p, unwind=UNWIND)
            bridge._keepalive.append(self)
        except BaseException:
            self.pause.close(); raise

    def execute(self):
        if self.closed or self.bridge.closed:
            raise ValueError('closed owned transaction')
        if self.bridge.kernel.GetCurrentThreadId() in self.pause.ids:
            raise ValueError('native transaction caller cannot be one of its paused workers')
        returned = int(self.entry(ctypes.addressof(self.job)))
        successful = returned == OK and self.job.rollback_failures == 0 and self.job.resume_failures == 0
        if successful:
            for site, target, replacement in self.changes:
                site.installed = target != site.original_address
                site.installed_bytes = replacement if site.installed else None
        primary = RESULT_NAMES[returned]
        reason = ('resume_failed' if self.job.resume_failures else
                  'rollback_failed' if self.job.rollback_failures else primary)
        return {'returned': returned, 'reason': reason, 'primary_reason': primary, 'complete': successful,
                'suspended': self.job.suspended, 'patched': self.job.patched,
                'rollback_restored': self.job.rollback_restored,
                'rollback_failures': self.job.rollback_failures, 'resume_failures': self.job.resume_failures,
                'failed_patch': self.job.failed_patch, 'worker_pcs': [t.rip for t in self.threads],
                'resume_counts': [t.resumed for t in self.threads], 'lock': self.job.lock,
                'python_or_lua_during_pause': False, 'game_access': False}

    def close(self):
        if not self.closed:
            self.pause.close(); self.closed = True

    def __enter__(self): return self
    def __exit__(self, *_): self.close()


FFI_CDEF = '''
typedef struct LedgerPatchThreadV1 {
    void *handle; void *context; uint64_t rip; uint32_t prior; uint32_t resumed;
} LedgerPatchThreadV1;
typedef struct LedgerPatchRowV1 {
    void *address; uint32_t length; uint32_t expected_protection;
    void *expected; void *replacement; uint32_t prior_protection;
    uint32_t scratch_protection; uint32_t protection_changed; uint32_t written;
} LedgerPatchRowV1;
typedef struct LedgerPatchJobV1 {
    uint32_t lock; uint32_t result; uint32_t failed_patch; uint32_t suspended;
    uint32_t patched; uint32_t rollback_failures; uint32_t resume_failures;
    uint32_t thread_count; uint32_t patch_count; uint32_t reserved;
    void *threads; void *patches; void *process;
    void *suspend; void *get_context; void *resume; void *protect; void *flush;
    uint32_t rollback_restored; uint32_t reserved2;
} LedgerPatchJobV1;
'''


def manifest():
    """Pure generation: entry has no absolute address constants/relocations."""
    def shape(structure, name):
        return {'name': name, 'size': ctypes.sizeof(structure), 'alignment': ctypes.alignment(structure),
                'fields': [{'name': field, 'offset': getattr(structure, field).offset,
                            'bytes': ctypes.sizeof(kind),
                            'type': 'void*' if kind is ctypes.c_void_p else
                                    'uint64_t' if kind is ctypes.c_uint64 else 'uint32_t'}
                           for field, kind in structure._fields_]}
    code = transaction_code()
    return {'revision': 'owned_native_patch_transaction_manifest_v1', 'abi': 1,
            'entries': [{'name': 'patch_transaction', 'code_hex': code.hex(),
                         'entry_offset': 0, 'executable_length': len(code),
                         'unwind_hex': UNWIND.hex(), 'relocations': []}],
            'signature': 'uint32_t (*)(LedgerPatchJobV1 *job)', 'argument_register': 'RCX',
            'ffi_cdef': FFI_CDEF,
            'layouts': {'job': shape(Job, 'LedgerPatchJobV1'),
                        'thread': shape(ThreadRecord, 'LedgerPatchThreadV1'),
                        'patch': shape(PatchRecord, 'LedgerPatchRowV1')},
            'limits': {'threads_min': 1, 'threads_max': 16, 'patches_min': 1, 'patches_max': 8,
                       'trusted_profile_patch_lengths': [5, 6], 'actual_owned_fixture_lengths': [5],
                       'native_rejects_invalid_descriptor_bounds': False},
            'context': {'bytes_min': 0x4D0, 'alignment': 16, 'flags_offset': 0x30,
                        'flags_value': 0x100001, 'rip_offset': 0xF8},
            'win32_functions': {
                'suspend': 'uint32_t SuspendThread(void *thread)',
                'get_context': 'int GetThreadContext(void *thread, void *aligned_context)',
                'resume': 'uint32_t ResumeThread(void *thread)',
                'protect': 'int VirtualProtect(void *address, size_t length, uint32_t protect, uint32_t *old)',
                'flush': 'int FlushInstructionCache(void *current_process, void *address, size_t length)'},
            'host_initialization': [
                'Allocate zeroed job112B/thread32B/patch48B arrays and retain all buffers/process-life code and unwind tables.',
                'Open explicit thread handles before entry; verify current PID, exclude calling TID, and prove safe known worker set.',
                'Allocate each CONTROL context at16B-aligned address, >=1232B, storeuint32 0x100001 at+0x30.',
                'Fill thread.handle/context. Fill patch address/length/expected/new buffers and exact prevalidated page protection.',
                'Fill job.thread_count/patch_count/threads/patches and five real preloaded Win32 function pointers.',
                'Set job.process to current-process pseudo HANDLE -1 via an exact pointer/intptr cdata cast, never a foreign handle.',
                'Validate ranges/ownership/whole instruction spans/length5or6/counts before entry. The native primitive trusts prepared descriptors.',
                'Cast function pointer once and call with job; no Lua/Python executes between native suspension/resume.',
                'Read return code then rollback/resume failure fields. Busy return1 must not be mistaken for a fresh result snapshot.'],
            'result_codes': {name: code for code, name in enumerate(RESULT_NAMES)},
            'game_connected': False, 'game_access': False,
            'game_thread_set_complete': False, 'new_thread_barrier_proven': False,
            'six_byte_span_actual_tested': False, 'unexpected_seh_cleanup_handler': False}


if __name__ == '__main__':
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description='Export pure native transaction bytes/layout; no process access.')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest(), indent=2) + '\n', encoding='utf8')
    print(args.output.resolve())
