"""One Ship-only read of the actual direct contact's final damage producer.

Actual13AD88B e8a004efff ->129DD30 occurs after the projectile force override.
Read only its declared range/bounded ancestry; no contacts, native call or hook.
"""
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('damage_producer_session',
                                             ROOT/'tools/hit-consumer-followup.py')
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
worker.REVISION = worker.session.REVISION = worker.session.reader.REVISION = 'direct_damage_producer_declared_v1'
worker.CALLER, worker.CALL_PIN, worker.CALLEE = 0x13AD88B, 'e8a004efff', 0x129DD30
worker.SOURCE_SHA = 'c062eb498383dd15c9e4c22bdc2668eda732db8e737cf8bee11b7f97076408e4'
worker.session.reader.TARGET_RVA, worker.session.reader.TARGET_PIN = worker.CALLEE, ''
worker.session.reader.SOURCE_REFERENCE = 'Actual direct contact SHA'+worker.SOURCE_SHA+';13AD88B ->129DD30'
worker.caller_window = worker.window_factory((('impact_consumer_callsite',worker.CALLER,5),))
worker.caller_window.PINS = ((worker.CALLER,worker.CALL_PIN),)

if __name__ == '__main__':
    worker.main()
