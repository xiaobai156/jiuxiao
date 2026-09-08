from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

from v2.config.repository import SourceRepository
from v2.domain.models import Document, DocumentMethod, Source
from v2.fetchers.browser_page import (
    BrowserPageFetcher,
    PlaywrightBrowserClient,
    PlaywrightHttpClient,
)
from v2.fetchers.dynamic_article import DynamicArticleFetcher
from v2.fetchers.list_detail import ListDetailFetcher
from v2.fetchers.registry import FetchRequest, FetcherRegistry
from v2.fetchers.static_page import StaticPageFetcher
from v2.parsers.factory import build_parser_registry
from v2.services.golden import snapshot_from_v2
from v2.services.history import HistoricalAuditService
from v2.storage.golden import GoldenRepository
from v2.validator import Validator


ISSUES = tuple(range(210, 200, -1))


def _ocr_documents_from_cache(
    source: Source,
    cached: dict[str, Any],
    issues: tuple[int, ...],
) -> tuple[Document, ...]:
    records = cached.get("records", {})
    audit = cached.get("audit", {})
    lines: list[str] = []
    for issue in reversed(issues):
        zodiac = records.get(str(issue), records.get(issue, ""))
        if not zodiac:
            continue
        evidence = audit.get(str(issue), audit.get(issue, {}))
        source_line = (
            evidence.get("source_line", "")
            if isinstance(evidence, dict)
            else ""
        )
        lines.append(source_line or f"{issue}期：{zodiac}")
    return (
        Document(
            label="golden-ocr-anchor",
            url=source.url,
            text=source.section_marker or source.name,
            method=DocumentMethod.BROWSER_DOM,
        ),
        Document(
            label="golden-ocr-cache",
            url=source.url,
            text="\n".join(lines),
            method=DocumentMethod.IMAGE_OCR,
        ),
    )


class GoldenBrowserPageFetcher:
    def __init__(
        self,
        delegate: BrowserPageFetcher,
        cache: dict[tuple[str, str], dict[str, Any]],
    ) -> None:
        self.delegate = delegate
        self.cache = cache

    async def fetch(
        self,
        source: Source,
        request: FetchRequest,
    ) -> tuple[Document, ...]:
        cached = self.cache.get((source.name, source.url))
        cached_records = cached.get("records", {}) if cached else {}
        if (
            source.parser == "image_ocr"
            and cached is not None
            and all(
                str(issue) in cached_records or issue in cached_records
                for issue in request.issues
            )
        ):
            return _ocr_documents_from_cache(source, cached, request.issues)
        return await self.delegate.fetch(source, request)


def _load_cache(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    return {
        (item["source"]["name"], item["source"]["url"]): item
        for item in document["sources"]
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--issue", type=int)
    return parser.parse_args()


def selected_issues(issue: int | None) -> tuple[int, ...]:
    if issue is None:
        return ISSUES
    if issue <= 0:
        raise ValueError("issue must be positive")
    return (issue,)


def _safe_output(project_root: Path, output: Path) -> Path:
    allowed = (project_root / "v2" / "reviews").resolve()
    resolved = output.resolve()
    if resolved.parent != allowed:
        raise ValueError("V2 golden output must be directly inside v2/reviews")
    return resolved


async def export(args: argparse.Namespace) -> None:
    project_root = args.project_root.resolve()
    output = _safe_output(project_root, args.output)
    issues = selected_issues(args.issue)
    source_repository = SourceRepository(
        project_root / "v2" / "config" / "sources.json",
        project_root / "v2" / "config" / "archived_sources.json",
    )
    sources = source_repository.load_active()
    golden_cache = _load_cache(
        project_root / "v2" / "baseline" / "recent_10_cache.json"
    )
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(ignore_https_errors=False)
        try:
            http = PlaywrightHttpClient(context)
            browser_client = PlaywrightBrowserClient(context)
            fetchers = FetcherRegistry()
            fetchers.register("static_page", StaticPageFetcher(http))
            fetchers.register(
                "dynamic_article",
                DynamicArticleFetcher(http, browser_client),
            )
            fetchers.register(
                "browser_page",
                GoldenBrowserPageFetcher(
                    BrowserPageFetcher(browser_client),
                    golden_cache,
                ),
            )
            fetchers.register(
                "list_detail",
                ListDetailFetcher(browser_client),
            )
            audits = await HistoricalAuditService(
                fetchers,
                build_parser_registry(),
                Validator(),
            ).audit_many(
                sources,
                issues,
                concurrency=max(1, args.concurrency),
            )
        finally:
            await context.close()
            await browser.close()
    snapshot = snapshot_from_v2(audits, issues)
    GoldenRepository(output).write(snapshot)
    print(f"v2_sources={len(snapshot.sources)}")


def main() -> None:
    asyncio.run(export(parse_args()))


if __name__ == "__main__":
    main()
