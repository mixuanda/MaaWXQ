"""Read-only executable identity plus one optional normal foreground request."""
import ctypes as c,time
from ctypes import wintypes as w
from pathlib import PureWindowsPath
from window_identity import inspect_window

def process_security(pid=None):
    k=c.WinDLL('kernel32',use_last_error=True);a=c.WinDLL('advapi32',use_last_error=True)
    k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];k.OpenProcess.restype=w.HANDLE
    k.GetCurrentProcess.argtypes=[];k.GetCurrentProcess.restype=w.HANDLE
    k.CloseHandle.argtypes=[w.HANDLE];k.CloseHandle.restype=w.BOOL
    a.OpenProcessToken.argtypes=[w.HANDLE,w.DWORD,c.POINTER(w.HANDLE)];a.OpenProcessToken.restype=w.BOOL
    a.GetTokenInformation.argtypes=[w.HANDLE,c.c_int,c.c_void_p,w.DWORD,c.POINTER(w.DWORD)];a.GetTokenInformation.restype=w.BOOL
    a.GetSidSubAuthorityCount.argtypes=[c.c_void_p];a.GetSidSubAuthorityCount.restype=c.POINTER(c.c_ubyte)
    a.GetSidSubAuthority.argtypes=[c.c_void_p,w.DWORD];a.GetSidSubAuthority.restype=c.POINTER(w.DWORD)
    process=k.OpenProcess(0x1000,False,pid) if pid is not None else k.GetCurrentProcess()
    if not process:raise RuntimeError('security_process_query_failed:'+str(c.get_last_error()))
    try:
        token=w.HANDLE()
        if not a.OpenProcessToken(process,8,c.byref(token)):raise RuntimeError('security_token_query_failed:'+str(c.get_last_error()))
        try:
            result={'known':True}
            for name,cls in [('elevated',20),('ui_access',26),('app_container',29)]:
                v=w.DWORD();size=w.DWORD()
                if not a.GetTokenInformation(token,cls,c.byref(v),c.sizeof(v),c.byref(size)):
                    raise RuntimeError('token_field_unavailable:'+name+':'+str(c.get_last_error()))
                result[name]=bool(v.value)
            size=w.DWORD();a.GetTokenInformation(token,25,None,0,c.byref(size))
            if not 0<size.value<65536:raise RuntimeError('integrity_size_unavailable')
            buf=c.create_string_buffer(size.value)
            if not a.GetTokenInformation(token,25,buf,size,c.byref(size)):raise RuntimeError('integrity_query_failed')
            sid=c.cast(buf,c.POINTER(c.c_void_p)).contents.value
            count=a.GetSidSubAuthorityCount(sid).contents.value
            rid=a.GetSidSubAuthority(sid,count-1).contents.value
            result['integrity_rid']=rid
            result['integrity_name']={4096:'low',8192:'medium',12288:'high',16384:'system'}.get(rid,'other')
            return result
        finally:k.CloseHandle(token)
    finally:
        if pid is not None:k.CloseHandle(process)

def executable_path(pid):
    k=c.WinDLL('kernel32',use_last_error=True)
    k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];k.OpenProcess.restype=w.HANDLE
    k.CloseHandle.argtypes=[w.HANDLE];k.CloseHandle.restype=w.BOOL
    k.QueryFullProcessImageNameW.argtypes=[w.HANDLE,w.DWORD,w.LPWSTR,c.POINTER(w.DWORD)]
    k.QueryFullProcessImageNameW.restype=w.BOOL
    handle=k.OpenProcess(0x1000,False,pid)
    if not handle:raise RuntimeError('game_query_limited_information_failed:'+str(c.get_last_error()))
    try:
        text=c.create_unicode_buffer(32768);length=w.DWORD(len(text))
        if not k.QueryFullProcessImageNameW(handle,0,text,c.byref(length)):
            raise RuntimeError('game_image_path_query_failed:'+str(c.get_last_error()))
        return text.value
    finally:k.CloseHandle(handle)

def inspect_game(hwnd,pid):
    row=inspect_window(hwnd,pid);row['executable_path']=executable_path(pid)
    row['process_security']=process_security(pid)
    if (row['title']!='王者万象棋' or row['class_name']!='UnityWndClass'
            or PureWindowsPath(row['executable_path']).name.lower()!='wxq.exe'):
        raise RuntimeError('game_profile_mismatch')
    return row

def activate_once(row):
    u=c.WinDLL('user32',use_last_error=True)
    u.ShowWindowAsync.argtypes=[w.HWND,c.c_int];u.ShowWindowAsync.restype=w.BOOL
    u.SetForegroundWindow.argtypes=[w.HWND];u.SetForegroundWindow.restype=w.BOOL
    u.GetForegroundWindow.argtypes=[];u.GetForegroundWindow.restype=w.HWND
    foreground=lambda:int(u.GetForegroundWindow() or 0)
    result=dict(restore_calls=0,foreground_calls=0,foreground_before=foreground())
    if row['minimized'] or result['foreground_before']!=row['hwnd']:
        c.set_last_error(0)
        result['restore_calls']=1;result['restore_result']=bool(u.ShowWindowAsync(row['hwnd'],9))
        result['restore_raw_last_error']=c.get_last_error();time.sleep(.4)
    result['foreground_after_restore']=foreground()
    if result['foreground_after_restore']!=row['hwnd']:
        c.set_last_error(0)
        result['foreground_calls']=1;result['foreground_result']=bool(u.SetForegroundWindow(row['hwnd']))
        result['foreground_raw_last_error']=c.get_last_error()
        result['foreground_last_error_is_documented']=False;time.sleep(.2)
    result['foreground_after']=foreground()
    result['foreground_confirmed']=result['foreground_after']==row['hwnd']
    return result
