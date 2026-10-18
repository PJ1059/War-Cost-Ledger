"""Read only the declared fragment reached by the actual local-peer match JE.

19A69E8 7413 reaches 19A69FD, the prior parent range end. This is a
fragment continuation, not an independent function or callable interface.
One shared 8K/32-read/2-second budget includes the 2-byte edge guard;
declared code union remains <=4K. No fallback traversal or native calls.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import time

ROOT = Path(__file__).resolve().parents[1]
REVISION = 'career_local_peer_match_fragment_v1'
EDGE_RVA, EDGE_PIN, TARGET_RVA = 0x19A69E8, '7413', 0x19A69FD
SOURCE_SHA = '68523d1281b7b8bc55c50763d3fe2e6ee56749b28aa09062245d863affdb2bdb'
SOURCE_FOLDER = ROOT / 'dist/career-local-profile-20261012-nextship/capture'
spec = importlib.util.spec_from_file_location('local_peer_match_private_session',
                                             ROOT / 'tools/hit-consumer-followup.py')
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
reader = worker.session.reader
worker.REVISION = worker.session.REVISION = reader.REVISION = REVISION
reader.TARGET_RVA, reader.TARGET_PIN = TARGET_RVA, ''
reader.SOURCE_REFERENCE = ('Actual local-peer UI entry SHA' + SOURCE_SHA
                          + ';19A69E8 shortJE7413 ->19A69FD=parent declared end; '
                          'RCX=matched roster entry, EAX=index, RSI=identity, RDI=UI child; '
                          'fragment only, role unknown, no fallback/helper traversal')
base_body_capture = worker.body_capture
edge_window = worker.window_factory((('local_peer_match_edge', EDGE_RVA, 2),))
edge_window.PINS = ((EDGE_RVA, EDGE_PIN),)


def edge_target(raw):
    if raw != bytes.fromhex(EDGE_PIN) or len(raw) != 2 or raw[0] != 0x74:
        raise ValueError('CAREER_MATCH_SHORT_JE_PIN')
    return EDGE_RVA + 2 + int.from_bytes(raw[1:], 'little', signed=True)


def verify_source():
    raw = (SOURCE_FOLDER / 'drain.bin').read_bytes()
    meta = json.loads((SOURCE_FOLDER / 'drain.json').read_text('utf8'))
    if (hashlib.sha256(raw).hexdigest() != SOURCE_SHA
            or meta.get('sha256') != SOURCE_SHA or len(raw) != 114
            or meta.get('function_begin') != 0x19A6990
            or meta.get('function_end') != TARGET_RVA
            or meta.get('source_revision') != 'career_local_peer_ui_declared_v1'
            or raw[:5] != bytes.fromhex('e8a38a0b00')):
        raise ValueError('CAREER_MATCH_SOURCE_CHANGED')
    offset = 5 + EDGE_RVA - 0x19A6990
    if edge_target(raw[offset:offset + 2]) != TARGET_RVA:
        raise ValueError('CAREER_MATCH_SOURCE_EDGE')
    return {'sha256': SOURCE_SHA, 'parent_begin': 0x19A6990,
            'parent_end': TARGET_RVA, 'edge_binary_offset': offset}


def capture(process, identity, clock=time.perf_counter, evidence=None):
    source = verify_source()
    reader.validate_module(identity)
    evidence = {} if evidence is None else evidence
    evidence.update(source_revision=REVISION, source_parent=source,
                    entry_branch='short_je_rel8', fragment_only=True,
                    native_called=False, native_written=False)
    # The outer adapter accounts every physical IO including the edge. The
    # original PE reader may create its own Budget; that never resets this one.
    budget = reader.Budget(process, identity, clock)
    try:
        prefix, edge_meta = edge_window.capture(budget, identity, sleep=lambda _: None)
        if edge_target(prefix) != TARGET_RVA:
            raise ValueError('CAREER_MATCH_TARGET_CHANGED')
        body, body_meta = base_body_capture(budget, identity, clock, evidence)
        budget.time_gate()
        body_meta['budget'] = budget.summary()
        binary = prefix + body
        meta = dict(body_meta)
        meta.update(candidate_body=dict(body_meta), source_parent=source,
                    edge_rva=EDGE_RVA, edge_pin=EDGE_PIN, edge_target_rva=TARGET_RVA,
                    entry_branch='short_je_rel8', fragment_only=True,
                    body_binary_offset=2, edge_bytes_read=2, edge_reads=1,
                    bytes_written=len(binary), binary_sha256=hashlib.sha256(binary).hexdigest(),
                    complete_stream=False, classification_ready=False,
                    logical_function_complete=False, all_sibling_fragments_captured=False,
                    pins=edge_meta['pins'])
        meta['ranges'] = edge_meta['ranges'] + [dict(r, binary_offset=r['binary_offset'] + 2)
                                               for r in body_meta['ranges']]
        meta['chunks'] = edge_meta['chunks'] + body_meta['chunks']
        return binary, meta
    finally:
        evidence['budget'] = budget.summary()


def verify_saved(meta, binary):
    if (meta.get('source_revision') != REVISION
            or meta.get('edge_rva') != EDGE_RVA or meta.get('edge_pin') != EDGE_PIN
            or meta.get('edge_target_rva') != TARGET_RVA
            or meta.get('entry_branch') != 'short_je_rel8'
            or meta.get('fragment_only') is not True or meta.get('body_binary_offset') != 2
            or meta.get('source_parent') != {'sha256': SOURCE_SHA, 'parent_begin': 0x19A6990,
                    'parent_end': TARGET_RVA, 'edge_binary_offset': 93}
            or meta.get('native_called') is not False or meta.get('native_written') is not False
            or meta.get('classification_ready') is not False
            or meta.get('logical_function_complete') is not False
            or edge_target(binary[:2]) != TARGET_RVA
            or meta.get('binary_sha256') != hashlib.sha256(binary).hexdigest()):
        raise ValueError('CAREER_MATCH_SAVED_PROFILE')
    reader.verify_saved(meta['candidate_body'], binary[2:])
    expected = [{'name': 'local_peer_match_edge', 'rva': EDGE_RVA, 'length': 2, 'binary_offset': 0}]
    expected += [dict(r, binary_offset=r['binary_offset'] + 2)
                 for r in meta['candidate_body']['ranges']]
    if meta['ranges'] != expected or meta['budget'] != meta['candidate_body']['budget']:
        raise ValueError('CAREER_MATCH_SAVED_RANGES')
    if (meta['budget']['read_calls'] > 32 or meta['budget']['query_calls'] > 32
            or meta['budget']['bytes_requested'] > 8192 or len(binary[2:]) > 4096):
        raise ValueError('CAREER_MATCH_SAVED_BUDGET')


worker.capture = worker.session.reader.capture = capture
worker.verify_saved = verify_saved

if __name__ == '__main__':
    worker.main()
