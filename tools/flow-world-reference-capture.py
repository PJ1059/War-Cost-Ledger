"""One bounded Ship-only observation of the Game World's Flow reference fields.

Read only: exact EXE pins, context+10E8, Application's <=64 world pointers,
the unique matched World's 12B state-container/ref field, and optionally its
state-container first8B. Re-read the full path; changes withhold all results.
No Lua API, registry/object lookup, engine calls, other-World dereference,
waiting or retries. All process reads share4096B/32RPM/query/2s soft.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
REVISION = 'flow_game_world_reference_fields_v1'
IAT_TOOL = ROOT / 'tools/flow-exe-iat-target-capture.py'
IAT_TOOL_SHA = '6e5d6addb8d08f3333e82c4d18b9ee2b3154cc26ee4ab78090ce808e5f262860'
if hashlib.sha256(IAT_TOOL.read_bytes()).hexdigest() != IAT_TOOL_SHA:
    raise ValueError('FLOW_WORLD_FROZEN_SOURCE_CHANGED')
spec = importlib.util.spec_from_file_location('_flow_world_source_modules', IAT_TOOL)
iat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(iat)
iat.flow.MAX_BYTES, iat.flow.MAX_READS = 4096, 32
SDK = Path(r'external/HD2Runtime')
SDK_DOMAIN = SDK / 'domains/stratagem_selector.lua'
SDK_DOMAIN_SHA = 'd959cbb32cf55e4fe53956b446711eb316bdbfb3fed768938cba899c58951b95'
SDK_UI_SOUND = SDK / 'runtime/ui_sound.lua'
SDK_UI_SOUND_SHA = 'b1c6f0d5d11a5c951e992552675afd2360ca75ede06889b8a714b5c2286862bf'
WORLD_PINS = ((0x3F821F, '488b05e27f6101'), (0x3F823D, '8ba890050000'),
              (0x3F826C, '488b9098050000'), (0x3F8277, 'e804cd0000'))
CONTEXT_GLOBAL = 0x3326340
STATE_OFFSET = 0xAC21C
GAME_WORLD_OFFSET = 0x10E8
APPLICATION_GLOBAL = 0x1A10208
WORLD_COUNT_OFFSET = 0x590
WORLD_ARRAY_OFFSET = 0x598
WORLD_STATE_REF_OFFSET = 0x2301D8


def validate_sdk_source():
    records = []
    texts = []
    for path, expected in ((SDK_DOMAIN, SDK_DOMAIN_SHA), (SDK_UI_SOUND, SDK_UI_SOUND_SHA)):
        before = path.stat()
        raw = path.read_bytes()
        after = path.stat()
        if (hashlib.sha256(raw).hexdigest() != expected
                or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns)):
            raise ValueError('FLOW_WORLD_SDK_SOURCE_CHANGED')
        texts.append(raw.decode('utf8'))
        records.append({'path': str(path.resolve()), 'sha256': expected,
                        'size': after.st_size, 'mtime_ns': after.st_mtime_ns})
    domain, ui_sound = texts
    pattern = r'\{\["label"\]="([^"\n]+)",\["rva"\]=(\d+),\["hex"\]="([0-9a-f]+)",\["module"\]="([^"\n]+)"\}'
    found = {int(m[2]): {'label': m[1], 'rva': int(m[2]), 'hex': m[3], 'module': m[4]}
             for m in re.finditer(pattern, domain)}
    for rva, pin in WORLD_PINS:
        if rva not in found or found[rva]['hex'] != pin or found[rva]['module'] != 'exe':
            raise ValueError('FLOW_WORLD_SDK_PIN_SOURCE')
    required = ('["gameContext"]=53633856', '["application"]=27329032',
                '["worldCount"]=1424', '["worldArray"]=1432',
                '["uiSound"]={["context"]=53633856,["world"]=4328')
    if not all(value in domain for value in required) or 'context+U.world' not in ui_sound:
        raise ValueError('FLOW_WORLD_SDK_FIELD_SOURCE')
    return {'files': records, 'world_order_pins': [found[rva] for rva, _ in WORLD_PINS],
            'fields': {'context_global': {'module': 'game', 'rva': CONTEXT_GLOBAL,
                        'source': 'D.uiSound.context / D.slotOverlay.gameContext; existing Ship reader'},
                       'state': {'offset': STATE_OFFSET, 'source': 'existing Ship reader'},
                       'game_world': {'offset': GAME_WORLD_OFFSET, 'source': 'D.uiSound.world; runtime/ui_sound.lua M.game_world'},
                       'application': {'module': 'exe', 'rva': APPLICATION_GLOBAL, 'source': 'D.slotOverlay.application'},
                       'world_count': {'offset': WORLD_COUNT_OFFSET, 'source': 'D.slotOverlay.worldCount'},
                       'world_array': {'offset': WORLD_ARRAY_OFFSET, 'source': 'D.slotOverlay.worldArray'},
                       'state_container_ref': {'offset': WORLD_STATE_REF_OFFSET, 'bytes': 12,
                          'source': 'frozen110B World.set_flow_callback_object body; named ref/unref slots'},
                       'state_container_head': {'offset': 0, 'bytes': 8,
                          'source': 'setter3F15A6/3F15B2; raw pointer candidate only'}}}


def sdk_stats_unchanged(source):
    for record in source['files']:
        current = Path(record['path']).stat()
        if (current.st_size, current.st_mtime_ns) != (record['size'], record['mtime_ns']):
            raise ValueError('FLOW_WORLD_SDK_SOURCE_CHANGED')


def valid_pointer(value):
    return type(value) is int and 65536 <= value < 0x800000000000 and value % 8 == 0


class Budget(iat.flow.Budget):
    """Reuse counters without labeling observed heap fields as EXE RVAs."""
    def read(self, address, size, purpose='ship'):
        previous = len(self.records)
        try:
            return super().read(address, size, purpose='ship')
        finally:
            if len(self.records) > previous:
                row = self.records[-1]
                row['purpose'] = purpose
                if purpose != 'ship':
                    base = self.identity['exe_base']
                    if base <= address < address + size <= base + self.identity['exe_size']:
                        row.update(module='exe', rva=address - base)
                    else:
                        row['address_hex'] = hex(address)


def read_heap(budget, address, size, label):
    if not valid_pointer(address) or address + size >= 0x800000000000:
        raise ValueError('FLOW_WORLD_HEAP_ADDRESS_INVALID: ' + label)
    budget.require_capacity(size)
    region = budget.query(address)
    protection = region['protect']
    if not (region['state'] == 0x1000 and not protection & 0x100
            and protection & 0xFF in (2, 4, 8, 0x20, 0x40, 0x80)
            and region['base'] <= address < address + size <= region['base'] + region['size']):
        raise ValueError('FLOW_WORLD_FIELD_UNREADABLE: ' + label)
    return budget.read(address, size, label)


def qword(raw):
    return struct.unpack('<Q', raw)[0]


def read_snapshot(budget, context):
    game_world_raw = read_heap(budget, context + GAME_WORLD_OFFSET, 8, 'game_world_pointer')
    game_world = qword(game_world_raw)
    if not valid_pointer(game_world):
        raise ValueError('FLOW_WORLD_GAME_WORLD_POINTER_INVALID')
    app_raw = budget.read_module(APPLICATION_GLOBAL, 8, 'application_pointer')
    app = qword(app_raw)
    if not valid_pointer(app):
        raise ValueError('FLOW_WORLD_APPLICATION_POINTER_INVALID')
    count_raw = read_heap(budget, app + WORLD_COUNT_OFFSET, 4, 'world_count')
    count = struct.unpack('<I', count_raw)[0]
    if not 1 <= count <= 64:
        raise ValueError('FLOW_WORLD_COUNT_LIMIT')
    array_raw = read_heap(budget, app + WORLD_ARRAY_OFFSET, 8, 'world_array_pointer')
    array = qword(array_raw)
    if not valid_pointer(array):
        raise ValueError('FLOW_WORLD_ARRAY_POINTER_INVALID')
    # Read array bytes only; no other World pointers are dereferenced or queried.
    contents = read_heap(budget, array, count * 8, 'world_array_contents')
    matches = [index for index in range(count)
               if struct.unpack_from('<Q', contents, index * 8)[0] == game_world]
    if len(matches) != 1:
        raise ValueError('FLOW_WORLD_EXPECTS_UNIQUE_GAME_WORLD')
    fields = read_heap(budget, game_world + WORLD_STATE_REF_OFFSET, 12, 'world_state_container_ref')
    container, reference = struct.unpack('<Qi', fields)
    if container and not valid_pointer(container):
        raise ValueError('FLOW_WORLD_STATE_CONTAINER_INVALID')
    head = read_heap(budget, container, 8, 'state_container_head') if container else None
    old_l = qword(head) if head is not None else None
    return {'game_world': game_world, 'application': app, 'world_count': count,
            'world_array': array, 'matched_index_one_based': matches[0] + 1,
            'world_array_hex': contents.hex(), 'state_container': container, 'reference_i32': reference,
            'state_ref_hex': fields.hex(), 'state_container_head_hex': head.hex() if head is not None else None,
            'old_l_pointer_candidate': old_l,
            'old_l_candidate_status': ('pointer_shape_only' if valid_pointer(old_l) else 'null_or_invalid_or_unread'),
            'old_l_type_verified': False, 'old_l_state_status_verified': False,
            'registry_identity_verified': False, 'callback_object_observed': False,
            'other_world_fields_read': 0}


def run(output, dependencies=None, clock=time.perf_counter, lua_path=iat.LUA_PATH):
    folder = Path(output).resolve()
    if folder.exists():
        raise ValueError('FLOW_WORLD_OUTPUT_EXISTS: use a new evidence folder')
    folder.mkdir(parents=True)
    evidence = {'source_revision': REVISION, 'complete': False, 'fields_ready': False,
                'classification_ready': False, 'callback_ready': False, 'native_called': False,
                'native_written': False, 'registry_reads': 0, 'other_world_fields_read': 0,
                'attempts': 1, 'capture_attempted': False}
    budget = None
    try:
        evidence['setter_source'] = iat.validate_source()
        evidence['sdk_source'] = validate_sdk_source()
        lua = iat.load_lua_file(lua_path)
        evidence['lua_file'] = {key: lua[key] for key in ('path', 'size', 'mtime_ns', 'sha256')}
        deps = dependencies if dependencies is not None else iat.load_dependencies()
        stamps = deps['fingerprints']()
        pids = tuple(deps['game_processes']())
        if len(pids) != 1:
            raise ValueError('FLOW_WORLD_EXPECTS_ONE_RUNNING_GAME')
        pid = pids[0]
        identity = deps['resolve_game'](pid)
        iat.validate_identity(identity, stamps, lua, deps)
        evidence.update(game_pid=pid, identity=identity, fingerprint=iat.flow.FINGERPRINT)
        with deps['Process'](pid) as process:
            budget = Budget(process, identity, clock)
            before = deps['ship_state'](budget, identity)
            evidence['ship_before'] = before
            if before['state'] != 3:
                raise ValueError('FLOW_WORLD_EXPECTS_SHIP')
            evidence['pins'] = []
            for rva, pin in ((iat.flow.TARGET_RVA, iat.flow.TARGET_PIN), *WORLD_PINS):
                raw = budget.read_module(rva, len(bytes.fromhex(pin)), 'identity_pin', True)
                evidence['pins'].append({'module': 'exe', 'rva': rva, 'hex': raw.hex(), 'matched': raw.hex() == pin})
                if raw.hex() != pin:
                    raise ValueError('FLOW_WORLD_PIN_MISMATCH: ' + hex(rva))
            evidence['capture_attempted'] = True
            first = read_snapshot(budget, before['context'])
            second = read_snapshot(budget, before['context'])
            evidence['path_snapshots_match'] = first == second
            if first != second:
                raise ValueError('FLOW_WORLD_PATH_OR_FIELD_CHANGED')
            after = deps['ship_state'](budget, identity)
            evidence['ship_after'] = after
            if before != after:
                raise ValueError('FLOW_WORLD_SHIP_CHANGED')
            budget.time_gate()
        final = deps['resolve_game'](pid)
        iat.validate_identity(final, stamps, lua, deps)
        if final != identity or tuple(deps['game_processes']()) != (pid,):
            raise ValueError('FLOW_WORLD_MODULE_CHANGED')
        sdk_stats_unchanged(evidence['sdk_source'])
        budget.time_gate()
        evidence.update(complete=True, fields_ready=True, observation=first,
                        captured_at=datetime.now(timezone.utc).isoformat(),
                        budget=budget.summary(), read_records=budget.records,
                        maximum_world_array_bytes=512, path_reads_twice=True)
        report = folder / 'world-reference.json'
        report.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', 'utf8')
        status = {'status': 'complete', 'source_revision': REVISION,
                  'json_path': str(report), 'sha256': hashlib.sha256(report.read_bytes()).hexdigest()}
        iat.flow.tail['write_status'](folder, status)
        return status
    except Exception as error:
        if budget is not None:
            evidence.update(budget=budget.summary(), read_records=budget.records)
        failure = {**evidence, 'status': 'failed', 'complete': False, 'fields_ready': False,
                   'error': str(error), 'results_withheld': True,
                   'failed_at': datetime.now(timezone.utc).isoformat()}
        report = folder / 'world-reference.incomplete.json'
        report.write_text(json.dumps(failure, ensure_ascii=False, indent=2) + '\n', 'utf8')
        iat.flow.tail['write_status'](folder, {**failure, 'json_path': str(report)})
        raise


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
