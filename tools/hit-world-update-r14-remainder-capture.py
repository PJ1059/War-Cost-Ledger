"""One fixed5006B continuation, AB62D6..AB7664 before known switch data.

Private new profile only:32KiB/32RPM-query/2s,12KiB declaration subbudget.
Reuse frozen metadata capture; insert exactly two body reads immediately
before its post204B window/source gates. Whole source window/UW bytes are
fresh pinned. No further target/body/callee/handler/heap, calls or writes.
Metadata ownership of only two prior targets is not ownership of later
chunks and is not CFG closure. Only offline reachable bytes may settle CFG.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / 'tools/hit-world-update-logical-metadata-capture.py'
WRAPPER_SHA = '45393bedb484106c45ae022cafa90904aea5e9e5b41d075266e061c2d725f111'
if hashlib.sha256(WRAPPER.read_bytes()).hexdigest() != WRAPPER_SHA:
    raise ValueError('R14_REMAINDER_FROZEN_METADATA_WRAPPER_CHANGED')
spec = importlib.util.spec_from_file_location('_r14_remainder_private_metadata', WRAPPER)
metadata_private = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metadata_private)
v1 = metadata_private.v1
REVISION = 'game_world_update_r14_remaining_to_switch_data_v1'
PACKET = ROOT / 'dist/hit-world-update-logical-metadata-live-20261013-v1'
PACKET_JSON_SHA = '4a69e090cfdb1c802ee15d0b48266124039ee957f7fa7cdaa3a9963d4c59f13a'
PACKET_BIN_SHA = '8faac0b1a1e4095deac343d3fd88c6b7b1fe818a8174d7a0919662d81980d027'
METADATA_PIN = (PACKET / 'callsite.bin').read_bytes()
BODY_BEGIN, BODY_END = 0xAB62D6, 0xAB7664
BODY_BYTES = BODY_END - BODY_BEGIN
MAX_BYTES, MAX_READS, MAX_SECONDS = 32 * 1024, 32, 2.0
MAX_DECLARATION_BYTES = 12 * 1024
POST_BYTES, POST_CALLS = 84 + 4000 + 738 + 24 + 204 + 4096 + 12 + 12, 9
if len(METADATA_PIN) != 204 or hashlib.sha256(METADATA_PIN).hexdigest() != PACKET_BIN_SHA:
    raise ValueError('R14_REMAINDER_COMPLETE_METADATA_BINARY_CHANGED')


def validate_metadata_packet():
    raw = (PACKET / 'callsite.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != PACKET_JSON_SHA:
        raise ValueError('R14_REMAINDER_COMPLETE_METADATA_PACKET_CHANGED')
    meta = json.loads(raw)
    ownership = meta.get('ownership', [])
    if (not meta.get('complete') or meta.get('source_revision') != metadata_private.REVISION
            or meta.get('fingerprint') != v1.frozen.profile.FINGERPRINT
            or meta.get('sha256') != PACKET_BIN_SHA
            or not meta.get('exception_window_before_after_match')
            or not meta.get('full_source_pins_before_after_match')
            or not meta.get('fresh_unwind_matches_complete_source')
            or not meta.get('fresh_gates_verified')
            or len(ownership) != 2 or not all(row.get('same_AB5000_primary') for row in ownership)
            or [row.get('target_rva') for row in ownership] != list(metadata_private.TARGETS)
            or meta.get('unwind_chain') != metadata_private.validate_switch_packet()['unwind_chain']):
        raise ValueError('R14_REMAINDER_COMPLETE_METADATA_PROFILE')
    records = meta['exception_records']
    needed = records[:7]
    if ([(row['index'], row['begin'], row['end']) for row in needed] !=
            [(43772, 0xAB5054, 0xAB62D6), (43773, 0xAB62D6, 0xAB6A65),
             (43774, 0xAB6A65, 0xAB6A7E), (43775, 0xAB6A7E, 0xAB7034),
             (43776, 0xAB7034, 0xAB761C), (43777, 0xAB761C, 0xAB767C),
             (43778, 0xAB7680, 0xAB7D84)]
            or METADATA_PIN[:12] != metadata_private.HINT.HINT_BYTES
            or BODY_BYTES != 5006 or BODY_END != metadata_private.switch_private.TABLE_RVA):
        raise ValueError('R14_REMAINDER_SOURCE_SCOPE_CHANGED')
    return meta


def validate_source():
    source = metadata_private.validate_source()
    validate_metadata_packet()
    source['complete_logical_metadata_packet'] = {'directory': str(PACKET.resolve()),
        'metadata_sha256': PACKET_JSON_SHA, 'binary_sha256': PACKET_BIN_SHA,
        'source_complete': True, 'window_rva': metadata_private.WINDOW_RVA,
        'window_bytes': 204, 'only_first_two_target_ownership_proven': True,
        'later_three_declarations_ownership_proven': False}
    source['r14_remainder_wrapper_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return source


_base_budget = v1.Budget
_metadata_capture = v1.capture


class Budget(_base_budget):
    def __init__(self, process, identity, clock=time.perf_counter):
        self.body_pending, self.body_raw, self.window_reads = True, None, 0
        super().__init__(process, identity, clock)
        # These globals belong only to this independently imported private copy.
        v1.frozen.MAX_BYTES = MAX_BYTES
        v1.frozen.MAX_READS = MAX_READS
        v1.frozen.MAX_SECONDS = MAX_SECONDS
        v1.frozen.MAX_CODE_BYTES = BODY_BYTES
        v1.frozen.MAX_DECLARATION_BYTES = MAX_DECLARATION_BYTES
        v1.frozen.DECLARATION_PURPOSES.add('r14_fixed_remainder_code')
        meta = validate_metadata_packet()
        self.known_UW = {}
        for chain in [meta['unwind_chain']] + [row['unwind_chain'] for row in meta['ownership']]:
            for node in chain:
                for key in ('header', 'chain_entry'):
                    if key in node:
                        raw = bytes.fromhex(node[key]['raw_hex'])
                        self.known_UW[(node[key]['rva'], len(raw))] = raw

    def require_capacity(self, size, calls=1):
        # Reserve both body reads throughout the original pre/metadata stage.
        if self.query_calls + calls + (2 if self.body_pending else 0) > MAX_READS:
            raise ValueError('R14_REMAINDER_QUERY_RESERVATION_BUDGET')
        return super().require_capacity(size + (2 * BODY_BYTES if self.body_pending else 0),
            calls + (2 if self.body_pending else 0))

    def read_module(self, rva, size, purpose, executable=False):
        if purpose == 'logical_exception_window':
            if (rva, size) != (metadata_private.WINDOW_RVA, 204) or self.window_reads > 1:
                raise ValueError('R14_REMAINDER_METADATA_WINDOW_SCOPE')
            if self.window_reads == 1:
                # Frozen capture reaches this call only after both finite
                # ownership walks. Insert2 fixed code reads before all post gates.
                self.require_capacity(POST_BYTES, POST_CALLS)
                if self.query_calls + POST_CALLS + 2 > MAX_READS:
                    raise ValueError('R14_REMAINDER_POST_QUERY_RESERVATION_BUDGET')
                self.body_pending = False
                raw = super().read_module(BODY_BEGIN, BODY_BYTES, 'r14_fixed_remainder_code', True)
                after = super().read_module(BODY_BEGIN, BODY_BYTES, 'r14_fixed_remainder_code', True)
                if after != raw:
                    raise ValueError('R14_REMAINDER_CODE_CHANGED_DURING_CAPTURE')
                self.body_raw = raw
            raw = super().read_module(rva, size, purpose, executable)
            self.window_reads += 1
            if raw != METADATA_PIN:
                raise ValueError('R14_REMAINDER_FRESH_FULL_METADATA_WINDOW_CHANGED')
            return raw
        if purpose == 'unwind_metadata' and (rva, size) not in self.known_UW:
            raise ValueError('R14_REMAINDER_UW_READ_NOT_IN_FROZEN_SOURCE')
        raw = super().read_module(rva, size, purpose, executable)
        if purpose == 'unwind_metadata' and raw != self.known_UW[(rva, size)]:
            raise ValueError('R14_REMAINDER_FRESH_SOURCE_UW_CHANGED')
        return raw


def capture(budget, evidence):
    try:
        _metadata_capture(budget, evidence)
    finally:
        # Even a failed post gate must report any actual body IO honestly.
        body_records = [row for row in budget.records if row['purpose'] == 'r14_fixed_remainder_code']
        evidence.update(capture_purpose='STATIC_FIXED_REMAINDER_TO_KNOWN_SWITCH_DATA_ONLY',
            code_only=True, metadata_only=False, new_code_body_reads=len(body_records),
            unknown_code_bytes_returned=sum(row.get('returned', 0) for row in body_records),
            requested_remainder={'rva': BODY_BEGIN, 'length': BODY_BYTES},
            logical_function_complete=False, normal_CFG_closed=False)
    expected = validate_metadata_packet()
    if (budget.body_raw is None or budget.body_pending or budget.window_reads != 2
            or evidence['ownership'] != expected['ownership']):
        raise ValueError('R14_REMAINDER_FRESH_OWNERSHIP_OR_BODY_INCOMPLETE')
    evidence.update(capture_purpose='STATIC_FIXED_REMAINDER_TO_KNOWN_SWITCH_DATA_ONLY',
        target_rva=BODY_BEGIN, code_only=True, metadata_only=False,
        ranges=[{'name': 'world_update_fixed_remainder_before_switch_data', 'module': 'game',
                 'rva': BODY_BEGIN, 'length': BODY_BYTES, 'binary_offset': 0}],
        code_bytes=BODY_BYTES, new_code_body_reads=2, remainder_before_after_match=True,
        full_metadata_window_matches_frozen_source=True, source_UW_matches_frozen_before_body=True,
        metadata_bytes=204, metadata_window_stored_in_JSON_only=True,
        later_three_declarations_ownership_proven=False, offline_CFG_required=True,
        normal_CFG_closed=False, logical_function_complete=False,
        classification_ready=False, contract_ready=False,
        boundary_kind='fixed_5006B_continuation_excluding_known_24B_switch_data')
    return budget.body_raw


v1.REVISION, v1.validate_source, v1.Budget, v1.capture = REVISION, validate_source, Budget, capture


def run(output, dependencies=None, clock=time.perf_counter):
    return v1.run(output, dependencies, clock)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.output), ensure_ascii=False, indent=2))
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
