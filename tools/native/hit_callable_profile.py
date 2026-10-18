"""Relocatable x64 CALL gateways. Pure generation never accesses any process.

Inline points enter through E8, giving each observer a real return address and
its own unwindable frame. Original parent EH/UH metadata is never transplanted.
Owned replay tests are required before this manifest is usable by a game host.
"""
import struct
from hit_bridge_owned import _Code, publish_code, drain_code, PUSH_SI_DI_UNWIND
from hit_contact_arena_owned import arena_code, UNWIND as ARENA_UNWIND

FRAME_BYTES = 0x120
# LEA RSP instead of SUB preserves incoming arithmetic flags. RtlVirtualUnwind
# uses declared allocation metadata; actual owned prolog/epilog PCs are tested.
GATE_UNWIND = bytes.fromhex('010e0605 0e03 0b01 2400 0370 0260 0150')
SAVED = {0:32,1:40,2:48,8:56,9:64,10:72,11:80}
XMM = 96
MXCSR = 192
FLAGS = 200
ACTIVE = 208


class RelocCode(_Code):
    def __init__(self):
        super().__init__();self.relocations=[]

    def address(self, opcode, key, addend=0):
        self.emit(opcode)
        self.relocations.append({'offset':len(self.code),'width':8,'address_key':key,'addend':addend})
        self.emit('00 00 00 00 00 00 00 00')

    def call(self,key):
        self.address('48 b8',key);self.emit('ff d0')


def gp(c,store,reg,offset,base=4):
    prefix=0x48|(4 if reg>=8 else 0)
    modrm=0x80|((reg&7)<<3)|base
    c.emit(bytes([prefix,0x89 if store else 0x8B,modrm]).hex(' ')+( ' 24' if base==4 else '')+' '+struct.pack('<i',offset).hex(' '))


def prolog(c):
    c.emit('55 56 57 48 8d a4 24 e0 fe ff ff 48 89 e5')
    for reg,offset in SAVED.items():gp(c,True,reg,offset)
    for xmm in range(6):
        c.emit('0f 29 '+bytes([0x84+xmm*8,0x24]).hex(' ')+' '+struct.pack('<I',XMM+16*xmm).hex(' '))
    c.emit('0f ae 9c 24 c0 00 00 00 9f 88 a4 24 c8 00 00 00 0f 90 84 24 c9 00 00 00')
    c.emit('c7 84 24 d0 00 00 00 00 00 00 00')
    c.address('48 b8','arena')
    c.emit('8b 50 3c f6 c2 01');c.branch('0f 85','restore')
    c.emit('89 94 24 d8 00 00 00')
    c.emit('83 78 28 01');c.branch('0f 85','restore')
    c.emit('f0 ff 40 2c 3b 50 3c');c.branch('0f 85','lost_entry')
    c.emit('83 78 28 01');c.branch('0f 84','entered')
    c.label('lost_entry')
    c.emit('f0 ff 48 2c');c.branch('e9','restore')
    c.label('entered');c.emit('c7 84 24 d0 00 00 00 01 00 00 00')


def restore(c,mode):
    c.label('restore')
    c.emit('83 bc 24 d0 00 00 00 01');c.branch('0f 85','no_active')
    c.address('48 b8','arena');c.emit('f0 ff 48 2c')
    c.label('no_active')
    c.emit('0f ae 94 24 c0 00 00 00')
    for xmm in range(6):
        c.emit('0f 28 '+bytes([0x84+xmm*8,0x24]).hex(' ')+' '+struct.pack('<I',XMM+16*xmm).hex(' '))
    for reg,offset in SAVED.items():
        if reg!=0:gp(c,False,reg,offset)
    c.emit('8a 84 24 c9 00 00 00 04 7f 8a a4 24 c8 00 00 00 9e')
    gp(c,False,0,SAVED[0])
    if mode=='default_delta':c.emit('f3 41 0f 5c c1')
    if mode=='ap_result':c.emit('f3 0f 11 77 04')
    if mode=='physical_success':
        c.emit('4c 8b 94 24 30 01 00 00 32 c0 41 88 42 1c');gp(c,False,10,SAVED[10])
    if mode=='iteration_end':c.emit('8b 84 24 b4 01 00 00 ff c0')
    c.emit('48 8d a5 20 01 00 00 5f 5e 5d')
    if mode in ('contact_begin','custom_curve','normal_final'):
        c.address('ff 25 00 00 00 00','original_'+mode)
    else:c.emit('c3')


def hi_arg(c,mode):
    if mode=='contact_begin':gp(c,False,2,SAVED[2])
    elif mode=='normal_final':gp(c,False,2,SAVED[8])
    elif mode=='physical_success':c.emit('4c 89 ea')
    elif mode=='iteration_end':c.emit('48 8b 94 24 30 01 00 00 48 81 c2 80 05 00 00')
    else:c.emit('48 89 da')


