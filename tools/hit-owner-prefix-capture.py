"""One fixed source-block candidate and the missing 32B ricochet entry.

Upstream gives direct hit function13AC300..13AF280; retained actual code
begins13AD400. Read only that missing prefix and the known call-target entry.
This establishes no event counts. Per read<=4096B; sourcecode only, Ship gates.
"""
from pathlib import Path
import hashlib
import importlib.util

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('owner_prefix_session',
                                            ROOT/'tools/hit-queue-consumer-code-capture.py')
session=importlib.util.module_from_spec(spec)
spec.loader.exec_module(session)
REVISION='direct_owner_prefix_and_ricochet_entry_v1'
session.REVISION=REVISION
windows=session.reader.window_capture((('owner_builder_pin',0x13AD4A2,7),
                                       ('ricochet_call_pin',0x13AD751,5),
                                       ('direct_owner_prefix_candidate',0x13AC300,0x1100),
                                       ('ricochet_missing_entry',0x13B0BD0,0x20)))
windows.REVISION=REVISION
PINS=((0x13AD4A2,'4c8d85a0010000'),(0x13AD751,'e87a340000'))
windows.PINS=PINS


def capture(process,identity,clock=None,evidence=None):
    # Read the two exact PIN ranges first and stop before candidate bodies on mismatch.
    prefix_session=session.reader.window_capture(windows.RANGES[:2])
    prefix_session.PINS=PINS
    pins,pin_meta=prefix_session.capture(process,identity,sleep=lambda _:None)
    body_session=session.reader.window_capture(windows.RANGES[2:])
    body_session.PINS=()
    body,body_meta=body_session.capture(process,identity,sleep=lambda _:None)
    binary=pins+body
    meta=dict(body_meta,source_revision=REVISION,complete=True,code_only=True,
              candidate_only=True,classification_ready=False,complete_stream=False,
              logical_function_complete=False,body_binary_offset=12,
              source_prefix_rva=0x13AC300,source_prefix_length=0x1100,
              ricochet_entry_rva=0x13B0BD0,ricochet_entry_offset=12+0x1100,
              ricochet_entry_length=32,bytes_written=len(binary),
              binary_sha256=hashlib.sha256(binary).hexdigest())
    meta['ranges']=pin_meta['ranges']+[dict(r,binary_offset=r['binary_offset']+12)
                                     for r in body_meta['ranges']]
    meta['chunks']=pin_meta['chunks']+body_meta['chunks']
    meta['pins']=pin_meta['pins']
    meta['budget']={'bytes_requested':len(binary),'read_calls':len(meta['chunks']),
                    'per_read_limit':4096}
    return binary,meta


session.reader.capture=capture

if __name__=='__main__':
    session.main()
