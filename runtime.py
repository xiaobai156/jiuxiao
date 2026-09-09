from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from playwright.async_api import async_playwright

from v2.config.main_list import MainListCatalog
from v2.config.repository import SourceRepository
from v2.domain.identity import normalize_url, source_identity
from v2.domain.models import Position, Source
from v2.fetchers.browser_page import (
    BrowserPageFetcher,
    PlaywrightBrowserClient,
    PlaywrightHttpClient,
)
from v2.fetchers.dynamic_article import DynamicArticleFetcher
from v2.fetchers.list_detail import (
    ListDetailCurrentFetcher,
    ListDetailFetcher,
    ListDetailTopThreeFetcher,
)
from v2.fetchers.liuiuqu import LiuiuquFetcher
from v2.fetchers.narrow_image_browser import NarrowImagePlaywrightBrowserClient
from v2.fetchers.registry import FetcherRegistry
from v2.fetchers.static_page import StaticPageFetcher
from v2.parsers.factory import build_parser_registry
from v2.services.cache_sync import CacheSyncService
from v2.services.crawl import CrawlService, ProgressCallback
from v2.services.run_modes import CrawlRunService, IssueRun, RangeRun
from v2.services.shadow import (
    ShadowRun,
    ShadowRunService,
    SubprocessSnapshotRunner,
)
from v2.services.switching import (
    PreflightReport,
    SwitchPreflightService,
    SwitchService,
)
from v2.storage.cache import CacheRepository
from v2.storage.reports import ReportRepository
from v2.storage.switching import BatSwitchStorage
from v2.validator import Validator


def project_root() -> Path:
    package = Path(__file__).resolve().parent
    legacy_root = package.parent
    if package.name.casefold() == "v2" and (legacy_root / "crawler.py").is_file():
        return legacy_root
    return package


def _v2_root(root: Path) -> Path:
    root = Path(root).resolve()
    nested = root / "v2"
    if any(
        path.is_file()
        for path in (
            nested / "__main__.py",
            nested / "config" / "sources.json",
            nested / "baseline" / "manifest.json",
        )
    ):
        return nested
    return root


def _main_list_key(source: Source) -> tuple[str, str, str]:
    return (
        source.name.strip(),
        source.section_marker.strip(),
        normalize_url(source.url),
    )


def _configured_main_list_keys(directions_path: Path) -> set[tuple[str, str, str]]:
    document = json.loads(Path(directions_path).read_text(encoding="utf-8"))
    excluded = {
        str(value).strip() for value in document.get("excluded_titles", ())
    }
    return {
        (
            str(item["name"]).strip(),
            str(item["title"]).strip(),
            normalize_url(str(item["url"])),
        )
        for item in document.get("sources", ())
        if isinstance(item, dict)
        and str(item.get("title", "")).strip() not in excluded
    }


def _validate_main_list_completeness(
    v2_root: Path,
    listed: tuple[Source, ...],
) -> None:
    configured = _configured_main_list_keys(
        v2_root / "config" / "main_list_directions.json"
    )
    if not configured:
        return
    previous = CacheRepository(
        v2_root / "cache" / "recent_10_cache.json"
    ).load()
    if not previous.sources:
        return
    expected = {
        key
        for cached in previous.sources
        if (key := _main_list_key(cached.source)) in configured
    }
    actual = {_main_list_key(source) for source in listed}
    missing = expected - actual
    if missing:
        names = ", ".join(
            f"{name}[{section}]"
            for name, section, _url in sorted(missing)
        )
        raise ValueError(
            f"main list incomplete; missing previously active sources: {names}"
        )


def _source_repository(root: Path) -> SourceRepository:
    v2_root = _v2_root(root)
    return SourceRepository(
        v2_root / "config" / "sources.json",
        v2_root / "config" / "archived_sources.json",
    )


def _fetchers(context, browser: PlaywrightBrowserClient) -> FetcherRegistry:
    http = PlaywrightHttpClient(context)
    registry = FetcherRegistry()
    registry.register("static_page", StaticPageFetcher(http))
    registry.register("dynamic_article", DynamicArticleFetcher(http, browser))
    registry.register("browser_page", BrowserPageFetcher(browser))
    registry.register(
        "browser_page_narrow_image",
        BrowserPageFetcher(
            NarrowImagePlaywrightBrowserClient(
                browser.context,
                ocr_reader=browser.ocr_reader,
            )
        ),
    )
    registry.register("list_detail", ListDetailFetcher(browser))
    registry.register("list_detail_top3", ListDetailTopThreeFetcher(browser))
    registry.register("list_detail_current", ListDetailCurrentFetcher(browser))
    registry.register("liuiuqu", LiuiuquFetcher(http))
    return registry


def _reports(root: Path) -> ReportRepository:
    v2_root = _v2_root(root)
    parent = v2_root.parent
    return ReportRepository(
        parent / "七类数据统一归纳",
        failure_dir=parent / "七类数据统一归纳失败",
        success_filename="{issue}期-生肖.txt",
        failure_filename="{issue}期-生肖-失败.txt",
        range_failure_dir=v2_root / "outputs",
        range_failure_filename="{start_issue}-{end_issue}-all-failures.txt",
    )


def _cycle_label(cycle: str | None) -> str:
    normalized = str(cycle).strip() if cycle is not None else str(date.today().year)
    if not normalized or len(normalized) > 64 or any(
        character.isspace() for character in normalized
    ):
        raise ValueError("cycle must be a non-empty label without whitespace")
    return normalized


