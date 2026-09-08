from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from v2.cli import CommandHandlers, async_main
from v2.domain.errors import ErrorCode, Failure
from v2.domain.models import Evidence, History, Position, Record, Result, Source
from v2.services.cache_sync import CacheSyncService
from v2.services.run_modes import CrawlRunService
from v2.storage.cache import CacheRepository
from v2.storage.reports import ReportRepository


def make_source(name: str, suffix: str) -> Source:
    return Source(
        name=name,
        url=f"https://example.test/{suffix}",
        position=Position.BOTTOM,
        section_marker=name,
        fetcher="fake",
        parser="fake",
    )


def make_result(source: Source, issue: int, *, successful: bool) -> Result:
    if not successful:
        return Result.failed(
            source,
            (issue,),
            Failure(
                ErrorCode.ISSUE_MISSING,
                context=(("issue", str(issue)),),
            ),
        )
    record = Record(
        issue=issue,
        zodiacs=tuple("鼠牛虎兔龙蛇马羊猴"),
        evidence=Evidence(
            method="test",
            source_line=f"{issue}期",
            directory_anchor=source.name,
            document_label="test",
        ),
    )
    return Result.succeeded(
        source,
        (issue,),
        History((record,), issue),
    )


class FakeCrawlMany:
    def __init__(self, results_by_issue: dict[int, tuple[Result, ...]]) -> None:
        self.results_by_issue = results_by_issue
        self.calls: list[tuple[tuple[str, ...], tuple[int, ...], int]] = []
        self.progress_callbacks: list[object] = []

    async def crawl_many(
        self,
        sources: tuple[Source, ...],
        issues: tuple[int, ...],
        *,
        concurrency: int,
        history_mode: bool = False,
        on_progress=None,
    ) -> tuple[Result, ...]:
        self.calls.append(
            (tuple(source.name for source in sources), issues, concurrency)
        )
        self.progress_callbacks.append(on_progress)
        return self.results_by_issue[issues[0]]


class RecordingCacheSync:
    def __init__(self) -> None:
        self.calls: list[tuple[int, tuple[str, ...]]] = []

    def sync_single(
        self,
        sources: tuple[Source, ...],
        results: tuple[Result, ...],
        issue: int,
    ) -> object:
        self.calls.append((issue, tuple(result.source.name for result in results)))
        return object()


