"""One new owned group: fixed envelope success/body-change/metadata-change."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import test_hit_contact_exit_metadata_capture as fixture

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('owned_contact_whole_envelope',
    ROOT/'tools/hit-contact-whole-envelope-capture.py')
capture=importlib.util.module_from_spec(spec);spec.loader.exec_module(capture)
OLD_LIMITS=(fixture.capture.v1.frozen.MAX_BYTES,fixture.capture.v1.frozen.MAX_READS,
            fixture.capture.v1.frozen.MAX_CODE_BYTES)


class Memory(fixture.Memory):
    def __init__(self,change=None):
        super().__init__(state=3,change=change)
        self.table=capture.METADATA_PIN
        self.allowed[(capture.metadata_private.WINDOW_RVA,84)]=self.table
        meta=capture.validate_metadata_packet()
        for chain in [meta['unwind_chain']]+[row['unwind_chain'] for row in meta['ownership']]:
            for node in chain:
                for key in ('header','chain_entry'):
                    if key in node:
                        raw=bytes.fromhex(node[key]['raw_hex'])
                        self.allowed[(node[key]['rva'],len(raw))]=raw
        body=bytearray(b'\x90'*capture.BODY_BYTES)
        for _,rva,raw in capture.fragments():
            body[rva-capture.BODY_BEGIN:rva-capture.BODY_BEGIN+len(raw)]=raw
        self.body=bytes(body);self.body_reads=0

    def read(self,address,size):
        rva=address-self.game
        if (rva,size)==(capture.BODY_BEGIN,capture.BODY_BYTES):
            self.reads.append((address,size));self.custom_reads.append((rva,size))
            if self.clock:self.clock.value+=self.delay
            self.body_reads+=1
            if self.change=='body_after' and self.body_reads==2:
                return self.body[:-1]+bytes((self.body[-1]^1,))
            return self.body
        return super().read(address,size)


class Scenario(fixture.fixture.previous.fixture.Scenario):
    def __init__(self,change=None):super().__init__();self.memory=Memory(change)


class WholeEnvelopeTests(unittest.TestCase):
    def test_exact_body_and_changes_withhold_without_old_suite_or_game(self):
        for name,change,reason in (('success',None,None),
                ('body_change','body_after','BODY_CHANGED_DURING_CAPTURE'),
                ('metadata_change','window_after','FRESH_FULL_METADATA_CHANGED')):
            with self.subTest(case=name),tempfile.TemporaryDirectory() as temp:
                scenario=Scenario(change);folder=Path(temp)/'capture'
                clock=fixture.fixture.previous.fixture.Clock()
                if reason:
                    with self.assertRaisesRegex(ValueError,reason):
                        capture.run(folder,scenario.dependencies(),clock)
                    self.assertEqual(list(folder.glob('*.bin')),[])
                    meta=json.loads((folder/'callsite.incomplete.json').read_text('utf8'))
                    self.assertFalse(meta['complete']);self.assertFalse(meta['partial_binary_saved'])
                else:
                    result=capture.run(folder,scenario.dependencies(),clock)
                    meta=json.loads(Path(result['json_path']).read_text('utf8'))
                    self.assertEqual(Path(result['binary_path']).read_bytes(),scenario.memory.body)
                    self.assertEqual(meta['ranges'],[{'name':'contact_whole_candidate_envelope',
                        'module':'game','rva':capture.BODY_BEGIN,'length':17266,'binary_offset':0}])
                    self.assertEqual(meta['ownership'],capture.validate_metadata_packet()['ownership'])
                    self.assertTrue(meta['all_real_contained_saved_fragments_match'])
                    self.assertTrue(meta['body_before_after_match'])
                    self.assertTrue(meta['full_metadata_window_matches_frozen'])
                    self.assertTrue(meta['fresh_gates_verified'])
                    self.assertEqual(meta['ship_before'],meta['ship_after'])
                    self.assertEqual(meta['budget']['read_calls'],29)
                    self.assertEqual(meta['budget']['query_calls'],29)
                    self.assertEqual(meta['budget']['bytes_requested'],43788)
                    self.assertEqual(scenario.memory.window_reads,2)
                self.assertEqual(scenario.memory.body_reads,2)
                self.assertEqual(meta['new_code_body_reads'],2)
                self.assertEqual(meta['unknown_code_bytes_returned'],34532)
                self.assertEqual(meta['budget']['read_calls'],len(scenario.memory.reads))
                self.assertEqual(meta['budget']['query_calls'],len(scenario.memory.queries))
                self.assertEqual(meta['budget']['bytes_requested'],sum(size for _,size in scenario.memory.reads))
                self.assertLessEqual(meta['budget']['read_calls'],56)
                self.assertLessEqual(meta['budget']['bytes_requested'],49152)
                self.assertEqual(meta['budget']['max_bytes'],49152)
                self.assertEqual(meta['budget']['max_reads'],56)
                self.assertFalse(meta['logical_function_complete']);self.assertFalse(meta['normal_CFG_closed'])
                self.assertFalse(meta['payload_ready']);self.assertFalse(meta['classification_ready'])
                self.assertFalse(meta['contract_ready']);self.assertFalse(meta['native_called'])
                self.assertFalse(meta['native_written']);self.assertEqual(meta['heap_reads'],0)
                self.assertEqual(meta['extra_callee_reads'],0)
                self.assertNotIn((0x13B0BD0,32),scenario.memory.custom_reads)
                self.assertTrue(scenario.memory.closed)
                self.assertEqual((fixture.capture.v1.frozen.MAX_BYTES,fixture.capture.v1.frozen.MAX_READS,
                                  fixture.capture.v1.frozen.MAX_CODE_BYTES),OLD_LIMITS)
                print('OWNED_BUDGET '+json.dumps({'case':name,'Game_accessed':False,'old_suites_run':False,
                    'body_reads':scenario.memory.body_reads,'binary_saved':not bool(reason),'budget':meta['budget']}))


if __name__=='__main__':unittest.main()
