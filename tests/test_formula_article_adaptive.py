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

from v2.domain.errors import ErrorCode  # noqa: E402
from v2.config.repository import SourceRepository  # noqa: E402
from v2.domain.models import (  # noqa: E402
    Document,
    DocumentMethod,
    Position,
    Source,
)
from v2.parsers.custom.formula_article_adaptive import (  # noqa: E402
    FormulaArticleAdaptiveParser,
)
from v2.parsers.custom.formula_article_ocr_alias import (  # noqa: E402
    FormulaArticleOcrAliasParser,
)
from v2.parsers.factory import build_parser_registry  # noqa: E402
from v2.parsers.registry import ParseError  # noqa: E402
from v2.validator import ValidationError, Validator  # noqa: E402


URL = "https://bemgrnty.o1uab-4e5oe-yyddxc.xyz:16677/topic/433514.html"
EXPECTED_228 = "羊马蛇龙兔虎牛鼠猪"


def source(
    *,
    position: Position = Position.BOTTOM,
    marker: str = "风神九肖",
) -> Source:
    return Source(
        name="风神九肖",
        url=URL,
        position=position,
        section_marker=marker,
        fetcher="browser_page",
        parser="formula_article_adaptive",
        data_marker="九肖",
        source_policy=("browser_dom", "image_ocr"),
    )


def dom_document(text: str) -> Document:
    return Document(
        label="browser-dom",
        url=URL,
        text=text,
        method=DocumentMethod.BROWSER_DOM,
    )


def ocr_document(text: str) -> Document:
    return Document(
        label="image-ocr:1",
        url=URL,
        text=text,
        method=DocumentMethod.IMAGE_OCR,
        metadata=(
            ("image_index", "1"),
            ("parent_url", URL),
            ("anchor_line", "228期风神九肖"),
            ("anchor_term", "风神九肖"),
            ("data_marker_line", "228期风神九肖"),
            ("anchor_index", "9"),
            ("block_start", "9"),
            ("block_end", "18"),
        ),
    )


DOM_IMAGE_DAY = """澳门白虎
228期风神九肖
作者:澳门公式
上一篇：
228期小白平特
下一篇：
228期怡情四头
澳门-白虎 『站长推荐好料』
228期㉿一肖㉿【虎】免费公开
228期㉿三肖㉿【虎猴马】免费公开
228期㉿五肖㉿【虎猴马鸡蛇】免费公开
228期㉿七肖㉿【虎猴马鸡蛇牛猪】免费公开
228期㉿九肖㉿【虎猴马鸡蛇牛猪兔鼠】免费公开
"""


OCR_IMAGE_DAY = """224期:251908491836+09公式：+9下期：虎牛鼠猪狗鸡猴羊马√
225期：073427101938+01公式：+9下期：鼠猪狗鸡猴羊马蛇龙×
226期:011129380433+17公式：+9下期：蛇龙兔虎牛鼠猪狗鸡√
227期：232429071331+16公式：+9下期：羊马蛇龙兔虎牛鼠猪√
228期：羊马蛇龙免虎牛鼠猪
"""


DOM_TEXT_DAY = """澳门白虎
228期风神九肖
作者:澳门公式
226期：鼠猪狗鸡猴羊马蛇龙
227期：蛇龙兔虎牛鼠猪狗鸡
228期：羊马蛇龙兔虎牛鼠猪
上一篇：
228期小白平特
澳门-白虎 『站长推荐好料』
228期㉿一肖㉿【虎】免费公开
228期㉿九肖㉿【虎猴马鸡蛇牛猪兔鼠】免费公开
"""


def validate(
    documents: tuple[Document, ...],
    issue: int = 228,
    *,
    candidate: Source | None = None,
):
    selected_source = candidate or source()
    parsed = FormulaArticleAdaptiveParser().parse(
        selected_source,
        documents,
        (issue,),
    )
    return Validator().validate(selected_source, parsed, (issue,))


def test_image_day_uses_clean_previous_next_issue_when_explicit_ocr_is_malformed() -> None:
    verified = validate(
        (dom_document(DOM_IMAGE_DAY), ocr_document(OCR_IMAGE_DAY))
    )

    record = verified.history.records[0]
    assert record.zodiac_text == EXPECTED_228
    assert record.evidence.document_method == "image_ocr"
    assert record.evidence.direction_window == (228, 227, 226)
    assert dict(record.evidence.metadata)["issue_mapping"] == "next_issue"