@asynccontextmanager
async def _browser_clients() -> AsyncIterator[
    tuple[object, PlaywrightBrowserClient]
]:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            context = await browser.new_context(ignore_https_errors=False)
            try:
                yield context, PlaywrightBrowserClient(context)
            finally:
                await context.close()
        finally:
            await browser.close()


def liuiuqu_source() -> Source:
    return Source(
        name="六爱趣",
        url="https://kef5b.6hgsiyutapp1.com/index/index/videoExplain.html",
        api_url="https://kef5b.6hgsiyutapp1.com/index/index/getziliaoExplain",
        position=Position.TOP,
        section_marker="六爱趣",
        fetcher="liuiuqu",
        parser="liuiuqu",
    )


async def daily_sources(
    root: Path,
    browser: PlaywrightBrowserClient,
    repository: SourceRepository | None = None,
) -> tuple[Source, ...]:
    """Build the configured daily catalog without importing another project."""
    root = Path(root).resolve()
    v2_root = _v2_root(root)
    fixed = (repository or _source_repository(root)).load_active()
    listed = await MainListCatalog(
        browser,
        v2_root / "config" / "main_list_directions.json",
    ).load()
    _validate_main_list_completeness(v2_root, listed)
    sources = (*listed, liuiuqu_source(), *fixed)
    names: set[str] = set()
    identities: set[str] = set()
    for source in sources:
        identity = source_identity(source).key
        if source.name in names or identity in identities:
            raise ValueError(f"daily source duplicate: {source.name}")
        names.add(source.name)
        identities.add(identity)
    return sources


async def run_crawl(
    root: Path,
    issue: int,
    *,
    concurrency: int,
    on_progress: ProgressCallback | None = None,
    cycle: str | None = None,
) -> IssueRun:
    root = Path(root).resolve()
    v2_root = _v2_root(root)
    cycle_label = _cycle_label(cycle)
    async with _browser_clients() as (context, browser_client):
        sources = await daily_sources(root, browser_client)
        service = CrawlRunService(
            CrawlService(
                _fetchers(context, browser_client),
                build_parser_registry(),
                Validator(),
            ),
            _reports(v2_root),
            CacheSyncService(
                CacheRepository(v2_root / "cache" / "recent_10_cache.json")
            ),
        )
        if on_progress is None:
            return await service.crawl(
                sources,
                issue,
                concurrency=concurrency,
                cycle=cycle_label,
            )
        return await service.crawl(
            sources,
            issue,
            concurrency=concurrency,
            on_progress=on_progress,
            cycle=cycle_label,
        )


async def run_crawl_range(
    root: Path,
    start_issue: int,
    end_issue: int,
    *,
    concurrency: int,
) -> RangeRun:
    root = Path(root).resolve()
    v2_root = _v2_root(root)
    issues = tuple(range(start_issue, end_issue - 1, -1))
    async with _browser_clients() as (context, browser_client):
        sources = await daily_sources(root, browser_client)
        service = CrawlRunService(
            CrawlService(
                _fetchers(context, browser_client),
                build_parser_registry(),
                Validator(),
            ),
            _reports(v2_root),
            CacheSyncService(
                CacheRepository(v2_root / "cache" / "recent_10_cache.json")
            ),
        )
        return await service.crawl_range(
            sources,
            issues,
            concurrency=concurrency,
        )


async def run_retry_failed(
    root: Path,
    issue: int,
    *,
    concurrency: int,
    cycle: str | None = None,
) -> RangeRun:
    root = Path(root).resolve()
    v2_root = _v2_root(root)
    cycle_label = _cycle_label(cycle)
    async with _browser_clients() as (context, browser_client):
        all_sources = await daily_sources(root, browser_client)
        reports = _reports(v2_root)
        sources = reports.failed_sources(issue, all_sources)
        if not sources:
            raise ValueError(f"{issue}期失败TXT没有可重抓站点")
        service = CrawlRunService(
            CrawlService(
                _fetchers(context, browser_client),
                build_parser_registry(),
                Validator(),
            ),
            reports,
            CacheSyncService(
                CacheRepository(v2_root / "cache" / "recent_10_cache.json")
            ),
        )
        run = await service.repair(
            sources,
            issue,
            concurrency=concurrency,
            cycle=cycle_label,
        )
        return RangeRun(
            (run,),
            reports.range_failure_dir / "retry-failed-complete.txt",
        )


def _v1_manifest_paths(root: Path) -> tuple[Path, ...]:
    root = Path(root).resolve()
    v2_root = _v2_root(root)
    manifest = json.loads(
        (v2_root / "baseline" / "manifest.json").read_text(encoding="utf-8")
    )
    paths: list[Path] = []
    for item in manifest["v1_files"]:
        path = (root / str(item["path"])).resolve()
        if root not in path.parents:
            raise ValueError("V1 manifest path escaped project root")
        paths.append(path)
    return tuple(paths)


async def run_shadow(
    root: Path,
    issue: int,
    *,
    concurrency: int,
) -> ShadowRun:
    root = Path(root).resolve()
    v2_root = _v2_root(root)
    return await ShadowRunService(
        SubprocessSnapshotRunner(root, concurrency=concurrency),
        v2_root / "reviews",
        readonly_paths=_v1_manifest_paths(root),
    ).run(issue)


def run_preflight(root: Path) -> PreflightReport:
    return SwitchPreflightService(Path(root)).check()


def run_switch(root: Path) -> PreflightReport:
    root = Path(root).resolve()
    return SwitchService(
        SwitchPreflightService(root),
        BatSwitchStorage(root),
    ).switch()


def run_rollback(root: Path) -> None:
    BatSwitchStorage(Path(root).resolve()).rollback()
