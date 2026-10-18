"""Read only the actual Career panel/list initializer call, never invoke it."""
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('career_panel_list_init_private',
                                             ROOT / 'tools/career-presenter-init-code-capture.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
worker = probe.worker
worker.REVISION = worker.session.REVISION = worker.session.reader.REVISION = 'career_panel_list_init_declared_v1'
worker.CALLER, worker.CALL_PIN, worker.CALLEE = 0x18EDDCA, 'e8e174ffff', 0x18E52B0
worker.SOURCE_SHA = '390516011461495dd7e09f4e106c980c00df00861385a47299d3fef6d7babcff'
worker.session.reader.TARGET_RVA = worker.CALLEE
worker.session.reader.SOURCE_REFERENCE = (
    'Actual Career block initializer SHA' + worker.SOURCE_SHA + ';18EDDCA ->18E52B0; '
    'RCX=actual Armory+4DC08 (Career block+110), RDX/R8/R9 geometry; no call/Stats getter claim')
worker.caller_window = worker.window_factory((('impact_consumer_callsite', worker.CALLER, 5),))
worker.caller_window.PINS = ((worker.CALLER, worker.CALL_PIN),)
old_capture = worker.capture

def capture(*args, **kwargs):
    raw, meta = old_capture(*args, **kwargs)
    meta['entry_branch'] = 'call_rel32'
    return raw, meta

def verify_saved(meta, raw):
    if meta.get('entry_branch') != 'call_rel32':
        raise ValueError('CAREER_PANEL_LIST_INIT_BRANCH')
    probe.base_verify(meta, raw)

worker.capture = worker.session.reader.capture = capture
worker.verify_saved = verify_saved

if __name__ == '__main__':
    worker.main()
