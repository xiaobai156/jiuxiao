"""造褔人群（261 期新增）配置与解析回归测试。"""

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
    assert specification is not None and specification.loader is not None
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
from v2.validator import ValidationError, Validator  # noqa: E402

URL = "https://bbyy.700020.com/read.php?tid=7072"
NAME = "造褔人群"
# 该页为论坛讨论串：顶部是标题行与栏目标记，历史行按 187→261 由旧到新，
# 最新期在尾部，故方向为 bottom。
PAGE = """主题 : 361期:🏆宝塔论坛🏆【造褔人群🀄⑨肖中特】新澳独家发表
【造褔人群】
361期:🏆宝塔论坛🏆【造褔人群🀄⑨肖中特】新澳独家发表
187期:📇［造褔人群］⑨肖中特📇『蛇马猪龙兔虎鼠猴羊』开:马01中
188期:📇［造褔人群］⑨肖中特📇『兔猴鼠羊猪龙蛇虎牛』开:兔16中
189期:📇［造褔人群］⑨肖中特📇『鸡猪蛇马牛龙猴鼠兔』开:龙15中
259期:📇［造褔人群］⑨肖中特📇『龙羊狗虎兔牛蛇鼠马』开:鸡22错
260期:📇［造褔人群］⑨肖中特📇『龙羊狗虎猪牛蛇鼠马』开:猪20中
261期:📇［造褔人群］⑨肖中特📇『龙羊狗虎兔牛蛇鼠马』开:？00中
下一篇：261期:六合彩网-家野中特-93911.com
"""


def source(*, position: Position = Position.BOTTOM, marker: str = NAME) -> Source:
    return Source(
        name=NAME,
        url=URL,
        position=position,
        section_marker=marker,
        fetcher="browser_page",
        parser="direct_nine",
        aliases=("造福人群",),
    )


def document() -> Document:
    return Document(
        label="browser-dom",
        url=URL,
        text=PAGE,
        method=DocumentMethod.BROWSER_DOM,
    )


def test_formal_source_is_registered_exactly_once() -> None:
    repo = SourceRepository(
        PROJECT_ROOT / "config" / "sources.json",
        PROJECT_ROOT / "config" / "archived_sources.json",
    )
    matches = [s for s in repo.load_active() if s.name == NAME]
    assert len(matches) == 1
    assert matches[0] == source()


def test_bottom_window_selects_current_issue() -> None:
    candidate = source()
    parsed = DirectNineParser().parse(candidate, (document(),), (261,))
    verified = Validator().validate(candidate, parsed, (261,))
    record = verified.history.records[0]
    assert record.zodiac_text == "龙羊狗虎兔牛蛇鼠马"
    assert record.evidence.direction_window == (261, 260, 259)


def test_adjacent_issues_within_window() -> None:
    candidate = source()
    for issue, expected in ((260, "龙羊狗虎猪牛蛇鼠马"), (259, "龙羊狗虎兔牛蛇鼠马")):
        parsed = DirectNineParser().parse(candidate, (document(),), (issue,))
        verified = Validator().validate(candidate, parsed, (issue,))
        assert verified.history.records[0].zodiac_text == expected


def test_issue_outside_window_fails() -> None:
    candidate = source()
    parsed = DirectNineParser().parse(candidate, (document(),), (258,))
    with pytest.raises(ValidationError) as captured:
        Validator().validate(candidate, parsed, (258,))
    assert captured.value.failure.code is ErrorCode.ISSUE_MISSING


def test_nonexistent_issue_fails() -> None:
    candidate = source()
    parsed = DirectNineParser().parse(candidate, (document(),), (362,))
    with pytest.raises(ValidationError) as captured:
        Validator().validate(candidate, parsed, (362,))
    assert captured.value.failure.code is ErrorCode.ISSUE_MISSING


def test_wrong_anchor_fails() -> None:
    candidate = replace(source(), section_marker="不存在栏目")
    with pytest.raises(ParseError) as captured:
        DirectNineParser().parse(candidate, (document(),), (261,))
    assert captured.value.failure.code is ErrorCode.ANCHOR_MISSING


def test_top_direction_cannot_take_tail_issue() -> None:
    candidate = source(position=Position.TOP)
    parsed = DirectNineParser().parse(candidate, (document(),), (261,))
    with pytest.raises(ValidationError) as captured:
        Validator().validate(candidate, parsed, (261,))
    assert captured.value.failure.code in {
        ErrorCode.ISSUE_MISSING,
        ErrorCode.INVALID_ZODIAC_COUNT,
    }
