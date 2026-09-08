from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from v2.domain.identity import source_identity
from v2.domain.models import Result, Source
from v2.services.crawl import ProgressCallback
from v2.storage.reports import ReportRepository


class CrawlMany(Protocol):
    async def crawl_many(
        self,
        sources: tuple[Source, ...],
        issues: tuple[int, ...],
        *,
        concurrency: int,
        history_mode: bool = False,
        on_progress: ProgressCallback | None = None,
    ) -> tuple[Result, ...]: ...


class SyncSingle(Protocol):
    def sync_single(
        self,
        sources: tuple[Source, ...],
        results: tuple[Result, ...],
        issue: int,
    ) -> object: ...

    def sync_selected_single(
        self,
        sources: tuple[Source, ...],
        results: tuple[Result, ...],
        issue: int,
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class IssueRun:
    issue: int
    results: tuple[Result, ...]
    output_path: Path
    failure_path: Path
    success_count: int = 0
    total_count: int = 0
    cache_updated: bool = False
    cache_error: str = ""


@dataclass(frozen=True, slots=True)
class RangeRun:
    issues: tuple[IssueRun, ...]
    failure_summary_path: Path


class CrawlRunService:
    def __init__(
        self,
        crawl: CrawlMany,
        reports: ReportRepository,
        cache_sync: SyncSingle,
    ) -> None:
        self._crawl = crawl
        self._reports = reports
        self._cache_sync = cache_sync

    async def crawl(
        self,
        sources: tuple[Source, ...],
        issue: int,
        *,
        concurrency: int,
        on_progress: ProgressCallback | None = None,
    ) -> IssueRun:
        results = await self._crawl.crawl_many(
            sources,
            (issue,),
            concurrency=concurrency,
            on_progress=on_progress,
        )
        self._validate_batch(sources, results, issue)
        output_path, failure_path = self._reports.write_issue(issue, results)
        success_count = self._success_count(results)
        cache_updated = False
        cache_error = ""
        try:
            self._cache_sync.sync_single(sources, results, issue)
        except (OSError, RuntimeError, ValueError) as exc:
            cache_error = f"{type(exc).__name__}: {exc}"
        else:
            cache_updated = True
        return IssueRun(
            issue,
            results,
            output_path,
            failure_path,
            success_count=success_count,
            total_count=len(results),
            cache_updated=cache_updated,
            cache_error=cache_error,
        )

    async def repair(
        self,
        sources: tuple[Source, ...],
        issue: int,
        *,
        concurrency: int,
        on_progress: ProgressCallback | None = None,
    ) -> IssueRun:
        """Merge repaired sources without replacing the full issue reports."""
        results = await self._crawl.crawl_many(
            sources,
            (issue,),
            concurrency=concurrency,
            on_progress=on_progress,
        )
        self._validate_batch(sources, results, issue)
        output_path, failure_path = self._reports.merge_issue(issue, results)
        success_count = self._success_count(results)
        cache_updated = False
        cache_error = ""
        try:
            self._cache_sync.sync_selected_single(sources, results, issue)
        except (OSError, RuntimeError, ValueError) as exc:
            cache_error = f"{type(exc).__name__}: {exc}"
        else:
            cache_updated = True
        return IssueRun(
            issue,
            results,
            output_path,
            failure_path,
            success_count=success_count,
            total_count=len(results),
            cache_updated=cache_updated,
            cache_error=cache_error,
        )

    async def crawl_range(
        self,
        sources: tuple[Source, ...],
        issues: tuple[int, ...],
        *,
        concurrency: int,
    ) -> RangeRun:
        if not issues:
            raise ValueError("issues cannot be empty")
        batches: list[tuple[int, tuple[Result, ...]]] = []
        for issue in issues:
            results = await self._crawl.crawl_many(
                sources,
                (issue,),
                concurrency=concurrency,
            )
            self._validate_batch(sources, results, issue)
            batches.append((issue, results))

        runs: list[IssueRun] = []
        for issue, results in batches:
            output_path, failure_path = self._reports.write_issue(issue, results)
            runs.append(
                IssueRun(
                    issue,
                    results,
                    output_path,
                    failure_path,
                    success_count=self._success_count(results),
                    total_count=len(results),
                )
            )
        summary = self._reports.write_range_failures(tuple(batches))
        return RangeRun(tuple(runs), summary)

    @staticmethod
    def _success_count(results: tuple[Result, ...]) -> int:
        return sum(result.successful for result in results)

    @staticmethod
    def _validate_batch(
        sources: tuple[Source, ...],
        results: tuple[Result, ...],
        issue: int,
    ) -> None:
        expected = tuple(source_identity(source).key for source in sources)
        actual = tuple(source_identity(result.source).key for result in results)
        if expected != actual:
            raise ValueError("result identities or order do not match sources")
        if any(result.requested_issues != (issue,) for result in results):
            raise ValueError("result issue does not match requested issue")
        for result in results:
            records = result.history.records_for(issue)
            if result.successful and len(records) != 1:
                raise ValueError("successful result must contain one issue record")
