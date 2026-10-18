"""Real owned x64 calls. Never open or inspect the running game."""
import ctypes
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/native'))
from hit_bridge_owned import OwnedBridge
from hit_entity_resolver_owned import OwnedEntityResolver,MAP,DESCRIPTORS,STRIDE

class EntityResolverTests(unittest.TestCase):
    def test_actual_native_hash_type_and_uint64_catalog_lookup(self):
        with OwnedBridge() as bridge:
            resolver=OwnedEntityResolver(bridge)
            resolver.insert(123,resolver.enemies[0],0)
            resolver.insert(456,resolver.sources[-1],1)
            self.assertEqual(resolver.lookup(123),resolver.enemies[0])
            self.assertEqual(resolver.lookup(456),resolver.sources[-1])
            self.assertTrue(resolver.admitted('enemy',resolver.lookup(123)))
            self.assertTrue(resolver.admitted('source',resolver.lookup(456)))
            self.assertFalse(resolver.admitted('enemy',resolver.lookup(456)))
            self.assertEqual(resolver.lookup(0),0)
            self.assertEqual(resolver.lookup(789),0)

    def test_probe_bound_returns_unknown_at_ninth_collision(self):
        with OwnedBridge() as bridge:
            resolver=OwnedEntityResolver(bridge)
            for i in range(9):resolver.insert(1+16*i,resolver.enemies[0],i)
            self.assertEqual(resolver.lookup(1+16*7),resolver.enemies[0])
            self.assertEqual(resolver.lookup(1+16*8),0)

    def test_changed_descriptor_identity_never_reuses_type(self):
        with OwnedBridge() as bridge:
            resolver=OwnedEntityResolver(bridge)
            slot=resolver.insert(123,resolver.enemies[0],0)
            ctypes.c_uint32.from_address(resolver.manager+DESCRIPTORS+8).value=456
            self.assertEqual(resolver.lookup(123),0)
            ctypes.c_uint32.from_address(resolver.buckets+slot*8+4).value=0xffffffff
            self.assertEqual(resolver.lookup(123),0)

    def test_invalid_capacity_or_absent_buckets_refuses_before_lookup(self):
        with OwnedBridge() as bridge:
            resolver=OwnedEntityResolver(bridge)
            for capacity in (0,3,0x200000):
                ctypes.c_uint32.from_address(resolver.manager+MAP+8).value=capacity
                self.assertEqual(resolver.lookup(123),0)
            ctypes.c_uint32.from_address(resolver.manager+MAP+8).value=16
            ctypes.c_uint64.from_address(resolver.manager+MAP).value=0
            self.assertEqual(resolver.lookup(123),0)

    def test_allowlist_excludes_unresolved_enemy_and_spray_source(self):
        with OwnedBridge() as bridge:
            resolver=OwnedEntityResolver(bridge)
            self.assertFalse(resolver.admitted('enemy',0x089833D2880D9E06))
            self.assertFalse(resolver.admitted('source',0xE90F771A36FB441E)) # FLAM-40
            self.assertFalse(resolver.admitted('source',0xFDE262593307CA2F)) # LAS-98 beam
            self.assertTrue(resolver.admitted('source',0x11C27D3BABB38956)) # MG-43 weapon source
            self.assertTrue(resolver.admitted('source',0xC12A34F375BD5A87)) # incendiary bullet source
            self.assertFalse(resolver.admitted('enemy',0))
        with self.assertRaises(ValueError):resolver.lookup(123)

    def test_native_qualifier_sets_only_proven_bits_and_publishes_nothing(self):
        with OwnedBridge() as bridge:
            resolver=OwnedEntityResolver(bridge)
            resolver.insert(123,resolver.enemies[0],0)
            resolver.insert(456,0xC12A34F375BD5A87,1)
            record=bridge.record(target=123,source=456,capture_flags=0xBF)
            self.assertEqual(resolver.qualify(record),0x1FF)
            self.assertEqual(record.target_kind,1)
            self.assertEqual(bridge.drain(),[])
            record.source=789
            self.assertEqual(resolver.qualify(record),0xFF)
            record.target=789
            self.assertEqual(resolver.qualify(record),0xBF)
            self.assertEqual(record.target_kind,0)

    def test_native_qualifier_actual_unwind_body_and_each_epilog_pc(self):
        with OwnedBridge() as bridge:
            resolver=OwnedEntityResolver(bridge)
            procedure=resolver._qualify
            address=int(ctypes.cast(procedure,ctypes.c_void_p).value)
            code=bridge._procedures[address]['code']
            epilog=len(code)-7
            for pc,delta,rdi,rsi in [(6,56,False,False),(epilog,56,False,False),
                                   (epilog+4,16,False,False),(epilog+5,8,True,False),
                                   (epilog+6,0,True,True)]:
                result=bridge.unwind_fixture(procedure,pc,stack_delta=delta,
                    restored_rdi=rdi,restored_rsi=rsi)
                for field in ('rsp','rdi','rsi','rip'):
                    self.assertEqual(result[field],result['expected_'+field])

if __name__=='__main__':unittest.main()
