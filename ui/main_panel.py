"""
Main floating panel for the macro tool.
This is the central hub that wires all components together.
"""
from __future__ import annotations
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from core.action import (
    ActionType, ACTION_TYPE_LABELS, GlobalSettings,
    ActionGroup, AnyAction, ClickOnceAction,
)
from core.config import ConfigManager
from core.executor import MacroExecutor, HotkeyListener
from core.input_sim import InputSimulator
from core.ocr_engine import OcrEngine
from ui.action_editor import ActionEditor
from ui.text_verify_dialog import TextVerifyDialog
from ui.widgets import StatusBar


# Color scheme
CLR_BG        = "#1e1f22"
CLR_BG2       = "#2b2d30"
CLR_BG3       = "#313438"
CLR_FG        = "#dfe1e5"
CLR_FG_DIM    = "#888a8e"
CLR_ACCENT    = "#4a9eff"
CLR_ACCENT2   = "#2d6bbf"
CLR_RUN       = "#2d7a3a"
CLR_RUN_HOV   = "#3a9a4a"
CLR_STOP      = "#8b2020"
CLR_STOP_HOV  = "#aa3030"
CLR_HIGHLIGHT = "#214283"
CLR_DISABLED  = "#555759"
CLR_VERIFY    = "#c8a020"
CLR_BORDER    = "#3d4043"
CLR_TITLEBAR  = "#16181a"


