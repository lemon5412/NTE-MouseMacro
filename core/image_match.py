"""
OpenCV template matching for image-based action triggers.
Uses mss for screenshot, cv2 for template matching, PIL for encoding.
All dependencies already installed (mss, opencv-python-headless via rapidocr, Pillow).
"""
from __future__ import annotations
import base64
import io
from typing import Optional

import cv2
import mss
import numpy as np
from PIL import Image

from core.action import OcrRegion


class ImageMatcher:
    """Captures screen regions and matches them against stored template images."""

    METHOD_MAP = {
        "TM_CCOEFF_NORMED":  cv2.TM_CCOEFF_NORMED,
        "TM_CCORR_NORMED":   cv2.TM_CCORR_NORMED,
        "TM_SQDIFF_NORMED":  cv2.TM_SQDIFF_NORMED,
    }

    def capture_template(self, region: OcrRegion) -> str:
        """Capture a screen region and return a base64-encoded PNG string."""
        with mss.mss() as sct:
            monitor = {
                "left": region.x, "top": region.y,
                "width": region.w, "height": region.h,
            }
            screenshot = sct.grab(monitor)
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("ascii")

    @staticmethod
    def _base64_to_cv2(data: str) -> np.ndarray:
        """Decode a base64 PNG string to a BGR numpy array (cv2 format)."""
        raw = base64.b64decode(data)
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        arr = np.array(img)
        return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

    def match(
        self,
        region: OcrRegion,
        template_base64: str,
        threshold: float = 0.8,
        method: str = "TM_CCOEFF_NORMED",
    ) -> tuple[bool, int, int]:
        """
        Capture the screen region and match against the stored template.
        Returns (matched, center_x, center_y) — center coords are absolute screen pixels.
        """
        # Capture current screen region
        with mss.mss() as sct:
            monitor = {
                "left": region.x, "top": region.y,
                "width": region.w, "height": region.h,
            }
            screenshot = sct.grab(monitor)
            screen_img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
        screen_bgr = cv2.cvtColor(np.array(screen_img), cv2.COLOR_RGB2BGR)

        # Decode template
        template_bgr = self._base64_to_cv2(template_base64)
        th, tw = template_bgr.shape[:2]
        sh, sw = screen_bgr.shape[:2]
        if th > sh or tw > sw:
            return False, 0, 0

        # Run template matching
        cv_method = self.METHOD_MAP.get(method, cv2.TM_CCOEFF_NORMED)
        result = cv2.matchTemplate(screen_bgr, template_bgr, cv_method)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if "SQDIFF" in method:
            matched = max_val <= (1.0 - threshold)
        else:
            matched = max_val >= threshold

        if matched:
            center_x = region.x + max_loc[0] + tw // 2
            center_y = region.y + max_loc[1] + th // 2
            return True, center_x, center_y
        return False, 0, 0
