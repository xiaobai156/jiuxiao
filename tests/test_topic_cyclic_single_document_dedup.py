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
    if specification is None or specification.loader is None:
        raise RuntimeError("无法加载 V2 测试包")
    package = importlib.util.module_from_spec(specification)
    sys.modules["v2"] = package
    specification.loader.exec_module(package)

from v2.config.repository import SourceRepository  # noqa: E402
from v2.domain.errors import ErrorCode  # noqa: E402
from v2.domain.models import Document, DocumentMethod  # noqa: E402
from v2.parsers.custom.topic_cyclic import TopicCyclicParser  # noqa: E402
from v2.validator import ValidationError, Validator  # noqa: E402


CURRENT_314 = "马鸡鼠蛇兔猴狗牛羊"
POST_COUNT = 8


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


def _post(index: int) -> list[str]:
    """SPA 用户页里的一个帖子区块：锚点行自带期号，正文只有一轮历史。"""
    return [
        "停止武术",
        f"2026-11-10 11:0{index}:34",
        "314",
        "九肖中特",
        "澳彩",
        f"314期:九肖中特【{CURRENT_314}】开0000准",
        "0",
        f"{1000 + index}",
        "0",
    ]


def multi_section_document() -> Document:
    lines: list[str] = ["【会员专区】", "全部主题"]
    for index in range(POST_COUNT):
        lines.extend(_post(index))
    return Document(
        label="browser-dom",
        url=configured_source().url,
        text="\n".join(lines),
        method=DocumentMethod.BROWSER_DOM,
    )


def test_single_document_multi_section_submits_document_once() -> None:
    """同一文档里的多个单轮板块只能把整篇文档收一次，否则区块身份重复。"""
    source = configured_source()
    records = TopicCyclicParser().parse(source, (multi_section_document(),), (314,))

    assert len(records) == POST_COUNT

    verified = Validator().validate(source, records, (314,))

    assert verified.history.records[0].issue == 314
    assert verified.history.records[0].zodiac_text == CURRENT_314


def test_single_document_multi_section_rejects_nonexistent_issue() -> None:
    source = configured_source()
    records = TopicCyclicParser().parse(source, (multi_section_document(),), (315,))

    with pytest.raises(ValidationError) as captured:
        Validator().validate(source, records, (315,))

    assert captured.value.failure.code is ErrorCode.ISSUE_MISSING
