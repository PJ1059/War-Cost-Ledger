"""One read-only snapshot of the fixed child inside each proven chat row.

The prior live snapshot proves all 64 rows are containers, each child=row+110.
This reads only that fixed composite range. Unknown label values stay raw.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import struct
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('_recon_chat_child_reader', ROOT / 'tools/recon-chat-row-descriptor-snapshot.py')
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)
SOURCE = Path(os.environ.get('HD2_RESEARCH_FIXTURES_ROOT', str(ROOT/'dist')))/'recon-chat-row-descriptors-ship-20261013-v2/rows.json'
SOURCE_SHA = '137c3cd5d14780efe9594db5e75fcf9eaf7b787e5f528b3444dfa5344e64a2b4'
CHILD_SOURCE = Path(os.environ.get('HD2_RESEARCH_FIXTURES_ROOT', str(ROOT/'dist')))/'recon-chat-row-child-descriptors-ship-20261013-v1/rows.json'
CHILD_SOURCE_SHA = 'eec89b8a3323c0921fb3b7bdfd73df60bdf1644763bfd9c712de44d5f25a2af6'
LOCALE_SOURCE = Path(os.environ.get('HD2_RESEARCH_FIXTURES_ROOT', str(ROOT/'dist')))/'mod-research/task-layout/full-ui-20261011/strings/0x353194c702a3c234.strings.json'
LOCALE_SHA = '77102338e1a47417a4eb2ea3f01da991e409530a406daa8cef074135cc13e876'
CHILD, COMPOSITE_BYTES, ROW_PARENT = 0x110, 889, 0x330
# Chat's observed localized child is kind 8. Career's currently observed rows
# are kind 7; they cannot supply the type gate for a different native control.
LOCALIZED_CHILD_KIND = 8
REVISION = 'recon_chat_fixed_child_descriptors_v3_kind8'
SNAPSHOT_SECONDS = 1.5


def source():
    raw = SOURCE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA:
        raise ValueError('RECON_CHAT_CHILD_SOURCE_CHANGED')
    evidence = json.loads(raw)
    if len(evidence['rows']) != 64:
        raise ValueError('RECON_CHAT_CHILD_SOURCE_COUNT')
    for i, row in enumerate(evidence['rows']):
        at = evidence['chat'] + reader.ROW_BASE + i * reader.ROW_STRIDE
        header = bytes.fromhex(row['header_hex'])
        who = reader.identity(header)
        child, nxt = struct.unpack_from('<QQ', header, 0xE0)
        if (row['index'] != i or row['address'] != at or who['kind'] != 1
            or who['parent'] != evidence['chat'] + ROW_PARENT
            or who['context'] != evidence['chat_identity']['context']
            or child != at + CHILD or nxt != (at + reader.ROW_STRIDE if i < 63 else 0)):
            raise ValueError('RECON_CHAT_CHILD_SOURCE_LAYOUT')
    raw = CHILD_SOURCE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != CHILD_SOURCE_SHA:
        raise ValueError('RECON_CHAT_LOCALIZED_CHILD_SOURCE_CHANGED')
    observed = json.loads(raw)
    if len(observed['rows']) != 64:
        raise ValueError('RECON_CHAT_LOCALIZED_CHILD_SOURCE_COUNT')
    for row in observed['rows']:
        raw = bytes.fromhex(row['composite_hex'])
        if (reader.identity(raw[CHILD:CHILD + 256]) != row['identity']
            or row['identity']['kind'] != LOCALIZED_CHILD_KIND
            or row['identity']['parent'] != row['container']
            or row['identity']['context'] != observed['chat_identity']['context']
            or struct.unpack_from('<I', raw, CHILD + 272)[0] != 0x14DCC78A
            or raw[CHILD + 272 + 344] != 0):
            raise ValueError('RECON_CHAT_LOCALIZED_CHILD_SOURCE_LAYOUT')
    raw = LOCALE_SOURCE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != LOCALE_SHA:
        raise ValueError('RECON_CHAT_CHILD_LOCALE_SOURCE_CHANGED')
    if [r['Value'] for r in json.loads(raw)['Items'] if r['Key'] == 0x14DCC78A] != ['#NAME加入任务']:
        raise ValueError('RECON_CHAT_CHILD_LOCALE_BINDING')
    return reader.sources()


def snapshot(process, module, clock=time.perf_counter, name_probe=None):
    profile, pins = source()
    layout = reader.layout
    # Same fixed 61,918B / 209-read plan. External Windows reads can incur
    # scheduler delay during combat; this changes wall time, never read scope.
    budget = layout.Budget(process, module, clock, seconds=SNAPSHOT_SECONDS)
    for rva, pin in tuple((p['rva'], p['hex']) for p in profile['pins'][:2]) + pins + layout.PINS:
        if budget.read(module['game_base'] + rva, len(bytes.fromhex(pin)), image=True, code=True) != bytes.fromhex(pin):
            raise ValueError('RECON_CHAT_DESCRIPTOR_CODE_PIN_CHANGED')
    state = budget.ptr(module['game_base'] + layout.STATE_GLOBAL, image=True)
    if not layout.pointer(state):
        raise ValueError('RECON_CHAT_STATE_POINTER')
    mode = budget.u32(state + layout.STATE_OFFSET)
    if mode not in (3, 4):
        raise ValueError('RECON_CHAT_EXPECTS_SHIP_OR_MISSION')
    hud = budget.ptr(module['game_base'] + profile['hud'], image=True)
    if not layout.pointer(hud):
        raise ValueError('RECON_CHAT_HUD_POINTER')
    chat = hud + profile['widget']
    root = budget.read(chat, 256)
    root_id = reader.identity(root)
    if root_id['kind'] != 1 or not layout.pointer(root_id['parent']) or not layout.pointer(root_id['context']):
        raise ValueError('RECON_CHAT_ROOT_IDENTITY')
    if name_probe is not None:
        name_probe.start(budget)
    rows = []
    for i in range(reader.ROW_COUNT):
        at = chat + reader.ROW_BASE + i * reader.ROW_STRIDE
        raw = budget.read(at, COMPOSITE_BYTES)
        parent = reader.identity(raw[:256])
        child, nxt = struct.unpack_from('<QQ', raw, 0xE0)
        if (parent['kind'] != 1 or parent['parent'] != chat + ROW_PARENT
            or parent['context'] != root_id['context'] or child != at + CHILD
            or nxt != (at + reader.ROW_STRIDE if i < 63 else 0)):
            raise ValueError('RECON_CHAT_CHILD_RELATION_CHANGED')
        child_header = raw[CHILD:CHILD + 256]
        who = reader.identity(child_header)
        row = {'index': i, 'container': at, 'address': child, 'container_identity': parent,
               'identity': who, 'header_hex': child_header.hex(), 'composite_hex': raw.hex()}
        if who['kind'] == LOCALIZED_CHILD_KIND and who['parent'] == at and who['context'] == root_id['context']:
            label = raw[CHILD + 272:CHILD + 272 + 345]
            row.update(descriptor=reader.descriptor(label), descriptor_hex=label.hex())
        else:
            row['reason'] = 'not_proven_direct_text_child'
        if name_probe is not None:
            name_probe.before_identity(budget, row)
        # 52B includes parent child/next/parent/context and child's 4B kind.
        # 16B includes child's parent/context. 3 reads/row; 957B/row total.
        relation = budget.read(at + 0xE0, 52)
        child_identity = budget.read(child + 0xF0, 16)
        if relation != raw[0xE0:0xE0 + 52] or child_identity != child_header[0xF0:0x100]:
            raise ValueError('RECON_CHAT_CHILD_IDENTITY_CHANGED')
        row['identity_stable'] = True
        if name_probe is not None:
            name_probe.after_identity(budget, row)
        rows.append(row)
    if name_probe is not None:
        name_probe.finish(budget)
    if (budget.ptr(module['game_base'] + profile['hud'], image=True) != hud
        or reader.identity(budget.read(chat, 256)) != root_id
        or budget.ptr(module['game_base'] + layout.STATE_GLOBAL, image=True) != state
        or budget.u32(state + layout.STATE_OFFSET) != mode):
        raise ValueError('RECON_CHAT_CONTEXT_CHANGED')
    return {'status': 'complete', 'source_revision': REVISION, 'mode': mode, 'hud': hud, 'chat': chat,
            'chat_identity': root_id, 'rows': rows, 'read_records': budget.total['records'],
            'read_calls': budget.reads, 'read_bytes': budget.bytes,
            'elapsed_ms': (clock() - budget.started) * 1000, 'discovery_keys': list(reader.DISCOVERY_KEYS),
            'source_sha256': reader.SOURCE_SHA, 'locator_sha256': reader.PROFILE_SHA,
            'child_layout_source_sha256': SOURCE_SHA, 'localized_child_source_sha256': CHILD_SOURCE_SHA,
            'discovery_events_emitted': 0,
            'string_pointers_followed': 0, 'native_called': False, 'native_written': False, 'atomic': False}


reader.snapshot = snapshot
if __name__ == '__main__':
    source()
    reader.main()