def test_unrelated_dom_recommendations_never_become_formula_candidates() -> None:
    candidate = source()
    parsed = FormulaArticleAdaptiveParser().parse(
        candidate,
        (dom_document(DOM_IMAGE_DAY), ocr_document(OCR_IMAGE_DAY)),
        (228,),
    )

    assert parsed.records
    assert all(
        record.evidence.document_method == "image_ocr"
        for record in parsed.records
        if record.issue == 228
    )
    assert not any(
        "站长推荐" in record.evidence.source_line
        or "一肖" in record.evidence.source_line
        for record in parsed.records
    )


def test_text_day_uses_strict_dom_article_block() -> None:
    verified = validate((dom_document(DOM_TEXT_DAY),))

    record = verified.history.records[0]
    assert record.zodiac_text == EXPECTED_228
    assert record.evidence.document_method == "browser_dom"
    assert record.evidence.actual_anchor_line == "228期风神九肖"


def test_adjacent_issue_is_parsed_from_same_linked_image_block() -> None:
    verified = validate(
        (dom_document(DOM_IMAGE_DAY), ocr_document(OCR_IMAGE_DAY)),
        227,
    )

    assert verified.history.records[0].zodiac_text == "蛇龙兔虎牛鼠猪狗鸡"


def test_missing_issue_fails_without_using_unrelated_dom_data() -> None:
    with pytest.raises(ValidationError) as captured:
        validate(
            (dom_document(DOM_IMAGE_DAY), ocr_document(OCR_IMAGE_DAY)),
            229,
        )

    assert captured.value.failure.code is ErrorCode.ISSUE_MISSING


def test_wrong_anchor_fails() -> None:
    with pytest.raises(ParseError) as captured:
        validate(
            (dom_document(DOM_IMAGE_DAY), ocr_document(OCR_IMAGE_DAY)),
            candidate=source(marker="不存在栏目"),
        )

    assert captured.value.failure.code is ErrorCode.ANCHOR_MISSING


def test_top_direction_cannot_take_bottom_target() -> None:
    with pytest.raises(ValidationError) as captured:
        validate(
            (dom_document(DOM_IMAGE_DAY), ocr_document(OCR_IMAGE_DAY)),
            candidate=source(position=Position.TOP),
        )

    assert captured.value.failure.code is ErrorCode.ISSUE_MISSING


def test_valid_dom_and_ocr_disagreement_is_rejected() -> None:
    conflicting_ocr = ocr_document(
        OCR_IMAGE_DAY.replace(EXPECTED_228, "鼠牛虎兔龙蛇马羊猴")
    )

    with pytest.raises(ValidationError) as captured:
        validate((dom_document(DOM_TEXT_DAY), conflicting_ocr))

    assert captured.value.failure.code is ErrorCode.DOCUMENT_CONFLICT


def test_malformed_target_without_valid_previous_mapping_fails() -> None:
    malformed_only = ocr_document("228期：羊马蛇龙免虎牛鼠猪")

    with pytest.raises(ParseError) as captured:
        validate((dom_document(DOM_IMAGE_DAY), malformed_only))

    assert captured.value.failure.code is ErrorCode.INVALID_ZODIAC_COUNT


def test_parser_does_not_mutate_source_identity() -> None:
    candidate = source()
    original = replace(candidate)

    validate((dom_document(DOM_TEXT_DAY),), candidate=candidate)

    assert candidate == original


def test_formal_config_selects_strict_ocr_alias_parser_for_target() -> None:
    repository = SourceRepository(
        PROJECT_ROOT / "config" / "sources.json",
        PROJECT_ROOT / "config" / "archived_sources.json",
    )
    active = repository.load_active()
    matches = tuple(item for item in active if item.name == "风神九肖")

    assert len(matches) == 1
    assert matches[0].parser == "formula_article_ocr_alias"
    assert isinstance(
        build_parser_registry().resolve(matches[0].parser),
        FormulaArticleOcrAliasParser,
    )
