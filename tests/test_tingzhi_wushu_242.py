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
    if specification is None or specification.loader is None:
        raise RuntimeError("无法加载 V2 测试包")
    package = importlib.util.module_from_spec(specification)
    sys.modules["v2"] = package
    specification.loader.exec_module(package)

from v2.config.repository import SourceRepository  # noqa: E402
from v2.domain.errors import ErrorCode  # noqa: E402
from v2.domain.models import Document, DocumentMethod  # noqa: E402
from v2.parsers.custom.topic_cyclic import TopicCyclicParser  # noqa: E402
from v2.parsers.direct_nine import DirectNineParser  # noqa: E402
from v2.validator import ValidationError, Validator  # noqa: E402


CURRENT_242 = "鼠牛蛇猴马兔虎羊龙"
OLD_242 = "牛羊虎蛇猴鸡猪龙鼠"
DUMMY = "鼠牛虎兔龙蛇马羊猴"


def configured_source():
    repository = SourceRepository(
        PROJECT_ROOT / "config" / "sources.json",
        PROJECT_ROOT / "config" / "archived_sources.json",
    )
    matches = tuple(
        source for source in repository.load_active() if source.name == "停止武术"
    )
    assert len(matches) == 1
    return matches[0]


def cyclic_document() -> Document:
    lines = (
        "停止武术",
        "2026-08-30 10:05:24",
        f"242期:九肖中特【{CURRENT_242}】开0000准",
        *(f"{issue:03d}期:九肖中特【{DUMMY}】开0000准" for issue in range(21, 0, -1)),
        *(f"{issue:03d}期:九肖中特【{DUMMY}】开0000准" for issue in range(365, 344, -1)),
        f"242期:九肖中特【{OLD_242}】开猴34准",
    )
    return Document(
        label="browser-dom",
        url=configured_source().url,
        text="\n".join(lines),
        method=DocumentMethod.BROWSER_DOM,
    )


def test_regular_profile_semantics_reproduce_cross_cycle_conflict() -> None:
    source = replace(configured_source(), parser="profile_history")
    records = DirectNineParser("profile_history").parse(
        source, (cyclic_document(),), (242,)
    )

    with pytest.raises(ValidationError) as captured:
        Validator().validate(source, records, (242,))

    assert captured.value.failure.code is ErrorCode.CANDIDATE_CONFLICT


def test_formal_source_uses_current_cycle_parser() -> None:
    assert configured_source().parser == "topic_cyclic_nine"


def test_current_cycle_parser_keeps_current_242_in_original_order() -> None:
    source = configured_source()
    records = TopicCyclicParser().parse(source, (cyclic_document(),), (242,))

    verified = Validator().validate(source, records, (242,))

    assert verified.history.records[0].zodiac_text == CURRENT_242


def test_current_cycle_parser_rejects_nonexistent_issue() -> None:
    source = configured_source()
    records = TopicCyclicParser().parse(source, (cyclic_document(),), (243,))

    with pytest.raises(ValidationError) as captured:
        Validator().validate(source, records, (243,))

    assert captured.value.failure.code is ErrorCode.ISSUE_MISSING
