"""Read only the actual Armory Career-block initializer call, never invoke it."""
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('career_panel_init_private',
                                             ROOT / 'tools/career-presenter-init-code-capture.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
worker = probe.worker
worker.REVISION = worker.session.REVISION = worker.session.reader.REVISION = 'career_panel_init_declared_v1'
worker.CALLER, worker.CALL_PIN, worker.CALLEE = 0x1456529, 'e872774900', 0x18EDCA0
worker.SOURCE_SHA = '4ab9fe08c4d409637872f9f6926b73a0906ad8d53292023bd32c1100a7990257'
worker.session.reader.TARGET_RVA = worker.CALLEE
worker.session.reader.SOURCE_REFERENCE = (
    'Actual Armory view initializer SHA' + worker.SOURCE_SHA + ';1456529 ->18EDCA0; '
    'RCX=actual Armory+4DAF8; knownCareer panel4DC08=block+110; registeredkind224; no call/Stats getter claim')
worker.caller_window = worker.window_factory((('impact_consumer_callsite', worker.CALLER, 5),))
worker.caller_window.PINS = ((worker.CALLER, worker.CALL_PIN),)
old_capture = worker.capture

def capture(*args, **kwargs):
    raw, meta = old_capture(*args, **kwargs)
    meta['entry_branch'] = 'call_rel32'
    return raw, meta

def verify_saved(meta, raw):
    if meta.get('entry_branch') != 'call_rel32':
        raise ValueError('CAREER_PANEL_INIT_BRANCH')
    probe.base_verify(meta, raw)

worker.capture = worker.session.reader.capture = capture
worker.verify_saved = verify_saved

if __name__ == '__main__':
    worker.main()
