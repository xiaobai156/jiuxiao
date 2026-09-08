from __future__ import annotations

import argparse
import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


AsyncCommand = Callable[..., Awaitable[object]]


class CliApplication(Protocol):
    async def crawl(self, issue: int, concurrency: int) -> object: ...

    async def crawl_range(
        self,
        start_issue: int,
        end_issue: int,
        concurrency: int,
    ) -> object: ...

    async def onboard(self, candidate_path: Path) -> object: ...

    async def verify(self, source_key: str, issue: int) -> object: ...

    async def shadow(self, issue: int) -> object: ...

    async def duplicate(self, candidate_path: Path) -> object: ...


@dataclass(frozen=True, slots=True)
class CommandHandlers:
    crawl: AsyncCommand
    crawl_range: AsyncCommand
    onboard: AsyncCommand
    verify: AsyncCommand
    shadow: AsyncCommand
    duplicate: AsyncCommand

    @classmethod
    def from_application(cls, application: CliApplication) -> CommandHandlers:
        return cls(
            crawl=application.crawl,
            crawl_range=application.crawl_range,
            onboard=application.onboard,
            verify=application.verify,
            shadow=application.shadow,
            duplicate=application.duplicate,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ling-she-v2")
    subparsers = parser.add_subparsers(dest="command", required=True)

    crawl = subparsers.add_parser("crawl")
    crawl.add_argument("issue", type=_positive_int)
    crawl.add_argument("--concurrency", type=_positive_int, default=8)

    crawl_range = subparsers.add_parser("crawl-range")
    crawl_range.add_argument("start_issue", type=_positive_int)
    crawl_range.add_argument("end_issue", type=_positive_int)
    crawl_range.add_argument("--concurrency", type=_positive_int, default=8)

    onboard = subparsers.add_parser("onboard")
    onboard.add_argument("candidate_path", type=Path)

    verify = subparsers.add_parser("verify")
    verify.add_argument("source_key")
    verify.add_argument("issue", type=_positive_int)

    shadow = subparsers.add_parser("shadow")
    shadow.add_argument("issue", type=_positive_int)

    duplicate = subparsers.add_parser("duplicate")
    duplicate.add_argument("candidate_path", type=Path)
    return parser


def _positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


async def async_main(
    argv: Sequence[str],
    handlers: CommandHandlers,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "crawl":
        await handlers.crawl(args.issue, args.concurrency)
    elif args.command == "crawl-range":
        if args.start_issue < args.end_issue:
            parser.error("start_issue must be greater than or equal to end_issue")
        await handlers.crawl_range(
            args.start_issue,
            args.end_issue,
            args.concurrency,
        )
    elif args.command == "onboard":
        await handlers.onboard(args.candidate_path)
    elif args.command == "verify":
        await handlers.verify(args.source_key, args.issue)
    elif args.command == "shadow":
        await handlers.shadow(args.issue)
    elif args.command == "duplicate":
        await handlers.duplicate(args.candidate_path)
    return 0


def main(argv: Sequence[str], handlers: CommandHandlers) -> int:
    return asyncio.run(async_main(argv, handlers))