class MainPanel:
    """
    The main application window.
    Compact, always-on-top floating panel.
    """

    def __init__(self) -> None:
        self._actions: list[AnyAction] = []
        self._settings = GlobalSettings()

        # Core components
        self._sim = InputSimulator()
        self._ocr = OcrEngine()
        self._executor = MacroExecutor(self._sim, self._ocr)
        self._hotkey_listener = HotkeyListener(self._executor)

        self._root = tk.Tk()
        self._root.title("鼠标宏")
        self._root.configure(bg=CLR_BG)
        self._root.attributes("-topmost", True)
        self._root.overrideredirect(True)   # remove system title bar
        self._root.resizable(False, False)
        self._root.minsize(420, 360)

        # Window drag state
        self._drag_x = 0
        self._drag_y = 0

        # Drag-to-reorder state
        self._drag_idx: Optional[int] = None
        self._drag_start_y: int = 0
        self._dragging: bool = False
        self._drag_last_hover: int = -1
        self._DRAG_THRESHOLD: int = 10

        # Window monitor state
        self._monitor_thread: Optional[threading.Thread] = None
        self._monitor_active: bool = False

        # Expanded index mapping: (action, parent_group_or_none, depth)
        self._expanded_map: list[tuple[AnyAction, Optional[AnyAction], int]] = []

        self._build_ui()
        self._setup_executor_callback()
        self._start_hotkey_listener()
        self._warm_up_ocr()

        # Center on screen
        self._root.update_idletasks()
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        w = self._root.winfo_width()
        h = self._root.winfo_height()
        self._root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # Outer border frame
        outer = tk.Frame(self._root, bg=CLR_BORDER, padx=1, pady=1)
        outer.pack(fill=tk.BOTH, expand=True)
        self._main = tk.Frame(outer, bg=CLR_BG)
        self._main.pack(fill=tk.BOTH, expand=True)

        self._build_titlebar()
        self._build_toolbar()
        self._build_settings_bar()
        self._build_action_list()
        self._build_action_buttons()
        self._build_io_buttons()
        self._status_bar = StatusBar(self._main, bg=CLR_BG)
        self._status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        self._status_bar._label.configure(bg=CLR_BG, fg=CLR_FG_DIM, font=("Microsoft YaHei", 8))

    def _build_titlebar(self) -> None:
        bar = tk.Frame(self._main, bg=CLR_TITLEBAR, height=32)
        bar.pack(fill=tk.X)
        bar.pack_propagate(False)

        # App icon dot + title
        tk.Label(bar, text="⬡", bg=CLR_TITLEBAR, fg=CLR_ACCENT,
                 font=("", 11)).pack(side=tk.LEFT, padx=(10, 4))
        tk.Label(bar, text="鼠标宏", bg=CLR_TITLEBAR, fg=CLR_FG,
                 font=("Microsoft YaHei", 9, "bold")).pack(side=tk.LEFT)

        # Window controls
        def btn(parent, text, fg, cmd):
            b = tk.Label(parent, text=text, bg=CLR_TITLEBAR, fg=fg,
                         font=("", 11), padx=10, cursor="hand2")
            b.pack(side=tk.RIGHT)
            b.bind("<Button-1>", lambda e: cmd())
            b.bind("<Enter>", lambda e: b.configure(bg="#3a3d40"))
            b.bind("<Leave>", lambda e: b.configure(bg=CLR_TITLEBAR))
            return b

        btn(bar, "✕", "#e06060", self._on_close)
        btn(bar, "─", CLR_FG_DIM, self._minimize)

        # Drag to move
        bar.bind("<ButtonPress-1>", self._on_drag_start)
        bar.bind("<B1-Motion>", self._on_drag_move)
        for child in bar.winfo_children():
            if isinstance(child, tk.Label) and child.cget("text") not in ("✕", "─"):
                child.bind("<ButtonPress-1>", self._on_drag_start)
                child.bind("<B1-Motion>", self._on_drag_move)

        # Separator line
        tk.Frame(self._main, bg=CLR_BORDER, height=1).pack(fill=tk.X)

    def _on_drag_start(self, event) -> None:
        self._drag_x = event.x_root - self._root.winfo_x()
        self._drag_y = event.y_root - self._root.winfo_y()

    def _on_drag_move(self, event) -> None:
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        self._root.geometry(f"+{x}+{y}")

    def _minimize(self) -> None:
        """Temporarily restore system frame to allow iconify, then re-hide it."""
        self._root.overrideredirect(False)
        self._root.iconify()

        def bind_restore():
            def on_map(event):
                if event.widget is not self._root:
                    return
                self._root.overrideredirect(True)
                self._root.unbind("<Map>")
            self._root.bind("<Map>", on_map)

        # Delay binding so the <Map> from overrideredirect(False) doesn't trigger it
        self._root.after(200, bind_restore)

    def _build_toolbar(self) -> None:
        bar = tk.Frame(self._main, bg=CLR_BG, pady=6)
        bar.pack(fill=tk.X, padx=8)

        def mk_btn(parent, text, bg, hover, cmd, state=tk.NORMAL):
            b = tk.Button(parent, text=text, bg=bg, fg="white",
                          activebackground=hover, activeforeground="white",
                          relief=tk.FLAT, padx=12, pady=4,
                          font=("Microsoft YaHei", 9),
                          bd=0, cursor="hand2", command=cmd, state=state)
            return b

        self._run_btn = mk_btn(bar, "▶  运行", CLR_RUN, CLR_RUN_HOV, self._on_run)
        self._run_btn.pack(side=tk.LEFT, padx=(0, 4))

        self._stop_btn = mk_btn(bar, "■  停止", CLR_STOP, CLR_STOP_HOV,
                                self._on_stop, state=tk.DISABLED)
        self._stop_btn.pack(side=tk.LEFT, padx=(0, 4))

        tk.Button(bar, text="⚙", bg=CLR_BG3, fg=CLR_FG_DIM,
                  activebackground=CLR_BORDER, activeforeground=CLR_FG,
                  relief=tk.FLAT, padx=8, pady=4, bd=0, cursor="hand2",
                  font=("", 11), command=self._open_settings).pack(side=tk.LEFT)

        # Status dot
        self._status_dot = tk.Label(bar, text="●", fg=CLR_DISABLED,
                                    bg=CLR_BG, font=("", 13))
        self._status_dot.pack(side=tk.RIGHT, padx=4)

    def _build_settings_bar(self) -> None:
        bar = tk.Frame(self._main, bg=CLR_BG2, pady=5)
        bar.pack(fill=tk.X, padx=8, pady=(0, 4))

        def lbl(parent, text):
            return tk.Label(parent, text=text, bg=CLR_BG2,
                            fg=CLR_FG_DIM, font=("Microsoft YaHei", 8))

        def entry(parent, var, width):
            return tk.Entry(parent, textvariable=var, width=width,
                            bg=CLR_BG3, fg=CLR_FG, insertbackground=CLR_FG,
                            relief=tk.FLAT, font=("Consolas", 9),
                            highlightthickness=1,
                            highlightbackground=CLR_BORDER,
                            highlightcolor=CLR_ACCENT)

        lbl(bar, " 热键:").pack(side=tk.LEFT)
        self._hotkey_var = tk.StringVar(value=self._settings.start_stop_hotkey.upper())
        tk.Label(bar, textvariable=self._hotkey_var, bg=CLR_BG2,
                 fg=CLR_ACCENT, font=("Consolas", 9, "bold")).pack(side=tk.LEFT, padx=(2, 10))

        lbl(bar, "重复:").pack(side=tk.LEFT)
        self._repeat_var = tk.StringVar(value="1")
        entry(bar, self._repeat_var, 4).pack(side=tk.LEFT, padx=(2, 10))

        lbl(bar, "间隔(ms):").pack(side=tk.LEFT)
        self._interval_var = tk.StringVar(value="100")
        entry(bar, self._interval_var, 5).pack(side=tk.LEFT, padx=2)

    def _build_action_list(self) -> None:
        list_frame = tk.Frame(self._main, bg=CLR_BG)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 2))

        # Header
        header = tk.Frame(list_frame, bg=CLR_BG3, pady=3)
        header.pack(fill=tk.X)
        for text, w in [("  #", 3), ("类型", 7), ("描述", 20), ("验", 3), ("跳", 4), ("◆", 2), ("状", 3)]:
            tk.Label(header, text=text, bg=CLR_BG3, fg=CLR_FG_DIM,
                     width=w, font=("Microsoft YaHei", 8), anchor="w").pack(side=tk.LEFT, padx=2)

        # Listbox + custom scrollbar
        lb_frame = tk.Frame(list_frame, bg=CLR_BG)
        lb_frame.pack(fill=tk.BOTH, expand=True)

        self._listbox = tk.Listbox(
            lb_frame,
            bg="#18191c", fg=CLR_FG,
            selectbackground=CLR_HIGHLIGHT,
            selectforeground="white",
            activestyle="none",
            font=("Consolas", 9),
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=0,
        )
        self._listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Custom slim scrollbar using Canvas
        self._sb_canvas = tk.Canvas(lb_frame, width=6, bg=CLR_BG,
                                    highlightthickness=0, cursor="arrow")
        self._sb_canvas.pack(side=tk.RIGHT, fill=tk.Y)
        self._sb_thumb = self._sb_canvas.create_rectangle(
            0, 0, 6, 40, fill="#4a4d52", outline="", tags="thumb")

        self._listbox.configure(yscrollcommand=self._on_listbox_scroll)
        self._sb_canvas.bind("<ButtonPress-1>", self._on_sb_click)
        self._sb_canvas.bind("<B1-Motion>", self._on_sb_drag)
        self._sb_canvas.bind("<MouseWheel>", lambda e: self._listbox.yview_scroll(
            -1 if e.delta > 0 else 1, "units"))
        self._listbox.bind("<MouseWheel>", lambda e: self._listbox.yview_scroll(
            -1 if e.delta > 0 else 1, "units"))
        self._sb_drag_start_y = 0
        self._sb_drag_start_frac = 0.0

        self._listbox.bind("<ButtonPress-1>", self._on_list_press)
        self._listbox.bind("<B1-Motion>", self._on_list_drag)
        self._listbox.bind("<ButtonRelease-1>", self._on_list_release)
        self._listbox.bind("<Double-Button-1>", self._on_double_click)
        self._listbox.bind("<Button-3>", self._on_right_click)

    def _on_listbox_scroll(self, first: str, last: str) -> None:
        """Update custom scrollbar thumb position."""
        first, last = float(first), float(last)
        h = self._sb_canvas.winfo_height()
        if h <= 1:
            return
        y0 = int(first * h)
        y1 = int(last * h)
        y1 = max(y1, y0 + 8)
        self._sb_canvas.coords(self._sb_thumb, 1, y0, 5, y1)
        # Hide thumb if all items visible
        if first <= 0.0 and last >= 1.0:
            self._sb_canvas.itemconfig(self._sb_thumb, fill="")
        else:
            self._sb_canvas.itemconfig(self._sb_thumb, fill="#4a4d52")

    def _on_sb_click(self, event) -> None:
        coords = self._sb_canvas.coords(self._sb_thumb)
        if not coords:
            return
        self._sb_drag_start_y = event.y
        self._sb_drag_start_frac = float(self._listbox.yview()[0])

    def _on_sb_drag(self, event) -> None:
        h = self._sb_canvas.winfo_height()
        if h <= 0:
            return
        delta = (event.y - self._sb_drag_start_y) / h
        self._listbox.yview_moveto(self._sb_drag_start_frac + delta)

    # ------------------------------------------------------------------
    # Drag-to-reorder handlers
    # ------------------------------------------------------------------

    def _on_list_press(self, event) -> None:
        idx = self._listbox.nearest(event.y)
        if 0 <= idx < len(self._expanded_map):
            self._drag_idx = idx
            self._drag_start_y = event.y
            self._dragging = False
            self._drag_last_hover = idx
        else:
            self._drag_idx = None

    def _on_list_drag(self, event) -> None:
        if self._drag_idx is None:
            return
        dy = abs(event.y - self._drag_start_y)
        if not self._dragging and dy < self._DRAG_THRESHOLD:
            return
        if not self._dragging:
            self._dragging = True
            self._listbox.configure(cursor="exchange")
        target = self._listbox.nearest(event.y)
        if target < 0:
            target = 0
        elif target >= len(self._expanded_map):
            target = len(self._expanded_map) - 1
        if target != self._drag_last_hover:
            self._listbox.selection_clear(0, tk.END)
            self._listbox.selection_set(target)
            self._drag_last_hover = target

    def _on_list_release(self, event) -> None:
        self._listbox.configure(cursor="")
        if not self._dragging:
            self._drag_idx = None
            return
        self._dragging = False
        from_row = self._drag_idx
        self._drag_idx = None
        if from_row is None:
            return
        to_row = self._listbox.nearest(event.y)
        if to_row < 0:
            to_row = 0
        elif to_row >= len(self._expanded_map):
            to_row = len(self._expanded_map) - 1
        if to_row == from_row:
            self._listbox.selection_clear(0, tk.END)
            self._listbox.selection_set(to_row)
            return

        from_act, from_parent, _ = self._expanded_map[from_row]
        to_act, to_parent, _ = self._expanded_map[to_row]

        # Case: drag child out of group
        if from_parent is not None:
            if isinstance(from_act, ActionGroup) and from_act.children:
                self._status_bar.set("不能将非空动作组拖入其他动作组")
                return
            from_parent.children.remove(from_act)
            if isinstance(to_act, ActionGroup):
                to_act.children.append(from_act)
            elif to_parent is not None:
                idx = to_parent.children.index(to_act)
                to_parent.children.insert(idx, from_act)
            else:
                self._actions.append(from_act)
            self._refresh_list()
            return

        # Case: drag onto group → add as child (only if dragged item is not a non-empty group)
        if isinstance(to_act, ActionGroup):
            if from_act is to_act:
                return
            if isinstance(from_act, ActionGroup) and from_act.children:
                self._status_bar.set("不能将非空动作组拖入其他动作组")
                return
            if from_act in self._actions:
                self._actions.remove(from_act)
            to_act.children.append(from_act)
            self._status_bar.set(f"已移入动作组: {len(to_act.children)}个子动作")
            self._refresh_list()
            return

        # Case: drag onto a child → add to that child's parent
        if to_parent is not None:
            if isinstance(from_act, ActionGroup) and from_act.children:
                self._status_bar.set("不能将非空动作组拖入其他动作组")
                return
            if from_act in self._actions:
                self._actions.remove(from_act)
            idx = to_parent.children.index(to_act)
            to_parent.children.insert(idx, from_act)
            self._refresh_list()
            return

        # Case: both top-level → normal reorder
        if from_act in self._actions and to_act in self._actions:
            from_ai = self._actions.index(from_act)
            to_ai = self._actions.index(to_act)
            if from_ai != to_ai:
                self._reorder_action(from_ai, to_ai)
            else:
                self._listbox.selection_clear(0, tk.END)
                self._listbox.selection_set(to_row)

    def _reorder_action(self, from_idx: int, to_idx: int) -> None:
        old_actions = self._actions[:]
        action = self._actions.pop(from_idx)
        self._actions.insert(to_idx, action)
        self._fix_jump_refs_after_reorder(old_actions)
        self._refresh_list()
        self._listbox.selection_clear(0, tk.END)
        self._listbox.selection_set(to_idx)

    # ------------------------------------------------------------------
    # Jump reference auto-update helpers
    # ------------------------------------------------------------------

    def _fix_jump_refs_after_reorder(self, old_actions: list[AnyAction]) -> None:
        """After reordering, update on_fail_jump to track the same target objects."""
        old_ids = [id(a) for a in old_actions]
        id_to_new_idx: dict[int, int] = {}
        for new_idx, action in enumerate(self._actions):
            id_to_new_idx[id(action)] = new_idx
        for action in self._actions:
            if action.on_fail_jump >= 0 and action.on_fail_jump < len(old_ids):
                target_id = old_ids[action.on_fail_jump]
                action.on_fail_jump = id_to_new_idx.get(target_id, -1)

    def _fix_jump_refs_after_delete(self, deleted_idx: int) -> None:
        """After deleting an action, update all on_fail_jump references."""
        for action in self._actions:
            if action.on_fail_jump == deleted_idx:
                action.on_fail_jump = -1
            elif action.on_fail_jump > deleted_idx:
                action.on_fail_jump -= 1

    def _build_action_buttons(self) -> None:
        bar = tk.Frame(self._main, bg=CLR_BG, pady=4)
        bar.pack(fill=tk.X, padx=8)

        def mk(text, cmd, bg=CLR_BG3, fg=CLR_FG, w=None):
            kw = dict(bg=bg, fg=fg, activebackground=CLR_BORDER,
                      activeforeground=CLR_FG, relief=tk.FLAT,
                      padx=8, pady=3, bd=0, cursor="hand2",
                      font=("Microsoft YaHei", 8), command=cmd)
            if w:
                kw["width"] = w
            return tk.Button(bar, text=text, **kw)

        mk("＋ 添加", self._on_add).pack(side=tk.LEFT, padx=(0, 2))
        mk("↑", self._on_move_up, w=2).pack(side=tk.LEFT, padx=2)
        mk("↓", self._on_move_down, w=2).pack(side=tk.LEFT, padx=2)
        mk("✕ 删除", self._on_delete, bg="#4a1a1a", fg="#e08080").pack(side=tk.LEFT, padx=2)

    def _build_io_buttons(self) -> None:
        bar = tk.Frame(self._main, bg=CLR_BG, pady=2)
        bar.pack(fill=tk.X, padx=8, pady=(0, 6))

        def mk(text, cmd):
            return tk.Button(bar, text=text, bg=CLR_BG, fg=CLR_FG_DIM,
                             activebackground=CLR_BG3, activeforeground=CLR_FG,
                             relief=tk.FLAT, padx=6, pady=2, bd=0, cursor="hand2",
                             font=("Microsoft YaHei", 8), command=cmd)

        mk("↥ 导入", self._on_import).pack(side=tk.LEFT, padx=(0, 2))
        mk("↧ 导出", self._on_export).pack(side=tk.LEFT)

        self._ocr_status_var = tk.StringVar(value="OCR: 加载中...")
        tk.Label(bar, textvariable=self._ocr_status_var,
                 bg=CLR_BG, fg=CLR_DISABLED,
                 font=("Microsoft YaHei", 7)).pack(side=tk.RIGHT, padx=4)

    # ------------------------------------------------------------------
    # Action list management
    # ------------------------------------------------------------------

    def _refresh_list(self) -> None:
        self._listbox.delete(0, tk.END)
        self._expanded_map = self._build_expanded_map()
        jump_targets: set[int] = {a.on_fail_jump for a in self._actions if a.on_fail_jump >= 0}
        # Assign numbers to top-level entries only
        top_num = 0
        for row_idx, (act, parent, depth) in enumerate(self._expanded_map):
            indent = "    " * depth
            is_group = isinstance(act, ActionGroup)
            iv_mark = " I" if act.image_verify.enabled and act.image_verify.template_data else ""

            if parent is not None:
                # Child row — no number
                tl = ACTION_TYPE_LABELS.get(act.action_type, "?")
                desc = act.label if act.label else act.description()
                verify_mark = "V" if act.text_verify.enabled else " "
                if is_group:
                    n = len(act.children)
                    lbl = act.label if act.label else "子动作组"
                    desc = f"[{n}个子动作]"
                    line = f"{indent}📁 {lbl:<10} {desc:<12} {verify_mark}{iv_mark}"
                else:
                    line = f"{indent}{tl:<5}  {desc:<20}  {verify_mark}{iv_mark}"
                self._listbox.insert(tk.END, line)
                if not act.enabled:
                    self._listbox.itemconfig(row_idx, fg=CLR_DISABLED)
                else:
                    self._listbox.itemconfig(row_idx, fg="#70a0c0")
                continue

            # Top-level entries
            top_num += 1
            if is_group:
                n = len(act.children)
                lbl = act.label if act.label else f"动作组{top_num}"
                desc = f"[{n}个子动作]"
                line = f"{top_num:>2}  {'📁':<2} {lbl:<12} {desc:<12} {iv_mark}"
                self._listbox.insert(tk.END, line)
                if not act.enabled:
                    self._listbox.itemconfig(row_idx, fg=CLR_DISABLED)
                elif act.image_verify.enabled and act.image_verify.template_data:
                    self._listbox.itemconfig(row_idx, fg="#00dddd")
                else:
                    self._listbox.itemconfig(row_idx, fg="#00cccc")
            else:
                type_lbl = ACTION_TYPE_LABELS.get(act.action_type, "?")
                desc = act.label if act.label else act.description()
                verify_mark = "V" if act.text_verify.enabled else " "
                jump_mark = f"→{act.on_fail_jump + 1}" if act.on_fail_jump >= 0 else " "
                ai = self._actions.index(act) if act in self._actions else -1
                is_target = ai in jump_targets
                target_mark = "◆" if is_target else " "
                enabled_mark = "✓" if act.enabled else "✗"
                line = f"{top_num:>2}  {type_lbl:<5}  {desc:<24}  {verify_mark}{iv_mark}  {jump_mark:<3}  {target_mark}  {enabled_mark}"
                self._listbox.insert(tk.END, line)
                if not act.enabled:
                    self._listbox.itemconfig(row_idx, fg=CLR_DISABLED)
                elif is_target:
                    self._listbox.itemconfig(row_idx, fg="#9a70c0")
                elif act.on_fail_jump >= 0:
                    self._listbox.itemconfig(row_idx, fg="#e0a030")
                elif act.text_verify.enabled:
                    self._listbox.itemconfig(row_idx, fg=CLR_VERIFY)

    def _selected_index(self) -> Optional[int]:
        sel = self._listbox.curselection()
        return sel[0] if sel else None

    def _highlight_step(self, idx: int) -> None:
        self._listbox.selection_clear(0, tk.END)
        if 0 <= idx < self._listbox.size():
            self._listbox.selection_set(idx)
            self._listbox.see(idx)

    # ------------------------------------------------------------------
    # Expanded index mapping for group children
    # ------------------------------------------------------------------

    def _build_expanded_map(self) -> list[tuple[AnyAction, Optional[AnyAction], int]]:
        """Build expanded index mapping, recursively expanding nested ActionGroups.
        Each entry: (action, parent_group_or_none, depth)."""
        mapping: list[tuple[AnyAction, Optional[AnyAction], int]] = []
        for action in self._actions:
            mapping.append((action, None, 0))
            if isinstance(action, ActionGroup):
                self._expand_children(mapping, action, 1)
        return mapping

    def _expand_children(self, mapping, parent, depth: int) -> None:
        """Recursively expand children of an ActionGroup into the mapping."""
        if not isinstance(parent, ActionGroup):
            return
        for child in parent.children:
            mapping.append((child, parent, depth))
            if isinstance(child, ActionGroup):
                self._expand_children(mapping, child, depth + 1)

    def _is_child_row(self, row_idx: int) -> bool:
        if 0 <= row_idx < len(self._expanded_map):
            return self._expanded_map[row_idx][1] is not None
        return False

    def _is_group_header_row(self, row_idx: int) -> bool:
        if 0 <= row_idx < len(self._expanded_map):
            act, _, _ = self._expanded_map[row_idx]
            return isinstance(act, ActionGroup)
        return False

    def _selected_expanded(self) -> Optional[tuple[AnyAction, Optional[AnyAction], int]]:
        sel = self._listbox.curselection()
        if not sel:
            return None
        row_idx = sel[0]
        if 0 <= row_idx < len(self._expanded_map):
            return self._expanded_map[row_idx]
        return None

    def _find_next_top_level(self, row_idx: int, delta: int) -> Optional[int]:
        """Find the next top-level row index, skipping child rows."""
        r = row_idx + delta
        while 0 <= r < len(self._expanded_map):
            if not self._is_child_row(r):
                return r
            r += delta
        return None

    # ------------------------------------------------------------------
    # Toolbar actions
    # ------------------------------------------------------------------

    def _on_run(self) -> None:
        if not self._actions:
            messagebox.showinfo("提示", "请先添加动作步骤", parent=self._root)
            return
        settings = self._collect_settings()
        self._executor.start(self._actions[:], settings)
        self._run_btn.config(state=tk.DISABLED)
        self._stop_btn.config(state=tk.NORMAL)
        self._status_dot.config(fg="#00cc00")

    def _on_stop(self) -> None:
        self._executor.stop()

    def _open_settings(self) -> None:
        SettingsDialog(self._root, self._settings, self._on_settings_saved, self._actions)

    def _on_settings_saved(self, settings: GlobalSettings) -> None:
        self._settings = settings
        self._hotkey_var.set(settings.start_stop_hotkey.upper())
        self._repeat_var.set(str(settings.repeat_count))
        self._interval_var.set(str(settings.interval_ms))
        self._hotkey_listener.update_hotkey(settings.start_stop_hotkey)
        self._refresh_list()
        # Start/stop window monitor based on new settings
        if settings.window_monitor_locked and not self._monitor_active:
            self._start_window_monitor()
        elif not settings.window_monitor_locked and self._monitor_active:
            self._stop_window_monitor()

    def _collect_settings(self) -> GlobalSettings:
        s = GlobalSettings(
            repeat_count=int(self._repeat_var.get() or 1),
            interval_ms=int(self._interval_var.get() or 100),
            random_delay_min_ms=self._settings.random_delay_min_ms,
            random_delay_max_ms=self._settings.random_delay_max_ms,
            start_stop_hotkey=self._settings.start_stop_hotkey,
            stop_on_error=self._settings.stop_on_error,
            target_window_title=self._settings.target_window_title,
            reference_window_width=self._settings.reference_window_width,
            reference_window_height=self._settings.reference_window_height,
            mouse_speed_ms=self._settings.mouse_speed_ms,
            window_monitor_locked=self._settings.window_monitor_locked,
            relative_coords_enabled=self._settings.relative_coords_enabled,
        )
        return s

    # ------------------------------------------------------------------
    # Action CRUD
    # ------------------------------------------------------------------

    def _on_add(self) -> None:
        editor = ActionEditor(self._root,
                              target_window_title=self._settings.target_window_title,
                              relative_coords_enabled=self._settings.relative_coords_enabled)
        self._root.wait_window(editor)
        if editor.result:
            self._actions.append(editor.result)
            self._refresh_list()
            self._listbox.selection_set(len(self._actions) - 1)

    def _on_double_click(self, event=None) -> None:
        exp = self._selected_expanded()
        if exp is None:
            return
        act, parent, depth = exp
        row_idx = self._listbox.curselection()[0]

        if parent is not None:
            # Double-click on child: edit it
            editor = ActionEditor(self._root, initial=act,
                                  target_window_title=self._settings.target_window_title,
                                  relative_coords_enabled=self._settings.relative_coords_enabled)
            self._root.wait_window(editor)
            if editor.result:
                editor.result.text_verify = act.text_verify
                editor.result.on_fail_jump = act.on_fail_jump
                idx = parent.children.index(act)
                parent.children[idx] = editor.result
                self._refresh_list()
            return

        action = act
        editor = ActionEditor(self._root, initial=action,
                              target_window_title=self._settings.target_window_title,
                              relative_coords_enabled=self._settings.relative_coords_enabled)
        self._root.wait_window(editor)
        if editor.result:
            if isinstance(action, ActionGroup):
                editor.result.text_verify = action.text_verify
                editor.result.on_fail_jump = action.on_fail_jump
                editor.result.children = action.children
            else:
                editor.result.text_verify = action.text_verify
                editor.result.on_fail_jump = action.on_fail_jump
            ai = self._actions.index(act)
            self._actions[ai] = editor.result
            self._refresh_list()
            self._listbox.selection_set(row_idx)

    def _on_delete(self) -> None:
        exp = self._selected_expanded()
        if exp is None:
            return
        act, parent, _ = exp
        row_idx = self._listbox.curselection()[0]
        if parent is not None:
            ci = parent.children.index(act)
            for c in parent.children:
                if c.on_fail_jump == ci:
                    c.on_fail_jump = -1
                elif c.on_fail_jump > ci:
                    c.on_fail_jump -= 1
            parent.children.remove(act)
            self._refresh_list()
            return
        if act in self._actions:
            ai = self._actions.index(act)
            self._fix_jump_refs_after_delete(ai)
            self._actions.remove(act)
            self._refresh_list()
            if self._actions:
                new_row = self._find_next_top_level(row_idx, -1)
                if new_row is None:
                    new_row = self._find_next_top_level(row_idx, 1)
                if new_row is not None:
                    self._listbox.selection_set(new_row)

    def _on_move_up(self) -> None:
        row_idx = self._selected_index()
        if row_idx is None or self._is_child_row(row_idx):
            return
        prev_row = self._find_next_top_level(row_idx, -1)
        if prev_row is None:
            return
        act = self._expanded_map[row_idx][0]
        prev_act = self._expanded_map[prev_row][0]
        if act in self._actions and prev_act in self._actions:
            ai = self._actions.index(act)
            pi = self._actions.index(prev_act)
            old_actions = self._actions[:]
            self._actions[pi], self._actions[ai] = self._actions[ai], self._actions[pi]
            self._fix_jump_refs_after_reorder(old_actions)
            self._refresh_list()
            self._listbox.selection_set(prev_row)

    def _on_move_down(self) -> None:
        row_idx = self._selected_index()
        if row_idx is None or self._is_child_row(row_idx):
            return
        next_row = self._find_next_top_level(row_idx, 1)
        if next_row is None:
            return
        act = self._expanded_map[row_idx][0]
        next_act = self._expanded_map[next_row][0]
        if act in self._actions and next_act in self._actions:
            ai = self._actions.index(act)
            ni = self._actions.index(next_act)
            old_actions = self._actions[:]
            self._actions[ni], self._actions[ai] = self._actions[ai], self._actions[ni]
            self._fix_jump_refs_after_reorder(old_actions)
            self._refresh_list()
            self._listbox.selection_set(next_row)

    # ------------------------------------------------------------------
    # Right-click context menu
    # ------------------------------------------------------------------

    def _on_right_click(self, event) -> None:
        row_idx = self._listbox.nearest(event.y)
        if row_idx < 0 or row_idx >= len(self._expanded_map):
            return
        self._listbox.selection_clear(0, tk.END)
        self._listbox.selection_set(row_idx)

        act, parent, depth = self._expanded_map[row_idx]

        if parent is not None:
            # Right-click on child
            menu = tk.Menu(self._root, tearoff=0, bg=CLR_BG2, fg=CLR_FG,
                           activebackground=CLR_HIGHLIGHT, activeforeground="white")
            menu.add_command(label="编辑", command=lambda: self._edit_child_action2(act, parent))
            menu.add_command(label="文字验证", command=lambda: self._open_child_text_verify2(act, parent))
            menu.add_separator()
            toggle = "禁用" if act.enabled else "启用"
            menu.add_command(label=toggle, command=lambda: self._toggle_child2(act, parent))
            menu.add_separator()
            menu.add_command(label="从组中移出", command=lambda: self._remove_child_from_group2(act, parent))
            menu.add_command(label="删除", command=lambda: self._delete_child_action2(act, parent))
            menu.tk_popup(event.x_root, event.y_root)
            return

        # Top-level row
        idx = self._actions.index(act) if act in self._actions else -1
        menu = tk.Menu(self._root, tearoff=0, bg=CLR_BG2, fg=CLR_FG,
                       activebackground=CLR_HIGHLIGHT, activeforeground="white")
        menu.add_command(label="编辑", command=lambda: self._on_double_click())
        menu.add_command(label="文字验证", command=lambda: self._open_text_verify(idx))
        menu.add_command(label="设置联动", command=lambda: self._open_jump_dialog(idx))
        menu.add_separator()

        action = self._actions[idx]
        toggle_label = "禁用" if action.enabled else "启用"
        menu.add_command(label=toggle_label, command=lambda: self._toggle_enabled(idx))
        menu.add_separator()
        menu.add_command(label="上移", command=self._on_move_up)
        menu.add_command(label="下移", command=self._on_move_down)
        menu.add_separator()
        menu.add_command(label="删除", command=self._on_delete)

        menu.tk_popup(event.x_root, event.y_root)

    def _edit_child_action2(self, child, parent) -> None:
        editor = ActionEditor(self._root, initial=child,
                              target_window_title=self._settings.target_window_title,
                              relative_coords_enabled=self._settings.relative_coords_enabled)
        self._root.wait_window(editor)
        if editor.result:
            editor.result.text_verify = child.text_verify
            editor.result.on_fail_jump = child.on_fail_jump
            idx = parent.children.index(child)
            parent.children[idx] = editor.result
            self._refresh_list()

    def _open_child_text_verify2(self, child, parent) -> None:
        dlg = TextVerifyDialog(self._root, self._ocr, initial=child.text_verify)
        self._root.wait_window(dlg)
        if dlg.result is not None:
            child.text_verify = dlg.result
            self._refresh_list()

    def _toggle_child2(self, child, parent) -> None:
        child.enabled = not child.enabled
        self._refresh_list()

    def _remove_child_from_group2(self, child, parent) -> None:
        parent.children.remove(child)
        self._actions.append(child)
        self._refresh_list()

    def _delete_child_action2(self, child, parent) -> None:
        ci = parent.children.index(child)
        for c in parent.children:
            if c.on_fail_jump == ci:
                c.on_fail_jump = -1
            elif c.on_fail_jump > ci:
                c.on_fail_jump -= 1
        parent.children.remove(child)
        self._refresh_list()

    def _open_text_verify(self, idx: int) -> None:
        action = self._actions[idx]
        dlg = TextVerifyDialog(self._root, self._ocr, initial=action.text_verify)
        self._root.wait_window(dlg)
        if dlg.result is not None:
            action.text_verify = dlg.result
            self._refresh_list()

    def _toggle_enabled(self, idx: int) -> None:
        self._actions[idx].enabled = not self._actions[idx].enabled
        self._refresh_list()
        self._listbox.selection_set(idx)

    def _open_jump_dialog(self, idx: int) -> None:
        JumpDialog(self._root, idx, self._actions, self._on_jump_saved)

    def _on_jump_saved(self, src_idx: int, target_idx: int) -> None:
        self._actions[src_idx].on_fail_jump = target_idx
        self._refresh_list()
        self._listbox.selection_set(src_idx)

    # ------------------------------------------------------------------
    # Import / Export
    # ------------------------------------------------------------------

    def _on_export(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self._root,
            defaultextension=".json",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
            title="导出宏配置",
        )
        if not path:
            return
        try:
            settings = self._collect_settings()
            ConfigManager.export(self._actions, settings, path)
            self._status_bar.set(f"已导出: {path}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e), parent=self._root)

    def _on_import(self) -> None:
        path = filedialog.askopenfilename(
            parent=self._root,
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
            title="导入宏配置",
        )
        if not path:
            return
        try:
            actions, settings = ConfigManager.import_file(path)
            self._actions = actions
            self._settings = settings
            self._hotkey_var.set(settings.start_stop_hotkey.upper())
            self._repeat_var.set(str(settings.repeat_count))
            self._interval_var.set(str(settings.interval_ms))
            self._refresh_list()
            self._hotkey_listener.update_hotkey(settings.start_stop_hotkey)
            self._status_bar.set(f"已导入: {path}  ({len(actions)} 个步骤)")
        except Exception as e:
            messagebox.showerror("导入失败", str(e), parent=self._root)

    # ------------------------------------------------------------------
    # Executor callback & hotkey
    # ------------------------------------------------------------------

    def _setup_executor_callback(self) -> None:
        def on_status(msg: str, step_idx: int) -> None:
            # Schedule UI update on main thread
            self._root.after(0, self._on_executor_status, msg, step_idx)

        self._executor.set_status_callback(on_status)

    def _on_executor_status(self, msg: str, step_idx: int) -> None:
        self._status_bar.set(msg)
        if step_idx >= 0:
            self._highlight_step(step_idx)
        if msg == "已停止":
            self._run_btn.config(state=tk.NORMAL)
            self._stop_btn.config(state=tk.DISABLED)
            self._status_dot.config(fg=CLR_DISABLED)

    def _start_hotkey_listener(self) -> None:
        self._hotkey_listener.set_callbacks(
            get_actions=lambda: self._actions[:],
            get_settings=self._collect_settings,
        )
        self._hotkey_listener.start(self._settings.start_stop_hotkey)

    def _warm_up_ocr(self) -> None:
        def run():
            try:
                self._ocr.warm_up()
                self._root.after(0, lambda: self._ocr_status_var.set("OCR: 就绪"))
            except Exception as e:
                self._root.after(0, lambda: self._ocr_status_var.set("OCR: 不可用"))

        threading.Thread(target=run, daemon=True).start()

    # ------------------------------------------------------------------
    # Window monitor (continuous resolution tracking)
    # ------------------------------------------------------------------

    def _start_window_monitor(self) -> None:
        """Start a background thread that tracks the target window's resolution."""
        if self._monitor_active:
            return
        self._monitor_active = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, daemon=True, name="WindowMonitor")
        self._monitor_thread.start()
        self._status_bar.set("窗口监控已开启")

    def _stop_window_monitor(self) -> None:
        """Stop the window monitor thread."""
        self._monitor_active = False
        self._monitor_thread = None
        self._status_bar.set("窗口监控已停止")

    def is_window_monitor_active(self) -> bool:
        return self._monitor_active

    def _monitor_loop(self) -> None:
        """Periodically check target window position and size."""
        from core.win_utils import find_window_by_title, get_window_rect
        while self._monitor_active:
            title = self._settings.target_window_title
            if title:
                hwnd = find_window_by_title(title)
                if hwnd:
                    rect = get_window_rect(hwnd)
                    if rect:
                        w, h = rect[2] - rect[0], rect[3] - rect[1]
                        if w > 0 and h > 0:
                            changed = (self._settings.reference_window_width != w or
                                       self._settings.reference_window_height != h)
                            if changed:
                                self._settings.reference_window_width = w
                                self._settings.reference_window_height = h
                                self._root.after(0, self._status_bar.set,
                                    f"窗口分辨率已更新: {w}x{h}")
            time.sleep(3)

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._root.mainloop()

    def _on_close(self) -> None:
        self._executor.stop()
        self._hotkey_listener.stop()
        self._monitor_active = False
        self._root.destroy()


