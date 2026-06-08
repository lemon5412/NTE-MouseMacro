"""
Text verification configuration dialog.
Right-click an action in the main panel → "文字验证" to open this.
"""
from __future__ import annotations
import threading
import tkinter as tk
from tkinter import messagebox
from typing import Optional

from core.action import (
    MatchMode, MATCH_MODE_LABELS,
    VerifyOnFail, VERIFY_ON_FAIL_LABELS,
    OcrRegion, TextVerification,
)
from core.ocr_engine import OcrEngine
from ui.position_picker import PositionPicker
from ui.widgets import (
    BG, BG2, BG3, FG, FG_DIM, ACCENT, BORDER,
    SectionFrame, button, label, entry, checkbutton,
    radiobutton, separator, btn_row, _style_ttk,
)


class TextVerifyDialog(tk.Toplevel):
    """
    Modal dialog for configuring per-action text verification.
    Returns the updated TextVerification object via .result after closing.
    """

    def __init__(
        self,
        parent: tk.Tk | tk.Toplevel,
        ocr_engine: OcrEngine,
        initial: Optional[TextVerification] = None,
    ) -> None:
        super().__init__(parent)
        self.title("文字验证设置")
        self.resizable(False, False)
        self.grab_set()
        self.transient(parent)
        self.configure(bg=BG)
        _style_ttk()

        self._ocr = ocr_engine
        self._parent_win = parent
        self.result: Optional[TextVerification] = None

        tv = initial or TextVerification()
        self._build_ui(tv)
        self._load(tv)

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self._center()

    def _center(self) -> None:
        self.update_idletasks()
        self.geometry(f"+{self._parent_win.winfo_rootx() + 40}+{self._parent_win.winfo_rooty() + 40}")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self, tv: TextVerification) -> None:
        pad = {"padx": 10, "pady": 4}

        # Enable toggle
        top = tk.Frame(self, bg=BG)
        top.pack(fill=tk.X, padx=10, pady=(10, 4))
        self._enabled_var = tk.BooleanVar()
        checkbutton(top, "启用文字验证", self._enabled_var,
                    cmd=self._on_toggle, bg=BG).pack(side=tk.LEFT)

        # OCR region
        region_sec = SectionFrame(self, "识别区域")
        region_sec.pack(fill=tk.X, **pad)

        row1 = tk.Frame(region_sec, bg=BG2)
        row1.pack(fill=tk.X, pady=2)
        for lbl_text, attr in [("X:", "_rx"), ("Y:", "_ry"), ("W:", "_rw"), ("H:", "_rh")]:
            label(row1, lbl_text, dim=True).pack(side=tk.LEFT, padx=(4, 0))
            var = tk.StringVar()
            setattr(self, attr, var)
            entry(row1, var, width=6).pack(side=tk.LEFT, padx=2)
        button(row1, "框选区域", self._pick_region).pack(side=tk.LEFT, padx=(8, 0))

        # Target text
        text_sec = SectionFrame(self, "目标文字")
        text_sec.pack(fill=tk.X, **pad)
        self._target_var = tk.StringVar()
        entry(text_sec, self._target_var, width=32).pack(fill=tk.X, pady=2)

        # Match mode
        mode_sec = SectionFrame(self, "匹配模式")
        mode_sec.pack(fill=tk.X, **pad)
        self._match_var = tk.StringVar()
        row = tk.Frame(mode_sec, bg=BG2)
        row.pack(fill=tk.X)
        for mode, lbl_text in MATCH_MODE_LABELS.items():
            radiobutton(row, lbl_text, self._match_var, mode.value).pack(side=tk.LEFT, padx=4)

        # Condition
        cond_sec = SectionFrame(self, "执行条件")
        cond_sec.pack(fill=tk.X, **pad)
        self._require_found_var = tk.BooleanVar()
        row = tk.Frame(cond_sec, bg=BG2)
        row.pack(fill=tk.X)
        radiobutton(row, "找到文字时执行", self._require_found_var, True).pack(side=tk.LEFT, padx=4)
        radiobutton(row, "未找到文字时执行", self._require_found_var, False).pack(side=tk.LEFT, padx=4)

        # On fail
        fail_sec = SectionFrame(self, "条件不满足时")
        fail_sec.pack(fill=tk.X, **pad)
        self._on_fail_var = tk.StringVar()
        self._on_fail_var.trace_add("write", self._on_fail_change)
        row = tk.Frame(fail_sec, bg=BG2)
        row.pack(fill=tk.X)
        for fail, lbl_text in VERIFY_ON_FAIL_LABELS.items():
            radiobutton(row, lbl_text, self._on_fail_var, fail.value).pack(side=tk.LEFT, padx=4)

        # WAIT timeout row (visible only when on_fail == "wait")
        self._wait_timeout_row = tk.Frame(fail_sec, bg=BG2)
        label(self._wait_timeout_row, "等待超时(ms):", dim=True).pack(side=tk.LEFT)
        self._wait_timeout_var = tk.StringVar(value="5000")
        entry(self._wait_timeout_row, self._wait_timeout_var, width=7).pack(side=tk.LEFT, padx=(6, 0))

        # Fine-tune
        ft_sec = SectionFrame(self, "位置微调")
        ft_sec.pack(fill=tk.X, **pad)
        self._fine_tune_var = tk.BooleanVar()
        checkbutton(ft_sec, "启用微调（将点击位置移向识别到的文字中心）",
                    self._fine_tune_var).pack(anchor="w")
        ft_row = tk.Frame(ft_sec, bg=BG2)
        ft_row.pack(anchor="w", pady=(4, 0))
        label(ft_row, "最大偏移(px):", dim=True).pack(side=tk.LEFT)
        self._ft_offset = tk.StringVar(value="50")
        entry(ft_row, self._ft_offset, width=6).pack(side=tk.LEFT, padx=(6, 0))

        # Test button
        test_frame = tk.Frame(self, bg=BG)
        test_frame.pack(fill=tk.X, padx=10, pady=4)
        button(test_frame, "测试识别", self._test_ocr).pack(side=tk.LEFT)
        self._test_result_var = tk.StringVar(value="")
        tk.Label(test_frame, textvariable=self._test_result_var,
                 bg=BG, fg=ACCENT, font=("Microsoft YaHei", 8),
                 wraplength=280, justify=tk.LEFT).pack(side=tk.LEFT, padx=8)

        # Buttons
        btn_row(self, self._on_ok, self._on_cancel).pack(fill=tk.X, padx=10, pady=(4, 10))

        self._content_widgets = [region_sec, text_sec, mode_sec, cond_sec, fail_sec, ft_sec]

    def _load(self, tv: TextVerification) -> None:
        self._enabled_var.set(tv.enabled)
        self._rx.set(str(tv.region.x))
        self._ry.set(str(tv.region.y))
        self._rw.set(str(tv.region.w))
        self._rh.set(str(tv.region.h))
        self._target_var.set(tv.target_text)
        self._match_var.set(tv.match_mode.value)
        self._require_found_var.set(tv.require_found)
        self._on_fail_var.set(tv.on_fail.value)
        self._fine_tune_var.set(tv.fine_tune)
        self._ft_offset.set(str(tv.fine_tune_max_offset))
        self._wait_timeout_var.set(str(tv.wait_timeout_ms))
        self._on_toggle()
        self._on_fail_change()

    def _on_toggle(self) -> None:
        state = tk.NORMAL if self._enabled_var.get() else tk.DISABLED
        for w in self._content_widgets:
            self._set_state(w, state)

    def _on_fail_change(self, *args) -> None:
        if self._on_fail_var.get() == VerifyOnFail.WAIT.value:
            self._wait_timeout_row.pack(fill=tk.X, pady=3)
        else:
            self._wait_timeout_row.pack_forget()

    def _set_state(self, widget: tk.Widget, state: str) -> None:
        try:
            widget.configure(state=state)
        except tk.TclError:
            pass
        for child in widget.winfo_children():
            self._set_state(child, state)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _pick_region(self) -> None:
        picker = PositionPicker(self)
        x, y, w, h = picker.pick_region()
        if x is not None:
            self._rx.set(str(x))
            self._ry.set(str(y))
            self._rw.set(str(w))
            self._rh.set(str(h))

    def _test_ocr(self) -> None:
        self._test_result_var.set("识别中...")
        self.update()

        def run():
            try:
                region = self._read_region()
                results = self._ocr.recognize(region)
                if results:
                    lines = "\n".join(f"{r.text}  ({r.confidence:.2f})" for r in results[:8])
                    self._test_result_var.set(f"识别结果:\n{lines}")
                else:
                    self._test_result_var.set("未识别到文字")
            except Exception as e:
                self._test_result_var.set(f"错误: {e}")

        threading.Thread(target=run, daemon=True).start()

    def _read_region(self) -> OcrRegion:
        return OcrRegion(
            x=int(self._rx.get() or 0),
            y=int(self._ry.get() or 0),
            w=int(self._rw.get() or 200),
            h=int(self._rh.get() or 50),
        )

    def _collect(self) -> TextVerification:
        return TextVerification(
            enabled=self._enabled_var.get(),
            region=self._read_region(),
            target_text=self._target_var.get(),
            match_mode=MatchMode(self._match_var.get()),
            require_found=self._require_found_var.get(),
            on_fail=VerifyOnFail(self._on_fail_var.get()),
            fine_tune=self._fine_tune_var.get(),
            fine_tune_max_offset=int(self._ft_offset.get() or 50),
            wait_timeout_ms=int(self._wait_timeout_var.get() or 5000),
        )

    def _on_ok(self) -> None:
        try:
            self.result = self._collect()
        except (ValueError, Exception) as e:
            messagebox.showerror("输入错误", str(e), parent=self)
            return
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()
