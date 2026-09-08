from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from v2.config.repository import SourceRepository
from v2.domain.errors import ErrorCode, Failure
from v2.domain.identity import source_identity
from v2.domain.models import (
    Document,
    DocumentMethod,
    Evidence,
    History,
    Position,
    Record,
    Result,
    Source,
)
from v2.fetchers.registry import FetchError, FetchRequest, FetcherRegistry
from v2.parsers.registry import ParserRegistry
from v2.services.cache_sync import (
    CacheSyncService,
    CacheWriteForbiddenError,
)
from v2.services.crawl import CrawlProgress, CrawlService
from v2.services.duplicate import (
    BaselineHistory,
    DuplicateChecker,
    DuplicateState,
)
from v2.services.onboarding import OnboardingService, OnboardingState
from v2.services.shadow import ShadowComparator
from v2.services.verification import VerificationService
from v2.storage.cache import CacheRepository
from v2.validator import Validator


def make_source(name: str, suffix: str = "a") -> Source:
    return Source(
        name=name,
        url=f"https://example.test/{suffix}",
        position=Position.BOTTOM,
        section_marker=name,
        fetcher="fake",
        parser="fake",
    )


def make_record(issue: int, zodiac: str, name: str) -> Record:
    return Record(
        issue=issue,
        zodiacs=tuple(zodiac),
        evidence=Evidence(
            method="test",
            source_line=f"{issue}期:{zodiac}",
            directory_anchor=name,
            document_label="test",
            metadata=(("document_index", "0"), ("line_index", str(issue))),
        ),
    )


def success_result(source: Source, records: tuple[Record, ...]) -> Result:
    issues = tuple(record.issue for record in records)
    current = max(issues)
    return Result.succeeded(
        source,
        issues,
        History(records=records, current_issue=current),
    )


class FakeFetcher:
    def __init__(
        self,
        documents: tuple[Document, ...] = (),
        failure: Failure | None = None,
    ) -> None:
        self.documents = documents
        self.failure = failure
        self.calls: list[tuple[str, tuple[int, ...]]] = []
        self.history_modes: list[bool] = []

    async def fetch(
        self,
        source: Source,
        request: FetchRequest,
    ) -> tuple[Document, ...]:
        self.calls.append((source.name, request.issues))
        self.history_modes.append(request.history_mode)
        if self.failure is not None:
            raise FetchError(self.failure)
        return self.documents


class FakeParser:
    def __init__(self, records_by_name: dict[str, tuple[Record, ...]]) -> None:
        self.records_by_name = records_by_name

    def parse(
        self,
        source: Source,
        documents: tuple[Document, ...],
        issues: tuple[int, ...],
    ) -> tuple[Record, ...]:
        return self.records_by_name[source.name]


class FakeCrawlService:
    def __init__(self, result: Result) -> None:
        self.result = result
        self.calls: list[tuple[str, tuple[int, ...], bool]] = []

    async def crawl_one(
        self,
        source: Source,
        issues: tuple[int, ...],
        *,
        history_mode: bool = False,
    ) -> Result:
        self.calls.append((source.name, issues, history_mode))
        return self.result


