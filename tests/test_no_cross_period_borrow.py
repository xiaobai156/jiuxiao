"""跨期借值回归测试（2026-10-25 代码审查修复）。

审查确认 5 条可复现路径，本文件把其中不依赖真实抓取的部分固化成回归：

1. `fajiazhifu` / `taipingshengshi` 曾把首块扩张成「整页区块」，
   使 `observed_issues` 吞进同页其它栏目的期号 ⇒ 跨栏目借值。
   修法：只在区块自身 `block.start..block.end` 范围内配对。
2. `leitingdanu` 曾用 `range(len(lines)-1)` 扫全页，绕过区块边界。
   修法：同样限定在区块行号范围内。
3. `header_direct_nine` 曾把锚点替换成数据词「九肖中特」，同页任何含该词的
   栏目都会命中。修法：锚点保持站点自身的 `section_marker`。
4. `direct_nine` 在 001/365 双轮页面只截断不丢弃，保留上一轮同号期，
   使指定期只存在于上一轮时被当成本期结果。修法：不截断，让同期两个不同
   取值都进入候选，由 Validator 报 `CANDIDATE_CONFLICT`。
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


def _document(name: str, text: str) -> Document:
    return Document(
        label="browser-dom",
        url=f"https://example.test/{name}",
        text=text,
        method=DocumentMethod.BROWSER_DOM,
    )


def _parse(parser: str, source: Source, text: str, issues: tuple[int, ...]):
    return build_parser_registry().resolve(parser).parse(
        source, (_document(source.name, text),), issues
    )


# ---------------------------------------------------------------- fajiazhifu
def _fajiazhifu_source() -> Source:
    return Source(
        name="发家致富",
        url="https://example.test/fajiazhifu",
        position=Position.TOP,
        section_marker="发家致富",
        fetcher="browser_page",
        parser="fajiazhifu",
        data_marker="九肖",
    )


def test_fajiazhifu_does_not_borrow_from_another_column() -> None:
    """本栏只有 296/295；294 只出现在同页另一个栏目，必须取不到。"""
    text = "\n".join(
        (
            "296期:49姜子牙【皇帝九肖】发家致富",
            "作者:发家致富",
            "296期:【皇帝九肖】开:？00准",
            "马牛蛇狗龙虎猴鼠兔",
            "295期:【皇帝九肖】开:马25准",
            "兔牛虎鸡猴猪马羊鼠",
            "",
            "某广告栏目",
            "294期:【皇帝九肖】开:兔28错",
            "马羊猴鼠猪龙狗蛇鸡",
        )
    )
    result = _parse("fajiazhifu", _fajiazhifu_source(), text, (296, 295, 294))

    issues = {record.issue for record in result.records}
    assert 294 not in issues, "不得借同页其它栏目的 294 期"
    assert {296, 295} <= issues


# ------------------------------------------------------------ taipingshengshi
def _taipingshengshi_source() -> Source:
    return Source(
        name="太平盛世",
        url="https://example.test/taipingshengshi",
        position=Position.TOP,
        section_marker="太平盛世",
        fetcher="browser_page",
        parser="taipingshengshi",
        data_marker="九肖中特",
    )


def test_taipingshengshi_does_not_borrow_from_another_column() -> None:
    text = "\n".join(
        (
            "298期:49高手精选【九肖中特】太平盛世",
            "作者:太平盛世",
            "298期九肖中特开？00准",
            "",
            "【狗猪虎羊鼠牛兔龙鸡】",
            "297期九肖中特开马13准",
            "",
            "【鼠蛇牛龙鸡狗马羊猴】",
            "",
            "乙栏标题",
            "296期九肖中特开猴23准",
            "",
            "【猪鼠龙狗猴蛇牛鸡马】",
        )
    )
    result = _parse(
        "taipingshengshi", _taipingshengshi_source(), text, (298, 297, 296)
    )

    issues = {record.issue for record in result.records}
    assert 296 not in issues, "不得借同页其它栏目的 296 期"
    assert {298, 297} <= issues


# --------------------------------------------------------------- leitingdanu
def _leitingdanu_source() -> Source:
    return Source(
        name="雷霆大怒",
        url="https://example.test/leitingdanu",
        position=Position.TOP,
        section_marker="",
        fetcher="browser_page",
        parser="leitingdanu",
        data_marker="九肖",
    )


def test_leitingdanu_does_not_scan_whole_page() -> None:
    text = "\n".join(
        (
            "返回首页",
            "296期雷霆大怒【枯木逢春九肖】准",
            "296期：枯木逢春九肖",
            "【牛猪马虎鸡鼠猴狗羊】开？00准",
            "295期：枯木逢春九肖",
            "【牛猴鸡兔鼠虎狗猪龙】开马25错",
            "",
            "其它栏目",
            "292期：枯木逢春九肖",
            "【鸡狗猪鼠牛虎兔龙蛇】开虎05准",
        )
    )
    result = _parse("leitingdanu", _leitingdanu_source(), text, (296, 295, 292))

    issues = {record.issue for record in result.records}
    assert 292 not in issues, "不得越过区块边界取到 292 期"
    assert {296, 295} <= issues
