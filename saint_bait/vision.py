"""Optional catch awards and lighting only. No OCR and no audio capture."""
import ctypes as C
from ctypes import wintypes as W
import numpy as np
import cv2
from mss import mss
from .settings import TROPHY_IMG,TROPHY2_IMG,CARD_IMG


def frame(pid):
    api=C.WinDLL('user32',use_last_error=True)
    api.GetForegroundWindow.restype=W.HWND
    api.GetWindowThreadProcessId.argtypes=[W.HWND,C.POINTER(W.DWORD)]
    api.GetClientRect.argtypes=[W.HWND,C.POINTER(W.RECT)]
    api.ClientToScreen.argtypes=[W.HWND,C.POINTER(W.POINT)]
    hwnd=api.GetForegroundWindow()
    actual=W.DWORD()
    api.GetWindowThreadProcessId(hwnd,C.byref(actual))
    if actual.value!=pid:return None
    rect,origin=W.RECT(),W.POINT()
    if not api.GetClientRect(hwnd,C.byref(rect)) or not api.ClientToScreen(hwnd,C.byref(origin)):return None
    if rect.right<640 or rect.bottom<400:return None
    with mss() as capture:
        return np.array(capture.grab({'left':origin.x,'top':origin.y,'width':rect.right,'height':rect.bottom}))


def game_brightness(pid):
    pixels=frame(pid)
    return float(cv2.cvtColor(pixels,cv2.COLOR_BGRA2GRAY).mean()) if pixels is not None else None


def catch_awards(pid):
    pixels=frame(pid)
    if pixels is None:return None,None
    gray=cv2.cvtColor(pixels,cv2.COLOR_BGRA2GRAY)
    def matches(path):
        template=cv2.imread(path,0)
        return bool(template is not None and template.shape[0]<=gray.shape[0] and template.shape[1]<=gray.shape[1]
                    and cv2.minMaxLoc(cv2.matchTemplate(gray,template,cv2.TM_CCOEFF_NORMED))[1]>=.85)
    return matches(TROPHY_IMG) or matches(TROPHY2_IMG),matches(CARD_IMG)