class RunModeTests(unittest.IsolatedAsyncioTestCase):
    async def test_cached_issue_difference_does_not_override_live_success(
        self,
    ) -> None:
        source = make_source("田乘风破", "tian")
        original = make_result(source, 211, successful=True)
        changed_record = Record(
            issue=211,
            zodiacs=tuple("狗虎龙马牛蛇鼠羊猪"),
            evidence=original.history.records[0].evidence,
        )
        changed = Result.succeeded(
            source,
            (211,),
            History((changed_record,), 211),
        )
        crawl = FakeCrawlMany({211: (changed,)})
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cache = CacheSyncService(CacheRepository(root / "cache.json"))
            cache.sync_single((source,), (original,), 211)
            service = CrawlRunService(crawl, ReportRepository(root), cache)

            run = await service.crawl((source,), 211, concurrency=1)

            self.assertTrue(run.results[0].successful)
            self.assertEqual(
                run.output_path.read_text(encoding="utf-8"),
                "狗虎龙马牛蛇鼠羊猪 田乘风破\n",
            )
            self.assertEqual(run.failure_path.read_text(encoding="utf-8"), "")
            snapshot = CacheRepository(root / "cache.json").load()
            self.assertEqual(
                dict(snapshot.sources[0].records)[211],
                "狗虎龙马牛蛇鼠羊猪",
            )

    async def test_single_crawl_validates_batch_then_writes_reports_without_cache_at_low_success_rate(
        self,
    ) -> None:
        first = make_source("甲", "a")
        second = make_source("乙", "b")
        results = (
            make_result(first, 210, successful=True),
            make_result(second, 210, successful=False),
        )
        crawl = FakeCrawlMany({210: results})
        cache = RecordingCacheSync()
        with tempfile.TemporaryDirectory() as temp_dir:
            reports = ReportRepository(Path(temp_dir))
            service = CrawlRunService(crawl, reports, cache)

            run = await service.crawl(
                (first, second),
                210,
                concurrency=2,
            )

            self.assertEqual(cache.calls, [])
            self.assertEqual(
                run.output_path.read_text(encoding="utf-8"),
                "鼠牛虎兔龙蛇马羊猴 甲\n",
            )
            failure_text = run.failure_path.read_text(encoding="utf-8")
            self.assertIn(
                "失败 乙 https://example.test/b 方向: bottom 期数: 210 "
                "阶段: 指定期数校验 原因: 没有找到目标期记录",
                failure_text,
            )

    async def test_cache_requires_strictly_more_than_85_percent_success(
        self,
    ) -> None:
        for successful_count, should_sync in ((17, False), (18, True)):
            with self.subTest(successful_count=successful_count):
                sources = tuple(
                    make_source(f"站点{index}", str(index))
                    for index in range(20)
                )
                results = tuple(
                    make_result(
                        source,
                        210,
                        successful=index < successful_count,
                    )
                    for index, source in enumerate(sources)
                )
                crawl = FakeCrawlMany({210: results})
                cache = RecordingCacheSync()
                with tempfile.TemporaryDirectory() as temp_dir:
                    service = CrawlRunService(
                        crawl,
                        ReportRepository(Path(temp_dir)),
                        cache,
                    )

                    await service.crawl(sources, 210, concurrency=20)

                expected = (
                    [(210, tuple(source.name for source in sources))]
                    if should_sync
                    else []
                )
                self.assertEqual(cache.calls, expected)

    async def test_invalid_batch_fails_before_any_formal_write(self) -> None:
        first = make_source("甲", "a")
        second = make_source("乙", "b")
        crawl = FakeCrawlMany(
            {210: (make_result(second, 210, successful=True),)}
        )
        cache = RecordingCacheSync()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = CrawlRunService(crawl, ReportRepository(root), cache)

            with self.assertRaises(ValueError):
                await service.crawl((first, second), 210, concurrency=2)

            self.assertEqual(cache.calls, [])
            self.assertEqual(tuple(root.iterdir()), ())

    async def test_single_crawl_forwards_progress_callback(self) -> None:
        source = make_source("甲", "a")
        crawl = FakeCrawlMany(
            {210: (make_result(source, 210, successful=True),)}
        )
        progress = object()
        with tempfile.TemporaryDirectory() as temp_dir:
            service = CrawlRunService(
                crawl,
                ReportRepository(Path(temp_dir)),
                RecordingCacheSync(),
            )

            await service.crawl(
                (source,),
                210,
                concurrency=1,
                on_progress=progress,
            )

        self.assertEqual(crawl.progress_callbacks, [progress])

    async def test_range_writes_each_issue_and_combined_failures_without_cache(
        self,
    ) -> None:
        first = make_source("甲", "a")
        second = make_source("乙", "b")
        crawl = FakeCrawlMany(
            {
                210: (
                    make_result(first, 210, successful=True),
                    make_result(second, 210, successful=False),
                ),
                209: (
                    make_result(first, 209, successful=True),
                    make_result(second, 209, successful=True),
                ),
            }
        )
        cache = RecordingCacheSync()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = CrawlRunService(crawl, ReportRepository(root), cache)

            run = await service.crawl_range(
                (first, second),
                (210, 209),
                concurrency=2,
            )

            self.assertEqual(cache.calls, [])
            self.assertEqual([item.issue for item in run.issues], [210, 209])
            self.assertEqual(
                [call[1] for call in crawl.calls],
                [(210,), (209,)],
            )
            summary = run.failure_summary_path.read_text(encoding="utf-8")
            self.assertIn("210期", summary)
            self.assertIn(
                "失败 乙 https://example.test/b 方向: bottom 期数: 210 "
                "阶段: 指定期数校验 原因: 没有找到目标期记录",
                summary,
            )
            self.assertTrue((root / "210.txt").exists())
            self.assertTrue((root / "209.txt").exists())


class FakeCliApplication:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    async def crawl(self, issue: int, concurrency: int) -> None:
        self.calls.append(("crawl", issue, concurrency))

    async def crawl_range(
        self,
        start_issue: int,
        end_issue: int,
        concurrency: int,
    ) -> None:
        self.calls.append(("crawl-range", start_issue, end_issue, concurrency))

    async def onboard(self, candidate_path: Path) -> None:
        self.calls.append(("onboard", candidate_path))

    async def verify(self, source_key: str, issue: int) -> None:
        self.calls.append(("verify", source_key, issue))

    async def shadow(self, issue: int) -> None:
        self.calls.append(("shadow", issue))

    async def duplicate(self, candidate_path: Path) -> None:
        self.calls.append(("duplicate", candidate_path))


class CliTests(unittest.IsolatedAsyncioTestCase):
    async def test_cli_dispatches_every_mode_without_business_logic(self) -> None:
        app = FakeCliApplication()
        handlers = CommandHandlers.from_application(app)
        cases = (
            (["crawl", "210", "--concurrency", "3"], ("crawl", 210, 3)),
            (
                ["crawl-range", "210", "201", "--concurrency", "4"],
                ("crawl-range", 210, 201, 4),
            ),
            (["onboard", "candidate.json"], ("onboard", Path("candidate.json"))),
            (["verify", "identity", "210"], ("verify", "identity", 210)),
            (["shadow", "210"], ("shadow", 210)),
            (
                ["duplicate", "candidate-cache.json"],
                ("duplicate", Path("candidate-cache.json")),
            ),
        )

        for arguments, expected in cases:
            with self.subTest(arguments=arguments):
                app.calls.clear()
                exit_code = await async_main(arguments, handlers)
                self.assertEqual(exit_code, 0)
                self.assertEqual(app.calls, [expected])

    async def test_cli_rejects_invalid_range_before_dispatch(self) -> None:
        app = FakeCliApplication()
        handlers = CommandHandlers.from_application(app)

        with self.assertRaises(SystemExit):
            await async_main(["crawl-range", "201", "210"], handlers)

        self.assertEqual(app.calls, [])


if __name__ == "__main__":
    unittest.main()
