from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from v2.domain.errors import Failure
from v2.domain.models import Document, Source


@dataclass(frozen=True, slots=True)
class FetchRequest:
    issues: tuple[int, ...]
    attempts: int = 5
    timeout_ms: int = 60_000
    settle_ms: int = 1_200
    retry_delay_ms: int = 0
    history_mode: bool = False

    def __post_init__(self) -> None:
        issues = tuple(self.issues)
        if not issues or any(
            not isinstance(issue, int)
            or isinstance(issue, bool)
            or issue <= 0
            for issue in issues
        ):
            raise ValueError("issues 必须包含正整数")
        if len(issues) != len(set(issues)):
            raise ValueError("issues 不能重复")
        if self.attempts <= 0:
            raise ValueError("attempts 必须大于 0")
        if self.timeout_ms <= 0:
            raise ValueError("timeout_ms 必须大于 0")
        if self.settle_ms < 0 or self.retry_delay_ms < 0:
            raise ValueError("等待时间不能小于 0")
        if not isinstance(self.history_mode, bool):
            raise TypeError("history_mode 必须是 bool")
        object.__setattr__(self, "issues", issues)


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status: int | None
    text: str
    url: str
    error: str = ""


@dataclass(frozen=True, slots=True)
class Link:
    url: str
    text: str


class HttpClient(Protocol):
    async def get(
        self,
        url: str,
        *,
        timeout_ms: int,
        headers: tuple[tuple[str, str], ...],
    ) -> HttpResponse: ...

    async def post(
        self,
        url: str,
        *,
        timeout_ms: int,
        headers: tuple[tuple[str, str], ...],
        form: tuple[tuple[str, str], ...],
    ) -> HttpResponse: ...


class BrowserClient(Protocol):
    async def collect(
        self,
        url: str,
        *,
        timeout_ms: int,
        settle_ms: int,
        include_image_ocr: bool = False,
        anchor_terms: tuple[str, ...] = (),
        data_marker_terms: tuple[str, ...] = (),
    ) -> tuple[Document, ...]: ...

    async def links(
        self,
        url: str,
        *,
        timeout_ms: int,
        settle_ms: int,
    ) -> tuple[Link, ...]: ...


class Fetcher(Protocol):
    async def fetch(
        self,
        source: Source,
        request: FetchRequest,
    ) -> tuple[Document, ...]: ...


class FetchError(RuntimeError):
    def __init__(self, failure: Failure) -> None:
        super().__init__(failure.code.value)
        self.failure = failure


class FetcherRegistry:
    def __init__(self) -> None:
        self._fetchers: dict[str, Fetcher] = {}

    def register(self, key: str, fetcher: Fetcher) -> None:
        normalized = str(key).strip()
        if not normalized:
            raise ValueError("fetcher key 不能为空")
        if normalized in self._fetchers:
            raise ValueError(f"fetcher 已注册: {normalized}")
        self._fetchers[normalized] = fetcher

    def resolve(self, key: str) -> Fetcher:
        normalized = str(key).strip()
        if normalized not in self._fetchers:
            raise KeyError(normalized)
        return self._fetchers[normalized]
