"""Offline293B stored-function CFG/arguments only; never follow its helpers."""
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,'external/hd2-fire-analysis-deps')
from capstone import Cs,CS_ARCH_X86,CS_MODE_64,CS_GRP_JUMP,CS_GRP_RET
from capstone.x86 import X86_OP_IMM,X86_OP_MEM
SOURCE=ROOT/'dist/career-tab-callback-body-live-20261013-v1'
OUTPUT=ROOT/'dist/career-tab-callback-body-analysis-20261013-v1'
BIN_SHA='8e60a2604a3e4e73daaac70fb2b09b086fe210676a89700f713b09ecf38a092a'
JSON_SHA='94ffff08d57cde9a0ef500934c97d7b0b87fb038c225922e59d5ee0d959a1d4c'
BEGIN,END=0x17A9630,0x17A9755


def main():
    raw=(SOURCE/'body.bin').read_bytes();report=(SOURCE/'body.json').read_bytes();m=json.loads(report)
    if (hashlib.sha256(raw).hexdigest()!=BIN_SHA or hashlib.sha256(report).hexdigest()!=JSON_SHA
            or len(raw)!=293 or not m.get('complete') or not m.get('body_before_after_match')
            or not m.get('parent_RF_UW_before_after_match') or not m.get('fresh_gates_verified')
            or (m.get('function_begin'),m.get('function_end'))!=(BEGIN,END)):
        raise ValueError('OFFLINE_CALLBACK_BODY_SOURCE_PROFILE')
    md=Cs(CS_ARCH_X86,CS_MODE_64);md.detail=True
    ins=list(md.disasm(raw,BEGIN));by_pc={i.address:i for i in ins}
    if sum(i.size for i in ins)!=293:raise ValueError('OFFLINE_CALLBACK_BODY_DECODE_GAP')
    edges=[];external=[];calls=[];writes=[];successors={}
    for i in ins:
        nxt=i.address+i.size;targets=[]
        if i.group(CS_GRP_RET):pass
        elif i.group(CS_GRP_JUMP):
            if i.operands[0].type!=X86_OP_IMM:raise ValueError('OFFLINE_CALLBACK_INDIRECT_JUMP')
            targets.append(i.operands[0].imm)
            if i.mnemonic!='jmp':targets.append(nxt)
        else:targets.append(nxt)
        successors[i.address]=[]
        for target in targets:
            if target in by_pc:edges.append([i.address,target]);successors[i.address].append(target)
            else:external.append({'pc':i.address,'target':target,'asm':i.mnemonic+' '+i.op_str})
        if i.mnemonic=='call':calls.append({'pc':i.address,'target':i.operands[0].imm,'bytes':i.bytes.hex()})
        if i.mnemonic=='mov'and i.operands[0].type==X86_OP_MEM:
            writes.append({'pc':i.address,'asm':i.mnemonic+' '+i.op_str,'displacement':i.operands[0].mem.disp})
    reachable=set();queue=[BEGIN]
    while queue:
        pc=queue.pop()
        if pc in reachable:continue
        reachable.add(pc);queue.extend(successors[pc])
    result={'source_BIN_SHA256':BIN_SHA,'source_JSON_SHA256':JSON_SHA,'begin':BEGIN,'end':END,
        'bytes':293,'decoded_instruction_count':len(ins),'all_bytes_decoded':True,
        'reachable_instructions_under_normal_CALL_return':len(reachable),'instruction_edges':edges,
        'external_tail_edges_not_followed':external,'direct_calls_not_followed':calls,
        'normal_CFG_closed_within_saved_body':not external,
        'normal_return_sites':[i.address for i in ins if i.group(CS_GRP_RET)],'memory_mov_writes':writes,
        'current_index_E06C_written_in_this_body':any(i.operands and i.operands[0].type==X86_OP_MEM
            and i.operands[0].mem.disp==0xE06C and i.mnemonic not in ('cmp','test')for i in ins),
        'visible_entry_argument_read':{'RCX':'saved RBX; bar fields E08C,E08D,E084,E088',
            'RDX_R8_R9_entry_values_read_before_first_helper':False,
            'helper_may_consume_unproven_extra_arguments':True},
        'visible_notifications':[{'pc':0x17A9639,'field':0xE08C,'value':1},
            {'pc':0x17A973B,'field':0xE084,'bytes':8,'value':'new two-f32 packed value'}],
        'sender_status':'UNKNOWN_EXTERNAL_HELPER_NOT_FOLLOWED','normal_tab_request_proven':False,
        'notification_semantic_name_proven':False,
        'unique_missing_helper_contract':{'source_RVA':0x17A9640,'source_pin':'e89b2d0000','target_RVA':0x17AC3E0,
            'RCX':'same entry bar pointer','RDX_R8_R9_and_stack_arguments':'unknown',
            'full_signature_and_behavior_proven':False},
        'conditional_tail_contract':{'source_RVA':0x17A974A,'source_pin':'e9612d0000','target_RVA':0x17AC4B0,
            'RCX':'same bar','EDX':0,'condition':'cached two-f32 differ, including unordered comparisons',
            'helper_not_followed':True},
        'Game_accessed':False,'native_called':False,'new_heap_or_callee_reads':0}
    OUTPUT.mkdir(parents=True,exist_ok=True)
    (OUTPUT/'17A9630.asm').write_text('\n'.join(f'{i.address:08X} {i.bytes.hex():32} {i.mnemonic} {i.op_str}'for i in ins)+'\n','utf8')
    (OUTPUT/'analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf8')
    print(json.dumps({k:result[k]for k in ('decoded_instruction_count','reachable_instructions_under_normal_CALL_return',
        'current_index_E06C_written_in_this_body','external_tail_edges_not_followed','unique_missing_helper_contract')},indent=2))

if __name__=='__main__':main()
