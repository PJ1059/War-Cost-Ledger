"""Wait outside Codex, then run each bounded read-only interface capture in order."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PLAN = (('recon', 'recon_chat_code_capture.py'), ('status', 'status-code-capture.py'),
        ('hits', 'hit-code-capture.py'))


def run(runner=subprocess.run, folder=None):
    folder = folder or ROOT / 'dist/interface-code-capture'
    folder.mkdir(parents=True, exist_ok=True)
    state = {'status': 'running', 'samplers': [], 'native_called': False, 'native_written': False,
             'code_only': True, 'concurrent_samplers': 1, 'timeout_seconds': None}
    def save():
        state['updated_at'] = datetime.now(timezone.utc).isoformat()
        (folder / 'status.json').write_text(json.dumps(state, indent=2), encoding='utf8')
    save()
    for name, filename in PLAN:
        state['current'] = name
        save()
        with (folder / (name + '.log')).open('w', encoding='utf8') as log:
            result = runner([sys.executable, str(ROOT / 'tools' / filename)], cwd=ROOT,
                            stdout=log, stderr=subprocess.STDOUT,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                            | getattr(subprocess, 'BELOW_NORMAL_PRIORITY_CLASS', 0))
        state['samplers'].append({'name': name, 'exit_code': result.returncode,
                                  'log': str(folder / (name + '.log'))})
        save()
    state['current'] = None
    state['status'] = 'finished' if all(p['exit_code'] == 0 for p in state['samplers']) else 'finished_with_gaps'
    save()
    return 0 if state['status'] == 'finished' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    raise SystemExit(run())
