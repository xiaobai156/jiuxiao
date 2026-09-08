from __future__ import annotations

import json
import unittest

from v2.domain.errors import ErrorCode
from v2.domain.models import Document, DocumentMethod, Position, Source
from v2.fetchers.browser_page import (
    BrowserPageFetcher,
    PlaywrightBrowserClient,
    PlaywrightHttpClient,
)
from v2.fetchers.dynamic_article import (
    DynamicArticleFetcher,
    article_api_url,
    article_record_identity,
)
from v2.fetchers.list_detail import (
    ListDetailFetcher,
    ListDetailTopThreeFetcher,
)
from v2.fetchers.registry import (
    FetchError,
    FetchRequest,
    FetcherRegistry,
    HttpResponse,
    Link,
)
from v2.fetchers.static_page import StaticPageFetcher


def make_source(
    *,
    url: str = "https://example.test/article/manager/abc?url=x",
    fetcher: str = "dynamic_article",
    parser: str = "direct_nine",
    detail_link_keyword: str = "",
) -> Source:
    return Source(
        name="测试站",
        url=url,
        position=Position.BOTTOM,
        section_marker="测试站",
        fetcher=fetcher,
        parser=parser,
        detail_link_keyword=detail_link_keyword,
    )


class FakeHttpClient:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[str] = []

    async def get(
        self,
        url: str,
        *,
        timeout_ms: int,
        headers: tuple[tuple[str, str], ...],
    ) -> HttpResponse:
        self.calls.append(url)
        if not self.responses:
            raise AssertionError("unexpected HTTP request")
        return self.responses.pop(0)


class FakeBrowserClient:
    def __init__(
        self,
        *,
        documents: tuple[Document, ...] = (),
        document_batches: list[tuple[Document, ...]] | None = None,
        ocr_documents: tuple[Document, ...] = (),
        links: tuple[Link, ...] = (),
        link_batches: list[tuple[Link, ...]] | None = None,
    ) -> None:
        self.documents = documents
        self.document_batches = (
            list(document_batches) if document_batches is not None else None
        )
        self.ocr_documents = ocr_documents
        self.available_links = links
        self.link_batches = (
            list(link_batches) if link_batches is not None else None
        )
        self.collect_calls: list[str] = []
        self.ocr_requests: list[bool] = []
        self.link_calls: list[str] = []

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
        self.collect_calls.append(url)
        self.ocr_requests.append(include_image_ocr)
        documents = (
            self.document_batches.pop(0)
            if self.document_batches is not None
            else self.documents
        )
        return (
            *documents,
            *(self.ocr_documents if include_image_ocr else ()),
        )

    async def links(
        self,
        url: str,
        *,
        timeout_ms: int,
        settle_ms: int,
    ) -> tuple[Link, ...]:
        self.link_calls.append(url)
        return (
            self.link_batches.pop(0)
            if self.link_batches is not None
            else self.available_links
        )


class FakeLocator:
    def __init__(
        self,
        *,
        text: str = "",
        scripts: list[str] | None = None,
        links: list[dict[str, str]] | None = None,
    ) -> None:
        self.text = text
        self.scripts = scripts or []
        self.link_values = links or []

    async def inner_text(self, *, timeout: int) -> str:
        return self.text

    async def all_text_contents(self) -> list[str]:
        return self.scripts

    async def evaluate_all(self, script: str) -> list[dict[str, str]]:
        return self.link_values


class FakeImageItem:
    def __init__(self, content: bytes) -> None:
        self.content = content

    async def screenshot(self, *, timeout: int) -> bytes:
        return self.content


class FakeImageLocator:
    def __init__(
        self,
        candidates: list[dict[str, int]],
        contents: dict[int, bytes],
    ) -> None:
        self.candidates = candidates
        self.contents = contents

    async def evaluate_all(self, script: str) -> list[dict[str, int]]:
        return self.candidates

    def nth(self, index: int) -> FakeImageItem:
        return FakeImageItem(self.contents[index])


class FakeFrame:
    def __init__(self, url: str, text: str) -> None:
        self.url = url
        self.body = FakeLocator(text=text)

    def locator(self, selector: str) -> FakeLocator:
        if selector != "body":
            raise AssertionError(selector)
        return self.body


