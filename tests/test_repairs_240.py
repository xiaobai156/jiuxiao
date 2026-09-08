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
from v2.parsers.custom.topic_cyclic import TopicCyclicParser  # noqa: E402
from v2.parsers.direct_nine import DirectNineParser  # noqa: E402
from v2.parsers.registry import ParseError  # noqa: E402
from v2.validator import ValidationError, Validator  # noqa: E402


DUMMY = "鼠牛虎兔龙蛇马羊猴"
CYCLIC_CASES = (
    (
        Source(
            "恍如隔世",
            "https://gxixcfq.4hxms-k65ek-jsvqzm.xyz:16677/topic/276888.html",
            Position.TOP,
            "",
            "browser_page",
            "topic_cyclic_nine",
        ),
        "虎狗猴龙猪鼠羊鸡蛇",
        "兔鼠猪蛇鸡羊马虎猴",
        "鸡蛇羊猪马虎龙狗兔",
    ),
    (
        Source(
            "百思不解",
            "https://ssytmks.kcyub-abvtn-uvalbe.xyz:16677/topic/732213.html",
            Position.BOTTOM,
            "百思不解",
            "browser_page",
            "topic_cyclic_nine",
        ),
        "龙马猴鼠兔羊狗蛇牛",
        "兔马龙蛇猴鼠羊鸡牛",
        "兔蛇猪龙虎马牛羊鼠",
    ),
)


def cyclic_document(
    source: Source,
    current_240: str,
    current_239: str,
    old_240: str,
) -> Document:
    if source.position is Position.TOP:
        lines = (
            f"{source.name} 发表于 08月28日 12:20:49",
            f"240期【九肖中特】▶{current_240}◀开:0000准",
            f"239期【九肖中特】▶{current_239}◀开:虎05准",
            *(f"{issue}期【九肖中特】▶{DUMMY}◀开:00准" for issue in range(346, 366)),
            *(f"{issue:03d}期【九肖中特】▶{DUMMY}◀开:00准" for issue in range(1, 21)),
            f"240期【九肖中特】▶{old_240}◀开:虎28准",
        )
    else:
        lines = (
            f"作者:{source.name}",
            f"240期:【九肖中特】〖{old_240}〗开:虎28准",
            *(f"{issue}期:【九肖中特】〖{DUMMY}〗开:00准" for issue in range(346, 366)),
            *(f"{issue:03d}期:【九肖中特】〖{DUMMY}〗开:00准" for issue in range(1, 21)),
            f"239期:【九肖中特】〖{current_239}〗开:虎05错",
            f"240期:【九肖中特】〖{current_240}〗开:0000准",
        )
    return Document(
        "browser-dom",
        source.url,
        "\n".join(lines),
        DocumentMethod.BROWSER_DOM,
    )


@pytest.mark.parametrize(
    ("source", "current_240", "current_239", "old_240"), CYCLIC_CASES
)
def test_cyclic_repairs_select_the_configured_current_run(
    source: Source,
    current_240: str,
    current_239: str,
    old_240: str,
) -> None:
    document = cyclic_document(source, current_240, current_239, old_240)
    parsed = TopicCyclicParser().parse(source, (document,), (240,))

    record = Validator().validate(source, parsed, (240,)).history.records[0]
    assert record.zodiac_text == current_240
    assert record.evidence.direction_window[:2] == (240, 239)

    with pytest.raises(ValidationError) as missing:
        Validator().validate(source, parsed, (999,))
    assert missing.value.failure.code is ErrorCode.ISSUE_MISSING

    with pytest.raises(ParseError) as wrong_anchor:
        TopicCyclicParser().parse(
            replace(source, section_marker=f"{source.name}【错误栏目】"),
            (document,),
            (240,),
        )
    assert wrong_anchor.value.failure.code is ErrorCode.ANCHOR_MISSING


def test_relianyinkuang_uses_top_240_window() -> None:
    source = Source(
        "热泪盈眶",
        "https://uicphb.v8vzj-9qywy-tbwdte.xyz:16677/topic/622385.html",
        Position.TOP,
        "",
        "browser_page",
        "direct_nine",
    )
    document = Document(
        "browser-dom",
        source.url,
        "\n".join(
            (
                "热泪盈眶 发表于 01月15日 21:08:35",
                "240期 ￥九肖中特￥虎兔猴马龙牛羊鸡蛇￥开：0000准",
                "239期 ￥九肖中特￥鸡虎龙兔鼠牛蛇猪狗￥开：虎05准",
                "238期 ￥九肖中特￥蛇兔虎牛鼠猪马龙羊￥开：虎17准",
                "237期 ￥九肖中特￥马兔蛇鸡猴羊狗龙虎￥开：羊12准",
                "236期 ￥九肖中特￥虎牛猪狗龙兔鸡鼠猴￥开：猴11准",
            )
        ),
        DocumentMethod.BROWSER_DOM,
    )
    parsed = DirectNineParser().parse(source, (document,), (240,))

    record = Validator().validate(source, parsed, (240,)).history.records[0]
    assert record.zodiac_text == "虎兔猴马龙牛羊鸡蛇"
    assert record.evidence.direction_window == (240, 239, 238)


def test_formal_240_repairs_are_registered() -> None:
    active = SourceRepository(
        PROJECT_ROOT / "config" / "sources.json",
        PROJECT_ROOT / "config" / "archived_sources.json",
    ).load_active()
    sources = {source.name: source for source in active}

    assert sources["恍如隔世"].parser == "topic_cyclic_nine"
    assert sources["百思不解"].parser == "topic_cyclic_nine"
    assert sources["热泪盈眶"].position is Position.TOP
