"""One owned group for only the new known20/opaque4 fixed read profile."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import test_hit_contact_consume_tail_capture as fixture

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('owned_contact_primary_prefix',
    ROOT/'tools/hit-contact-primary-handler-prefix-capture.py')
capture=importlib.util.module_from_spec(spec);spec.loader.exec_module(capture)
OLD_LIMITS=(fixture.capture.v1.frozen.MAX_BYTES,fixture.capture.v1.frozen.MAX_READS,
            fixture.capture.v1.frozen.MAX_SECONDS)


class Memory(fixture.Memory):
    def __init__(self,change=None):
        super().__init__(state=3);self.change=change;self.prefix_reads=0
        self.prefix=capture.KNOWN+b'\x38\0\0\0'

    def read(self,address,size):
        rva=address-self.game
        if (rva,size)==(capture.BEGIN,24):
            self.reads.append((address,size));self.custom_reads.append((rva,size))
            if self.clock:self.clock.value+=self.delay
            self.prefix_reads+=1
            if self.change=='known20':return bytes((self.prefix[0]^1,))+self.prefix[1:]
            if self.change=='opaque4_after' and self.prefix_reads==2:
                return self.prefix[:20]+bytes((self.prefix[20]^1,))+self.prefix[21:]
            return self.prefix
        return super().read(address,size)


class Scenario(fixture.previous.fixture.Scenario):
    def __init__(self,change=None):super().__init__();self.memory=Memory(change)


class PrimaryPrefixTests(unittest.TestCase):
    def test_success_or_prefix_changes_keep_scope_and_withhold(self):
        self.assertEqual(capture.validate_source()['primary_known20_source']['hex'],capture.KNOWN_HEX)
        for name,change,reason in (('success',None,None),
                ('known20_change','known20','FRESH_KNOWN20_CHANGED'),
                ('opaque4_change','opaque4_after','OPAQUE4_CHANGED_DURING_CAPTURE')):
            with self.subTest(case=name),tempfile.TemporaryDirectory() as temp:
                scenario=Scenario(change);folder=Path(temp)/'capture';clock=fixture.previous.fixture.Clock()
                if reason:
                    with self.assertRaisesRegex(ValueError,reason):
                        capture.run(folder,scenario.dependencies(),clock)
                    self.assertEqual(list(folder.glob('*.bin')),[])
                    meta=json.loads((folder/'callsite.incomplete.json').read_text('utf8'))
                    self.assertFalse(meta['complete']);self.assertFalse(meta['partial_binary_saved'])
                else:
                    result=capture.run(folder,scenario.dependencies(),clock)
                    meta=json.loads(Path(result['json_path']).read_text('utf8'))
                    self.assertEqual(Path(result['binary_path']).read_bytes(),scenario.memory.prefix)
                    self.assertEqual(meta['ranges'],[{'name':'contact_primary_known20_opaque4_prefix',
                        'module':'game','rva':capture.BEGIN,'length':24,'binary_offset':0}])
                    self.assertTrue(meta['known20_before_after_match'])
                    self.assertTrue(meta['primary_prefix_before_after_match'])
                    self.assertEqual(meta['opaque4_hex'],'38000000')
                    self.assertEqual(meta['budget']['read_calls'],30)
                    self.assertEqual(meta['budget']['query_calls'],30)
                    self.assertEqual(meta['budget']['bytes_requested'],8924)
                    self.assertEqual(meta['ship_before'],meta['ship_after'])
                    self.assertTrue(meta['fresh_gates_verified'])
                windows=[(rva,size) for rva,size in scenario.memory.custom_reads if size==24]
                self.assertEqual(windows,[(capture.BEGIN,24)]*(1 if change=='known20' else 2))
                self.assertEqual(scenario.memory.tail_reads,0)
                self.assertEqual(meta['budget']['read_calls'],len(scenario.memory.reads))
                self.assertEqual(meta['budget']['query_calls'],len(scenario.memory.queries))
                self.assertEqual(meta['budget']['bytes_requested'],sum(size for _,size in scenario.memory.reads))
                self.assertEqual(meta['budget']['max_reads'],32)
                self.assertEqual(meta['budget']['max_bytes'],24576)
                self.assertTrue(meta['raw_only']);self.assertTrue(meta['metadata_only'])
                self.assertEqual(meta['new_opaque_bytes'],4);self.assertEqual(meta['new_unknown_code_bytes'],0)
                for key in ('handler_body_read','complete_handler_data','handler_data_format_proven',
                            'structured_scope_table_decoded','native_called','native_written','classification_ready',
                            'contract_ready'):
                    self.assertFalse(meta[key])
                self.assertEqual(meta['heap_reads'],0);self.assertEqual(meta['extra_callee_reads'],0)
                self.assertTrue(scenario.memory.closed)
                self.assertEqual((fixture.capture.v1.frozen.MAX_BYTES,fixture.capture.v1.frozen.MAX_READS,
                                  fixture.capture.v1.frozen.MAX_SECONDS),OLD_LIMITS)
                print('OWNED_BUDGET '+json.dumps({'case':name,'Game_accessed':False,'old_suites_run':False,
                    'prefix_reads':scenario.memory.prefix_reads,'binary_saved':not bool(reason),'budget':meta['budget']}))


if __name__=='__main__':unittest.main()
