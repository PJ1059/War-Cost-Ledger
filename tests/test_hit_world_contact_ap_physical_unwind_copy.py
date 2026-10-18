"""Necessary pure six-region UW/RF mapping tests; no APIs/Game/old suite."""
import hashlib
import importlib.util
from pathlib import Path
import struct
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('owned_six_region_UW',
    ROOT/'tools/native/hit_world_contact_ap_physical_unwind_copy.py')
mapper=importlib.util.module_from_spec(spec);spec.loader.exec_module(mapper)
BASE,NEAR=0x180000000,0x190000000
LAYOUT={name:NEAR+offset for name,offset in
        [('frame',0x100),('world',0x1000),('contact',0x4000),
         ('ap',0xB000),('dispatcher',0xA000),('physical',0x9000)]}
UW,TABLE=NEAR+0xC000,NEAR+0xD000
RESULTS=[]
BUILD=None


class SixRegionUnwindTests(unittest.TestCase):
    def test_actual28_RF22_chains_and_only_embedded_triples_change(self):
        global BUILD
        source=mapper.load_sources();built=mapper.build(BASE,LAYOUT,UW,TABLE)
        BUILD=built
        meta=built['manifest'];raw=built['unwind_blob'];table=built['runtime_table_blob']
        self.assertEqual(len(raw),732);self.assertEqual(len(table),336)
        self.assertEqual(len(meta['runtime_records']),28);self.assertEqual(len(meta['chain_rewrites']),22)
        self.assertEqual(len(meta['unwind_nodes']),28)
        self.assertEqual(source['records']['physical'][3],(0x13B0D0F,0x13B0D63,0x25116A8))
        self.assertEqual(source['evidence']['physical_indices_fresh'],list(range(68146,68153)))
        rows=[struct.unpack_from('<III',table,i*12)for i in range(28)]
        self.assertEqual(rows,[tuple(r['new'])for r in meta['runtime_records']])
        self.assertEqual(rows,sorted(rows));self.assertTrue(all(a[1]<=b[0]for a,b in zip(rows,rows[1:])))
        for record in meta['runtime_records']:
            name=record['region'];begin,size,_=mapper.REGIONS[name]
            u_begin,_,_,u_offset=mapper.UW_BLOCKS[name]
            old=record['old']
            self.assertEqual(tuple(record['new']),
                (LAYOUT[name]-BASE+old[0]-begin,LAYOUT[name]-BASE+old[1]-begin,
                 UW-BASE+u_offset+old[2]-u_begin))
        for name,(_,size,_)in mapper.REGIONS.items():
            copied=[r for r in meta['runtime_records']if r['region']==name]
            self.assertEqual(copied[-1]['new'][1],LAYOUT[name]-BASE+size,'End==region_end supported')
        masks=set()
        for rewrite in meta['chain_rewrites']:
            at=rewrite['blob_offset'];masks.update(range(at,at+12))
            self.assertEqual(struct.unpack_from('<III',raw,at),tuple(rewrite['new_chain']))
        self.assertTrue(all(raw[i]==source['raw'][i]for i in range(732)if i not in masks),
                        'Only22 embedded triples may change; headers/slots/padding/GS4 preserved')
        gs=[n for n in meta['unwind_nodes']if n['flags']==3]
        self.assertEqual({n['region']for n in gs},{'world','contact'})
        for node in gs:self.assertEqual(node['copy_hex'],node['source_hex'])
        for name in ('ap','dispatcher','physical'):
            self.assertTrue(all(n['flags']in(0,4)for n in source['nodes'][name]))
        for key in ('native_registered','native_called','Game_accessed','new_RX_executed',
                    'owned_unwind_parity_proven','Game_or_exception_safety_proven','classification_ready'):
            self.assertFalse(meta[key])
        self.assertEqual(sum(len(v)for v in built['code']['blobs'].values()),29824)
        RESULTS.append({'case':'actual28RF22chain','status':'PASS','UW_bytes':732,'RF_bytes':336,
            'RF_count':28,'chain_count':22,'code_bytes':29824,
            'unwind_sha256':hashlib.sha256(raw).hexdigest(),'table_sha256':hashlib.sha256(table).hexdigest()})

    def test_actual_new_packet_hard_SHA_is_required(self):
        with patch.object(mapper,'SOURCE_BIN_SHA','0'*64):
            with self.assertRaisesRegex(ValueError,'SOURCE_SHA_MISMATCH'):
                mapper.build(BASE,LAYOUT,UW,TABLE)
        RESULTS.append({'case':'new_packet_SHA','status':'PASS'})

    def test_metadata_alignment_RVA32_and_overlap_are_rejected(self):
        for name,uw,table,reason in [('alignment',UW+1,TABLE,'ADDRESS_OR_ALIGNMENT'),
                ('RVA32',BASE+0x100000000,TABLE,'RVA32_OUT_OF_RANGE'),
                ('overlap',LAYOUT['physical'],TABLE,'LAYOUT_OVERLAP')]:
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError,reason):mapper.build(BASE,LAYOUT,uw,table)
        RESULTS.append({'case':'metadata_layout_rejects','status':'PASS','checks':['4B_alignment','RVA32','overlap']})


if __name__=='__main__':unittest.main()
