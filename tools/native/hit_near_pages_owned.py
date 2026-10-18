"""One bounded VirtualAlloc2 allocation above an OWNED image, no foreign PID.

New code and xdata can use the original image base for RVA32/handler semantics.
No address-space scan, thread pause, code patch or game access is implemented.
"""
import ctypes


class AddressRequirements(ctypes.Structure):
    _fields_=[('lowest',ctypes.c_void_p),('highest',ctypes.c_void_p),('alignment',ctypes.c_size_t)]


class ExtendedParameter(ctypes.Structure):
    _fields_=[('type_and_reserved',ctypes.c_uint64),('pointer',ctypes.c_void_p)]


class SystemInfo(ctypes.Structure):
    _fields_=[('architecture',ctypes.c_uint32),('page_size',ctypes.c_uint32),
        ('minimum',ctypes.c_void_p),('maximum',ctypes.c_void_p),('processor_mask',ctypes.c_size_t),
        ('processor_count',ctypes.c_uint32),('processor_type',ctypes.c_uint32),
        ('allocation_granularity',ctypes.c_uint32),('level',ctypes.c_uint16),('revision',ctypes.c_uint16)]


assert ctypes.sizeof(AddressRequirements)==24 and ctypes.sizeof(ExtendedParameter)==16
assert ctypes.sizeof(SystemInfo)==48


def allocate_owned_near(bridge,image_base,image_size,*,size=4096):
    if bridge.closed or image_base not in bridge._allocations or not 4096<=image_size<0x7FFF0000:
        raise ValueError('near allocation requires a live owned image identity')
    if not 4096<=size<=0x100000 or size%4096:
        raise ValueError('near region is bounded whole pages')
    k=bridge.kernel
    k.GetSystemInfo.argtypes=[ctypes.POINTER(SystemInfo)];k.GetSystemInfo.restype=None
    info=SystemInfo();k.GetSystemInfo(ctypes.byref(info))
    granularity=info.allocation_granularity
    if not granularity or granularity&(granularity-1):raise ValueError('system allocation granularity')
    lowest=(image_base+image_size+granularity-1)&~(granularity-1)
    maximum=min(int(info.maximum),image_base+0x7FFFFFFF)
    highest=((maximum+1)&~(granularity-1))-1
    if lowest+size-1>highest:raise ValueError('no legal owned rel32/RVA32 range')
    req=AddressRequirements(lowest,highest,granularity)
    param=ExtendedParameter(1,ctypes.addressof(req))  # public enum AddressRequirements = 1
    # This Windows installation exports the documented API from KernelBase,
    # while kernel32 has no VirtualAlloc2 export. No other process/module load.
    memory_api=ctypes.WinDLL('KernelBase',use_last_error=True)
    api=memory_api.VirtualAlloc2
    api.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_uint32,
                  ctypes.c_uint32,ctypes.POINTER(ExtendedParameter),ctypes.c_uint32]
    api.restype=ctypes.c_void_p
    address=api(None,None,size,0x3000,4,ctypes.byref(param),1)
    if not address:raise ctypes.WinError(ctypes.get_last_error())
    bridge._allocations.append(address)
    if not lowest<=address<=address+size-1<=highest or address%granularity:
        raise RuntimeError('public allocator result violates specified owned address constraints')
    return address,{'image_base':image_base,'image_size':image_size,'size':size,'lowest':lowest,
        'highest':highest,'alignment':granularity,'rva':address-image_base,'allocation_calls':1,
        'process_handle':'NULL/current tool only','foreign_process_access':False}
