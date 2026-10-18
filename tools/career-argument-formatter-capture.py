"""One code-only Ship capture of the proven UILabel argument formatter call.

Actual143A28C e8dfd62f00 ->1737970 on the null string-input path. The callee
is not invoked, and no Career/stat/user data are read by this profile.
"""
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('career_arg_formatter_session',
                                             ROOT/'tools/hit-consumer-followup.py')
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
worker.REVISION = worker.session.REVISION = worker.session.reader.REVISION = 'career_argument_formatter_declared_v1'
worker.CALLER, worker.CALL_PIN, worker.CALLEE = 0x143A28C, 'e8dfd62f00', 0x1737970
worker.SOURCE_SHA = '2cacbe9e8dca9f0b404c05cbb9cf72ef9185871a07f8d5de343787ef903936d1'
worker.session.reader.TARGET_RVA, worker.session.reader.TARGET_PIN = worker.CALLEE, ''
worker.session.reader.SOURCE_REFERENCE = 'Actual argument storage SHA'+worker.SOURCE_SHA+';143A28C ->1737970'
worker.caller_window = worker.window_factory((('impact_consumer_callsite',worker.CALLER,5),))
worker.caller_window.PINS = ((worker.CALLER,worker.CALL_PIN),)

if __name__ == '__main__':
    worker.main()
