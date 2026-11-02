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
    name="路叟之忧",
    url="https://fyzxhjpo.b4t3z-aukfj-nqkmvv.work:17455/topic/464091.html",
    position=Position.TOP,
    section_marker="路叟之忧",
    fetcher="browser_page",
    parser="direct_nine",
)

ANCHOR = "作者:路叟之忧"
RAW_306 = "306期:九肖中特- 马兔猴羊牛龙鸡鼠猪 开:00准"
RAW_305 = "305期:九肖中特- 虎兔马猴猪狗牛鼠蛇 开:蛇26准"
RAW_304 = "304期:九肖中特- 马鸡牛猴鼠龙羊虎兔 开:狗21错"


def _document(anchor: str = ANCHOR) -> Document:
    return Document(
        label="browser-dom",
        url=SOURCE.url,
        text="\n".join(
            (
                "306期:彩霸王【九肖中特】路叟之忧！",
                anchor,
                RAW_306,
                RAW_305,
                RAW_304,
            )
        ),
        method=DocumentMethod.BROWSER_DOM,
    )


def test_306_top_site_takes_newest_record_in_window() -> None:
    parser = build_parser_registry().resolve(SOURCE.parser)
    parsed = parser.parse(SOURCE, (_document(),), (306,))
    record = Validator().validate(SOURCE, parsed, (306,)).history.records[0]

    assert record.zodiac_text == "马兔猴羊牛龙鸡鼠猪"
    assert record.evidence.actual_anchor_line == ANCHOR
    assert record.evidence.direction_window == (306, 305, 304)
    assert record.evidence.raw_issue_line == RAW_306


def test_306_top_site_adjacent_issues_share_window() -> None:
    parser = build_parser_registry().resolve(SOURCE.parser)
    parsed = parser.parse(SOURCE, (_document(),), (305,))
    record = Validator().validate(SOURCE, parsed, (305,)).history.records[0]

    assert record.zodiac_text == "虎兔马猴猪狗牛鼠蛇"
    assert record.evidence.direction_window == (306, 305, 304)


def test_306_top_site_missing_issue_stays_failed() -> None:
    parser = build_parser_registry().resolve(SOURCE.parser)
    parsed = parser.parse(SOURCE, (_document(),), (307,))

    with pytest.raises(Exception) as missing:
        Validator().validate(SOURCE, parsed, (307,))
    assert "ISSUE_MISSING" in str(missing.value)


def test_wrong_section_marker_is_anchor_missing() -> None:
    parser = build_parser_registry().resolve(SOURCE.parser)

    with pytest.raises(ParseError) as wrong_anchor:
        parser.parse(
            replace(SOURCE, section_marker=f"{SOURCE.name}错误"),
            (_document(),),
            (306,),
        )
    assert wrong_anchor.value.failure.code is ErrorCode.ANCHOR_MISSING


def test_formal_306_site_is_registered_exactly_once() -> None:
    active = SourceRepository(
        PROJECT_ROOT / "config" / "sources.json",
        PROJECT_ROOT / "config" / "archived_sources.json",
    ).load_active()

    assert tuple(item for item in active if item.name == "路叟之忧") == (SOURCE,)
