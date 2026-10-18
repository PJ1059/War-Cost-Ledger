"""Capture the known game's client for local coordinate diagnosis; no input."""
import ctypes as C
from ctypes import wintypes as W
from datetime import datetime, timezone
import json
from pathlib import Path
import argparse
from PIL import Image

def capture(hwnd, pid, output, career_page=False):
    u, g = C.WinDLL('user32'), C.WinDLL('gdi32')
    u.GetDC.argtypes=[W.HWND];u.GetDC.restype=W.HDC
    u.GetWindowThreadProcessId.argtypes=[W.HWND,C.POINTER(W.DWORD)]
    u.GetClientRect.argtypes=[W.HWND,C.POINTER(W.RECT)]
    u.PrintWindow.argtypes=[W.HWND,W.HDC,W.UINT]
    u.ReleaseDC.argtypes=[W.HWND,W.HDC]
    g.CreateCompatibleDC.argtypes=[W.HDC];g.CreateCompatibleDC.restype=W.HDC
    g.CreateCompatibleBitmap.argtypes=[W.HDC,C.c_int,C.c_int];g.CreateCompatibleBitmap.restype=W.HBITMAP
    g.SelectObject.argtypes=[W.HDC,W.HANDLE];g.SelectObject.restype=W.HANDLE
    g.GetDIBits.argtypes=[W.HDC,W.HBITMAP,W.UINT,W.UINT,C.c_void_p,C.c_void_p,W.UINT]
    g.DeleteObject.argtypes=[W.HANDLE];g.DeleteDC.argtypes=[W.HDC]
    actual=W.DWORD();u.GetWindowThreadProcessId(hwnd,C.byref(actual))
    if actual.value != pid: raise RuntimeError('Game window process changed')
    rect=W.RECT();assert u.GetClientRect(hwnd,C.byref(rect))
    width,height=rect.right,rect.bottom
    assert 640<=width<=7680 and 480<=height<=4320
    dc=u.GetDC(hwnd);mem=g.CreateCompatibleDC(dc)
    bmp=g.CreateCompatibleBitmap(dc,width,height);old=g.SelectObject(mem,bmp)
    class Header(C.Structure):
        _fields_=[('size',W.DWORD),('width',W.LONG),('height',W.LONG),('planes',W.WORD),('bits',W.WORD),('compression',W.DWORD),('image',W.DWORD),('x',W.LONG),('y',W.LONG),('used',W.DWORD),('important',W.DWORD)]
    try:
        if not u.PrintWindow(hwnd,mem,3): raise RuntimeError('PrintWindow failed')
        h=Header(C.sizeof(Header),width,-height,1,32,0,0,0,0,0,0)
        pixels=C.create_string_buffer(width*height*4)
        assert g.GetDIBits(mem,bmp,0,height,pixels,C.byref(h),0)==height
        # Only persist our panel region. No full desktop or unrelated windows.
        crop=((int(width*.08),int(height*.09),int(width*.77),int(height*.90)) if career_page
              else (int(width*.36),int(height*.12),int(width*.77),int(height*.77)))
        image=Image.frombuffer('RGB',(width,height),pixels,'raw','BGRX',0,1)
        output.parent.mkdir(parents=True,exist_ok=True)
        image.crop(crop).save(output)
        data={'captured_at':datetime.now(timezone.utc).isoformat(),'pid':pid,'hwnd':hwnd,'client':[width,height],'crop':crop,'path':str(output)}
        output.with_suffix('.json').write_text(json.dumps(data,indent=2),encoding='utf8')
        print(json.dumps(data))
    finally:
        g.SelectObject(mem,old);g.DeleteObject(bmp);g.DeleteDC(mem);u.ReleaseDC(hwnd,dc)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--hwnd',type=int,required=True);p.add_argument('--pid',type=int,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--career-page',action='store_true',help='Include the native statistics beside the MOD panel for comparison.')
    a=p.parse_args();capture(a.hwnd,a.pid,a.output,a.career_page)
