"""Only newly exported qualifier/data paths; seven frozen gateways stay unchanged."""
import ctypes
import hashlib
import json
import struct
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/native'))
from hit_observer_package import package,MANAGER_GLOBAL_RVA
from hit_callable_profile import manifest as original_manifest
from hit_entity_resolver_owned import lookup_code,allow_code,qualify_code,OwnedEntityResolver
from hit_bridge_owned import OwnedBridge
sys.path.insert(0,str(ROOT/'tests'))
from test_native_hit_callable_profile_owned import OwnedProfile


def bind(entry,addresses):
    raw=bytearray.fromhex(entry['code_hex'])
    for item in entry['relocations']:
        assert item['width']==8 and raw[item['offset']:item['offset']+8]==bytes(8)
        struct.pack_into('<Q',raw,item['offset'],addresses[item['address_key']]+item['addend'])
    return bytes(raw)


class FullPackageExportTests(unittest.TestCase):
    def test_thirteen_frozen_entries_are_byte_and_metadata_equal_and_all_symbols_resolve(self):
        m=package();old=original_manifest()
        frozen=json.loads((ROOT/'dist/hit-native-callable-profile-owned-20261012/profile-manifest.json').read_text())
        self.assertEqual(old,frozen);self.assertEqual(m['entries'][:13],old['entries'])
        self.assertEqual(len(m['entries']),16)
        available={e['name'] for e in m['entries']}|{'arena','bridge','entity_manager_global',
            'original_contact_begin','original_normal_final','original_custom_curve'}|set(m['data_tables'])
        for entry in m['entries']:
            for rel in entry['relocations']:self.assertIn(rel['address_key'],available)
        for name,count in [('enemy_types',111),('source_types',91)]:
            values=m['data_tables'][name];self.assertEqual(len(values),count)
            self.assertTrue(all(len(v)==16 and int(v,16)>0 for v in values))
            self.assertEqual(values,sorted(set(values)))

    def test_explicit_qualifier_relocations_rebuild_original_proved_generator_exactly(self):
        m=package();entry=m['entries'][-1]
        addresses={'resolve':0x1111222233334444,'allow':0x2222333344445555,
            'enemy_types':0x3333444455556666,'source_types':0x4444555566667777}
        expected=qualify_code(addresses['resolve'],addresses['allow'],addresses['enemy_types'],111,
                              addresses['source_types'],91)
        self.assertEqual(bind(entry,addresses),expected)
        self.assertEqual(bytes.fromhex(m['entries'][-3]['code_hex']),lookup_code())
        self.assertEqual(bytes.fromhex(m['entries'][-2]['code_hex']),allow_code())

    def test_manager_global_is_runtime_wielder_and_actual_rip_target(self):
        evidence=package()['entity_manager_evidence']
        self.assertEqual(evidence['manager_global_rva'],MANAGER_GLOBAL_RVA)
        self.assertEqual(evidence['actual_global_rip_target'],0x346BF98)
        self.assertEqual(evidence['actual_global_load_rva'],0xFD9D50)
        self.assertEqual(evidence['sdk_wielder']['entityMap'],0xF1AEB0)
        self.assertEqual(evidence['sdk_wielder']['descriptors'],0xF32F18)
        raw=(ROOT/evidence['actual_lookup_path']).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),evidence['actual_lookup_sha256'])

    def test_complete_export_new_native_qualifier_uses_relocated_tables_and_functions(self):
        m=package();entries={e['name']:e for e in m['entries']}
        with OwnedBridge() as b:
            fixture=OwnedEntityResolver(b)
            fixture.insert(1001,int(m['data_tables']['enemy_types'][0],16),0)
            fixture.insert(1002,int(m['data_tables']['source_types'][0],16),1)
            resolve=b._procedure(bytes.fromhex(entries['resolve']['code_hex']),ctypes.c_uint64,
                ctypes.c_void_p,ctypes.c_uint32,unwind=bytes.fromhex(entries['resolve']['unwind_hex']))
            allow=b._procedure(bytes.fromhex(entries['allow']['code_hex']),ctypes.c_uint32,
                ctypes.c_void_p,ctypes.c_uint64,ctypes.c_uint32,unwind=bytes.fromhex(entries['allow']['unwind_hex']))
            addresses={'resolve':int(ctypes.cast(resolve,ctypes.c_void_p).value),
                'allow':int(ctypes.cast(allow,ctypes.c_void_p).value)}
            for name,values in m['data_tables'].items():
                raw=b''.join(struct.pack('<Q',int(v,16)) for v in values)
                at=b._allocate(len(raw),executable=False);ctypes.memmove(at,raw,len(raw));addresses[name]=at
            entry=entries['qualifier'];qualified=b._procedure(bind(entry,addresses),ctypes.c_uint32,
                ctypes.c_void_p,ctypes.c_void_p,unwind=bytes.fromhex(entry['unwind_hex']))
            record=b.record(target=1001,source=1002,capture_flags=3)
            self.assertEqual(qualified(fixture.manager,ctypes.addressof(record)),0x143)
            self.assertEqual(record.target_kind,1)
            record.source=9999;self.assertEqual(qualified(fixture.manager,ctypes.addressof(record)),0x43)
            record.target=9999;record.source=1002
            self.assertEqual(qualified(fixture.manager,ctypes.addressof(record)),0x103)
            record.target=0;record.source=0
            self.assertEqual(qualified(fixture.manager,ctypes.addressof(record)),3)
            self.assertEqual(record.target_kind,0)
            self.assertEqual(b.stats()['accepted'],0)

    def test_portable_qualifier_and_tables_feed_frozen_gateways_all_four_classes(self):
        m=package();entries={e['name']:e for e in m['entries']}
        with OwnedBridge() as b:
            p=OwnedProfile(b);addresses=dict(p.addresses)
            resolve=b._procedure(bytes.fromhex(entries['resolve']['code_hex']),ctypes.c_uint64,
                ctypes.c_void_p,ctypes.c_uint32,unwind=bytes.fromhex(entries['resolve']['unwind_hex']))
            allow=b._procedure(bytes.fromhex(entries['allow']['code_hex']),ctypes.c_uint32,
                ctypes.c_void_p,ctypes.c_uint64,ctypes.c_uint32,unwind=bytes.fromhex(entries['allow']['unwind_hex']))
            addresses.update(resolve=int(ctypes.cast(resolve,ctypes.c_void_p).value),
                             allow=int(ctypes.cast(allow,ctypes.c_void_p).value))
            for name,values in m['data_tables'].items():
                raw=b''.join(struct.pack('<Q',int(v,16)) for v in values)
                at=b._allocate(len(raw),executable=False);ctypes.memmove(at,raw,len(raw));addresses[name]=at
            entry=entries['qualifier'];fn=b._procedure(bind(entry,addresses),ctypes.c_uint32,
                ctypes.c_void_p,ctypes.c_void_p,unwind=bytes.fromhex(entry['unwind_hex']))
            addresses['qualifier']=int(ctypes.cast(fn,ctypes.c_void_p).value)
            for name in ['normal_final','physical_success']:
                entry=entries[name]
                p.functions[name]=b._procedure(bind(entry,addresses),ctypes.c_uint64,
                    ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint64,ctypes.c_uint64,ctypes.c_void_p,
                    unwind=bytes.fromhex(entry['unwind_hex']),executable_length=entry['executable_length'])
            p.site.restore();p.site.install(p.functions['normal_final'])
            for ap in [3,4,5]:p.begin();p.ap(ap);p.final_call()
            p.begin();out=b._allocate(1040,executable=False)
            p.physical_caller()(out,ctypes.addressof(p.final),ctypes.addressof(p.hit),17)
            records=b.drain();self.assertEqual(len(records),4)
            self.assertEqual([(v.native_branch,v.capture_flags) for v in records],[(1,0x1FF)]*3+[(2,0x143)])
            self.assertEqual([v.ap_delta for v in records[:3]],[-1,0,1])
            self.assertTrue(all(v.creditor==b.local_peer and v.source==1002 and v.target==1001 for v in records))
            self.last_records=records


if __name__=='__main__':unittest.main(verbosity=2)
