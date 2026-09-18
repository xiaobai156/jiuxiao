r"""261 期修复回归：期号与「期」字之间允许空格。

站点把当前期写成「261 期」（期字前多一个空格），旧正则 (?<!\d)\d{3}期 不认，
导致整行被跳过、当前期无候选。
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
from v2.parsers.grouped import GroupedParser  # noqa: E402
from v2.parsers.registry import line_issue  # noqa: E402
from v2.parsers.safety import issue_scoped_segments  # noqa: E402
from v2.validator import ValidationError, Validator  # noqa: E402


@pytest.mark.parametrize(
    "line",
    (
        "261期【三季生肖】",
        "261 期【三季生肖】",
        "261  期【三季生肖】",
        "261   期【三季生肖】",
    ),
)
def test_line_issue_accepts_optional_whitespace_before_suffix(line: str) -> None:
    assert line_issue(line) == 261


@pytest.mark.parametrize(
    "line",
    (
        "261期: 九肖",
        "261 期: 九肖",
        "261   期: 九肖",
    ),
)
def test_issue_scoped_segments_accepts_optional_whitespace(line: str) -> None:
    segments = issue_scoped_segments(line)
    assert len(segments) == 1
    assert segments[0][0] == 261


@pytest.mark.parametrize(
    "line",
    (
        "1261期",  # 四位数字，不应识别
        "0261 期",  # 前置数字，不应识别
        "000期",  # 无效期号
    ),
)
def test_line_issue_still_rejects_invalid_forms(line: str) -> None:
    assert line_issue(line) is None


def _source() -> Source:
    return Source(
        name="进寸退尺",
        url="https://example.test/article/manager/abc",
        position=Position.BOTTOM,
        section_marker="",
        fetcher="dynamic_article",
        parser="grouped",
        group_map=(
            ("琴", "兔蛇鸡"),
            ("棋", "鼠牛狗"),
            ("书", "虎龙马"),
            ("画", "羊猴猪"),
        ),
        data_marker="琴棋书画",
    )


def test_grouped_parser_reads_current_issue_written_with_space() -> None:
    """当前期写成「261 期」时仍能取到该期数据。"""
    source = _source()
    document = Document(
        label="api:$",
        url=source.url,
        text=(
            "261期：【琴棋书画】〓 共同致富\n"
            "进寸退尺\n"
            "260期: 『进寸退尺』 琴棋书画 【书.画.琴】开: 猪20 准\n"
            "259期: 『进寸退尺』 琴棋书画 【画.琴.棋】开: 鸡22 准\n"
            "261   期: 『进寸退尺』 琴棋书画 【棋.书.画】开: 00 准\n"
        ),
        method=DocumentMethod.DYNAMIC_API,
    )

    parsed = GroupedParser().parse(source, (document,), (261,))
    records = [record for record in parsed.records if record.issue == 261]
    assert records, "261 期应能解析出候选"
    # 【棋.书.画】按 棋=鼠牛狗 书=虎龙马 画=羊猴猪 展开
    assert records[0].zodiac_text == "鼠牛狗虎龙马羊猴猪"

    verified = Validator().validate(source, parsed, (261,))
    assert verified.history.records[0].zodiac_text == "鼠牛狗虎龙马羊猴猪"
    # bottom 方向按行号逆序收集，故窗口为 (261, 259, 260)；仅证据元数据，不影响取值
    assert set(verified.history.records[0].evidence.direction_window) == {261, 260, 259}
    assert verified.history.records[0].evidence.direction_window[0] == 261


def test_grouped_parser_still_rejects_missing_issue() -> None:
    """正文没有 261 期时必须失败，不得用相邻期凑数。"""
    source = _source()
    document = Document(
        label="api:$",
        url=source.url,
        text=(
            "260期：【琴棋书画】〓 共同致富\n"
            "进寸退尺\n"
            "260期: 『进寸退尺』 琴棋书画 【书.画.琴】开: 猪20 准\n"
            "259期: 『进寸退尺』 琴棋书画 【画.琴.棋】开: 鸡22 准\n"
        ),
        method=DocumentMethod.DYNAMIC_API,
    )

    parsed = GroupedParser().parse(source, (document,), (261,))
    with pytest.raises(ValidationError) as captured:
        Validator().validate(source, parsed, (261,))
    assert captured.value.failure.code is ErrorCode.ISSUE_MISSING
