"""Run the production Career reader in an owned Lua VM with external read-only IO.

No Game Lua injection, remote calls, UI actions, writes, or account access.
The fixed production reader determines every address. One capture is limited to
160 ReadProcessMemory calls / 32 KiB, including the fixed local-peer handshake.
"""
from __future__ import annotations

import argparse
import ctypes as c
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import struct
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('career_panel_live_parent', ROOT / 'tools/career-parent-snapshot.py')
parent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parent)
MAX_READS, MAX_BYTES = 160, 32768
REVISION = 'production_career_reader_external_vm_v1'
RUNTIME = Path(r'external/HD2Runtime')
LUA = Path(os.environ.get('HD2_LUA51_DLL', r'G:/SteamLibrary/steamapps/common/Helldivers 2/bin/lua51.dll'))


def quote(value):
    return '"' + ''.join('\\%03d' % b for b in str(value).replace('\\', '/').encode('utf8')) + '"'


class ReadBudget:
    def __init__(self, process):
        self.process, self.records, self.reads, self.bytes, self.queries = process, [], 0, 0, 0
        self.phase = 'peer'

    def read(self, address, size):
        if (type(address) is not int or type(size) is not int or not 65536 <= address
                or address + size >= 0x800000000000 or not 0 < size <= 4096):
            raise ValueError('CAREER_PANEL_LIVE_READ_ADDRESS')
        if self.reads >= MAX_READS or self.bytes + size > MAX_BYTES:
            raise ValueError('CAREER_PANEL_LIVE_READ_BUDGET')
        record = {'phase': self.phase, 'address': address, 'length': size}
        self.records.append(record)
        try:
            self.queries += 1
            region = self.process.query(address)
            protect = region['protect']
            if (region['state'] != 0x1000 or protect & 0x100
                    or protect & 0xff not in (2, 4, 8, 0x20, 0x40, 0x80)
                    or not region['base'] <= address < address + size <= region['base'] + region['size']):
                record['region'] = region
                raise ValueError('CAREER_PANEL_LIVE_UNREADABLE')
            self.reads += 1
            self.bytes += size
            raw = self.process.read(address, size)
            if not isinstance(raw, bytes) or len(raw) != size:
                raise ValueError('CAREER_PANEL_LIVE_SHORT_READ')
            record['raw_hex'] = raw.hex()
            return raw
        except Exception as error:
            record['error'] = str(error)
            raise


