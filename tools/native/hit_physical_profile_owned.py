"""Real JMP-based physical-success replay on owned frames/pages only.

The gateway never changes RSP. Its CHAININFO references the tool's known
original parent frame. A game adapter requires the actual parent's metadata,
and this constructor rejects every external code/data address.
"""
import ctypes
import struct

from hit_bridge_owned import RuntimeFunction, _Code

GET_TID_BODY = bytes.fromhex("65 48 8b 04 25 30 00 00 00 8b 40 48 c3")
PARENT_UNWIND = bytes.fromhex("01090400 0932 05f0 03d0 0150")
XMM_OFFSET = 160
MXCSR_OFFSET = 128
SCRATCH_BYTES = 512


def gp_memory(c, *, store, register, base, displacement):
    """MOV64 with disp32; base/register indices are x64 register numbers."""
    prefix = 0x48 | (4 if register >= 8 else 0) | (1 if base >= 8 else 0)
    modrm = 0x80 | ((register & 7) << 3) | (base & 7)
    c.emit(bytes([prefix, 0x89 if store else 0x8B, modrm]).hex(" ")
           + " " + displacement.to_bytes(4, "little").hex(" "))


def xmm_memory(c, *, store, register, base, displacement):
    prefix = "f3 " + ("44 " if register >= 8 else "")
    modrm = 0x80 | ((register & 7) << 3) | base
    c.emit(prefix + "0f " + ("7f " if store else "6f ") + bytes([modrm]).hex()
           + " " + displacement.to_bytes(4, "little").hex(" "))


def snapshot_code(c, displacement):
    # RCX is the owned output buffer. These MOV/STMXCSR/flags stores change no
    # incoming GPR/XMM state; all 16 GP registers are recorded before the jump.
    for register in range(16):
        gp_memory(c, store=True, register=register, base=1, displacement=displacement+register*8)
    # LAHF/SETO captures arithmetic flags without a transient RSP change.
    # Restore RAX (including its AH) before entering the gateway/return path.
    c.emit("9f 88 a1 " + (displacement+128).to_bytes(4,"little").hex(" "))
    c.emit("0f 90 81 " + (displacement+129).to_bytes(4,"little").hex(" "))
    gp_memory(c,store=False,register=0,base=1,displacement=displacement)
    c.emit("0f ae 99 " + (displacement+136).to_bytes(4,"little").hex(" "))
    for register in range(16):
        xmm_memory(c,store=True,register=register,base=1,displacement=displacement+160+register*16)


def parent_fixture_code():
    c = _Code()
    # Actual binding required by the proved success branch, in a known owned
    # parent frame: RBP=DP, R13=HI, R15D=slot. Shadow0..17 is dead here.
    c.emit("55 41 55 41 57 48 83 ec 20 48 89 d5 4d 89 c5 4d 89 cf")
    snapshot_code(c,0)
    # A plain terminal FF25 is recognised as a CALL-frame epilog and would
    # incorrectly skip this already-live parent frame. A恒true Jcc remains a
    # body instruction; original XOR later defines the required output flags.
    c.emit("48 39 c0 0f 84")
    jump_operand = len(c.code)
    c.emit("00 00 00 00 0f 0b 90 90 90")
    continuation = len(c.code)
    c.emit("32 c0 88 45 1c 34 01")  # the actual5B replay, then original XOR AL,1
    snapshot_code(c,512)
    c.emit("48 ff 81 00 04 00 00")  # owned original counter exactly once, not an event
    c.emit("48 83 c4 20 41 5f 41 5d 5d c3")
    return c.finish(), jump_operand, continuation


