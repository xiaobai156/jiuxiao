from __future__ import annotations

import json
from pathlib import Path

from playwright.async_api import async_playwright

from v2.config.main_list import MainListCatalog
from v2.config.repository import SourceRepository
from v2.domain.identity import source_identity
from v2.domain.models import Position, Source
from v2.fetchers.browser_page import (
    BrowserPageFetcher,
    PlaywrightBrowserClient,
    PlaywrightHttpClient,
)
from v2.fetchers.dynamic_article import DynamicArticleFetcher
from v2.fetchers.list_detail import (
    ListDetailFetcher,
    ListDetailTopThreeFetcher,
)
from v2.fetchers.liuiuqu import LiuiuquFetcher
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
    if package.name.casefold() == "v2" and (
        legacy_root / "crawler.py"
    ).is_file():
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
    registry.register(
        "dynamic_article",
        DynamicArticleFetcher(http, browser),
    )
    registry.register("browser_page", BrowserPageFetcher(browser))
    registry.register("list_detail", ListDetailFetcher(browser))
    registry.register(
        "list_detail_top3",
        ListDetailTopThreeFetcher(browser),
    )
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
    )


def liuiuqu_source() -> Source:
    return Source(
        name="六爱趣",
        url="https://kef5b.6hgsiyutapp1.com/index/index/videoExplain.html",
        api_url=(
            "https://kef5b.6hgsiyutapp1.com/index/index/getziliaoExplain"
        ),
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
    """Build the same 353-source daily catalog as V1 without importing V1."""
    root = Path(root).resolve()
    v2_root = _v2_root(root)
    fixed = (repository or _source_repository(root)).load_active()
    listed = await MainListCatalog(
        browser,
        v2_root / "config" / "main_list_directions.json",
    ).load()
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
) -> IssueRun:
    root = Path(root).resolve()
    v2_root = _v2_root(root)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(ignore_https_errors=False)
        try:
            browser_client = PlaywrightBrowserClient(context)
            sources = await daily_sources(root, browser_client)
            service = CrawlRunService(
                CrawlService(
                    _fetchers(context, browser_client),
                    build_parser_registry(),
                    Validator(),
                ),
                _reports(v2_root),
                CacheSyncService(
                    CacheRepository(
                        v2_root / "cache" / "recent_10_cache.json"
                    )
                ),
            )
            if on_progress is None:
                return await service.crawl(
                    sources,
                    issue,
                    concurrency=concurrency,
                )
            return await service.crawl(
                sources,
                issue,
                concurrency=concurrency,
                on_progress=on_progress,
            )
        finally:
            await context.close()
            await browser.close()


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
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(ignore_https_errors=False)
        try:
            browser_client = PlaywrightBrowserClient(context)
            sources = await daily_sources(root, browser_client)
            service = CrawlRunService(
                CrawlService(
                    _fetchers(context, browser_client),
                    build_parser_registry(),
                    Validator(),
                ),
                _reports(v2_root),
                CacheSyncService(
                    CacheRepository(
                        v2_root / "cache" / "recent_10_cache.json"
                    )
                ),
            )
            return await service.crawl_range(
                sources,
                issues,
                concurrency=concurrency,
            )
        finally:
            await context.close()
            await browser.close()


def _v1_manifest_paths(root: Path) -> tuple[Path, ...]:
    root = Path(root).resolve()
    v2_root = _v2_root(root)
    manifest = json.loads(
        (v2_root / "baseline" / "manifest.json").read_text(
            encoding="utf-8"
        )
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