class CrawlServiceTests(unittest.IsolatedAsyncioTestCase):
    """A daily operator sees progress as each concurrent site finishes."""

    async def test_crawl_passes_history_mode_to_fetch_request(self) -> None:
        source = make_source("甲")
        document = Document(
            "test",
            source.url,
            "210期",
            DocumentMethod.STATIC_PAGE,
        )
        record = make_record(210, "鼠牛虎兔龙蛇马羊猴", source.name)
        fetcher = FakeFetcher((document,))
        fetchers = FetcherRegistry()
        fetchers.register("fake", fetcher)
        parsers = ParserRegistry()
        parsers.register("fake", FakeParser({source.name: (record,)}))

        result = await CrawlService(
            fetchers,
            parsers,
            Validator(),
        ).crawl_one(source, (210,), history_mode=True)

        self.assertTrue(result.successful)
        self.assertEqual(fetcher.history_modes, [True])

    async def test_unknown_fetcher_or_parser_is_a_config_failure(self) -> None:
        source = make_source("未知配置")
        service = CrawlService(
            FetcherRegistry(),
            ParserRegistry(),
            Validator(),
        )

        result = await service.crawl_one(source, (210,))

        self.assertFalse(result.successful)
        self.assertIs(result.failures[0].code, ErrorCode.CONFIG_INVALID)

    async def test_crawl_composes_fetch_parse_validate_without_writing(self) -> None:
        source = make_source("甲")
        document = Document(
            "test",
            source.url,
            "210期",
            DocumentMethod.STATIC_PAGE,
        )
        record = make_record(210, "鼠牛虎兔龙蛇马羊猴", source.name)
        fetchers = FetcherRegistry()
        fetchers.register("fake", FakeFetcher((document,)))
        parsers = ParserRegistry()
        parsers.register("fake", FakeParser({source.name: (record,)}))
        service = CrawlService(fetchers, parsers, Validator())

        result = await service.crawl_one(source, (210,))

        self.assertTrue(result.successful)
        self.assertEqual(result.history.records, (record,))

    async def test_crawl_converts_structured_failures_and_preserves_order(
        self,
    ) -> None:
        first = make_source("甲", "a")
        second = make_source("乙", "b")
        fetchers = FetcherRegistry()
        fetchers.register(
            "fake",
            FakeFetcher(failure=Failure(ErrorCode.FETCH_FAILED)),
        )
        parsers = ParserRegistry()
        parsers.register("fake", FakeParser({}))
        service = CrawlService(fetchers, parsers, Validator())

        results = await service.crawl_many(
            (first, second),
            (210,),
            concurrency=2,
        )

        self.assertEqual([result.source.name for result in results], ["甲", "乙"])
        self.assertTrue(
            all(
                result.failures[0].code is ErrorCode.FETCH_FAILED
                for result in results
            )
        )

    async def test_crawl_reports_completed_success_and_failure_counts(
        self,
    ) -> None:
        first = make_source("慢站", "slow")
        second = make_source("快站", "fast")
        success = success_result(
            second,
            (make_record(210, "鼠牛虎兔龙蛇马羊猴", second.name),),
        )
        failure = Result.failed(
            first,
            (210,),
            Failure(ErrorCode.ISSUE_MISSING),
        )
        service = CrawlService(FetcherRegistry(), ParserRegistry(), Validator())

        async def crawl_one(source: Source, *_args, **_kwargs) -> Result:
            if source is first:
                await asyncio.sleep(0.01)
                return failure
            return success

        service.crawl_one = AsyncMock(side_effect=crawl_one)
        updates: list[CrawlProgress] = []

        results = await service.crawl_many(
            (first, second),
            (210,),
            concurrency=2,
            on_progress=updates.append,
        )

        self.assertEqual([result.source for result in results], [first, second])
        self.assertEqual(
            [
                (
                    update.completed,
                    update.succeeded,
                    update.failed,
                    update.result.source.name,
                )
                for update in updates
            ],
            [(1, 1, 0, "快站"), (2, 1, 1, "慢站")],
        )


class DuplicateCheckerTests(unittest.TestCase):
    def test_duplicate_thresholds_use_concrete_issue_and_original_order(self) -> None:
        candidate_source = make_source("候选")
        baseline_source = make_source("基准", "baseline")
        values = {
            issue: "鼠牛虎兔龙蛇马羊猴"
            for issue in range(210, 200, -1)
        }
        candidate = History(
            records=tuple(
                make_record(issue, zodiac, candidate_source.name)
                for issue, zodiac in values.items()
            ),
            current_issue=210,
        )

        def decision_for(count: int):
            records = []
            for index, (issue, zodiac) in enumerate(values.items()):
                value = zodiac if index < count else "牛鼠虎兔龙蛇马羊猴"
                records.append(make_record(issue, value, baseline_source.name))
            return DuplicateChecker().compare(
                candidate,
                (
                    BaselineHistory(
                        source_identity(baseline_source).key,
                        baseline_source.name,
                        History(tuple(records), 210),
                    ),
                ),
                tuple(values),
            )

        self.assertEqual(decision_for(2).state, DuplicateState.CLEAR)
        self.assertEqual(decision_for(3).state, DuplicateState.MANUAL_REVIEW)
        self.assertEqual(decision_for(6).state, DuplicateState.DUPLICATE)

    def test_same_zodiac_set_in_different_order_is_not_a_match(self) -> None:
        candidate_source = make_source("候选")
        baseline_source = make_source("基准", "baseline")
        candidate = History(
            (make_record(210, "鼠牛虎兔龙蛇马羊猴", candidate_source.name),),
            210,
        )
        baseline = History(
            (make_record(210, "牛鼠虎兔龙蛇马羊猴", baseline_source.name),),
            210,
        )

        decision = DuplicateChecker().compare(
            candidate,
            (
                BaselineHistory(
                    source_identity(baseline_source).key,
                    baseline_source.name,
                    baseline,
                ),
            ),
            (210,),
        )

        self.assertEqual(decision.matches, ())


