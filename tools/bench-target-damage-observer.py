"""Offline same-target source benchmark; only owned local-process buffers."""
import hashlib
import json
from pathlib import Path
import runpy
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
helpers = runpy.run_path(str(ROOT / 'tools/bench-stat-reader.py'))
quote, run_lua = helpers['quote'], helpers['run_lua']
runtime, dll = helpers['DEFAULT_RUNTIME'], helpers['DEFAULT_DLL']
config = '{runtime=' + quote(runtime.as_posix()) + ',observer=' + quote((ROOT / 'src/kill-observer.lua').as_posix())
config += ',trace=' + quote((ROOT / 'src/target-damage-attribution.lua').as_posix())
config += ',resolver=' + quote((ROOT / 'src/damage-source-resolver.lua').as_posix()) + ',iterations=1000}'
script = ('_BENCH=' + config + '\nreturn dofile(' + quote((ROOT / 'tests/bench_target_damage_observer.lua').as_posix()) + ')').encode('utf8')
result = run_lua(script, dll)
result.update(measured_utc=datetime.now(timezone.utc).isoformat(),
              observer_sha256=hashlib.sha256((ROOT / 'src/kill-observer.lua').read_bytes()).hexdigest(),
              trace_sha256=hashlib.sha256((ROOT / 'src/target-damage-attribution.lua').read_bytes()).hexdigest(),
              resolver_sha256=hashlib.sha256((ROOT / 'src/damage-source-resolver.lua').read_bytes()).hexdigest(),
              method='actual game LuaJIT + ReadProcessMemory over own synthetic buffers; eight living target HP changes and native contacts per poll',
              shared_fragment_context_method='16-death burst through real observer/resolver, drained within six 100ms logical polls; poll_ms/read fields are per-poll peaks; position callback reads one owned 12-byte coordinate buffer per target, not the full Runtime unit-registration lookup',
              position_callback_limit=64,
              runtime_unit_position_max_reads_per_callback=12,
              actual_fps_verified=False, game_process_read=False)
target = ROOT / 'docs/target-damage-performance.json'
target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
print(json.dumps(result, ensure_ascii=False))
