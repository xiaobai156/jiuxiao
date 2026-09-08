from __future__ import annotations

import importlib.util
import io
import sys
import types
from pathlib import Path

import numpy as np
import pytest
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if "v2" not in sys.modules:
    specification = importlib.util.spec_from_file_location(
        "v2",
        PROJECT_ROOT / "__init__.py",
        submodule_search_locations=[str(PROJECT_ROOT)],
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("无法加载 V2 测试包")
    package = importlib.util.module_from_spec(specification)
    sys.modules["v2"] = package
    specification.loader.exec_module(package)

from v2.fetchers.paddle_ocr import (  # noqa: E402
    PaddleOcrReader,
    build_paddle_engine,
    texts_from_result,
)


def png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (20, 10), color="white").save(buffer, format="PNG")
    return buffer.getvalue()


class JsonResult:
    def __init__(self, payload):
        self.json = payload


class FakeEngine:
    def __init__(self, result=None, error: Exception | None = None):
        self.result = result if result is not None else []
        self.error = error
        self.inputs = []

    def predict(self, image):
        self.inputs.append(image)
        if self.error is not None:
            raise self.error
        return self.result


def test_texts_from_result_supports_paddle_v3_nested_json() -> None:
    result = JsonResult(
        {
            "res": {
                "rec_texts": [
                    "228期风神九肖",
                    "228期：羊马蛇龙兔虎牛鼠猪",
                ]
            }
        }
    )

    assert texts_from_result(result) == (
        "228期风神九肖",
        "228期：羊马蛇龙兔虎牛鼠猪",
    )


def test_texts_from_result_supports_direct_mapping_and_keeps_order() -> None:
    assert texts_from_result(
        {"rec_texts": ["第一行", "", "第二行"]}
    ) == ("第一行", "第二行")


def test_texts_from_result_supports_json_string() -> None:
    assert texts_from_result(
        JsonResult('{"res":{"rec_texts":["兔","龙"]}}')
    ) == ("兔", "龙")


def test_texts_from_result_ignores_unknown_shape() -> None:
    assert texts_from_result({"boxes": []}) == ()
    assert texts_from_result({"res": {"boxes": []}}) == ()


def test_reader_decodes_png_bytes_and_preserves_recognition_line_order() -> None:
    engine = FakeEngine(
        [
            JsonResult({"res": {"rec_texts": ["228期", "羊牛鸡"]}}),
            {"rec_texts": ["第三行"]},
        ]
    )

    text = PaddleOcrReader(lambda: engine)(png_bytes())

    assert text == "228期\n羊牛鸡\n第三行"
    assert len(engine.inputs) == 1
    assert isinstance(engine.inputs[0], np.ndarray)
    assert engine.inputs[0].shape[:2] == (10, 20)


def test_reader_normalizes_traditional_zodiac_characters() -> None:
    engine = FakeEngine(
        [JsonResult({"res": {"rec_texts": ["龍馬雞豬"]}})]
    )

    assert PaddleOcrReader(lambda: engine)(png_bytes()) == "龙马鸡猪"


def test_reader_returns_empty_for_empty_bytes_without_calling_engine() -> None:
    engine = FakeEngine()

    assert PaddleOcrReader(lambda: engine)(b"") == ""
    assert engine.inputs == []


def test_reader_returns_empty_for_bad_image_without_calling_engine() -> None:
    engine = FakeEngine()

    assert PaddleOcrReader(lambda: engine)(b"not-an-image") == ""
    assert engine.inputs == []


def test_reader_returns_empty_when_engine_raises() -> None:
    engine = FakeEngine(error=RuntimeError("inference failed"))

    assert PaddleOcrReader(lambda: engine)(png_bytes()) == ""


def test_reader_returns_empty_when_engine_factory_raises() -> None:
    def exploding_factory():
        raise RuntimeError("engine construction failed")

    assert PaddleOcrReader(exploding_factory)(png_bytes()) == ""


def test_build_paddle_engine_uses_cpu_mobile_models_and_disables_corrections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    class FakePaddleOCR:
        def __init__(self, **kwargs):
            calls.append(kwargs)

    fake_paddleocr = types.ModuleType("paddleocr")
    fake_paddleocr.PaddleOCR = FakePaddleOCR
    monkeypatch.setitem(sys.modules, "paddleocr", fake_paddleocr)

    cache_clear = getattr(build_paddle_engine, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()
    try:
        engine = build_paddle_engine()
    finally:
        if cache_clear is not None:
            cache_clear()

    assert isinstance(engine, FakePaddleOCR)
    assert calls == [
        {
            "device": "cpu",
            "text_detection_model_name": "PP-OCRv5_mobile_det",
            "text_recognition_model_name": "PP-OCRv5_mobile_rec",
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": False,
            "enable_mkldnn": False,
        }
    ]
