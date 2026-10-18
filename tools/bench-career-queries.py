"""Measure retained-career queries in the actual LuaJIT over synthetic data only."""
from pathlib import Path
import argparse
from datetime import datetime, timezone
import hashlib
import json
import runpy

ROOT = Path(__file__).resolve().parents[1]
helpers = runpy.run_path(str(ROOT / 'tools/bench-stat-reader.py'))
quote, run_lua = helpers['quote'], helpers['run_lua']
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--report', type=Path, default=ROOT / 'dist/career-query-performance-0.4.57.json')
args = parser.parse_args()
config = '{combat=' + quote((ROOT / 'src/combat-records.lua').as_posix())
config += ',summary=' + quote((ROOT / 'src/career-history-summary.lua').as_posix()) + '}'
script = ('_BENCH=' + config + '\nreturn dofile(' + quote((ROOT / 'tests/bench_career_queries.lua').as_posix()) + ')').encode('utf8')
result = run_lua(script, helpers['DEFAULT_DLL'])
result.update(measured_utc=datetime.now(timezone.utc).isoformat(),
              combat_sha256=hashlib.sha256((ROOT / 'src/combat-records.lua').read_bytes()).hexdigest(),
              summary_sha256=hashlib.sha256((ROOT / 'src/career-history-summary.lua').read_bytes()).hexdigest(),
              method='Actual game LuaJIT, QueryPerformanceCounter, synthetic 500-match retained archive; no game process or account writes',
              actual_game_frame_time_verified=False)
args.report.parent.mkdir(parents=True, exist_ok=True)
args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
print(json.dumps(result, ensure_ascii=False))
