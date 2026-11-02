"""分组图例行不得截断历史区块（2026-10-20，293 期「一毛不拔」）。

站方把图例 `春:虎兔龙 夏:蛇马羊 秋:猴狗鸡 冬:鼠牛猪` 插在第一段历史与续段
之间。旧逻辑把它当成「区块结束信号」，导致续段（含最新 293 期）整段被切掉，
表现为 ISSUE_MISSING。修复后图例行只跳过、不结束区块。
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
from v2.parsers.registry import is_group_legend  # noqa: E402


GROUP_MAP = (
    ("春", "虎兔龙"),
    ("夏", "蛇马羊"),
    ("秋", "猴狗鸡"),
    ("冬", "鼠牛猪"),
)
LEGEND = "春:虎兔龙 夏:蛇马羊 秋:猴狗鸡 冬:鼠牛猪"


def source() -> Source:
    return Source(
        name="一毛不拔",
        url="https://example.test/article/1",
        position=Position.BOTTOM,
        section_marker="",
        fetcher="dynamic_article",
        parser="grouped",
        group_map=GROUP_MAP,
        data_marker="春夏秋冬",
    )


def history(issues: range) -> list[str]:
    lines = []
    for issue in issues:
        lines.append(
            f"{issue}期: 【一毛不拔】 🍀 ③季中特 🍀【冬秋春】开: 00 准"
        )
    return lines


def parse(text: str, issues: tuple[int, ...]):
    document = Document(
        label="api:$",
        url="https://example.test/article/1",
        text=text,
        method=DocumentMethod.DYNAMIC_API,
    )
    return build_parser_registry().resolve("grouped").parse(
        source(), (document,), issues
    )


def test_group_legend_is_recognized() -> None:
    assert is_group_legend(LEGEND)
    # 数据行与普通文本都不得被判为图例
    assert not is_group_legend(
        "292期: 【一毛不拔】 🍀 ③季中特 🍀【秋夏春】开: 00 准"
    )
    assert not is_group_legend("一毛不拔")


def test_legend_between_two_history_runs_does_not_cut_block() -> None:
    """图例插在两段历史之间时，续段里的最新期必须能读到。"""
    text = "\n".join(
        [
            "293期：【③季中特】〓 大胆下注",
            "一毛不拔",
            *history(range(164, 293)),
            LEGEND,
            *history(range(240, 294)),
            LEGEND,
        ]
    )
    result = parse(text, (293,))

    issues = {record.issue for record in result.records}
    assert 293 in issues
    assert len(result.blocks) == 1
    latest = next(record for record in result.records if record.issue == 293)
    # 冬=鼠牛猪 秋=猴狗鸡 春=虎兔龙
    assert latest.zodiac_text == "鼠牛猪猴狗鸡虎兔龙"


def test_legend_without_following_history_still_parses_earlier_run() -> None:
    """图例后没有续段时，前面的历史照常可读，不受影响。"""
    text = "\n".join(
        [
            "293期：【③季中特】〓 大胆下注",
            "一毛不拔",
            *history(range(290, 294)),
            LEGEND,
        ]
    )
    result = parse(text, (293,))

    assert {record.issue for record in result.records} >= {290, 291, 292, 293}
