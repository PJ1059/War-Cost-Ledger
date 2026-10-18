"""One immediate Ship-only read of four observed EXE indirect-call slots.

No calls or target code reads. The frozen 110B setter is the source; current
setter prefix, before/after Ship and four qwords share 4096B/16RPM/2s soft.
The exact 469080B pinned LuaDLL file is parsed offline for public exports.
Unmapped pointers and forwarders remain unknown; no following or retries.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
REVISION = 'flow_exe_setter_four_slot_identity_v1'
SOURCE = ROOT / 'dist/flow-exe-setter-live-20261012-v1'
SOURCE_BIN_SHA = '243fa89235066e4594aad990fa80b6820cee6cbd8273b30d38eacc10ace4dda8'
SOURCE_META_SHA = '2f1472b3de0b88142ea51c8fba5c3fec02cef9cc50942aea24f9beff54051125'
LUA_PATH = Path(r'G:/SteamLibrary/steamapps/common/Helldivers 2/bin/lua51.dll')
LUA_SHA = '2c8720c9f446c848436ad993b1a88099d76f0b0b09df53689719b797c3039ce7'
LUA_FILE_SIZE = 469080
LUA_IMAGE_SIZE = 0x73000
CALLS = ((0x3F1572, 0x13F7A98), (0x3F1583, 0x13F7918),
         (0x3F1591, 0x13F7B48), (0x3F15B5, 0x13F7A50))
spec = importlib.util.spec_from_file_location(
    '_flow_exe_iat_budget', ROOT / 'tools/flow-exe-entry-code-capture.py')
flow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(flow)
# Private module only: the original sampler and its exported budget stay frozen.
flow.MAX_BYTES, flow.MAX_READS = 4096, 16


def validate_source(folder=SOURCE):
    folder = Path(folder)
    raw, meta_raw = (folder / 'setter.bin').read_bytes(), (folder / 'setter.json').read_bytes()
    if (hashlib.sha256(raw).hexdigest() != SOURCE_BIN_SHA
            or hashlib.sha256(meta_raw).hexdigest() != SOURCE_META_SHA):
        raise ValueError('FLOW_IAT_SOURCE_CHANGED')
    meta = json.loads(meta_raw)
    if (len(raw) != 110 or not meta.get('complete') or meta.get('target_module') != 'exe'
            or meta.get('fingerprint') != flow.FINGERPRINT
            or meta.get('target_rva') != flow.TARGET_RVA
            or meta.get('target_pin') != flow.TARGET_PIN
            or meta.get('ranges') != [{'name': flow.TARGET_NAME, 'module': 'exe',
                                      'rva': flow.TARGET_RVA, 'length': 110, 'binary_offset': 0}]):
        raise ValueError('FLOW_IAT_SOURCE_PROFILE')
    for call_rva, slot in CALLS:
        at = call_rva - flow.TARGET_RVA
        if (raw[at:at + 2] != b'\xff\x15'
                or call_rva + 6 + struct.unpack_from('<i', raw, at + 2)[0] != slot):
            raise ValueError('FLOW_IAT_SOURCE_CALL')
    return {'binary_path': str((folder / 'setter.bin').resolve()), 'binary_sha256': SOURCE_BIN_SHA,
            'metadata_path': str((folder / 'setter.json').resolve()), 'metadata_sha256': SOURCE_META_SHA,
            'target_module': 'exe', 'target_name': flow.TARGET_NAME,
            'target_rva': flow.TARGET_RVA, 'prefix_hex': flow.TARGET_PIN,
            'body_bytes': 110, 'body_fresh_rechecked': False}


def parse_exports(raw):
    """Pure bounded PE64 data parser: public names/RVAs only, no code decoding."""
    def unpack(fmt, at):
        size = struct.calcsize(fmt)
        if not 0 <= at < at + size <= len(raw):
            raise ValueError('FLOW_IAT_LUA_PE_BOUNDS')
        return struct.unpack_from(fmt, raw, at)
    if raw[:2] != b'MZ':
        raise ValueError('FLOW_IAT_LUA_DOS')
    pe = unpack('<I', 60)[0]
    if raw[pe:pe + 4] != b'PE\0\0' or unpack('<H', pe + 4)[0] != 0x8664:
        raise ValueError('FLOW_IAT_LUA_NT')
    section_count, optional_size = unpack('<H', pe + 6)[0], unpack('<H', pe + 20)[0]
    optional = pe + 24
    if not (0 < section_count <= 32 and optional_size >= 120
            and unpack('<H', optional)[0] == 0x20B and unpack('<I', optional + 108)[0] >= 1):
        raise ValueError('FLOW_IAT_LUA_OPTIONAL')
    image_size, header_size = unpack('<II', optional + 56)
    export_rva, export_size = unpack('<II', optional + 112)
    if not (0 < header_size <= len(raw) and 0 < export_rva < export_rva + export_size <= image_size):
        raise ValueError('FLOW_IAT_LUA_EXPORT_BOUNDS')
    sections = []
    for i in range(section_count):
        at = optional + optional_size + 40 * i
        virtual_size, rva, file_size, file_offset = unpack('<IIII', at + 8)
        flags = unpack('<I', at + 36)[0]
        if file_offset + file_size > len(raw) or rva + virtual_size > image_size:
            raise ValueError('FLOW_IAT_LUA_SECTION_BOUNDS')
        sections.append((rva, file_size, file_offset, virtual_size, flags))
    def data(rva, size):
        if not (size > 0 and 0 <= rva < rva + size <= image_size):
            raise ValueError('FLOW_IAT_LUA_RVA_BOUNDS')
        if rva + size <= header_size:
            offset = rva
        else:
            matched = [s for s in sections if s[0] <= rva < rva + size <= s[0] + s[1]]
            if len(matched) != 1:
                raise ValueError('FLOW_IAT_LUA_RVA_UNMAPPED')
            begin, _, offset, _, _ = matched[0]
            offset += rva - begin
        value = raw[offset:offset + size]
        if len(value) != size:
            raise ValueError('FLOW_IAT_LUA_SHORT_DATA')
        return value
    directory = data(export_rva, 40)
    base, function_count, name_count, functions_rva, names_rva, ordinals_rva = struct.unpack_from('<IIIIII', directory, 16)
    if not (0 < function_count <= 4096 and 0 <= name_count <= 4096):
        raise ValueError('FLOW_IAT_LUA_EXPORT_COUNT')
    functions = struct.unpack('<' + 'I' * function_count, data(functions_rva, function_count * 4))
    names = struct.unpack('<' + 'I' * name_count, data(names_rva, name_count * 4)) if name_count else ()
    ordinals = struct.unpack('<' + 'H' * name_count, data(ordinals_rva, name_count * 2)) if name_count else ()
    rows, seen = [], set()
    for name_rva, ordinal_index in zip(names, ordinals):
        if ordinal_index >= function_count:
            raise ValueError('FLOW_IAT_LUA_EXPORT_ORDINAL')
        text = bytearray()
        for i in range(96):
            value = data(name_rva + i, 1)[0]
            if value == 0:
                break
            if value < 33 or value > 126:
                raise ValueError('FLOW_IAT_LUA_EXPORT_NAME')
            text.append(value)
        else:
            raise ValueError('FLOW_IAT_LUA_EXPORT_NAME_LIMIT')
        name = text.decode('ascii')
        if not name or name in seen:
            raise ValueError('FLOW_IAT_LUA_EXPORT_NAME_DUPLICATE')
        seen.add(name)
        rva = functions[ordinal_index]
        if not 0 < rva < image_size:
            raise ValueError('FLOW_IAT_LUA_EXPORT_ADDRESS')
        forwarded = export_rva <= rva < export_rva + export_size
        executable = any(s[0] <= rva < s[0] + s[3] and s[4] & 0x20000000 for s in sections)
        rows.append({'name': name, 'rva': rva, 'ordinal': base + ordinal_index,
                     'forwarded': forwarded, 'executable_file_section': bool(executable)})
    return {'image_size': image_size, 'export_directory': {'rva': export_rva, 'size': export_size},
            'named_exports': sorted(rows, key=lambda row: row['name']),
            'name_count': name_count, 'function_count': function_count,
            'forwarder_strings_read': False, 'code_read_or_decoded': False}


def load_lua_file(path=LUA_PATH):
    path = Path(path).resolve()
    before = path.stat()
    if before.st_size != LUA_FILE_SIZE:
        raise ValueError('FLOW_IAT_LUA_FILE_SIZE')
    raw = path.read_bytes()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError('FLOW_IAT_LUA_FILE_CHANGED')
    if len(raw) != LUA_FILE_SIZE or hashlib.sha256(raw).hexdigest() != LUA_SHA:
        raise ValueError('FLOW_IAT_LUA_FILE_HASH')
    exports = parse_exports(raw)
    if exports['image_size'] != LUA_IMAGE_SIZE:
        raise ValueError('FLOW_IAT_LUA_IMAGE_SIZE')
    return {'path': str(path), 'size': after.st_size, 'mtime_ns': after.st_mtime_ns,
            'sha256': LUA_SHA, 'exports': exports, 'raw': raw}


def resolve_sources(pid, module_enumerator=None):
    if module_enumerator is None:
        from fire_code_windows import _modules
        module_enumerator = _modules
    modules = module_enumerator(pid)
    result = flow.resolve_sources(pid, lambda _: modules)
    lua = [row for row in modules if row['name'].casefold() == 'lua51.dll']
    if len(lua) != 1:
        raise FileNotFoundError('FLOW_IAT_EXPECTS_EXACT_LUA_MODULE')
    result.update(lua_base=lua[0]['base'], lua_size=lua[0]['size'], lua_path=lua[0]['path'])
    return result


def validate_identity(identity, stamps, lua, deps):
    deps['validate_identity'](identity, stamps)
    flow.validate_module(identity)
    base = identity.get('lua_base')
    if (type(base) is not int or base < 65536 or base % 4096
            or base + LUA_IMAGE_SIZE >= 0x800000000000
            or identity.get('lua_size') != LUA_IMAGE_SIZE
            or Path(identity['lua_path']).resolve() != Path(lua['path']).resolve()):
        raise ValueError('FLOW_IAT_LUA_MODULE_INVALID')
    current = Path(lua['path']).stat()
    if (current.st_size, current.st_mtime_ns) != (lua['size'], lua['mtime_ns']):
        raise ValueError('FLOW_IAT_LUA_FILE_CHANGED')


def identify(pointer, identity, exports):
    # Poison/marker and noncanonical values are never promoted to identities.
    if pointer in (0, 0xFFFFFFFFFFFFFFFF, 0xCCCCCCCCCCCCCCCC, 0xCDCDCDCDCDCDCDCD):
        return {'status': 'unknown', 'reason': 'INVALID_OR_MARKER_POINTER', 'names': []}
    base = identity['lua_base']
    if not base <= pointer < base + identity['lua_size']:
        return {'status': 'unknown', 'reason': 'OUTSIDE_PINNED_LUA_IMAGE', 'names': []}
    rva = pointer - base
    rows = [row for row in exports['named_exports'] if row['rva'] == rva]
    if not rows:
        return {'status': 'unknown', 'reason': 'NO_EXACT_PUBLIC_EXPORT', 'lua_rva': rva, 'names': []}
    if any(row['forwarded'] for row in rows):
        return {'status': 'unknown', 'reason': 'FORWARDER_NOT_FOLLOWED', 'lua_rva': rva, 'names': []}
    if not all(row['executable_file_section'] for row in rows):
        return {'status': 'unknown', 'reason': 'EXPORT_NOT_IN_EXECUTABLE_FILE_SECTION',
                'lua_rva': rva, 'names': []}
    return {'status': 'identified', 'reason': 'EXACT_PINNED_PUBLIC_EXPORT_RVA',
            'module': 'lua51.dll', 'lua_rva': rva, 'names': sorted(row['name'] for row in rows)}


def load_dependencies():
    deps = flow.load_dependencies()
    deps['resolve_game'] = resolve_sources
    return deps


def run(output, dependencies=None, clock=time.perf_counter, source=SOURCE, lua_path=LUA_PATH):
    folder = Path(output).resolve()
    if folder.exists():
        raise ValueError('FLOW_IAT_OUTPUT_EXISTS: use a new evidence folder')
    folder.mkdir(parents=True)
    evidence = {'source_revision': REVISION, 'target_module': 'exe', 'complete': False,
                'contract_ready': False, 'classification_ready': False, 'capture_attempted': False,
                'native_called': False, 'native_written': False, 'target_code_reads': 0,
                'attempts': 1, 'resolved': 0, 'rows': []}
    budget = None
    try:
        evidence['source'] = validate_source(source)
        lua = load_lua_file(lua_path)
        evidence['lua_file'] = {key: lua[key] for key in ('path', 'size', 'mtime_ns', 'sha256')}
        evidence['lua_exports'] = {'image_size': lua['exports']['image_size'],
                                   'name_count': lua['exports']['name_count'],
                                   'function_count': lua['exports']['function_count'],
                                   'export_directory': lua['exports']['export_directory']}
        deps = dependencies if dependencies is not None else load_dependencies()
        stamps = deps['fingerprints']()
        pids = tuple(deps['game_processes']())
        if len(pids) != 1:
            raise ValueError('FLOW_IAT_EXPECTS_ONE_RUNNING_GAME')
        pid = pids[0]
        identity = deps['resolve_game'](pid)
        validate_identity(identity, stamps, lua, deps)
        evidence.update(game_pid=pid, identity=identity, fingerprint=flow.FINGERPRINT)
        with deps['Process'](pid) as process:
            budget = flow.Budget(process, identity, clock)
            before = deps['ship_state'](budget, identity)
            evidence['ship_before'] = before
            if before['state'] != 3:
                raise ValueError('FLOW_IAT_EXPECTS_SHIP')
            fresh = budget.read_module(flow.TARGET_RVA, 16, 'entry_pin', True)
            evidence['fresh_pin'] = {'module': 'exe', 'rva': flow.TARGET_RVA, 'hex': fresh.hex(),
                                     'matched': fresh.hex() == flow.TARGET_PIN}
            if fresh.hex() != flow.TARGET_PIN:
                raise ValueError('FLOW_IAT_SETTER_PIN_MISMATCH')
            budget.require_capacity(32 + 12, 4 + 2)
            evidence['capture_attempted'] = True
            chunks = []
            for index, (call_rva, slot_rva) in enumerate(CALLS):
                raw = budget.read_module(slot_rva, 8, 'indirect_call_slot')
                pointer = struct.unpack('<Q', raw)[0]
                row = {'call_rva': call_rva, 'slot_module': 'exe', 'slot_rva': slot_rva,
                       'binary_offset': index * 8, 'qword_hex': raw.hex(),
                       **identify(pointer, identity, lua['exports'])}
                chunks.append(raw)
                evidence['rows'].append(row)
            after = deps['ship_state'](budget, identity)
            evidence['ship_after'] = after
            if before != after:
                raise ValueError('FLOW_IAT_SHIP_CHANGED')
            budget.time_gate()
        final = deps['resolve_game'](pid)
        validate_identity(final, stamps, lua, deps)
        if final != identity or tuple(deps['game_processes']()) != (pid,):
            raise ValueError('FLOW_IAT_MODULE_CHANGED')
        budget.time_gate()
        binary, report = folder / 'iat.bin', folder / 'iat.json'
        raw = b''.join(chunks)
        resolved = sum(row['status'] == 'identified' for row in evidence['rows'])
        evidence.update(complete=True, resolved=resolved, identity_ready=resolved == 4,
                        captured_at=datetime.now(timezone.utc).isoformat(),
                        slot_bytes=32, slot_reads=4, ship_bytes=24, ship_reads=4,
                        budget=budget.summary(), read_records=budget.records,
                        binary_path=str(binary), sha256=hashlib.sha256(raw).hexdigest(),
                        lua_file_copy=str(folder / 'lua51-source.dll'))
        binary.write_bytes(raw)
        (folder / 'lua51-source.dll').write_bytes(lua['raw'])
        (folder / 'lua-exports.json').write_text(json.dumps(lua['exports'], indent=2) + '\n', 'utf8')
        report.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', 'utf8')
        status = {'status': 'complete', 'source_revision': REVISION, 'resolved': resolved,
                  'json_path': str(report), 'binary_path': str(binary), 'sha256': evidence['sha256']}
        flow.tail['write_status'](folder, status)
        return status
    except Exception as error:
        if budget is not None:
            evidence.update(budget=budget.summary(), read_records=budget.records)
        failure = {**evidence, 'status': 'failed', 'complete': False, 'identity_ready': False,
                   'resolved': 0, 'error': str(error), 'partial_binary_saved': False,
                   'failed_at': datetime.now(timezone.utc).isoformat()}
        for row in failure['rows']:
            row.update(status='withheld', reason='SOURCE_OR_SESSION_NOT_CONFIRMED', names=[])
            row.pop('lua_rva', None)
            row.pop('module', None)
        report = folder / 'iat.incomplete.json'
        report.write_text(json.dumps(failure, ensure_ascii=False, indent=2) + '\n', 'utf8')
        flow.tail['write_status'](folder, {**failure, 'json_path': str(report)})
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
