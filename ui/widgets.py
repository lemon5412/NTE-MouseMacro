"""
Reusable UI widgets and theme constants for the macro tool.
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

# ── Shared dark theme colors ──────────────────────────────────────────
BG       = "#1e1f22"
BG2      = "#2b2d30"
BG3      = "#313438"
FG       = "#dfe1e5"
FG_DIM   = "#888a8e"
ACCENT   = "#4a9eff"
BORDER   = "#3d4043"
SEL      = "#214283"
DISABLED = "#555759"


def apply_theme(root: tk.Misc) -> None:
    """Recursively apply dark theme to all widgets in a window."""
    _style_ttk()


def _style_ttk() -> None:
    """Configure ttk styles for dark theme."""
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure("TCombobox",
                    fieldbackground=BG3, background=BG3,
                    foreground=FG, selectbackground=SEL,
                    selectforeground=FG, bordercolor=BORDER,
                    arrowcolor=FG_DIM, insertcolor=FG)
    style.map("TCombobox",
              fieldbackground=[("readonly", BG3)],
              foreground=[("readonly", FG)],
              selectbackground=[("readonly", SEL)])
    style.configure("TScrollbar", background=BG3, troughcolor=BG,
                    bordercolor=BORDER, arrowcolor=FG_DIM)


def themed_toplevel(parent: tk.Misc, title: str) -> tk.Toplevel:
    """Create a dark-themed Toplevel dialog."""
    win = tk.Toplevel(parent)
    win.title(title)
    win.configure(bg=BG)
    win.resizable(False, False)
    _style_ttk()
    return win


def section(parent: tk.Misc, title: str) -> tk.LabelFrame:
    """Dark-themed labeled section frame."""
    return tk.LabelFrame(
        parent, text=title,
        bg=BG2, fg=FG_DIM,
        font=("Microsoft YaHei", 8),
        padx=8, pady=6,
        bd=1, relief=tk.FLAT,
        highlightthickness=1,
        highlightbackground=BORDER,
    )


def label(parent: tk.Misc, text: str, dim: bool = False, **kw) -> tk.Label:
    return tk.Label(parent, text=text,
                    bg=kw.pop("bg", BG2),
                    fg=kw.pop("fg", FG_DIM if dim else FG),
                    font=kw.pop("font", ("Microsoft YaHei", 9)),
                    **kw)


def entry(parent: tk.Misc, var: tk.Variable, width: int = 8, **kw) -> tk.Entry:
    return tk.Entry(parent, textvariable=var, width=width,
                    bg=kw.pop("bg", BG3),
                    fg=kw.pop("fg", FG),
                    insertbackground=kw.pop("insertbackground", FG),
                    relief=kw.pop("relief", tk.FLAT),
                    highlightthickness=kw.pop("highlightthickness", 1),
                    highlightbackground=kw.pop("highlightbackground", BORDER),
                    highlightcolor=kw.pop("highlightcolor", ACCENT),
                    font=kw.pop("font", ("Consolas", 9)),
                    **kw)


def button(parent: tk.Misc, text: str, cmd: Callable,
           accent: bool = False, danger: bool = False,
           width: int = None, **kw) -> tk.Button:
    if accent:
        bg, fg, hov = "#2d6bbf", "white", "#3a7fd0"
    elif danger:
        bg, fg, hov = "#4a1a1a", "#e08080", "#5a2a2a"
    else:
        bg, fg, hov = BG3, FG, BORDER
    b = tk.Button(parent, text=text, command=cmd,
                  bg=kw.pop("bg", bg),
                  fg=kw.pop("fg", fg),
                  activebackground=kw.pop("activebackground", hov),
                  activeforeground=kw.pop("activeforeground", fg),
                  relief=kw.pop("relief", tk.FLAT),
                  bd=kw.pop("bd", 0),
                  cursor=kw.pop("cursor", "hand2"),
                  font=kw.pop("font", ("Microsoft YaHei", 9)),
                  padx=kw.pop("padx", 10),
                  pady=kw.pop("pady", 4),
                  **kw)
    if width:
        b.configure(width=width)
    return b


def checkbutton(parent: tk.Misc, text: str, var: tk.BooleanVar,
                cmd: Callable = None, bg: str = None) -> tk.Checkbutton:
    kw = {}
    if cmd:
        kw["command"] = cmd
    return tk.Checkbutton(
        parent, text=text, variable=var,
        bg=bg or BG2, fg=FG, selectcolor=BG3,
        activebackground=bg or BG2, activeforeground=FG,
        font=("Microsoft YaHei", 9), **kw
    )


def radiobutton(parent: tk.Misc, text: str, var: tk.Variable,
                value, bg: str = None) -> tk.Radiobutton:
    return tk.Radiobutton(
        parent, text=text, variable=var, value=value,
        bg=bg or BG2, fg=FG, selectcolor=BG3,
        activebackground=bg or BG2, activeforeground=FG,
        font=("Microsoft YaHei", 9),
    )


def separator(parent: tk.Misc) -> tk.Frame:
    return tk.Frame(parent, bg=BORDER, height=1)


def btn_row(parent: tk.Misc, ok_cmd: Callable,
            cancel_cmd: Callable) -> tk.Frame:
    """Standard OK / Cancel button row."""
    f = tk.Frame(parent, bg=BG)
    separator(f).pack(fill=tk.X, pady=(0, 8))
    button(f, "取消", cancel_cmd, width=8).pack(side=tk.RIGHT, padx=(4, 10))
    button(f, "确定", ok_cmd, accent=True, width=8).pack(side=tk.RIGHT, padx=4)
    return f


# ── Legacy classes (kept for compatibility) ───────────────────────────

class LabeledEntry(tk.Frame):
    def __init__(self, parent, lbl: str, width: int = 8,
                 default: str = "", **kwargs) -> None:
        super().__init__(parent, bg=BG2, **kwargs)
        label(self, lbl).pack(side=tk.LEFT)
        self._var = tk.StringVar(value=default)
        entry(self, self._var, width).pack(side=tk.LEFT, padx=(4, 0))

    @property
    def var(self) -> tk.StringVar:
        return self._var

    def get(self) -> str:
        return self._var.get()

    def set(self, value: str) -> None:
        self._var.set(value)


class CoordEntry(tk.Frame):
    def __init__(self, parent, lbl: str = "坐标",
                 on_pick: Optional[Callable] = None, **kwargs) -> None:
        super().__init__(parent, bg=BG2, **kwargs)
        label(self, lbl).pack(side=tk.LEFT)
        label(self, "X:", dim=True).pack(side=tk.LEFT, padx=(6, 0))
        self._x_var = tk.StringVar(value="0")
        entry(self, self._x_var, 6).pack(side=tk.LEFT)
        label(self, "Y:", dim=True).pack(side=tk.LEFT, padx=(4, 0))
        self._y_var = tk.StringVar(value="0")
        entry(self, self._y_var, 6).pack(side=tk.LEFT)
        if on_pick:
            button(self, "拾取", on_pick, width=4).pack(side=tk.LEFT, padx=(6, 0))

    def get(self) -> tuple[int, int]:
        try:
            return int(self._x_var.get()), int(self._y_var.get())
        except ValueError:
            return 0, 0

    def set(self, x: int, y: int) -> None:
        self._x_var.set(str(x))
        self._y_var.set(str(y))


class IntSpinbox(tk.Frame):
    def __init__(self, parent, lbl: str, from_: int = 0,
                 to: int = 99999, default: int = 0,
                 width: int = 7, **kwargs) -> None:
        super().__init__(parent, bg=BG2, **kwargs)
        label(self, lbl).pack(side=tk.LEFT)
        self._var = tk.IntVar(value=default)
        tk.Spinbox(self, from_=from_, to=to, textvariable=self._var,
                   width=width, bg=BG3, fg=FG, buttonbackground=BG3,
                   relief=tk.FLAT, insertbackground=FG,
                   highlightthickness=1, highlightbackground=BORDER,
                   highlightcolor=ACCENT).pack(side=tk.LEFT, padx=(4, 0))

    def get(self) -> int:
        try:
            return int(self._var.get())
        except (ValueError, tk.TclError):
            return 0

    def set(self, value: int) -> None:
        self._var.set(value)


class SectionFrame(tk.LabelFrame):
    def __init__(self, parent, title: str, **kwargs) -> None:
        super().__init__(parent, text=title,
                         bg=BG2, fg=FG_DIM,
                         font=("Microsoft YaHei", 8),
                         padx=8, pady=6, bd=1, relief=tk.FLAT,
                         highlightthickness=1,
                         highlightbackground=BORDER,
                         **kwargs)


class StatusBar(tk.Frame):
    def __init__(self, parent, **kwargs) -> None:
        kwargs.setdefault("bg", BG)
        super().__init__(parent, **kwargs)
        bar_bg = kwargs["bg"]
        self._label = tk.Label(self, text="就绪", anchor="w",
                               padx=6, bg=bar_bg, fg=FG_DIM,
                               font=("Microsoft YaHei", 8))
        self._label.pack(fill=tk.X)

    def set(self, text: str) -> None:
        self._label.config(text=text)


class ToolTip:
    def __init__(self, widget: tk.Widget, text: str) -> None:
        self._widget = widget
        self._text = text
        self._tip: Optional[tk.Toplevel] = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, event=None) -> None:
        x = self._widget.winfo_rootx() + 20
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 4
        self._tip = tk.Toplevel(self._widget)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self._tip, text=self._text,
                 background="#2a2d30", foreground=FG,
                 relief=tk.FLAT, borderwidth=1,
                 font=("Microsoft YaHei", 9),
                 wraplength=220, padx=6, pady=4).pack()

    def _hide(self, event=None) -> None:
        if self._tip:
            self._tip.destroy()
            self._tip = None
