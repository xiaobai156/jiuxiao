from __future__ import annotations

import asyncio
import base64
import binascii
import html
import json
import re
from typing import Any
from urllib.parse import urljoin

from v2.domain.errors import ErrorCode, Failure
from v2.domain.models import Document, DocumentMethod, Source
from v2.fetchers.browser_page import BrowserPageFetcher, same_origin
from v2.fetchers.registry import (
    BrowserClient,
    FetchError,
    FetchRequest,
    HttpClient,
)
from v2.fetchers.static_page import RECOVERABLE_HTTP_STATUSES


ARTICLE_ID_KEYS = (
    "id",
    "_id",
    "articleId",
    "article_id",
    "recordId",
    "record_id",
)
ARTICLE_PATTERN = re.compile(
    r"/article/(?P<kind>admin|manager|lottery)/(?P<record_id>[^/?#]+)",
    re.IGNORECASE,
)


def article_record_identity(url: str) -> tuple[str, str]:
    match = ARTICLE_PATTERN.search(url)
    if not match:
        return "", ""
    return match.group("kind").lower(), match.group("record_id")


def article_api_url(source: Source) -> str:
    if source.api_url:
        return urljoin(source.url, source.api_url)
    kind, record_id = article_record_identity(source.url)
    if not record_id:
        return ""
    api_kind = "manager" if kind == "admin" else kind
    return urljoin(
        source.url,
        f"/api/proxy/{api_kind}-articles/{record_id}",
    )


def _select_record(
    payload: Any,
    expected_record_id: str,
) -> tuple[dict[str, Any] | None, str, bool]:
    matches: list[tuple[dict[str, Any], str]] = []

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            record_ids = {
                str(value[key]).strip()
                for key in ARTICLE_ID_KEYS
                if key in value
                and value[key] is not None
                and not isinstance(value[key], (dict, list))
            }
            if expected_record_id in record_ids:
                matches.append((value, path))
            for key, child in value.items():
                walk(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")

    walk(payload, "$")
    if len(matches) == 1:
        record, path = matches[0]
        return record, path, False
    return None, "", len(matches) > 1


def _decode_field(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    try:
        decoded = base64.b64decode(text, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return text
    return decoded if decoded.strip() else text


def _html_to_text(value: Any) -> str:
    text = _decode_field(value)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(?:p|div|li|tr|h[1-6])>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(text)


def _record_text(record: dict[str, Any]) -> str:
    parts = [
        _html_to_text(record.get("title", "")),
        _html_to_text(record.get("authorNickname", "")),
        _html_to_text(record.get("html", "")),
    ]
    sections = record.get("formSections", [])
    if isinstance(sections, list):
        for section in sections:
            if not isinstance(section, dict):
                continue
            parts.extend(
                (
                    _html_to_text(section.get("name", "")),
                    _html_to_text(section.get("htmlCode", "")),
                    _html_to_text(section.get("disclaimerHtml", "")),
                )
            )
    return "\n".join(part for part in parts if part.strip())


def _payload_has_body(payload: Any) -> bool:
    if isinstance(payload, dict):
        if any(
            _html_to_text(payload.get(key, "")).strip()
            for key in ("html", "htmlCode", "disclaimerHtml")
        ):
            return True
        return any(_payload_has_body(child) for child in payload.values())
    if isinstance(payload, list):
        return any(_payload_has_body(child) for child in payload)
    return False


class DynamicArticleFetcher:
    def __init__(
        self,
        http: HttpClient,
        browser: BrowserClient,
    ) -> None:
        self.http = http
        self.browser = browser

    async def fetch(
        self,
        source: Source,
        request: FetchRequest,
    ) -> tuple[Document, ...]:
        _kind, expected_record_id = article_record_identity(source.url)
        api_url = article_api_url(source)
        if not expected_record_id or not api_url:
            raise FetchError(
                Failure(
                    ErrorCode.CONFIG_INVALID,
                    detail="dynamic article identity is missing",
                    context=(("url", source.url),),
                )
            )

        for attempt in range(1, request.attempts + 1):
            response = await self.http.get(
                api_url,
                timeout_ms=request.timeout_ms,
                headers=(("Accept", "application/json,text/plain,*/*"),),
            )
            if response.url and not same_origin(api_url, response.url):
                raise FetchError(
                    Failure(
                        ErrorCode.CROSS_DOMAIN,
                        context=(
                            ("api_url", api_url),
                            ("document_url", response.url),
                        ),
                    )
                )
            if response.status is None:
                if attempt < request.attempts:
                    if request.retry_delay_ms:
                        await asyncio.sleep(request.retry_delay_ms / 1000)
                    continue
                raise FetchError(
                    Failure(
                        ErrorCode.FETCH_FAILED,
                        detail=response.error,
                        context=(("api_url", api_url),),
                    )
                )
            if response.status in RECOVERABLE_HTTP_STATUSES:
                if attempt < request.attempts:
                    if request.retry_delay_ms:
                        await asyncio.sleep(request.retry_delay_ms / 1000)
                    continue
                raise FetchError(
                    Failure(
                        ErrorCode.HTTP_ERROR,
                        context=(
                            ("api_url", api_url),
                            ("status", str(response.status)),
                        ),
                    )
                )
            if response.status == 404 or (
                response.status == 200 and not response.text
            ):
                return await self._browser_fallback(
                    source,
                    request,
                    expected_record_id,
                )
            if response.status != 200:
                raise FetchError(
                    Failure(
                        ErrorCode.HTTP_ERROR,
                        context=(
                            ("api_url", api_url),
                            ("status", str(response.status)),
                        ),
                    )
                )
            try:
                payload = json.loads(response.text)
            except json.JSONDecodeError as exc:
                raise FetchError(
                    Failure(
                        ErrorCode.SOURCE_UNTRUSTED,
                        detail="api response is not json",
                        context=(("api_url", api_url),),
                    )
                ) from exc
            record, record_path, conflict = _select_record(
                payload,
                expected_record_id,
            )
            if conflict:
                raise FetchError(
                    Failure(
                        ErrorCode.API_RECORD_MISMATCH,
                        detail="record id is duplicated",
                        context=(("article_id", expected_record_id),),
                    )
                )
            if record is None:
                if not _payload_has_body(payload):
                    return await self._browser_fallback(
                        source,
                        request,
                        expected_record_id,
                    )
                raise FetchError(
                    Failure(
                        ErrorCode.API_RECORD_MISMATCH,
                        detail="expected record id is missing",
                        context=(("article_id", expected_record_id),),
                    )
                )
            text = _record_text(record)
            if not text.strip():
                return await self._browser_fallback(
                    source,
                    request,
                    expected_record_id,
                )
            return (
                Document(
                    label=f"api:{record_path}",
                    url=response.url or api_url,
                    text=text,
                    method=DocumentMethod.DYNAMIC_API,
                    metadata=(
                        ("article_id", expected_record_id),
                        ("record_path", record_path),
                        ("api_url", api_url),
                    ),
                ),
            )
        raise AssertionError("unreachable")

    async def _browser_fallback(
        self,
        source: Source,
        request: FetchRequest,
        expected_record_id: str,
    ) -> tuple[Document, ...]:
        documents = await BrowserPageFetcher(self.browser).fetch(
            source,
            request,
        )
        if not any(
            document.method is DocumentMethod.BROWSER_DOM
            and article_record_identity(document.url)[1] == expected_record_id
            for document in documents
        ):
            raise FetchError(
                Failure(
                    ErrorCode.API_RECORD_MISMATCH,
                    detail="browser url is not bound to article id",
                    context=(("article_id", expected_record_id),),
                )
            )
        return documents
