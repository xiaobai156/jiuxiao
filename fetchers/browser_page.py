from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from urllib.parse import urljoin, urlsplit

from playwright.async_api import (
    BrowserContext,
    Error as PlaywrightError,
    Page,
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

# 换址重抓（旧域名 301 → 新域名 + 原路径）时的最小等待时间。
# 实测这类站点 1200ms 只拿到门户壳，4000ms 才能渲染出正文。
REBASE_SETTLE_MS = 4_000
# 换址链路最多追几跳（旧域名 → 门户域名 → …），防止在域名池里无限打转。
MAX_REBASE_HOPS = 4


# 站方会随机掐断首连（Chromium 报 ERR_CONNECTION_CLOSED），同一地址新连接重试即可成功。
# 这类错误发生在导航阶段、走不到解析器，所以必须在这里重试；连接被拒/域名解析失败
# 等确定性错误不在名单内，仍然立即抛出，避免把真实故障拖成超时。
TRANSIENT_NAVIGATION_MARKERS = (
    "ERR_CONNECTION_CLOSED",
    "ERR_CONNECTION_RESET",
    "ERR_CONNECTION_ABORTED",
    "ERR_EMPTY_RESPONSE",
    "ERR_SOCKET_NOT_CONNECTED",
    "ERR_NETWORK_CHANGED",
    "ERR_TIMED_OUT",
)
NAVIGATION_ATTEMPTS = 3
NAVIGATION_RETRY_DELAY_MS = 1_500


_PADDLE_OCR_READER = PaddleOcrReader()


def _read_image_text(content: bytes) -> str:
    return _PADDLE_OCR_READER(content)


def _error_detail(exc: Exception) -> str:
    message = str(exc).strip()
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__


def _is_transient_navigation_error(exc: PlaywrightError) -> bool:
    message = str(exc)
    return any(marker in message for marker in TRANSIENT_NAVIGATION_MARKERS)


async def _goto_with_retry(
    page: Page,
    url: str,
    *,
    timeout_ms: int,
) -> None:
    """导航到目标地址；连接类抖动时换新连接重试。

    导航超时沿用原逻辑（页面可能已渲染出可用内容，交给后续解析判断）；
    确定性错误与重试用尽后的抖动错误原样抛出，由调用方记录失败原因。
    """
    for attempt in range(1, NAVIGATION_ATTEMPTS + 1):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            return
        except PlaywrightTimeoutError:
            return
        except PlaywrightError as exc:
            if (
                attempt == NAVIGATION_ATTEMPTS
                or not _is_transient_navigation_error(exc)
            ):
                raise
            await asyncio.sleep(NAVIGATION_RETRY_DELAY_MS / 1000)


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


def same_path(left: str, right: str) -> bool:
    """路径与查询串是否完全相同（域名换址判定只看路径，不看 host）。"""
    try:
        left_parts = urlsplit(left)
        right_parts = urlsplit(right)
    except ValueError:
        return False
    return (left_parts.path, left_parts.query) == (
        right_parts.path,
        right_parts.query,
    )


def rebase_path(source_url: str, landing_url: str) -> str:
    """把 source_url 的路径/查询串挂到 landing_url 的协议+主机+端口上。"""
    source_parts = urlsplit(source_url)
    landing_parts = urlsplit(landing_url)
    scheme = landing_parts.scheme or source_parts.scheme
    netloc = landing_parts.netloc
    return f"{scheme}://{netloc}{source_parts.path}" + (
        f"?{source_parts.query}" if source_parts.query else ""
    )


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
        insecure_context_factory: Callable[[], Awaitable[BrowserContext]] | None = None,
        login_context_factory: Callable[[], Awaitable[BrowserContext]] | None = None,
    ) -> None:
        self.context = context
        self.ocr_reader = ocr_reader or _read_image_text
        # 仅当站点在配置中显式授权（allow_invalid_certificate）时，才用该工厂
        # 另建一个 ignore_https_errors=True 的临时上下文；其它站点始终用严格上下文。
        self.insecure_context_factory = insecure_context_factory
        # 仅当站点在配置中显式授权（requires_login）时，才改用持久化登录上下文；
        # 其它站点始终用未登录的临时上下文，行为不变。
        self.login_context_factory = login_context_factory

    @asynccontextmanager
    async def _call_context(
        self,
        allow_invalid_certificate: bool,
        requires_login: bool = False,
    ) -> AsyncIterator[BrowserContext]:
        if requires_login and self.login_context_factory is not None:
            # 持久化上下文由 runtime 统一持有并在结束时关闭，这里只借用。
            yield await self.login_context_factory()
            return
        if not allow_invalid_certificate or self.insecure_context_factory is None:
            yield self.context
            return
        context = await self.insecure_context_factory()
        try:
            yield context
        finally:
            await context.close()

    async def collect(
        self,
        url: str,
        *,
        timeout_ms: int,
        settle_ms: int,
        include_image_ocr: bool = False,
        anchor_terms: tuple[str, ...] = (),
        data_marker_terms: tuple[str, ...] = (),
        allow_invalid_certificate: bool = False,
        requires_login: bool = False,
    ) -> tuple[Document, ...]:
        async with self._call_context(
            allow_invalid_certificate, requires_login
        ) as context:
            return await self._collect_in(
                context,
                url,
                timeout_ms=timeout_ms,
                settle_ms=settle_ms,
                include_image_ocr=include_image_ocr,
                anchor_terms=anchor_terms,
                data_marker_terms=data_marker_terms,
            )

    async def _collect_in(
        self,
        context: BrowserContext,
        url: str,
        *,
        timeout_ms: int,
        settle_ms: int,
        include_image_ocr: bool = False,
        anchor_terms: tuple[str, ...] = (),
        data_marker_terms: tuple[str, ...] = (),
    ) -> tuple[Document, ...]:
        page = await context.new_page()
        try:
            await _goto_with_retry(
                page,
                url,
                timeout_ms=timeout_ms,
            )
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
        allow_invalid_certificate: bool = False,
    ) -> tuple[Link, ...]:
        async with self._call_context(allow_invalid_certificate) as context:
            return await self._links_in(
                context,
                url,
                timeout_ms=timeout_ms,
                settle_ms=settle_ms,
            )

    async def _links_in(
        self,
        context: BrowserContext,
        url: str,
        *,
        timeout_ms: int,
        settle_ms: int,
    ) -> tuple[Link, ...]:
        page = await context.new_page()
        try:
            await _goto_with_retry(
                page,
                url,
                timeout_ms=timeout_ms,
            )
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
        # 站方整域换址：旧域名 301 到门户首页，真实文章仍在「新域名 + 原路径」。
        # 同一批新域名里也有的只是空壳（路径对但无正文），且每次 301 落点都不同，
        # 所以每轮都重新推导目标域名，直到拿到能通过锚点/期数校验的正文为止。
        tried_hosts: set[str] = set()
        for attempt in range(1, request.attempts + 1):
            try:
                documents = await self._collect_trusted(
                    source,
                    request,
                    include_image_ocr,
                    tried_hosts,
                )
            except FetchError as exc:
                last_error = exc.failure.code.value
                documents = ()
            last_documents = documents
            if documents and self._history_is_ready(source, documents):
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

    async def _collect_trusted(
        self,
        source: Source,
        request: FetchRequest,
        include_image_ocr: bool,
        tried_hosts: set[str],
    ) -> tuple[Document, ...]:
        """抓取并只保留可信文档；整域换址时沿跳转链继续找能出正文的域名。

        实测这类站点会连环换址：旧域名 → 门户域名（空壳）→ 又一个域名首页。
        因此不能只换一次，必须在同一轮内顺着落地域名一路追下去，直到拿到
        含锚点与期号行的正文；追满 `MAX_REBASE_HOPS` 次仍无正文才失败。
        """
        url = source.url
        for hop in range(MAX_REBASE_HOPS + 1):
            documents = await self._collect(source, url, request, include_image_ocr)
            trusted = self._trusted_or_empty(source, documents, url)
            if trusted and self._history_is_ready(source, trusted):
                return trusted
            target = self._rebase_target(source, documents)
            if not target:
                if url == source.url:
                    raise FetchError(
                        Failure(
                            ErrorCode.CROSS_DOMAIN,
                            context=(
                                ("source_url", source.url),
                                (
                                    "document_url",
                                    documents[0].url if documents else "",
                                ),
                            ),
                        )
                    )
                break
            host = urlsplit(target).netloc.casefold()
            if host in tried_hosts:
                break
            tried_hosts.add(host)
            url = target
        raise FetchError(
            Failure(
                ErrorCode.FETCH_FAILED,
                detail="rebase chain returned no article body",
                context=(("url", source.url),),
            )
        )

    @staticmethod
    def _trusted_or_empty(
        source: Source,
        documents: tuple[Document, ...],
        url: str,
    ) -> tuple[Document, ...]:
        """按当前访问地址筛出可信文档；跨域时返回空（由调用方决定是否追链）。"""
        try:
            return tuple(
                BrowserPageFetcher._trust_documents(
                    source,
                    documents,
                    "" if url == source.url else url,
                )
            )
        except FetchError:
            return ()

    async def _collect(
        self,
        source: Source,
        url: str,
        request: FetchRequest,
        include_image_ocr: bool,
    ) -> tuple[Document, ...]:
        return await self.browser.collect(
            url,
            timeout_ms=request.timeout_ms,
            settle_ms=self._settle_ms(request, url, source),
            include_image_ocr=include_image_ocr,
            anchor_terms=self._anchor_terms(source),
            data_marker_terms=(
                (source.data_marker or "九肖",) if include_image_ocr else ()
            ),
            allow_invalid_certificate=source.allow_invalid_certificate,
            # 仅配置显式声明 requires_login 的站点（正文「回复可见」）才使用
            # 持久化登录上下文；其余站点行为完全不变。
            requires_login=source.requires_login,
        )

    @staticmethod
    def _settle_ms(request: FetchRequest, url: str, source: Source) -> int:
        """换址重抓需要更长等待，页面脚本才会把正文渲染出来。

        这类站点 301 后先返回门户壳，正文由脚本二次写入；实测 1200ms 时
        只有空壳（锚点 0 命中），4000ms 才有正文。仅对「换址目标」放宽，
        原 URL 仍用配置的等待时间，避免拖慢其余站点。
        """
        if url != source.url:
            return max(request.settle_ms, REBASE_SETTLE_MS)
        return request.settle_ms

    @staticmethod
    def _anchor_terms(source: Source) -> tuple[str, ...]:
        if source.section_marker:
            return (source.section_marker,)
        return tuple(dict.fromkeys((source.name, *source.aliases)))

    @staticmethod
    def _rebase_target(
        source: Source,
        documents: tuple[Document, ...],
    ) -> str:
        """从落地文档推导换址重抓目标；无可信落地域名则返回空串（不重抓）。"""
        for document in documents:
            if document.method is DocumentMethod.BROWSER_FRAME:
                continue
            if same_origin(source.url, document.url):
                continue
            rebased = rebase_path(source.url, document.url)
            if rebased and rebased != source.url:
                return rebased
        return ""

    @staticmethod
    def _trust_documents(
        source: Source,
        documents: tuple[Document, ...],
        rebased_url: str = "",
    ) -> list[Document]:
        """只接受同源文档。

        换址重抓（rebased_url 非空）时，还要求文档路径与原路径完全一致，
        以证明抓到的是同一篇文章而不是门户首页；任何一条不满足即照旧失败。
        """
        expected = rebased_url or source.url
        trusted: list[Document] = []
        for document in documents:
            if same_origin(expected, document.url) and (
                not rebased_url or same_path(source.url, document.url)
            ):
                trusted.append(document)
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
        return trusted

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
