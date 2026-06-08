"""
Full-screen transparent overlay for picking screen coordinates.
Usage:
    picker = PositionPicker(parent_window)
    x, y = picker.pick()   # blocks until user clicks or presses ESC
    # returns (x, y) or (None, None) if cancelled

For region selection (used by text verification):
    x, y, w, h = picker.pick_region()
"""
from __future__ import annotations
import tkinter as tk
from typing import Optional

from core.win_utils import window_from_point, get_window_title, get_window_rect


class PositionPicker:
    """
    Displays a full-screen semi-transparent overlay.
    The user clicks to capture a coordinate, or ESC to cancel.
    """

    def __init__(self, parent: tk.Tk | tk.Toplevel) -> None:
        self._parent = parent
        self._result: Optional[tuple[int, int]] = None
        self._region_result: Optional[tuple[int, int, int, int]] = None
        self._window_result: Optional[tuple[str, tuple[int, int, int, int]]] = None

    def _get_root(self) -> tk.Tk:
        """Walk up the widget tree to find the Tk root window."""
        w = self._parent
        while not isinstance(w, tk.Tk):
            w = w.master
        return w

    def _hide_all(self) -> list[tk.Toplevel]:
        """Withdraw all Toplevel windows and return them for later restore."""
        root = self._get_root()
        hidden = []
        for w in root.winfo_children():
            if isinstance(w, tk.Toplevel) and w.winfo_viewable():
                w.withdraw()
                hidden.append(w)
        # overrideredirect windows can't iconify directly
        root.overrideredirect(False)
        root.iconify()
        return hidden

    def _show_all(self, hidden: list[tk.Toplevel]) -> None:
        root = self._get_root()
        root.deiconify()
        root.overrideredirect(True)
        for w in hidden:
            w.deiconify()
        self._parent.lift()

    def pick(self) -> tuple[Optional[int], Optional[int]]:
        """
        Minimize parent, show overlay, wait for click.
        Returns (x, y) in screen coordinates, or (None, None) on cancel.
        """
        self._result = None
        hidden = self._hide_all()
        self._get_root().update()

        overlay = self._create_overlay(mode="point")
        overlay.wait_window()

        self._show_all(hidden)

        if self._result:
            return self._result
        return None, None

    def pick_region(self) -> tuple[Optional[int], Optional[int], Optional[int], Optional[int]]:
        """
        Minimize parent, show overlay for drag-to-select a region.
        Returns (x, y, w, h) or (None, None, None, None) on cancel.
        """
        self._region_result = None
        hidden = self._hide_all()
        self._get_root().update()

        overlay = self._create_overlay(mode="region")
        overlay.wait_window()

        self._show_all(hidden)

        if self._region_result:
            return self._region_result
        return None, None, None, None

    def pick_window(self) -> tuple[Optional[str], Optional[tuple[int, int, int, int]]]:
        """
        Pick a target window by clicking on it.
        Returns (window_title, (left, top, right, bottom)) or (None, None) on cancel.
        """
        self._window_result = None
        hidden = self._hide_all()
        self._get_root().update()

        overlay = self._create_overlay(mode="window")
        overlay.wait_window()

        self._show_all(hidden)

        if self._window_result:
            return self._window_result
        return None, None

    def _create_overlay(self, mode: str) -> tk.Toplevel:
        overlay = tk.Toplevel(self._parent)
        overlay.attributes("-fullscreen", True)
        overlay.attributes("-alpha", 0.25)
        overlay.attributes("-topmost", True)
        overlay.configure(bg="black")
        overlay.overrideredirect(True)

        canvas = tk.Canvas(
            overlay,
            bg="black",
            cursor="crosshair",
            highlightthickness=0,
        )
        canvas.pack(fill=tk.BOTH, expand=True)

        # Instruction label
        hints = {
            "point": "点击选择坐标  |  ESC 取消",
            "region": "拖动选择区域  |  ESC 取消",
            "window": "点击目标窗口  |  ESC 取消",
        }
        hint = hints.get(mode, hints["point"])
        canvas.create_text(
            overlay.winfo_screenwidth() // 2, 30,
            text=hint,
            fill="white",
            font=("Microsoft YaHei", 14),
        )

        # Crosshair lines
        h_line = canvas.create_line(0, 0, overlay.winfo_screenwidth(), 0, fill="#00ff00", width=1)
        v_line = canvas.create_line(0, 0, 0, overlay.winfo_screenheight(), fill="#00ff00", width=1)
        coord_label = canvas.create_text(0, 0, text="", fill="#00ff00", font=("Consolas", 11), anchor="nw")

        # Region selection state
        drag_start: list[Optional[int]] = [None, None]
        rect_id: list[Optional[int]] = [None]

        def on_motion(event):
            x, y = event.x_root, event.y_root
            canvas.coords(h_line, 0, y, overlay.winfo_screenwidth(), y)
            canvas.coords(v_line, x, 0, x, overlay.winfo_screenheight())
            lx = x + 12
            ly = y + 12
            canvas.coords(coord_label, lx, ly)
            canvas.itemconfig(coord_label, text=f"({x}, {y})")

            if mode == "region" and drag_start[0] is not None:
                if rect_id[0]:
                    canvas.delete(rect_id[0])
                rect_id[0] = canvas.create_rectangle(
                    drag_start[0], drag_start[1], x, y,
                    outline="#00ff00", width=2,
                )

        def on_press(event):
            if mode == "region":
                drag_start[0] = event.x_root
                drag_start[1] = event.y_root

        def on_release(event):
            if mode == "point":
                self._result = (event.x_root, event.y_root)
                overlay.destroy()
            elif mode == "window":
                # Temporarily hide overlay so WindowFromPoint sees the window beneath
                overlay.withdraw()
                overlay.update_idletasks()
                hwnd = window_from_point(event.x_root, event.y_root)
                if hwnd:
                    title = get_window_title(hwnd)
                    rect = get_window_rect(hwnd)
                    if title and rect:
                        self._window_result = (title, rect)
                overlay.destroy()
            elif mode == "region":
                if drag_start[0] is not None:
                    x1, y1 = drag_start[0], drag_start[1]
                    x2, y2 = event.x_root, event.y_root
                    rx = min(x1, x2)
                    ry = min(y1, y2)
                    rw = abs(x2 - x1)
                    rh = abs(y2 - y1)
                    if rw > 5 and rh > 5:
                        self._region_result = (rx, ry, rw, rh)
                    overlay.destroy()

        def on_escape(event):
            overlay.destroy()

        canvas.bind("<Motion>", on_motion)
        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<ButtonRelease-1>", on_release)
        overlay.bind("<Escape>", on_escape)
        overlay.focus_force()

        return overlay
