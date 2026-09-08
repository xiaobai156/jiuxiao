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
from v2.domain.models import (  # noqa: E402
    Document,
    DocumentMethod,
    Position,
    Source,
)
from v2.parsers.custom.formula_article_ocr_alias import (  # noqa: E402
    FormulaArticleOcrAliasParser,
)
from v2.parsers.grouped import GroupedParser  # noqa: E402
from v2.parsers.registry import ParseError  # noqa: E402
from v2.validator import ValidationError, Validator  # noqa: E402


FORMULA_URL = "https://example.test/topic/544154.html"
FORMULA_MARKER = "嫦娥彩报╠无错九肖╣公式规律"


def formula_source(marker: str = FORMULA_MARKER) -> Source:
    return Source(
        name="嫦娥公式",
        url=FORMULA_URL,
        position=Position.BOTTOM,
        section_marker=marker,
        fetcher="browser_page",
        parser="formula_article_ocr_alias",
        data_marker="九肖",
        source_policy=("browser_dom", "image_ocr"),
    )


def formula_documents() -> tuple[Document, ...]:
    dom = Document(
        label="browser-dom",
        url=FORMULA_URL,
        text=f"231期：{FORMULA_MARKER}\n作者:澳门公式\n上一篇：",
        method=DocumentMethod.BROWSER_DOM,
    )
    image = Document(
        label="image-ocr:3",
        url=FORMULA_URL,
        text=(
            "229期:110715133316+38公式:+0下期:羊马蛇龙免虎牛鼠猪√\n"
            "230期:282647144910+16公式:+0下期:牛鼠猪狗鸡猴羊马蛇√\n"
            "231期：牛鼠猪狗鸡猴羊马蛇"
        ),
        method=DocumentMethod.IMAGE_OCR,
        metadata=(
            ("image_index", "3"),
            ("parent_url", FORMULA_URL),
            ("anchor_line", f"231期：{FORMULA_MARKER}"),
            ("anchor_term", FORMULA_MARKER),
            ("data_marker_line", f"231期：{FORMULA_MARKER}"),
            ("anchor_index", "4"),
            ("block_start", "4"),
            ("block_end", "6"),
        ),
    )
    return dom, image


def validate_formula(issue: int):
    source = formula_source()
    parsed = FormulaArticleOcrAliasParser().parse(
        source,
        formula_documents(),
        (issue,),
    )
    return Validator().validate(source, parsed, (issue,)).history.records[0]


def test_formula_231_uses_linked_image_and_ignores_dom_title() -> None:
    record = validate_formula(231)
    assert record.zodiac_text == "牛鼠猪狗鸡猴羊马蛇"
    assert record.evidence.document_method == "image_ocr"
    assert record.evidence.direction_window == (231, 230)


def test_formula_adjacent_issue_repairs_unambiguous_ocr_alias() -> None:
    record = validate_formula(230)
    metadata = dict(record.evidence.metadata)
    assert record.zodiac_text == "羊马蛇龙兔虎牛鼠猪"
    assert metadata["ocr_correction"] == "免->兔"
    assert "免" in metadata["ocr_original_line"]
    assert "兔" in metadata["ocr_corrected_line"]


def test_formula_missing_issue_and_wrong_anchor_still_fail() -> None:
    source = formula_source()
    parsed = FormulaArticleOcrAliasParser().parse(
        source,
        formula_documents(),
        (232,),
    )
    with pytest.raises(ValidationError) as missing:
        Validator().validate(source, parsed, (232,))
    assert missing.value.failure.code is ErrorCode.ISSUE_MISSING

    with pytest.raises(ParseError) as wrong_anchor:
        FormulaArticleOcrAliasParser().parse(
            formula_source("不存在栏目"),
            formula_documents(),
            (231,),
        )
    assert wrong_anchor.value.failure.code is ErrorCode.ANCHOR_MISSING


def test_ocr_alias_is_not_repaired_when_result_is_ambiguous() -> None:
    line = "229期:+0下期:羊马蛇龙免免虎牛鼠"
    assert FormulaArticleOcrAliasParser._repair_line(line) == line


def test_baozhuang_231_uses_actual_api_anchor_and_group_order() -> None:
    source = Source(
        name="爆庄内幕",
        url="https://example.test/article/manager/record-id",
        position=Position.BOTTOM,
        section_marker="桩桩件件",
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
    document = Document(
        label="api:$",
        url="https://example.test/api/record-id",
        text=(
            "桩桩件件\n"
            "230期:《桩桩件件》琴棋书画【书.棋.琴】\n"
            "231期:《桩桩件件》琴棋书画【画.书.棋】\n"
            "232期:《桩桩件件》琴棋书画【棋.画.书】"
        ),
        method=DocumentMethod.DYNAMIC_API,
        metadata=(("article_id", "record-id"),),
    )
    parsed = GroupedParser().parse(source, (document,), (231,))
    record = Validator().validate(source, parsed, (231,)).history.records[0]
    assert record.zodiac_text == "羊猴猪虎龙马鼠牛狗"
    assert record.evidence.direction_window == (232, 231, 230)


def test_formal_config_binds_only_the_two_repaired_sources() -> None:
    active = SourceRepository(
        PROJECT_ROOT / "config" / "sources.json",
        PROJECT_ROOT / "config" / "archived_sources.json",
    ).load_active()
    formula = next(source for source in active if source.name == "嫦娥公式")
    baozhuang = next(source for source in active if source.name == "爆庄内幕")

    assert formula.parser == "formula_article_ocr_alias"
    assert formula.section_marker == FORMULA_MARKER
    assert formula.data_marker == "九肖"
    assert baozhuang.parser == "grouped"
    assert baozhuang.section_marker == "桩桩件件"
