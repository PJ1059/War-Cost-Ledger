"""One Ship-only code capture of the actual source identity constructor call.

Actual owner prefix13AD2E9 e8223fefff ->12A1210. This reads no live hits.
It does not modify the game, account, original readers or production MOD.
"""
from pathlib import Path
import importlib.util

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('hit_source_constructor_session',
                                           ROOT/'tools/hit-consumer-followup.py')
worker=importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
worker.REVISION=worker.session.REVISION=worker.session.reader.REVISION='hit_source_constructor_declared_v1'
worker.CALLER,worker.CALL_PIN,worker.CALLEE=0x13AD2E9,'e8223fefff',0x12A1210
worker.SOURCE_SHA='1776ae47d88e6f4dfa95d4b077709e5693f810e72284bbf05be74b08316a4b8a'
worker.session.reader.TARGET_RVA,worker.session.reader.TARGET_PIN=worker.CALLEE,''
worker.session.reader.SOURCE_REFERENCE='Actual direct owner prefix SHA'+worker.SOURCE_SHA+';13AD2E9 ->12A1210'
worker.caller_window=worker.window_factory((('impact_consumer_callsite',worker.CALLER,5),))
worker.caller_window.PINS=((worker.CALLER,worker.CALL_PIN),)

if __name__=='__main__':
    worker.main()
