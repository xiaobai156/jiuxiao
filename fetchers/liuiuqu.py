from __future__ import annotations

import asyncio

from v2.domain.errors import ErrorCode, Failure
from v2.domain.models import Document, DocumentMethod, Source
from v2.fetchers.registry import FetchError, FetchRequest, HttpClient
from v2.fetchers.static_page import RECOVERABLE_HTTP_STATUSES


class LiuiuquFetcher:
    """Fetch 六爱趣 through its only authoritative JSON endpoint."""

    def __init__(self, http: HttpClient) -> None:
        self._http = http

    async def fetch(
        self,
        source: Source,
        request: FetchRequest,
    ) -> tuple[Document, ...]:
        if not source.api_url:
            raise FetchError(
                Failure(
                    ErrorCode.CONFIG_INVALID,
                    detail="liuiuqu requires api_url",
                )
            )
        for attempt in range(1, request.attempts + 1):
            response = await self._http.post(
                source.api_url,
                timeout_ms=request.timeout_ms,
                headers=(
                    ("Accept", "application/json,text/plain,*/*"),
                    ("X-Requested-With", "XMLHttpRequest"),
                ),
                form=(("type", "3"),),
            )
            if response.status == 200 and response.text.strip():
                return (
                    Document(
                        label="liuiuqu-api",
                        url=response.url or source.api_url,
                        text=response.text,
                        method=DocumentMethod.DYNAMIC_API,
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
                        detail=response.error,
                        context=(("api_url", source.api_url),),
                    )
                )
            if response.status == 200:
                raise FetchError(
                    Failure(
                        ErrorCode.SOURCE_UNTRUSTED,
                        detail="empty api response",
                        context=(("api_url", source.api_url),),
                    )
                )
            raise FetchError(
                Failure(
                    ErrorCode.HTTP_ERROR,
                    context=(
                        ("api_url", source.api_url),
                        ("status", str(response.status)),
                    ),
                )
            )
        raise AssertionError("unreachable")
