"""
Input simulation using pynput.
All mouse/keyboard actions are performed as real hardware-level press/release events.
"""
from __future__ import annotations
import time
from typing import Optional

from pynput import mouse as _mouse, keyboard as _keyboard
from pynput.mouse import Button
from pynput.keyboard import Key, KeyCode


# Map common key name strings to pynput Key objects
_KEY_MAP: dict[str, Key | KeyCode] = {
    "ctrl":       Key.ctrl,
    "control":    Key.ctrl,
    "alt":        Key.alt,
    "shift":      Key.shift,
    "win":        Key.cmd,
    "super":      Key.cmd,
    "enter":      Key.enter,
    "return":     Key.enter,
    "tab":        Key.tab,
    "space":      Key.space,
    "backspace":  Key.backspace,
    "delete":     Key.delete,
    "del":        Key.delete,
    "esc":        Key.esc,
    "escape":     Key.esc,
    "up":         Key.up,
    "down":       Key.down,
    "left":       Key.left,
    "right":      Key.right,
    "home":       Key.home,
    "end":        Key.end,
    "pageup":     Key.page_up,
    "pagedown":   Key.page_down,
    "f1":  Key.f1,  "f2":  Key.f2,  "f3":  Key.f3,  "f4":  Key.f4,
    "f5":  Key.f5,  "f6":  Key.f6,  "f7":  Key.f7,  "f8":  Key.f8,
    "f9":  Key.f9,  "f10": Key.f10, "f11": Key.f11, "f12": Key.f12,
    "insert": Key.insert,
    "caps_lock": Key.caps_lock,
    "num_lock": Key.num_lock,
    "print_screen": Key.print_screen,
    "scroll_lock": Key.scroll_lock,
    "pause": Key.pause,
    "menu": Key.menu,
}


def _resolve_key(name: str) -> Key | KeyCode:
    """Convert a key name string to a pynput key object."""
    lower = name.lower().strip()
    if lower in _KEY_MAP:
        return _KEY_MAP[lower]
    # Single character
    if len(lower) == 1:
        return KeyCode.from_char(lower)
    # Try as KeyCode char anyway
    return KeyCode.from_char(lower)


class InputSimulator:
    """
    Wraps pynput mouse and keyboard controllers.
    All operations simulate real hardware input events.
    """

    def __init__(self) -> None:
        self._mouse = _mouse.Controller()
        self._keyboard = _keyboard.Controller()
        self.mouse_speed_ms: int = 80

    # ------------------------------------------------------------------
    # Mouse operations
    # ------------------------------------------------------------------

    def move_to(self, x: int, y: int, smooth: bool = False, duration_ms: int = None) -> None:
        if duration_ms is None:
            duration_ms = self.mouse_speed_ms
        if not smooth:
            self._mouse.position = (x, y)
            return
        cx, cy = self._mouse.position
        steps = max(8, duration_ms // 10)
        step_delay = duration_ms / 1000.0 / steps
        for i in range(1, steps + 1):
            t = i / steps
            self._mouse.position = (int(cx + (x - cx) * t), int(cy + (y - cy) * t))
            time.sleep(step_delay)

    def click_once(self, x: int, y: int, hold_ms: int = 50) -> None:
        """Move to position, press left button, hold, release."""
        self.move_to(x, y, smooth=True)
        self._mouse.press(Button.left)
        time.sleep(hold_ms / 1000.0)
        self._mouse.release(Button.left)

    def click_hold(self, x: int, y: int, hold_ms: int = 1000) -> None:
        """Press and hold left button for hold_ms milliseconds."""
        self.move_to(x, y, smooth=True)
        self._mouse.press(Button.left)
        time.sleep(hold_ms / 1000.0)
        self._mouse.release(Button.left)

    def middle_click(self, x: int, y: int, hold_ms: int = 50) -> None:
        """Middle button click."""
        self.move_to(x, y, smooth=True)
        self._mouse.press(Button.middle)
        time.sleep(hold_ms / 1000.0)
        self._mouse.release(Button.middle)

    def scroll(self, x: int, y: int, direction: str, amount: int) -> None:
        """
        Scroll at position. direction: 'up' or 'down'.
        Sends in batches of up to 10 ticks to avoid Windows WHEEL_DELTA overflow.
        """
        self.move_to(x, y)
        sign = 1 if direction == "up" else -1
        batch = 10
        remaining = amount
        while remaining > 0:
            ticks = min(remaining, batch)
            self._mouse.scroll(0, sign * ticks)
            remaining -= ticks
            if remaining > 0:
                time.sleep(0.01)

    def drag(
        self,
        start_x: int, start_y: int,
        end_x: int, end_y: int,
        duration_ms: int = 300,
        steps: int = 20,
    ) -> None:
        """
        Drag from start to end using linear interpolation.
        Produces smooth movement that most applications recognize.
        """
        self.move_to(start_x, start_y)
        time.sleep(0.05)
        self._mouse.press(Button.left)
        time.sleep(0.02)

        step_delay = duration_ms / 1000.0 / max(steps, 1)
        for i in range(1, steps + 1):
            t = i / steps
            ix = int(start_x + (end_x - start_x) * t)
            iy = int(start_y + (end_y - start_y) * t)
            self._mouse.position = (ix, iy)
            time.sleep(step_delay)

        self._mouse.release(Button.left)

    # ------------------------------------------------------------------
    # Keyboard operations
    # ------------------------------------------------------------------

    def key_press(self, keys: list[str], hold_ms: int = 50) -> None:
        """
        Press a key combination.
        keys: list of key name strings, e.g. ["ctrl", "c"]
        All keys are pressed in order, held for hold_ms, then released in reverse.
        """
        resolved = [_resolve_key(k) for k in keys]
        for k in resolved:
            self._keyboard.press(k)
        time.sleep(hold_ms / 1000.0)
        for k in reversed(resolved):
            self._keyboard.release(k)

    def type_text(self, text: str) -> None:
        """Type a string of text character by character."""
        self._keyboard.type(text)