def run_reader(read, game, peer, *, source=None, runtime=RUNTIME, dll_path=LUA, frozen_clock=False):
    """Execute the unchanged reader using a C closure owned by this Python process."""
    source = Path(source or ROOT / 'src/native-career-panel-reader.lua').resolve()
    dll = c.CDLL(str(dll_path))
    state_type = c.c_void_p
    callback_type = c.CFUNCTYPE(c.c_int, state_type)
    signatures = {
        'luaL_newstate': ([], state_type), 'luaL_openlibs': ([state_type], None),
        'lua_close': ([state_type], None),
        'luaL_loadbuffer': ([state_type, c.c_char_p, c.c_size_t, c.c_char_p], c.c_int),
        'lua_pcall': ([state_type, c.c_int, c.c_int, c.c_int], c.c_int),
        'lua_tonumber': ([state_type, c.c_int], c.c_double),
        'lua_tolstring': ([state_type, c.c_int, c.POINTER(c.c_size_t)], c.c_void_p),
        'lua_pushlstring': ([state_type, c.c_char_p, c.c_size_t], None),
        'lua_pushnil': ([state_type], None),
        'lua_pushcclosure': ([state_type, callback_type, c.c_int], None),
        'lua_setfield': ([state_type, c.c_int, c.c_char_p], None),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(dll, name);function.argtypes, function.restype = arguments, result

    @callback_type
    def memory_read(state):
        # Never call lua_error across the ctypes callback boundary (longjmp).
        # Return nil/error and let the ordinary Lua wrapper raise safely.
        try:
            address, size = dll.lua_tonumber(state, 1), dll.lua_tonumber(state, 2)
            if not math.isfinite(address) or not math.isfinite(size) or address % 1 or size % 1:
                raise ValueError('CAREER_PANEL_LIVE_CALLBACK_ARGUMENT')
            raw = read(int(address), int(size))
            dll.lua_pushlstring(state, raw, len(raw));return 1
        except Exception as error:
            reason = str(error).encode('utf8', errors='replace')[:512]
            dll.lua_pushnil(state);dll.lua_pushlstring(state, reason, len(reason));return 2

    clock = '{clock=function()return 0 end}' if frozen_clock else '{}'
    script = '\n'.join([
        'table.insert(package.loaders,2,function(name) if name:sub(1,11)=="hd2runtime/" then '
        'return assert(loadfile(' + quote(Path(runtime).resolve()) + '.."/"..name:sub(12)..".lua"))end end)',
        'local JSON=require("hd2runtime/runtime/mod_store")',
        'local M=dofile(' + quote(source) + ')',
        'local reader=M.new(' + clock + ')',
        'local world={game=' + str(game) + ',runtime={mode="live"},view={read=function(at,n)'
        'local raw,why=__career_read(at,n);if raw==nil then error(why,0)end;return raw end}}',
        'local ok,value,why=pcall(reader.read,reader,world,' + quote(peer) + ')',
        'return JSON.encode({reader_call_ok=ok,snapshot=ok and value or nil,'
        'reason=ok and why or tostring(value),diagnostics=reader.diagnostics})',
    ]).encode('utf8')
    state = dll.luaL_newstate()
    if not state:
        raise ValueError('CAREER_PANEL_LIVE_LUA_STATE')
    started = time.perf_counter()
    try:
        dll.luaL_openlibs(state)
        dll.lua_pushcclosure(state, memory_read, 0)
        dll.lua_setfield(state, -10002, b'__career_read')
        status = dll.luaL_loadbuffer(state, script, len(script), b'=career_panel_external_readonly')
        if status == 0:
            status = dll.lua_pcall(state, 0, 1, 0)
        length = c.c_size_t()
        value = dll.lua_tolstring(state, -1, c.byref(length))
        raw = c.string_at(value, length.value) if value else b''
        if status:
            raise ValueError('CAREER_PANEL_LIVE_LUA: ' + raw.decode('utf8', errors='replace'))
        result = json.loads(raw)
        result.update(clock_policy='frozen_diagnostic_only' if frozen_clock else 'production_os_clock_external_vm',
                      external_elapsed_ms=(time.perf_counter() - started) * 1000)
        return result
    finally:
        dll.lua_close(state)


def capture(process, identity, *, source=None, runtime=RUNTIME, dll_path=LUA, retry_timeout=True):
    budget = ReadBudget(process)
    result = {'source_revision': REVISION, 'identity': identity, 'attempts': [],
              'account_modified': False, 'native_written': False, 'native_called': False,
              'Game_lua_injected': False, 'atomic': False,
              'limits': {'reads': MAX_READS, 'bytes': MAX_BYTES, 'max_single_read': 4096}}
    try:
        game = identity['game_base']
        user = struct.unpack('<Q', budget.read(game + 0x347CEF0, 8))[0]
        if not parent.layout.pointer(user):
            raise ValueError('CAREER_PANEL_LIVE_LOCAL_USER')
        raw_peer = budget.read(user + 0xB398, 8)
        peer = raw_peer[::-1].hex().upper()
        if peer == '0000000000000000':
            raise ValueError('CAREER_PANEL_LIVE_LOCAL_PEER')
        result['local_peer'] = peer
        budget.phase = 'production_reader'
        first = run_reader(budget.read, game, peer, source=source, runtime=runtime, dll_path=dll_path)
        result['attempts'].append(first)
        # ctypes/ReadProcessMemory costs differ from in-game calls. Retain the
        # genuine timeout, then optionally complete the same fixed read plan
        # with a frozen diagnostic clock; never label that as production pass.
        if retry_timeout and 'CAREER_PANEL_TIME_BUDGET' in first.get('reason', ''):
            budget.phase = 'timeout_geometry_diagnostic'
            result['attempts'].append(run_reader(budget.read, game, peer, source=source,
                runtime=runtime, dll_path=dll_path, frozen_clock=True))
        result['status'] = 'complete'
    except Exception as error:
        result.update(status='failed', error=str(error))
    result.update(active_read_calls=budget.reads, active_read_bytes=budget.bytes,
                  active_query_calls=budget.queries, read_records=budget.records)
    return result


def run(folder, *, pid=None, deps=None, source=None, runtime=RUNTIME, dll_path=LUA):
    folder = Path(folder).resolve()
    if folder.exists():
        raise ValueError('CAREER_PANEL_LIVE_OUTPUT_EXISTS')
    folder.mkdir(parents=True)
    result = {'source_revision': REVISION, 'status': 'failed', 'account_modified': False,
              'native_written': False, 'native_called': False}
    try:
        deps = parent.layout.dependencies() if deps is None else deps
        stamps = deps['fingerprints']()
        pids = tuple(deps['game_processes']())
        if len(pids) != 1 or pid is not None and pids != (pid,):
            raise ValueError('CAREER_PANEL_LIVE_EXPECTS_ONE_GAME_PID')
        pid = pids[0];identity = deps['resolve_game'](pid)
        deps['validate_identity'](identity, stamps)
        if identity['game_size'] != parent.layout.IMAGE_SIZE or identity['game_base'] % 4096:
            raise ValueError('CAREER_PANEL_LIVE_MODULE')
        source = Path(source or ROOT / 'src/native-career-panel-reader.lua').resolve()
        source_before = source.read_bytes()
        (folder / 'reader-source.lua').write_bytes(source_before)
        with deps['Process'](pid) as process:
            result = capture(process, identity, source=source, runtime=runtime, dll_path=dll_path)
        result.update(game_pid=pid, captured_at=datetime.now(timezone.utc).isoformat(),
                      reader_source_path=str(source), reader_source_sha256=hashlib.sha256(source_before).hexdigest())
        final = deps['resolve_game'](pid);deps['validate_identity'](final, stamps)
        if final != identity or tuple(deps['game_processes']()) != (pid,) or source.read_bytes() != source_before:
            raise ValueError('CAREER_PANEL_LIVE_IDENTITY_CHANGED')
    except Exception as error:
        result.update(status='failed', error=str(error))
    path = folder / 'career-panel-reader.json'
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    brief = {key: value for key, value in result.items() if key not in ('read_records', 'identity', 'attempts')}
    brief['attempts'] = [{key: value for key, value in item.items() if key != 'snapshot'} for item in result.get('attempts', [])]
    brief.update(json_path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    (folder / 'status.json').write_text(json.dumps(brief, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--pid', type=int)
    parser.add_argument('--runtime', type=Path, default=RUNTIME)
    parser.add_argument('--lua51-dll', type=Path, default=LUA)
    parser.add_argument('--reader', type=Path, default=ROOT / 'src/native-career-panel-reader.lua')
    args = parser.parse_args()
    result = run(args.output, pid=args.pid, runtime=args.runtime, dll_path=args.lua51_dll, source=args.reader)
    print(json.dumps({key: result[key] for key in ('status', 'game_pid', 'active_read_calls', 'active_read_bytes', 'error') if key in result}))
    if result['status'] != 'complete':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
