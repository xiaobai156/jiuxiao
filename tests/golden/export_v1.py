from __future__ import annotations

import argparse
import asyncio
import builtins
import json
import sys
from pathlib import Path

from playwright.async_api import async_playwright


ISSUES = tuple(range(210, 200, -1))
OCR_FALLBACK_NAMES = {"嫦娥公式", "嫦娥奔月"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--retries", type=int, default=3)
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
        raise ValueError("V1 golden output must be directly inside v2/reviews")
    return resolved


def _fallback_histories(path: Path) -> dict[tuple[str, str], dict]:
    document = json.loads(path.read_text(encoding="utf-8"))
    return {
        (item["source"]["name"], item["source"]["url"]): item
        for item in document["sources"]
    }


async def export(args: argparse.Namespace) -> None:
    project_root = args.project_root.resolve()
    output = _safe_output(project_root, args.output)
    issues = selected_issues(args.issue)
    sys.path.insert(0, str(project_root))

    import detect_duplicates as legacy

    from v2.config.repository import SourceRepository
    from v2.services.golden import snapshot_from_v1_document
    from v2.storage.golden import GoldenRepository

    legacy.DUPE_BASELINE_LIMIT = 20
    sources = legacy.load_extra_sources(project_root / "extra_sources.json")
    fallbacks = _fallback_histories(
        project_root / "v2" / "baseline" / "recent_10_cache.json"
    )
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            ignore_https_errors=True,
            viewport={"width": 900, "height": 1400},
        )
        try:
            semaphore = asyncio.Semaphore(max(1, args.concurrency))

            async def guarded(source, index):
                fallback = fallbacks.get((source.name, source.url))
                fallback_records = fallback.get("records", {}) if fallback else {}
                if (
                    source.name in OCR_FALLBACK_NAMES
                    and fallback is not None
                    and all(
                        str(issue) in fallback_records or issue in fallback_records
                        for issue in issues
                    )
                ):
                    return legacy.SourceHistory(
                        source=source,
                        records={
                            int(issue): value
                            for issue, value in fallback.get("records", {}).items()
                            if int(issue) in issues
                        },
                        current_issue=fallback.get("current_issue"),
                        errors=list(fallback.get("errors", [])),
                        audit={
                            int(issue): value
                            for issue, value in fallback.get("audit", {}).items()
                            if int(issue) in issues
                        },
                    )
                async with semaphore:
                    return await legacy.fetch_history(
                        context,
                        source,
                        index,
                        len(sources),
                        max(1, args.retries),
                        None,
                    )

            original_print = builtins.print
            builtins.print = lambda *_args, **_kwargs: None
            try:
                histories = await asyncio.gather(
                    *(
                        guarded(source, index)
                        for index, source in enumerate(sources, start=1)
                    )
                )
            finally:
                builtins.print = original_print
        finally:
            await context.close()
            await browser.close()

    raw_document = {
        "schema_version": 1,
        "engine": "v1",
        "issues": list(issues),
        "sources": [
            {
                "source": {
                    "name": history.source.name,
                    "url": history.source.url,
                    "position": history.source.position,
                    "section_marker": history.source.section_marker,
                    "api_url": history.source.api_url,
                    "group_map": history.source.group_map,
                    "detail_link_keyword": history.source.detail_link_keyword,
                },
                "current_issue": history.current_issue,
                "records": {
                    str(issue): history.records[issue]
                    for issue in issues
                    if issue in history.records
                },
                "audit": {
                    str(issue): history.audit[issue]
                    for issue in issues
                    if history.audit and issue in history.audit
                },
                "errors": history.errors,
            }
            for history in histories
        ],
    }
    repository = SourceRepository(
        project_root / "v2" / "config" / "sources.json",
        project_root / "v2" / "config" / "archived_sources.json",
    )
    snapshot = snapshot_from_v1_document(
        raw_document,
        repository.load_active(),
        issues,
    )
    GoldenRepository(output).write(snapshot)
    print(f"v1_sources={len(snapshot.sources)}")


def main() -> None:
    asyncio.run(export(parse_args()))


if __name__ == "__main__":
    main()
