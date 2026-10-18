"""Native bounded arena fixtures use only current-tool owned memory."""
import ctypes
import sys
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/native'))
sys.path.insert(0, str(ROOT / 'tests'))
from hit_bridge_owned import OwnedBridge, NORMAL_UNWIND
from hit_contact_arena_owned import OwnedContactArena, OWNER, PHASE, HIT, ROW_SIZE
from hit_contact_context_owned import ap_stage_code, ap_call_fixture_code, curve_marker_code
from hit_entity_resolver_owned import OwnedEntityResolver
from hit_bridge_install_owned import OwnedE8Callsite
import test_native_hit_contact_context_owned as earlier_context_tests


class ContactArenaTests(unittest.TestCase):
    def test_same_hit_next_iteration_clears_unfinished_proof_and_never_sticks_ambiguous(self):
        with OwnedBridge() as b:
            a = OwnedContactArena(b); hit = (ctypes.c_uint8 * 0x118)()
            address = a.invoke('begin', hit); record = a.record(address)
            record.capture_flags = 0x1FF; record.effect_flags = 7; record.ap_delta = 99
            ctypes.c_uint32.from_address(address + PHASE).value = 4
            self.assertEqual(a.invoke('begin', hit), address)
            self.assertEqual(record.contact_ordinal, 2)
            self.assertEqual((record.capture_flags, record.effect_flags), (0, 0))
            self.assertNotEqual(record.ap_delta, record.ap_delta)
            self.assertEqual(ctypes.c_uint32.from_address(address + PHASE).value, 1)

    def test_nested_unknown_hit_preserves_outer_and_iteration_end_releases_it(self):
        with OwnedBridge() as b:
            a = OwnedContactArena(b); outer=(ctypes.c_uint8*0x118)(); inner=(ctypes.c_uint8*0x118)()
            row = a.invoke('begin', outer); a.record(row).capture_flags = 0x8C
            self.assertEqual(a.invoke('begin', inner), 0)
            self.assertEqual(a.invoke('lookup', outer), row)
            self.assertEqual(a.record(row).capture_flags, 0x8C)
            self.assertEqual(a.invoke('end', inner), 0)
            self.assertEqual(a.invoke('end', outer), 1)
            self.assertEqual(a.invoke('lookup', outer), 0)
            self.assertEqual(a.invoke('begin', inner), row)
            self.assertEqual(a.record(row).contact_ordinal, 2)

    def test_same_hi_different_frame_is_rejected_until_certified_end(self):
        with OwnedBridge() as b:
            a=OwnedContactArena(b);hit=(ctypes.c_uint8*0x118)();frames=(ctypes.c_uint8*32)()
            first=ctypes.addressof(frames);second=first+16
            row=a.invoke('begin',hit,frame=first)
            self.assertEqual(a.invoke('begin',hit,frame=second),0)
            self.assertEqual(a.invoke('lookup',hit),row)
            self.assertEqual(a.invoke('end',hit,frame=second),0)
            self.assertEqual(a.invoke('end',hit,frame=first),1)
            self.assertEqual(a.invoke('begin',hit,frame=second),row)

    def test_two_live_threads_have_separate_owned_rows_and_no_cross_thread_lookup(self):
        with OwnedBridge() as b:
            a=OwnedContactArena(b); hits=[(ctypes.c_uint8*0x118)() for _ in range(2)]
            gate=threading.Barrier(2); results=[]
            def worker(i):
                row=a.invoke('begin',hits[i]); gate.wait()
                results.append((i,row,a.invoke('lookup',hits[1-i]),a.invoke('lookup',hits[i])))
            workers=[threading.Thread(target=worker,args=(i,)) for i in range(2)]
            for w in workers:w.start()
            for w in workers:w.join()
            self.assertEqual(len(results),2)
            self.assertNotEqual(results[0][1],results[1][1])
            self.assertTrue(all(row and foreign==0 and own==row for _,row,foreign,own in results))
            self.assertEqual(a.stats()['contact_counter'],2)

    def test_probe_bound_reports_drop_instead_of_scanning_more_slots(self):
        with OwnedBridge() as b:
            a=OwnedContactArena(b,capacity=16); hit=(ctypes.c_uint8*0x118)()
            tid=b.kernel.GetCurrentThreadId(); start=tid&15
            for i in range(8):
                ctypes.c_uint32.from_address(a.rows+((start+i)&15)*ROW_SIZE+OWNER).value=tid+1+i
            self.assertEqual(a.invoke('begin',hit),0)
            self.assertEqual(a.stats()['contact_counter'],0)
            self.assertEqual(a.stats()['rejected'],1)
            self.assertEqual(ctypes.c_uint32.from_address(a.rows+((start+8)&15)*ROW_SIZE+OWNER).value,0)

    def test_epoch_disable_and_quiescent_reset_have_explicit_lifecycle(self):
        with OwnedBridge() as b:
            a=OwnedContactArena(b); hit=(ctypes.c_uint8*0x118)()
            row=a.invoke('begin',hit); self.assertEqual(a.record(row).epoch,1)
            a.reset_after_owned_calls_return(enabled=False)
            self.assertEqual(a.invoke('begin',hit),0)
            b.epoch=2; a.reset_after_owned_calls_return()
            self.assertEqual(a.record(a.invoke('begin',hit)).epoch,2)

    def test_counter_refuses_u32_wrap(self):
        with OwnedBridge() as b:
            a=OwnedContactArena(b); hit=(ctypes.c_uint8*0x118)()
            ctypes.c_uint64.from_address(a.address+24).value=0xFFFFFFFF
            self.assertEqual(a.invoke('begin',hit),0)
            self.assertEqual(a.stats()['contact_counter'],0x100000000)
            self.assertEqual(a.invoke('lookup',hit),0)

    def test_lifecycle_guard_refuses_foreign_row_and_closed_memory(self):
        b=OwnedBridge(); a=OwnedContactArena(b); hit=(ctypes.c_uint8*0x118)()
        with self.assertRaises(ValueError):a.record(ctypes.addressof(hit))
        with self.assertRaises(ValueError):OwnedContactArena(b,capacity=256)
        b.close()
        for call in (lambda:a.invoke('begin',hit),a.stats,lambda:a.record(a.rows)):
            with self.assertRaises(ValueError):call()

    def test_pending_next_iteration_overflow_invalidates_previous_ap_proof(self):
        with OwnedBridge() as b:
            a=OwnedContactArena(b);hit=(ctypes.c_uint8*0x118)()
            row=a.invoke('begin',hit);a.record(row).capture_flags=0x1FF
            ctypes.c_uint32.from_address(row+PHASE).value=2
            ctypes.c_uint64.from_address(a.address+24).value=0xFFFFFFFF
            self.assertEqual(a.invoke('begin',hit),0)
            self.assertEqual(a.invoke('lookup',hit),0)
            self.assertEqual(a.record(row).capture_flags,0)

    def test_returned_native_row_drives_actual_ap_final_qualifier_fifo(self):
        with OwnedBridge() as b:
            a=OwnedContactArena(b); resolver=OwnedEntityResolver(b)
            resolver.insert(1001,resolver.enemies[0],0); resolver.insert(1002,resolver.sources[0],1)
            hit=(ctypes.c_uint8*0x118)(); calc=(ctypes.c_uint8*0x24)(); final=(ctypes.c_uint8*0x24)()
            projectile=(ctypes.c_uint8*0x100)(); calls=ctypes.c_uint64()
            ctypes.c_uint64.from_buffer(hit,0x110).value=b.local_peer
            ctypes.c_uint32.from_buffer(hit,0x20).value=1001; ctypes.c_uint32.from_buffer(hit,0x80).value=1002
            ctypes.c_float.from_buffer(hit,0x50).value=4
            row=a.invoke('begin',hit); record=a.record(row)
            gettid=int(ctypes.cast(b.kernel.GetCurrentThreadId,ctypes.c_void_p).value)
            stage=b._procedure(ap_stage_code(row,gettid,certified_contact_profile=True),None,unwind=NORMAL_UNWIND)
            caller=b._procedure(ap_call_fixture_code(int(ctypes.cast(stage,ctypes.c_void_p).value)),None,
                ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,
                unwind=bytes.fromhex('01170900 17a80400 11980300 0b680200 06a2 0270 0130 0000'))
            curve=b._procedure(curve_marker_code(gettid),ctypes.c_uint32,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint32,
                unwind=bytes.fromhex('01070400 0732 0370 0260 0130'))
            original=b._procedure(bytes.fromhex('48 ff 01 c3'),ctypes.c_uint64,
                ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint64,ctypes.c_uint64,ctypes.c_void_p)
            wrapper=b.owned_normal_wrapper(record,original,extra_arg_types=(ctypes.c_uint64,ctypes.c_void_p),
                context_guard=True,projectile_info_from_entry_rax=True,certified_contact_profile=True,
                qualifier=resolver._qualify,entity_manager=resolver.manager)
            site=OwnedE8Callsite(b,original,projectile_info_from_sixth_arg=True);site.install(wrapper)
            floats=(ctypes.c_float*3)(5,4,1)
            self.assertEqual(curve(row,ctypes.addressof(hit),0),1)
            caller(None,ctypes.addressof(hit),ctypes.addressof(calc),ctypes.addressof(floats))
            ctypes.memmove(final,calc,0x24)
            for _ in range(2):site.invoke(ctypes.addressof(calls),ctypes.addressof(final),ctypes.addressof(hit),0,0,ctypes.addressof(projectile))
            out=b.drain(); self.assertEqual(len(out),1)
            self.assertEqual((out[0].capture_flags,out[0].ap_delta,out[0].source,out[0].creditor),(0x1FF,1,1002,b.local_peer))
            self.assertEqual(calls.value,2);self.assertEqual(a.invoke('lookup',hit),0)

    def test_native_unwind_body_and_each_epilog_pc(self):
        with OwnedBridge() as b:
            a=OwnedContactArena(b); helper=earlier_context_tests.OwnedAPFinalTests()
            for procedure in a._calls.values():
                address=int(ctypes.cast(procedure,ctypes.c_void_p).value);size=len(b._procedures[address]['code'])
                helper.assert_unwind(b,procedure,pc=3,pushes=('rbx','rsi','rdi'),frame=0)
                for pc,popped in [(size-4,()),(size-3,('rdi',)),(size-2,('rdi','rsi')),(size-1,('rdi','rsi','rbx'))]:
                    helper.assert_unwind(b,procedure,pc=pc,pushes=('rbx','rsi','rdi'),frame=0,popped=popped)


if __name__=='__main__':unittest.main(verbosity=2)