class FakePage(FakeFrame):
    def __init__(
        self,
        url: str,
        text: str,
        *,
        frames: list[FakeFrame] | None = None,
        scripts: list[str] | None = None,
        links: list[dict[str, str]] | None = None,
        images: list[dict[str, int]] | None = None,
        image_contents: dict[int, bytes] | None = None,
    ) -> None:
        super().__init__(url, text)
        self.main_frame = self
        self.frames = [self, *(frames or [])]
        self.script_locator = FakeLocator(scripts=scripts)
        self.link_locator = FakeLocator(links=links)
        self.image_locator = FakeImageLocator(
            images or [],
            image_contents or {},
        )
        self.closed = False
        self.waited: list[int] = []
        self.wait_functions: list[int] = []

    async def goto(
        self,
        url: str,
        *,
        wait_until: str,
        timeout: int,
    ) -> None:
        self.url = url

    async def wait_for_timeout(self, milliseconds: int) -> None:
        self.waited.append(milliseconds)

    async def wait_for_function(self, script: str, *, timeout: int) -> None:
        self.wait_functions.append(timeout)

    def locator(self, selector: str) -> FakeLocator:
        if selector == "script":
            return self.script_locator
        if selector == "a":
            return self.link_locator
        if selector == "img":
            return self.image_locator
        return super().locator(selector)

    async def close(self) -> None:
        self.closed = True


class FakePlaywrightContext:
    def __init__(self, pages: list[FakePage], request: object | None = None) -> None:
        self.pages = list(pages)
        self.request = request

    async def new_page(self) -> FakePage:
        if not self.pages:
            raise AssertionError("unexpected page")
        return self.pages.pop(0)


class FakeApiResponse:
    def __init__(self, status: int, text: str, url: str) -> None:
        self.status = status
        self._text = text
        self.url = url

    async def text(self) -> str:
        return self._text


