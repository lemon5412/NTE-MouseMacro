"""
OCR engine wrapper using RapidOCR (onnxruntime backend).
Lazy-loads the model on first use to avoid slow startup.
No torch dependency — much smaller package size.
"""
from __future__ import annotations
import re
import threading
from dataclasses import dataclass
from typing import Optional

import mss
import numpy as np
from PIL import Image

from core.action import OcrRegion, MatchMode


@dataclass
class OcrResult:
    text: str
    confidence: float
    # Bounding box relative to the captured region
    bbox_x: int
    bbox_y: int
    bbox_w: int
    bbox_h: int
    # Absolute screen center of the found text
    abs_center_x: int
    abs_center_y: int


class OcrEngine:
    """
    Wraps RapidOCR for screen text recognition.
    Uses PaddleOCR-compatible models via ONNX Runtime — no torch required.
    Call warm_up() in a background thread at app start to avoid first-use delay.
    """

    def __init__(self) -> None:
        self._ocr = None
        self._lock = threading.Lock()
        self._ready = False

    def warm_up(self) -> None:
        """Pre-load the OCR model. Safe to call from a background thread."""
        self._get_ocr()

    def _get_ocr(self):
        with self._lock:
            if self._ocr is None:
                try:
                    from rapidocr_onnxruntime import RapidOCR
                    self._ocr = RapidOCR()
                    self._ready = True
                except Exception as e:
                    raise RuntimeError(f"RapidOCR 加载失败: {e}") from e
        return self._ocr

    @property
    def is_ready(self) -> bool:
        return self._ready

    def capture_region(self, region: OcrRegion) -> np.ndarray:
        """Capture a screen region and return as an RGB numpy array."""
        with mss.mss() as sct:
            monitor = {
                "left": region.x,
                "top": region.y,
                "width": region.w,
                "height": region.h,
            }
            screenshot = sct.grab(monitor)
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            return np.array(img)

    def recognize(self, region: OcrRegion) -> list[OcrResult]:
        """
        Capture the given screen region and run OCR.
        Returns a list of OcrResult objects sorted by confidence descending.

        RapidOCR result format:
            result: list of [bbox, text, confidence]
            bbox = [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
        """
        ocr = self._get_ocr()
        img_array = self.capture_region(region)

        raw, _ = ocr(img_array)
        results: list[OcrResult] = []

        if not raw:
            return results

        for item in raw:
            box, text, conf = item
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            bx = int(min(xs))
            by = int(min(ys))
            bw = int(max(xs) - min(xs))
            bh = int(max(ys) - min(ys))
            abs_cx = region.x + bx + bw // 2
            abs_cy = region.y + by + bh // 2
            results.append(OcrResult(
                text=text,
                confidence=float(conf),
                bbox_x=bx, bbox_y=by, bbox_w=bw, bbox_h=bh,
                abs_center_x=abs_cx, abs_center_y=abs_cy,
            ))

        # Sort by position: top-to-bottom, left-to-right (reading order)
        results.sort(key=lambda r: (r.bbox_y, r.bbox_x))
        return results

    def match(
        self,
        results: list[OcrResult],
        target_text: str,
        mode: MatchMode,
    ) -> Optional[OcrResult]:
        """
        Find the first OcrResult that matches target_text according to mode.
        Returns None if no match found.
        """
        for r in results:
            if self._text_matches(r.text, target_text, mode):
                return r
        return None

    @staticmethod
    def _text_matches(text: str, target: str, mode: MatchMode) -> bool:
        if mode == MatchMode.EXACT:
            return text.strip() == target.strip()
        elif mode == MatchMode.CONTAINS:
            return target.strip() in text
        elif mode == MatchMode.REGEX:
            try:
                return bool(re.search(target, text))
            except re.error:
                return False
        return False
