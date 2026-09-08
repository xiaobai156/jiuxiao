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


NAME = "花开富贵"
URL = "https://4.48kk49.com:1888/Article/ar_content/id/1125/tid/77.html"
MARKER = "花开富贵㊣㊣九肖"
EXPECTED = "猴牛马龙鸡猪羊鼠蛇"
PAGE = f"""高手九肖
235期: 【{MARKER}】
温馨提示:为了提高网速，部分连错期数记录已删除
235期 花开富贵九肖 :【{EXPECTED}】 开 ?? 准
234期 花开富贵九肖 :【鼠牛猴狗兔龙猪虎羊】 开 39,龙 准
233期 花开富贵九肖 :【龙猴鸡牛蛇马鼠狗猪】 开 07,鼠 准
上一篇：235期: 【横行霸道㊣㊣九肖】
下一篇：235期: 【随遇而安㊣㊣九肖】
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


def parse(candidate: Source, issue: int):
    document = Document(
        label="browser-dom",
        url=URL,
        text=PAGE,
        method=DocumentMethod.STATIC_PAGE,
    )
    return DirectNineParser().parse(candidate, (document,), (issue,))


def test_top_selects_235_and_ignores_navigation_posts() -> None:
    candidate = source()
    records = parse(candidate, 235)

    verified = Validator().validate(candidate, records, (235,))
    record = verified.history.records[0]

    assert record.zodiac_text == EXPECTED
    assert record.evidence.direction_window == (235, 234, 233)
    assert record.evidence.actual_anchor_line == f"235期: 【{MARKER}】"


def test_nonexistent_236_fails() -> None:
    candidate = source()
    records = parse(candidate, 236)

    with pytest.raises(ValidationError) as captured:
        Validator().validate(candidate, records, (236,))

    assert captured.value.failure.code is ErrorCode.ISSUE_MISSING


def test_wrong_section_marker_fails() -> None:
    candidate = source(marker="不存在栏目㊣㊣九肖")

    with pytest.raises(ParseError) as captured:
        parse(candidate, 235)

    assert captured.value.failure.code is ErrorCode.ANCHOR_MISSING


def test_formal_source_is_registered_exactly_once() -> None:
    repository = SourceRepository(
        PROJECT_ROOT / "config" / "sources.json",
        PROJECT_ROOT / "config" / "archived_sources.json",
    )
    matches = tuple(item for item in repository.load_active() if item.name == NAME)

    assert len(matches) == 1
    candidate = matches[0]
    assert candidate.url == URL
    assert candidate.position is Position.TOP
    assert candidate.section_marker == MARKER
    assert candidate.fetcher == "static_page"
    assert candidate.parser == "direct_nine"