class FakeApiRequest:
    def __init__(
        self,
        response: FakeApiResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = response
        self.error = error

    async def get(
        self,
        url: str,
        *,
        timeout: int,
        headers: dict[str, str],
    ) -> FakeApiResponse:
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


class FetcherRegistryTests(unittest.TestCase):
    def test_registry_rejects_duplicate_and_unknown_keys(self) -> None:
        registry = FetcherRegistry()
        fetcher = StaticPageFetcher(FakeHttpClient([]))
        registry.register("static_page", fetcher)

        self.assertIs(registry.resolve("static_page"), fetcher)
        with self.assertRaises(ValueError):
            registry.register("static_page", fetcher)
        with self.assertRaises(KeyError):
            registry.resolve("missing")

    def test_fetch_request_rejects_invalid_limits(self) -> None:
        for kwargs in (
            {"issues": ()},
            {"issues": (210, 210)},
            {"issues": (0,)},
            {"issues": (210,), "attempts": 0},
            {"issues": (210,), "timeout_ms": 0},
            {"issues": (210,), "settle_ms": -1},
        ):
            with self.assertRaises(ValueError):
                FetchRequest(**kwargs)


class PlaywrightAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_browser_adapter_creates_ranked_in_memory_ocr_documents(
        self,
    ) -> None:
        page = FakePage(
            "https://example.test/page",
            "body text",
            images=[
                {"index": 4, "width": 800, "height": 250},
                {
                    "index": 3,
                    "width": 787,
                    "height": 541,
                    "anchorLine": "澳门公式 九肖",
                    "anchorTerm": "澳门公式",
                    "dataMarkerLine": "嫦娥彩报 无错九肖",
                    "anchorIndex": 4,
                    "blockStart": 4,
                    "blockEnd": 9,
                },
            ],
            image_contents={3: b"content", 4: b"advert"},
        )
        reader_calls: list[bytes] = []

        def reader(content: bytes) -> str:
            reader_calls.append(content)
            return (
                "210期：鼠牛虎兔龙蛇马羊猴"
                if content == b"content"
                else ""
            )

        client = PlaywrightBrowserClient(
            FakePlaywrightContext([page]),
            ocr_reader=reader,
        )

        documents = await client.collect(
            "https://example.test/page",
            timeout_ms=20_000,
            settle_ms=0,
            include_image_ocr=True,
            anchor_terms=("澳门公式",),
            data_marker_terms=("九肖",),
        )

        ocr_documents = tuple(
            document
            for document in documents
            if document.method is DocumentMethod.IMAGE_OCR
        )
        self.assertEqual(reader_calls, [b"content", b"advert"])
        self.assertEqual(len(ocr_documents), 1)
        self.assertEqual(ocr_documents[0].label, "image-ocr:3")
        self.assertEqual(
            dict(ocr_documents[0].metadata)["image_index"],
            "3",
        )
        evidence = dict(ocr_documents[0].metadata)
        self.assertEqual(evidence["parent_url"], "https://example.test/page")
        self.assertEqual(evidence["anchor_line"], "澳门公式 九肖")
        self.assertEqual(evidence["anchor_term"], "澳门公式")
        self.assertEqual(
            evidence["data_marker_line"],
            "嫦娥彩报 无错九肖",
        )
        self.assertEqual(evidence["block_start"], "4")
        self.assertEqual(evidence["block_end"], "9")
        self.assertEqual(page.wait_functions, [10_000])
        self.assertTrue(page.closed)

    async def test_http_adapter_returns_response_and_contains_exceptions(
        self,
    ) -> None:
        response = FakeApiResponse(200, "body", "https://example.test/final")
        context = FakePlaywrightContext(
            [],
            request=FakeApiRequest(response=response),
        )

        result = await PlaywrightHttpClient(context).get(
            "https://example.test",
            timeout_ms=1000,
            headers=(("Accept", "text/plain"),),
        )
        self.assertEqual(result.status, 200)
        self.assertEqual(result.text, "body")
        self.assertEqual(result.url, "https://example.test/final")

        failing_context = FakePlaywrightContext(
            [],
            request=FakeApiRequest(error=RuntimeError("network")),
        )
        result = await PlaywrightHttpClient(failing_context).get(
            "https://example.test",
            timeout_ms=1000,
            headers=(),
        )
        self.assertIsNone(result.status)
        self.assertEqual(result.error, "RuntimeError")

    async def test_browser_adapter_collects_dom_frames_scripts_and_links(
        self,
    ) -> None:
        frame = FakeFrame("https://example.test/frame", "frame text")
        page = FakePage(
            "https://example.test/page",
            "body text",
            frames=[FakeFrame("https://example.test/dupe", "body text"), frame],
            scripts=["", "script text"],
        )
        link_page = FakePage(
            "https://example.test/list",
            "list",
            links=[
                {"href": "/detail", "text": "详情"},
                {"href": "", "text": "空"},
            ],
        )
        client = PlaywrightBrowserClient(
            FakePlaywrightContext([page, link_page])
        )

        documents = await client.collect(
            "https://example.test/page",
            timeout_ms=1000,
            settle_ms=10,
        )
        links = await client.links(
            "https://example.test/list",
            timeout_ms=1000,
            settle_ms=0,
        )

        self.assertEqual(
            [document.method for document in documents],
            [
                DocumentMethod.BROWSER_DOM,
                DocumentMethod.BROWSER_FRAME,
                DocumentMethod.SCRIPT,
            ],
        )
        self.assertEqual(documents[1].text, "frame text")
        self.assertEqual(links, (Link("https://example.test/detail", "详情"),))
        self.assertTrue(page.closed)
        self.assertTrue(link_page.closed)


class StaticPageFetcherTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_returns_raw_document_without_parsing(self) -> None:
        response = HttpResponse(
            status=200,
            text="<html><body>210期：鼠牛虎兔龙蛇马羊猴</body></html>",
            url="https://example.test/page",
        )
        fetcher = StaticPageFetcher(FakeHttpClient([response]))

        documents = await fetcher.fetch(
            make_source(url=response.url, fetcher="static_page"),
            FetchRequest((210,)),
        )

        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].method, DocumentMethod.STATIC_PAGE)
        self.assertIn("<html>", documents[0].text)

    async def test_network_failure_retries_then_fails_without_document(self) -> None:
        responses = [
            HttpResponse(None, "", "https://example.test/page", "network")
            for _ in range(3)
        ]
        client = FakeHttpClient(responses)
        fetcher = StaticPageFetcher(client)

        with self.assertRaises(FetchError) as raised:
            await fetcher.fetch(
                make_source(
                    url="https://example.test/page",
                    fetcher="static_page",
                ),
                FetchRequest((210,), attempts=3),
            )

        self.assertEqual(raised.exception.failure.code, ErrorCode.FETCH_FAILED)
        self.assertEqual(len(client.calls), 3)

    async def test_recoverable_http_status_retries_but_500_fails_immediately(self) -> None:
        retrying = FakeHttpClient(
            [
                HttpResponse(503, "", "https://example.test/page"),
                HttpResponse(200, "ready", "https://example.test/page"),
            ]
        )
        documents = await StaticPageFetcher(retrying).fetch(
            make_source(url="https://example.test/page", fetcher="static_page"),
            FetchRequest((210,)),
        )
        self.assertEqual(documents[0].text, "ready")
        self.assertEqual(len(retrying.calls), 2)

        failing = FakeHttpClient(
            [HttpResponse(500, "error", "https://example.test/page")]
        )
        with self.assertRaises(FetchError) as raised:
            await StaticPageFetcher(failing).fetch(
                make_source(
                    url="https://example.test/page",
                    fetcher="static_page",
                ),
                FetchRequest((210,)),
            )
        self.assertEqual(raised.exception.failure.code, ErrorCode.HTTP_ERROR)
        self.assertEqual(len(failing.calls), 1)


