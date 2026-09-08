from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable
from contextlib import suppress
from urllib.parse import urljoin, urlsplit

from playwright.async_api import (
    BrowserContext,
)
from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
)
from v2.domain.errors import ErrorCode, Failure
from v2.domain.models import Document, DocumentMethod, Source
from v2.fetchers.paddle_ocr import PaddleOcrReader
from v2.fetchers.registry import (
    BrowserClient,
    FetchError,
    FetchRequest,
    HttpResponse,
    Link,
)

OcrReader = Callable[[bytes], str]


_PADDLE_OCR_READER = PaddleOcrReader()


def _read_image_text(content: bytes) -> str:
    return _PADDLE_OCR_READER(content)


def _error_detail(exc: Exception) -> str:
    message = str(exc).strip()
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__


def same_origin(left: str, right: str) -> bool:
    def origin(value: str) -> tuple[str, str, int | None]:
        parsed = urlsplit(value)
        scheme = parsed.scheme.lower()
        default_port = 443 if scheme == "https" else 80 if scheme == "http" else None
        return scheme, (parsed.hostname or "").casefold(), parsed.port or default_port

    try:
        return origin(left) == origin(right)
    except ValueError:
        return False


class PlaywrightHttpClient:
    def __init__(self, context: BrowserContext) -> None:
        self.context = context

    async def get(
        self,
        url: str,
        *,
        timeout_ms: int,
        headers: tuple[tuple[str, str], ...],
    ) -> HttpResponse:
        response = None
        try:
            response = await self.context.request.get(
                url,
                timeout=timeout_ms,
                headers=dict(headers),
            )
            return HttpResponse(
                status=response.status,
                text=await response.text(),
                url=response.url,
            )
        except Exception as exc:
            return HttpResponse(
                status=None,
                text="",
                url=url,
                error=_error_detail(exc),
            )
        finally:
            if response is not None:
                with suppress(Exception):
                    await response.dispose()

    async def post(
        self,
        url: str,
        *,
        timeout_ms: int,
        headers: tuple[tuple[str, str], ...],
        form: tuple[tuple[str, str], ...],
    ) -> HttpResponse:
        response = None
        try:
            response = await self.context.request.post(
                url,
                timeout=timeout_ms,
                headers=dict(headers),
                form=dict(form),
            )
            return HttpResponse(
                status=response.status,
                text=await response.text(),
                url=response.url,
            )
        except Exception as exc:
            return HttpResponse(
                status=None,
                text="",
                url=url,
                error=_error_detail(exc),
            )
        finally:
            if response is not None:
                with suppress(Exception):
                    await response.dispose()


