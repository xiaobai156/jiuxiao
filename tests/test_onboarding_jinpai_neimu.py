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


NAME = "金牌内幕"
URL = "https://4.48kk49.com:1888/Article/ar_content/id/1424/tid/81.html"
MARKER = "金牌内幕【独家九肖】"
EXPECTED = "兔猪蛇虎羊猴龙鸡狗"
PAGE = f"""239期: {MARKER}
温馨提示:为了提高网速，部分连错期数记录已删除
239期 金牌内幕九肖 :【蛇鸡虎牛猴鼠龙羊马】 开 ?? 准
238期 金牌内幕九肖 :【{EXPECTED}】 开 17,虎 准
236期 金牌内幕九肖 :【猴龙兔蛇马狗羊牛鸡】 开 11,猴 准
上一篇：239期: 四方来贺【原创九肖】
下一篇：239期: 纸上谈兵【九肖来特】
"""


def source(*, marker: str = MARKER) -> Source:
    return Source(
        name=NAME,
        url=URL,
        position=Position.TOP,
        section_marker=marker,
        fetcher="static_page",
        parser="direct_nine",
    )


def parse(candidate: Source):
    document = Document(
        label="static-page",
        url=URL,
        text=PAGE,
        method=DocumentMethod.STATIC_PAGE,
    )
    return DirectNineParser().parse(candidate, (document,), (238,))


def test_approved_short_history_selects_top_238() -> None:
    candidate = source()
    records = parse(candidate)
    verified = Validator().validate(candidate, records, (238,))
    record = verified.history.records[0]

    assert record.zodiac_text == EXPECTED
    assert record.evidence.actual_anchor_line == f"239期: {MARKER}"
    assert record.evidence.direction_window == (239, 238, 236)

    with pytest.raises(ValidationError) as missing:
        Validator().validate(candidate, records, (237,))
    assert missing.value.failure.code is ErrorCode.ISSUE_MISSING


def test_wrong_section_marker_is_rejected() -> None:
    with pytest.raises(ParseError) as captured:
        parse(replace(source(), section_marker="金牌内幕【错误栏目】"))
    assert captured.value.failure.code is ErrorCode.ANCHOR_MISSING


def test_formal_source_is_registered_exactly_once() -> None:
    repository = SourceRepository(
        PROJECT_ROOT / "config" / "sources.json",
        PROJECT_ROOT / "config" / "archived_sources.json",
    )
    assert tuple(
        item for item in repository.load_active() if item.name == NAME
    ) == (source(),)