class DynamicArticleFetcherTests(unittest.IsolatedAsyncioTestCase):
    def test_article_identity_and_api_url_are_deterministic(self) -> None:
        source = make_source(
            url="https://example.test/article/admin/abc?url=x",
        )

        self.assertEqual(
            article_record_identity(source.url),
            ("admin", "abc"),
        )
        self.assertEqual(
            article_api_url(source),
            "https://example.test/api/proxy/manager-articles/abc",
        )

    async def test_api_selects_exact_record_and_preserves_provenance(self) -> None:
        payload = {
            "items": [
                {"id": "other", "html": "wrong"},
                {
                    "id": "abc",
                    "title": "测试站",
                    "html": "<p>210期：鼠牛虎兔龙蛇马羊猴</p>",
                },
            ]
        }
        response = HttpResponse(
            200,
            json.dumps(payload, ensure_ascii=False),
            "https://example.test/api/proxy/manager-articles/abc",
        )
        fetcher = DynamicArticleFetcher(
            FakeHttpClient([response]),
            FakeBrowserClient(),
        )

        documents = await fetcher.fetch(make_source(), FetchRequest((210,)))

        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].method, DocumentMethod.DYNAMIC_API)
        metadata = dict(documents[0].metadata)
        self.assertEqual(metadata["article_id"], "abc")
        self.assertEqual(metadata["record_path"], "$.items[1]")
        self.assertIn("210期", documents[0].text)

    async def test_mismatched_api_record_fails_without_browser_fallback(self) -> None:
        payload = {"id": "other", "html": "210期"}
        browser = FakeBrowserClient(
            documents=(
                Document(
                    "browser-dom",
                    "https://example.test/article/manager/abc",
                    "browser",
                    DocumentMethod.BROWSER_DOM,
                ),
            )
        )
        fetcher = DynamicArticleFetcher(
            FakeHttpClient(
                [
                    HttpResponse(
                        200,
                        json.dumps(payload),
                        "https://example.test/api",
                    )
                ]
            ),
            browser,
        )

        with self.assertRaises(FetchError) as raised:
            await fetcher.fetch(make_source(), FetchRequest((210,)))

        self.assertEqual(
            raised.exception.failure.code,
            ErrorCode.API_RECORD_MISMATCH,
        )
        self.assertEqual(browser.collect_calls, [])

    async def test_duplicate_id_invalid_json_and_bodyless_payload_fail_safely(
        self,
    ) -> None:
        duplicate_payload = {
            "items": [
                {"id": "abc", "html": "first"},
                {"id": "abc", "html": "second"},
            ]
        }
        with self.assertRaises(FetchError) as raised:
            await DynamicArticleFetcher(
                FakeHttpClient(
                    [
                        HttpResponse(
                            200,
                            json.dumps(duplicate_payload),
                            "https://example.test/api",
                        )
                    ]
                ),
                FakeBrowserClient(),
            ).fetch(make_source(), FetchRequest((210,)))
        self.assertEqual(
            raised.exception.failure.code,
            ErrorCode.API_RECORD_MISMATCH,
        )

        with self.assertRaises(FetchError) as raised:
            await DynamicArticleFetcher(
                FakeHttpClient(
                    [HttpResponse(200, "not-json", "https://example.test/api")]
                ),
                FakeBrowserClient(),
            ).fetch(make_source(), FetchRequest((210,)))
        self.assertEqual(
            raised.exception.failure.code,
            ErrorCode.SOURCE_UNTRUSTED,
        )

        browser_document = Document(
            "browser-dom",
            "https://example.test/article/manager/abc?url=x",
            "browser",
            DocumentMethod.BROWSER_DOM,
        )
        browser = FakeBrowserClient(documents=(browser_document,))
        documents = await DynamicArticleFetcher(
            FakeHttpClient(
                [HttpResponse(200, "{}", "https://example.test/api")]
            ),
            browser,
        ).fetch(make_source(), FetchRequest((210,)))
        self.assertEqual(documents, (browser_document,))

    async def test_404_or_empty_200_use_browser_but_500_and_network_do_not(self) -> None:
        browser_document = Document(
            "browser-dom",
            "https://example.test/article/manager/abc?url=x",
            "测试站\n210期",
            DocumentMethod.BROWSER_DOM,
        )
        for response in (
            HttpResponse(404, "", "https://example.test/api"),
            HttpResponse(200, "", "https://example.test/api"),
        ):
            browser = FakeBrowserClient(documents=(browser_document,))
            documents = await DynamicArticleFetcher(
                FakeHttpClient([response]),
                browser,
            ).fetch(make_source(), FetchRequest((210,)))
            self.assertEqual(documents, (browser_document,))
            self.assertEqual(len(browser.collect_calls), 1)

        for response, code in (
            (
                HttpResponse(500, "error", "https://example.test/api"),
                ErrorCode.HTTP_ERROR,
            ),
            (
                HttpResponse(None, "", "https://example.test/api", "network"),
                ErrorCode.FETCH_FAILED,
            ),
        ):
            browser = FakeBrowserClient(documents=(browser_document,))
            with self.assertRaises(FetchError) as raised:
                await DynamicArticleFetcher(
                    FakeHttpClient([response] * 5),
                    browser,
                ).fetch(make_source(), FetchRequest((210,)))
            self.assertEqual(raised.exception.failure.code, code)
            self.assertEqual(browser.collect_calls, [])


