"""Offline performance measurement; reads only this process's synthetic buffers."""
import hashlib
import json
from pathlib import Path
import runpy
from datetime import datetime, timezone
from build import ROOT

helpers = runpy.run_path(str(ROOT / 'tools/bench-stat-reader.py'))
quote, run_lua = helpers['quote'], helpers['run_lua']
runtime, dll = helpers['DEFAULT_RUNTIME'], helpers['DEFAULT_DLL']
config = '{runtime=' + quote(runtime.as_posix()) + ',observer=' + quote((ROOT / 'src/kill-observer.lua').as_posix()) + ',iterations=2000}'
script = ('_BENCH=' + config + '\nreturn dofile(' + quote((ROOT / 'tests/bench_kill_observer.lua').as_posix()) + ')').encode('utf8')
result = run_lua(script, dll)
result.update({'measured_utc': datetime.now(timezone.utc).isoformat(), 'lua_dll': str(dll),
               'observer_sha256': hashlib.sha256((ROOT / 'src/kill-observer.lua').read_bytes()).hexdigest(),
               'method': 'game LuaJIT + ReadProcessMemory of owned synthetic living-actor buffers',
               'game_running': False, 'actual_fps_verified': False,
               'excludes': ['game rendering', 'other MOD contention', 'real network attribution', 'storage',
                            'new actor burst', 'corpse burst', 'pending attribution candidates']})
target = ROOT / 'docs/kill-observer-performance.json'
target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
print(json.dumps(result, ensure_ascii=False))
