"""Only new finite exit metadata fixtures; no Game or old suite execution."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import test_hit_contact_consume_tail_capture as fixture

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('owned_contact_exit_metadata',ROOT/'tools/hit-contact-exit-metadata-capture.py')
capture=importlib.util.module_from_spec(spec);spec.loader.exec_module(capture)
OLD_LIMITS=(fixture.capture.v1.MAX_READS,fixture.capture.v1.frozen.MAX_READS)


class Memory(fixture.Memory):
    def __init__(self,state=2,depth=1,change=None,missing=False):
        super().__init__(state=state)
        self.change=change;self.window_reads=0
        record=[capture.parent.DECLARATION,(0x13AFCD1,0x13AFD17,0x2512000),
                struct.unpack('<III',bytes.fromhex(capture.ANCHORS[68133])),
                (0x13B02CF,0x13B0400,0x2512100),(0x13B0400,0x13B0520,0x2512200),
                (0x13B0520,0x13B053F if missing else 0x13B0580,0x2512300),
                struct.unpack('<III',bytes.fromhex(capture.ANCHORS[68137]))]
        self.table=b''.join(struct.pack('<III',*r) for r in record)
        self.allowed[(capture.WINDOW_RVA,84)]=self.table
        primary=tuple(capture.parent.unwind_source()[-1][k] for k in ('begin','end','unwind_rva'))
        for target_index,r in enumerate((record[1],record[5])):
            nodes=[r]+[(0x13B0300+j*4,0x13B0304+j*4,0x2513000+target_index*0x100+j*0x20)
                       for j in range(depth-1)]
            for node,next_node in zip(nodes,nodes[1:]+[primary]):
                self.allowed[(node[2],4)]=bytes((0x21,0,0,0))
                self.allowed[(node[2]+4,12)]=struct.pack('<III',*next_node)
        self.metadata_keys={(rva,size) for rva,size in self.allowed if 0x2512000<=rva<0x2514000}

    def read(self,address,size):
        rva=address-self.game
        if rva==capture.parent.TAIL_BEGIN:
            assert size==128;self.reads.append((address,size));self.custom_reads.append((rva,size))
            if self.clock:self.clock.value+=self.delay
            self.tail_reads+=1
            raw=capture.TAIL_PIN
            return bytes((raw[0]^1,))+raw[1:] if self.change=='source_after' and self.tail_reads==2 else raw
        if (rva,size)==(capture.WINDOW_RVA,84):
            self.reads.append((address,size));self.custom_reads.append((rva,size))
            if self.clock:self.clock.value+=self.delay
            self.window_reads+=1;raw=self.table
            if self.change=='first_record' or self.change=='window_after' and self.window_reads==2:
                raw=bytes((raw[0]^1,))+raw[1:]
            # Change the anchor UW while retaining order and DWORD alignment.
            if self.change=='saved_anchor':raw=raw[:33]+bytes((raw[33]^1,))+raw[34:]
            return raw
        return super().read(address,size)


class Scenario(fixture.previous.fixture.Scenario):
    def __init__(self,**options):super().__init__();self.memory=Memory(**options)


class ExitMetadataTests(unittest.TestCase):
    def test_finite_normal_and_maximum_two_chains_cache_to_fresh_primary(self):
        for state,depth in ((2,1),(3,4)):
            with self.subTest(state=state,depth=depth),tempfile.TemporaryDirectory() as temp:
                scenario=Scenario(state=state,depth=depth)
                status=capture.run(Path(temp)/'capture',scenario.dependencies(),fixture.previous.fixture.Clock())
                meta=json.loads(Path(status['json_path']).read_text('utf8'))
                self.assertEqual(Path(status['binary_path']).read_bytes(),scenario.memory.table)
                self.assertEqual(meta['ranges'],[{'name':'contact_hot_and_next6_exception_records','module':'game',
                                                'rva':0x409ADB0,'length':84,'binary_offset':0}])
                self.assertEqual(meta['ship_before'],meta['ship_after'])
                self.assertEqual(scenario.memory.window_reads,2)
                self.assertEqual(meta['budget']['read_calls'],23+4*depth)
                self.assertEqual(meta['budget']['query_calls'],23+4*depth)
                self.assertEqual(meta['budget']['bytes_requested'],9224+32*depth)
                self.assertEqual(meta['budget']['read_calls'],len(scenario.memory.reads))
                self.assertEqual(meta['budget']['query_calls'],len(scenario.memory.queries))
                self.assertEqual(meta['budget']['max_reads'],48)
                self.assertEqual(meta['budget']['max_bytes'],24576)
                self.assertTrue(meta['metadata_only']);self.assertEqual(meta['new_code_body_reads'],0)
                self.assertEqual([o['unknown_node_count'] for o in meta['ownership']],[depth,depth])
                self.assertTrue(all(o['same_contact_primary'] for o in meta['ownership']))
                for key in ('normal_CFG_closed','logical_function_complete','count_clear_or_consume_timing_proven',
                            'runtime_object_lifetime_proven','classification_ready','contract_ready','native_called','native_written'):
                    self.assertFalse(meta[key])
                self.assertTrue(scenario.memory.closed)
                self.assertEqual((fixture.capture.v1.MAX_READS,fixture.capture.v1.frozen.MAX_READS),OLD_LIMITS)
                print('OWNED_BUDGET '+json.dumps({'state':state,'unknown_nodes_per_target':depth,'budget':meta['budget']}))

    def test_fixed_scope_first_record_anchors_unknown_limit_and_resource_withhold(self):
        for name,opts,reason,cap in (
                ('first_record',{'change':'first_record'},'FRESH_FIRST_RECORD_CHANGED',None),
                ('saved_anchor',{'change':'saved_anchor'},'FRESH_SAVED_RECORD_ANCHOR_CHANGED',None),
                ('missing_target',{'missing':True},'TARGET_NOT_IN_FIXED_WINDOW',None),
                ('depth5',{'depth':5},'UNKNOWN_UW_NODE_LIMIT',None),
                ('capacity26',{},'READ_BUDGET',26)):
            with self.subTest(case=name),tempfile.TemporaryDirectory() as temp:
                scenario=Scenario(**opts);folder=Path(temp)/'capture'
                with patch.object(capture,'MAX_READS',cap or 48):
                    with self.assertRaisesRegex(ValueError,reason):
                        capture.run(folder,scenario.dependencies(),fixture.previous.fixture.Clock())
                self.assertEqual(list(folder.glob('*.bin')),[])
                meta=json.loads((folder/'callsite.incomplete.json').read_text('utf8'))
                self.assertFalse(meta['complete']);self.assertFalse(meta['partial_binary_saved'])
                self.assertLessEqual(meta['budget']['read_calls'],cap or 48)
                self.assertLessEqual(meta['budget']['bytes_requested'],24576)
                self.assertTrue(scenario.memory.closed)
                windows=[(rva,size) for rva,size in scenario.memory.custom_reads if rva==capture.WINDOW_RVA]
                self.assertEqual(windows,[(capture.WINDOW_RVA,84)])
                self.assertEqual(meta['new_code_body_reads'],0)

    def test_post_window_or_source_change_does_not_save_metadata(self):
        for change in ('window_after','source_after'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as temp:
                scenario=Scenario(change=change);folder=Path(temp)/'capture'
                with self.assertRaisesRegex(ValueError,'WINDOW_OR_SOURCE_CHANGED'):
                    capture.run(folder,scenario.dependencies(),fixture.previous.fixture.Clock())
                self.assertEqual(list(folder.glob('*.bin')),[])
                self.assertEqual(scenario.memory.window_reads,2)
                self.assertTrue(scenario.memory.closed)


if __name__=='__main__':unittest.main()
