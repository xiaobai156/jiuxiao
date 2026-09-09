from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from v2.domain.errors import ErrorCode, Failure
from v2.domain.models import Result, Source
from v2.fetchers.registry import FetchError, FetchRequest, FetcherRegistry
from v2.parsers.registry import ParseError, ParserRegistry
from v2.validator import ValidationError, Validator


@dataclass(frozen=True, slots=True)
class CrawlProgress:
    completed: int
    total: int
    succeeded: int
    failed: int
    elapsed_seconds: float
    result: Result


ProgressCallback = Callable[[CrawlProgress], Awaitable[None] | None]


class CrawlService:
    def __init__(
        self,
        fetchers: FetcherRegistry,
        parsers: ParserRegistry,
        validator: Validator,
    ) -> None:
        self._fetchers = fetchers
        self._parsers = parsers
        self._validator = validator

    async def crawl_one(
        self,
        source: Source,
        issues: tuple[int, ...],
        *,
        history_mode: bool = False,
    ) -> Result:
        try:
            fetcher = self._fetchers.resolve(source.fetcher)
            parser = self._parsers.resolve(source.parser)
        except KeyError as exc:
            return Result.failed(
                source,
                issues,
                Failure(ErrorCode.CONFIG_INVALID, detail=str(exc)),
            )

        try:
            documents = await fetcher.fetch(
                source,
                FetchRequest(issues, history_mode=history_mode),
            )
            records = parser.parse(source, documents, issues)
            verified = self._validator.validate(
                source,
                records,
                issues,
                history_mode=history_mode,
            )
        except (FetchError, ParseError, ValidationError) as exc:
            return Result.failed(source, issues, exc.failure)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            message = str(exc).strip()
            detail = (
                f"{type(exc).__name__}: {message}"
                if message
                else type(exc).__name__
            )
            return Result.failed(
                source,
                issues,
                Failure(ErrorCode.INTERNAL_ERROR, detail=detail),
            )
        return Result.succeeded(source, issues, verified.history)

    async def crawl_many(
        self,
        sources: tuple[Source, ...],
        issues: tuple[int, ...],
        *,
        concurrency: int,
        history_mode: bool = False,
        on_progress: ProgressCallback | None = None,
    ) -> tuple[Result, ...]:
        if concurrency <= 0:
            raise ValueError("concurrency must be greater than zero")
        semaphore = asyncio.Semaphore(concurrency)
        started_at = time.monotonic()

        async def limited(index: int, source: Source) -> tuple[int, Result]:
            async with semaphore:
                result = await self.crawl_one(
                    source,
                    issues,
                    history_mode=history_mode,
                )
                return index, result

        results: dict[int, Result] = {}
        succeeded = 0
        failed = 0
        for completed in asyncio.as_completed(
            tuple(
                limited(index, source)
                for index, source in enumerate(sources)
            )
        ):
            index, result = await completed
            results[index] = result
            if result.successful:
                succeeded += 1
            else:
                failed += 1
            if on_progress is not None:
                update = on_progress(
                    CrawlProgress(
                        completed=len(results),
                        total=len(sources),
                        succeeded=succeeded,
                        failed=failed,
                        elapsed_seconds=time.monotonic() - started_at,
                        result=result,
                    )
                )
                if inspect.isawaitable(update):
                    await update
        return tuple(results[index] for index in range(len(sources)))
