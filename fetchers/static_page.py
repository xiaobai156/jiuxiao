from __future__ import annotations

import asyncio

from v2.domain.errors import ErrorCode, Failure
from v2.domain.models import Document, DocumentMethod, Source
from v2.fetchers.registry import FetchError, FetchRequest, HttpClient


RECOVERABLE_HTTP_STATUSES = {408, 429, 502, 503, 504}


class StaticPageFetcher:
    def __init__(self, http: HttpClient) -> None:
        self.http = http

    async def fetch(
        self,
        source: Source,
        request: FetchRequest,
    ) -> tuple[Document, ...]:
        last_status: int | None = None
        last_error = ""
        for attempt in range(1, request.attempts + 1):
            response = await self.http.get(
                source.url,
                timeout_ms=request.timeout_ms,
                headers=(("Accept", "text/html,*/*"),),
            )
            last_status = response.status
            last_error = response.error
            if response.status == 200 and response.text:
                return (
                    Document(
                        label="static-page",
                        url=response.url or source.url,
                        text=response.text,
                        method=DocumentMethod.STATIC_PAGE,
                    ),
                )
            retryable = (
                response.status is None
                or response.status in RECOVERABLE_HTTP_STATUSES
            )
            if retryable and attempt < request.attempts:
                if request.retry_delay_ms:
                    await asyncio.sleep(request.retry_delay_ms / 1000)
                continue
            if response.status is None:
                raise FetchError(
                    Failure(
                        ErrorCode.FETCH_FAILED,
                        detail=last_error,
                        context=(("url", source.url),),
                    )
                )
            if response.status == 200:
                raise FetchError(
                    Failure(
                        ErrorCode.SOURCE_UNTRUSTED,
                        detail="empty response",
                        context=(("url", source.url),),
                    )
                )
            raise FetchError(
                Failure(
                    ErrorCode.HTTP_ERROR,
                    context=(
                        ("url", source.url),
                        ("status", str(last_status)),
                    ),
                )
            )
        raise AssertionError("unreachable")