class PlaywrightBrowserClient:
    IMAGE_MIN_WIDTH = 600
    IMAGE_MIN_HEIGHT = 200

    def __init__(
        self,
        context: BrowserContext,
        ocr_reader: OcrReader | None = None,
    ) -> None:
        self.context = context
        self.ocr_reader = ocr_reader or _read_image_text

    async def collect(
        self,
        url: str,
        *,
        timeout_ms: int,
        settle_ms: int,
        include_image_ocr: bool = False,
        anchor_terms: tuple[str, ...] = (),
        data_marker_terms: tuple[str, ...] = (),
    ) -> tuple[Document, ...]:
        page = await self.context.new_page()
        try:
            try:
                await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=timeout_ms,
                )
            except PlaywrightTimeoutError:
                pass
            if settle_ms:
                await page.wait_for_timeout(settle_ms)
            documents: list[Document] = []
            body = await self._body_text(page)
            self._append_document(
                documents,
                "browser-dom",
                page.url,
                body,
                DocumentMethod.BROWSER_DOM,
            )
            for index, frame in enumerate(page.frames):
                if frame == page.main_frame:
                    continue
                frame_text = await self._body_text(frame)
                self._append_document(
                    documents,
                    f"browser-frame:{index}",
                    frame.url,
                    frame_text,
                    DocumentMethod.BROWSER_FRAME,
                )
            try:
                scripts = await page.locator("script").all_text_contents()
            except Exception:
                scripts = []
            for index, script in enumerate(scripts):
                self._append_document(
                    documents,
                    f"script:{index}",
                    page.url,
                    script,
                    DocumentMethod.SCRIPT,
                )
            if include_image_ocr:
                try:
                    await page.wait_for_function(
                        """([minWidth, minHeight]) =>
                            [...document.images].some(image =>
                                image.naturalWidth >= minWidth &&
                                image.naturalHeight >= minHeight
                            )""",
                        arg=(
                            self.IMAGE_MIN_WIDTH,
                            self.IMAGE_MIN_HEIGHT,
                        ),
                        timeout=min(timeout_ms, 10_000),
                    )
                except Exception:
                    pass
                documents.extend(
                    await self._image_ocr_documents(
                        page,
                        anchor_terms,
                        data_marker_terms,
                    )
                )
            return tuple(documents)
        finally:
            await page.close()

    async def links(
        self,
        url: str,
        *,
        timeout_ms: int,
        settle_ms: int,
    ) -> tuple[Link, ...]:
        page = await self.context.new_page()
        try:
            try:
                await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=timeout_ms,
                )
            except PlaywrightTimeoutError:
                pass
            if settle_ms:
                await page.wait_for_timeout(settle_ms)
            raw_links = await page.locator("a").evaluate_all(
                """elements => elements.map(element => ({
                    href: element.getAttribute("href") || "",
                    text: (element.innerText || element.textContent || "").trim()
                }))"""
            )
            return tuple(
                Link(
                    url=urljoin(page.url, str(item.get("href", ""))),
                    text=str(item.get("text", "")).strip(),
                )
                for item in raw_links
                if str(item.get("href", "")).strip()
            )
        finally:
            await page.close()

    @staticmethod
    async def _body_text(page_or_frame) -> str:
        try:
            return await page_or_frame.locator("body").inner_text(
                timeout=10_000
            )
        except Exception:
            return ""

    @staticmethod
    def _append_document(
        documents: list[Document],
        label: str,
        url: str,
        text: str,
        method: DocumentMethod,
    ) -> None:
        normalized = str(text).strip()
        if not normalized or any(
            document.text.strip() == normalized for document in documents
        ):
            return
        documents.append(
            Document(
                label=label,
                url=url,
                text=normalized,
                method=method,
            )
        )

    async def _image_ocr_documents(
        self,
        page,
        anchor_terms: tuple[str, ...],
        data_marker_terms: tuple[str, ...],
    ) -> tuple[Document, ...]:
        images = page.locator("img")
        encoded_anchors = json.dumps(
            tuple(dict.fromkeys(anchor_terms)),
            ensure_ascii=False,
        )
        encoded_data_markers = json.dumps(
            tuple(dict.fromkeys(data_marker_terms)),
            ensure_ascii=False,
        )
        min_width = self.IMAGE_MIN_WIDTH
        min_height = self.IMAGE_MIN_HEIGHT
        try:
            candidates = await images.evaluate_all(
                f"""elements => {{
                    const anchors = {encoded_anchors};
                    const dataMarkers = {encoded_data_markers};
                    const minWidth = {min_width};
                    const minHeight = {min_height};
                    const bodyLines = (document.body?.innerText || "")
                        .split(/\\r?\\n/)
                        .map(line => line.trim())
                        .filter(Boolean);
                    const relation = image => {{
                        let node = image.parentElement;
                        for (let depth = 0; node && depth < 6; depth += 1) {{
                            if (node.tagName === "BODY" || node.tagName === "HTML") {{
                                break;
                            }}
                            const localLines = (node.innerText || "")
                                .split(/\\r?\\n/)
                                .map(line => line.trim())
                                .filter(Boolean);
                            for (const term of anchors) {{
                                const anchorLine = localLines.find(
                                    line => line.includes(term)
                                );
                                if (!anchorLine) continue;
                                const dataMarkerLine = localLines.find(
                                    line => dataMarkers.some(
                                        marker => line.includes(marker)
                                    )
                                );
                                if (!dataMarkerLine) continue;
                                const anchorIndex = bodyLines.findIndex(
                                    line => line === anchorLine
                                );
                                if (anchorIndex < 0) continue;
                                return {{
                                    anchorLine,
                                    anchorTerm: term,
                                    dataMarkerLine,
                                    anchorIndex,
                                    blockStart: anchorIndex,
                                    blockEnd: Math.max(
                                        anchorIndex + 1,
                                        Math.min(
                                            bodyLines.length,
                                            anchorIndex + localLines.length
                                        )
                                    )
                                }};
                            }}
                            node = node.parentElement;
                        }}
                        return {{}};
                    }};
                    return elements.map((image, index) => ({{
                        index,
                        width: image.naturalWidth,
                        height: image.naturalHeight,
                        ...relation(image)
                    }})).filter(
                        item => item.width >= minWidth &&
                            item.height >= minHeight
                    );
                }}"""
            )
        except Exception:
            return ()
        documents: list[Document] = []
        ranked = tuple(
            candidate
            for candidate in self._rank_image_candidates(candidates)
            if self._linked_image_candidate(
                candidate,
                anchor_terms,
                data_marker_terms,
            )
        )
        for candidate in ranked[:2]:
            try:
                image_index = int(candidate["index"])
                content = await images.nth(image_index).screenshot(
                    timeout=10_000
                )
                text = await asyncio.to_thread(self.ocr_reader, content)
            except Exception:
                continue
            if text.strip():
                metadata = [
                    ("image_index", str(image_index)),
                    ("parent_url", str(page.url)),
                ]
                anchor_line = str(candidate.get("anchorLine", "")).strip()
                anchor_term = str(candidate.get("anchorTerm", "")).strip()
                data_marker_line = str(
                    candidate.get("dataMarkerLine", "")
                ).strip()
                if (
                    anchor_line
                    and anchor_term in anchor_terms
                    and anchor_term in anchor_line
                    and data_marker_line
                    and any(
                        marker in data_marker_line
                        for marker in data_marker_terms
                    )
                ):
                    try:
                        anchor_index = int(candidate["anchorIndex"])
                        block_start = int(candidate["blockStart"])
                        block_end = int(candidate["blockEnd"])
                    except (KeyError, TypeError, ValueError):
                        pass
                    else:
                        if (
                            block_start >= 0
                            and block_end > block_start
                            and block_start <= anchor_index < block_end
                        ):
                            metadata.extend(
                                (
                                    ("anchor_line", anchor_line),
                                    ("anchor_term", anchor_term),
                                    ("data_marker_line", data_marker_line),
                                    ("anchor_index", str(anchor_index)),
                                    ("block_start", str(block_start)),
                                    ("block_end", str(block_end)),
                                )
                            )
                documents.append(
                    Document(
                        label=f"image-ocr:{image_index}",
                        url=page.url,
                        text=text,
                        method=DocumentMethod.IMAGE_OCR,
                        metadata=tuple(metadata),
                    )
                )
        return tuple(documents)

    @staticmethod
    def _rank_image_candidates(candidates):
        return tuple(
            sorted(
                candidates,
                key=lambda item: int(item["width"]) * int(item["height"]),
                reverse=True,
            )
        )

    @staticmethod
    def _linked_image_candidate(
        candidate,
        anchor_terms: tuple[str, ...],
        data_marker_terms: tuple[str, ...],
    ) -> bool:
        anchor_line = str(candidate.get("anchorLine", "")).strip()
        anchor_term = str(candidate.get("anchorTerm", "")).strip()
        data_marker_line = str(candidate.get("dataMarkerLine", "")).strip()
        try:
            anchor_index = int(candidate["anchorIndex"])
            block_start = int(candidate["blockStart"])
            block_end = int(candidate["blockEnd"])
        except (KeyError, TypeError, ValueError):
            return False
        return (
            bool(anchor_line)
            and anchor_term in anchor_terms
            and anchor_term in anchor_line
            and bool(data_marker_line)
            and any(marker in data_marker_line for marker in data_marker_terms)
            and block_start >= 0
            and block_end > block_start
            and block_start <= anchor_index < block_end
        )