# ------------------------------------------------------------------
# Settings dialog
# ------------------------------------------------------------------

class SettingsDialog(tk.Toplevel):
    """Global settings dialog."""

    def __init__(self, parent, settings: GlobalSettings, on_save,
                 actions: list = None) -> None:
        super().__init__(parent)
        self.title("全局设置")
        self.resizable(False, False)
        self.grab_set()
        self.transient(parent)
        self.configure(bg=CLR_BG)
        self._on_save = on_save
        self._actions = actions or []
        self._convert_timer: Optional[str] = None
        self._build(settings)
        self.update_idletasks()
        self.geometry(f"+{parent.winfo_rootx() + 50}+{parent.winfo_rooty() + 50}")

    def _build(self, s: GlobalSettings) -> None:
        from core.action import CoordMode
        from ui.widgets import BG, BG2, BG3, FG, FG_DIM, ACCENT, BORDER, SectionFrame
        from ui.widgets import label as wlabel, entry as wentry
        from ui.widgets import checkbutton as wcheck, button as wbtn, separator

        self.configure(bg=BG)

        sec = SectionFrame(self, "运行设置")
        sec.pack(fill=tk.X, padx=10, pady=(10, 4))

        self._hotkey_var    = tk.StringVar(value=s.start_stop_hotkey)
        self._repeat_var    = tk.StringVar(value=str(s.repeat_count))
        self._interval_var  = tk.StringVar(value=str(s.interval_ms))
        self._rnd_min_var   = tk.StringVar(value=str(s.random_delay_min_ms))
        self._rnd_max_var   = tk.StringVar(value=str(s.random_delay_max_ms))
        self._stop_on_err_var = tk.BooleanVar(value=s.stop_on_error)

        def row(lbl, var, width=10):
            f = tk.Frame(sec, bg=BG2)
            f.pack(fill=tk.X, pady=3)
            wlabel(f, lbl, dim=True, width=18, anchor="w").pack(side=tk.LEFT)
            wentry(f, var, width=width).pack(side=tk.LEFT, padx=(6, 0))

        row("启动/停止热键:", self._hotkey_var)
        row("重复次数 (0=无限):", self._repeat_var)
        row("步骤间隔(ms):", self._interval_var)
        row("随机延迟最小(ms):", self._rnd_min_var)
        row("随机延迟最大(ms):", self._rnd_max_var)

        f = tk.Frame(sec, bg=BG2)
        f.pack(fill=tk.X, pady=(6, 0))
        wcheck(f, "出错时停止", self._stop_on_err_var).pack(anchor="w")

        # Mouse speed
        spd_f = tk.Frame(sec, bg=BG2)
        spd_f.pack(fill=tk.X, pady=3)
        wlabel(spd_f, "鼠标移动速度(ms):", dim=True, width=18, anchor="w").pack(side=tk.LEFT)
        self._mouse_speed_var = tk.StringVar(value=str(s.mouse_speed_ms))
        wentry(spd_f, self._mouse_speed_var, width=7).pack(side=tk.LEFT, padx=(6, 0))

        # Advanced: relative coordinates (collapsed by default)
        self._rel_enabled_var = tk.BooleanVar(value=s.relative_coords_enabled)
        adv_toggle_row = tk.Frame(self, bg=BG)
        adv_toggle_row.pack(fill=tk.X, padx=10, pady=(10, 0))
        self._adv_toggle_btn = wbtn(adv_toggle_row,
             "▸ 高级坐标功能（相对窗口）" if not s.relative_coords_enabled
             else "▾ 高级坐标功能（相对窗口）",
             self._toggle_advanced, accent=True)
        self._adv_toggle_btn.pack(side=tk.LEFT)

        # Container for all advanced relative-coords widgets
        self._advanced_frame = tk.Frame(self, bg=BG)

        # Target window
        win_sec = SectionFrame(self._advanced_frame, "相对窗口设置")
        win_sec.pack(fill=tk.X, padx=2, pady=(4, 2))

        wf = tk.Frame(win_sec, bg=BG2)
        wf.pack(fill=tk.X, pady=3)
        wlabel(wf, "目标窗口标题:", dim=True, width=18, anchor="w").pack(side=tk.LEFT)
        self._target_win_var = tk.StringVar(value=s.target_window_title)
        wentry(wf, self._target_win_var, width=22).pack(side=tk.LEFT, padx=(6, 4))
        wbtn(wf, "拾取窗口", self._pick_target_window).pack(side=tk.LEFT, padx=(4, 0))

        # Lock toggle for continuous monitoring
        self._lock_var = tk.BooleanVar(value=s.window_monitor_locked)
        self._lock_btn = wbtn(wf, self._lock_label(),
                              self._toggle_lock)
        self._lock_btn.pack(side=tk.LEFT, padx=(8, 0))

        ref_f = tk.Frame(win_sec, bg=BG2)
        ref_f.pack(fill=tk.X, pady=3)
        wlabel(ref_f, "参考分辨率:", dim=True, width=18, anchor="w").pack(side=tk.LEFT)
        ref_text = f"{s.reference_window_width} x {s.reference_window_height}" if s.reference_window_width > 0 else "未设置"
        self._ref_label = wlabel(ref_f, ref_text, dim=True)
        self._ref_label.pack(side=tk.LEFT, padx=(6, 0))
        wlabel(ref_f, "(拾取窗口时自动填充)", dim=True).pack(side=tk.LEFT, padx=(4, 0))
        # Store ref values for save
        self._ref_w = s.reference_window_width
        self._ref_h = s.reference_window_height

        # Bulk convert all actions
        self._cvt_sec = SectionFrame(self._advanced_frame, "批量切换坐标模式")
        self._cvt_sec.pack(fill=tk.X, padx=2, pady=(8, 2))
        self._refresh_convert_section()

        # Show/hide advanced frame based on initial state
        if s.relative_coords_enabled:
            self._advanced_frame.pack(fill=tk.X, padx=8)

        # Buttons
        self._buttons_frame = tk.Frame(self, bg=BG)
        self._buttons_frame.pack(fill=tk.X, padx=10, pady=(4, 10))
        bf = self._buttons_frame
        separator(bf).pack(fill=tk.X, pady=(0, 8))
        wbtn(bf, "取消", self.destroy, width=8).pack(side=tk.RIGHT, padx=(4, 10))
        wbtn(bf, "保存", self._save, accent=True, width=8).pack(side=tk.RIGHT, padx=4)

    def _pick_target_window(self) -> None:
        from ui.position_picker import PositionPicker
        self.withdraw()
        self.update()
        picker = PositionPicker(self)
        title, rect = picker.pick_window()
        self.deiconify()
        if title:
            self._target_win_var.set(title)
            self._ref_w = rect[2] - rect[0] if rect else 0
            self._ref_h = rect[3] - rect[1] if rect else 0
            self._ref_label.configure(text=f"{self._ref_w} x {self._ref_h}")

    # ------------------------------------------------------------------
    # Bulk convert all actions coordinate mode
    # ------------------------------------------------------------------

    def _refresh_convert_section(self) -> None:
        """Rebuild the bulk-convert button and label to reflect current state."""
        from core.action import CoordMode
        for w in self._cvt_sec.winfo_children():
            w.destroy()
        if self._actions:
            abs_count = sum(1 for a in self._actions
                            if a.coord_mode == CoordMode.ABSOLUTE)
            rel_count = len(self._actions) - abs_count
            from ui.widgets import label as _wl, button as _wb
            _wl(self._cvt_sec,
                f"当前: 绝对坐标 {abs_count} 个  |  相对窗口 {rel_count} 个",
                dim=True).pack(anchor="w", pady=(2, 4))
            self._convert_btn = _wb(self._cvt_sec, "一键切换全部坐标模式",
                                    self._start_convert)
            self._convert_btn.pack(anchor="w")
        else:
            from ui.widgets import label as _wl
            _wl(self._cvt_sec, "（请先添加动作步骤）", dim=True).pack(pady=4)
            self._convert_btn = None

    def _start_convert(self) -> None:
        """Start the 5-second countdown before bulk converting coord modes."""
        if not self._convert_btn:
            return
        self._convert_countdown = 5
        self._convert_btn.configure(state=tk.DISABLED)
        self._tick_convert()

    def _tick_convert(self) -> None:
        if not self._convert_btn:
            return
        self._convert_countdown -= 1
        if self._convert_countdown > 0:
            self._convert_btn.configure(
                text=f"确认切换? ({self._convert_countdown}s) 点击取消")
            self._convert_btn.configure(command=self._cancel_convert)
            self._convert_timer = self.after(1000, self._tick_convert)
        else:
            self._do_convert()

    def _cancel_convert(self) -> None:
        if self._convert_timer:
            self.after_cancel(self._convert_timer)
            self._convert_timer = None
        if self._convert_btn:
            self._convert_btn.configure(text="已取消 (点击重试)")
            self._convert_btn.configure(state=tk.NORMAL)
            self._convert_btn.configure(command=self._start_convert)

    def _reset_convert_btn(self) -> None:
        if self._convert_btn:
            self._convert_btn.configure(text="一键切换全部坐标模式")
            self._convert_btn.configure(state=tk.NORMAL)
            self._convert_btn.configure(command=self._start_convert)

    def _do_convert(self) -> None:
        from core.action import CoordMode
        from core.win_utils import find_window_by_title, get_window_rect

        title = self._target_win_var.get()
        if not title:
            messagebox.showwarning("提示", "请先设置目标窗口标题", parent=self)
            self._reset_convert_btn()
            return

        hwnd = find_window_by_title(title)
        if hwnd is None:
            messagebox.showwarning("提示", f"未找到窗口 '{title}'", parent=self)
            self._reset_convert_btn()
            return

        rect = get_window_rect(hwnd)
        if rect is None:
            messagebox.showwarning("提示", "无法获取窗口位置", parent=self)
            self._reset_convert_btn()
            return

        win_left, win_top = rect[0], rect[1]

        # Determine target mode: majority wins, flip to opposite
        abs_count = sum(1 for a in self._actions
                        if a.coord_mode == CoordMode.ABSOLUTE)
        rel_count = len(self._actions) - abs_count
        to_relative = abs_count >= rel_count

        for action in self._actions:
            if to_relative and action.coord_mode == CoordMode.ABSOLUTE:
                action.coord_mode = CoordMode.RELATIVE_TO_WINDOW
                self._adjust_coords(action, -win_left, -win_top)
            elif not to_relative and action.coord_mode == CoordMode.RELATIVE_TO_WINDOW:
                action.coord_mode = CoordMode.ABSOLUTE
                self._adjust_coords(action, win_left, win_top)

        new_mode = "相对窗口" if to_relative else "绝对坐标"
        self._refresh_convert_section()
        if self._convert_btn:
            self._convert_btn.configure(text=f"已全部切换为: {new_mode}")
            self._convert_btn.configure(state=tk.DISABLED)
            self._convert_btn.configure(command=lambda: None)

    def _adjust_coords(self, action, dx: int, dy: int) -> None:
        """Add (dx, dy) to all coordinate fields of an action."""
        from core.action import ClickOnceAction, ClickHoldAction, MiddleClickAction
        from core.action import ScrollAction, DragAction
        if isinstance(action, (ClickOnceAction, ClickHoldAction, MiddleClickAction)):
            action.x += dx
            action.y += dy
        elif isinstance(action, ScrollAction):
            action.x += dx
            action.y += dy
        elif isinstance(action, DragAction):
            action.start_x += dx
            action.start_y += dy
            action.end_x += dx
            action.end_y += dy

    def _toggle_advanced(self) -> None:
        new_state = not self._rel_enabled_var.get()
        self._rel_enabled_var.set(new_state)
        if new_state:
            self._advanced_frame.pack(fill=tk.X, padx=8, before=self._buttons_frame)
        else:
            self._advanced_frame.pack_forget()
        self._adv_toggle_btn.configure(
            text="▾ 高级坐标功能（相对窗口）" if new_state
            else "▸ 高级坐标功能（相对窗口）")

    def _lock_label(self) -> str:
        return "🔒 已锁定" if self._lock_var.get() else "🔓 未锁定"

    def _toggle_lock(self) -> None:
        from core.win_utils import find_window_by_title, get_window_rect
        new_state = not self._lock_var.get()
        self._lock_var.set(new_state)
        self._lock_btn.configure(text=self._lock_label())
        if new_state:
            # Immediately update reference resolution from current window
            title = self._target_win_var.get()
            if title:
                hwnd = find_window_by_title(title)
                if hwnd:
                    rect = get_window_rect(hwnd)
                    if rect:
                        self._ref_w = rect[2] - rect[0]
                        self._ref_h = rect[3] - rect[1]
                        self._ref_label.configure(text=f"{self._ref_w} x {self._ref_h}")

    def _save(self) -> None:
        try:
            s = GlobalSettings(
                start_stop_hotkey=self._hotkey_var.get().lower().strip(),
                repeat_count=int(self._repeat_var.get() or 1),
                interval_ms=int(self._interval_var.get() or 100),
                random_delay_min_ms=int(self._rnd_min_var.get() or 0),
                random_delay_max_ms=int(self._rnd_max_var.get() or 0),
                stop_on_error=self._stop_on_err_var.get(),
                target_window_title=self._target_win_var.get(),
                reference_window_width=self._ref_w,
                reference_window_height=self._ref_h,
                mouse_speed_ms=int(self._mouse_speed_var.get() or 80),
                window_monitor_locked=self._lock_var.get(),
                relative_coords_enabled=self._rel_enabled_var.get(),
            )
            self._on_save(s)
            self.destroy()
        except ValueError as e:
            messagebox.showerror("输入错误", str(e), parent=self)


