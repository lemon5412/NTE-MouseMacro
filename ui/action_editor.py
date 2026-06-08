"""
Per-action configuration dialog.
Double-click an action in the main panel to open this.
"""
from __future__ import annotations
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional

from core.action import (
    ActionType, ACTION_TYPE_LABELS,
    ActionGroup, ImageVerification,
    CoordMode, COORD_MODE_LABELS,
    ClickOnceAction, ClickHoldAction, ScrollAction,
    MiddleClickAction, KeyPressAction, DragAction, WaitAction,
    AnyAction, VerifyOnFail, VERIFY_ON_FAIL_LABELS,
    OcrRegion,
)
from ui.position_picker import PositionPicker
from ui.widgets import (
    BG, BG2, BG3, FG, FG_DIM, ACCENT, BORDER, SEL,
    SectionFrame, button, label, entry, checkbutton,
    radiobutton, separator, btn_row, _style_ttk,
)


class ActionEditor(tk.Toplevel):
    """
    Modal dialog for creating or editing a single action.
    After closing, check .result for the configured action (None = cancelled).
    """

    def __init__(
        self,
        parent: tk.Tk | tk.Toplevel,
        initial: Optional[AnyAction] = None,
        target_window_title: str = "",
        relative_coords_enabled: bool = False,
    ) -> None:
        super().__init__(parent)
        self.title("编辑动作")
        self.resizable(False, False)
        self.grab_set()
        self.transient(parent)
        self.configure(bg=BG)
        _style_ttk()

        self._parent_win = parent
        self._target_window_title = target_window_title
        self._rel_enabled = relative_coords_enabled
        self.result: Optional[AnyAction] = None

        self._type_var = tk.StringVar()
        self._type_var.trace_add("write", self._on_type_change)

        self._build_static_ui()
        self._dynamic_frame = tk.Frame(self, bg=BG2, padx=8, pady=4)
        self._dynamic_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 4))
        self._build_buttons()

        if initial:
            self._type_var.set(initial.action_type.value)
            self._load_action(initial)
        else:
            self._type_var.set(ActionType.CLICK_ONCE.value)

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self._center()

    def _center(self) -> None:
        self.update_idletasks()
        pw = self._parent_win.winfo_rootx()
        py = self._parent_win.winfo_rooty()
        self.geometry(f"+{pw + 60}+{py + 60}")

    # ------------------------------------------------------------------
    # Static UI
    # ------------------------------------------------------------------

    def _build_static_ui(self) -> None:
        # Type selector
        type_sec = SectionFrame(self, "动作类型")
        type_sec.pack(fill=tk.X, padx=10, pady=(10, 4))

        type_names = list(ACTION_TYPE_LABELS.values())
        type_values = [t.value for t in ACTION_TYPE_LABELS.keys()]
        self._type_display = ttk.Combobox(
            type_sec, values=type_names, state="readonly", width=12,
            font=("Microsoft YaHei", 9),
        )
        self._type_display.pack(side=tk.LEFT)
        self._type_display.bind("<<ComboboxSelected>>", self._on_display_select)
        self._type_values = type_values
        self._type_names = type_names

        # Common fields
        common = SectionFrame(self, "通用设置")
        common.pack(fill=tk.X, padx=10, pady=4)

        row1 = tk.Frame(common, bg=BG2)
        row1.pack(fill=tk.X, pady=3)
        label(row1, "标签:", dim=True).pack(side=tk.LEFT)
        self._label_var = tk.StringVar()
        entry(row1, self._label_var, width=20).pack(side=tk.LEFT, padx=(6, 0))

        row2 = tk.Frame(common, bg=BG2)
        row2.pack(fill=tk.X, pady=3)
        label(row2, "执行后延迟(ms):", dim=True).pack(side=tk.LEFT)
        self._delay_var = tk.StringVar(value="0")
        entry(row2, self._delay_var, width=7).pack(side=tk.LEFT, padx=(6, 0))

        self._enabled_var = tk.BooleanVar(value=True)
        checkbutton(common, "启用此步骤", self._enabled_var).pack(anchor="w", pady=(4, 0))

        # CoordMode selector (only visible when relative coords are enabled)
        self._coord_row = tk.Frame(common, bg=BG2)
        label(self._coord_row, "坐标模式:", dim=True).pack(side=tk.LEFT)
        self._coord_mode_var = tk.StringVar(value=CoordMode.ABSOLUTE.value)
        for mode in CoordMode:
            radiobutton(self._coord_row, COORD_MODE_LABELS[mode],
                        self._coord_mode_var, mode.value).pack(side=tk.LEFT, padx=(4, 0))
        if self._rel_enabled:
            self._coord_row.pack(fill=tk.X, pady=(6, 0))

        # Image verification (collapsible)
        self._iv_expanded = False
        self._iv_toggle_btn = button(common,
            "▸ 图片验证", self._toggle_image_verify)
        self._iv_toggle_btn.pack(anchor="w", pady=(8, 0))

        self._iv_frame = tk.Frame(common, bg=BG2)
        self._iv_template_data: str = ""
        self._iv_preview_img = None
        self._build_image_verify_ui()

    def _build_image_verify_ui(self) -> None:
        """Build the image verification sub-panel (shared by all action types)."""
        f = self._iv_frame

        # Region row
        r1 = tk.Frame(f, bg=BG2)
        r1.pack(fill=tk.X, pady=2)
        for lbl_txt, attr in [("X:", "_iv_rx"), ("Y:", "_iv_ry"),
                               ("W:", "_iv_rw"), ("H:", "_iv_rh")]:
            label(r1, lbl_txt, dim=True).pack(side=tk.LEFT, padx=(2, 0))
            var = tk.StringVar(value="0" if "W" not in attr else "200" if attr == "_iv_rw" else "50" if attr == "_iv_rh" else "0")
            setattr(self, attr, var)
            entry(r1, var, width=5).pack(side=tk.LEFT, padx=1)

        btn_f = tk.Frame(f, bg=BG2)
        btn_f.pack(fill=tk.X, pady=2)
        button(btn_f, "框选区域", self._iv_pick_region).pack(side=tk.LEFT)
        button(btn_f, "截图", self._iv_capture).pack(side=tk.LEFT, padx=4)
        button(btn_f, "上传图片", self._iv_upload).pack(side=tk.LEFT)

        # Preview
        self._iv_preview_lbl = tk.Label(f, bg=BG2, text="(未截图)")
        self._iv_preview_lbl.pack(pady=2)

        # Threshold + on-fail
        srow = tk.Frame(f, bg=BG2)
        srow.pack(fill=tk.X, pady=2)
        label(srow, "阈值(0.1-1.0):", dim=True).pack(side=tk.LEFT)
        self._iv_threshold_var = tk.StringVar(value="0.8")
        entry(srow, self._iv_threshold_var, width=5).pack(side=tk.LEFT, padx=6)
        label(srow, "失败:", dim=True).pack(side=tk.LEFT, padx=(8, 0))
        self._iv_on_fail_var = tk.StringVar(value=VerifyOnFail.SKIP.value)
        for fm, fl in VERIFY_ON_FAIL_LABELS.items():
            radiobutton(srow, fl, self._iv_on_fail_var,
                        fm.value).pack(side=tk.LEFT, padx=2)

    def _toggle_image_verify(self) -> None:
        self._iv_expanded = not self._iv_expanded
        if self._iv_expanded:
            self._iv_frame.pack(fill=tk.X, pady=(4, 0))
        else:
            self._iv_frame.pack_forget()
        self._iv_toggle_btn.configure(
            text="▾ 图片验证" if self._iv_expanded else "▸ 图片验证")

    def _iv_pick_region(self) -> None:
        picker = PositionPicker(self)
        x, y, w, h = picker.pick_region()
        if x is not None:
            self._iv_rx.set(str(x)); self._iv_ry.set(str(y))
            self._iv_rw.set(str(w)); self._iv_rh.set(str(h))
            self._iv_capture()

    def _iv_capture(self) -> None:
        try:
            region = OcrRegion(
                x=int(self._iv_rx.get() or 0), y=int(self._iv_ry.get() or 0),
                w=int(self._iv_rw.get() or 200), h=int(self._iv_rh.get() or 50))
            from core.image_match import ImageMatcher
            self._iv_template_data = ImageMatcher().capture_template(region)
            self._iv_show_preview()
        except Exception as e:
            self._iv_preview_lbl.configure(text=f"截图失败: {e}", image="")

    def _iv_upload(self) -> None:
        from tkinter import filedialog
        import base64
        path = filedialog.askopenfilename(
            parent=self, title="选择模板图片",
            filetypes=[("图片文件", "*.png *.jpg *.jpeg *.bmp"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            with open(path, "rb") as fh:
                self._iv_template_data = base64.b64encode(fh.read()).decode("ascii")
            # Update region from image dimensions
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(base64.b64decode(self._iv_template_data)))
            self._iv_rw.set(str(img.width)); self._iv_rh.set(str(img.height))
            self._iv_show_preview()
        except Exception as e:
            self._iv_preview_lbl.configure(text=f"上传失败: {e}", image="")

    def _iv_show_preview(self) -> None:
        if not self._iv_template_data:
            return
        try:
            import base64, io
            from PIL import Image, ImageTk
            img = Image.open(io.BytesIO(base64.b64decode(self._iv_template_data)))
            orig_w, orig_h = img.width, img.height
            img.thumbnail((160, 100), Image.LANCZOS)
            self._iv_preview_img = ImageTk.PhotoImage(img)
            self._iv_preview_lbl.configure(
                image=self._iv_preview_img,
                text=f"   ({orig_w}x{orig_h})",
                compound=tk.TOP, bg=BG2)
        except Exception as e:
            self._iv_preview_lbl.configure(
                text=f"(预览失败: {e})", image="")

    def _on_display_select(self, event=None) -> None:
        idx = self._type_display.current()
        if 0 <= idx < len(self._type_values):
            self._type_var.set(self._type_values[idx])

    def _build_buttons(self) -> None:
        f = btn_row(self, self._on_ok, self._on_cancel)
        f.pack(fill=tk.X, padx=10, pady=(4, 10))

    # ------------------------------------------------------------------
    # Dynamic fields
    # ------------------------------------------------------------------

    def _on_type_change(self, *args) -> None:
        val = self._type_var.get()
        if val in self._type_values:
            self._type_display.set(self._type_names[self._type_values.index(val)])
        for w in self._dynamic_frame.winfo_children():
            w.destroy()
        self._build_dynamic_fields(val)

    def _row(self, parent=None) -> tk.Frame:
        p = parent or self._dynamic_frame
        f = tk.Frame(p, bg=BG2)
        f.pack(fill=tk.X, pady=3)
        return f

    def _build_dynamic_fields(self, type_val: str) -> None:
        t = ActionType(type_val)

        if t == ActionType.ACTION_GROUP:
            self._build_action_group_fields()
            return

        if t == ActionType.WAIT:
            row = self._row()
            label(row, "等待时长(ms):", dim=True).pack(side=tk.LEFT)
            self._wait_ms_var = tk.StringVar(value="1000")
            entry(row, self._wait_ms_var, width=7).pack(side=tk.LEFT, padx=(6, 0))
            return

        if t in (ActionType.CLICK_ONCE, ActionType.CLICK_HOLD, ActionType.MIDDLE_CLICK):
            self._build_coord_fields(self._dynamic_frame)
            row = self._row()
            label(row, "按下时长(ms):", dim=True).pack(side=tk.LEFT)
            default = "50" if t != ActionType.CLICK_HOLD else "1000"
            self._hold_var = tk.StringVar(value=default)
            entry(row, self._hold_var, width=7).pack(side=tk.LEFT, padx=(6, 0))

        elif t == ActionType.SCROLL:
            self._build_coord_fields(self._dynamic_frame)
            row = self._row()
            label(row, "方向:", dim=True).pack(side=tk.LEFT)
            self._scroll_dir_var = tk.StringVar(value="down")
            radiobutton(row, "向上", self._scroll_dir_var, "up").pack(side=tk.LEFT, padx=(8, 4))
            radiobutton(row, "向下", self._scroll_dir_var, "down").pack(side=tk.LEFT)
            row2 = self._row()
            label(row2, "滚动格数:", dim=True).pack(side=tk.LEFT)
            self._scroll_amount_var = tk.StringVar(value="3")
            entry(row2, self._scroll_amount_var, width=5).pack(side=tk.LEFT, padx=(6, 0))

        elif t == ActionType.KEY_PRESS:
            row = self._row()
            label(row, "按键组合:", dim=True).pack(side=tk.LEFT)
            self._keys_var = tk.StringVar()
            entry(row, self._keys_var, width=16).pack(side=tk.LEFT, padx=(6, 0))
            label(row, "(用+分隔)", dim=True).pack(side=tk.LEFT, padx=(6, 0))

            row2 = self._row()
            button(row2, "录制按键", self._record_key).pack(side=tk.LEFT)

            row3 = self._row()
            label(row3, "按下时长(ms):", dim=True).pack(side=tk.LEFT)
            self._hold_var = tk.StringVar(value="50")
            entry(row3, self._hold_var, width=7).pack(side=tk.LEFT, padx=(6, 0))

        elif t == ActionType.DRAG:
            sf = SectionFrame(self._dynamic_frame, "起点")
            sf.pack(fill=tk.X, pady=2)
            self._build_coord_fields(sf, prefix="start")
            ef = SectionFrame(self._dynamic_frame, "终点")
            ef.pack(fill=tk.X, pady=2)
            self._build_coord_fields(ef, prefix="end")

            row = self._row()
            label(row, "拖动时长(ms):", dim=True).pack(side=tk.LEFT)
            self._drag_dur_var = tk.StringVar(value="300")
            entry(row, self._drag_dur_var, width=7).pack(side=tk.LEFT, padx=(6, 0))
            label(row, "插值步数:", dim=True).pack(side=tk.LEFT, padx=(12, 0))
            self._drag_steps_var = tk.StringVar(value="20")
            entry(row, self._drag_steps_var, width=5).pack(side=tk.LEFT, padx=(6, 0))

    # ------------------------------------------------------------------
    # Action group editor
    # ------------------------------------------------------------------

    def _build_action_group_fields(self) -> None:
        self._group_children: list[AnyAction] = []
        # Image verification is in the common section (_build_image_verify_ui)
        # Just show a hint about child management
        hint_sec = SectionFrame(self._dynamic_frame, "子动作")
        hint_sec.pack(fill=tk.X, pady=2)
        tk.Label(hint_sec, text="在主界面中，将其他动作拖动到此动作组即可加入",
                 bg=BG2, fg=FG_DIM, font=("Microsoft YaHei", 9)).pack(pady=4)

    def _build_coord_fields(self, parent: tk.Widget, prefix: str = "") -> None:
        row = tk.Frame(parent, bg=BG2)
        row.pack(fill=tk.X, pady=3)
        if not prefix:
            label(row, "坐标:", dim=True).pack(side=tk.LEFT)
        x_var = tk.StringVar(value="0")
        label(row, "X:", dim=True).pack(side=tk.LEFT, padx=(6, 0))
        entry(row, x_var, width=6).pack(side=tk.LEFT, padx=2)
        y_var = tk.StringVar(value="0")
        label(row, "Y:", dim=True).pack(side=tk.LEFT, padx=(4, 0))
        entry(row, y_var, width=6).pack(side=tk.LEFT, padx=2)
        button(row, "拾取", lambda: self._pick_coord(x_var, y_var), width=4).pack(side=tk.LEFT, padx=(6, 0))

        if prefix == "start":
            self._start_x_var, self._start_y_var = x_var, y_var
        elif prefix == "end":
            self._end_x_var, self._end_y_var = x_var, y_var
        else:
            self._x_var, self._y_var = x_var, y_var

    def _pick_coord(self, x_var: tk.StringVar, y_var: tk.StringVar) -> None:
        if self._coord_mode_var.get() == CoordMode.RELATIVE_TO_WINDOW.value:
            self._pick_relative_coord(x_var, y_var)
        else:
            picker = PositionPicker(self)
            x, y = picker.pick()
            if x is not None:
                x_var.set(str(x))
                y_var.set(str(y))

    def _pick_relative_coord(self, x_var: tk.StringVar, y_var: tk.StringVar) -> None:
        if not self._target_window_title:
            messagebox.showwarning("提示", "请先在全局设置中设置目标窗口标题", parent=self)
            return
        from core.win_utils import find_window_by_title, get_window_rect
        hwnd = find_window_by_title(self._target_window_title)
        if hwnd is None:
            messagebox.showwarning("提示", f"未找到窗口 '{self._target_window_title}'", parent=self)
            return
        rect = get_window_rect(hwnd)
        if rect is None:
            messagebox.showwarning("提示", "无法获取窗口位置", parent=self)
            return
        picker = PositionPicker(self)
        abs_x, abs_y = picker.pick()
        if abs_x is not None:
            x_var.set(str(abs_x - rect[0]))
            y_var.set(str(abs_y - rect[1]))

    def _record_key(self) -> None:
        rec = tk.Toplevel(self)
        rec.title("录制按键")
        rec.configure(bg=BG)
        rec.geometry("280x110")
        rec.grab_set()
        rec.transient(self)
        label(rec, "请按下要录制的按键组合...", bg=BG).pack(pady=(16, 4))
        result_var = tk.StringVar(value="")
        tk.Label(rec, textvariable=result_var, bg=BG, fg=ACCENT,
                 font=("Consolas", 10, "bold")).pack()
        pressed: list[str] = []

        def on_key(event):
            key = event.keysym.lower()
            if key not in pressed:
                pressed.append(key)
            result_var.set("+".join(pressed))

        def on_release(event):
            self._keys_var.set("+".join(pressed))
            rec.destroy()

        rec.bind("<KeyPress>", on_key)
        rec.bind("<KeyRelease>", on_release)
        rec.focus_force()

    # ------------------------------------------------------------------
    # Load / collect
    # ------------------------------------------------------------------

    def _load_action(self, action: AnyAction) -> None:
        self._label_var.set(action.label)
        self._delay_var.set(str(action.delay_after_ms))
        self._enabled_var.set(action.enabled)
        cm = getattr(action, 'coord_mode', CoordMode.ABSOLUTE)
        self._coord_mode_var.set(cm.value if isinstance(cm, CoordMode) else cm)
        t = action.action_type
        # Load image_verify (common to all actions)
        iv = action.image_verify
        self._iv_rx.set(str(iv.region.x)); self._iv_ry.set(str(iv.region.y))
        self._iv_rw.set(str(iv.region.w)); self._iv_rh.set(str(iv.region.h))
        self._iv_template_data = iv.template_data
        self._iv_threshold_var.set(str(iv.threshold))
        self._iv_on_fail_var.set(iv.on_fail.value)
        if iv.template_data:
            self._iv_show_preview()
        else:
            self._iv_preview_lbl.configure(text="(未截图)", image="")
        self._iv_expanded = iv.enabled
        if iv.enabled:
            self._iv_frame.pack(fill=tk.X, pady=(4, 0))
            self._iv_toggle_btn.configure(text="▾ 图片验证")
        else:
            self._iv_frame.pack_forget()
            self._iv_toggle_btn.configure(text="▸ 图片验证")

        if t == ActionType.ACTION_GROUP:
            self._group_children = list(action.children)
            return
        if t in (ActionType.CLICK_ONCE, ActionType.CLICK_HOLD, ActionType.MIDDLE_CLICK):
            self._x_var.set(str(action.x))
            self._y_var.set(str(action.y))
            self._hold_var.set(str(action.hold_ms))
        elif t == ActionType.SCROLL:
            self._x_var.set(str(action.x))
            self._y_var.set(str(action.y))
            self._scroll_dir_var.set(action.direction)
            self._scroll_amount_var.set(str(action.amount))
        elif t == ActionType.KEY_PRESS:
            self._keys_var.set("+".join(action.keys))
            self._hold_var.set(str(action.hold_ms))
        elif t == ActionType.DRAG:
            self._start_x_var.set(str(action.start_x))
            self._start_y_var.set(str(action.start_y))
            self._end_x_var.set(str(action.end_x))
            self._end_y_var.set(str(action.end_y))
            self._drag_dur_var.set(str(action.duration_ms))
            self._drag_steps_var.set(str(action.steps))
        elif t == ActionType.WAIT:
            self._wait_ms_var.set(str(action.wait_ms))

    def _collect(self) -> AnyAction:
        t = ActionType(self._type_var.get())
        base = dict(
            action_type=t,
            label=self._label_var.get(),
            enabled=self._enabled_var.get(),
            delay_after_ms=int(self._delay_var.get() or 0),
            coord_mode=CoordMode(self._coord_mode_var.get()),
            image_verify=ImageVerification(
                enabled=bool(self._iv_template_data),
                region=OcrRegion(
                    x=int(self._iv_rx.get() or 0), y=int(self._iv_ry.get() or 0),
                    w=int(self._iv_rw.get() or 200), h=int(self._iv_rh.get() or 50),
                ),
                template_data=self._iv_template_data,
                match_method="TM_CCOEFF_NORMED",
                threshold=float(self._iv_threshold_var.get() or 0.8),
                on_fail=VerifyOnFail(self._iv_on_fail_var.get()),
            ),
        )
        if t == ActionType.ACTION_GROUP:
            return ActionGroup(**base, children=list(self._group_children))
        if t == ActionType.CLICK_ONCE:
            return ClickOnceAction(**base, x=int(self._x_var.get() or 0),
                                   y=int(self._y_var.get() or 0),
                                   hold_ms=int(self._hold_var.get() or 50))
        elif t == ActionType.CLICK_HOLD:
            return ClickHoldAction(**base, x=int(self._x_var.get() or 0),
                                   y=int(self._y_var.get() or 0),
                                   hold_ms=int(self._hold_var.get() or 1000))
        elif t == ActionType.SCROLL:
            return ScrollAction(**base, x=int(self._x_var.get() or 0),
                                y=int(self._y_var.get() or 0),
                                direction=self._scroll_dir_var.get(),
                                amount=int(self._scroll_amount_var.get() or 3))
        elif t == ActionType.MIDDLE_CLICK:
            return MiddleClickAction(**base, x=int(self._x_var.get() or 0),
                                     y=int(self._y_var.get() or 0),
                                     hold_ms=int(self._hold_var.get() or 50))
        elif t == ActionType.KEY_PRESS:
            keys = [k.strip() for k in self._keys_var.get().split("+") if k.strip()]
            return KeyPressAction(**base, keys=keys,
                                  hold_ms=int(self._hold_var.get() or 50))
        elif t == ActionType.DRAG:
            return DragAction(**base,
                              start_x=int(self._start_x_var.get() or 0),
                              start_y=int(self._start_y_var.get() or 0),
                              end_x=int(self._end_x_var.get() or 0),
                              end_y=int(self._end_y_var.get() or 0),
                              duration_ms=int(self._drag_dur_var.get() or 300),
                              steps=int(self._drag_steps_var.get() or 20))
        elif t == ActionType.WAIT:
            return WaitAction(**base,
                wait_ms=int(self._wait_ms_var.get() or 1000))
        raise ValueError(f"Unknown action type: {t}")

    def _on_ok(self) -> None:
        try:
            self.result = self._collect()
        except (ValueError, AttributeError) as e:
            messagebox.showerror("输入错误", f"请检查输入值:\n{e}", parent=self)
            return
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()
