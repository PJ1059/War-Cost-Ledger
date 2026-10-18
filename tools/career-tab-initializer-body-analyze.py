"""Offline CFG and literal arguments of the sole captured 17A9820 declaration.

No imported capture runner, native API, object heap, callee or handler execution.
CALL edges assume normal return; exception and external callee behavior unknown.
"""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,'external/hd2-fire-analysis-deps')
from capstone import Cs,CS_ARCH_X86,CS_MODE_64,CS_GRP_JUMP,CS_GRP_RET
from capstone.x86 import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP

BEGIN,END=0x17A9820,0x17AA47B
SOURCE=ROOT/'dist/career-tab-initializer-body-live-20261013-v1'
SHA='194a0e58ed04345c2b278f771bcd7328dde5f03b7158c4ee5bf736615ff82d13'
OUTPUT=ROOT/'dist/career-tab-initializer-body-analysis-20261013-v1'


def main():
    raw=(SOURCE/'body.bin').read_bytes();m=json.loads((SOURCE/'body.json').read_text('utf8'))
    if (hashlib.sha256(raw).hexdigest()!=SHA or len(raw)!=END-BEGIN
            or not m.get('complete') or not m.get('body_before_after_match')
            or not m.get('parent_RF_UW_before_after_match') or not m.get('fresh_gates_verified')
            or (m.get('function_begin'),m.get('function_end'))!=(BEGIN,END)):
        raise ValueError('OFFLINE_TAB_BODY_SOURCE_PROFILE')
    md=Cs(CS_ARCH_X86,CS_MODE_64);md.detail=True
    ins=list(md.disasm(raw,BEGIN));by_pc={i.address:i for i in ins}
    if sum(i.size for i in ins)!=len(raw):raise ValueError('OFFLINE_TAB_BODY_DECODE_GAP')
    for index,i in enumerate(ins):
        if i.address!=(BEGIN if index==0 else ins[index-1].address+ins[index-1].size):
            raise ValueError('OFFLINE_TAB_BODY_INSTRUCTION_GAP')
    successors={};edges=[];unknown=[];leaders={BEGIN};calls=[];rip_refs=[];writes=[]
    for index,i in enumerate(ins):
        next_pc=i.address+i.size;targets=[]
        if i.group(CS_GRP_RET):
            if next_pc<END:leaders.add(next_pc)
        elif i.group(CS_GRP_JUMP):
            if len(i.operands)==1 and i.operands[0].type==X86_OP_IMM:
                target=i.operands[0].imm
                targets.append(target);leaders.add(target)
            else:unknown.append({'pc':i.address,'reason':'INDIRECT_BRANCH_NOT_FOLLOWED'})
            if i.mnemonic!='jmp':targets.append(next_pc)
            if next_pc<END:leaders.add(next_pc)
        else:targets.append(next_pc)
        for target in targets:
            if target not in by_pc:unknown.append({'pc':i.address,'target':target,'reason':'CFG_TARGET_NOT_SAVED_BOUNDARY'})
            else:edges.append([i.address,target])
        successors[i.address]=[target for target in targets if target in by_pc]
        if i.mnemonic=='call':
            calls.append({'pc':i.address,'target':i.operands[0].imm if i.operands[0].type==X86_OP_IMM else i.op_str,
                'bytes':i.bytes.hex(),'preceding_instructions':[{'pc':p.address,'asm':p.mnemonic+' '+p.op_str}
                    for p in ins[max(0,index-8):index]],
                'argument_window_is_local_evidence_not_cross_branch_symbolic_proof':True})
        for op in i.operands:
            if op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP:
                rip_refs.append({'pc':i.address,'target':next_pc+op.mem.disp,'asm':i.mnemonic+' '+i.op_str,
                    'kind':'address_value'if i.mnemonic=='lea'else'external_data_reference_not_read'})
        if i.operands and i.operands[0].type==X86_OP_MEM and i.mnemonic not in ('cmp','test'):
            writes.append({'pc':i.address,'asm':i.mnemonic+' '+i.op_str})
    reachable=set();pending=[BEGIN]
    while pending:
        pc=pending.pop()
        if pc in reachable:continue
        reachable.add(pc);pending.extend(successors[pc])
    blocks=[];sorted_leaders=sorted(pc for pc in leaders if pc in by_pc)
    for n,start in enumerate(sorted_leaders):
        end=sorted_leaders[n+1]if n+1<len(sorted_leaders)else END
        pcs=[i.address for i in ins if start<=i.address<end]
        blocks.append({'begin':start,'end':end,'instruction_PCs':pcs,'reachable':start in reachable,
                       'successors':successors[pcs[-1]]})
    returns=[i.address for i in ins if i.group(CS_GRP_RET)and i.address in reachable]
    result={'source_BIN_SHA256':SHA,'source_JSON_SHA256':hashlib.sha256((SOURCE/'body.json').read_bytes()).hexdigest(),
        'begin':BEGIN,'end':END,'bytes':len(raw),'instructions':len(ins),'decoded_all_bytes':True,
        'normal_call_return_CFG_closed':not unknown and bool(returns),'CFG_unknowns':unknown,
        'reachable_instructions':len(reachable),'normal_return_PCs':returns,'basic_blocks':blocks,
        'instruction_edges':edges,'calls':calls,'rip_references':rip_refs,'memory_write_instructions':writes,
        'callback_pair_write':{'LEA_PC':0x17A9933,'function_RVA':0x17A9630,
            'object_store_PC':0x17A993A,'object_field':0x100,'function_store_PC':0x17A9948,'function_field':0x108,
            'object_expression':'entry.RCX = Armory + 0x570','callback_semantics_proven':False,
            'callback_target_bytes_read':False,'normal_tab_input_consumer_proven':False},
        'argument_EDX_900':{'derived_register':'R13D = entry.EDX + 1 = 901','derive_PC':0x17A986F,
            'used_as_EDX_to_14491F0_and_stack_arg5_of_subwidget_constructors':True,'semantic_type_proven':False},
        'resource_literal':{'PC':0x17A9A17,'RDX_hex':'7BF048B3D6DAA198','call_PC':0x17A9A27,
            'callee_RVA':0x144F800,'RCX_expression':'entry.RCX + 0x3C8','R8D':0,'resource_type_proven':False},
        'Game_accessed':False,'native_called':False,'callee_or_handler_followed':False,
        'exception_CFG_or_callback_signature_proven':False,'tool_SHA256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    OUTPUT.mkdir(parents=True,exist_ok=True)
    (OUTPUT/'17A9820.asm').write_text('\n'.join(f'{i.address:08X} {i.bytes.hex():32} {i.mnemonic} {i.op_str}'for i in ins)+'\n','utf8')
    (OUTPUT/'analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf8')
    print(json.dumps({key:result[key]for key in ('bytes','instructions','reachable_instructions',
        'normal_call_return_CFG_closed','CFG_unknowns','normal_return_PCs','callback_pair_write')},indent=2))


if __name__=='__main__':main()
