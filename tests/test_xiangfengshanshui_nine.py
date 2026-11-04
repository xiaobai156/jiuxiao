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
from v2.parsers.factory import build_parser_registry  # noqa: E402
from v2.parsers.registry import ParseError  # noqa: E402
from v2.validator import Validator  # noqa: E402


SOURCE = Source(
    name="翔凤山水",
    url="https://spjpffl.99xhg-228d5-syyqpo.work:17466/topic/670575.html",
    position=Position.TOP,
    section_marker="翔凤山水",
    fetcher="browser_page",
    parser="direct_nine",
)

ANCHOR = "308期:翔凤山水【九肖中特】←797938e.com"
RAW_308 = "308期九肖中特【羊蛇兔鼠虎鸡马牛猴】开0000准"
RAW_307 = "307期九肖中特【马牛虎猪龙蛇鸡猴兔】开牛42准"
RAW_306 = "306期九肖中特【羊猪虎龙兔猴鼠牛马】开龙15准"


def _document(anchor: str = ANCHOR) -> Document:
    return Document(
        label="browser-dom",
        url=SOURCE.url,
        text="\n".join((anchor, RAW_308, RAW_307, RAW_306)),
        method=DocumentMethod.BROWSER_DOM,
    )


def test_308_top_site_takes_newest_record_in_window() -> None:
    parser = build_parser_registry().resolve(SOURCE.parser)
    parsed = parser.parse(SOURCE, (_document(),), (308,))
    record = Validator().validate(SOURCE, parsed, (308,)).history.records[0]

    assert record.zodiac_text == "羊蛇兔鼠虎鸡马牛猴"
    assert record.evidence.actual_anchor_line == ANCHOR
    assert record.evidence.direction_window == (308, 307, 306)
    assert record.evidence.raw_issue_line == RAW_308


def test_308_top_site_adjacent_issues_share_window() -> None:
    parser = build_parser_registry().resolve(SOURCE.parser)
    parsed = parser.parse(SOURCE, (_document(),), (307,))
    record = Validator().validate(SOURCE, parsed, (307,)).history.records[0]

    assert record.zodiac_text == "马牛虎猪龙蛇鸡猴兔"
    assert record.evidence.direction_window == (308, 307, 306)


def test_308_top_site_missing_issue_stays_failed() -> None:
    parser = build_parser_registry().resolve(SOURCE.parser)
    parsed = parser.parse(SOURCE, (_document(),), (309,))

    with pytest.raises(Exception) as missing:
        Validator().validate(SOURCE, parsed, (309,))
    assert "ISSUE_MISSING" in str(missing.value)


def test_wrong_section_marker_is_anchor_missing() -> None:
    parser = build_parser_registry().resolve(SOURCE.parser)

    with pytest.raises(ParseError) as wrong_anchor:
        parser.parse(
            replace(SOURCE, section_marker=f"{SOURCE.name}错误"),
            (_document(),),
            (308,),
        )
    assert wrong_anchor.value.failure.code is ErrorCode.ANCHOR_MISSING


def test_formal_308_site_is_registered_exactly_once() -> None:
    active = SourceRepository(
        PROJECT_ROOT / "config" / "sources.json",
        PROJECT_ROOT / "config" / "archived_sources.json",
    ).load_active()

    assert tuple(item for item in active if item.name == "翔凤山水") == (SOURCE,)
