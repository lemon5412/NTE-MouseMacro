"""
Action data models for the macro tool.
All action types are represented as dataclasses with a common base.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ActionType(str, Enum):
    CLICK_ONCE   = "click_once"
    CLICK_HOLD   = "click_hold"
    SCROLL       = "scroll"
    MIDDLE_CLICK = "middle_click"
    KEY_PRESS    = "key_press"
    DRAG         = "drag"
    ACTION_GROUP = "action_group"
    WAIT         = "wait"


ACTION_TYPE_LABELS = {
    ActionType.CLICK_ONCE:   "单击",
    ActionType.CLICK_HOLD:   "长按",
    ActionType.SCROLL:       "滚动",
    ActionType.MIDDLE_CLICK: "中键",
    ActionType.KEY_PRESS:    "键盘",
    ActionType.DRAG:         "拖动",
    ActionType.ACTION_GROUP: "动作组",
    ActionType.WAIT:         "等待",
}


class MatchMode(str, Enum):
    EXACT    = "exact"
    CONTAINS = "contains"
    REGEX    = "regex"


MATCH_MODE_LABELS = {
    MatchMode.EXACT:    "精确匹配",
    MatchMode.CONTAINS: "包含",
    MatchMode.REGEX:    "正则",
}


class VerifyOnFail(str, Enum):
    SKIP = "skip"
    EXIT = "exit"
    WAIT = "wait"


VERIFY_ON_FAIL_LABELS = {
    VerifyOnFail.SKIP: "跳过此步骤",
    VerifyOnFail.EXIT: "退出脚本",
    VerifyOnFail.WAIT: "等待条件满足",
}


class CoordMode(str, Enum):
    ABSOLUTE = "absolute"
    RELATIVE_TO_WINDOW = "relative"


COORD_MODE_LABELS = {
    CoordMode.ABSOLUTE: "绝对坐标",
    CoordMode.RELATIVE_TO_WINDOW: "相对窗口",
}


@dataclass
class OcrRegion:
    x: int = 0
    y: int = 0
    w: int = 200
    h: int = 50

    def as_tuple(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.w, self.h)


@dataclass
class ImageVerification:
    """Image matching configuration for ActionGroup triggers."""
    enabled: bool = False
    region: OcrRegion = field(default_factory=OcrRegion)
    template_data: str = ""               # base64-encoded PNG
    match_method: str = "TM_CCOEFF_NORMED"
    threshold: float = 0.8
    on_fail: VerifyOnFail = VerifyOnFail.SKIP


@dataclass
class TextVerification:
    enabled: bool = False
    region: OcrRegion = field(default_factory=OcrRegion)
    target_text: str = ""
    match_mode: MatchMode = MatchMode.CONTAINS
    require_found: bool = True          # True = execute only if found
    on_fail: VerifyOnFail = VerifyOnFail.SKIP
    fine_tune: bool = False             # adjust click pos toward found text center
    fine_tune_max_offset: int = 50      # pixels
    wait_timeout_ms: int = 5000         # timeout for WAIT mode polling


@dataclass
class ActionBase:
    action_type: ActionType = ActionType.CLICK_ONCE
    label: str = ""
    enabled: bool = True
    delay_after_ms: int = 0
    text_verify: TextVerification = field(default_factory=TextVerification)
    image_verify: ImageVerification = field(default_factory=ImageVerification)
    coord_mode: CoordMode = CoordMode.ABSOLUTE
    on_fail_jump: int = -1   # index of action to execute when text_verify fails; -1 = no jump

    def display_label(self) -> str:
        """Return a human-readable label for the action list."""
        type_label = ACTION_TYPE_LABELS.get(self.action_type, self.action_type)
        if self.label:
            return f"{type_label}: {self.label}"
        return type_label

    def description(self) -> str:
        """Return a short description string shown in the action list."""
        return ""


@dataclass
class ClickOnceAction(ActionBase):
    action_type: ActionType = ActionType.CLICK_ONCE
    x: int = 0
    y: int = 0
    hold_ms: int = 50

    def description(self) -> str:
        return f"({self.x}, {self.y})  按住 {self.hold_ms}ms"


@dataclass
class ClickHoldAction(ActionBase):
    action_type: ActionType = ActionType.CLICK_HOLD
    x: int = 0
    y: int = 0
    hold_ms: int = 1000

    def description(self) -> str:
        return f"({self.x}, {self.y})  持续 {self.hold_ms}ms"


@dataclass
class ScrollAction(ActionBase):
    action_type: ActionType = ActionType.SCROLL
    x: int = 0
    y: int = 0
    direction: str = "down"   # "up" | "down"
    amount: int = 3

    def description(self) -> str:
        arrow = "↑" if self.direction == "up" else "↓"
        return f"({self.x}, {self.y})  {arrow} {self.amount}格"


@dataclass
class MiddleClickAction(ActionBase):
    action_type: ActionType = ActionType.MIDDLE_CLICK
    x: int = 0
    y: int = 0
    hold_ms: int = 50

    def description(self) -> str:
        return f"({self.x}, {self.y})  按住 {self.hold_ms}ms"


@dataclass
class KeyPressAction(ActionBase):
    action_type: ActionType = ActionType.KEY_PRESS
    keys: list = field(default_factory=list)   # e.g. ["ctrl", "c"]
    hold_ms: int = 50

    def description(self) -> str:
        combo = "+".join(k.upper() for k in self.keys) if self.keys else "(未设置)"
        return f"{combo}  按住 {self.hold_ms}ms"


@dataclass
class DragAction(ActionBase):
    action_type: ActionType = ActionType.DRAG
    start_x: int = 0
    start_y: int = 0
    end_x: int = 100
    end_y: int = 100
    duration_ms: int = 300
    steps: int = 20

    def description(self) -> str:
        return f"({self.start_x},{self.start_y})→({self.end_x},{self.end_y})  {self.duration_ms}ms"


@dataclass
class WaitAction(ActionBase):
    action_type: ActionType = ActionType.WAIT
    wait_ms: int = 1000

    def description(self) -> str:
        return f"等待 {self.wait_ms}ms"


@dataclass
class ActionGroup(ActionBase):
    action_type: ActionType = ActionType.ACTION_GROUP
    children: list = field(default_factory=list)       # list[AnyAction]

    def description(self) -> str:
        n = len(self.children)
        iv = " [I]" if self.image_verify.enabled and self.image_verify.template_data else ""
        return f"{n} 个子动作{iv}"


# Union type alias
AnyAction = ActionBase  # runtime isinstance checks use the concrete classes


@dataclass
class GlobalSettings:
    repeat_count: int = 1               # 0 = infinite
    interval_ms: int = 100              # delay between steps
    random_delay_min_ms: int = 0
    random_delay_max_ms: int = 0
    start_stop_hotkey: str = "f6"
    stop_on_error: bool = True
    target_window_title: str = ""           # title of target window for relative coords
    reference_window_width: int = 0         # recorded window width (0 = don't scale)
    reference_window_height: int = 0        # recorded window height (0 = don't scale)
    mouse_speed_ms: int = 80                # smooth mouse movement duration
    window_monitor_locked: bool = False     # continuously track window resolution when True
    relative_coords_enabled: bool = False   # show relative-coords UI features when True


# Map ActionType → concrete class for deserialization
ACTION_CLASS_MAP: dict[ActionType, type] = {
    ActionType.CLICK_ONCE:   ClickOnceAction,
    ActionType.CLICK_HOLD:   ClickHoldAction,
    ActionType.SCROLL:       ScrollAction,
    ActionType.MIDDLE_CLICK: MiddleClickAction,
    ActionType.KEY_PRESS:    KeyPressAction,
    ActionType.DRAG:         DragAction,
    ActionType.ACTION_GROUP: ActionGroup,
    ActionType.WAIT:         WaitAction,
}
