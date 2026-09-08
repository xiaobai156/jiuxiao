from __future__ import annotations

import importlib.util
import sys
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


NAME = "喜新厌旧"
URL = "https://qarppl.154bo-trld9-qppors.xyz:16677/topic/622194.html"
EXPECTED = "羊牛鸡鼠兔蛇马狗龙"
PAGE = """228期： 神庙网 【财神九肖】 已公开
喜新厌旧 发表于 06月27日 14:35:23
228期: 财神九肖《羊牛鸡鼠兔蛇马狗龙》开0000准
227期: 财神九肖《狗猪虎鼠鸡猴羊马兔》开兔16准
226期: 财神九肖《蛇狗马兔龙猪牛羊鼠》开虎17错
225期: 财神九肖《龙牛虎兔马蛇羊猴狗》开马01准
其他栏目
"""


def source(
    *,
    position: Position = Position.TOP,
    name: str = NAME,
) -> Source:
    return Source(
        name=name,
        url=URL,
        position=position,
        section_marker="",
        fetcher="browser_page",
        parser="direct_nine",
    )


def validate(candidate: Source, issue: int, text: str = PAGE):
    document = Document(
        label="browser-dom",
        url=URL,
        text=text,
        method=DocumentMethod.BROWSER_DOM,
    )
    parsed = DirectNineParser().parse(candidate, (document,), (issue,))
    return Validator().validate(candidate, parsed, (issue,))


def test_top_direction_selects_228_from_first_three_issue_window() -> None:
    record = validate(source(), 228).history.records[0]

    assert record.zodiac_text == EXPECTED
    assert record.evidence.direction_window == (228, 227, 226)
    assert record.evidence.actual_anchor_line.startswith(f"{NAME} 发表于")


def test_bottom_direction_cannot_take_228_outside_bottom_window() -> None:
    with pytest.raises(ValidationError) as captured:
        validate(source(position=Position.BOTTOM), 228)

    assert captured.value.failure.code is ErrorCode.ISSUE_MISSING


def test_top_direction_keeps_adjacent_227_in_same_block() -> None:
    record = validate(source(), 227).history.records[0]

    assert record.zodiac_text == "狗猪虎鼠鸡猴羊马兔"


def test_nonexistent_229_fails() -> None:
    with pytest.raises(ValidationError) as captured:
        validate(source(), 229)

    assert captured.value.failure.code is ErrorCode.ISSUE_MISSING


def test_wrong_author_anchor_fails() -> None:
    with pytest.raises(ParseError) as captured:
        validate(source(name="不存在作者"), 228)

    assert captured.value.failure.code is ErrorCode.ANCHOR_MISSING


def test_duplicate_zodiac_payload_is_invalid() -> None:
    malformed = PAGE.replace(EXPECTED, "羊牛鸡鼠兔蛇马狗狗")

    with pytest.raises(ValidationError) as captured:
        validate(source(), 228, malformed)

    assert captured.value.failure.code is ErrorCode.INVALID_ZODIAC_COUNT


def test_same_block_same_issue_conflict_fails() -> None:
    conflicting = PAGE.replace(
        "227期:",
        "228期: 财神九肖《鼠牛虎兔龙蛇马羊猴》开0000准\n227期:",
    )

    with pytest.raises(ValidationError) as captured:
        validate(source(), 228, conflicting)

    assert captured.value.failure.code is ErrorCode.CANDIDATE_CONFLICT


def test_formal_config_uses_top_direction() -> None:
    active = SourceRepository(
        PROJECT_ROOT / "config" / "sources.json",
        PROJECT_ROOT / "config" / "archived_sources.json",
    ).load_active()
    matches = tuple(item for item in active if item.name == NAME)

    assert len(matches) == 1
    assert matches[0].url == URL
    assert matches[0].position is Position.TOP
