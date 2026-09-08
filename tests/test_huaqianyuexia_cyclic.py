from __future__ import annotations

import importlib.util
import json
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
    if specification is None or specification.loader is None:
        raise RuntimeError("无法加载 V2 测试包")
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
from v2.parsers.custom.topic_cyclic import TopicCyclicParser  # noqa: E402
from v2.parsers.direct_nine import DirectNineParser  # noqa: E402
from v2.validator import ValidationError, Validator  # noqa: E402


NAME = "花前月下"
TITLE = "花前九肖"
URL = "https://jogavu.6bl6s-ilo1w-yfnvvl.work:16677/topic/622320.html"
OLD_VALUE = "狗猪羊马鼠鸡虎猴牛"
CURRENT_VALUE = "虎马鼠猴龙牛兔羊蛇"
HISTORY_VALUE = "猪羊猴兔鸡狗鼠虎牛"


def source(*, parser: str = "topic_cyclic_nine") -> Source:
    return Source(
        name=NAME,
        url=URL,
        position=Position.BOTTOM,
        section_marker=TITLE,
        fetcher="browser_page",
        parser=parser,
        aliases=(NAME,),
    )


def document() -> Document:
    old_cycle = [
        f"235期「{TITLE}」【{OLD_VALUE}】开：鼠42准",
        *(
            f"{issue:03d}期「{TITLE}」【鼠牛虎兔龙蛇马羊猴】开：0000准"
            for issue in range(346, 366)
        ),
    ]
    current_cycle = [
        *(
            f"{issue:03d}期「{TITLE}」【鼠牛虎兔龙蛇马羊猴】开：0000准"
            for issue in range(1, 19)
        ),
        f"234期「{TITLE}」【{HISTORY_VALUE}】开：龙39错",
        f"235期「{TITLE}」【{CURRENT_VALUE}】开：0000准",
    ]
    return Document(
        label="browser-dom",
        url=URL,
        text="\n".join(
            (
                f"九肖区 235期: {NAME}「{TITLE}」194中135",
                *old_cycle,
                *current_cycle,
            )
        ),
        method=DocumentMethod.BROWSER_DOM,
    )


def test_regular_parser_reproduces_cross_cycle_235_conflict() -> None:
    candidate = source(parser="direct_nine")
    records = DirectNineParser().parse(candidate, (document(),), (235,))

    with pytest.raises(ValidationError) as captured:
        Validator().validate(candidate, records, (235,))

    assert captured.value.failure.code is ErrorCode.CANDIDATE_CONFLICT


def test_cyclic_parser_selects_current_bottom_cycle() -> None:
    candidate = source()
    records = TopicCyclicParser().parse(candidate, (document(),), (235,))

    verified = Validator().validate(candidate, records, (235,))
    record = verified.history.records[0]

    assert record.zodiac_text == CURRENT_VALUE
    assert record.evidence.direction_window == (235, 234, 18)
    assert dict(record.evidence.metadata)["cycle_segment"] == "2"


def test_cyclic_parser_keeps_outside_issue_out_of_bottom_window() -> None:
    candidate = source()
    records = TopicCyclicParser().parse(candidate, (document(),), (236,))

    with pytest.raises(ValidationError) as captured:
        Validator().validate(candidate, records, (236,))

    assert captured.value.failure.code is ErrorCode.ISSUE_MISSING


def test_formal_override_uses_cyclic_parser_for_exact_identity() -> None:
    config = json.loads(
        (PROJECT_ROOT / "config" / "main_list_parser_overrides.json").read_text(
            encoding="utf-8"
        )
    )
    matches = tuple(
        item
        for item in config["overrides"]
        if item["name"] == NAME and item["title"] == TITLE and item["url"] == URL
    )

    assert len(matches) == 1
    assert matches[0]["parser"] == "topic_cyclic_nine"
