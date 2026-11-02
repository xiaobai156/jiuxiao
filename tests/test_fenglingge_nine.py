"""风铃歌（fenglingge）专属解析器回归测试。

页面每期一行，站名与「新澳九肖」夹在期号与九肖之间，九肖两侧有装饰符：
    304期：风铃歌 新澳九肖▂ ▂▂▃ 蛇兔龙猪马牛鼠狗羊 ▅▃▂▂ 开:??
    303期：风铃歌 新澳九肖▂ ▂▂▃ 猴马猪鸡虎蛇狗鼠兔 ▅▃▂▂ 开:虎17
正文数据按「期号升序」排列（最新期在尾部），故站点方向为 bottom。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

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

from v2.domain.errors import ErrorCode  # noqa: E402
from v2.domain.models import (  # noqa: E402
    Document,
    DocumentMethod,
    Position,
    Source,
)
from v2.parsers.factory import build_parser_registry  # noqa: E402
from v2.parsers.registry import ParseError  # noqa: E402
from v2.validator import ValidationError, Validator  # noqa: E402

URL = "https://wwlhc.com/thread-99865-1-1.html"

ROWS = {
    300: "龙鼠马牛虎狗猪猴兔",
    301: "鸡兔鼠虎蛇龙羊猴狗",
    302: "马龙兔狗鼠牛猪虎羊",
    303: "猴马猪鸡虎蛇狗鼠兔",
    304: "蛇兔龙猪马牛鼠狗羊",
}


def row(issue: int, zodiacs: str, tail: str = "开:??") -> str:
    return f"{issue}期：风铃歌 新澳九肖▂ ▂▂▃ {zodiacs} ▅▃▂▂ {tail}"


def source(**overrides) -> Source:
    values = {
        "name": "风铃歌",
        "url": URL,
        "position": Position.BOTTOM,
        "section_marker": "风铃歌",
        "fetcher": "browser_page",
        "parser": "fenglingge",
        "data_marker": "九肖",
        "requires_login": True,
    }
    values.update(overrides)
    return Source(**values)


def page(*extra_lines: str, skip: tuple[int, ...] = ()) -> Document:
    lines = [
        "首页BBS港彩讨论区新澳讨论区",
        "热搜:",
        "风铃歌",
        "忘忧",
        "【304期】【风铃歌★新澳九肖】 已更新...",
    ]
    lines.extend(extra_lines)
    for issue in sorted(ROWS):
        if issue in skip:
            continue
        tail = "开:虎17" if issue < 304 else "开:??"
        lines.append(row(issue, ROWS[issue], tail))
    lines.extend(
        [
            "开奖日20:00后不再更改",
            "本主题由 Dawen 于 前天 20:20 提升",
        ]
    )
    return Document(
        label="browser-dom",
        url=URL,
        text="\n".join(lines),
        method=DocumentMethod.BROWSER_DOM,
    )


def parse(document: Document, issues: tuple[int, ...] = (304,)):
    return build_parser_registry().resolve("fenglingge").parse(
        source(), (document,), issues
    )


def test_parser_reads_current_issue() -> None:
    parsed = parse(page())
    records = [record for record in parsed.records if record.issue == 304]
    assert len(records) == 1
    assert "".join(records[0].zodiacs) == ROWS[304]
    assert records[0].evidence.method == "fenglingge"


def test_parser_reads_adjacent_issues() -> None:
    parsed = parse(page(), (302, 303, 304))
    got = {record.issue: "".join(record.zodiacs) for record in parsed.records}
    assert got[302] == ROWS[302]
    assert got[303] == ROWS[303]


def test_open_result_tail_is_not_merged_into_zodiacs() -> None:
    """行尾「开:虎17」不得并入九肖；九肖必须恰好 9 个。"""
    parsed = parse(page(), (303,))
    record = next(record for record in parsed.records if record.issue == 303)
    assert len(record.zodiacs) == 9
    assert "".join(record.zodiacs) == ROWS[303]


def test_validator_accepts_bottom_window() -> None:
    """底部方向：最新期在尾部，304 期必须落在窗口内并通过校验。"""
    parsed = parse(page())
    verified = Validator().validate(source(), parsed, (304,))
    record = verified.history.records[0]
    assert "".join(record.zodiacs) == ROWS[304]


def test_validator_rejects_missing_issue() -> None:
    parsed = parse(page(skip=(304,)))
    with pytest.raises(ValidationError) as captured:
        Validator().validate(source(), parsed, (304,))
    assert captured.value.failure.code is ErrorCode.ISSUE_MISSING


def test_parser_rejects_wrong_anchor() -> None:
    with pytest.raises(ParseError) as captured:
        build_parser_registry().resolve("fenglingge").parse(
            source(section_marker="不存在栏目"), (page(),), (304,)
        )
    assert captured.value.failure.code is ErrorCode.ANCHOR_MISSING


def test_duplicate_zodiac_row_is_skipped() -> None:
    """站方写出 10 个字且含重复时，该行不得被当成 9 肖数据。"""
    broken = row(299, "鸡猴蛇马牛鼠猪虎羊猪", "开:??")
    parsed = parse(page(broken), (299,))
    assert all(record.issue != 299 for record in parsed.records)