# ------------------------------------------------------------------
# Jump linkage dialog
# ------------------------------------------------------------------

class JumpDialog(tk.Toplevel):
    """Dialog for setting the on_fail_jump target of an action."""

    def __init__(self, parent, src_idx: int, actions: list, on_save) -> None:
        super().__init__(parent)
        self.title("设置联动")
        self.resizable(False, False)
        self.grab_set()
        self.transient(parent)
        self._src_idx = src_idx
        self._actions = actions
        self._on_save = on_save
        self._build(actions, src_idx)
        self.update_idletasks()
        self.geometry(f"+{parent.winfo_rootx() + 60}+{parent.winfo_rooty() + 60}")

    def _build(self, actions: list, src_idx: int) -> None:
        from core.action import ACTION_TYPE_LABELS
        from ui.widgets import BG, BG2, BG3, FG, FG_DIM, ACCENT, BORDER
        from ui.widgets import label as wlabel, button as wbtn, separator, SectionFrame

        self.configure(bg=BG)

        src_action = actions[src_idx]
        src_lbl = src_action.label or ACTION_TYPE_LABELS.get(src_action.action_type, "?")

        top = tk.Frame(self, bg=BG)
        top.pack(fill=tk.X, padx=10, pady=(10, 4))
        wlabel(top, f"来源步骤:  {src_idx + 1}. {src_lbl}",
               bg=BG, font=("Microsoft YaHei", 9, "bold")).pack(anchor="w")
        wlabel(top, "当文字验证失败时，跳转执行：",
               bg=BG, dim=True).pack(anchor="w", pady=(4, 0))

        # Listbox
        lb_frame = tk.Frame(self, bg=BG)
        lb_frame.pack(fill=tk.BOTH, padx=10, pady=4)

        self._listbox = tk.Listbox(
            lb_frame,
            height=min(len(actions), 10), width=44,
            bg="#18191c", fg=FG,
            selectbackground=ACCENT, selectforeground="white",
            activestyle="none", relief=tk.FLAT, borderwidth=0,
            highlightthickness=1, highlightbackground=BORDER,
            font=("Consolas", 9),
        )
        self._listbox.pack(fill=tk.BOTH)

        current_jump = src_action.on_fail_jump
        select_idx = None
        for i, a in enumerate(actions):
            if i == src_idx:
                continue
            lbl = a.label or ACTION_TYPE_LABELS.get(a.action_type, "?")
            self._listbox.insert(tk.END, f"  {i + 1}. {lbl}  —  {a.description()}")
            if i == current_jump:
                select_idx = self._listbox.size() - 1

        self._idx_map = [i for i in range(len(actions)) if i != src_idx]
        if select_idx is not None:
            self._listbox.selection_set(select_idx)
            self._listbox.see(select_idx)

        # Buttons
        bf = tk.Frame(self, bg=BG)
        bf.pack(fill=tk.X, padx=10, pady=(4, 10))
        separator(bf).pack(fill=tk.X, pady=(0, 8))
        wbtn(bf, "清除联动", self._clear, danger=True).pack(side=tk.LEFT)
        wbtn(bf, "取消", self.destroy, width=8).pack(side=tk.RIGHT, padx=(4, 0))
        wbtn(bf, "确定", self._save, accent=True, width=8).pack(side=tk.RIGHT, padx=4)

    def _save(self) -> None:
        sel = self._listbox.curselection()
        if not sel:
            messagebox.showinfo("提示", "请选择一个目标步骤", parent=self)
            return
        self._on_save(self._src_idx, self._idx_map[sel[0]])
        self.destroy()

    def _clear(self) -> None:
        self._on_save(self._src_idx, -1)
        self.destroy()