class BrowserPageFetcherTests(unittest.IsolatedAsyncioTestCase):
    async def test_browser_retries_then_reports_empty_or_exception_failure(
        self,
    ) -> None:
        empty = FakeBrowserClient(document_batches=[(), ()])
        with self.assertRaises(FetchError) as raised:
            await BrowserPageFetcher(empty).fetch(
                make_source(
                    url="https://example.test/page",
                    fetcher="browser_page",
                ),
                FetchRequest((210,), attempts=2),
            )
        self.assertEqual(raised.exception.failure.code, ErrorCode.FETCH_FAILED)
        self.assertEqual(len(empty.collect_calls), 2)

        class RaisingBrowser(FakeBrowserClient):
            async def collect(self, *args, **kwargs):
                self.collect_calls.append(str(args[0]))
                raise RuntimeError("browser unavailable")

        failing = RaisingBrowser()
        with self.assertRaises(FetchError) as raised:
            await BrowserPageFetcher(failing).fetch(
                make_source(
                    url="https://example.test/page",
                    fetcher="browser_page",
                ),
                FetchRequest((210,), attempts=2),
            )
        self.assertEqual(raised.exception.failure.detail, "RuntimeError")
        self.assertEqual(len(failing.collect_calls), 2)

    async def test_browser_retries_empty_collection_before_success(self) -> None:
        document = Document(
            "browser-dom",
            "https://example.test/page",
            "content",
            DocumentMethod.BROWSER_DOM,
        )
        browser = FakeBrowserClient(document_batches=[(), (document,)])

        documents = await BrowserPageFetcher(browser).fetch(
            make_source(
                url="https://example.test/page",
                fetcher="browser_page",
            ),
            FetchRequest((210,), attempts=2),
        )

        self.assertEqual(documents, (document,))
        self.assertEqual(len(browser.collect_calls), 2)

    async def test_browser_retries_nonempty_spa_shell_until_history_ready(
        self,
    ) -> None:
        shell = Document(
            "browser-dom",
            "https://example.test/page",
            "用户主页\n测试站",
            DocumentMethod.BROWSER_DOM,
        )
        ready = Document(
            "browser-dom",
            "https://example.test/page",
            "用户主页\n测试站\n210期：正文已加载",
            DocumentMethod.BROWSER_DOM,
        )
        browser = FakeBrowserClient(document_batches=[(shell,), (ready,)])

        documents = await BrowserPageFetcher(browser).fetch(
            make_source(
                url="https://example.test/page",
                fetcher="browser_page",
            ),
            FetchRequest((210,), attempts=2),
        )

        self.assertEqual(documents, (ready,))
        self.assertEqual(len(browser.collect_calls), 2)

    async def test_browser_returns_last_nonempty_shell_after_retry_budget(
        self,
    ) -> None:
        shell = Document(
            "browser-dom",
            "https://example.test/page",
            "登录后查看",
            DocumentMethod.BROWSER_DOM,
        )
        browser = FakeBrowserClient(document_batches=[(shell,), (shell,)])

        documents = await BrowserPageFetcher(browser).fetch(
            make_source(
                url="https://example.test/page",
                fetcher="browser_page",
            ),
            FetchRequest((210,), attempts=2),
        )

        self.assertEqual(documents, (shell,))
        self.assertEqual(len(browser.collect_calls), 2)

    async def test_browser_requests_ocr_documents_only_from_parser_config(
        self,
    ) -> None:
        dom = Document(
            "browser-dom",
            "https://example.test/page",
            "测试站\n210期\n栏目标题",
            DocumentMethod.BROWSER_DOM,
        )
        ocr = Document(
            "image-ocr:0",
            "https://example.test/page",
            "210期：嫦娥公式【鼠牛虎兔龙蛇马羊猴】",
            DocumentMethod.IMAGE_OCR,
        )
        browser = FakeBrowserClient(documents=(dom,), ocr_documents=(ocr,))

        normal = await BrowserPageFetcher(browser).fetch(
            make_source(
                url="https://example.test/page",
                fetcher="browser_page",
            ),
            FetchRequest((210,)),
        )
        with_ocr = await BrowserPageFetcher(browser).fetch(
            make_source(
                url="https://example.test/page",
                fetcher="browser_page",
                parser="image_ocr",
            ),
            FetchRequest((210,)),
        )

        self.assertEqual(normal, (dom,))
        self.assertEqual(with_ocr, (dom, ocr))
        self.assertEqual(browser.ocr_requests, [False, True])

    async def test_browser_rejects_cross_domain_final_document(self) -> None:
        browser = FakeBrowserClient(
            documents=(
                Document(
                    "browser-dom",
                    "https://evil.test/page",
                    "content",
                    DocumentMethod.BROWSER_DOM,
                ),
            )
        )

        with self.assertRaises(FetchError) as raised:
            await BrowserPageFetcher(browser).fetch(
                make_source(
                    url="https://example.test/page",
                    fetcher="browser_page",
                ),
                FetchRequest((210,)),
            )

        self.assertEqual(raised.exception.failure.code, ErrorCode.CROSS_DOMAIN)

    async def test_browser_discards_untrusted_cross_domain_frame(self) -> None:
        main = Document(
            "browser-dom",
            "https://example.test/page",
            "测试站\n210期：同源正文",
            DocumentMethod.BROWSER_DOM,
        )
        frame = Document(
            "browser-frame:1",
            "https://widgets.test/live",
            "210期：无关开奖组件",
            DocumentMethod.BROWSER_FRAME,
        )
        browser = FakeBrowserClient(documents=(main, frame))

        documents = await BrowserPageFetcher(browser).fetch(
            make_source(
                url="https://example.test/page",
                fetcher="browser_page",
            ),
            FetchRequest((210,)),
        )

        self.assertEqual(documents, (main,))
        self.assertEqual(len(browser.collect_calls), 1)


