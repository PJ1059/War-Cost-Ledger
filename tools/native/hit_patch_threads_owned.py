"""Pause explicitly known tool-owned native workers for an owned E8 change.

This cannot open an external process, enumerate game threads or patch game
memory. It demonstrates the missing concurrency boundary of the earlier
Python-lock fixture. A live adapter still needs its own proved quiescent phase.
"""
import ctypes
from contextlib import contextmanager


class OwnedThreadPause:
    def __init__(self,bridge,thread_ids):
        if bridge.closed or not thread_ids or len(thread_ids)>16 or len(set(thread_ids))!=len(thread_ids):
            raise ValueError('owned pause requires 1..16 distinct explicit worker threads')
        self.bridge=bridge
        self.ids=tuple(thread_ids)
        self.handles=[]
        self.contexts=[]
        k=bridge.kernel
        k.GetCurrentProcessId.restype=ctypes.c_uint32
        k.GetCurrentThreadId.restype=ctypes.c_uint32
        k.OpenThread.argtypes=[ctypes.c_uint32,ctypes.c_int,ctypes.c_uint32]
        k.OpenThread.restype=ctypes.c_void_p
        k.GetProcessIdOfThread.argtypes=[ctypes.c_void_p]
        k.GetProcessIdOfThread.restype=ctypes.c_uint32
        k.SuspendThread.argtypes=[ctypes.c_void_p];k.SuspendThread.restype=ctypes.c_uint32
        k.ResumeThread.argtypes=[ctypes.c_void_p];k.ResumeThread.restype=ctypes.c_uint32
        k.GetThreadContext.argtypes=[ctypes.c_void_p,ctypes.c_void_p]
        k.GetThreadContext.restype=ctypes.c_int
        k.CloseHandle.argtypes=[ctypes.c_void_p];k.CloseHandle.restype=ctypes.c_int
        own_pid,own_tid=k.GetCurrentProcessId(),k.GetCurrentThreadId()
        try:
            for tid in self.ids:
                if not isinstance(tid,int) or not 0<tid<2**32 or tid==own_tid:
                    raise ValueError('the calling thread cannot be suspended')
                handle=k.OpenThread(0x802|0x8,False,tid) # suspend/context/query-limited
                if not handle:raise ctypes.WinError(ctypes.get_last_error())
                self.handles.append(handle)
                if k.GetProcessIdOfThread(handle)!=own_pid:
                    raise ValueError('external process thread refused before suspension')
                storage=ctypes.create_string_buffer(0x4D0+16)
                aligned=(ctypes.addressof(storage)+15)&~15
                ctypes.c_uint32.from_address(aligned+0x30).value=0x100001 # AMD64 CONTROL
                self.contexts.append((storage,aligned))
        except BaseException:
            self.close();raise

    def close(self):
        for handle in reversed(self.handles):self.bridge.kernel.CloseHandle(handle)
        self.handles=[]

    @contextmanager
    def paused(self,forbidden_ranges):
        if self.bridge.closed or not self.handles:
            raise ValueError('owned pause is closed')
        for begin,end in forbidden_ranges:
            if not isinstance(begin,int) or not isinstance(end,int) or not begin<end:
                raise ValueError('invalid owned instruction interval')
            if not any(at<=begin<end<=at+len(p['code']) for at,p in self.bridge._procedures.items()):
                raise ValueError('instruction interval must be in owned code')
        suspended=[]
        try:
            for handle in self.handles:
                prior=self.bridge.kernel.SuspendThread(handle)
                if prior==0xffffffff:raise ctypes.WinError(ctypes.get_last_error())
                suspended.append(handle)
                if prior!=0:raise ValueError('worker was already suspended; no patch')
            ips=[]
            for handle,(_,context) in zip(self.handles,self.contexts):
                if not self.bridge.kernel.GetThreadContext(handle,context):
                    raise ctypes.WinError(ctypes.get_last_error())
                rip=ctypes.c_uint64.from_address(context+0xF8).value
                if any(begin<=rip<end for begin,end in forbidden_ranges):
                    raise ValueError('worker PC is in the patch instruction; no write')
                ips.append(rip)
            yield ips
        finally:
            errors=[]
            for handle in reversed(suspended):
                if self.bridge.kernel.ResumeThread(handle)==0xffffffff:
                    errors.append(ctypes.get_last_error())
            if errors:raise OSError('owned worker resume failed: '+str(errors))

    def __enter__(self):return self
    def __exit__(self,*_):self.close()