class BrowserPageFetcher:
    def __init__(self, browser: BrowserClient) -> None:
        self.browser = browser

    async def fetch(
        self,
        source: Source,
        request: FetchRequest,
    ) -> tuple[Document, ...]:
        include_image_ocr = self._uses_image_ocr(source)
        last_error = "browser returned no documents"
        last_documents: tuple[Document, ...] = ()
        for attempt in range(1, request.attempts + 1):
            try:
                documents = await self.browser.collect(
                    source.url,
                    timeout_ms=request.timeout_ms,
                    settle_ms=request.settle_ms,
                    include_image_ocr=include_image_ocr,
                    anchor_terms=(
                        (source.section_marker,)
                        if source.section_marker
                        else tuple(
                            dict.fromkeys((source.name, *source.aliases))
                        )
                    ),
                    data_marker_terms=(
                        (source.data_marker or "九肖",)
                        if include_image_ocr
                        else ()
                    ),
                )
            except Exception as exc:
                last_error = _error_detail(exc)
                documents = ()
            trusted_documents: list[Document] = []
            for document in documents:
                if same_origin(source.url, document.url):
                    trusted_documents.append(document)
                    continue
                if document.method is DocumentMethod.BROWSER_FRAME:
                    continue
                raise FetchError(
                    Failure(
                        ErrorCode.CROSS_DOMAIN,
                        context=(
                            ("source_url", source.url),
                            ("document_url", document.url),
                        ),
                    )
                )
            documents = tuple(trusted_documents)
            last_documents = documents
            if self._history_is_ready(source, documents):
                return documents
            if attempt < request.attempts and request.retry_delay_ms:
                await asyncio.sleep(request.retry_delay_ms / 1000)
        if last_documents:
            return last_documents
        raise FetchError(
            Failure(
                ErrorCode.FETCH_FAILED,
                detail=last_error,
                context=(("url", source.url),),
            )
        )

    @staticmethod
    def _uses_image_ocr(source: Source) -> bool:
        return (
            source.parser == "image_ocr"
            or DocumentMethod.IMAGE_OCR.value in source.source_policy
        )

    @staticmethod
    def _history_is_ready(
        source: Source,
        documents: tuple[Document, ...],
    ) -> bool:
        content = "\n".join(
            document.text
            for document in documents
            if document.method is not DocumentMethod.SCRIPT
        )
        if not content:
            return False
        anchors = tuple(
            dict.fromkeys(
                (
                    source.section_marker or source.name,
                    source.name,
                    *source.aliases,
                )
            )
        )
        return any(anchor and anchor in content for anchor in anchors) and bool(
            re.search(r"(?<!\d)\d{1,3}\s*期", content)
        )