def physical_code(*,context,scratch,bridge,publisher,qualifier,manager,continuation,address):
    c=_Code()
    # At the ACTUAL success point, successor reads +70/+128 only before ADD
    # and POPs. +00/+08/+10 are dead; +20 is not used by this gateway.
    c.emit("48 89 04 24 4c 89 54 24 08 4c 89 5c 24 10")
    c.emit("48 b8 "+context.to_bytes(8,'little').hex(' '))
    # Matches this machine's public GetCurrentThreadId body, without a CALL
    # that could touch not-yet-saved volatile XMM state.
    c.emit("65 4c 8b 14 25 30 00 00 00 45 8b 52 48 44 3b 50 60")
    c.branch('0f 85','bypass')
    c.emit('83 78 64 01')
    c.branch('0f 84','phase_ready')
    c.emit('83 78 64 02')
    c.branch('0f 85','bypass')
    c.label('phase_ready')
    c.emit('4c 3b 68 68')
    c.branch('0f 85','bypass')
    c.emit('c7 40 64 03 00 00 00')
    c.emit('48 b8 '+scratch.to_bytes(8,'little').hex(' '))
    for register in range(16):
        if register not in (0,10,11):gp_memory(c,store=True,register=register,base=0,displacement=register*8)
    for register,shadow in [(0,0),(10,8),(11,16)]:
        c.emit('4c 8b 54 24 '+bytes([shadow]).hex())
        gp_memory(c,store=True,register=10,base=0,displacement=register*8)
    c.emit('0f ae 98 '+MXCSR_OFFSET.to_bytes(4,'little').hex(' '))
    for register in range(16):
        xmm_memory(c,store=True,register=register,base=0,displacement=XMM_OFFSET+register*16)
    c.emit('49 ba '+context.to_bytes(8,'little').hex(' '))
    c.emit('49 8b 85 10 01 00 00 49 89 42 10')
    for load,store in [
        ('41 8b 45 20','41 89 42 2c'),('41 8b 85 80 00 00 00','41 89 42 30'),
        ('41 8b 85 00 01 00 00','41 89 42 34'),('41 8b 45 00','41 89 42 50'),
        ('41 8b 45 50','41 89 42 44'),('8b 45 04','41 89 42 48'),('8b 45 00','41 89 42 4c')]:
        c.emit(load+' '+store)
    c.emit('45 89 7a 20 41 c7 42 38 00 00 00 00 41 c7 42 3c 02 00 00 00')
    c.emit('41 c7 42 54 00 00 00 00 41 c7 42 58 03 00 00 00')
    c.emit('48 b9 '+manager.to_bytes(8,'little').hex(' ')+' 4c 89 d2')
    c.emit('48 b8 '+qualifier.to_bytes(8,'little').hex(' ')+' ff d0')
    c.emit('48 b9 '+bridge.to_bytes(8,'little').hex(' ')+' 48 ba '+context.to_bytes(8,'little').hex(' '))
    c.emit('48 b8 '+publisher.to_bytes(8,'little').hex(' ')+' ff d0')
    c.emit('48 b8 '+scratch.to_bytes(8,'little').hex(' '))
    c.emit('0f ae 90 '+MXCSR_OFFSET.to_bytes(4,'little').hex(' '))
    for register in range(16):
        xmm_memory(c,store=False,register=register,base=0,displacement=XMM_OFFSET+register*16)
    for register in range(1,16):gp_memory(c,store=False,register=register,base=0,displacement=register*8)
    gp_memory(c,store=False,register=0,base=0,displacement=0)
    c.branch('e9','resume')
    c.label('bypass')
    c.emit('48 8b 04 24 4c 8b 54 24 08 4c 8b 5c 24 10')
    c.label('resume')
    c.emit('48 39 c0 0f 84')
    relative=continuation-(address+len(c.code)+4)
    if not -(2**31)<=relative<2**31:raise ValueError('owned physical continuation outside rel32')
    c.emit(struct.pack('<i',relative).hex(' ')+' 0f 0b')
    return c.finish()


