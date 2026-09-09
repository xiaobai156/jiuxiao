from __future__ import annotations

import asyncio
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
    assert specification is not None and specification.loader is not None
    package = importlib.util.module_from_spec(specification)
    sys.modules["v2"] = package
    specification.loader.exec_module(package)

from v2.config.main_list import MainListCatalog  # noqa: E402
from v2.domain.errors import ErrorCode  # noqa: E402
from v2.domain.models import (  # noqa: E402
    Document,
    DocumentMethod,
    Position,
    Source,
)
from v2.fetchers.registry import FetchRequest  # noqa: E402
from v2.parsers.custom.formula_next_issue_ocr import (  # noqa: E402
    FormulaNextIssueOcrParser,
)
from v2.parsers.direct_nine import DirectNineParser  # noqa: E402
from v2.parsers.grouped import GroupedParser  # noqa: E402
from v2.parsers.image_ocr import ImageOcrParser  # noqa: E402
from v2.parsers.registry import ParseError  # noqa: E402
from v2.services.cache_sync import CacheSyncService  # noqa: E402
from v2.services.crawl import CrawlService  # noqa: E402
from v2.storage.cache import (  # noqa: E402
    CacheRepository,
    CacheSnapshot,
    CacheSource,
)
from v2.storage.reports import ReportRepository  # noqa: E402
from v2.validator import ValidationError, Validator  # noqa: E402
from v2.runtime import _validate_main_list_completeness  # noqa: E402


def _source(
    *,
    name: str = "测试目录",
    url: str = "https://example.test/topic/1.html",
    parser: str = "direct_nine",
    section_marker: str = "九肖中特",
    source_policy: tuple[str, ...] = (),
    group_map: tuple[tuple[str, str], ...] = (),
) -> Source:
    return Source(
        name=name,
        url=url,
        position=Position.TOP,
        section_marker=section_marker,
        fetcher="static_page",
        parser=parser,
        source_policy=source_policy,
        group_map=group_map,
    )


def test_direct_parser_does_not_borrow_nine_zodiacs_from_next_issue_segment() -> None:
    target = _source()
    document = Document(
        label="page",
        url=target.url,
        text=(
            "九肖中特\n"
            "251期 九肖【鼠牛虎兔龙蛇马羊】 "
            "250期 九肖【鼠牛虎兔龙蛇马羊猴】"
        ),
        method=DocumentMethod.STATIC_PAGE,
    )

    parsed = DirectNineParser().parse(target, (document,), (251,))
    with pytest.raises(ValidationError) as captured:
        Validator().validate(target, parsed, (251,))
    assert captured.value.failure.code is ErrorCode.INVALID_ZODIAC_COUNT


def test_formula_ocr_does_not_complete_eight_zodiacs_with_opening_result() -> None:
    target = _source(
        parser="formula_next_issue_ocr",
        source_policy=(DocumentMethod.BROWSER_DOM.value,),
    )
    document = Document(
        label="browser-dom",
        url=target.url,
        text=(
            "九肖中特\n"
            "250期 九肖 公式:+0 下期:鼠牛虎兔龙蛇马羊 开:猴"
        ),
        method=DocumentMethod.BROWSER_DOM,
    )

    with pytest.raises(ParseError) as captured:
        FormulaNextIssueOcrParser().parse(target, (document,), (251,))
    assert captured.value.failure.code is ErrorCode.INVALID_ZODIAC_COUNT


def test_grouped_parser_exposes_same_issue_conflicts() -> None:
    mapping = (
        ("琴", "兔蛇鸡"),
        ("棋", "鼠牛狗"),
        ("书", "虎龙马"),
        ("画", "羊猴猪"),
    )
    target = _source(
        parser="grouped",
        section_marker="琴棋书画",
        group_map=mapping,
    )
    document = Document(
        label="page",
        url=target.url,
        text="琴棋书画\n251期 琴棋书画【琴棋书】【琴棋画】",
        method=DocumentMethod.STATIC_PAGE,
    )

    parsed = GroupedParser().parse(target, (document,), (251,))
    with pytest.raises(ValidationError) as captured:
        Validator().validate(target, parsed, (251,))
    assert captured.value.failure.code is ErrorCode.CANDIDATE_CONFLICT


class _EmptyLinksBrowser:
    async def links(self, *_args, **_kwargs):
        return ()


