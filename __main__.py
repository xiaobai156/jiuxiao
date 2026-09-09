from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence

from v2.runtime import (
    project_root,
    run_crawl,
    run_crawl_range,
    run_retry_failed,
    run_preflight,
    run_rollback,
    run_shadow,
    run_switch,
)
from v2.services.crawl import CrawlProgress


def positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def cycle_label(value: str) -> str:
    normalized = str(value).strip()
    if (
        not normalized
        or len(normalized) > 64
        or any(character.isspace() for character in normalized)
    ):
        raise argparse.ArgumentTypeError(
            "cycle must be a non-empty label without whitespace"
        )
    return normalized


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ling-she-v2")
    subparsers = parser.add_subparsers(dest="command", required=True)

    crawl = subparsers.add_parser("crawl")
    crawl.add_argument("issue", type=positive_int)
    crawl.add_argument("--concurrency", type=positive_int, default=8)
    crawl.add_argument(
        "--cycle",
        type=cycle_label,
        default=None,
        help="期号周期标签；默认使用当前年份，例如 2026",
    )

    crawl_range = subparsers.add_parser("crawl-range")
    crawl_range.add_argument("start_issue", type=positive_int)
    crawl_range.add_argument("end_issue", type=positive_int)
    crawl_range.add_argument("--concurrency", type=positive_int, default=8)

    retry_failed = subparsers.add_parser("retry-failed")
    retry_failed.add_argument("issue", type=positive_int)
    retry_failed.add_argument("--concurrency", type=positive_int, default=1)
    retry_failed.add_argument(
        "--cycle",
        type=cycle_label,
        default=None,
        help="必须与正式缓存周期一致；默认使用当前年份",
    )

    shadow = subparsers.add_parser("shadow")
    shadow.add_argument("issue", type=positive_int)
    shadow.add_argument("--concurrency", type=positive_int, default=10)

    subparsers.add_parser("preflight")
    subparsers.add_parser("switch")
    subparsers.add_parser("rollback")
    return parser


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "crawl-range" and args.start_issue < args.end_issue:
        parser.error("start_issue must be greater than or equal to end_issue")
    return args


def render_progress(progress: CrawlProgress) -> str:
    percent = progress.completed * 100 // progress.total
    return (
        f"进度 {progress.completed}/{progress.total} {percent}% "
        f"成功 {progress.succeeded} 失败 {progress.failed} "
        f"用时 {progress.elapsed_seconds:.1f}s "
        f"当前：{progress.result.source.name}"
    )


def print_progress(progress: CrawlProgress) -> None:
    print(render_progress(progress), flush=True)


async def async_main(argv: Sequence[str]) -> int:
    args = parse_args(argv)
    root = project_root()
    if args.command == "crawl":
        print(f"正在抓取 {args.issue}期，请稍候...", flush=True)
        run = await run_crawl(
            root,
            args.issue,
            concurrency=args.concurrency,
            on_progress=print_progress,
            cycle=args.cycle,
        )
        print(run.output_path)
        print(run.failure_path)
        print(f"成功率 {run.success_count}/{run.total_count}")
        if run.cache_updated:
            print("缓存已更新")
        else:
            print(f"缓存更新未完成：{run.cache_error}")
    elif args.command == "crawl-range":
        run = await run_crawl_range(
            root,
            args.start_issue,
            args.end_issue,
            concurrency=args.concurrency,
        )
        print(run.failure_summary_path)
    elif args.command == "retry-failed":
        run = await run_retry_failed(
            root,
            args.issue,
            concurrency=args.concurrency,
            cycle=args.cycle,
        )
        item = run.issues[0]
        print(item.output_path)
        print(item.failure_path)
        print(f"失败TXT定向重抓完成：{item.success_count}/{item.total_count}")
    elif args.command == "shadow":
        run = await run_shadow(root, args.issue, concurrency=args.concurrency)
        print(f"differences={run.difference_count}")
        print(run.report_path)
    elif args.command == "preflight":
        report = run_preflight(root)
        for check in report.checks:
            print(f"{'PASS' if check.passed else 'FAIL'} {check.name}: {check.detail}")
        return 0 if report.passed else 2
    elif args.command == "switch":
        run_switch(root)
        print("V2 BAT switch complete")
    elif args.command == "rollback":
        run_rollback(root)
        print("V1 BAT rollback complete")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(async_main(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    raise SystemExit(main())
