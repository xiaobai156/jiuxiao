"""发家致富专属解析器（fajiazhifu）回归测试。

页面把「期号 + 栏目 + 开奖结果」与「九肖」拆成相邻两行，九肖没有括号：
    296期:【皇帝九肖】开:？00准
    马牛蛇狗龙虎猴鼠兔
页首标题行（`296期:49姜子牙【皇帝九肖】发家致富`）也以三位期号开头，
但其下一行是空行，不得误配。
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
        name="发家致富",
        url="https://example.test/topic/794290.html",
        position=Position.TOP,
        section_marker="发家致富",
        fetcher="browser_page",
        parser="fajiazhifu",
        data_marker="九肖",
    )


def page(*pairs: tuple[str, str]) -> Document:
    lines = [
        "查看帖子",
        "<",
        "",
        "296期:49姜子牙【皇帝九肖】发家致富",
        "",
        "作者:发家致富",
        "",
    ]
    for issue_line, zodiac_line in pairs:
        lines.append(issue_line)
        lines.append(zodiac_line)
        lines.append("")
    return Document(
        label="browser-dom",
        url="https://example.test/topic/794290.html",
        text="\n".join(lines),
        method=DocumentMethod.BROWSER_DOM,
    )


def parse(document: Document, issues: tuple[int, ...] = (296, 295, 294)):
    return build_parser_registry().resolve("fajiazhifu").parse(
        source(), (document,), issues
    )


def test_parser_is_registered() -> None:
    parser = build_parser_registry().resolve("fajiazhifu")
    assert parser.parser_id == "fajiazhifu"


def test_pairs_issue_line_with_next_plain_zodiac_line() -> None:
    document = page(
        ("296期:【皇帝九肖】开:？00准", "马牛蛇狗龙虎猴鼠兔"),
        ("295期:【皇帝九肖】开:马25准", "兔牛虎鸡猴猪马羊鼠"),
        ("294期:【皇帝九肖】开:兔28错", "马羊猴鼠猪龙狗蛇鸡"),
    )
    result = parse(document)

    values = {record.issue: record.zodiac_text for record in result.records}
    assert values[296] == "马牛蛇狗龙虎猴鼠兔"
    assert values[295] == "兔牛虎鸡猴猪马羊鼠"
    assert values[294] == "马羊猴鼠猪龙狗蛇鸡"
    for text in values.values():
        assert len(text) == 9
        assert len(set(text)) == 9


def test_title_line_is_not_mistaken_for_a_record() -> None:
    """页首标题行同为 `296期:` 开头，但下一行不是纯九肖行，不得生成 296 记录。"""
    document = page(
        ("295期:【皇帝九肖】开:马25准", "兔牛虎鸡猴猪马羊鼠"),
        ("294期:【皇帝九肖】开:兔28错", "马羊猴鼠猪龙狗蛇鸡"),
    )
    result = parse(document, (296, 295, 294))

    issues = [r.issue for r in result.records]
    assert 296 not in issues
    assert {295, 294} <= set(issues)


def test_issue_line_without_zodiac_line_is_skipped() -> None:
    """期号行下一行不是九肖时，该期不生成记录。

    同时验证：遇到非数据内容行（这里是「版权所有」）即视为栏目边界，
    其后的期号不再被采纳——这正是防止跨栏目借值的连续性约束。
    """
    document = page(
        ("296期:【皇帝九肖】开:？00准", "马牛蛇狗龙虎猴鼠兔"),
        ("295期:【皇帝九肖】开:马25准", "版权所有 免责声明"),
        ("294期:【皇帝九肖】开:兔28错", "马羊猴鼠猪龙狗蛇鸡"),
    )
    result = parse(document, (296, 295, 294))

    issues = {r.issue for r in result.records}
    assert 295 not in issues, "下一行不是九肖，不得生成 295"
    assert 294 not in issues, "内容行之后的期号属其它栏目，不得采纳"
    assert 296 in issues


def test_duplicate_zodiacs_in_line_are_rejected() -> None:
    document = page(
        ("296期:【皇帝九肖】开:？00准", "马马蛇狗龙虎猴鼠兔"),
        ("295期:【皇帝九肖】开:马25准", "兔牛虎鸡猴猪马羊鼠"),
    )
    result = parse(document, (296, 295))

    assert 296 not in {r.issue for r in result.records}
    assert 295 in {r.issue for r in result.records}


def test_ten_period_depth_is_not_truncated() -> None:
    """区块必须覆盖完整历史（10 期），不得被通用区块构建的行数上限截断。"""
    pairs = [
        (f"{issue}期:【皇帝九肖】开:00准", "马牛蛇狗龙虎猴鼠兔")
        for issue in range(298, 288, -1)
    ]
    result = parse(page(*pairs), tuple(range(298, 288, -1)))

    issues = {r.issue for r in result.records}
    assert issues == set(range(298, 288, -1)), sorted(issues)
