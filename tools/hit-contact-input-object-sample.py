"""One read-only contact input address sample, not a hit/owner/AP producer.

Known9852B caller PIN before/after. Only proven Game+3326340 global qword
locates C=global+44F7E30. Read C+28 one byte and C+E7040 exactly36B twice.
Never follow row references/pools/Actor, call/write Game or retry.32KiB/
32 read-query/2s soft includes PE/CALL/real static Title-or-Ship/context/PID/
module gates. Store both raw samples even if mutable payload differs; base
pointer/source/module changes withhold. No callback-relative timing claim.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import time

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / 'tools/hit-world-update-r14-remainder-capture.py'
WRAPPER_SHA = '8241282412067c5026de7c15e696ffba269eaf59a54d26421daf970fa32397e0'
if hashlib.sha256(WRAPPER.read_bytes()).hexdigest() != WRAPPER_SHA:
    raise ValueError('CONTACT_INPUT_FROZEN_REMAINDER_WRAPPER_CHANGED')
spec = importlib.util.spec_from_file_location('_contact_input_private_remainder', WRAPPER)
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
v1 = previous.v1
REVISION = 'contact_input_single_readonly_address_sample_v1'
PACKET = ROOT / 'dist/hit-world-update-r14-remainder-live-20261013-v1'
JSON_SHA = 'd104f8b137f5644da6a774fcc7d3283958926da6077a8f16c9b9b36aea44e83b'
BIN_SHA = 'ad362eee2ebcd08df4a557490d8b6049d9a5e84ab436e3e2e60a473d67a42b16'
ANALYSIS_SHA = '8c9c7091cd2fc4a05cbd7700f92b257f56ab07dbd36d7ab84e5b303b186cfa25'
FULL_PIN_SHA = '96db8e734d30cc117d5a4cfa01b25caf03ee02e2d32249cc5a73cc745bac28c7'
SW = previous.metadata_private.switch_private
FULL_PIN = SW.ROOT_PIN + SW.PREFIX_PIN + SW.SUFFIX_PIN + (PACKET / 'callsite.bin').read_bytes() + previous.metadata_private.SWITCH_PIN
SOURCE_RVA = 0xAB5000
GLOBAL_RVA, CONTACT_OFFSET = 0x3326340, 0x44F7E30
ENABLE_OFFSET, BLOCK_OFFSET, BLOCK_BYTES = 0x28, 0xE7040, 36
MAX_BYTES, MAX_READS, MAX_SECONDS = 32 * 1024, 32, 2.0
PARENT = ROOT / 'dist/hit-contact-parent-fragment-live-20261013-v1/parent104.bin'
PARENT_SHA = '407a416a17c2b5153b9f81e0261d63e04ac67b05ee4eb557bc493342021ff118'
GAP = ROOT / 'dist/hit-contact-parent-gap-live-20261013-v1/parent-gap168.bin'
GAP_SHA = 'bcb1016a4a899f2132cda5c6ca72629e38a02c64310a63200d320371eb11b151'
PREFIX = ROOT / 'dist/hit-owner-prefix-20261012/drain.bin'
PREFIX_SHA = '1776ae47d88e6f4dfa95d4b077709e5693f810e72284bbf05be74b08316a4b8a'
if len(FULL_PIN) != 9852 or hashlib.sha256(FULL_PIN).hexdigest() != FULL_PIN_SHA:
    raise ValueError('CONTACT_INPUT_FULL_CALLER_SOURCE_CHANGED')


def validate_source():
    source = previous.validate_source()
    meta_raw, code = (PACKET / 'callsite.json').read_bytes(), (PACKET / 'callsite.bin').read_bytes()
    analysis_raw = (PACKET / 'r14-analysis.json').read_bytes()
    if (hashlib.sha256(meta_raw).hexdigest() != JSON_SHA
            or hashlib.sha256(code).hexdigest() != BIN_SHA
            or hashlib.sha256(analysis_raw).hexdigest() != ANALYSIS_SHA):
        raise ValueError('CONTACT_INPUT_NORMAL_CFG_SOURCE_CHANGED')
    meta, analysis = json.loads(meta_raw), json.loads(analysis_raw)
    if (not meta.get('complete') or meta.get('fingerprint') != v1.frozen.profile.FINGERPRINT
            or not meta.get('remainder_before_after_match') or not meta.get('fresh_gates_verified')
            or analysis.get('status') != 'PROVED_CAPTURED_CFG_UNDER_X64_CALL_ABI'
            or not analysis.get('normal_CFG_closed') or analysis.get('issues') != []
            or analysis.get('incoming_r14_states_at_call') != ['global_context']
            or analysis.get('call_predecessors') != [0xAB5FE8]
            or not analysis.get('contact_argument_source_proven_under_normal_x64_ABI')
            or analysis.get('contact_argument_if_proved') != 'qword[GameBase+0x3326340]+0x44F7E30'):
        raise ValueError('CONTACT_INPUT_NORMAL_CFG_PROFILE')
    parent, gap, prefix = PARENT.read_bytes(), GAP.read_bytes(), PREFIX.read_bytes()
    if (hashlib.sha256(parent).hexdigest() != PARENT_SHA
            or hashlib.sha256(gap).hexdigest() != GAP_SHA
            or hashlib.sha256(prefix).hexdigest() != PREFIX_SHA
            or parent[62:65].hex() != '4c8bf9' or parent[87:91].hex() != '80792800'
            or gap[113:115].hex() != '33f6'
            or prefix[12+27:12+29].hex() != '8bc6'
            or prefix[12+54:12+61].hex() != '4139b740700e00'
            or prefix[12+76:12+80].hex() != '48c1e305'
            or prefix[12+87:12+95].hex() != '428b843b44700e00'):
        raise ValueError('CONTACT_INPUT_EXISTING_LAYOUT_SOURCE_CHANGED')
    source.update(normal_CFG_packet={'directory': str(PACKET.resolve()), 'metadata_sha256': JSON_SHA,
        'binary_sha256': BIN_SHA, 'analysis_sha256': ANALYSIS_SHA,
        'call_AB5FEF_argument_under_ordinary_x64_nonvolatile_ABI': True,
        'runtime_pointer_or_exception_paths_proven': False},
        full_caller_pin={'rva': SOURCE_RVA, 'bytes': 9852, 'sha256': FULL_PIN_SHA},
        readonly_layout_evidence={'parent104_sha256': PARENT_SHA, 'gap168_sha256': GAP_SHA,
            'owner_prefix_sha256': PREFIX_SHA, 'incoming_RCX_to_R15': {'rva': 0x13AC22E, 'hex': '4c8bf9'},
            'enable_cmp': {'rva': 0x13AC247, 'hex': '80792800', 'offset': ENABLE_OFFSET},
            'count_cmp': {'rva': 0x13AC336, 'hex': '4139b740700e00', 'offset': BLOCK_OFFSET},
            'row_stride_shift': {'rva': 0x13AC34C, 'hex': '48c1e305', 'row_stride': 32},
            'first_row_load': {'rva': 0x13AC357, 'hex': '428b843b44700e00', 'offset': BLOCK_OFFSET+4},
            'capacity_proven': False, 'damage_AP_bounce_or_peer_semantics_proven': False},
        object_sample_wrapper_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return source


def canonical_range(address, size):
    return (type(address) is int and type(size) is int and 0 < size
            and 65536 <= address < address + size < 0x800000000000)


_base_budget = previous._base_budget  # Metadata budget, not the remainder-inserting subclass.


class Budget(_base_budget):
    def __init__(self, process, identity, clock=time.perf_counter):
        super().__init__(process, identity, clock)
        v1.frozen.MAX_BYTES, v1.frozen.MAX_READS, v1.frozen.MAX_SECONDS = MAX_BYTES, MAX_READS, MAX_SECONDS
        v1.frozen.MAX_CODE_BYTES = len(FULL_PIN)
        self.object_queries = []
        self.contact_address = None

    def read(self, address, size, purpose='ship'):
        start = len(self.records)
        try:
            return super().read(address, size, purpose)
        finally:
            if purpose.startswith('contact_object_') and len(self.records) > start:
                row = self.records[-1]
                row.pop('module', None); row.pop('rva', None)
                row.update(address=address, object_offset=address-self.contact_address,
                           address_basis='proven_C_plus_fixed_offset')

    def read_object(self, offset, size, purpose):
        if (offset, size) not in ((ENABLE_OFFSET, 1), (BLOCK_OFFSET, BLOCK_BYTES)):
            raise ValueError('CONTACT_INPUT_OBJECT_SCOPE')
        address = self.contact_address + offset
        if not canonical_range(address, size):
            raise ValueError('CONTACT_INPUT_NONCANONICAL_OBJECT_RANGE')
        self.require_capacity(size)
        region = self.query(address)
        self.object_queries.append({'address': address, 'object_offset': offset, 'bytes': size, **region})
        protection = region['protect']
        if not (region['state'] == 0x1000 and region['base'] <= address
                and address+size <= region['base']+region['size']
                and not protection & 0x100 and protection & 0xFF in (2,4,8,0x20,0x40,0x80)):
            raise ValueError('CONTACT_INPUT_OBJECT_RANGE_UNREADABLE')
        return self.read(address, size, purpose)


def capture(budget, evidence):
    evidence.update(capture_purpose='ONE_READONLY_CONTACT_INPUT_ADDRESS_SAMPLE', code_only=False,
        target_rva=GLOBAL_RVA, samples_atomic=False, callback_relative_timing_proven=False,
        native_called=False, native_written=False, row_refs_followed=0, Actor_pool_reads=0,
        capacity_proven=False, hit_producer_proven=False, classification_ready=False,
        contract_ready=False, object_type_or_owner_proven=False, repeated_sampling=False,
        object_range_queries=budget.object_queries)
    # Two9852 source PINs, two8 global-base reads, two(1+36) raw snapshots,
    # and original four post gates. Nothing is proportional to count.
    budget.require_capacity(9852*2 + 8*2 + 37*2 + 4120, 12)
    if budget.query_calls + 12 > MAX_READS:
        raise ValueError('CONTACT_INPUT_POST_QUERY_RESERVATION_BUDGET')
    source_before = budget.read_module(SOURCE_RVA, len(FULL_PIN), 'full_9852_known_caller_pin', True)
    if source_before != FULL_PIN:
        raise ValueError('CONTACT_INPUT_FRESH_FULL_CALLER_PIN_CHANGED')
    base_before = budget.read_module(GLOBAL_RVA, 8, 'proven_global_context_base')
    base = struct.unpack('<Q', base_before)[0]
    contact = base + CONTACT_OFFSET
    evidence.update(global_context_base=base, contact_input_address=contact,
                    contact_input_address_derivation='qword[Game+3326340]+44F7E30')
    if not canonical_range(base, 1) or not canonical_range(contact, BLOCK_OFFSET+BLOCK_BYTES):
        raise ValueError('CONTACT_INPUT_NONCANONICAL_PROVEN_BASE')
    budget.contact_address = contact
    samples, chunks = [], []
    for i in range(2):
        enable = budget.read_object(ENABLE_OFFSET, 1, 'contact_object_enable_sample_'+str(i+1))
        block = budget.read_object(BLOCK_OFFSET, BLOCK_BYTES, 'contact_object_count_row_sample_'+str(i+1))
        count = struct.unpack_from('<I', block)[0]
        chunks.append(enable+block)
        samples.append({'sample_index': i+1, 'enable_byte': enable[0], 'count_u32': count,
            'first_row_hex': block[4:].hex(), 'count_zero': count == 0,
            'first_row_interpreted_as_hit': False,
            'first_row_status': 'count_zero_raw_only' if count == 0 else 'semantics_unproven_raw_only'})
    evidence['samples'] = samples
    base_after = budget.read_module(GLOBAL_RVA, 8, 'proven_global_context_base')
    source_after = budget.read_module(SOURCE_RVA, len(FULL_PIN), 'full_9852_known_caller_pin', True)
    if base_after != base_before or source_after != source_before:
        raise ValueError('CONTACT_INPUT_BASE_OR_CALLER_SOURCE_CHANGED_DURING_CAPTURE')
    ranges = []
    for i in range(2):
        ranges.extend([{'name':'enable_sample_'+str(i+1), 'object_offset':ENABLE_OFFSET,
            'length':1, 'binary_offset':i*37}, {'name':'count_and_raw_first_row_sample_'+str(i+1),
            'object_offset':BLOCK_OFFSET, 'length':36, 'binary_offset':i*37+1}])
    evidence.update(full_9852_source_pin_before_after_match=True, proven_global_base_before_after_match=True,
        object_ranges_readable_and_canonical=True, object_payload_identical=chunks[0]==chunks[1],
        code_bytes=0, payload_bytes=74, ranges=ranges,
        boundary_kind='only_enable_and_count_plus_first_raw32B_no_reference_following')
    return b''.join(chunks)


v1.REVISION, v1.validate_source, v1.Budget, v1.capture = REVISION, validate_source, Budget, capture


def run(output, dependencies=None, clock=time.perf_counter):
    return v1.run(output, dependencies, clock)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args=parser.parse_args()
    try:
        print(json.dumps(run(args.output), ensure_ascii=False, indent=2))
    except (OSError, ValueError) as error:
        parser.exit(1, str(error)+'\n')


if __name__=='__main__':
    main()
