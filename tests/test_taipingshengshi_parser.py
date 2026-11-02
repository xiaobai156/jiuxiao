"""太平盛世专属解析器（taipingshengshi）回归测试。

页面把「期号 + 栏目 + 开奖结果」与「九肖」拆成相隔一个空行的两行，
九肖用【】/《》包裹：
    298期九肖中特开？00准
    （空行）
    【狗猪虎羊鼠牛兔龙鸡】
页首标题行（`298期:49高手精选【九肖中特】太平盛世`）与作者行各命中一次锚点，
通用解析会把区块切碎并丢期，故用显式配对逐期截取。
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
        name="太平盛世",
        url="https://example.test/topic/792779.html",
        position=Position.TOP,
        section_marker="太平盛世",
        fetcher="browser_page",
        parser="taipingshengshi",
        data_marker="九肖中特",
    )


def page(*pairs: tuple[str, str]) -> Document:
    lines = [
        "查看帖子",
        "<",
        "",
        "298期:49高手精选【九肖中特】太平盛世",
        "",
        "作者:太平盛世",
        "",
    ]
    for issue_line, zodiac_line in pairs:
        lines.append(issue_line)
        lines.append("")
        lines.append(zodiac_line)
        lines.append("")
    return Document(
        label="browser-dom",
        url="https://example.test/topic/792779.html",
        text="\n".join(lines),
        method=DocumentMethod.BROWSER_DOM,
    )


def parse(document: Document, issues: tuple[int, ...] = (298, 297, 296)):
    return build_parser_registry().resolve("taipingshengshi").parse(
        source(), (document,), issues
    )


def test_parser_is_registered() -> None:
    parser = build_parser_registry().resolve("taipingshengshi")
    assert parser.parser_id == "taipingshengshi"


def test_pairs_issue_line_with_bracketed_zodiac_after_blank_line() -> None:
    document = page(
        ("298期九肖中特开？00准", "【狗猪虎羊鼠牛兔龙鸡】"),
        ("297期九肖中特开马13准", "【鼠蛇牛龙鸡狗马羊猴】"),
        ("296期九肖中特开猴23准", "【猪鼠龙狗猴蛇牛鸡马】"),
    )
    result = parse(document)

    values = {record.issue: record.zodiac_text for record in result.records}
    assert values[298] == "狗猪虎羊鼠牛兔龙鸡"
    assert values[297] == "鼠蛇牛龙鸡狗马羊猴"
    assert values[296] == "猪鼠龙狗猴蛇牛鸡马"
    for text in values.values():
        assert len(text) == 9
        assert len(set(text)) == 9


def test_title_line_is_not_mistaken_for_a_record() -> None:
    """页首标题行含「九肖中特」但下一非空行不是九肖，不得生成 298 记录。"""
    document = page(("297期九肖中特开马13准", "【鼠蛇牛龙鸡狗马羊猴】"))
    result = parse(document, (298, 297))

    assert [r.issue for r in result.records] == [297]


def test_duplicate_zodiacs_are_rejected() -> None:
    document = page(("298期九肖中特开？00准", "【狗狗虎羊鼠牛兔龙鸡】"))
    result = parse(document, (298,))

    assert [r.issue for r in result.records] == []


def test_issue_line_without_zodiac_line_is_skipped() -> None:
    document = page(("298期九肖中特开？00准", "【狗猪虎羊鼠牛兔龙鸡】"))
    document = Document(
        label=document.label,
        url=document.url,
        text=document.text + "\n297期九肖中特开00准\n版权所有 免责声明",
        method=document.method,
    )
    result = parse(document, (298, 297))

    assert [r.issue for r in result.records] == [298]
