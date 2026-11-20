"""Send test clicks to one visible window without moving the system pointer."""
import os
import sys


class InactiveBoard(ValueError):
    """The target remains visible, but another app is active."""


def window_clicks(first, second):
    if sys.platform=='darwin':return MacWindowClicks(first,second)
    if sys.platform=='win32':return WindowsWindowClicks(first,second)
    raise ValueError('Cursor-free test clicks are available on Mac and Windows.')


class MacWindowClicks:
    def __init__(self,first,second):
        import AppKit
        import ctypes
        import Quartz
        self.q=Quartz
        self.workspace=AppKit.NSWorkspace.sharedWorkspace()
        a,b=self.window_at(first),self.window_at(second)
        if not a or a!=b or a[0]==os.getpid():
            raise ValueError('Both squares must be visible in the same external window.')
        self.target=a

        class Point(ctypes.Structure):
            _fields_=[('x',ctypes.c_double),('y',ctypes.c_double)]

        self.point=Point
        quartz=ctypes.CDLL('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
        self.post=quartz.CGPostMouseEvent
        self.post.argtypes=[Point,ctypes.c_int,ctypes.c_uint,ctypes.c_int]
        self.post.restype=ctypes.c_int

    def window_at(self,point):
        q=self.q
        windows=q.CGWindowListCopyWindowInfo(q.kCGWindowListOptionOnScreenOnly|q.kCGWindowListExcludeDesktopElements,q.kCGNullWindowID)
        x,y=point
        for window in windows or ():
            if not 0<=window.get(q.kCGWindowLayer,-1)<=q.CGWindowLevelForKey(q.kCGModalPanelWindowLevelKey) or window.get(q.kCGWindowAlpha,1)<.1:continue
            bounds=window.get(q.kCGWindowBounds,{})
            left,top=bounds.get('X',0),bounds.get('Y',0)
            if left<=x<left+bounds.get('Width',0) and top<=y<top+bounds.get('Height',0):
                return window.get(q.kCGWindowOwnerPID),window.get(q.kCGWindowNumber)
        return None

    def click(self,point):
        q=self.q
        if self.window_at(point)!=self.target:
            raise ValueError('The target window moved or is covered.')
        front=self.workspace.frontmostApplication()
        if front is None or front.processIdentifier()!=self.target[0]:
            raise InactiveBoard('Switch to the board window to send moves.')
        if q.CGEventSourceButtonState(q.kCGEventSourceStateCombinedSessionState,q.kCGMouseButtonLeft):
            raise ValueError('Release the left mouse button and start autoplay again.')
        at=self.point(*point)
        # Quartz supports sending at the square while leaving the cursor alone.
        for pressed in (1,0):
            code=self.post(at,0,1,pressed)
            if code:raise ValueError(f'macOS rejected the test click ({code}).')


class WindowsWindowClicks:
    def __init__(self,first,second):
        import ctypes
        from ctypes import wintypes as t
        self.point=t.POINT
        api=ctypes.WinDLL('user32',use_last_error=True)
        api.WindowFromPoint.argtypes=[t.POINT]
        api.WindowFromPoint.restype=t.HWND
        api.GetWindowThreadProcessId.argtypes=[t.HWND,ctypes.POINTER(t.DWORD)]
        api.GetWindowThreadProcessId.restype=t.DWORD
        api.ScreenToClient.argtypes=[t.HWND,ctypes.POINTER(t.POINT)]
        api.ScreenToClient.restype=t.BOOL
        api.PostMessageW.argtypes=[t.HWND,t.UINT,t.WPARAM,t.LPARAM]
        api.PostMessageW.restype=t.BOOL
        self.api=api
        self.ref=ctypes.byref
        start,end=self.window_at(first),self.window_at(second)
        if not start or start!=end:
            raise ValueError('Both squares must be visible in the same external window.')
        pid=t.DWORD()
        api.GetWindowThreadProcessId(start,self.ref(pid))
        if pid.value==os.getpid():raise ValueError('Choose an external board window.')
        self.target=start

    def window_at(self,point):
        return self.api.WindowFromPoint(self.point(*point))

    def click(self,point):
        if self.window_at(point)!=self.target:
            raise ValueError('The target window moved or is covered.')
        if self.api.GetAsyncKeyState(1)&0x8000:
            raise ValueError('Release the left mouse button and start autoplay again.')
        pt=self.point(*point)
        if not self.api.ScreenToClient(self.target,self.ref(pt)):
            raise ValueError('BoardLens lost the target window.')
        coords=((pt.y&0xffff)<<16)|(pt.x&0xffff)
        if not self.api.PostMessageW(self.target,0x201,1,coords) or not self.api.PostMessageW(self.target,0x202,0,coords):
            raise ValueError('The target window did not accept the test click.')