def lookup(c,mode):
    c.address('48 b9','arena');hi_arg(c,mode);c.emit('45 31 c0');c.call('lookup')
    c.emit('48 85 c0');c.branch('0f 84','restore');c.emit('48 89 c6')  # RSI row, callee preserved


def snapshot(c,mode):
    if mode=='normal_final':
        gp(c,False,10,SAVED[8]);gp(c,False,11,SAVED[2])
    else:c.emit('4d 89 ea 4c 8b 9c 24 30 01 00 00')
    c.emit('49 8b 82 10 01 00 00 48 89 46 10')
    for load,store in [('41 8b 42 20','89 46 2c'),('41 8b 82 80 00 00 00','89 46 30'),
        ('41 8b 82 00 01 00 00','89 46 34'),('41 8b 02','89 46 50'),('41 8b 42 50','89 46 44'),
        ('41 8b 43 04','89 46 48'),('41 8b 03','89 46 4c')]:c.emit(load+' '+store)
    c.emit('c7 46 64 03 00 00 00 c7 46 54 00 00 00 00 83 66 58 bf')
    if mode=='physical_success':
        c.emit('c7 46 58 03 00 00 00 c7 46 38 00 00 00 00 c7 46 3c 02 00 00 00 44 89 7e 20')
    else:
        c.emit('83 4e 58 23 83 66 38 fc 41 80 7a 73 00');c.branch('0f 84','hi_force_ready')
        c.emit('83 4e 38 01');c.label('hi_force_ready')
        gp(c,False,0,SAVED[0]);c.emit('f6 80 fc 00 00 00 01');c.branch('0f 84','projectile_force_ready')
        c.emit('83 4e 38 02');c.label('projectile_force_ready');c.emit('c7 46 3c 01 00 00 00')
    c.address('48 b8','bridge');c.emit('48 8b 4e 10 48 3b 48 10');c.branch('0f 85','no_qualifier')
    c.address('48 b9','entity_manager_global');c.emit('48 8b 09 48 85 c9');c.branch('0f 84','no_qualifier')
    c.emit('48 89 f2');c.call('qualifier');c.label('no_qualifier')
    c.address('48 b9','bridge');c.emit('48 89 f2');c.call('publish')


def gateway(mode):
    modes=('contact_begin','default_delta','custom_curve','ap_result','normal_final','physical_success','iteration_end')
    if mode not in modes:raise ValueError('unknown gateway')
    c=RelocCode();prolog(c)
    if mode in ('contact_begin','iteration_end'):
        c.address('48 b9','arena');hi_arg(c,mode);c.emit('4c 8d 84 24 40 01 00 00')
        c.call('begin' if mode=='contact_begin' else 'end')
    else:
        lookup(c,mode)
        if mode in ('default_delta','custom_curve'):
            value=1 if mode=='default_delta' else 2
            c.emit('8b 46 70 85 c0');c.branch('0f 84','set_curve')
            c.emit('83 f8 '+bytes([value]).hex());c.branch('0f 84','set_curve')
            c.emit('c7 46 64 04 00 00 00 c7 46 58 00 00 00 00');c.branch('e9','restore')
            c.label('set_curve');c.emit('c7 46 70 '+struct.pack('<I',value).hex(' ')+' 83 4e 58 10 83 66 38 fb')
            if mode=='custom_curve':c.emit('83 4e 38 04')
        elif mode=='ap_result':
            c.emit('83 7e 64 01');c.branch('0f 85','restore')
            c.emit('f3 44 0f 11 56 40 f3 44 0f 11 4e 44 f3 0f 11 76 48')
            c.emit('48 8b 83 10 01 00 00 48 89 46 10')
            for load,store in [('8b 43 20','89 46 2c'),('8b 83 80 00 00 00','89 46 30'),
                ('8b 83 00 01 00 00','89 46 34'),('8b 03','89 46 50')]:c.emit(load+' '+store)
            c.emit('8b 84 24 c0 00 00 00 0d 80 1f 00 00 89 84 24 c4 00 00 00 0f ae 94 24 c4 00 00 00')
            c.emit('f3 41 0f 10 c2 f3 41 0f 5c c1 f3 0f 11 46 5c 81 4e 58 8c 00 00 00 c7 46 64 02 00 00 00')
        else:
            if mode=='normal_final':
                gp(c,False,10,SAVED[8]);c.emit('83 7e 64 02');c.branch('0f 85','stage_done')
                c.emit('49 8b 82 10 01 00 00 48 3b 46 10');c.branch('0f 85','invalidate')
                for load,compare in [('41 8b 42 20','3b 46 2c'),('41 8b 82 80 00 00 00','3b 46 30'),
                    ('41 8b 82 00 01 00 00','3b 46 34'),('41 8b 02','3b 46 50'),('41 8b 42 50','3b 46 44')]:
                    c.emit(load+' '+compare);c.branch('0f 85','invalidate')
                c.branch('e9','stage_done');c.label('invalidate');c.emit('c7 46 58 00 00 00 00')
                c.label('stage_done')
            snapshot(c,mode)
    restore(c,mode);code=c.finish()
    return {'name':mode,'code_hex':code.hex(),'relocations':c.relocations,'unwind_hex':GATE_UNWIND.hex(),
            'executable_length':len(code)-(8 if mode in ('contact_begin','custom_curve','normal_final') else 0),
            'entry_offset':0,'frame_allocation':FRAME_BYTES,'frame_register':'RBP','original_parent_unwind_unchanged':True}


