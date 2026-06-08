"""
Macro execution engine.
Runs on a background daemon thread; communicates with the UI via callbacks.
"""
from __future__ import annotations
import random
import threading
import time
from enum import Enum
from typing import Callable, Optional

from core.action import (
    ActionType, VerifyOnFail, CoordMode, GlobalSettings, TextVerification,
    ImageVerification, ActionGroup, AnyAction,
    ClickOnceAction, ClickHoldAction, ScrollAction,
    MiddleClickAction, KeyPressAction, DragAction, WaitAction,
)
from core.input_sim import InputSimulator
from core.ocr_engine import OcrEngine
from core.win_utils import find_window_by_title, get_window_rect
from core.image_match import ImageMatcher


class StepResult(Enum):
    SUCCESS = "success"
    SKIPPED = "skipped"
    ABORTED = "aborted"
    JUMPED  = "jumped"


# Callback signature: (status_message, current_step_index_or_-1)
StatusCallback = Callable[[str, int], None]


class MacroExecutor:
    """
    Executes a list of actions repeatedly according to GlobalSettings.
    Thread-safe: start/stop can be called from any thread.
    """

    def __init__(self, input_sim: InputSimulator, ocr_engine: OcrEngine) -> None:
        self._sim = input_sim
        self._ocr = ocr_engine
        self._img = ImageMatcher()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._status_cb: Optional[StatusCallback] = None
        self._current_settings: Optional[GlobalSettings] = None
        self._lock = threading.Lock()

    def set_status_callback(self, cb: StatusCallback) -> None:
        self._status_cb = cb

    def _notify(self, msg: str, step_idx: int = -1) -> None:
        if self._status_cb:
            try:
                self._status_cb(msg, step_idx)
            except Exception:
                pass

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, actions: list[AnyAction], settings: GlobalSettings) -> None:
        with self._lock:
            if self.is_running():
                return
            self._current_settings = settings
            self._sim.mouse_speed_ms = settings.mouse_speed_ms
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                args=(actions, settings),
                daemon=True,
                name="MacroExecutor",
            )
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    # ------------------------------------------------------------------
    # Internal execution loop
    # ------------------------------------------------------------------

    def _run_loop(self, actions: list[AnyAction], settings: GlobalSettings) -> None:
        self._notify("运行中", -1)
        repeat = 0
        # Build set of indices that are jump targets — skip them in main loop
        jump_targets: set[int] = {a.on_fail_jump for a in actions if a.on_fail_jump >= 0}
        try:
            while not self._stop_event.is_set():
                idx = 0
                while idx < len(actions):
                    if self._stop_event.is_set():
                        break
                    action = actions[idx]

                    # Skip disabled actions and jump-target actions
                    if not action.enabled or idx in jump_targets:
                        idx += 1
                        continue

                    # ActionGroup: check image match, then execute children sub-loop
                    if isinstance(action, ActionGroup):
                        group: ActionGroup = action
                        self._notify(f"执行动作组 {idx + 1}", idx)
                        can_execute = True

                        if group.image_verify.enabled:
                            iv = group.image_verify
                            matched, _, _ = self._img.match(
                                iv.region, iv.template_data,
                                iv.threshold, iv.match_method,
                            )
                            if not matched:
                                if iv.on_fail == VerifyOnFail.WAIT:
                                    matched, _, _ = self._wait_for_image(iv)
                                if not matched:
                                    if iv.on_fail == VerifyOnFail.EXIT:
                                        self._stop_event.set()
                                        break
                                    can_execute = False

                        if can_execute:
                            child_jump_targets: set[int] = {
                                c.on_fail_jump for c in group.children
                                if c.on_fail_jump >= 0
                            }
                            ci = 0
                            while ci < len(group.children):
                                if self._stop_event.is_set():
                                    break
                                child = group.children[ci]
                                if not child.enabled or ci in child_jump_targets:
                                    ci += 1
                                    continue
                                self._notify(
                                    f"动作组 {idx+1} / 子步骤 {ci+1}", idx)
                                c_result, c_jump = self._execute_step(
                                    child, ci, group.children)
                                if c_result == StepResult.ABORTED:
                                    self._stop_event.set()
                                    break
                                if c_result == StepResult.JUMPED and c_jump is not None:
                                    ci = c_jump + 1
                                    continue
                                # child delay
                                c_total = child.delay_after_ms + settings.interval_ms
                                if settings.random_delay_max_ms > settings.random_delay_min_ms:
                                    c_total += random.randint(
                                        settings.random_delay_min_ms,
                                        settings.random_delay_max_ms)
                                elif settings.random_delay_min_ms > 0:
                                    c_total += settings.random_delay_min_ms
                                if c_total > 0:
                                    self._interruptible_sleep(c_total / 1000.0)
                                ci += 1

                        if self._stop_event.is_set():
                            break

                        # Group's own post-execution delay
                        total_ms = action.delay_after_ms + settings.interval_ms
                        if settings.random_delay_max_ms > settings.random_delay_min_ms:
                            total_ms += random.randint(
                                settings.random_delay_min_ms,
                                settings.random_delay_max_ms)
                        elif settings.random_delay_min_ms > 0:
                            total_ms += settings.random_delay_min_ms
                        if total_ms > 0:
                            self._interruptible_sleep(total_ms / 1000.0)
                        idx += 1
                        continue

                    self._notify(f"执行步骤 {idx + 1}", idx)
                    result, jump_to = self._execute_step(action, idx, actions)

                    if result == StepResult.ABORTED:
                        self._stop_event.set()
                        break

                    if result == StepResult.JUMPED and jump_to is not None:
                        # jump_to is already executed inside _execute_step,
                        # continue from the step after jump_to
                        idx = jump_to + 1
                        continue

                    # Per-step delay + global interval + random jitter
                    total_ms = action.delay_after_ms + settings.interval_ms
                    if settings.random_delay_max_ms > settings.random_delay_min_ms:
                        total_ms += random.randint(
                            settings.random_delay_min_ms,
                            settings.random_delay_max_ms,
                        )
                    elif settings.random_delay_min_ms > 0:
                        total_ms += settings.random_delay_min_ms

                    if total_ms > 0:
                        self._interruptible_sleep(total_ms / 1000.0)

                    idx += 1

                if self._stop_event.is_set():
                    break

                repeat += 1
                if settings.repeat_count != 0 and repeat >= settings.repeat_count:
                    break

        except Exception as e:
            self._notify(f"错误: {e}", -1)
        finally:
            self._notify("已停止", -1)

    def _execute_step(
        self,
        action: AnyAction,
        idx: int,
        actions: list[AnyAction],
    ) -> tuple[StepResult, Optional[int]]:
        """
        Run text verification (if enabled) then dispatch.
        Supports VerifyOnFail: EXIT (abort), SKIP, WAIT (poll with timeout),
        and on_fail_jump (linkage to another action).
        Returns (StepResult, jump_target_index_or_None).
        """
        fine_tune_x: Optional[int] = None
        fine_tune_y: Optional[int] = None

        if action.text_verify.enabled:
            met, ft_x, ft_y = self._check_text_verify(action.text_verify)
            if not met:
                # WAIT mode: poll OCR until condition met or timeout
                if action.text_verify.on_fail == VerifyOnFail.WAIT:
                    met, ft_x, ft_y = self._wait_for_text(action.text_verify)

                if not met:
                    if action.text_verify.on_fail == VerifyOnFail.EXIT:
                        return StepResult.ABORTED, None

                    # Check for jump linkage
                    jump_idx = action.on_fail_jump
                    if jump_idx >= 0 and jump_idx < len(actions):
                        jump_action = actions[jump_idx]
                        self._notify(f"联动跳转 → 步骤 {jump_idx + 1}", jump_idx)
                        jump_result, _ = self._execute_step(jump_action, jump_idx, actions)
                        if jump_result == StepResult.ABORTED:
                            return StepResult.ABORTED, None
                        return StepResult.JUMPED, jump_idx

                    return StepResult.SKIPPED, None
            fine_tune_x, fine_tune_y = ft_x, ft_y

        if action.image_verify.enabled and action.image_verify.template_data:
            iv = action.image_verify
            matched, iv_cx, iv_cy = self._img.match(
                iv.region, iv.template_data, iv.threshold, iv.match_method)
            if not matched:
                if iv.on_fail == VerifyOnFail.WAIT:
                    matched, iv_cx, iv_cy = self._wait_for_image(iv)
                if not matched:
                    if iv.on_fail == VerifyOnFail.EXIT:
                        return StepResult.ABORTED, None
                    jump_idx = action.on_fail_jump
                    if jump_idx >= 0 and jump_idx < len(actions):
                        jump_action = actions[jump_idx]
                        self._notify(f"联动跳转(图) → 步骤 {jump_idx + 1}", jump_idx)
                        jr, _ = self._execute_step(jump_action, jump_idx, actions)
                        if jr == StepResult.ABORTED:
                            return StepResult.ABORTED, None
                        return StepResult.JUMPED, jump_idx
                    return StepResult.SKIPPED, None
            # Override fine-tune with image match center (similar to text fine-tune)
            if fine_tune_x is None:
                fine_tune_x = iv_cx
                fine_tune_y = iv_cy

        try:
            self._dispatch(action, fine_tune_x, fine_tune_y)
        except Exception as e:
            self._notify(f"步骤 {idx + 1} 执行失败: {e}", idx)
            return StepResult.ABORTED, None

        return StepResult.SUCCESS, None

    def _dispatch(
        self,
        action: AnyAction,
        ft_x: Optional[int],
        ft_y: Optional[int],
    ) -> None:
        """Dispatch action to the appropriate InputSimulator method."""
        t = action.action_type

        if t == ActionType.ACTION_GROUP:
            return  # handled upstream in _run_loop

        if t == ActionType.WAIT:
            a: WaitAction = action
            self._interruptible_sleep(a.wait_ms / 1000.0)
            return

        if t == ActionType.CLICK_ONCE:
            a: ClickOnceAction = action
            if ft_x is not None and ft_y is not None:
                x, y = ft_x, ft_y  # fine-tune returns absolute coords, don't resolve
            else:
                x, y = self._resolve_coords(a, a.x, a.y)
            self._sim.click_once(x, y, a.hold_ms)

        elif t == ActionType.CLICK_HOLD:
            a: ClickHoldAction = action
            if ft_x is not None and ft_y is not None:
                x, y = ft_x, ft_y
            else:
                x, y = self._resolve_coords(a, a.x, a.y)
            self._sim.click_hold(x, y, a.hold_ms)

        elif t == ActionType.SCROLL:
            a: ScrollAction = action
            x, y = self._resolve_coords(a, a.x, a.y)
            self._sim.scroll(x, y, a.direction, a.amount)

        elif t == ActionType.MIDDLE_CLICK:
            a: MiddleClickAction = action
            if ft_x is not None and ft_y is not None:
                x, y = ft_x, ft_y
            else:
                x, y = self._resolve_coords(a, a.x, a.y)
            self._sim.middle_click(x, y, a.hold_ms)

        elif t == ActionType.KEY_PRESS:
            a: KeyPressAction = action
            self._sim.key_press(a.keys, a.hold_ms)

        elif t == ActionType.DRAG:
            a: DragAction = action
            start_x, start_y = self._resolve_coords(a, a.start_x, a.start_y)
            end_x, end_y = self._resolve_coords(a, a.end_x, a.end_y)
            self._sim.drag(start_x, start_y, end_x, end_y, a.duration_ms, a.steps)

    def _check_text_verify(
        self,
        tv: TextVerification,
    ) -> tuple[bool, Optional[int], Optional[int]]:
        """
        Run OCR on the configured region and check if the condition is met.
        Returns (condition_met, fine_tune_abs_x, fine_tune_abs_y).
        fine_tune coords are None when fine_tune is disabled or text not found.
        """
        try:
            results = self._ocr.recognize(tv.region)
            match = self._ocr.match(results, tv.target_text, tv.match_mode)
        except Exception:
            # OCR failure: treat as "not found"
            match = None

        found = match is not None
        condition_met = found if tv.require_found else not found

        if not condition_met:
            return False, None, None

        # Fine-tune: adjust click position toward the found text center
        if tv.fine_tune and match is not None:
            max_off = tv.fine_tune_max_offset
            raw_dx = match.abs_center_x
            raw_dy = match.abs_center_y
            # Clamp offset relative to original action position is handled in _dispatch
            # Here we just return the absolute OCR center, clamped to max_offset from region center
            region_cx = tv.region.x + tv.region.w // 2
            region_cy = tv.region.y + tv.region.h // 2
            dx = max(-max_off, min(max_off, match.abs_center_x - region_cx))
            dy = max(-max_off, min(max_off, match.abs_center_y - region_cy))
            return True, region_cx + dx, region_cy + dy

        return True, None, None

    def _wait_for_image(
        self,
        iv: ImageVerification,
        timeout_ms: int = 5000,
    ) -> tuple[bool, int, int]:
        """Poll image matching until found or timeout. Returns (matched, cx, cy)."""
        start = time.monotonic()
        while not self._stop_event.is_set():
            elapsed = (time.monotonic() - start) * 1000
            if elapsed >= timeout_ms:
                self._notify("图像等待超时", -1)
                return False, 0, 0
            matched, cx, cy = self._img.match(
                iv.region, iv.template_data, iv.threshold, iv.match_method)
            if matched:
                return True, cx, cy
            self._interruptible_sleep(0.2)
        return False, 0, 0

    def _wait_for_text(
        self,
        tv: TextVerification,
    ) -> tuple[bool, Optional[int], Optional[int]]:
        """
        Poll OCR until the text condition is met or wait_timeout_ms expires.
        Returns (condition_met, fine_tune_x, fine_tune_y) like _check_text_verify.
        """
        start = time.monotonic()
        timeout_ms = tv.wait_timeout_ms
        while not self._stop_event.is_set():
            elapsed_ms = (time.monotonic() - start) * 1000
            if elapsed_ms >= timeout_ms:
                self._notify("等待超时", -1)
                return False, None, None

            try:
                results = self._ocr.recognize(tv.region)
                match = self._ocr.match(results, tv.target_text, tv.match_mode)
            except Exception:
                match = None

            found = match is not None
            condition_met = found if tv.require_found else not found

            if condition_met:
                if tv.fine_tune and match is not None:
                    max_off = tv.fine_tune_max_offset
                    region_cx = tv.region.x + tv.region.w // 2
                    region_cy = tv.region.y + tv.region.h // 2
                    dx = max(-max_off, min(max_off, match.abs_center_x - region_cx))
                    dy = max(-max_off, min(max_off, match.abs_center_y - region_cy))
                    return True, region_cx + dx, region_cy + dy
                return True, None, None

            # Sleep 200ms between polls (responsive but not CPU-heavy)
            self._interruptible_sleep(0.2)

        return False, None, None

    def _resolve_coords(self, action: AnyAction, x: int, y: int) -> tuple[int, int]:
        """
        Resolve stored coordinates to absolute screen coords based on coord_mode.
        For RELATIVE_TO_WINDOW, finds the target window and applies offset + scaling.
        """
        if action.coord_mode != CoordMode.RELATIVE_TO_WINDOW:
            return x, y

        if not self._current_settings or not self._current_settings.target_window_title:
            self._notify("警告: 未设置目标窗口标题", -1)
            return x, y

        hwnd = find_window_by_title(self._current_settings.target_window_title)
        if hwnd is None:
            self._notify(f"警告: 未找到窗口 '{self._current_settings.target_window_title}'", -1)
            return x, y

        rect = get_window_rect(hwnd)
        if rect is None:
            self._notify("警告: 无法获取窗口位置", -1)
            return x, y

        win_left, win_top = rect[0], rect[1]
        cur_w = rect[2] - rect[0]
        cur_h = rect[3] - rect[1]

        ref_w = self._current_settings.reference_window_width
        ref_h = self._current_settings.reference_window_height

        scale_x = cur_w / ref_w if ref_w > 0 else 1.0
        scale_y = cur_h / ref_h if ref_h > 0 else 1.0

        return (win_left + int(x * scale_x), win_top + int(y * scale_y))

    def _interruptible_sleep(self, seconds: float) -> None:
        """Sleep in small chunks so stop_event is checked frequently."""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self._stop_event.is_set():
                return
            time.sleep(min(0.05, end - time.monotonic()))


