from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from v2.domain.errors import ErrorCode, Failure
from v2.domain.models import Document, Source
from v2.fetchers.browser_page import BrowserPageFetcher, same_origin
from v2.fetchers.registry import (
    BrowserClient,
    FetchError,
    FetchRequest,
)


MAX_LIST_PAGES = 20
TOP_THREE_LIST_PAGES = 3


def is_list_page_url(candidate_url: str, source_url: str) -> bool:
    candidate = urlsplit(candidate_url)
    source = urlsplit(source_url)
    if (
        candidate.scheme.lower(),
        candidate.netloc.lower(),
        candidate.path.lower(),
    ) != (
        source.scheme.lower(),
        source.netloc.lower(),
        source.path.lower(),
    ):
        return False
    candidate_query = parse_qsl(candidate.query, keep_blank_values=True)
    source_query = parse_qsl(source.query, keep_blank_values=True)
    page_values = [
        value for key, value in candidate_query if key.lower() == "page"
    ]
    if page_values and not all(value.isdigit() for value in page_values):
        return False

    def without_page(values: list[tuple[str, str]]) -> list[tuple[str, str]]:
        return sorted(
            (key.lower(), value)
            for key, value in values
            if key.lower() != "page"
        )

    return without_page(candidate_query) == without_page(source_query)


class ListDetailFetcher:
    fallback_to_latest = False

    def __init__(
        self,
        browser: BrowserClient,
        *,
        max_pages: int = MAX_LIST_PAGES,
    ) -> None:
        if max_pages <= 0:
            raise ValueError("max_pages must be greater than zero")
        self.browser = browser
        self.max_pages = max_pages

    async def fetch(
        self,
        source: Source,
        request: FetchRequest,
    ) -> tuple[Document, ...]:
        keyword = source.detail_link_keyword.strip()
        if not keyword:
            raise FetchError(
                Failure(
                    ErrorCode.CONFIG_INVALID,
                    detail="detail_link_keyword is required",
                )
            )
        try:
            links = await self._list_links(source, request)
        except Exception as exc:
            raise FetchError(
                Failure(
                    ErrorCode.FETCH_FAILED,
                    detail=type(exc).__name__,
                    context=(("url", source.url),),
                )
            ) from exc

        documents: list[Document] = []
        missing_issues: list[int] = []
        for issue in request.issues:
            matches = tuple(
                link
                for link in links
                if keyword in link.text
                and self._link_issue(link.text) == issue
            )
            if not matches:
                missing_issues.append(issue)
                continue
            unique_urls = tuple(dict.fromkeys(link.url for link in matches))
            if len(unique_urls) != 1:
                raise FetchError(
                    Failure(
                        ErrorCode.CANDIDATE_CONFLICT,
                        context=(
                            ("issue", str(issue)),
                            ("urls", " | ".join(unique_urls)),
                        ),
                    )
                )
            documents.extend(
                await self._detail_documents(
                    source,
                    request,
                    unique_urls[0],
                )
            )
        if documents:
            return tuple(documents)
        if self.fallback_to_latest:
            named = tuple(
                (issue, link.url)
                for link in links
                if keyword in link.text
                and (issue := self._link_issue(link.text)) is not None
            )
            if named:
                latest_issue = max(issue for issue, _url in named)
                unique_urls = tuple(
                    dict.fromkeys(
                        url for issue, url in named if issue == latest_issue
                    )
                )
                if len(unique_urls) != 1:
                    raise FetchError(
                        Failure(
                            ErrorCode.CANDIDATE_CONFLICT,
                            context=(
                                ("issue", str(latest_issue)),
                                ("urls", " | ".join(unique_urls)),
                            ),
                        )
                    )
                return await self._detail_documents(
                    source,
                    request,
                    unique_urls[0],
                )
        missing_issue = missing_issues[0] if missing_issues else request.issues[0]
        raise FetchError(
            Failure(
                ErrorCode.ISSUE_MISSING,
                context=(
                    ("issue", str(missing_issue)),
                    ("keyword", keyword),
                ),
            )
        )

    async def _detail_documents(
        self,
        source: Source,
        request: FetchRequest,
        detail_url: str,
    ) -> tuple[Document, ...]:
        if not same_origin(source.url, detail_url):
            raise FetchError(
                Failure(
                    ErrorCode.CROSS_DOMAIN,
                    context=(
                        ("source_url", source.url),
                        ("detail_url", detail_url),
                    ),
                )
            )
        detail_source = Source(
            name=source.name,
            url=detail_url,
            position=source.position,
            section_marker=source.section_marker,
            fetcher=source.fetcher,
            parser=source.parser,
            api_url=source.api_url,
            group_map=source.group_map,
            detail_link_keyword=source.detail_link_keyword,
            aliases=source.aliases,
            data_marker=source.data_marker,
            source_policy=source.source_policy,
        )
        return await BrowserPageFetcher(self.browser).fetch(
            detail_source,
            request,
        )

    @staticmethod
    def _link_issue(text: str) -> int | None:
        match = re.search(r"(?<!\d)(\d{1,3})\s*期", text)
        return int(match.group(1)) if match else None

    async def _list_links(
        self,
        source: Source,
        request: FetchRequest,
    ) -> tuple:
        pending = [source.url]
        visited: set[str] = set()
        collected = []
        while pending and len(visited) < self.max_pages:
            current = pending.pop(0)
            parts = urlsplit(current)
            current = urlunsplit(
                (parts.scheme, parts.netloc, parts.path, parts.query, "")
            )
            if current in visited:
                continue
            links = await self.browser.links(
                current,
                timeout_ms=request.timeout_ms,
                settle_ms=request.settle_ms,
            )
            visited.add(current)
            collected.extend(links)
            if (
                not request.history_mode
                and self._requested_links_found(
                    source,
                    request.issues,
                    collected,
                )
            ):
                return tuple(collected)
            for link in links:
                if not is_list_page_url(link.url, source.url):
                    continue
                link_parts = urlsplit(link.url)
                normalized = urlunsplit(
                    (
                        link_parts.scheme,
                        link_parts.netloc,
                        link_parts.path,
                        urlencode(
                            parse_qsl(
                                link_parts.query,
                                keep_blank_values=True,
                            )
                        ),
                        "",
                    )
                )
                if normalized not in visited and normalized not in pending:
                    pending.append(normalized)
        return tuple(collected)

    @classmethod
    def _requested_links_found(
        cls,
        source: Source,
        issues: tuple[int, ...],
        links: list,
    ) -> bool:
        keyword = source.detail_link_keyword.strip()
        found = {
            issue
            for link in links
            if keyword in link.text
            and (issue := cls._link_issue(link.text)) is not None
        }
        return set(issues).issubset(found)


class ListDetailTopThreeFetcher(ListDetailFetcher):
    def __init__(self, browser: BrowserClient) -> None:
        super().__init__(browser, max_pages=TOP_THREE_LIST_PAGES)


class ListDetailCurrentFetcher(ListDetailFetcher):
    fallback_to_latest = True
