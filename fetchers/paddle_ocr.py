from __future__ import annotations

import json
import threading
from collections.abc import Callable, Mapping
from functools import lru_cache
from typing import Any

import cv2
import numpy as np


_OCR_LOCK = threading.Lock()
_ZODIAC_TRANSLATION = str.maketrans("龍馬雞豬", "龙马鸡猪")


@lru_cache(maxsize=1)
def build_paddle_engine():
    from paddleocr import PaddleOCR

    return PaddleOCR(
        device="cpu",
        text_detection_model_name="PP-OCRv5_mobile_det",
        text_recognition_model_name="PP-OCRv5_mobile_rec",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        enable_mkldnn=False,
    )


def texts_from_result(value: Any) -> tuple[str, ...]:
    payload = getattr(value, "json", value)
    if callable(payload):
        payload = payload()
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return ()
    if isinstance(payload, Mapping):
        texts = payload.get("rec_texts")
        if isinstance(texts, (list, tuple)):
            return tuple(
                normalized
                for item in texts
                if (normalized := str(item).strip())
            )
        for key in ("res", "result", "data"):
            if key in payload:
                nested = texts_from_result(payload[key])
                if nested:
                    return nested
    return ()


class PaddleOcrReader:
    def __init__(self, engine_factory: Callable[[], Any] = build_paddle_engine):
        self._engine_factory = engine_factory

    def __call__(self, content: bytes) -> str:
        if not content:
            return ""
        encoded = np.frombuffer(content, dtype=np.uint8)
        image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if image is None:
            return ""
        try:
            with _OCR_LOCK:
                results = self._engine_factory().predict(image)
                lines = tuple(
                    text
                    for result in results
                    for text in texts_from_result(result)
                )
        except Exception:
            return ""
        return "\n".join(lines).translate(_ZODIAC_TRANSLATION)
