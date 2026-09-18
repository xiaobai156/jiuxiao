r"""261 期修复回归：循环双轮页面（每期只列 3 个分组字）应能按方向取当前期。

翻风滚雨：页面含本轮 261..001 与上一轮 365..261 两段历史，同区块内 261 期出现
两个值；配置 group_map 是四季，但页面每期只写 3 个分组字。
"""

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

from v2.domain.errors import ErrorCode  # noqa: E402
from v2.domain.models import (  # noqa: E402
    Document,
    DocumentMethod,
    Position,
    Source,
)
from v2.parsers.custom.topic_cyclic import (  # noqa: E402
    TopicCyclicGroupedParser,
)
from v2.parsers.factory import build_parser_registry  # noqa: E402
from v2.parsers.registry import ParseError  # noqa: E402
from v2.validator import ValidationError, Validator  # noqa: E402

CURRENT_261 = "鼠牛猪虎兔龙蛇马羊"  # 本轮当前期【冬春夏】
OLD_261 = "鼠牛猪蛇马羊猴鸡狗"  # 上一轮【冬夏秋】
DUMMY = "鼠牛猪虎兔龙蛇马羊"


def source(*, position: Position = Position.TOP, marker: str = "翻风滚雨") -> Source:
    return Source(
        name="翻风滚雨",
        url="https://example.test/topic/1.html",
        position=position,
        section_marker=marker,
        fetcher="browser_page",
        parser="topic_cyclic_grouped",
        group_map=(
            ("春", "虎兔龙"),
            ("夏", "蛇马羊"),
            ("秋", "猴鸡狗"),
            ("冬", "鼠牛猪"),
        ),
        data_marker="春夏秋冬",
    )


def document() -> Document:
    lines = (
        "翻风滚雨",
        "261期【三季生肖】【冬春夏】开0000准",
        "260期【三季生肖】【秋春夏】开猪20错",
        *(f"{issue:03d}期【三季生肖】【春夏秋】开龙26准" for issue in range(259, 1, -1)),
        "001期【三季生肖】【春冬秋】开牛29准",
        *(f"{issue:03d}期【三季生肖】【春夏秋】开龙26准" for issue in range(365, 261, -1)),
        "261期【三季生肖】【冬夏秋】开鸡33准",
    )
    return Document(
        label="browser-dom",
        url="https://example.test/topic/1.html",
        text="\n".join(lines),
        method=DocumentMethod.BROWSER_DOM,
    )


def test_cyclic_grouped_selects_current_run_for_top() -> None:
    candidate = source()
    parsed = TopicCyclicGroupedParser().parse(candidate, (document(),), (261,))
    verified = Validator().validate(candidate, parsed, (261,))
    record = verified.history.records[0]

    assert record.zodiac_text == CURRENT_261
    assert dict(record.evidence.metadata).get("cycle_segment") == "1"
    assert record.evidence.direction_window[0] == 261


def test_cyclic_grouped_selects_previous_run_for_bottom() -> None:
    candidate = source(position=Position.BOTTOM)
    parsed = TopicCyclicGroupedParser().parse(candidate, (document(),), (261,))
    verified = Validator().validate(candidate, parsed, (261,))
    record = verified.history.records[0]

    assert record.zodiac_text == OLD_261
    assert dict(record.evidence.metadata).get("cycle_segment") == "2"


def test_cyclic_grouped_missing_issue_and_wrong_anchor_fail() -> None:
    candidate = source()
    parsed = TopicCyclicGroupedParser().parse(candidate, (document(),), (362,))
    with pytest.raises(ValidationError) as missing:
        Validator().validate(candidate, parsed, (362,))
    assert missing.value.failure.code is ErrorCode.ISSUE_MISSING

    with pytest.raises(ParseError) as wrong_anchor:
        TopicCyclicGroupedParser().parse(
            replace(candidate, section_marker="不存在栏目"),
            (document(),),
            (261,),
        )
    assert wrong_anchor.value.failure.code is ErrorCode.ANCHOR_MISSING


def test_cyclic_grouped_parser_is_registered() -> None:
    parser = build_parser_registry().resolve("topic_cyclic_grouped")
    assert isinstance(parser, TopicCyclicGroupedParser)
    assert parser.parser_id == "topic_cyclic_grouped"
