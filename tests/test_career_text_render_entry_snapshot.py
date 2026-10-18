"""Sparse owned memory only: no process access, calls or account writes."""
import importlib.util
from pathlib import Path
import struct
import unittest

ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
t=load('career_text_entry',ROOT/'tools/career-text-render-entry-snapshot.py')
f=load('career_text_entry_memory',ROOT/'tests/test_career_ui_snapshot.py')

class Memory(f.Memory):
    def __init__(self):
        super().__init__();self.identity={**self.identity,'exe_base':0x400000000,'exe_size':0x39E8000}
        self.api,self.table,self.engine_gui=0x303000000,0x303001000,0x303002000
        self.entry=self.identity['exe_base']+0x20000;self.entry_protect=0x20
        self.put(self.gui+8,struct.pack('<Q',self.engine_gui))
        self.put(self.identity['game_base']+t.API_GLOBAL,struct.pack('<Q',self.api))
        self.put(self.api+0xD0,struct.pack('<Q',self.table));self.put(self.table+0x1B0,struct.pack('<Q',self.entry))
        self.put(self.entry,b'\x90'*512)
        for at,pin in t.PINS:self.put(self.identity['game_base']+at,bytes.fromhex(pin))
        owner={'controller':self.controller,'gui_context':self.gui,'list':self.list,'panel':self.controller+t.layout.CAREER_PANEL,
               'state_context':self.state_context,'dispatch':self.dispatch}
        self.source={'status':'complete','headers_stable':True,'identity':f.Memory.identity,'owner_before':owner}
    def query(self,address):
        if self.identity['exe_base']<=address<self.identity['exe_base']+self.identity['exe_size']:
            self.queries.append(address)
            return {'base':self.identity['exe_base'],'size':self.identity['exe_size'],'state':0x1000,
                    'protect':self.entry_protect,'type':0x1000000}
        return super().query(address)

class Tests(unittest.TestCase):
    def capture(self,m):return t.capture(m,m.identity,m.source,clock=lambda:0)
    def test_exact_one_entry_module_rva_and_stable_chain(self):
        m=Memory();r=self.capture(m)
        self.assertEqual((r['entry']['module'],r['entry']['rva'],r['entry']['length']),('exe',0x20000,512))
        self.assertEqual(m.reads.count((m.entry,512)),1)
        self.assertEqual(m.reads.count((m.table+0x1B0,8)),2)
        self.assertNotIn((m.engine_gui,256),m.reads)
        self.assertLessEqual(r['active_read_bytes'],t.MAX_BYTES);self.assertLessEqual(r['active_read_calls'],t.MAX_READS)
        self.assertFalse(r['native_called']);self.assertFalse(r['account_modified'])
    def test_changed_chain_after_copy_rejects(self):
        m=Memory()
        def changed(mem,at,size):
            if at==mem.entry:mem.put(mem.table+0x1B0,struct.pack('<Q',mem.entry+16))
        m.changed=changed
        with self.assertRaisesRegex(ValueError,'CHAIN_CHANGED'):self.capture(m)
    def test_closed_or_foreign_page_cannot_follow_api(self):
        for foreign in (False,True):
            m=Memory()
            if foreign:m.source['owner_before']['gui_context']+=8
            else:m.alphas=[0]
            with self.subTest(foreign=foreign),self.assertRaises((ValueError,t.parent.NotVisible)):self.capture(m)
            self.assertNotIn((m.api+0xD0,8),m.reads)
    def test_bad_caller_pin_stops_before_api(self):
        m=Memory();m.put(m.identity['game_base']+t.PINS[0][0],b'\x90')
        with self.assertRaisesRegex(ValueError,'CALLER_PIN'):self.capture(m)
        self.assertNotIn((m.gui+8,8),m.reads)
    def test_non_executable_and_outside_image_refused(self):
        m=Memory();m.entry_protect=4
        with self.assertRaisesRegex(ValueError,'UNREADABLE'):self.capture(m)
        self.assertNotIn((m.entry,512),m.reads)
        m=Memory();m.put(m.table+0x1B0,struct.pack('<Q',m.engine_gui))
        with self.assertRaisesRegex(ValueError,'OUTSIDE_IMAGES'):self.capture(m)
        self.assertNotIn((m.engine_gui,512),m.reads)
    def test_only_observed_submit_call_and_512_bytes(self):
        m=Memory();m.entry=m.identity['exe_base']+0x340C30
        m.put(m.table+0x1B0,struct.pack('<Q',m.entry));m.put(m.entry,b'\x90'*512)
        m.put(m.identity['exe_base']+0x340DB4,bytes.fromhex('e87764f2ff'))
        prior=self.capture(m);m.reads=[]
        next_at=m.identity['exe_base']+0x267230;m.put(next_at,b'\x90'*512)
        r=t.capture(m,m.identity,m.source,clock=lambda:0,submit_source=prior)
        self.assertEqual((r['stage'],r['entry']['rva']),('gui_text_submit',0x267230))
        self.assertNotIn((m.entry,512),m.reads);self.assertEqual(m.reads.count((next_at,512)),1)
        third=m.identity['exe_base']+0x26D310;m.put(third,b'\x90'*512)
        m.put(m.identity['exe_base']+0x26726B,bytes.fromhex('e8a0600000'));m.reads=[]
        prepare=t.capture(m,m.identity,m.source,clock=lambda:0,prepare_source=r)
        self.assertEqual((prepare['stage'],prepare['entry']['rva']),('gui_text_prepare',0x26D310))
        self.assertNotIn((next_at,512),m.reads);self.assertEqual(m.reads.count((third,512)),1)
        matrix_at=m.identity['exe_base']+0x25F5F0;m.put(matrix_at,b'\x90'*512)
        m.put(m.identity['exe_base']+0x341ED0,bytes.fromhex('f30f105918f30f105114e911d7f1ff'));m.reads=[]
        move=t.capture(m,m.identity,m.source,clock=lambda:0,move_source=prepare)
        self.assertEqual((move['stage'],move['entry']['rva']),('gui_move_matrix',0x25F5F0))
        self.assertNotIn((third,512),m.reads);self.assertEqual(m.reads.count((matrix_at,512)),1)
        m.put(m.identity['exe_base']+0x340DB4,b'\x90');m.reads=[]
        with self.assertRaisesRegex(ValueError,'SUBMIT_CALL_PIN'):
            t.capture(m,m.identity,m.source,clock=lambda:0,submit_source=prior)
        self.assertNotIn((next_at,512),m.reads)

if __name__=='__main__':unittest.main()