def test_main_list_partial_load_fails_before_daily_catalog_can_shrink(
    tmp_path: Path,
) -> None:
    directions = tmp_path / "main_list_directions.json"
    directions.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "excluded_titles": [],
                "sources": [
                    {
                        "name": "目录甲",
                        "title": "九肖中特",
                        "url": "https://example.test/topic/1.html",
                        "position": "top",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "main_list_parser_overrides.json").write_text(
        json.dumps({"schema_version": 1, "overrides": []}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="main list incomplete"):
        asyncio.run(MainListCatalog(_EmptyLinksBrowser(), directions).load())


def test_partial_main_list_is_rejected_against_previous_active_cache(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"
    cache_dir = tmp_path / "cache"
    config_dir.mkdir()
    cache_dir.mkdir()
    first = _source(
        name="目录甲",
        url="https://example.test/topic/1.html",
        section_marker="甲九肖",
    )
    second = _source(
        name="目录乙",
        url="https://example.test/topic/2.html",
        section_marker="乙九肖",
    )
    (config_dir / "main_list_directions.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "excluded_titles": [],
                "sources": [
                    {
                        "name": first.name,
                        "title": first.section_marker,
                        "url": first.url,
                        "position": "top",
                    },
                    {
                        "name": second.name,
                        "title": second.section_marker,
                        "url": second.url,
                        "position": "top",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    snapshot = CacheSnapshot(
        latest_issue=251,
        issues=(251,),
        sources=(CacheSource(first), CacheSource(second)),
    )
    (cache_dir / "recent_10_cache.json").write_bytes(
        CacheRepository._encode(snapshot)
    )

    with pytest.raises(ValueError, match="missing previously active sources"):
        _validate_main_list_completeness(tmp_path, (first,))


def test_failed_retry_rejects_ambiguous_same_url_sources(tmp_path: Path) -> None:
    url = "https://example.test/shared.html"
    first = _source(name="栏目甲", url=url, section_marker="甲")
    second = _source(name="栏目乙", url=url, section_marker="乙")
    reports = ReportRepository(tmp_path)
    (tmp_path / "251-failures.txt").write_text(
        f"失败 栏目甲 {url} 方向: top 期数: 251 阶段: 网络抓取 原因: 失败\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="无法唯一匹配"):
        reports.failed_sources(251, (first, second))


class _FetcherRegistry:
    class _Fetcher:
        async def fetch(self, _source, _request: FetchRequest):
            return ()

    def resolve(self, _key):
        return self._Fetcher()


class _ParserRegistry:
    class _Parser:
        def parse(self, *_args):
            raise ValueError("unexpected malformed input")

    def resolve(self, _key):
        return self._Parser()


def test_unexpected_site_exception_is_returned_as_failure_not_raised() -> None:
    target = _source()
    result = asyncio.run(
        CrawlService(_FetcherRegistry(), _ParserRegistry(), Validator()).crawl_one(
            target,
            (251,),
        )
    )
    assert not result.successful
    assert result.failures[0].code is ErrorCode.INTERNAL_ERROR
    assert "ValueError" in result.failures[0].detail


def test_linked_image_ocr_keeps_continuation_line() -> None:
    marker = "测试九肖"
    target = _source(
        parser="image_ocr",
        section_marker=marker,
        source_policy=(DocumentMethod.IMAGE_OCR.value,),
    )
    document = Document(
        label="image-ocr:1",
        url=target.url,
        text="251期 九肖\n鼠牛虎兔龙蛇马羊猴",
        method=DocumentMethod.IMAGE_OCR,
        metadata=(
            ("image_index", "1"),
            ("parent_url", target.url),
            ("anchor_line", marker),
            ("anchor_term", marker),
            ("data_marker_line", f"{marker} 九肖"),
            ("anchor_index", "4"),
            ("block_start", "4"),
            ("block_end", "6"),
        ),
    )

    parsed = ImageOcrParser().parse(target, (document,), (251,))
    verified = Validator().validate(target, parsed, (251,))
    assert verified.history.records[0].zodiac_text == "鼠牛虎兔龙蛇马羊猴"


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


def test_new_cycle_resets_numeric_issue_window_instead_of_dropping_issue_001() -> None:
    target = _source()
    previous = CacheSnapshot(
        latest_issue=365,
        issues=tuple(range(365, 355, -1)),
        sources=(CacheSource(target),),
        cycle="2026",
    )
    repository = _MemoryCacheRepository(previous)
    service = CacheSyncService(repository)

    from v2.domain.models import Evidence, History, Record, Result

    record = Record(
        1,
        tuple("鼠牛虎兔龙蛇马羊猴"),
        Evidence("test", "鼠牛虎兔龙蛇马羊猴", target.name, "test"),
    )
    result = Result.succeeded(target, (1,), History((record,), 1))
    snapshot = service.sync_single(
        (target,),
        (result,),
        1,
        cycle="2027",
    )

    assert snapshot.cycle == "2027"
    assert snapshot.issues == (1,)
    assert dict(snapshot.sources[0].records)[1] == "鼠牛虎兔龙蛇马羊猴"
