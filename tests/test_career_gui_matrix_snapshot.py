import importlib.util
from pathlib import Path
import struct
import unittest
ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
t=load('gui_pose',ROOT/'tools/career-gui-matrix-snapshot.py')
fixture=load('gui_pose_memory',ROOT/'tests/test_career_text_render_entry_snapshot.py')
def memory():
    m=fixture.Memory();matrix=[1,0,0,0,0,1,0,0,0,0,.85,0,0,0,0,1];raw=bytearray(128)
    struct.pack_into('<ff',raw,4,1436,792);struct.pack_into('<16f',raw,0x18,*matrix)
    m.put(m.engine_gui+16,raw);m.put(m.identity['exe_base']+t.SETTER,bytes.fromhex(t.PREFIX))
    source={'status':'complete','stage':'gui_move_matrix','entry':{'module':'exe','rva':t.SETTER,'hex':t.PREFIX},
        'identity':m.identity,'owner_before':m.source['owner_before'],'pointers':{'engine_gui':m.engine_gui}}
    return m,source
class Tests(unittest.TestCase):
    def test_exact_stable_fields(self):
        m,s=memory();r=t.capture(m,m.identity,s,clock=lambda:0)
        self.assertEqual(r['dimensions'],[1436,792]);self.assertAlmostEqual(r['pose_matrix'][10],.85)
        self.assertEqual(m.reads.count((m.engine_gui+16,128)),2);self.assertFalse(r['native_called'])
    def test_changed_matrix_refuses(self):
        m,s=memory()
        def mutate(mem,at,size):
            if at==mem.engine_gui+16 and mem.reads.count((at,size))==2:mem.put(at+24,struct.pack('<f',2))
        m.changed=mutate
        with self.assertRaisesRegex(ValueError,'POSE_CHANGED'):t.capture(m,m.identity,s,clock=lambda:0)
    def test_changed_gui_or_hidden_page_stops(self):
        for hidden in (True,False):
            m,s=memory()
            if hidden:m.alphas=[0]
            else:m.put(m.gui+8,struct.pack('<Q',m.engine_gui+8))
            with self.subTest(hidden=hidden),self.assertRaises((ValueError,t.entry.parent.NotVisible)):
                t.capture(m,m.identity,s,clock=lambda:0)
            self.assertNotIn((m.engine_gui+16,128),m.reads)
if __name__=='__main__':unittest.main()
