"""
Win32 window utilities using ctypes.
No external dependencies beyond the Python standard library.
"""
from __future__ import annotations
import ctypes
from ctypes import wintypes
from typing import Optional

# Constants
GA_ROOT = 2

_user32 = ctypes.windll.user32


class RECT(ctypes.Structure):
    _fields_ = [
        ("left",   ctypes.c_long),
        ("top",    ctypes.c_long),
        ("right",  ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


def find_window_by_title(title: str) -> Optional[int]:
    """Find a top-level window by exact title. Returns HWND or None."""
    hwnd = _user32.FindWindowW(None, title)
    return hwnd if hwnd else None


def get_window_rect(hwnd: int) -> Optional[tuple[int, int, int, int]]:
    """Get window rectangle as (left, top, right, bottom). Returns None on failure."""
    rect = RECT()
    if _user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return (rect.left, rect.top, rect.right, rect.bottom)
    return None


def window_from_point(x: int, y: int) -> Optional[int]:
    """Get the root ancestor HWND of the window at screen coordinates (x, y)."""
    hwnd = _user32.WindowFromPoint(wintypes.POINT(x, y))
    if hwnd:
        root = _user32.GetAncestor(hwnd, GA_ROOT)
        return root if root else hwnd
    return None


def get_window_title(hwnd: int) -> str:
    """Get the title text of a window. Returns empty string on failure."""
    buf = ctypes.create_unicode_buffer(256)
    _user32.GetWindowTextW(hwnd, buf, 255)
    return buf.value
