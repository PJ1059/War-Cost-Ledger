"""Small owned code/data scopes only; never invokes the live CLI or Game APIs."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import test_flow_exe_entry_code_capture as fixture

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('owned_contact_index', ROOT / 'tools/hit-contact-registration-index.py')
indexer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(indexer)
HEADER = (indexer.SOURCE / 'game-pe-header.bin').read_bytes()


def scopes(code, data):
    return tuple({**row, 'virtual_size': len(payload), 'end_exclusive': row['rva'] + len(payload)}
                 for row, payload in zip(indexer.SECTIONS, (code, data)))


def reference_payloads(base=fixture.Memory.game):
    code, data = bytearray(256), bytearray(256)
    start = indexer.SECTIONS[0]['rva']
    def rel(at, opcode, prefix=b''):
        head = prefix + opcode
        code[at:at + len(head) + 4] = head + struct.pack('<i', indexer.TARGET_RVA - (start + at + len(head) + 4))
    rel(63, b'\xe8')
    rel(125, b'\xe9')
    rel(188, b'\x8d\x05', b'\x48')
    rel(30, b'\x8d\x0d', b'\x4c')
    # An indirect virtual/import call to a slot at the same RVA is NOT an E8
    # reference to the target function. Data code-looking bytes are not decoded.
    rel(10, b'\xff\x15')
    code[81:86] = b'\xe8' + struct.pack('<i', indexer.TARGET_RVA + 4 - (start + 81 + 5))
    code[95:102] = b'\x48\x8d\x00' + struct.pack('<i', indexer.TARGET_RVA - (start + 95 + 7))
    absolute = struct.pack('<Q', base + indexer.TARGET_RVA)
    code[230:238] = absolute
    data[63:71] = absolute
    data[249:257] = absolute[:7]  # Incomplete target at true section edge must not match.
    data[10:15] = b'\xe8' + struct.pack('<i', indexer.TARGET_RVA - (indexer.SECTIONS[1]['rva'] + 10 + 5))
    return bytes(code), bytes(data)


class Memory(fixture.Memory):
    def __init__(self, code, data, changed_pin=False, failed_payload_at=None,
                 code_protect=0x20, region_bytes=None, clock=None, delay=0, **options):
        super().__init__(**options)
        self.code, self.data = code, data
        self.changed_pin, self.failed_payload_at = changed_pin, failed_payload_at
        self.code_protect, self.region_bytes = code_protect, region_bytes
        self.clock, self.delay = clock, delay
        self.pin_reads = self.payload_reads = 0

    def query(self, address):
        if self.clock:
            self.clock.value += self.delay
        rva = address - self.game
        if address == self.game or rva == indexer.PIN_RVA:
            self.queries.append(address)
            return {'base': self.game, 'size': indexer.profile.GAME_IMAGE_SIZE,
                    'state': 0x1000, 'type': 0x1000000, 'protect': 2 if address == self.game else 0x20}
        for row, raw in zip(indexer.SECTIONS, (self.code, self.data)):
            if row['rva'] <= rva < row['rva'] + len(raw):
                self.queries.append(address)
                base = self.game + row['rva']
                size = len(raw)
                if self.region_bytes:
                    base += ((address - base) // self.region_bytes) * self.region_bytes
                    size = min(self.region_bytes, self.game + row['rva'] + len(raw) - base)
                return {'base': base, 'size': size, 'state': 0x1000, 'type': 0x1000000,
                        'protect': self.code_protect if row['kind'] == 'code' else 2}
        return super().query(address)

    def read(self, address, size):
        if address == self.game:
            assert size == 4096
            self.reads.append((address, size))
            return HEADER
        if address == self.game + indexer.PIN_RVA:
            assert size == 16
            self.pin_reads += 1
            self.reads.append((address, size))
            return bytes(size) if self.changed_pin and self.pin_reads > 1 else bytes.fromhex(indexer.PIN_HEX)
        rva = address - self.game
        for row, raw in zip(indexer.SECTIONS, (self.code, self.data)):
            at = rva - row['rva']
            if 0 <= at < at + size <= len(raw):
                self.payload_reads += 1
                if self.payload_reads == self.failed_payload_at:
                    raise OSError('OWNED_PAYLOAD_RPM_FAILED')
                self.reads.append((address, size))
                return raw[at:at + size]
        return super().read(address, size)


class Scenario(fixture.Scenario):
    def __init__(self, code, data, **options):
        final_change = options.pop('final_change', None)
        super().__init__(final_change=final_change)
        self.memory = Memory(code, data, **options)


class ContactReferenceTests(unittest.TestCase):
    def run_small(self, scenario, folder, clock=None, allow_title_screen=False):
        original = indexer.stream_index
        selected = scopes(scenario.memory.code, scenario.memory.data)
        # Production still uses both hard full sections. Only this owned
        # fixture supplies short spans to the pure bounded stream function.
        def owned_stream(budget, _, evidence):
            with patch.object(indexer, 'CHUNK_BYTES', 64):
                return original(budget, selected, evidence)
        with patch.object(indexer, 'stream_index', side_effect=owned_stream):
            return indexer.run(folder, scenario.dependencies(), clock=clock or fixture.Clock(),
                               allow_title_screen=allow_title_screen)

    def test_code_data_target_forms_cross_chunk_unaligned_and_false_virtual_call(self):
        code, data = reference_payloads()
        memory = Memory(code, data)
        budget = indexer.Budget(memory, memory.identity, fixture.Clock())
        with patch.object(indexer, 'CHUNK_BYTES', 64):
            result = indexer.stream_index(budget, scopes(code, data), {})
        self.assertTrue(result['complete'])
        rows = result['candidates']
        self.assertEqual(len(rows), 6)
        self.assertEqual([row['reference_kind'] for row in rows],
                         ['byte_rip_lea', 'byte_call_rel32', 'byte_jmp_rel32', 'byte_rip_lea',
                          'byte_absolute_qword', 'byte_absolute_qword'])
        self.assertEqual(len({(row['rva'], row['reference_kind']) for row in rows}), 6)
        self.assertEqual(rows[-1]['slot_alignment_mod8'], 7)
        self.assertTrue(all(not row['instruction_boundary_verified'] and not row['registration_proven'] for row in rows))
        for row in rows:
            selected = indexer.SECTIONS[row['section_index']]
            payload = code if row['section_index'] == 0 else data
            at = row['rva'] - selected['rva']
            lo, hi = max(0, at - 16), min(len(payload), at + row['match_length'] + 32)
            self.assertEqual(row['window_hex'], payload[lo:hi].hex())
            self.assertLessEqual(row['window_bytes'], 64)
        self.assertEqual(result['payload_bytes'], len(code) + len(data))
        self.assertEqual(memory.payload_reads, 8)

    def test_region_split_and_tiny_source_gates_no_whole_binary(self):
        code, data = reference_payloads()
        scenario = Scenario(code, data, region_bytes=40)
        with tempfile.TemporaryDirectory() as parent:
            status = self.run_small(scenario, Path(parent) / 'capture')
            meta = json.loads(Path(status['json_path']).read_text('utf8'))
            self.assertTrue(meta['source_gates_verified'])
            self.assertEqual(len(meta['candidates']), 6)
            self.assertEqual(meta['ship_before'], meta['ship_after'])
            self.assertTrue(meta['fresh_pin']['before_after_match'])
            self.assertEqual(scenario.memory.pin_reads, 2)
            self.assertEqual(meta['payload_bytes'], 512)
            self.assertEqual(meta['budget']['bytes_requested'], 512 + 8192 + 32 + 24)
            self.assertEqual(list((Path(parent) / 'capture').glob('*.bin')), [])
            self.assertFalse(meta['registered_callback_proven'])
            self.assertTrue(scenario.memory.closed)

    def test_combined65th_candidate_is_explicit_truncated_and_gated(self):
        absolute = struct.pack('<Q', fixture.Memory.game + indexer.TARGET_RVA)
        scenario = Scenario(absolute * 4, absolute * 70)
        with tempfile.TemporaryDirectory() as parent:
            status = self.run_small(scenario, Path(parent) / 'capture')
            meta = json.loads(Path(status['json_path']).read_text('utf8'))
            self.assertEqual(status['status'], 'truncated')
            self.assertTrue(meta['truncated'])
            self.assertFalse(meta['complete'])
            self.assertEqual(len(meta['candidates']), 64)
            self.assertEqual(sum(row['section_index'] == 0 for row in meta['candidates']), 4)
            self.assertTrue(meta['source_gates_verified'])

    def test_nonship_wrong_scope_and_nonexec_page_cannot_give_negative_complete(self):
        code, data = reference_payloads()
        scenario = Scenario(code, data, state=4)
        with tempfile.TemporaryDirectory() as parent:
            with self.assertRaisesRegex(ValueError, 'EXPECTS_SHIP'):
                self.run_small(scenario, Path(parent) / 'capture')
            self.assertEqual(scenario.memory.payload_reads, 0)
        # The explicit option preserves real TitleScreen state/name/context;
        # default Title2 and Mission4 remain refused without any index payload.
        scenario = Scenario(code, data, state=2, after=2)
        with tempfile.TemporaryDirectory() as parent:
            with self.assertRaisesRegex(ValueError, 'EXPECTS_SHIP'):
                self.run_small(scenario, Path(parent) / 'default-title')
            self.assertEqual(scenario.memory.payload_reads, 0)
            scenario = Scenario(code, data, state=2, after=2)
            status = self.run_small(scenario, Path(parent) / 'explicit-title', allow_title_screen=True)
            meta = json.loads(Path(status['json_path']).read_text('utf8'))
            self.assertEqual(meta['allowed_capture_states'], [2, 3])
            self.assertEqual(meta['ship_before']['state'], 2)
            self.assertEqual(meta['ship_before']['name'], 'TitleScreen')
            self.assertEqual(meta['ship_before'], meta['ship_after'])
            self.assertEqual(meta['capture_purpose'], 'STATIC_GAME_IMAGE_REFERENCE_INDEX_ONLY')
            scenario = Scenario(code, data, state=4, after=4)
            with self.assertRaisesRegex(ValueError, 'EXPECTS_ALLOWED_STATIC_STATE'):
                self.run_small(scenario, Path(parent) / 'explicit-mission', allow_title_screen=True)
            self.assertEqual(scenario.memory.payload_reads, 0)
        memory = Memory(code, data)
        budget = indexer.Budget(memory, memory.identity, fixture.Clock())
        wrong = [{**scopes(code, data)[0], 'kind': 'declared_ro_data'}]
        with self.assertRaisesRegex(ValueError, 'SCOPE_CHANGED'):
            indexer.stream_index(budget, wrong, {})
        scenario = Scenario(code, data, code_protect=2)
        with tempfile.TemporaryDirectory() as parent:
            with self.assertRaisesRegex(ValueError, 'REGION_UNREADABLE'):
                self.run_small(scenario, Path(parent) / 'capture')
            self.assertEqual(scenario.memory.payload_reads, 0)

    def test_source_pin_module_ship_or_readfailure_withholds_all_windows(self):
        code, data = reference_payloads()
        for options, reason in (({'changed_pin': True}, 'LOADED_SOURCE_CHANGED'),
                                ({'final_change': ('game_base', fixture.Memory.game + 4096)}, 'MODULE_CHANGED'),
                                ({'after': 4}, 'SHIP_CHANGED'),
                                ({'failed_payload_at': 2}, 'PAYLOAD_RPM_FAILED')):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as parent:
                scenario = Scenario(code, data, **options)
                folder = Path(parent) / 'capture'
                with self.assertRaisesRegex((ValueError, OSError), reason):
                    self.run_small(scenario, folder)
                meta = json.loads((folder / 'references.incomplete.json').read_text('utf8'))
                self.assertTrue(meta['results_withheld'])
                self.assertNotIn('candidates', meta)
                self.assertFalse(meta['source_gates_verified'])
                self.assertTrue(scenario.memory.closed)

    def test_hard_source_budget_and_softtime_fail_once(self):
        code, data = reference_payloads()
        with tempfile.TemporaryDirectory() as parent:
            scenario = Scenario(code, data)
            with patch.object(indexer, 'SOURCE_SHA', '0' * 64):
                with self.assertRaisesRegex(ValueError, 'STATIC_SOURCE_CHANGED'):
                    self.run_small(scenario, Path(parent) / 'source')
            self.assertEqual(scenario.opens, 0)
            scenario = Scenario(code, data)
            with patch.object(indexer, 'MAX_READS', 6):
                with self.assertRaisesRegex(ValueError, 'BUDGET'):
                    self.run_small(scenario, Path(parent) / 'budget')
            self.assertEqual(scenario.opens, 1)
            clock = fixture.Clock()
            scenario = Scenario(code, data, clock=clock, delay=0.5)
            with self.assertRaisesRegex(ValueError, 'TIME_BUDGET'):
                self.run_small(scenario, Path(parent) / 'time', clock)
            self.assertEqual(scenario.opens, 1)


if __name__ == '__main__':
    unittest.main()
