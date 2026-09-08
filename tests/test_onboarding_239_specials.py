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
from v2.validator import Validator  # noqa: E402


CASES = (
    (
        "四方来贺",
        "1425",
        "原创九肖",
        "虎兔羊龙猪蛇马猴鸡",
        ((239, "虎兔羊龙猪蛇马猴鸡"), (238, "猪龙兔蛇羊牛鸡马虎"), (237, "蛇猴鼠鸡牛猪兔羊龙")),
    ),
    (
        "欣欣宝贝",
        "1418",
        "期期九肖",
        "猪兔狗鼠虎羊龙猴蛇",
        ((239, "猪兔狗鼠虎羊龙猴蛇"), (238, "鸡蛇虎猪马牛羊鼠猴"), (237, "猪鸡鼠马羊牛猴兔虎")),
    ),
    (
        "光明前途",
        "1428",
        "权威九肖",
        "牛鸡狗羊猪鼠兔龙马",
        ((239, "牛鸡狗羊猪鼠兔龙马"), (238, "鸡羊蛇鼠狗马虎龙牛"), (236, "马虎猪鸡羊猴牛兔蛇")),
    ),
    (
        "灯红酒绿",
        "1432",
        "九肖中特",
        "羊狗猪兔马牛鸡蛇鼠",
        ((239, "羊狗猪兔马牛鸡蛇鼠"), (237, "蛇猪马兔虎猴狗牛羊"), (236, "蛇兔龙虎羊猴鼠猪狗")),
    ),
    (
        "海里捞金",
        "1404",
        "经典九肖",
        "猴狗虎牛鸡鼠龙猪蛇",
        ((239, "猴狗虎牛鸡鼠龙猪蛇"), (238, "牛蛇猪兔龙羊狗虎鼠"), (237, "狗兔龙鸡马牛虎猴羊")),
    ),
    (
        "风雪无阻",
        "1403",
        "经典九肖",
        "猪蛇狗牛龙羊猴鼠兔",
        ((239, "猪蛇狗牛龙羊猴鼠兔"), (238, "兔狗鼠猪龙蛇猴虎鸡"), (235, "龙蛇羊兔虎猴鼠猪马")),
    ),
    (
        "繁花人生",
        "1406",
        "无敌九肖",
        "虎马鸡鼠猴牛蛇狗兔",
        ((239, "虎马鸡鼠猴牛蛇狗兔"), (238, "龙鼠蛇牛虎猪羊狗鸡"), (236, "猴鼠马龙狗猪兔蛇鸡")),
    ),
)


def source(name: str, article_id: str, column: str) -> Source:
    return Source(
        name=name,
        url=(
            "https://4.48kk49.com:1888/Article/ar_content/"
            f"id/{article_id}/tid/81.html"
        ),
        position=Position.TOP,
        section_marker=f"{name}【{column}】",
        fetcher="static_page",
        parser="direct_nine",
    )


@pytest.mark.parametrize(
    ("name", "article_id", "column", "expected", "rows"), CASES
)
def test_approved_sources_keep_239_top_boundaries(
    name: str,
    article_id: str,
    column: str,
    expected: str,
    rows: tuple[tuple[int, str], ...],
) -> None:
    candidate = source(name, article_id, column)
    marker = candidate.section_marker
    page = "\n".join(
        (
            f"239期: {marker}",
            *(f"{issue}期 {name}九肖 :【{value}】 开 ?? 准" for issue, value in rows),
            "上一篇：239期: 其他目录【九肖】",
        )
    )
    document = Document(
        label="static-page",
        url=candidate.url,
        text=page,
        method=DocumentMethod.STATIC_PAGE,
    )
    parsed = DirectNineParser().parse(candidate, (document,), (239,))
    record = Validator().validate(candidate, parsed, (239,)).history.records[0]

    assert record.zodiac_text == expected
    assert record.evidence.actual_anchor_line == f"239期: {marker}"
    assert record.evidence.direction_window == tuple(issue for issue, _ in rows)

    with pytest.raises(ParseError) as wrong_anchor:
        DirectNineParser().parse(
            replace(candidate, section_marker=f"{name}【错误栏目】"),
            (document,),
            (239,),
        )
    assert wrong_anchor.value.failure.code is ErrorCode.ANCHOR_MISSING


def test_formal_sources_are_registered_exactly_once() -> None:
    active = SourceRepository(
        PROJECT_ROOT / "config" / "sources.json",
        PROJECT_ROOT / "config" / "archived_sources.json",
    ).load_active()
    for name, article_id, column, _expected, _rows in CASES:
        assert tuple(item for item in active if item.name == name) == (
            source(name, article_id, column),
        )
