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
    Evidence,
    History,
    Position,
    Record,
    Result,
    Source,
)
from v2.parsers.custom.complement_three import ComplementThreeParser  # noqa: E402
from v2.parsers.custom.formula_next_issue_ocr import (  # noqa: E402
    FormulaNextIssueOcrParser,
)
from v2.parsers.custom.yueying import YueyingParser  # noqa: E402
from v2.parsers.direct_nine import DirectNineParser  # noqa: E402
from v2.parsers.image_ocr import ImageOcrParser  # noqa: E402
from v2.parsers.registry import line_issue  # noqa: E402
from v2.runtime import _cycle_label  # noqa: E402
from v2.services.cache_sync import CacheSyncService  # noqa: E402
from v2.storage.cache import CacheSnapshot, CacheSource  # noqa: E402
from v2.validator import ValidationError, Validator  # noqa: E402


NINE_A = "鼠牛虎兔龙蛇马羊猴"
NINE_B = "鸡狗猪鼠牛虎兔龙蛇"


def _source(
    *,
    name: str = "测试目录",
    url: str = "https://example.test/topic/1.html",
    parser: str = "direct_nine",
    section_marker: str = "九肖中特",
    fetcher: str = "static_page",
    data_marker: str = "",
    source_policy: tuple[str, ...] = (),
) -> Source:
    return Source(
        name=name,
        url=url,
        position=Position.TOP,
        section_marker=section_marker,
        fetcher=fetcher,
        parser=parser,
        data_marker=data_marker,
        source_policy=source_policy,
    )


def _result(source: Source, issue: int, value: str = NINE_A) -> Result:
    record = Record(
        issue,
        tuple(value),
        Evidence("test", value, source.name, "test"),
    )
    return Result.succeeded(source, (issue,), History((record,), issue))


def test_complement_three_does_not_bind_later_issue_payload_to_first_issue() -> None:
    target = _source(
        parser="complement_three",
        section_marker="绝杀三肖",
        data_marker="绝杀三肖",
    )
    document = Document(
        label="page",
        url=target.url,
        text=(
            "绝杀三肖\n"
            "251期 绝杀三肖【鼠牛虎】 "
            "250期 绝杀三肖【兔龙蛇】"
        ),
        method=DocumentMethod.STATIC_PAGE,
    )

    parsed = ComplementThreeParser().parse(target, (document,), (251,))
    verified = Validator().validate(target, parsed, (251,))

    assert verified.history.records[0].zodiac_text == "兔龙蛇马羊猴鸡狗猪"


def test_yueying_does_not_borrow_second_issue_nine_zodiacs() -> None:
    target = _source(
        name="月影舞华",
        parser="yueying",
        section_marker="月影舞华",
    )
    document = Document(
        label="page",
        url=target.url,
        text=(
            "月影舞华\n"
            f"251期九肖中特【{NINE_A}】 "
            f"250期九肖中特【{NINE_B}】"
        ),
        method=DocumentMethod.STATIC_PAGE,
    )

    parsed = YueyingParser().parse(target, (document,), (251,))
    verified = Validator().validate(target, parsed, (251,))

    assert verified.history.records[0].zodiac_text == NINE_A


def test_formula_multiple_complete_nine_zodiac_fields_conflict() -> None:
    target = _source(
        parser="formula_next_issue_ocr",
        fetcher="browser_page",
        source_policy=(DocumentMethod.BROWSER_DOM.value,),
    )
    document = Document(
        label="browser-dom",
        url=target.url,
        text=(
            "九肖中特\n"
            f"250期 九肖 下期：【{NINE_A}】 备用：【{NINE_B}】"
        ),
        method=DocumentMethod.BROWSER_DOM,
    )

    parsed = FormulaNextIssueOcrParser().parse(target, (document,), (251,))
    with pytest.raises(ValidationError) as captured:
        Validator().validate(target, parsed, (251,))

    assert captured.value.failure.code is ErrorCode.CANDIDATE_CONFLICT


def test_zero_issue_is_ignored_before_block_evidence_is_built() -> None:
    assert line_issue(f"000期 九肖【{NINE_B}】") is None

    target = _source()
    document = Document(
        label="page",
        url=target.url,
        text=(
            "九肖中特\n"
            f"000期 九肖【{NINE_B}】\n"
            f"251期 九肖【{NINE_A}】"
        ),
        method=DocumentMethod.STATIC_PAGE,
    )
    parsed = DirectNineParser().parse(target, (document,), (251,))
    verified = Validator().validate(target, parsed, (251,))

    assert verified.history.records[0].zodiac_text == NINE_A


def test_linked_image_ocr_can_join_three_or_more_continuation_lines() -> None:
    marker = "测试九肖"
    target = _source(
        parser="image_ocr",
        fetcher="browser_page",
        section_marker=marker,
        source_policy=(DocumentMethod.IMAGE_OCR.value,),
    )
    document = Document(
        label="image-ocr:1",
        url=target.url,
        text="251期 九肖\n鼠牛虎兔\n龙蛇马\n羊猴",
        method=DocumentMethod.IMAGE_OCR,
        metadata=(
            ("image_index", "1"),
            ("parent_url", target.url),
            ("anchor_line", marker),
            ("anchor_term", marker),
            ("data_marker_line", f"{marker} 九肖"),
            ("anchor_index", "4"),
            ("block_start", "4"),
            ("block_end", "8"),
        ),
    )

    parsed = ImageOcrParser().parse(target, (document,), (251,))
    verified = Validator().validate(target, parsed, (251,))

    assert verified.history.records[0].zodiac_text == NINE_A


class _MemoryCacheRepository:
    def __init__(self, snapshot: CacheSnapshot) -> None:
        self.snapshot = snapshot

    class _Lock:
        def __enter__(self):
            return None

        def __exit__(self, *_args):
            return False

    def locked(self):
        return self._Lock()

    def load(self) -> CacheSnapshot:
        return self.snapshot

    def sync(self, snapshot: CacheSnapshot) -> CacheSnapshot:
        self.snapshot = snapshot
        return snapshot


def test_default_cycle_label_is_empty_and_preserves_existing_cycle() -> None:
    assert _cycle_label(None) == ""

    target = _source()
    old_issues = tuple(range(365, 355, -1))
    previous = CacheSnapshot(
        latest_issue=365,
        issues=old_issues,
        sources=(CacheSource(target),),
        cycle="2026",
    )
    repository = _MemoryCacheRepository(previous)
    snapshot = CacheSyncService(repository).sync_single(
        (target,),
        (_result(target, 365),),
        365,
    )

    assert snapshot.cycle == "2026"
    assert snapshot.issues == old_issues


def test_explicit_cycle_switch_resets_even_from_legacy_unknown_cycle() -> None:
    target = _source()
    previous = CacheSnapshot(
        latest_issue=365,
        issues=tuple(range(365, 355, -1)),
        sources=(CacheSource(target),),
        cycle="",
    )
    repository = _MemoryCacheRepository(previous)
    snapshot = CacheSyncService(repository).sync_single(
        (target,),
        (_result(target, 1),),
        1,
        cycle="2027",
    )

    assert snapshot.cycle == "2027"
    assert snapshot.issues == (1,)
    assert dict(snapshot.sources[0].records)[1] == NINE_A
