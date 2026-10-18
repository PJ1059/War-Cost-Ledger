"""One Ship-only code capture of the helper reached by the actual 122B writer.

Fresh143C960 e84bd8ffff ->143A1B0. No UI heap or Career values are read;
the shared names in low-level metadata do not make this a damage consumer.
"""
from pathlib import Path
import importlib.util

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('career_format_helper_session',
                                           ROOT/'tools/hit-consumer-followup.py')
worker=importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
worker.REVISION=worker.session.REVISION=worker.session.reader.REVISION='career_format_storage_helper_v1'
worker.CALLER,worker.CALL_PIN,worker.CALLEE=0x143C960,'e84bd8ffff',0x143A1B0
worker.SOURCE_SHA='25ba83081af51693f651347c55770b4ebdf62af9f16f407e3d49be9933d0f796'
worker.session.reader.TARGET_RVA,worker.session.reader.TARGET_PIN=worker.CALLEE,''
worker.session.reader.SOURCE_REFERENCE='Actual UILabel writer SHA'+worker.SOURCE_SHA+';143C960 ->143A1B0'
worker.caller_window=worker.window_factory((('impact_consumer_callsite',worker.CALLER,5),))
worker.caller_window.PINS=((worker.CALLER,worker.CALL_PIN),)

if __name__=='__main__':
    worker.main()
