"""Windows x64 read-only adapter for the external, fixed FIRE code capture.

This module only locates loaded modules and reads/query memory. Waiting, build
fingerprints, bounded code windows and output files belong to fire_code_capture.
No write, protection-changing or remote execution API is declared here.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from functools import lru_cache
import os

if __package__:
    from .probe_session import game_processes
else:
    from probe_session import game_processes

__all__ = ['game_processes', 'resolve_game', 'Process']

PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
TH32CS_SNAPMODULE = 0x00000008
TH32CS_SNAPMODULE32 = 0x00000010
ERROR_NO_MORE_FILES = 18


class _ModuleEntry(ctypes.Structure):
    _fields_ = [
        ('dwSize', wintypes.DWORD), ('th32ModuleID', wintypes.DWORD),
        ('th32ProcessID', wintypes.DWORD), ('GlblcntUsage', wintypes.DWORD),
        ('ProccntUsage', wintypes.DWORD), ('modBaseAddr', ctypes.c_void_p),
        ('modBaseSize', wintypes.DWORD), ('hModule', wintypes.HMODULE),
        ('szModule', wintypes.WCHAR * 256), ('szExePath', wintypes.WCHAR * 260),
    ]


class _MemoryBasicInformation(ctypes.Structure):
    _fields_ = [
        ('BaseAddress', ctypes.c_void_p), ('AllocationBase', ctypes.c_void_p),
        ('AllocationProtect', wintypes.DWORD), ('PartitionId', wintypes.WORD),
        ('RegionSize', ctypes.c_size_t), ('State', wintypes.DWORD),
        ('Protect', wintypes.DWORD), ('Type', wintypes.DWORD),
    ]


@lru_cache(maxsize=1)
def _kernel():
    if os.name != 'nt' or ctypes.sizeof(ctypes.c_void_p) != 8:
        raise OSError('FIRE code capture requires Windows x64 Python.')
    if (ctypes.sizeof(_ModuleEntry) != 1080
            or ctypes.sizeof(_MemoryBasicInformation) != 48
            or _MemoryBasicInformation.RegionSize.offset != 24):
        raise OSError('Unexpected Windows x64 ctypes structure layout.')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Module32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ModuleEntry)]
    kernel.Module32FirstW.restype = wintypes.BOOL
    kernel.Module32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ModuleEntry)]
    kernel.Module32NextW.restype = wintypes.BOOL
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p,
                                       ctypes.c_void_p, ctypes.c_size_t,
                                       ctypes.POINTER(ctypes.c_size_t)]
    kernel.ReadProcessMemory.restype = wintypes.BOOL
    kernel.VirtualQueryEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p,
                                     ctypes.POINTER(_MemoryBasicInformation),
                                     ctypes.c_size_t]
    kernel.VirtualQueryEx.restype = ctypes.c_size_t
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    return kernel


def _modules(pid: int) -> list[dict]:
    """One Toolhelp module snapshot; all handles close even on enumeration errors."""
    kernel = _kernel()
    snapshot = kernel.CreateToolhelp32Snapshot(
        TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid)
    if snapshot == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        entry = _ModuleEntry()
        entry.dwSize = ctypes.sizeof(entry)
        if not kernel.Module32FirstW(snapshot, ctypes.byref(entry)):
            error = ctypes.get_last_error()
            if error == ERROR_NO_MORE_FILES:
                return []
            raise ctypes.WinError(error)
        modules = []
        while True:
            modules.append({'name': str(entry.szModule),
                            'base': int(entry.modBaseAddr or 0),
                            'size': int(entry.modBaseSize),
                            'path': str(entry.szExePath)})
            if not kernel.Module32NextW(snapshot, ctypes.byref(entry)):
                error = ctypes.get_last_error()
                if error != ERROR_NO_MORE_FILES:
                    raise ctypes.WinError(error)
                return modules
    finally:
        kernel.CloseHandle(snapshot)


def resolve_game(pid: int) -> dict:
    """Resolve the loaded game.dll image and EXE paths without reading their bytes."""
    modules = {module['name'].casefold(): module for module in _modules(pid)}
    game, exe = modules.get('game.dll'), modules.get('helldivers2.exe')
    if game is None or exe is None:
        raise FileNotFoundError('Helldivers 2 EXE/game.dll modules are not loaded.')
    return {'game_base': game['base'], 'game_size': game['size'],
            'game_path': game['path'], 'exe_path': exe['path']}


class Process:
    """Explicitly closed process handle with exactly read/query permissions (0x410)."""

    def __init__(self, pid: int):
        self.pid = pid
        self._kernel = _kernel()
        self._handle = self._kernel.OpenProcess(
            PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
        if not self._handle:
            raise ctypes.WinError(ctypes.get_last_error())

    def __enter__(self):
        self._require_open()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False

    def _require_open(self):
        if self._handle is None:
            raise ValueError('Process handle is closed.')
        return self._handle

    def close(self):
        if self._handle is not None:
            handle, self._handle = self._handle, None
            if not self._kernel.CloseHandle(handle):
                raise ctypes.WinError(ctypes.get_last_error())

    def read(self, address: int, size: int) -> bytes:
        """Return exactly size bytes; inaccessible memory and short reads raise."""
        handle = self._require_open()
        if size < 0:
            raise ValueError('Read size must be nonnegative.')
        if size == 0:
            return b''
        buffer = ctypes.create_string_buffer(size)
        count = ctypes.c_size_t()
        if not self._kernel.ReadProcessMemory(
                handle, address, buffer, size, ctypes.byref(count)):
            raise ctypes.WinError(ctypes.get_last_error())
        if count.value != size:
            raise OSError('FIRE_CODE_SHORT_READ: requested %d, received %d.'
                          % (size, count.value))
        return buffer.raw

    def query(self, address: int) -> dict:
        """Return one native memory region; no page scanning or protection changes."""
        information = _MemoryBasicInformation()
        expected = ctypes.sizeof(information)
        received = self._kernel.VirtualQueryEx(
            self._require_open(), address, ctypes.byref(information), expected)
        if received == 0:
            raise ctypes.WinError(ctypes.get_last_error())
        if received != expected:
            raise OSError('FIRE_CODE_MEMORY_QUERY_SHORT: %d/%d.' % (received, expected))
        return {'base': int(information.BaseAddress or 0),
                'size': int(information.RegionSize), 'state': int(information.State),
                'type': int(information.Type), 'protect': int(information.Protect)}
