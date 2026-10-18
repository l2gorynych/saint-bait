"""Owned transparent read-only HUD. All Tk operations stay on the UI thread."""
import ctypes as C
from ctypes import wintypes as W
import tkinter as tk
from tkinter import font as tkfont


class RodOverlay:
    def __init__(self, owner):
        self.api=C.WinDLL('user32',use_last_error=True)
        self.api.GetForegroundWindow.restype=W.HWND
        self.api.GetWindowThreadProcessId.argtypes=[W.HWND,C.POINTER(W.DWORD)]
        self.api.GetClientRect.argtypes=[W.HWND,C.POINTER(W.RECT)]
        self.api.ClientToScreen.argtypes=[W.HWND,C.POINTER(W.POINT)]
        self.api.GetParent.argtypes,self.api.GetParent.restype=[W.HWND],W.HWND
        self.api.GetWindowLongPtrW.argtypes,self.api.GetWindowLongPtrW.restype=[W.HWND,C.c_int],C.c_ssize_t
        self.api.SetWindowLongPtrW.argtypes,self.api.SetWindowLongPtrW.restype=[W.HWND,C.c_int,C.c_ssize_t],C.c_ssize_t
        self.api.SetWindowPos.argtypes=[W.HWND,W.HWND,C.c_int,C.c_int,C.c_int,C.c_int,W.UINT]
        self.api.SetLayeredWindowAttributes.argtypes=[W.HWND,W.DWORD,W.BYTE,W.DWORD]
        self.api.SetLayeredWindowAttributes.restype=W.BOOL
        self.window=tk.Toplevel(owner)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.attributes('-topmost',True)
        self.window.attributes('-transparentcolor','#010203')
        self.canvas=tk.Canvas(self.window,bg='#010203',width=420,height=70,highlightthickness=0,borderwidth=0)
        self.canvas.pack()
        self.font=tkfont.Font(root=self.window,family='Segoe UI',size=10,weight='normal')
        self.window.update_idletasks()
        self.hwnd=self.api.GetParent(self.window.winfo_id()) or self.window.winfo_id()
        style=self.api.GetWindowLongPtrW(self.hwnd,-20)
        self.api.SetWindowLongPtrW(self.hwnd,-20,style|0x08000000|0x00000020|0x00080000|0x00000080)
        if not self.api.SetLayeredWindowAttributes(self.hwnd,0x030201,255,3):
            raise C.WinError(C.get_last_error())
        self.shown=False
        self.previous=None

    def update(self, pid, lines):
        foreground=self.api.GetForegroundWindow()
        process=W.DWORD()
        if foreground:
            self.api.GetWindowThreadProcessId(foreground,C.byref(process))
        if not pid or process.value!=pid or not lines:
            if self.shown:
                self.window.withdraw()
                self.shown=False
            return
        rect,point=W.RECT(),W.POINT()
        if not self.api.GetClientRect(foreground,C.byref(rect)) or rect.right<640 or rect.bottom<400:
            return
        if not self.api.ClientToScreen(foreground,C.byref(point)):
            return
        current=tuple(lines[:3])
        width=min(max((self.font.measure(line)+18 for line in current),default=300),rect.right-40)
        self.canvas.configure(width=width)
        self.api.SetWindowPos(self.hwnd,W.HWND(-1),point.x+18,
                              point.y+min(rect.bottom-88,round(rect.bottom*.70)),width,70,0x10)
        if not self.shown:
            self.window.deiconify()
            self.shown=True
        if current==self.previous:
            return
        self.canvas.delete('all')
        for row,line in enumerate(current):
            x,y=6,4+row*21
            for dx,dy in ((-1,-1),(0,-1),(1,-1),(-1,0),(1,0),(-1,1),(0,1),(1,1),(2,2)):
                self.canvas.create_text(x+dx,y+dy,text=line,fill='black',font=self.font,anchor='nw')
            self.canvas.create_text(x,y,text=line,fill='white',font=self.font,anchor='nw')
        self.previous=current
