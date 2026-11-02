"""雷霆大怒专属解析器（leitingdanu）回归测试。

页面把「期号 + 栏目」与「九肖」拆成相邻两行：
    296期：枯木逢春九肖
    【牛猪马虎鸡鼠猴狗羊】开？00准
锚点「雷霆大怒」只出现在页首标题行（`296期雷霆大怒【枯木逢春九肖】准`），
通用解析拿不到稳定的「期号行 + 九肖行」配对，故用显式成对正则逐期截取。
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
        name="雷霆大怒",
        url="https://example.test/topic/462501.html",
        position=Position.TOP,
        section_marker="",
        fetcher="browser_page",
        parser="leitingdanu",
        data_marker="九肖",
    )


def page(*pairs: tuple[str, str]) -> Document:
    lines = [
        "返回首页",
        "落霞雪落【16码中特】←已公开",
        "296期雷霆大怒【枯木逢春九肖】准",
        "提高速度,减少浏览流量,不保留大量往期记录!",
    ]
    for issue_line, zodiac_line in pairs:
        lines.append(issue_line)
        lines.append(zodiac_line)
    return Document(
        label="browser-dom",
        url="https://example.test/topic/462501.html",
        text="\n".join(lines),
        method=DocumentMethod.BROWSER_DOM,
    )


def parse(document: Document, issues: tuple[int, ...] = (296, 295, 294)):
    return build_parser_registry().resolve("leitingdanu").parse(
        source(), (document,), issues
    )


def test_parser_is_registered() -> None:
    parser = build_parser_registry().resolve("leitingdanu")
    assert parser.parser_id == "leitingdanu"


def test_pairs_issue_line_with_next_zodiac_line() -> None:
    document = page(
        ("296期：枯木逢春九肖", "【牛猪马虎鸡鼠猴狗羊】开？00准"),
        ("295期：枯木逢春九肖", "【牛猴鸡兔鼠虎狗猪龙】开马25错"),
        ("294期：枯木逢春九肖", "【牛羊马鼠龙猪虎蛇兔】开兔28准"),
    )
    result = parse(document)

    values = {record.issue: record.zodiac_text for record in result.records}
    assert values[296] == "牛猪马虎鸡鼠猴狗羊"
    assert values[295] == "牛猴鸡兔鼠虎狗猪龙"
    assert values[294] == "牛羊马鼠龙猪虎蛇兔"
    for text in values.values():
        assert len(text) == 9
        assert len(set(text)) == 9


def test_draw_result_zodiac_is_not_merged() -> None:
    """九肖行尾部的开奖结果生肖（本例「马」）不得并入。"""
    document = page(("295期：枯木逢春九肖", "【牛猴鸡兔鼠虎狗猪龙】开马25错"))
    result = parse(document, (295,))

    record = next(r for r in result.records if r.issue == 295)
    assert record.zodiac_text == "牛猴鸡兔鼠虎狗猪龙"
    assert len(record.zodiacs) == 9


def test_issue_line_without_following_zodiac_line_is_skipped() -> None:
    """期号行后面不是九肖行（例如页脚说明）时不得凭空生成记录。"""
    document = page(("296期：枯木逢春九肖", "【牛猪马虎鸡鼠猴狗羊】开？00准"))
    document = Document(
        label=document.label,
        url=document.url,
        text=document.text + "\n297期：枯木逢春九肖\n版权所有 免责声明",
        method=document.method,
    )
    result = parse(document, (296, 297))

    assert [r.issue for r in result.records] == [296]


def test_duplicate_zodiacs_in_line_are_rejected() -> None:
    """九个位置里出现重复生肖时必须丢弃（不是合法九肖）。"""
    document = page(("296期：枯木逢春九肖", "【牛牛马虎鸡鼠猴狗羊】开？00准"))
    result = parse(document, (296,))

    assert [r.issue for r in result.records] == []
