from __future__ import annotations

import importlib.util
import sys
from dataclasses import replace
from pathlib import Path

import pytest


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

from v2.config.repository import SourceRepository  # noqa: E402
from v2.domain.errors import ErrorCode  # noqa: E402
from v2.domain.models import (  # noqa: E402
    Document,
    DocumentMethod,
    Position,
    Source,
)
from v2.parsers.direct_nine import DirectNineParser  # noqa: E402
from v2.parsers.registry import ParseError  # noqa: E402
from v2.validator import ValidationError, Validator  # noqa: E402


URL = "https://4.48kk49.com:1888/Article/ar_content/id/1402/tid/81.html"
MARKER = "流星恋月【九肖中特】"
PAGE_TEXT = """
236期: 流星恋月【九肖中特】
236期 流星恋月九肖 :【鸡猪羊鼠猴虎马狗龙】 开 ?? 准
235期 流星恋月九肖 :【鸡羊虎猴猪马牛狗龙】 开 32,猪 准
234期 流星恋月九肖 :【龙猴猪马蛇兔羊狗鼠】 开 39,龙 准
232期 流星恋月九肖 :【马鸡牛猪虎兔猴蛇狗】 开 42,牛 准
上一篇：236期: 风雪无阻【经典九肖】
"""


def _source() -> Source:
    return Source(
        name="流星恋月",
        url=URL,
        position=Position.TOP,
        section_marker=MARKER,
        fetcher="static_page",
        parser="direct_nine",
    )


def _document() -> Document:
    return Document(
        label="browser-dom",
        url=URL,
        text=PAGE_TEXT,
        method=DocumentMethod.STATIC_PAGE,
    )


def test_liuxinglianyue_is_registered_exactly_once() -> None:
    repository = SourceRepository(
        PROJECT_ROOT / "config" / "sources.json",
        PROJECT_ROOT / "config" / "archived_sources.json",
    )
    matches = tuple(
        source for source in repository.load_active() if source.name == "流星恋月"
    )
    assert matches == (_source(),)


def test_liuxinglianyue_top_issue_236_and_boundaries() -> None:
    source = _source()
    records = DirectNineParser().parse(source, (_document(),), (236,))
    verified = Validator().validate(source, records, (236,))
    record = verified.history.records[0]
    assert record.zodiac_text == "鸡猪羊鼠猴虎马狗龙"
    assert record.evidence.actual_anchor_line == "236期: 流星恋月【九肖中特】"
    assert record.evidence.direction_window == (236, 235, 234)

    with pytest.raises(ValidationError) as missing:
        Validator().validate(source, records, (237,))
    assert missing.value.failure.code is ErrorCode.ISSUE_MISSING

    bottom = replace(source, position=Position.BOTTOM)
    bottom_records = DirectNineParser().parse(bottom, (_document(),), (236,))
    with pytest.raises(ValidationError) as wrong_direction:
        Validator().validate(bottom, bottom_records, (236,))
    assert wrong_direction.value.failure.code is ErrorCode.ISSUE_MISSING


def test_liuxinglianyue_wrong_anchor_is_rejected() -> None:
    wrong = replace(_source(), section_marker="流星恋月【错误栏目】")
    with pytest.raises(ParseError) as captured:
        DirectNineParser().parse(wrong, (_document(),), (236,))
    assert captured.value.failure.code is ErrorCode.ANCHOR_MISSING