class HotkeyListener:
    """
    Listens for a global hotkey and toggles the macro executor.
    Runs in its own daemon thread for the lifetime of the application.
    """

    def __init__(self, executor: MacroExecutor) -> None:
        self._executor = executor
        self._listener = None
        self._hotkey_str = "f6"
        self._get_actions_cb: Optional[Callable] = None
        self._get_settings_cb: Optional[Callable] = None

    def set_callbacks(
        self,
        get_actions: Callable[[], list[AnyAction]],
        get_settings: Callable[[], GlobalSettings],
    ) -> None:
        self._get_actions_cb = get_actions
        self._get_settings_cb = get_settings

    def update_hotkey(self, hotkey_str: str) -> None:
        """Update the hotkey and restart the listener."""
        self._hotkey_str = hotkey_str.lower().strip()
        self._restart()

    def start(self, hotkey_str: str) -> None:
        self._hotkey_str = hotkey_str.lower().strip()
        self._restart()

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None

    def _restart(self) -> None:
        self.stop()
        try:
            from pynput import keyboard as _kb

            def on_activate():
                if self._executor.is_running():
                    self._executor.stop()
                else:
                    if self._get_actions_cb and self._get_settings_cb:
                        actions = self._get_actions_cb()
                        settings = self._get_settings_cb()
                        if actions:
                            self._executor.start(actions, settings)

            hotkey_combo = f"<{self._hotkey_str}>" if len(self._hotkey_str) > 1 else self._hotkey_str
            self._listener = _kb.GlobalHotKeys({hotkey_combo: on_activate})
            self._listener.daemon = True
            self._listener.start()
        except Exception:
            pass  # Hotkey registration failure is non-fatal
