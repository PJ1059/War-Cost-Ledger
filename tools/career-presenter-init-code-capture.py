"""One code-only followup of the proven presenter-open tail jump.

Actual14C03B0 e99b010000 ->14C0550. The target is not called; no Armory,
Career page, UI heap or account is opened/read. Its role remains a candidate.
"""
from pathlib import Path
import importlib.util
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('career_presenter_init_private',
                                             ROOT / 'tools/hit-consumer-followup.py')
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
worker.REVISION = worker.session.REVISION = worker.session.reader.REVISION = 'career_presenter_init_declared_v1'
worker.CALLER, worker.CALL_PIN, worker.CALLEE = 0x14C03B0, 'e99b010000', 0x14C0550
worker.SOURCE_SHA = '84039cf1a12eecd9aa309e5f7a649a4928567952517439de34f6e663098c4814'
worker.session.reader.TARGET_RVA, worker.session.reader.TARGET_PIN = worker.CALLEE, ''
worker.session.reader.SOURCE_REFERENCE = 'Actual PresenterManager::open SHA' + worker.SOURCE_SHA + '; tail jmp14C03B0 ->14C0550'
# The fresh branch5B/1RPM is part of the global8192B/32 budget; Ship is separate.
worker.session.reader.MAX_BYTES = 8192 - 5
worker.session.reader.MAX_READS = 32 - 1
worker.caller_window = worker.window_factory((('impact_consumer_callsite', worker.CALLER, 5),))
worker.caller_window.PINS = ((worker.CALLER, worker.CALL_PIN),)
base_capture, base_verify = worker.capture, worker.verify_saved


def capture(process, identity, clock=time.perf_counter, evidence=None):
    started, first = clock(), True
    def shared_clock():
        nonlocal first
        if first:
            first = False
            return started
        return clock()
    raw, meta = base_capture(process, identity, shared_clock, evidence)
    meta['entry_branch'] = 'jmp_rel32'
    return raw, meta


def verify_saved(meta, raw):
    if meta.get('entry_branch') != 'jmp_rel32' or raw[:5] != bytes.fromhex(worker.CALL_PIN):
        raise ValueError('CAREER_PRESENTER_INIT_BRANCH')
    base_verify(meta, raw)


worker.capture = worker.session.reader.capture = capture
worker.verify_saved = verify_saved

if __name__ == '__main__':
    worker.main()
