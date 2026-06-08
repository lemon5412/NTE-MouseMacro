"""
JSON import/export for macro configurations.
Uses action_type as a discriminator key for deserialization.
"""
from __future__ import annotations
import json
from dataclasses import asdict
from typing import Any

from core.action import (
    ActionType, MatchMode, VerifyOnFail, CoordMode,
    OcrRegion, TextVerification, ImageVerification, GlobalSettings,
    ActionGroup, ACTION_CLASS_MAP, AnyAction,
    ClickOnceAction, ClickHoldAction, ScrollAction,
    MiddleClickAction, KeyPressAction, DragAction, WaitAction,
)

CONFIG_VERSION = "1.1"


def _serialize_action(action: AnyAction) -> dict:
    """Convert an action dataclass to a JSON-serializable dict."""
    d = asdict(action)
    d["action_type"] = action.action_type.value
    tv = d.get("text_verify", {})
    if tv:
        tv["match_mode"] = action.text_verify.match_mode.value
        tv["on_fail"] = action.text_verify.on_fail.value
    iv = d.get("image_verify", {})
    if iv and action.image_verify.template_data:
        iv["on_fail"] = action.image_verify.on_fail.value
    # Recursively serialize children for ActionGroup
    if action.action_type == ActionType.ACTION_GROUP:
        d["children"] = [_serialize_action(c) for c in action.children]
    return d


def _deserialize_image_verify(iv_data: dict) -> ImageVerification:
    iv_region_data = iv_data.get("region", {})
    return ImageVerification(
        enabled=iv_data.get("enabled", False),
        region=OcrRegion(
            x=iv_region_data.get("x", 0), y=iv_region_data.get("y", 0),
            w=iv_region_data.get("w", 200), h=iv_region_data.get("h", 50),
        ),
        template_data=iv_data.get("template_data", ""),
        match_method=iv_data.get("match_method", "TM_CCOEFF_NORMED"),
        threshold=iv_data.get("threshold", 0.8),
        on_fail=VerifyOnFail(iv_data.get("on_fail", VerifyOnFail.SKIP.value)),
    )


def _deserialize_action(d: dict) -> AnyAction:
    """Reconstruct an action dataclass from a dict."""
    action_type = ActionType(d["action_type"])

    # ActionGroup: handle nested children
    if action_type == ActionType.ACTION_GROUP:
        iv = _deserialize_image_verify(d.get("image_verify", {}))
        children = [_deserialize_action(c) for c in d.get("children", [])]
        return ActionGroup(
            action_type=ActionType.ACTION_GROUP,
            label=d.get("label", ""),
            enabled=d.get("enabled", True),
            delay_after_ms=d.get("delay_after_ms", 0),
            coord_mode=CoordMode(d.get("coord_mode", CoordMode.ABSOLUTE.value)),
            on_fail_jump=d.get("on_fail_jump", -1),
            image_verify=iv,
            children=children,
        )

    cls = ACTION_CLASS_MAP[action_type]

    # Reconstruct nested objects
    tv_data = d.get("text_verify", {})
    region_data = tv_data.get("region", {})
    region = OcrRegion(
        x=region_data.get("x", 0),
        y=region_data.get("y", 0),
        w=region_data.get("w", 200),
        h=region_data.get("h", 50),
    )
    text_verify = TextVerification(
        enabled=tv_data.get("enabled", False),
        region=region,
        target_text=tv_data.get("target_text", ""),
        match_mode=MatchMode(tv_data.get("match_mode", MatchMode.CONTAINS.value)),
        require_found=tv_data.get("require_found", True),
        on_fail=VerifyOnFail(tv_data.get("on_fail", VerifyOnFail.SKIP.value)),
        fine_tune=tv_data.get("fine_tune", False),
        fine_tune_max_offset=tv_data.get("fine_tune_max_offset", 50),
        wait_timeout_ms=tv_data.get("wait_timeout_ms", 5000),
    )

    # Build kwargs for the concrete class, excluding nested objects we handle manually
    kwargs: dict[str, Any] = {
        "action_type": action_type,
        "label": d.get("label", ""),
        "enabled": d.get("enabled", True),
        "delay_after_ms": d.get("delay_after_ms", 0),
        "text_verify": text_verify,
        "coord_mode": CoordMode(d.get("coord_mode", CoordMode.ABSOLUTE.value)),
        "on_fail_jump": d.get("on_fail_jump", -1),
        "image_verify": _deserialize_image_verify(d.get("image_verify", {})),
    }

    if action_type in (ActionType.CLICK_ONCE, ActionType.CLICK_HOLD, ActionType.MIDDLE_CLICK):
        kwargs["x"] = d.get("x", 0)
        kwargs["y"] = d.get("y", 0)
        kwargs["hold_ms"] = d.get("hold_ms", 50)

    elif action_type == ActionType.SCROLL:
        kwargs["x"] = d.get("x", 0)
        kwargs["y"] = d.get("y", 0)
        kwargs["direction"] = d.get("direction", "down")
        kwargs["amount"] = d.get("amount", 3)

    elif action_type == ActionType.KEY_PRESS:
        kwargs["keys"] = d.get("keys", [])
        kwargs["hold_ms"] = d.get("hold_ms", 50)

    elif action_type == ActionType.DRAG:
        kwargs["start_x"] = d.get("start_x", 0)
        kwargs["start_y"] = d.get("start_y", 0)
        kwargs["end_x"] = d.get("end_x", 100)
        kwargs["end_y"] = d.get("end_y", 100)
        kwargs["duration_ms"] = d.get("duration_ms", 300)
        kwargs["steps"] = d.get("steps", 20)

    elif action_type == ActionType.WAIT:
        kwargs["wait_ms"] = d.get("wait_ms", 1000)

    return cls(**kwargs)


def _serialize_settings(settings: GlobalSettings) -> dict:
    return asdict(settings)


def _deserialize_settings(d: dict) -> GlobalSettings:
    return GlobalSettings(
        repeat_count=d.get("repeat_count", 1),
        interval_ms=d.get("interval_ms", 100),
        random_delay_min_ms=d.get("random_delay_min_ms", 0),
        random_delay_max_ms=d.get("random_delay_max_ms", 0),
        start_stop_hotkey=d.get("start_stop_hotkey", "f6"),
        stop_on_error=d.get("stop_on_error", True),
        target_window_title=d.get("target_window_title", ""),
        reference_window_width=d.get("reference_window_width", 0),
        reference_window_height=d.get("reference_window_height", 0),
        mouse_speed_ms=d.get("mouse_speed_ms", 80),
        window_monitor_locked=d.get("window_monitor_locked", False),
        relative_coords_enabled=d.get("relative_coords_enabled", False),
    )


class ConfigManager:
    """Handles JSON import and export of macro configurations."""

    @staticmethod
    def export(
        actions: list[AnyAction],
        settings: GlobalSettings,
        filepath: str,
    ) -> None:
        """Serialize actions and settings to a JSON file."""
        data = {
            "version": CONFIG_VERSION,
            "settings": _serialize_settings(settings),
            "actions": [_serialize_action(a) for a in actions],
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def import_file(filepath: str) -> tuple[list[AnyAction], GlobalSettings]:
        """Load actions and settings from a JSON file."""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        settings = _deserialize_settings(data.get("settings", {}))
        actions = [_deserialize_action(a) for a in data.get("actions", [])]
        return actions, settings
