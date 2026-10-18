"""A real own-process native worker is paused/resumed; no game interaction."""
import ctypes
from pathlib import Path
import sys
import threading
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/native'))
from hit_bridge_owned import OwnedBridge,_Code
from hit_bridge_install_owned import OwnedE8Callsite
from hit_patch_threads_owned import OwnedThreadPause


class PausedPatchTests(unittest.TestCase):
    def test_real_native_worker_install_and_restore_while_paused(self):
        with OwnedBridge() as b:
            original=b._procedure(bytes.fromhex('48 ff 01 31 c0 c3'),ctypes.c_uint64)
            callsite=OwnedE8Callsite(b,original)
            seen=ctypes.c_uint64()
            observer=b._procedure(bytes.fromhex('48 b8')+ctypes.addressof(seen).to_bytes(8,'little')
                +bytes.fromhex('48 ff 00 ff 25 00 00 00 00')
                +int(ctypes.cast(original,ctypes.c_void_p).value).to_bytes(8,'little'),ctypes.c_uint64)
            # {stop u32, entered u32, original_calls u64}, all owned stable memory.
            state=ctypes.create_string_buffer(16)
            data=ctypes.addressof(state)
            c=_Code();c.emit('53 48 83 ec 30 48 89 cb c7 43 04 01 00 00 00')
            c.label('loop');c.emit('83 3b 00');c.branch('0f 85','end')
            c.emit('48 8d 4b 08 31 d2 45 31 c0 45 31 c9 48 c7 44 24 20 00 00 00 00')
            c.emit('48 b8 '+callsite.address.to_bytes(8,'little').hex(' ')+' ff d0')
            c.branch('e9','loop');c.label('end');c.emit('48 83 c4 30 5b c3')
            loop=b._procedure(c.finish(),None,ctypes.c_void_p,unwind=bytes.fromhex('01050200 0552 0130'))
            ready=threading.Event();result=[]
            def work():
                result.append(threading.get_native_id());ready.set();loop(data)
            worker=threading.Thread(target=work)
            worker.start();self.assertTrue(ready.wait(1))
            try:
                deadline=time.monotonic()+1
                while ctypes.c_uint32.from_address(data+4).value==0 and time.monotonic()<deadline:
                    time.sleep(.001)
                self.assertEqual(ctypes.c_uint32.from_address(data+4).value,1)
                with OwnedThreadPause(b,result) as pause:
                    for action in (lambda:callsite.install(observer),callsite.restore):
                        # A PC landing on the exact 5B instruction is a refusal,
                        # not permission to patch anyway. Retry only after resume.
                        for attempt in range(10):
                            try:
                                with pause.paused([(callsite.call_address,callsite.call_address+5)]) as ips:
                                    before=ctypes.c_uint64.from_address(data+8).value
                                    action()
                                    self.assertEqual(ctypes.c_uint64.from_address(data+8).value,before)
                                    self.assertEqual(len(ips),1)
                                break
                            except ValueError as error:
                                if 'worker PC' not in str(error):raise
                                time.sleep(.001)
                        else:self.fail('owned PC did not leave the instruction')
                        time.sleep(.005)
                        self.assertGreater(ctypes.c_uint64.from_address(data+8).value,before)
                        if callsite.installed:self.assertGreater(seen.value,0)
                    snapshot=seen.value
                    time.sleep(.005)
                    self.assertEqual(seen.value,snapshot)
            finally:
                ctypes.c_uint32.from_address(data).value=1
                worker.join(1)
                self.assertFalse(worker.is_alive())

    def test_self_thread_and_external_code_interval_refused(self):
        with OwnedBridge() as b:
            with self.assertRaises(ValueError):OwnedThreadPause(b,[threading.get_native_id()])
            # Invalid ranges are checked before any thread can be suspended.
            pause=OwnedThreadPause.__new__(OwnedThreadPause)
            pause.bridge=b;pause.handles=[1];pause.contexts=[]
            with self.assertRaises(ValueError):
                with pause.paused([(1,6)]):self.fail('must refuse external code')

if __name__=='__main__':unittest.main()
