"""大智若愚专属解析器（dazhiruoyu）回归测试。

页面格式：`NNN期：【九肖中特】<九肖>：<开奖结果>准/错`
九肖没有括号包裹，直接跟 9 个生肖，随后「：」接开奖结果。

通用 safe_zodiac_candidates 会把开奖结果里的生肖并入（例如
`294期：【九肖中特】鼠鸡羊龙猴兔狗虎马：兔28准` 会取到 10 个，
尾部「兔」来自开奖结果），导致 INVALID_ZODIAC_COUNT。
本解析器用 `【九肖中特】` + 恰好 9 个生肖 的边界截取，不碰通用解析器。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if "v2" not in sys.modules:
    specification = importlib.util.spec_from_file_location(
        "v2",
        PROJECT_ROOT / "__init__.py",
        submodule_search_locations=[str(PROJECT_ROOT)],
    )
    assert specification is not None and specification.loader is not None
    package = importlib.util.module_from_spec(specification)
    sys.modules["v2"] = package
    specification.loader.exec_module(package)

from v2.domain.models import (  # noqa: E402
    Document,
    DocumentMethod,
    Position,
    Source,
)
from v2.parsers.factory import build_parser_registry  # noqa: E402


def source() -> Source:
    return Source(
        name="大智若愚",
        url="https://example.test/topic/481117.html",
        position=Position.BOTTOM,
        section_marker="大智若愚",
        fetcher="browser_page",
        parser="dazhiruoyu",
        data_marker="九肖中特",
    )


def page(*lines: str) -> Document:
    text = "\n".join(
        (
            "赚钱贴 295期【九肖中特】",
            "大智若愚 发表于 10月22日 10:19:58",
            *lines,
        )
    )
    return Document(
        label="browser-dom",
        url="https://example.test/topic/481117.html",
        text=text,
        method=DocumentMethod.BROWSER_DOM,
    )


def parse(document: Document, issues: tuple[int, ...] = (295, 294, 293)):
    return build_parser_registry().resolve("dazhiruoyu").parse(
        source(), (document,), issues
    )


def test_parser_is_registered() -> None:
    parser = build_parser_registry().resolve("dazhiruoyu")
    assert parser.parser_id == "dazhiruoyu"


def test_trailing_draw_zodiac_is_not_merged() -> None:
    """开奖结果里的生肖不得并入九肖（旧行为会取到 10 个）。"""
    document = page(
        "295期：【九肖中特】马猴鸡猪蛇虎兔鼠龙：？00准",
        "294期：【九肖中特】鼠鸡羊龙猴兔狗虎马：兔28准",
        "293期：【九肖中特】狗羊虎马龙猪鼠鸡蛇：虎05准",
    )
    result = parse(document)

    values = {record.issue: record.zodiac_text for record in result.records}
    assert values[295] == "马猴鸡猪蛇虎兔鼠龙"
    assert values[294] == "鼠鸡羊龙猴兔狗虎马"
    assert values[293] == "狗羊虎马龙猪鼠鸡蛇"
    for text in values.values():
        assert len(text) == 9
        assert len(set(text)) == 9


def test_draw_result_zodiac_matching_pick_zodiac() -> None:
    """开奖生肖与九肖中某一字重复时，也必须只取 9 个。"""
    document = page("294期：【九肖中特】鼠鸡羊龙猴兔狗虎马：马44准")
    result = parse(document, (294,))

    record = next(r for r in result.records if r.issue == 294)
    assert record.zodiac_text == "鼠鸡羊龙猴兔狗虎马"
    assert len(record.zodiacs) == 9


def test_issue_without_colon_before_bracket_still_parses() -> None:
    """期号后不带冒号的写法同样要能解析。"""
    document = page("295期【九肖中特】马猴鸡猪蛇虎兔鼠龙：？00准")
    result = parse(document, (295,))

    assert [r.zodiac_text for r in result.records if r.issue == 295] == [
        "马猴鸡猪蛇虎兔鼠龙"
    ]


def test_other_columns_on_same_page_are_ignored() -> None:
    """同页其它栏目（六肖/五肖等）不得被当作九肖。"""
    document = page(
        "295期：【九肖中特】马猴鸡猪蛇虎兔鼠龙：？00准",
        "赚钱贴 295期【内幕五肖】",
        "赚钱贴 295期【美女六肖】",
    )
    result = parse(document, (295,))

    assert [r.issue for r in result.records] == [295]
    assert result.records[0].zodiac_text == "马猴鸡猪蛇虎兔鼠龙"
