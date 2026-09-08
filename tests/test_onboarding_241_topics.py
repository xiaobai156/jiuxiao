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


CASES = (
    (
        Source(
            name="金钱九肖",
            url="https://wnorzspl.cp7ea-w9xfp-rmksqw.work:17477/topic/621663.html",
            position=Position.TOP,
            section_marker="金钱九肖",
            fetcher="browser_page",
            parser="direct_nine",
        ),
        "241期:王者九点网【金钱九肖】已公开",
        "241期【金钱九肖】【羊鼠鸡蛇马猴牛狗兔】开：0000准",
        "羊鼠鸡蛇马猴牛狗兔",
    ),
    (
        Source(
            name="忧心忡忡",
            url="https://flirclg.d9n5a-2i9au-ezvqgb.xyz:16677/topic/451881.html",
            position=Position.TOP,
            section_marker="忧心忡忡",
            fetcher="browser_page",
            parser="topic_cyclic_nine",
        ),
        "作者:忧心忡忡",
        "241期：【九肖中特】猪狗蛇牛兔鼠马鸡羊：0000准",
        "猪狗蛇牛兔鼠马鸡羊",
    ),
    (
        Source(
            name="紫月幽怜",
            url="https://labijgfu.v0th1-soldo-jlquuk.work:17466/topic/442916.html",
            position=Position.TOP,
            section_marker="紫月幽怜",
            fetcher="browser_page",
            parser="topic_cyclic_nine",
        ),
        "作者:紫月幽怜",
        "241期：【九肖中特】马鸡兔龙蛇猪狗鼠牛 开000准",
        "马鸡兔龙蛇猪狗鼠牛",
    ),
    (
        Source(
            name="颂德歌功",
            url="https://ojiptsou.9n42n-7ntih-uqgxsi.work:17477/topic/256074.html",
            position=Position.TOP,
            section_marker="颂德歌功",
            fetcher="browser_page",
            parser="direct_nine",
        ),
        "241期:颂德歌功『九肖中特』155573a.com",
        "241期九肖中特【猴蛇狗兔鸡羊龙马虎】开0000准",
        "猴蛇狗兔鸡羊龙马虎",
    ),
    (
        Source(
            name="正弦定理",
            url="https://rambbaoz.ehhv1-wetxh-webjef.work:17477/topic/473521.html",
            position=Position.TOP,
            section_marker="正弦定理",
            fetcher="browser_page",
            parser="direct_nine",
        ),
        "作者:正弦定理",
        "241期《必中九肖》（狗兔马牛猪鸡蛇羊鼠）开:0000准",
        "狗兔马牛猪鸡蛇羊鼠",
    ),
)


@pytest.mark.parametrize(
    ("source", "anchor", "raw", "expected"),
    CASES,
)
def test_approved_241_topics_keep_top_boundary(
    source: Source,
    anchor: str,
    raw: str,
    expected: str,
) -> None:
    document = Document(
        label="browser-dom",
        url=source.url,
        text="\n".join((anchor, raw, raw.replace("241期", "240期"), raw.replace("241期", "239期"))),
        method=DocumentMethod.BROWSER_DOM,
    )
    parser = build_parser_registry().resolve(source.parser)
    parsed = parser.parse(source, (document,), (241,))
    record = Validator().validate(source, parsed, (241,)).history.records[0]

    assert record.zodiac_text == expected
    assert record.evidence.actual_anchor_line == anchor
    assert record.evidence.direction_window == (241, 240, 239)

    with pytest.raises(ParseError) as wrong_anchor:
        parser.parse(
            replace(source, section_marker=f"{source.name}错误"),
            (document,),
            (241,),
        )
    assert wrong_anchor.value.failure.code is ErrorCode.ANCHOR_MISSING


def test_formal_241_topics_are_registered_exactly_once() -> None:
    active = SourceRepository(
        PROJECT_ROOT / "config" / "sources.json",
        PROJECT_ROOT / "config" / "archived_sources.json",
    ).load_active()

    for source, _anchor, _raw, _expected in CASES:
        assert tuple(item for item in active if item.name == source.name) == (
            source,
        )
