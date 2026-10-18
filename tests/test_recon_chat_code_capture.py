"""Owned exception-table/code fixtures; never opens or reads the game process."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import recon_chat_code_capture as sampler
import fire_code_capture as fire_sampler


class Clock:
    value = 0.0

    def __call__(self):
        return self.value


class Memory:
    base = 0x180000000
    identity = {'game_base': base, 'game_size': sampler.IMAGE_SIZE,
                'game_path': 'owned-fixture.dll', 'exe_path': 'owned-fixture.exe'}

    def __init__(self):
        self.reads, self.queries = [], []
        self.protection, self.kind, self.state = 0x20, 0x1000000, 0x1000
        self.short = self.corrupt = self.invalid_entry = self.gap = False
        self.bad_unwind = False
        self.begin = sampler.TARGET_RVA & ~0xff
        self.end = self.begin + 0x100
        self.clock, self.query_delay, self.read_delay = None, 0, 0
        self.metadata = {0x3000000: bytes((1,0,0,0))}
        self.code_intervals = None

    def configure_chain(self, parents, count=6):
        nodes = [(self.begin, self.end, 0x3000000)]
        for i in range(parents):
            begin = self.begin - (i+1)*0x200
            nodes.append((begin,begin+0x80,0x3000100+i*0x100))
        self.set_nodes(nodes, count)
        return nodes

    def set_nodes(self, nodes, count=6):
        self.metadata, self.code_intervals = {}, [(b,e) for b,e,_ in nodes]
        for i, (begin,end,unwind) in enumerate(nodes):
            self.metadata[unwind] = bytes((0x21 if i+1 < len(nodes) else 1,15,count,0))
            if i+1 < len(nodes):
                chain_rva = unwind + 4 + 2*((count+1)&~1)
                self.metadata[chain_rva] = struct.pack('<III',*nodes[i+1])

    def query(self, address):
        self.queries.append(address)
        if self.clock:
            self.clock.value += self.query_delay
        return {'base': self.base, 'size': sampler.IMAGE_SIZE,
                'protect': self.protection, 'type': self.kind, 'state': self.state}

    def read(self, address, length):
        self.reads.append((address, length))
        if self.clock:
            self.clock.value += self.read_delay
        rva = address - self.base
        if rva in self.metadata:
            raw = self.metadata[rva]
            assert length == len(raw)
            if self.bad_unwind and rva == 0x3000000:
                raw = bytes(4)
        elif sampler.EXCEPTION_RVA <= rva < sampler.EXCEPTION_RVA + sampler.EXCEPTION_SIZE:
            assert length == sampler.ENTRY_SIZE
            index = (rva - sampler.EXCEPTION_RVA) // sampler.ENTRY_SIZE
            begin, end = (index + 1) * 0x100, (index + 2) * 0x100
            if begin == sampler.TARGET_RVA & ~0xff:
                begin = self.begin
                end = self.begin + 0x40 if self.gap else self.end
            raw = bytes(12) if self.invalid_entry else struct.pack('<III', begin, end, 0x3000000)
        else:
            intervals = self.code_intervals or [(self.begin,self.end)]
            assert all(any(b<=at<e for b,e in intervals) for at in range(rva,rva+length)), 'Read outside exact ancestry code intervals'
            body = bytearray(length)
            pin = bytes.fromhex(sampler.TARGET_PIN)
            offset = sampler.TARGET_RVA - rva
            if 0 <= offset and offset + len(pin) <= length:
                body[offset:offset + len(pin)] = bytes(len(pin)) if self.corrupt else pin
            raw = bytes(body)
        return raw[:-1] if self.short else raw


class CaptureTests(unittest.TestCase):
    def test_complete_function_pin_and_single_shared_budget(self):
        memory = Memory()
        binary, meta = sampler.capture(memory, memory.identity, clock=Clock())
        table_reads = len(meta['exception_records'])
        self.assertLessEqual(table_reads, 24)
        self.assertEqual(len(memory.reads), table_reads + 2)
        self.assertEqual([n for _, n in memory.reads[:-1]], [12] * table_reads + [4])
        self.assertEqual(memory.reads[-1], (memory.base + memory.begin, 256))
        self.assertEqual(meta['budget']['bytes_requested'], 12 * table_reads + 4 + 256)
        self.assertEqual(meta['budget']['read_calls'], table_reads + 2)
        self.assertEqual(meta['budget']['query_calls'], table_reads + 2)
        self.assertLessEqual(meta['budget']['bytes_requested'], sampler.MAX_BYTES)
        self.assertEqual(meta['function_begin'], memory.begin)
        self.assertEqual(meta['function_end'], memory.end)
        self.assertEqual(meta['pins'], [{'rva': sampler.TARGET_RVA,
                                         'range': 'chat_history_consumer', 'matched': True}])
        self.assertTrue(meta['complete'])
        self.assertFalse(meta['native_written']); self.assertFalse(meta['native_called'])
        self.assertEqual(meta['chat_messages_read'], 0)
        self.assertEqual(meta['recon_events_emitted'], 0)
        sampler.verify_saved(meta, binary)
        self.assertEqual(fire_sampler.REVISION, 'fire_death_code_v1')
        self.assertEqual(fire_sampler.TOTAL_BYTES, 19328)

    def test_oversized_function_stops_without_partial_code_read(self):
        memory, evidence = Memory(), {}
        memory.end = memory.begin + sampler.MAX_FUNCTION_BYTES + 1
        with self.assertRaisesRegex(ValueError, 'FUNCTION_TOO_LARGE'):
            sampler.capture(memory, memory.identity, clock=Clock(), evidence=evidence)
        self.assertTrue(evidence['exception_records'])
        self.assertEqual(evidence['exception_records'][-1]['end'], memory.end)
        self.assertTrue(all(n == 12 for _, n in memory.reads))
        self.assertLessEqual(evidence['budget']['read_calls'], 24)

    def test_maximum_body_stays_inside_total_byte_and_operation_caps(self):
        memory = Memory(); memory.end = memory.begin + sampler.MAX_FUNCTION_BYTES
        binary, meta = sampler.capture(memory, memory.identity, clock=Clock())
        self.assertEqual(len(binary), 4096)
        self.assertLessEqual(meta['budget']['bytes_requested'], 24 * 12 + 4 + 4096)
        self.assertLessEqual(meta['budget']['read_calls'], 26)
        self.assertLessEqual(meta['budget']['query_calls'], 26)

    def test_invalid_entry_and_gap_do_not_read_body(self):
        for field, error in (('invalid_entry', 'ENTRY_INVALID'), ('gap', 'FUNCTION_NOT_FOUND')):
            memory = Memory(); setattr(memory, field, True)
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, error):
                sampler.capture(memory, memory.identity, clock=Clock())
            self.assertTrue(all(n == 12 for _, n in memory.reads))
            self.assertLessEqual(len(memory.reads), 24)

    def test_pin_mismatch_and_short_read_stop(self):
        memory = Memory(); memory.corrupt = True
        with self.assertRaisesRegex(ValueError, 'PIN_MISMATCH'):
            sampler.capture(memory, memory.identity, clock=Clock())
        memory = Memory(); memory.short = True
        with self.assertRaisesRegex(ValueError, 'SHORT_READ'):
            sampler.capture(memory, memory.identity, clock=Clock())
        self.assertEqual(len(memory.reads), 1)

    def test_unknown_unwind_stops_without_code_body_read(self):
        memory, evidence = Memory(), {}; memory.bad_unwind = True
        with self.assertRaisesRegex(ValueError, 'UNWIND_FORMAT_UNKNOWN'):
            sampler.capture(memory, memory.identity, clock=Clock(), evidence=evidence)
        self.assertEqual(memory.reads[-1], (memory.base + 0x3000000, 4))
        self.assertTrue(all(n in (4,12) for _,n in memory.reads))
        self.assertIn('unwind_chain',evidence)

    def test_native_v1_six_slot_chain_offset_and_exact_disjoint_ranges(self):
        memory = Memory(); nodes = memory.configure_chain(1)
        self.assertEqual(memory.metadata[0x3000000].hex(),'210f0600')
        binary,meta = sampler.capture(memory,memory.identity,clock=Clock())
        self.assertIn((memory.base+0x3000010,12),memory.reads)
        self.assertEqual(len(meta['unwind_chain']),2)
        self.assertEqual([(r['rva'],r['length']) for r in meta['ranges']],
                         [(nodes[1][0],0x80),(nodes[0][0],0x100)])
        self.assertEqual(len(binary),0x180)
        self.assertFalse(meta['all_sibling_fragments_captured'])
        self.assertFalse(meta['logical_function_complete'])
        sampler.verify_saved(meta,binary)

    def test_captured_v1_leaf_layout_and_owned_parent_use_exact_chain_address(self):
        # The leaf/header are observed v1 evidence. The parent below is owned
        # fixture data, not a claim about the uncollected real parent.
        initial=(0x10979E3,0x1097A88,0x24DB610)
        parent=(0x1097600,0x1097700,0x3000000)
        records={0x24DB610:bytes.fromhex('210f0600'),
                 0x24DB620:struct.pack('<III',*parent),0x3000000:bytes((1,15,6,0))}
        reads=[]
        def read(rva,size):
            reads.append((rva,size));raw=records[rva];self.assertEqual(len(raw),size);return raw
        nodes=[];sampler.unwind_ancestry(initial,read,nodes)
        self.assertEqual(reads,[(0x24DB610,4),(0x24DB620,12),(0x3000000,4)])
        self.assertEqual(len(nodes),2)

    def test_odd_unwind_slot_count_rounds_up_before_chain_record(self):
        memory = Memory(); memory.configure_chain(1,count=3)
        sampler.capture(memory,memory.identity,clock=Clock())
        self.assertIn((memory.base+0x300000C,12),memory.reads)
        self.assertNotIn((memory.base+0x300000A,12),memory.reads)

    def test_four_nodes_succeed_with_shared_budget_and_fifth_stops(self):
        memory=Memory();memory.configure_chain(3)
        binary,meta=sampler.capture(memory,memory.identity,clock=Clock())
        self.assertEqual(len(meta['unwind_chain']),4)
        self.assertLessEqual(meta['budget']['read_calls'],31)
        self.assertLessEqual(meta['budget']['bytes_requested'],4388)
        sampler.verify_saved(meta,binary)
        memory=Memory();memory.configure_chain(4);evidence={}
        with self.assertRaisesRegex(ValueError,'DEPTH_LIMIT'):
            sampler.capture(memory,memory.identity,clock=Clock(),evidence=evidence)
        self.assertEqual(len(evidence['unwind_chain']),4)
        self.assertTrue(all(n in (4,12) for _,n in memory.reads))

    def test_cycle_frame_mixed_flags_count_and_invalid_parent_stop_before_code(self):
        changes=(('cycle',lambda m,n:m.metadata.update({0x3000010:struct.pack('<III',*n[0])}),'UNWIND_CYCLE'),
                 ('frame',lambda m,n:m.metadata.update({n[1][2]:bytes((1,15,6,1))}),'FRAME_MISMATCH'),
                 ('flags',lambda m,n:m.metadata.update({0x3000000:bytes((0x29,15,6,0))}),'FLAGS_MIXED'),
                 ('count',lambda m,n:m.metadata.update({0x3000000:bytes((0x21,15,65,0))}),'CODES_LIMIT'),
                 ('parent',lambda m,n:m.metadata.update({0x3000010:struct.pack('<III',0,1,n[1][2])}),'ENTRY_INVALID'),
                 ('unaligned',lambda m,n:m.metadata.update({0x3000010:struct.pack('<III',n[1][0],n[1][1],n[1][2]+1)}),'ADDRESS_INVALID'),
                 ('outside',lambda m,n:m.metadata.update({0x3000010:struct.pack('<III',n[1][0],n[1][1],sampler.IMAGE_SIZE)}),'ENTRY_INVALID'))
        for label,change,error in changes:
            memory=Memory();nodes=memory.configure_chain(1);change(memory,nodes)
            with self.subTest(label=label),self.assertRaisesRegex(ValueError,error):
                sampler.capture(memory,memory.identity,clock=Clock())
            self.assertTrue(all(n in (4,12) for _,n in memory.reads))

    def test_exact_union_byte_limit_and_overlap_merge(self):
        memory=Memory();nodes=memory.configure_chain(1)
        memory.set_nodes([nodes[0],(nodes[1][0]-0x1000,nodes[1][0]-0x1000+4096,nodes[1][2])])
        with self.assertRaisesRegex(ValueError,'CHAIN_CODE_BYTES_LIMIT'):
            sampler.capture(memory,memory.identity,clock=Clock())
        self.assertTrue(all(n in (4,12) for _,n in memory.reads))
        memory=Memory();nodes=memory.configure_chain(1)
        memory.set_nodes([nodes[0],(memory.begin-32,memory.end,nodes[1][2])])
        binary,meta=sampler.capture(memory,memory.identity,clock=Clock())
        self.assertEqual(len(meta['ranges']),1)
        self.assertEqual(meta['ranges'][0]['rva'],memory.begin-32)
        self.assertEqual(len(binary),288)
        sampler.verify_saved(meta,binary)

    def test_guard_private_and_noaccess_table_rejected_before_rpm(self):
        for field, value in (('protection', 0x120), ('protection', 0x01),
                             ('kind', 0x20000), ('state', 0x2000)):
            memory = Memory(); setattr(memory, field, value)
            with self.subTest(field=field, value=value), self.assertRaisesRegex(ValueError, 'REGION_UNREADABLE'):
                sampler.capture(memory, memory.identity, clock=Clock())
            self.assertEqual(memory.reads, [])

    def test_readonly_table_permitted_but_body_must_be_executable(self):
        memory = Memory(); memory.protection = 0x02
        with self.assertRaisesRegex(ValueError, 'REGION_UNREADABLE'):
            sampler.capture(memory, memory.identity, clock=Clock())
        self.assertTrue(memory.reads)
        self.assertTrue(all(n in (4, 12) for _, n in memory.reads))

    def test_module_invalid_before_any_memory_access(self):
        for change in ({'game_base': 0x123}, {'game_size': sampler.IMAGE_SIZE - 4096}):
            memory = Memory()
            with self.assertRaisesRegex(ValueError, 'MODULE_INVALID'):
                sampler.capture(memory, dict(memory.identity, **change), clock=Clock())
            self.assertEqual(memory.queries, [])

    def test_byte_operations_and_time_gates_before_reads(self):
        memory, clock = Memory(), Clock()
        budget = sampler.Budget(memory, memory.identity, clock)
        budget.bytes_requested = sampler.MAX_BYTES - 11
        with self.assertRaisesRegex(ValueError, 'READ_BUDGET'):
            sampler.table_read(budget, 0)
        self.assertEqual(memory.queries, [])
        budget.bytes_requested, budget.read_calls = 0, sampler.MAX_READS
        with self.assertRaisesRegex(ValueError, 'READ_BUDGET'):
            sampler.table_read(budget, 0)
        self.assertEqual(memory.reads, [])
        budget.read_calls = 0
        clock.value = sampler.MAX_SECONDS
        with self.assertRaisesRegex(ValueError, 'TIME_BUDGET'):
            sampler.table_read(budget, 0)
        self.assertEqual(memory.queries, [])

    def test_slow_query_stops_before_rpm_and_slow_rpm_before_next_query(self):
        memory = Memory(); memory.clock = Clock(); memory.query_delay = 2
        with self.assertRaisesRegex(ValueError, 'TIME_BUDGET'):
            sampler.capture(memory, memory.identity, clock=memory.clock)
        self.assertEqual(len(memory.queries), 1); self.assertEqual(memory.reads, [])
        memory = Memory(); memory.clock = Clock(); memory.read_delay = 3
        with self.assertRaisesRegex(ValueError, 'TIME_BUDGET'):
            sampler.capture(memory, memory.identity, clock=memory.clock)
        self.assertEqual(len(memory.queries), 1); self.assertEqual(len(memory.reads), 1)

    def save(self, folder, binary, meta):
        bin_path, meta_path = folder / 'capture.bin', folder / 'capture.json'
        bin_path.write_bytes(binary)
        meta_path.write_text(json.dumps(meta), encoding='utf8')
        sampler.profile.write_status(folder, {'status': 'complete', 'binary_path': str(bin_path),
                                             'json_path': str(meta_path)})
        return bin_path, meta_path

    def test_cache_revalidates_exact_body_pin_hash_search_and_build(self):
        memory = Memory()
        binary, good = sampler.capture(memory, memory.identity, clock=Clock())
        changes = (lambda m: m.update(source_revision='other'),
                   lambda m: m.update(dll_sha='other'),
                   lambda m: m.update(binary_sha256='0' * 64),
                   lambda m: m.update(function_begin=memory.begin - 1),
                   lambda m: m['unwind_chain'][0]['header'].update(raw_hex='21000000'),
                   lambda m: m['exception_records'][0].update(index=0),
                   lambda m: m['budget'].update(bytes_requested=8193))
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            self.save(folder, binary, good)
            self.assertIsNotNone(sampler.saved_complete(folder))
            for change in changes:
                meta = json.loads(json.dumps(good)); change(meta)
                self.save(folder, binary, meta)
                self.assertIsNone(sampler.saved_complete(folder))
            self.save(folder, binary + b'X', good)
            self.assertIsNone(sampler.saved_complete(folder))

    def test_chain_cache_rejects_record_cycle_address_order_and_range_changes(self):
        memory=Memory();nodes=memory.configure_chain(1)
        binary,good=sampler.capture(memory,memory.identity,clock=Clock())
        changes=(lambda m:m['unwind_chain'][0]['chain_entry'].update(rva=0x300000C),
                 lambda m:m['unwind_chain'][0]['chain_entry'].update(raw_hex=struct.pack('<III',*nodes[0]).hex()),
                 lambda m:m['unwind_chain'].reverse(),
                 lambda m:m['ranges'].reverse(),
                 lambda m:m['unwind_chain'][1]['header'].update(raw_hex='010f0601'))
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)
            self.save(folder,binary,good);self.assertIsNotNone(sampler.saved_complete(folder))
            for change in changes:
                meta=json.loads(json.dumps(good));change(meta)
                self.save(folder,binary,meta);self.assertIsNone(sampler.saved_complete(folder))

    def context(self, memory):
        class Process:
            def __enter__(self):
                return memory
            def __exit__(self, *args):
                return False
        return SimpleNamespace(Process=lambda pid: Process(), resolve_game=lambda pid: memory.identity)

    def test_wait_beyond_120_seconds_then_one_successful_capture_and_stop(self):
        memory, delays = Memory(), []
        pids = [()] * 76 + [(111,), (111,)]
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            with patch.dict(sys.modules, {'fire_code_windows': self.context(memory)}), \
                    patch('probe_session.game_processes', side_effect=pids), \
                    patch.object(sampler.profile, 'fingerprints', return_value={}), \
                    patch.object(sampler.profile, 'validate_identity'), \
                    patch.object(sampler.time, 'sleep', side_effect=delays.append):
                result = sampler.wait_and_capture(folder)
            self.assertEqual(result['status'], 'complete')
            self.assertEqual(delays, [2] * 76 + [20])
            self.assertEqual(len(list(folder.glob('*.bin'))), 1)
            self.assertEqual(sampler.saved_complete(folder), result)
            self.assertEqual(result['chat_messages_read'], 0)

    def test_capture_failure_is_one_attempt_without_retry_or_partial_output(self):
        memory = Memory(); memory.short = True
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            with patch.dict(sys.modules, {'fire_code_windows': self.context(memory)}), \
                    patch('probe_session.game_processes', return_value=(111,)), \
                    patch.object(sampler.profile, 'fingerprints', return_value={}), \
                    patch.object(sampler.profile, 'validate_identity'), \
                    patch.object(sampler.time, 'sleep'):
                with self.assertRaisesRegex(ValueError, 'SHORT_READ'):
                    sampler.wait_and_capture(folder)
            self.assertEqual(len(memory.reads), 1)
            self.assertFalse(list(folder.glob('*.bin')))
            status = json.loads((folder / 'status.json').read_text(encoding='utf8'))
            self.assertEqual(status['attempts'], 1)
            self.assertEqual(status['status'], 'failed')
            self.assertEqual(status['evidence']['budget']['read_calls'], 1)


if __name__ == '__main__':
    unittest.main()