def configure_code():
    """u32 configure(bridge,arena,epoch,peer,enable): no spin, no allocation."""
    c=_Code();c.emit('56 57 48 89 ce 48 89 d7')
    c.emit('31 c0 41 ba 01 00 00 00 f0 44 0f b1 57 38');c.branch('0f 85','fail')
    c.emit('83 7f 3c fc');c.branch('0f 87','generation_full')
    c.emit('f0 ff 47 3c')
    c.emit('c7 47 28 00 00 00 00 83 7f 2c 00');c.branch('0f 85','unlock_config')
    c.emit('31 c0 f0 44 0f b1 56 18');c.branch('0f 85','unlock_config')
    c.emit('83 7f 2c 00');c.branch('0f 85','unlock_queue')
    c.emit('4c 89 46 08 4c 89 4e 10 4c 89 47 08 4c 89 4f 10')
    c.emit('c7 46 1c 00 00 00 00 c7 46 20 00 00 00 00 c7 46 24 00 00 00 00')
    c.emit('49 89 fb 48 8b 7f 30 41 8b 0b 48 69 c9 50 00 00 00 31 c0 fc f3 48 ab')
    c.emit('c7 46 18 00 00 00 00 8b 44 24 38 83 e0 01 41 89 43 28 f0 41 ff 43 3c 41 c7 43 38 00 00 00 00 b8 01 00 00 00')
    c.branch('e9','return');c.label('unlock_queue');c.emit('c7 46 18 00 00 00 00')
    c.label('unlock_config');c.emit('f0 ff 47 3c')
    c.label('generation_full');c.emit('c7 47 38 00 00 00 00');c.label('fail');c.emit('31 c0')
    c.label('return');c.emit('5f 5e c3');return c.finish()


def manifest():
    sites=[('contact_begin',0x13AD4E8,'e8c350efff',0x12A25B0),('default_delta',0x129CABC,'f3410f5cc1',None),
        ('custom_curve',0x129CADF,'e85cfeffff',0x129C940),('ap_result',0x129CB61,'f30f117704',None),
        ('normal_final',0x13AD88B,'e8a004efff',0x129DD30),('physical_success',0x13B11D4,'32c088451c',None),
        ('iteration_end',0x13AD1D4,'8b442474ffc0',None)]
    entries=[gateway(name) for name,_,_,_ in sites]
    entries.extend({'name':name,'code_hex':code.hex(),'relocations':[],'unwind_hex':uw.hex(),
                    'executable_length':len(code),'entry_offset':0} for name,code,uw in
                   [('publish',publish_code(),PUSH_SI_DI_UNWIND),('drain',drain_code(),PUSH_SI_DI_UNWIND),
                    ('configure',configure_code(),PUSH_SI_DI_UNWIND),
                    *[(name,arena_code(name),ARENA_UNWIND) for name in ('begin','lookup','end')]])
    return {'revision':'callable_hit_profile_v2','abi':1,'record_bytes':96,'queue_header_bytes':64,
        'arena_header_bytes':64,'arena_row_bytes':640,'arena_capacity':32,'max_probes':8,'max_drain':64,
        'arena_fields':{'capacity':0,'row_stride':4,'epoch':8,'peer':16,'contact_counter':24,
            'rejected_u64':32,'enabled':40,'active_u32':44,'rows_pointer':48,'configure_lock':56,'configuration_generation_u32':60},
        'consumer_entry':'drain','coverage_complete':False,'arena_rejections_mean_partial':True,
        'sites':[{'name':name,'rva':rva,'pin_hex':pin,'replace_bytes':len(bytes.fromhex(pin)),
                  'patch_kind':'E8_CALL' if len(pin)==10 else 'E8_CALL_NOP','original_rva':callee}
                 for name,rva,pin,callee in sites], 'entries':entries,
        'game_connected':False,'game_access':False,'lifetime':'process-life once installed; host owns transaction',
        'configure_signature':'uint32_t(void* bridge,void* arena,uint64_t epoch,uint64_t peer,uint32_t enabled)'}


if __name__=='__main__':
    import argparse,json
    from pathlib import Path
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True)
    args=p.parse_args();target=Path(args.output)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(manifest(),indent=2),encoding='utf-8')
    print(str(target.resolve()))
