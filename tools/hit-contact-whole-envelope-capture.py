"""Fixed [13AC1F0,13B0562)17266B twice, not a complete-CFG claim.

Fresh frozen84B exit metadata and only its saved UW chains, with original
PE/CALL/source/Title-or-Ship/context/PID/module pre/post gates. One private
48KiB/56RPM-query/2s profile; old defaults stay unchanged. Check every real
contained parent/gap/owner/tail fragment in the fresh body. No callee/EH/
heap/reference read or native Game invocation/write; no recursive extension.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import time

ROOT=Path(__file__).resolve().parents[1]
WRAPPER=ROOT/'tools/hit-contact-exit-metadata-capture.py'
WRAPPER_SHA='c1a00eacadc3046b424668f38387e43d4bc49605c4dc743fd2bb4d1bc26a0c6b'
if hashlib.sha256(WRAPPER.read_bytes()).hexdigest()!=WRAPPER_SHA:
    raise ValueError('CONTACT_ENVELOPE_FROZEN_METADATA_TOOL_CHANGED')
spec=importlib.util.spec_from_file_location('_contact_envelope_private_metadata',WRAPPER)
metadata_private=importlib.util.module_from_spec(spec);spec.loader.exec_module(metadata_private)
v1=metadata_private.v1
REVISION='contact_fixed_whole_candidate_envelope_v1'
PACKET=ROOT/'dist/hit-contact-exit-metadata-live-20261013-v1'
JSON_SHA='b53789a23c1dd2713c9d05565ea052d927f83f4dbe1291d26fdb353a62ad19d6'
BIN_SHA='d8e70824390969d30e74549ab91be3d966db54fe86f508f48a143f775bd95981'
METADATA_PIN=metadata_private.parent.material(PACKET/'callsite.bin',BIN_SHA,84)
BODY_BEGIN,BODY_END=0x13AC1F0,0x13B0562
BODY_BYTES=BODY_END-BODY_BEGIN
MAX_BYTES,MAX_READS,MAX_SECONDS=48*1024,56,2.0
POST_BYTES,POST_CALLS=382+84+4120,8


def validate_metadata_packet():
    meta=json.loads(metadata_private.parent.material(PACKET/'callsite.json',JSON_SHA))
    ownership=meta.get('ownership',[])
    if (not meta.get('complete') or meta.get('source_revision')!=metadata_private.REVISION
            or meta.get('fingerprint')!=v1.frozen.profile.FINGERPRINT or meta.get('sha256')!=BIN_SHA
            or not meta.get('exception_window_before_after_match')
            or not meta.get('full_known_source_pins_before_after_match')
            or not meta.get('fresh_primary_chain_verified') or not meta.get('fresh_gates_verified')
            or meta.get('unwind_chain')!=metadata_private.parent.unwind_source()
            or [row.get('target_rva') for row in ownership]!=list(metadata_private.TARGETS)
            or not all(row.get('same_contact_primary') for row in ownership)
            or [(row['declaration_begin'],row['declaration_end']) for row in ownership]
               !=[(0x13AFCD1,0x13AFD17),(0x13B053F,BODY_END)]
            or BODY_BYTES!=17266 or meta.get('ranges')!=[{'name':'contact_hot_and_next6_exception_records',
                'module':'game','rva':metadata_private.WINDOW_RVA,'length':84,'binary_offset':0}]):
        raise ValueError('CONTACT_ENVELOPE_ACTUAL_METADATA_PROFILE')
    return meta


def fragments():
    p=metadata_private.parent
    parent=p.material(p.PARENT_SOURCE,p.PARENT_SHA,104)
    gap=p.material(p.GAP_SOURCE,p.GAP_SHA,168)
    owner=p.material(p.OWNER_SOURCE,p.OWNER_SHA,4396)
    return [('parent104',0x13AC1F0,parent),('gap168',0x13AC258,gap),
            ('owner_prefix4352',0x13AC300,owner[12:4364]),
            ('owner_builder_pin7',0x13AD4A2,owner[:7]),
            ('ricochet_call_pin5',0x13AD751,owner[7:12]),
            ('consume_tail128',p.TAIL_BEGIN,metadata_private.TAIL_PIN)]


def validate_source():
    source=metadata_private.validate_source();validate_metadata_packet()
    known=fragments()
    if any(not BODY_BEGIN<=rva<rva+len(raw)<=BODY_END for _,rva,raw in known):
        raise ValueError('CONTACT_ENVELOPE_KNOWN_FRAGMENT_OUTSIDE_BODY')
    source.update(complete_exit_metadata_source={'directory':str(PACKET.resolve()),
        'metadata_sha256':JSON_SHA,'binary_sha256':BIN_SHA,'source_complete':True,
        'only_two_exit_statement_ownerships_proven':True},
        saved_body_fragments=[{'name':name,'rva':rva,'length':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
                              for name,rva,raw in known],
        excluded_saved_fragment={'name':'ricochet_entry32','rva':0x13B0BD0,'length':32,
                                 'reason':'outside_fixed_envelope_not_read'},
        whole_body_source_previously_proven=False,
        envelope_wrapper_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return source


_base_budget=v1.Budget
_metadata_capture=v1.capture


class Budget(_base_budget):
    def __init__(self,process,identity,clock=time.perf_counter):
        self.body_pending,self.body_raw,self.window_reads=True,None,0
        super().__init__(process,identity,clock)
        # Independently imported private modules only, never old files/defaults.
        v1.MAX_READS=MAX_READS
        v1.frozen.MAX_BYTES,v1.frozen.MAX_READS,v1.frozen.MAX_SECONDS=MAX_BYTES,MAX_READS,MAX_SECONDS
        v1.frozen.MAX_CODE_BYTES=BODY_BYTES
        meta=validate_metadata_packet();self.known_UW={}
        for chain in [meta['unwind_chain']]+[row['unwind_chain'] for row in meta['ownership']]:
            for node in chain:
                for key in ('header','chain_entry'):
                    if key in node:
                        raw=bytes.fromhex(node[key]['raw_hex']);self.known_UW[(node[key]['rva'],len(raw))]=raw

    def require_capacity(self,size,calls=1):
        if self.query_calls+calls+(2 if self.body_pending else 0)>MAX_READS:
            raise ValueError('CONTACT_ENVELOPE_QUERY_RESERVATION_BUDGET')
        return super().require_capacity(size+(BODY_BYTES*2 if self.body_pending else 0),
                                        calls+(2 if self.body_pending else 0))

    def read_module(self,rva,size,purpose,executable=False):
        if purpose=='exit_exception_window':
            if (rva,size)!=(metadata_private.WINDOW_RVA,84) or self.window_reads>1:
                raise ValueError('CONTACT_ENVELOPE_FIXED_METADATA_WINDOW_SCOPE')
            if self.window_reads==1:
                self.require_capacity(POST_BYTES,POST_CALLS)
                self.body_pending=False
                raw=super().read_module(BODY_BEGIN,BODY_BYTES,'fixed_contact_envelope',True)
                for name,at,pin in fragments():
                    if raw[at-BODY_BEGIN:at-BODY_BEGIN+len(pin)]!=pin:
                        raise ValueError('CONTACT_ENVELOPE_FRESH_BODY_FRAGMENT_CHANGED: '+name)
                after=super().read_module(BODY_BEGIN,BODY_BYTES,'fixed_contact_envelope',True)
                if after!=raw:raise ValueError('CONTACT_ENVELOPE_BODY_CHANGED_DURING_CAPTURE')
                self.body_raw=raw
            raw=super().read_module(rva,size,purpose,executable)
            self.window_reads+=1
            if raw!=METADATA_PIN:raise ValueError('CONTACT_ENVELOPE_FRESH_FULL_METADATA_CHANGED')
            return raw
        if purpose=='unwind_metadata' and (rva,size) not in self.known_UW:
            raise ValueError('CONTACT_ENVELOPE_UW_OUTSIDE_FROZEN_CHAINS')
        raw=super().read_module(rva,size,purpose,executable)
        if purpose=='unwind_metadata' and raw!=self.known_UW[(rva,size)]:
            raise ValueError('CONTACT_ENVELOPE_FRESH_UW_CHANGED')
        return raw


def capture(budget,evidence):
    try:_metadata_capture(budget,evidence)
    finally:
        body_records=[row for row in budget.records if row['purpose']=='fixed_contact_envelope']
        evidence.update(capture_purpose='FIXED_WHOLE_CANDIDATE_ENVELOPE_ONLY',code_only=True,
            metadata_only=False,new_code_body_reads=len(body_records),
            unknown_code_bytes_returned=sum(row.get('returned',0) for row in body_records),
            requested_envelope={'rva':BODY_BEGIN,'length':BODY_BYTES},
            logical_function_complete=False,normal_CFG_closed=False,payload_ready=False)
    meta=validate_metadata_packet()
    if (budget.body_raw is None or budget.body_pending or budget.window_reads!=2
            or evidence['ownership']!=meta['ownership']):
        raise ValueError('CONTACT_ENVELOPE_FRESH_OWNERSHIP_OR_BODY_INCOMPLETE')
    evidence.update(target_rva=BODY_BEGIN,ranges=[{'name':'contact_whole_candidate_envelope',
        'module':'game','rva':BODY_BEGIN,'length':BODY_BYTES,'binary_offset':0}],
        code_bytes=BODY_BYTES,metadata_bytes=84,new_code_body_reads=2,body_before_after_match=True,
        all_real_contained_saved_fragments_match=True,full_metadata_window_matches_frozen=True,
        saved_UW_chains_fresh_before_body=True,whole_body_source_previously_proven=False,
        excluded_ricochet_entry32_read=False,declared_code_complete=False,
        boundary_kind='fixed_candidate_envelope_not_full_CFG_or_all_fragment_ownership',
        offline_CFG_required=True,payload_ready=False,classification_ready=False,contract_ready=False)
    return budget.body_raw


v1.REVISION,v1.validate_source,v1.Budget,v1.capture=REVISION,validate_source,Budget,capture


def run(output,dependencies=None,clock=time.perf_counter):return v1.run(output,dependencies,clock)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:print(json.dumps(run(args.output),ensure_ascii=False,indent=2))
    except (OSError,ValueError) as error:parser.exit(1,str(error)+'\n')


if __name__=='__main__':main()
