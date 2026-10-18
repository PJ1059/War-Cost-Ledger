"""Read only the actual shared-row constructor: metadata/label/callback initialization, no call."""
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('career_row_constructor_private',
                                             ROOT / 'tools/career-presenter-init-code-capture.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
worker = probe.worker
worker.REVISION = worker.session.REVISION = worker.session.reader.REVISION = 'career_row_constructor_declared_v1'
worker.CALLER, worker.CALL_PIN, worker.CALLEE = 0x18E58C1, 'e85adaffff', 0x18E3320
worker.SOURCE_SHA = '0b32a1a11119f7cb16f4761d2e6cf65ae97aba181bac646de24ef528378a3056'
worker.session.reader.TARGET_RVA = worker.CALLEE
worker.session.reader.SOURCE_REFERENCE = (
    'Actual shared panel/list initializer SHA' + worker.SOURCE_SHA + ';18E58C1 ->18E3320; '
    'RCX=actual row, prior layout-only characterization unproven; onlymetadata18FC/1900,taglabelsource,callbackwrites; no geometry-helper traversal')
worker.caller_window = worker.window_factory((('impact_consumer_callsite', worker.CALLER, 5),))
worker.caller_window.PINS = ((worker.CALLER, worker.CALL_PIN),)
old_capture = worker.capture

def capture(*args, **kwargs):
    raw, meta = old_capture(*args, **kwargs)
    meta['entry_branch'] = 'call_rel32'
    return raw, meta

def verify_saved(meta, raw):
    if meta.get('entry_branch') != 'call_rel32':
        raise ValueError('CAREER_ROW_CONSTRUCTOR_BRANCH')
    probe.base_verify(meta, raw)

worker.capture = worker.session.reader.capture = capture
worker.verify_saved = verify_saved

if __name__ == '__main__':
    worker.main()