class ListDetailFetcherTests(unittest.IsolatedAsyncioTestCase):
    async def test_history_request_uses_latest_matching_detail_once(self) -> None:
        detail_document = Document(
            "browser-dom",
            "https://example.test/detail/211",
            "测试站\n210期\n209期",
            DocumentMethod.BROWSER_DOM,
        )
        browser = FakeBrowserClient(
            links=(
                Link("https://example.test/detail/207", "207期：目标九肖"),
                Link("https://example.test/detail/211", "211期：目标九肖"),
            ),
            documents=(detail_document,),
        )
        source = make_source(
            url="https://example.test/list",
            fetcher="list_detail",
            detail_link_keyword="目标九肖",
        )

        documents = await ListDetailFetcher(browser).fetch(
            source,
            FetchRequest((210, 209), history_mode=True),
        )

        self.assertEqual(documents, (detail_document,))
        self.assertEqual(
            browser.collect_calls,
            ["https://example.test/detail/211"],
        )

    async def test_list_detail_follows_controlled_same_page_pagination(
        self,
    ) -> None:
        detail_document = Document(
            "browser-dom",
            "https://example.test/detail/210",
            "测试站\n210期",
            DocumentMethod.BROWSER_DOM,
        )
        browser = FakeBrowserClient(
            link_batches=[
                (
                    Link(
                        "https://example.test/list?id=7&page=2",
                        "下一页",
                    ),
                ),
                (
                    Link(
                        "https://example.test/detail/210",
                        "210期：目标九肖",
                    ),
                    Link(
                        "https://example.test/list?id=7&page=3",
                        "下一页",
                    ),
                ),
            ],
            documents=(detail_document,),
        )
        source = make_source(
            url="https://example.test/list?id=7",
            fetcher="list_detail",
            detail_link_keyword="目标九肖",
        )

        documents = await ListDetailFetcher(browser).fetch(
            source,
            FetchRequest((210,)),
        )

        self.assertEqual(documents, (detail_document,))
        self.assertEqual(
            browser.link_calls,
            [
                "https://example.test/list?id=7",
                "https://example.test/list?id=7&page=2",
            ],
        )

    async def test_list_detail_stops_at_three_pages_and_keeps_page_three_target(
        self,
    ) -> None:
        detail_document = Document(
            "browser-dom",
            "https://example.test/detail/210",
            "测试站\n210期：测试站九肖【鼠牛虎兔龙蛇马羊猴】",
            DocumentMethod.BROWSER_DOM,
        )
        browser = FakeBrowserClient(
            link_batches=[
                (
                    Link(
                        "https://example.test/list?id=7&page=2",
                        "下一页",
                    ),
                ),
                (
                    Link(
                        "https://example.test/list?id=7&page=3",
                        "下一页",
                    ),
                ),
                (
                    Link(
                        "https://example.test/detail/210",
                        "210期：目标九肖",
                    ),
                    Link(
                        "https://example.test/list?id=7&page=4",
                        "下一页",
                    ),
                ),
            ],
            documents=(detail_document,),
        )
        source = make_source(
            url="https://example.test/list?id=7",
            fetcher="list_detail",
            detail_link_keyword="目标九肖",
        )

        documents = await ListDetailTopThreeFetcher(browser).fetch(
            source,
            FetchRequest((210,)),
        )

        self.assertEqual(documents, (detail_document,))
        self.assertEqual(
            browser.link_calls,
            [
                "https://example.test/list?id=7",
                "https://example.test/list?id=7&page=2",
                "https://example.test/list?id=7&page=3",
            ],
        )

    async def test_list_detail_reports_missing_after_three_pages(self) -> None:
        browser = FakeBrowserClient(
            link_batches=[
                (
                    Link(
                        "https://example.test/list?id=7&page=2",
                        "下一页",
                    ),
                ),
                (
                    Link(
                        "https://example.test/list?id=7&page=3",
                        "下一页",
                    ),
                ),
                (
                    Link(
                        "https://example.test/list?id=7&page=4",
                        "下一页",
                    ),
                ),
            ]
        )
        source = make_source(
            url="https://example.test/list?id=7",
            fetcher="list_detail",
            detail_link_keyword="目标九肖",
        )

        with self.assertRaises(FetchError) as raised:
            await ListDetailTopThreeFetcher(browser).fetch(
                source,
                FetchRequest((210,)),
            )

        self.assertEqual(
            raised.exception.failure.code,
            ErrorCode.ISSUE_MISSING,
        )
        self.assertEqual(len(browser.link_calls), 3)

    async def test_multi_issue_fetch_keeps_found_details_when_one_is_missing(
        self,
    ) -> None:
        detail_document = Document(
            "browser-dom",
            "https://example.test/detail/210",
            "测试站\n210期",
            DocumentMethod.BROWSER_DOM,
        )
        browser = FakeBrowserClient(
            links=(
                Link("https://example.test/detail/210", "210期：目标九肖"),
            ),
            documents=(detail_document,),
        )
        source = make_source(
            url="https://example.test/list",
            fetcher="list_detail",
            detail_link_keyword="目标九肖",
        )

        documents = await ListDetailFetcher(browser).fetch(
            source,
            FetchRequest((210, 209)),
        )

        self.assertEqual(documents, (detail_document,))
        self.assertEqual(
            browser.collect_calls,
            ["https://example.test/detail/210"],
        )

    async def test_list_detail_uses_one_exact_same_domain_issue_link(self) -> None:
        detail_document = Document(
            "browser-dom",
            "https://example.test/detail/210",
            "测试站\n210期",
            DocumentMethod.BROWSER_DOM,
        )
        browser = FakeBrowserClient(
            links=(
                Link("https://example.test/detail/209", "209期：金瓯无缺九肖"),
                Link("https://example.test/detail/210", "210期：金瓯无缺九肖"),
                Link("https://example.test/detail/ad", "210期：其他广告"),
            ),
            documents=(detail_document,),
        )
        source = make_source(
            url="https://example.test/list",
            fetcher="list_detail",
            detail_link_keyword="金瓯无缺九肖",
        )

        documents = await ListDetailFetcher(browser).fetch(
            source,
            FetchRequest((210,)),
        )

        self.assertEqual(documents, (detail_document,))
        self.assertEqual(
            browser.collect_calls,
            ["https://example.test/detail/210"],
        )

    async def test_list_detail_rejects_conflict_and_cross_domain(self) -> None:
        source = make_source(
            url="https://example.test/list",
            fetcher="list_detail",
            detail_link_keyword="目标九肖",
        )
        conflict = FakeBrowserClient(
            links=(
                Link("https://example.test/a", "210期：目标九肖"),
                Link("https://example.test/b", "210期：目标九肖"),
            )
        )
        with self.assertRaises(FetchError) as raised:
            await ListDetailFetcher(conflict).fetch(
                source,
                FetchRequest((210,)),
            )
        self.assertEqual(
            raised.exception.failure.code,
            ErrorCode.CANDIDATE_CONFLICT,
        )

        cross_domain = FakeBrowserClient(
            links=(Link("https://evil.test/a", "210期：目标九肖"),)
        )
        with self.assertRaises(FetchError) as raised:
            await ListDetailFetcher(cross_domain).fetch(
                source,
                FetchRequest((210,)),
            )
        self.assertEqual(raised.exception.failure.code, ErrorCode.CROSS_DOMAIN)


if __name__ == "__main__":
    unittest.main()
