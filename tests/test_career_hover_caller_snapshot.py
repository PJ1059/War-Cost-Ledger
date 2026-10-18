"""Owned sparse memory fixtures; never open Game or invoke native code."""
import importlib.util
from pathlib import Path
import struct
import unittest

ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
t=load('hover_caller',ROOT/'tools/career-hover-caller-snapshot.py')
f=load('hover_memory',ROOT/'tests/test_career_ui_snapshot.py')

class Memory(f.Memory):
    def __init__(self):
        super().__init__(nodes=0)
        self.target=self.identity['game_base']+t.TARGET_RVA
        self.put(self.target,b'\x90'*t.CODE_BYTES)
        self.put(self.identity['game_base']+t.CONTAINS_RVA,t.CONTAINS_PIN)
        owner,_=t.layout.locate(t.Budget(self,self.identity,clock=lambda:0))
        self.source={'status':'complete','headers_stable':True,'identity':dict(self.identity),'owner_before':owner}
        self.reads=[];self.queries=[]

class Tests(unittest.TestCase):
    def capture(self,m):return t.capture(m,m.identity,m.source,clock=lambda:0)
    def test_fixed_1k_plus_16byte_identity_only(self):
        m=Memory();r=self.capture(m)
        self.assertEqual((r['entry']['rva'],r['entry']['length']),(0x18D0690,1024))
        self.assertEqual([n for at,n in m.reads if at==m.target],[1024,16])
        self.assertEqual(r['active_read_bytes'],1697)
        self.assertEqual(r['active_read_calls'],21)
        self.assertLessEqual(r['active_query_calls'],t.MAX_QUERIES)
        self.assertFalse(r['native_called']);self.assertFalse(r['career_coordinate_applicability_proven'])
    def test_hidden_foreign_page_and_bad_pin_stop_before_target(self):
        for mode in ('hidden','foreign','pin'):
            m=Memory()
            if mode=='hidden':m.alphas=[0]
            if mode=='foreign':m.source['owner_before']['gui_context']+=8
            if mode=='pin':m.put(m.identity['game_base']+t.CONTAINS_RVA,b'\x90')
            with self.subTest(mode=mode),self.assertRaises((ValueError,t.parent.NotVisible)):self.capture(m)
            self.assertNotIn((m.target,1024),m.reads)
    def test_page_or_code_change_after_capture_rejected(self):
        for mode in ('code','page'):
            m=Memory()
            def changed(mem,at,size):
                if at==mem.target and size==16:
                    if mode=='code':mem.put(mem.target,b'\xcc')
                    else:mem.alphas=[0]
            m.changed=changed
            with self.subTest(mode=mode),self.assertRaisesRegex(ValueError,'CHANGED'):self.capture(m)
    def test_non_executable_and_time_budget_stop(self):
        m=Memory();m.guard=m.target
        with self.assertRaisesRegex(ValueError,'UNREADABLE'):self.capture(m)
        self.assertNotIn((m.target,1024),m.reads)
        m=Memory();times=iter([0,1.1])
        with self.assertRaisesRegex(ValueError,'TIME_BUDGET'):t.capture(m,m.identity,m.source,clock=lambda:next(times))
        self.assertEqual(m.reads,[])
    def test_adapter_only_follows_exact_proven_call_144_bytes(self):
        m=Memory();call=b'\xe8'+struct.pack('<i',t.ADAPTER_RVA-t.ADAPTER_CALL-5)
        m.put(m.identity['game_base']+t.ADAPTER_CALL,call);prior=self.capture(m)
        at=m.identity['game_base']+t.ADAPTER_RVA;m.put(at,b'\x90'*t.ADAPTER_BYTES);m.reads=[]
        r=t.capture(m,m.identity,m.source,clock=lambda:0,adapter_source=prior)
        self.assertEqual((r['entry']['rva'],r['entry']['length']),(t.ADAPTER_RVA,144))
        self.assertEqual([n for addr,n in m.reads if addr==at],[144,16])
        self.assertEqual(r['active_read_bytes'],822);self.assertEqual(r['active_read_calls'],22)
        self.assertNotIn((m.target,1024),m.reads)
        m.put(m.identity['game_base']+t.ADAPTER_CALL,b'\x90');m.reads=[]
        with self.assertRaisesRegex(ValueError,'ADAPTER_CALL_CHANGED'):
            t.capture(m,m.identity,m.source,clock=lambda:0,adapter_source=prior)
        self.assertNotIn((at,144),m.reads)

if __name__=='__main__':unittest.main()
