"""Ship7416 one fixed RF12 and complete UW64, twice; no code/body expansion."""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import time

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('_demolition_unwind_parent',ROOT/'tools/bughole-consumer-caller-capture.py')
parent=importlib.util.module_from_spec(spec);spec.loader.exec_module(parent)
worker,reader=parent.worker,parent.reader
RF_RVA,RF_HEX,UW_RVA,UW_HEADER=0x409DA80,'a07b3f019c813f01dc615102',0x25161DC,'015d1d00'
REVISION='demolition_dispatch_complete_fixed_unwind64_v1'
worker.REVISION=worker.session.REVISION=reader.REVISION=REVISION

def capture(process,identity,clock=time.perf_counter,evidence=None):
    reader.validate_module(identity)
    budget=reader.Budget(process,identity,clock)
    rf=reader.checked_metadata_read(budget,RF_RVA,12)
    if rf.hex()!=RF_HEX:raise ValueError('DEMOLITION_DISPATCH_RF_CHANGED')
    raw=reader.checked_metadata_read(budget,UW_RVA,64)
    if raw[:4].hex()!=UW_HEADER:raise ValueError('DEMOLITION_DISPATCH_UW_HEADER_CHANGED')
    if reader.checked_metadata_read(budget,RF_RVA,12)!=rf or reader.checked_metadata_read(budget,UW_RVA,64)!=raw:
        raise ValueError('DEMOLITION_DISPATCH_METADATA_CHANGED')
    meta={'source_revision':REVISION,'complete':True,'native_called':False,'native_written':False,
          'scope':'fixed_complete_unwind_only','rf_rva':RF_RVA,'rf_hex':RF_HEX,'unwind_rva':UW_RVA,
          'unwind_header':UW_HEADER,'flags':0,'unwind_slots':29,'before_after_equal':True,
          'ranges':[{'name':'dispatch_UW64','rva':UW_RVA,'length':64,'binary_offset':0}],
          'budget':budget.summary()}
    if evidence is not None:evidence.update(meta)
    return raw,meta

worker.capture=capture
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    print(json.dumps(worker.run(p.parse_args().output),ensure_ascii=False,indent=2))