class OwnedPhysicalProfile:
    def __init__(self,bridge,context,resolver):
        self.bridge=bridge
        self.context=context
        if bridge.closed or context.bridge is not bridge or resolver.bridge is not bridge:
            raise ValueError('physical profile needs one live owned bridge/context/map')
        qualifier=int(ctypes.cast(resolver._qualify,ctypes.c_void_p).value or 0)
        expected_getter=int(ctypes.cast(bridge.kernel.GetCurrentThreadId,ctypes.c_void_p).value)
        if (context.address not in bridge._allocations or resolver.manager not in bridge._allocations
                or qualifier not in bridge._procedures or context.get_thread_id!=expected_getter):
            raise ValueError('physical profile requires owned context/map/procedure and the actual kernel export')
        actual=ctypes.string_at(context.get_thread_id,len(GET_TID_BODY))
        if actual!=GET_TID_BODY:
            raise ValueError('public owned-process GetCurrentThreadId implementation is not the proved profile')
        self.thread_getter_pin=actual.hex()
        self.scratch=bridge._allocate(SCRATCH_BYTES,executable=False)
        parent_code,operand,continuation=parent_fixture_code()
        self.parent=bridge._procedure(parent_code,ctypes.c_uint8,ctypes.c_void_p,ctypes.c_void_p,
            ctypes.c_void_p,ctypes.c_uint32,unwind=PARENT_UNWIND)
        self.parent_address=int(ctypes.cast(self.parent,ctypes.c_void_p).value)
        self.continuation=self.parent_address+continuation
        self.address=bridge._allocate(4096,executable=True)
        code=physical_code(context=context.address,scratch=self.scratch,bridge=bridge.base,
            publisher=int(ctypes.cast(bridge.publisher,ctypes.c_void_p).value),
            qualifier=qualifier,manager=resolver.manager,
            continuation=self.continuation,address=self.address)
        if len(code)>=0x800:raise ValueError('owned physical program overlaps unwind metadata')
        self.image_base=min(self.address,self.parent_address)
        items=[self.address-self.image_base,self.address+len(code)-self.image_base,self.address+0x800-self.image_base,
               self.parent_address-self.image_base,self.parent_address+len(parent_code)-self.image_base,
               self.parent_address+0x800-self.image_base]
        if any(not 0<=item<2**32 for item in items):raise ValueError('owned chain addresses cannot be represented by RVA32')
        self.unwind=bytes.fromhex('21000000')+struct.pack('<III',*items[3:])
        ctypes.memmove(self.address,code,len(code));ctypes.memmove(self.address+0x800,self.unwind,len(self.unwind))
        self._protect(self.address,0x20)
        entry=RuntimeFunction(*items[:3])
        if not bridge.nt.RtlAddFunctionTable(ctypes.byref(entry),1,self.image_base):raise RuntimeError('owned physical chain registration')
        bridge._function_tables.append((self.image_base,entry))
        bridge._procedures[self.address]={'code':code,'unwind':self.unwind,'executable_length':len(code)}
        self.gateway=ctypes.WINFUNCTYPE(None)(self.address)
        self._protect(self.parent_address,4)
        relative=self.address-(self.parent_address+operand+4)
        if not -(2**31)<=relative<2**31:raise ValueError('owned physical gateway outside rel32')
        ctypes.memmove(self.parent_address+operand,struct.pack('<i',relative),4)
        self._protect(self.parent_address,0x20)
        self.output=ctypes.create_string_buffer(1032)
        self.code=code
        self.parent_code=ctypes.string_at(self.parent_address,len(parent_code))
        bridge._keepalive.extend([context,resolver,self,self.output])

    def _protect(self,address,protection):
        old=ctypes.c_uint32()
        if not self.bridge.kernel.VirtualProtect(address,4096,protection,ctypes.byref(old)):
            raise ctypes.WinError(ctypes.get_last_error())
        if protection==0x20 and not self.bridge.kernel.FlushInstructionCache(self.bridge.kernel.GetCurrentProcess(),address,4096):
            raise ctypes.WinError(ctypes.get_last_error())

    def invoke(self,hit,values,slot=7):
        if self.bridge.closed:raise ValueError('closed bridge')
        return int(self.parent(ctypes.addressof(self.output),ctypes.addressof(values),ctypes.addressof(hit),slot))

    def snapshots(self):
        if self.bridge.closed:raise ValueError('closed bridge')
        raw=bytes(self.output)
        return raw[:512],raw[512:1024],struct.unpack_from('<Q',raw,1024)[0]
