"""Read screen2's last initialization dispatch call, without invoking it."""
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('career_screen_enter_private',
                                             ROOT / 'tools/career-presenter-init-code-capture.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
worker = probe.worker
worker.REVISION = worker.session.REVISION = worker.session.reader.REVISION = 'career_screen_enter_declared_v1'
worker.CALLER, worker.CALL_PIN, worker.CALLEE = 0x1438264, 'e8f7d00500', 0x1495360
worker.SOURCE_SHA = 'de186c67b79039ea62ce0948a3b7d3bec11233f0dd9f9d9f0c788096aa32a805'
worker.session.reader.TARGET_RVA = worker.CALLEE
worker.session.reader.SOURCE_REFERENCE = (
    'Actual screen2 dispatch SHA' + worker.SOURCE_SHA + ';1438264 ->1495360; '
    'RCX=RDX=screen stack owner [347CE38], R8=original extra; no Stats getter claim')
worker.caller_window = worker.window_factory((('impact_consumer_callsite', worker.CALLER, 5),))
worker.caller_window.PINS = ((worker.CALLER, worker.CALL_PIN),)
old_capture = worker.capture

def capture(*args, **kwargs):
    raw, meta = old_capture(*args, **kwargs)
    meta['entry_branch'] = 'call_rel32'
    return raw, meta

def verify_saved(meta, raw):
    if meta.get('entry_branch') != 'call_rel32':
        raise ValueError('CAREER_SCREEN_ENTER_BRANCH')
    probe.base_verify(meta, raw)

worker.capture = worker.session.reader.capture = capture
worker.verify_saved = verify_saved

if __name__ == '__main__':
    worker.main()
