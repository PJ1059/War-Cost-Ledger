"""Read the proven screen2 selector dispatch call, without invoking it."""
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('career_screen_selector_private',
                                             ROOT / 'tools/career-presenter-init-code-capture.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
worker = probe.worker
worker.REVISION = worker.session.REVISION = worker.session.reader.REVISION = 'career_screen_selector_declared_v1'
worker.CALLER, worker.CALL_PIN, worker.CALLEE = 0x149544E, 'e82d000000', 0x1495480
worker.SOURCE_SHA = '23e5f12987e910a192e38fcf92bba619ac8695fff6495cc6e67209cae8622ffd'
worker.session.reader.TARGET_RVA = worker.CALLEE
worker.session.reader.SOURCE_REFERENCE = (
    'Actual screen enter completed dispatch SHA' + worker.SOURCE_SHA + ';149544E ->1495480; '
    'RCX=RDX=screen stack owner [347CE38], R8=extra, R9D=screen2; onlycase2/object path, no Stats getter claim')
worker.caller_window = worker.window_factory((('impact_consumer_callsite', worker.CALLER, 5),))
worker.caller_window.PINS = ((worker.CALLER, worker.CALL_PIN),)
old_capture = worker.capture

def capture(*args, **kwargs):
    raw, meta = old_capture(*args, **kwargs)
    meta['entry_branch'] = 'call_rel32'
    return raw, meta

def verify_saved(meta, raw):
    if meta.get('entry_branch') != 'call_rel32':
        raise ValueError('CAREER_SCREEN_SELECTOR_BRANCH')
    probe.base_verify(meta, raw)

worker.capture = worker.session.reader.capture = capture
worker.verify_saved = verify_saved

if __name__ == '__main__':
    worker.main()
