"""Measure stat readers in the game's LuaJIT, reading only our own synthetic buffers."""
from __future__ import annotations

import argparse
import ctypes as c
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME = Path(os.environ.get(
    'HD2_RUNTIME_SOURCE',
    r'external/HD2Runtime'))
DEFAULT_DLL = Path(os.environ.get(
    'HD2_LUA51_DLL', r'G:\SteamLibrary\steamapps\common\Helldivers 2\bin\lua51.dll'))


def quote(value: str) -> str:
    return '"' + ''.join('\\%03d' % byte for byte in value.encode('utf8')) + '"'


def run_lua(script: bytes, dll_path: Path) -> dict:
    dll = c.CDLL(str(dll_path))
    dll.luaL_newstate.restype = c.c_void_p
    dll.luaL_openlibs.argtypes = [c.c_void_p]
    dll.luaL_loadbuffer.argtypes = [c.c_void_p, c.c_char_p, c.c_size_t, c.c_char_p]
    dll.lua_pcall.argtypes = [c.c_void_p, c.c_int, c.c_int, c.c_int]
    dll.lua_tolstring.argtypes = [c.c_void_p, c.c_int, c.c_void_p]
    dll.lua_tolstring.restype = c.c_char_p
    dll.lua_close.argtypes = [c.c_void_p]
    state = dll.luaL_newstate()
    if not state:
        raise RuntimeError('Could not create LuaJIT state')
    try:
        dll.luaL_openlibs(state)
        status = dll.luaL_loadbuffer(state, script, len(script), b'=stat_reader_benchmark')
        if status == 0:
            status = dll.lua_pcall(state, 0, 1, 0)
        value = dll.lua_tolstring(state, -1, None)
        message = value.decode('utf8', errors='replace') if value else '<no result>'
        if status:
            raise RuntimeError(message)
        return json.loads(message)
    finally:
        dll.lua_close(state)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument('--lua-dll', type=Path, default=DEFAULT_DLL)
    parser.add_argument('--reader', type=Path, default=ROOT / 'src/native-stats.lua')
    parser.add_argument('--iterations', type=int, default=2000)
    parser.add_argument('--warmup', type=int, default=300)
    parser.add_argument('--baseline-only', action='store_true')
    parser.add_argument('--capture-cost', action='store_true',
                        help='Measure snapshot, production JSON encoding and real temporary file writes instead of reader-only cases')
    parser.add_argument('--capture-format', choices=['json', 'binary', 'both'], default='json')
    parser.add_argument('--capture-iterations', type=int, default=100)
    parser.add_argument('--capture-warmup', type=int, default=10)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if not args.capture_cost and (args.iterations < 1000 or args.warmup < 200):
        parser.error('Use at least 1000 measured iterations and 200 warmup iterations')
    if args.capture_cost and (args.capture_iterations < 100 or args.capture_warmup < 10):
        parser.error('Use at least 100 measured capture iterations and 10 warmup iterations')
    if args.capture_cost and args.baseline_only:
        parser.error('--capture-cost requires the new reader')
    report_path = args.report or ROOT / ('docs/probe-capture-performance.json' if args.capture_cost
                                        else 'docs/performance-baseline.json')
    runtime = args.runtime.resolve()
    dll = args.lua_dll.resolve()
    reader = args.reader.resolve()
    for path in (dll, runtime / 'runtime/event_world.lua', ROOT / 'tests/bench_stat_reader.lua'):
        if not path.is_file():
            parser.error('Missing required file: ' + str(path))
    if not args.baseline_only and not reader.is_file():
        parser.error('New reader missing; use --baseline-only while it is being developed')
    def measure(capture_dir: Path | None = None) -> dict:
        config = '{runtime_root=' + quote(runtime.as_posix())
        config += ',reader=' + quote(reader.as_posix())
        config += ',iterations=' + str(args.capture_iterations if args.capture_cost else args.iterations)
        config += ',warmup=' + str(args.capture_warmup if args.capture_cost else args.warmup)
        config += ',include_new=' + ('false' if args.baseline_only else 'true')
        config += ',capture_cost=' + ('true' if args.capture_cost else 'false')
        config += ',capture_format=' + quote(args.capture_format)
        if capture_dir is not None:
            config += ',capture_dir=' + quote(capture_dir.as_posix())
        config += '}'
        script = ('_BENCH=' + config + '\nreturn dofile('
                  + quote((ROOT / 'tests/bench_stat_reader.lua').as_posix()) + ')').encode('utf8')
        return run_lua(script, dll)

    if args.capture_cost:
        # Only this generated directory is owned by the benchmark. Lua must remove
        # every capture/pending file, and TemporaryDirectory also cleans up failures.
        with tempfile.TemporaryDirectory(prefix='hd2-probe-capture-bench-') as name:
            capture_dir = Path(name).resolve()
            report = measure(capture_dir)
            leftovers = list(capture_dir.iterdir())
            if leftovers:
                raise RuntimeError('Benchmark did not clean up its capture files: ' + str(leftovers))
            report['temporary_files_cleaned'] = True
    else:
        report = measure()
    report.update({
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'benchmark_kind': ('synthetic_self_process_probe_capture_with_real_files' if args.capture_cost
                           else 'synthetic_self_process_ReadProcessMemory_microbenchmark'),
        'game_started': False,
        'game_fps_measured': False,
        'environment': {'os': platform.platform(), 'python': platform.python_version(),
                        'logical_cpus': os.cpu_count(), 'lua_dll': str(dll), 'lua_dll_sha256': sha(dll)},
        'runtime_commit': 'dcd996daca2573443956c07252c55c2d86dd0320',
        'source_sha256': {str(path): sha(path) for path in (
            runtime / 'runtime/event_world.lua', runtime / 'runtime/native_view.lua',
            runtime / 'runtime/windows_readonly.lua', ROOT / 'tests/bench_stat_reader.lua',
            *(() if args.baseline_only else (reader,)),
            *((runtime / 'runtime/mod_store.lua',) if args.capture_cost else ()))},
        'limitations': [
            'Synthetic stable, fully populated buffers in this benchmark process; no game process was opened.',
            'Uses real Runtime ReadProcessMemory, native_view and production reader code; excludes world.open build proofs.',
            ('Includes production mod_store JSON encoding and real write/close/rename to OS temporary files; '
             'excludes request file reading/decoding/removal, code-range captures, lazy module initialization and logging.'
             if args.capture_cost else
             'No rendering, other mods, gameplay contention, asynchronous changes, storage writes or FPS measurement.'),
            *(['Binary cases use the production raw reader and wire layout; small position/state metadata is synthetic, excluding the optional avatar/position native lookup.',
               'Warm filesystem cache, repeated writes in a temporary directory, no fsync; antivirus and real gameplay contention may alter stalls.',
               'These are single-capture timing distributions, not live FPS measurements; averaging across the sampling interval hides individual frame stalls.']
              if args.capture_cost else []),
            'Per-call QPC samples include timing and instrumentation overhead; no overhead subtraction.',
            'LuaJIT enabled, normal garbage collection, OS scheduling and fixed case order can affect tails.',
        ],
    })
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    for case in report['cases']:
        print(f"{case['name']}: avg {case['avg_us']:.2f} us; p95 {case['p95_us']:.2f}; "
              f"p99 {case['p99_us']:.2f}; {case['read_calls_per_poll']:g} reads; "
              f"{case['read_bytes_per_poll']:g} bytes")
        if args.capture_cost:
            print(f"  {case['capture_bytes']['avg']:g} {case['capture_format']} bytes; "
                  f"snapshot {case['stages']['snapshot']['avg_us']:.2f} us; "
                  f"encode {case['stages']['encode']['avg_us']:.2f} us; "
                  f"write/close/rename {case['stages']['file_write']['avg_us']:.2f} us")
    print('Report: ' + str(report_path.resolve()))
    print('Synthetic capture cost with warm temporary files; live FPS is not measured.' if args.capture_cost
          else 'Synthetic reader cost only; live game FPS is not measured.')


if __name__ == '__main__':
    main()