class CacheSyncTests(unittest.TestCase):
    def test_single_issue_sync_records_failure_without_old_value(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "cache.json"
            repository = CacheRepository(path)
            service = CacheSyncService(repository)
            first = make_source("甲", "a")
            second = make_source("乙", "b")
            first_success = success_result(
                first,
                (make_record(210, "鼠牛虎兔龙蛇马羊猴", first.name),),
            )
            second_failure = Result.failed(
                second,
                (210,),
                Failure(ErrorCode.ISSUE_MISSING),
            )

            snapshot = service.sync_single(
                (first, second),
                (first_success, second_failure),
                210,
            )

            self.assertEqual(
                [entry.source.name for entry in snapshot.sources],
                ["甲", "乙"],
            )
            self.assertEqual(dict(snapshot.sources[0].records)[210], "鼠牛虎兔龙蛇马羊猴")
            self.assertEqual(
                dict(snapshot.sources[1].errors)[210],
                ErrorCode.ISSUE_MISSING,
            )

            first_failure = Result.failed(
                first,
                (210,),
                Failure(ErrorCode.FETCH_FAILED),
            )
            snapshot = service.sync_single(
                (first, second),
                (first_failure, second_failure),
                210,
            )
            self.assertEqual(
                dict(snapshot.sources[0].records),
                {},
            )
            self.assertEqual(
                dict(snapshot.sources[0].errors)[210],
                ErrorCode.FETCH_FAILED,
            )

    def test_sync_single_persists_live_value_even_when_cache_differs(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "cache.json"
            repository = CacheRepository(path)
            service = CacheSyncService(repository)
            source = make_source("田乘风破")
            original = success_result(
                source,
                (make_record(211, "兔蛇虎猴羊牛猪鸡鼠", source.name),),
            )
            changed = success_result(
                source,
                (make_record(211, "狗虎龙马牛蛇鼠羊猪", source.name),),
            )
            service.sync_single((source,), (original,), 211)

            snapshot = service.sync_single((source,), (changed,), 211)
            self.assertEqual(
                dict(snapshot.sources[0].records)[211],
                "狗虎龙马牛蛇鼠羊猪",
            )
            self.assertEqual(dict(snapshot.sources[0].errors), {})

    def test_range_mode_never_writes_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "cache.json"
            service = CacheSyncService(CacheRepository(path))

            with self.assertRaises(CacheWriteForbiddenError):
                service.sync_range()

            self.assertFalse(path.exists())

    def test_incomplete_or_reordered_batch_is_rejected_before_cache_write(
        self,
    ) -> None:
        first = make_source("甲", "a")
        second = make_source("乙", "b")
        first_result = success_result(
            first,
            (make_record(210, "鼠牛虎兔龙蛇马羊猴", first.name),),
        )
        second_result = success_result(
            second,
            (make_record(210, "牛鼠虎兔龙蛇马羊猴", second.name),),
        )

        for results in ((first_result,), (second_result, first_result)):
            with self.subTest(results=results):
                with tempfile.TemporaryDirectory() as temp_dir:
                    path = Path(temp_dir) / "cache.json"
                    service = CacheSyncService(CacheRepository(path))
                    with self.assertRaises(ValueError):
                        service.sync_single((first, second), results, 210)
                    self.assertFalse(path.exists())

    def test_cache_round_trip_prunes_to_ten_issues(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "cache.json"
            repository = CacheRepository(path)
            service = CacheSyncService(repository)
            source = make_source("甲", "a")

            for issue in range(201, 212):
                result = success_result(
                    source,
                    (
                        make_record(
                            issue,
                            "鼠牛虎兔龙蛇马羊猴",
                            source.name,
                        ),
                    ),
                )
                service.sync_single((source,), (result,), issue)

            snapshot = repository.load()
            self.assertEqual(snapshot.issues, tuple(range(211, 201, -1)))
            self.assertEqual(
                tuple(dict(snapshot.sources[0].records)),
                tuple(range(211, 201, -1)),
            )


class OnboardingAndVerificationTests(unittest.IsolatedAsyncioTestCase):
    async def test_onboarding_requires_exactly_ten_distinct_issues(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repository = SourceRepository(
                root / "sources.json",
                root / "archived_sources.json",
            )
            repository.initialize()
            candidate = make_source("候选")
            crawl = FakeCrawlService(
                Result.failed(
                    candidate,
                    (210,),
                    Failure(ErrorCode.ISSUE_MISSING),
                )
            )
            service = OnboardingService(
                crawl,
                DuplicateChecker(),
                repository,
            )

            for issues in (
                tuple(range(210, 201, -1)),
                (210,) * 10,
            ):
                with self.subTest(issues=issues):
                    with self.assertRaises(ValueError):
                        await service.onboard(candidate, (), issues)

            self.assertEqual(crawl.calls, [])
            self.assertEqual(repository.load_active(), ())

    async def test_onboarding_rejects_incomplete_success_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repository = SourceRepository(
                root / "sources.json",
                root / "archived_sources.json",
            )
            repository.initialize()
            candidate = make_source("候选")
            incomplete = tuple(
                make_record(
                    issue,
                    "鼠牛虎兔龙蛇马羊猴",
                    candidate.name,
                )
                for issue in range(210, 201, -1)
            )
            service = OnboardingService(
                FakeCrawlService(success_result(candidate, incomplete)),
                DuplicateChecker(),
                repository,
            )

            with self.assertRaises(ValueError):
                await service.onboard(
                    candidate,
                    (),
                    tuple(range(210, 200, -1)),
                )

            self.assertEqual(repository.load_active(), ())

    async def test_onboarding_writes_only_after_clear_duplicate_decision(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repository = SourceRepository(
                root / "sources.json",
                root / "archived_sources.json",
            )
            repository.initialize()
            candidate = make_source("候选")
            records = tuple(
                make_record(
                    issue,
                    "鼠牛虎兔龙蛇马羊猴",
                    candidate.name,
                )
                for issue in range(210, 200, -1)
            )
            crawl = FakeCrawlService(success_result(candidate, records))
            service = OnboardingService(
                crawl,
                DuplicateChecker(),
                repository,
            )

            decision = await service.onboard(
                candidate,
                (),
                tuple(range(210, 200, -1)),
            )

            self.assertEqual(decision.state, OnboardingState.ACCEPTED)
            self.assertEqual(repository.load_active(), (candidate,))
            self.assertTrue(crawl.calls[0][2])

    async def test_duplicate_candidate_is_rejected_without_config_write(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repository = SourceRepository(
                root / "sources.json",
                root / "archived_sources.json",
            )
            repository.initialize()
            candidate = make_source("候选")
            baseline_source = make_source("基准", "baseline")
            records = tuple(
                make_record(
                    issue,
                    "鼠牛虎兔龙蛇马羊猴",
                    candidate.name,
                )
                for issue in range(210, 200, -1)
            )
            baseline_records = tuple(
                make_record(
                    issue,
                    "鼠牛虎兔龙蛇马羊猴",
                    baseline_source.name,
                )
                for issue in range(210, 200, -1)
            )
            service = OnboardingService(
                FakeCrawlService(success_result(candidate, records)),
                DuplicateChecker(),
                repository,
            )

            decision = await service.onboard(
                candidate,
                (
                    BaselineHistory(
                        source_identity(baseline_source).key,
                        baseline_source.name,
                        History(baseline_records, 210),
                    ),
                ),
                tuple(range(210, 200, -1)),
            )

            self.assertEqual(decision.state, OnboardingState.REJECTED)
            self.assertEqual(repository.load_active(), ())

    async def test_manual_review_candidate_is_not_written(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repository = SourceRepository(
                root / "sources.json",
                root / "archived_sources.json",
            )
            repository.initialize()
            candidate = make_source("候选")
            baseline_source = make_source("基准", "baseline")
            candidate_records = tuple(
                make_record(
                    issue,
                    "鼠牛虎兔龙蛇马羊猴",
                    candidate.name,
                )
                for issue in range(210, 200, -1)
            )
            baseline_records = tuple(
                make_record(
                    issue,
                    (
                        "鼠牛虎兔龙蛇马羊猴"
                        if issue >= 208
                        else "牛鼠虎兔龙蛇马羊猴"
                    ),
                    baseline_source.name,
                )
                for issue in range(210, 200, -1)
            )
            service = OnboardingService(
                FakeCrawlService(success_result(candidate, candidate_records)),
                DuplicateChecker(),
                repository,
            )

            decision = await service.onboard(
                candidate,
                (
                    BaselineHistory(
                        source_identity(baseline_source).key,
                        baseline_source.name,
                        History(baseline_records, 210),
                    ),
                ),
                tuple(range(210, 200, -1)),
            )

            self.assertEqual(decision.state, OnboardingState.MANUAL_REVIEW)
            self.assertEqual(repository.load_active(), ())

    async def test_verification_returns_result_without_storage_dependencies(
        self,
    ) -> None:
        source = make_source("验证站")
        result = Result.failed(
            source,
            (210,),
            Failure(ErrorCode.ANCHOR_MISSING),
        )
        service = VerificationService(FakeCrawlService(result))

        verified = await service.verify(source, (210,))

        self.assertIs(verified, result)


class ShadowComparatorTests(unittest.TestCase):
    def test_shadow_diff_aligns_by_identity_and_issue(self) -> None:
        source = make_source("甲")
        expected = success_result(
            source,
            (make_record(210, "鼠牛虎兔龙蛇马羊猴", source.name),),
        )
        actual = success_result(
            source,
            (make_record(210, "牛鼠虎兔龙蛇马羊猴", source.name),),
        )

        report = ShadowComparator().compare((expected,), (actual,), (210,))

        self.assertEqual(len(report.differences), 1)
        self.assertEqual(report.differences[0].issue, 210)


if __name__ == "__main__":
    unittest.main()
