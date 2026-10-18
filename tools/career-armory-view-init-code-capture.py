"""Read only the actual Armory-object view initializer call, never invoke it."""
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('career_armory_view_init_private',
                                             ROOT / 'tools/career-presenter-init-code-capture.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
worker = probe.worker
worker.REVISION = worker.session.REVISION = worker.session.reader.REVISION = 'career_armory_view_init_declared_v1'
worker.CALLER, worker.CALL_PIN, worker.CALLEE = 0x1455A34, 'e8f7010000', 0x1455C30
worker.SOURCE_SHA = '0b60ac9427b42b76feaed6c9d1abea397d9e40857f68532f74c200f9ce22219a'
worker.session.reader.TARGET_RVA = worker.CALLEE
worker.session.reader.SOURCE_REFERENCE = (
    'Actual Armory enter SHA' + worker.SOURCE_SHA + ';1455A34 ->1455C30; '
    'RCX=[[347CE38]+60] actual Armory object; outparam+38/90/94/98 untyped, no call/Stats getter claim')
worker.caller_window = worker.window_factory((('impact_consumer_callsite', worker.CALLER, 5),))
worker.caller_window.PINS = ((worker.CALLER, worker.CALL_PIN),)
old_capture = worker.capture

def capture(*args, **kwargs):
    raw, meta = old_capture(*args, **kwargs)
    meta['entry_branch'] = 'call_rel32'
    return raw, meta

def verify_saved(meta, raw):
    if meta.get('entry_branch') != 'call_rel32':
        raise ValueError('CAREER_ARMORY_VIEW_INIT_BRANCH')
    probe.base_verify(meta, raw)

worker.capture = worker.session.reader.capture = capture
worker.verify_saved = verify_saved

if __name__ == '__main__':
    worker.main()
