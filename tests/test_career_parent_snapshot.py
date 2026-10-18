"""Owned widget headers only: no live process or UI operations."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result
target = load('career_parent_test', ROOT / 'tools/career-parent-snapshot.py')
prior = load('career_parent_owned_memory', ROOT / 'tests/test_career_ui_snapshot.py')


class Memory(prior.Memory):
    def __init__(self, siblings=2):
        super().__init__(nodes=1)
        self.ancestors = [self.controller + target.PARENT_OFFSET, self.controller + 0x48000,
                          self.controller + 0x44000]
        a,b,c = self.ancestors
        self.widget(self.list, a, child=self.first_node)
        self.widget(a, b, child=self.list)
        self.widget(b, c, child=a, sibling=self.controller + 0x43000 if siblings else 0)
        self.widget(c, 0, child=b)
        self.adjacent = [self.controller + 0x43000 - i*0x200 for i in range(siblings)]
        for i,address in enumerate(self.adjacent):
            self.widget(address, c, sibling=self.adjacent[i+1] if i+1<siblings else 0,
                        child=0x303000000)  # An unread, deliberately unowned subtree.
        for address in [self.list,*self.ancestors,*self.adjacent]:
            self.put(address+0x24, struct.pack('<ff', 500, 600))
            self.put(address+0x64, struct.pack('<f', 1))
            self.put(address+0x8C, struct.pack('<f', 1))


class Tests(unittest.TestCase):
    def capture(self, memory):return target.capture(memory,memory.identity,clock=lambda:0)

    def test_three_parents_adjacent_headers_no_stat_rows_or_child_subtree(self):
        memory=Memory();result=self.capture(memory)
        self.assertEqual(result['ancestors'],memory.ancestors)
        self.assertEqual(len(result['nodes']),6)
        self.assertTrue(result['headers_stable'])
        self.assertFalse(result['native_parent_mount_verified'])
        self.assertFalse(result['personal_account_verified'])
        self.assertEqual(result['active_read_calls'],28)
        self.assertLess(result['active_read_bytes'],4000)
        for address in [memory.list,*memory.ancestors,*memory.adjacent]:
            self.assertEqual(memory.reads.count((address,256)),2)
        self.assertNotIn((memory.first_node,256),memory.reads)
        self.assertNotIn((0x303000000,256),memory.reads)
        self.assertTrue(all(size<=256 for _,size in memory.reads))

    def test_large_sibling_list_truncates_at_fixed_limit_before_unknown_read(self):
        memory=Memory(siblings=20);result=self.capture(memory)
        self.assertEqual(len(result['nodes']),16)
        self.assertEqual(result['adjacent_count'],12)
        self.assertTrue(result['chains'][-1]['truncated'])
        self.assertEqual(result['chains'][-1]['next_unread'],memory.adjacent[12])
        self.assertNotIn((memory.adjacent[12],256),memory.reads)
        self.assertLessEqual(result['active_read_calls'],64)
        self.assertLessEqual(result['active_read_bytes'],16384)

    def test_closed_page_has_no_node_or_code_reads(self):
        memory=Memory();memory.alphas=[0]
        with self.assertRaises(target.NotVisible):self.capture(memory)
        self.assertFalse(any(address in memory.ancestors for address,_ in memory.reads))

    def test_unknown_list_parent_stops_before_following_it(self):
        memory=Memory();memory.put(memory.list+240,struct.pack('<Q',0x304000000))
        with self.assertRaisesRegex(ValueError,'KNOWN_LIST_PARENT'):self.capture(memory)
        self.assertNotIn((0x304000000,256),memory.reads)

    def test_cycles_context_parent_guard_and_geometry_fail(self):
        for failure in ('cycle','context','parent','guard','nan'):
            memory=Memory();address=memory.adjacent[0]
            if failure=='cycle':memory.put(address+232,struct.pack('<Q',address))
            if failure=='context':memory.put(address+248,struct.pack('<Q',memory.gui+8))
            if failure=='parent':memory.put(address+240,struct.pack('<Q',memory.ancestors[0]))
            if failure=='guard':memory.guard=address
            if failure=='nan':memory.put(address+0x24,struct.pack('<f',float('nan')))
            with self.subTest(failure=failure),self.assertRaises(ValueError):self.capture(memory)

    def test_second_header_change_or_page_close_rejected(self):
        for change in ('geometry','page'):
            memory=Memory();address=memory.ancestors[1];reads=[0]
            def mutate(memory,at,size):
                if at==address:
                    reads[0]+=1
                    if reads[0]==2:memory.put(address+0x24,struct.pack('<f',600))
            if change=='geometry':memory.changed=mutate
            else:memory.alphas=[1,0]
            with self.subTest(change=change),self.assertRaisesRegex(ValueError,'HEADER_CHANGED|PAGE_CLOSED'):
                self.capture(memory)

    def test_limits_stop_before_query(self):
        for field,value in (('reads',64),('bytes',16384),('queries',64)):
            memory=Memory();budget=target.Budget(memory,memory.identity,clock=lambda:0)
            if field=='queries':budget.queries=value
            else:budget.total[field]=value
            with self.assertRaisesRegex(ValueError,'BUDGET'):budget.ptr(memory.list)
            self.assertEqual(memory.queries,[]);self.assertEqual(memory.reads,[])

    def test_run_one_attempt_failure_never_waits(self):
        memory=Memory();memory.alphas=[0]
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)/'new'
            with self.assertRaises(target.NotVisible):target.run(folder,deps=prior.deps(memory),clock=lambda:0)
            self.assertEqual(json.loads((folder/'status.json').read_text('utf8'))['status'],'not_visible')
            self.assertEqual(memory.entered,1)

    def test_run_success_records_readonly_state(self):
        memory=Memory()
        with tempfile.TemporaryDirectory() as temporary:
            result=target.run(Path(temporary)/'new',deps=prior.deps(memory),clock=lambda:0)
            self.assertEqual(result['status'],'complete')
            self.assertEqual(memory.entered,1)
            for field in ('native_called','native_written','account_modified'):
                self.assertFalse(result[field])


if __name__=='__main__':unittest.main()
