from __future__ import annotations

import asyncio
from dataclasses import dataclass

from v2.domain.errors import ErrorCode, Failure
from v2.domain.models import Result, Source
from v2.fetchers.registry import FetchError, FetchRequest, FetcherRegistry
from v2.parsers.registry import ParseError, ParserRegistry
from v2.validator import ValidationError, Validator


HISTORICAL_SEARCH_LIMIT = 20


@dataclass(frozen=True, slots=True)
class HistoricalSourceAudit:
    source: Source
    results: tuple[Result, ...]


class HistoricalAuditService:
    def __init__(
        self,
        fetchers: FetcherRegistry,
        parsers: ParserRegistry,
        validator: Validator,
    ) -> None:
        self._fetchers = fetchers
        self._parsers = parsers
        self._validator = validator

    async def audit_one(
        self,
        source: Source,
        issues: tuple[int, ...],
    ) -> HistoricalSourceAudit:
        try:
            fetcher = self._fetchers.resolve(source.fetcher)
            parser = self._parsers.resolve(source.parser)
        except KeyError as exc:
            return self._failed_all(
                source,
                issues,
                Failure(ErrorCode.CONFIG_INVALID, detail=str(exc)),
            )
        try:
            documents = await fetcher.fetch(
                source,
                FetchRequest(issues, history_mode=True),
            )
            records = parser.parse(source, documents, issues)
        except (FetchError, ParseError) as exc:
            return self._failed_all(source, issues, exc.failure)

        results: list[Result] = []
        for issue in issues:
            try:
                verified = self._validator.validate(
                    source,
                    records,
                    (issue,),
                    history_mode=True,
                    history_limit=max(HISTORICAL_SEARCH_LIMIT, len(issues)),
                )
            except ValidationError as exc:
                results.append(Result.failed(source, (issue,), exc.failure))
            else:
                results.append(
                    Result.succeeded(source, (issue,), verified.history)
                )
        return HistoricalSourceAudit(source, tuple(results))

    async def audit_many(
        self,
        sources: tuple[Source, ...],
        issues: tuple[int, ...],
        *,
        concurrency: int,
    ) -> tuple[HistoricalSourceAudit, ...]:
        if concurrency <= 0:
            raise ValueError("concurrency must be greater than zero")
        semaphore = asyncio.Semaphore(concurrency)

        async def limited(source: Source) -> HistoricalSourceAudit:
            async with semaphore:
                return await self.audit_one(source, issues)

        return tuple(await asyncio.gather(*(limited(source) for source in sources)))

    @staticmethod
    def _failed_all(
        source: Source,
        issues: tuple[int, ...],
        failure: Failure,
    ) -> HistoricalSourceAudit:
        return HistoricalSourceAudit(
            source,
            tuple(Result.failed(source, (issue,), failure) for issue in issues),
        )
