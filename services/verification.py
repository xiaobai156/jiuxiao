from __future__ import annotations

from typing import Protocol

from v2.domain.models import Result, Source


class CrawlOne(Protocol):
    async def crawl_one(
        self,
        source: Source,
        issues: tuple[int, ...],
        *,
        history_mode: bool = False,
    ) -> Result: ...


class VerificationService:
    def __init__(self, crawl: CrawlOne) -> None:
        self._crawl = crawl

    async def verify(
        self,
        source: Source,
        issues: tuple[int, ...],
    ) -> Result:
        return await self._crawl.crawl_one(source, issues)
