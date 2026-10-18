"""Only the three new regions: owned RW same-input RtlVirtualUnwind(0).

The frozen old runner's memory/CONTEXT/API/free path is reused without editing
it. Its19RF array/count becomes28RF. Frame/World/contact PC lists stay empty;
only AP843 / dispatcher216 instruction bytes / physical1552 are tested. No
Game, copied instruction execution, handlers, RX pages or table registration.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
FROZEN=Path(__file__).with_name('hit_world_contact_unwind_parity_owned.py')
FROZEN_SHA='96a1b093371c8e63fb16a225d623de24b01ababd70edb20278cb12cae7731026'
MAPPER=Path(__file__).with_name('hit_world_contact_ap_physical_unwind_copy.py')
MAPPER_SHA='dd62aeaa10fbd1ce61a250bdbbb2c7130c69bdf52065540e5a3812cf276655f1'
CODE=Path(__file__).with_name('hit_world_contact_ap_physical_code_copy.py')
CODE_SHA='cc0beb9bc908b181cd66e40164b231810eb7008be3adffc031b3903a629c4bbd'
OLD_REPORT=ROOT/'dist/hit-unwind-parity-owned-20261013-v1/report.json'
OLD_REPORT_SHA='b7bd925f5ab822689a56ad5d201c7c3e049d4787f89ca9b2f00602f4b5c2532a'
for path,digest in ((FROZEN,FROZEN_SHA),(MAPPER,MAPPER_SHA),(CODE,CODE_SHA),(OLD_REPORT,OLD_REPORT_SHA)):
    if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('NEW_PARITY_FROZEN_SOURCE_CHANGED:'+path.name)
spec=importlib.util.spec_from_file_location('_new_parity_old_private',FROZEN)
frozen=importlib.util.module_from_spec(spec);spec.loader.exec_module(frozen)
spec=importlib.util.spec_from_file_location('_new_parity_six_mapper_private',MAPPER)
mapper=importlib.util.module_from_spec(spec);spec.loader.exec_module(mapper)
TEST_REGIONS=('ap','dispatcher','physical')
NOT_RETESTED=('frame','world','contact')
COPY_RVAS={'frame':0x10000000,'world':0x10001000,'contact':0x10004000,
           'ap':0x10009000,'dispatcher':0x1000A000,'physical':0x1000B000}


def load_pcs(code_source):
    md=mapper.code_copy.capstone.Cs(mapper.code_copy.capstone.CS_ARCH_X86,mapper.code_copy.capstone.CS_MODE_64)
    pcs={name:[]for name in mapper.code_copy.REGIONS};evidence=[]
    for name in TEST_REGIONS:
        begin,_,length=mapper.code_copy.REGIONS[name]
        code=code_source[name][:length];instructions=list(md.disasm(code,begin));cursor=begin
        for ins in instructions:
            offset=ins.address-begin
            if ins.address!=cursor or ins.size<1 or ins.bytes!=code[offset:offset+ins.size]:
                raise ValueError('NEW_PARITY_INSTRUCTION_BYTES_OR_BOUNDARY:'+name)
            cursor+=ins.size
        if not instructions or cursor!=begin+length:raise ValueError('NEW_PARITY_INCOMPLETE_DECODE:'+name)
        pcs[name]=[i.address for i in instructions]
        evidence.append({'region':name,'code_rva':begin,'instruction_bytes':length,
            'instruction_boundary_count':len(instructions),'code_sha256':hashlib.sha256(code).hexdigest(),
            'normal_CFG_closed_proven':False,'only_saved_code_bytes_decoded':True})
    return pcs,evidence


# Exactly these fixed literal substitutions parameterize the old run function;
# no memory, CONTEXT, native API, comparison, firstdiff or cleanup code changes.
PATCHES=[('RuntimeFunction * 19','RuntimeFunction * mapper.RF_COUNT',2),
         ("report['runtime_function_count'] = 19","report['runtime_function_count'] = mapper.RF_COUNT",1),
         ('owned_RW_same_input_RtlVirtualUnwind_parity_v1','owned_new_AP_dispatcher_physical_RW_unwind_parity_v1',1),
         ('One identical synthetic stack/CONTEXT at every saved normal-CFG PC; not actual Game frames.',
          'One identical synthetic stack/CONTEXT at each new saved linear instruction boundary; not Game frames or normal-CFG proof.',1),
         ('all_saved_reachable_PCs_tested','all_new_saved_instruction_boundaries_tested',2)]
run_source=inspect.getsource(frozen.run)
for old,new,count in PATCHES:
    if run_source.count(old)!=count:raise ValueError('NEW_PARITY_FIXED_PATCH_CONTRACT:'+old)
    run_source=run_source.replace(old,new)
frozen.mapper=mapper;frozen.COPY_RVAS=COPY_RVAS;frozen.load_pcs=load_pcs
exec(compile(run_source,str(FROZEN)+'#new-regions-only','exec'),frozen.__dict__)


def run():
    report=frozen.run()
    report.update(wrapper_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        frozen_runner_sha256=FROZEN_SHA,six_region_mapper_sha256=MAPPER_SHA,
        six_region_code_mapper_sha256=CODE_SHA,only_new_regions_tested=list(TEST_REGIONS),
        old_three_regions_not_retested=list(NOT_RETESTED),
        old_three_region_parity_reference={'path':str(OLD_REPORT),'sha256':OLD_REPORT_SHA},
        linear_decode_is_not_normal_CFG_proof=True)
    return report
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args();report=run();args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'status':report['status'],'tested_PC_counts':report['tested_PC_counts'],
        'RtlVirtualUnwind_calls':report['RtlVirtualUnwind_calls'],'differences':report['differences'],
        'owned_allocations_released':report['owned_allocations_released'],'report':str(args.report)}))
    raise SystemExit(0 if report['status']=='PASS'else 1)
if __name__=='__main__':main()
