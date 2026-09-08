from __future__ import annotations

import asyncio
import importlib.util
import sys
from dataclasses import replace
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if "v2" not in sys.modules:
    specification = importlib.util.spec_from_file_location(
        "v2",
        PROJECT_ROOT / "__init__.py",
        submodule_search_locations=[str(PROJECT_ROOT)],
    )
    assert specification is not None and specification.loader is not None
    package = importlib.util.module_from_spec(specification)
    sys.modules["v2"] = package
    specification.loader.exec_module(package)


from v2.domain.errors import ErrorCode, Failure  # noqa: E402
from v2.config.schema import source_to_dict  # noqa: E402
from v2.config.main_list import MainListCatalog  # noqa: E402
from v2.config.repository import SourceRepository  # noqa: E402
from v2.domain.identity import source_identity  # noqa: E402
from v2.domain.models import (  # noqa: E402
    Document,
    DocumentMethod,
    Evidence,
    History,
    Position,
    Record,
    RecordSet,
    Result,
    ResultState,
    Source,
)
from v2.fetchers.browser_page import (  # noqa: E402
    PlaywrightHttpClient,
    same_origin,
)
from v2.fetchers.dynamic_article import DynamicArticleFetcher  # noqa: E402
from v2.fetchers.list_detail import (  # noqa: E402
    ListDetailCurrentFetcher,
    ListDetailFetcher,
    is_list_page_url,
)
from v2.fetchers.liuiuqu import LiuiuquFetcher  # noqa: E402
from v2.fetchers.registry import (  # noqa: E402
    FetchError,
    FetchRequest,
    HttpResponse,
    Link,
)
from v2.fetchers.static_page import StaticPageFetcher  # noqa: E402
from v2.parsers.direct_nine import DirectNineParser  # noqa: E402
from v2.parsers.grouped import GroupedParser  # noqa: E402
from v2.parsers.image_ocr import ImageOcrParser  # noqa: E402
from v2.parsers.split_line import SplitLineParser  # noqa: E402
from v2.parsers.custom.liuiuqu import LiuiuquParser  # noqa: E402
from v2.parsers.custom.formula_next_issue_ocr import (  # noqa: E402
    FormulaNextIssueOcrParser,
)
from v2.parsers.custom.single_season_complement import (  # noqa: E402
    SingleSeasonComplementParser,
)
from v2.parsers.registry import LOCKED_MARKERS, ParseError  # noqa: E402
from v2.services.run_modes import CrawlRunService  # noqa: E402
from v2.services.duplicate import (  # noqa: E402
    BaselineHistory,
    DuplicateChecker,
    DuplicateState,
)
from v2.services.onboarding import OnboardingService, OnboardingState  # noqa: E402
from v2.storage.reports import ReportRepository  # noqa: E402
from v2.storage.cache import CacheRepository  # noqa: E402
from v2.validator import ValidationError, Validator  # noqa: E402
from v2 import runtime  # noqa: E402


def source(
    *,
    url: str = "https://example.test/topic/1.html",
    fetcher: str = "static_page",
) -> Source:
    return Source(
        name="测试目录",
        url=url,
        position=Position.TOP,
        section_marker="九肖中特",
        fetcher=fetcher,
        parser="direct_nine",
    )


class StubHttp:
    def __init__(self, response: HttpResponse) -> None:
        self.response = response

    async def get(self, *_args, **_kwargs) -> HttpResponse:
        return self.response


class StubBrowser:
    def __init__(self, documents: tuple[Document, ...]) -> None:
        self.documents = documents

    async def collect(self, *_args, **_kwargs) -> tuple[Document, ...]:
        return self.documents


def test_dynamic_browser_fallback_requires_exact_article_id() -> None:
    target = source(
        url="https://example.test/article/admin/abc?url=x",
        fetcher="dynamic_article",
    )
    browser = StubBrowser(
        (
            Document(
                label="browser-dom",
                url="https://example.test/article/admin/abc0?url=x",
                text="九肖中特\n236期：九肖【鼠牛虎兔龙蛇马羊猴】",
                method=DocumentMethod.BROWSER_DOM,
            ),
        )
    )
    fetcher = DynamicArticleFetcher(
        StubHttp(HttpResponse(404, "", target.url)),
        browser,
    )

    with pytest.raises(FetchError) as captured:
        asyncio.run(fetcher.fetch(target, FetchRequest((236,), attempts=1)))

    assert captured.value.failure.code is ErrorCode.API_RECORD_MISMATCH


def test_static_http_rejects_cross_domain_redirect() -> None:
    target = source()
    fetcher = StaticPageFetcher(
        StubHttp(
            HttpResponse(
                200,
                "九肖中特\n236期：九肖【鼠牛虎兔龙蛇马羊猴】",
                "https://other.test/topic/1.html",
            )
        )
    )

    with pytest.raises(FetchError) as captured:
        asyncio.run(fetcher.fetch(target, FetchRequest((236,), attempts=1)))

    assert captured.value.failure.code is ErrorCode.CROSS_DOMAIN


def test_liuiuqu_retries_a_malformed_200_json_response() -> None:
    target = replace(
        source(fetcher="liuiuqu"),
        api_url="https://example.test/api/liuiuqu",
    )

    class SequenceHttp:
        def __init__(self) -> None:
            self.calls = 0
            self.headers: tuple[tuple[str, str], ...] = ()

        async def post(self, *_args, **_kwargs) -> HttpResponse:
            self.calls += 1
            self.headers = _kwargs["headers"]
            text = "upstream TLS error{}" if self.calls == 1 else "{}"
            return HttpResponse(200, text, target.api_url)

    http = SequenceHttp()

    documents = asyncio.run(
        LiuiuquFetcher(http).fetch(
            target,
            FetchRequest((236,), attempts=2),
        )
    )

    assert http.calls == 2
    assert ("Connection", "close") in http.headers
    assert documents[0].text == "{}"


@pytest.mark.parametrize(
    ("response", "expected"),
    (
        (
            HttpResponse(200, "upstream TLS error{}", "https://example.test/api"),
            ErrorCode.SOURCE_UNTRUSTED,
        ),
        (
            HttpResponse(200, "", "https://example.test/api"),
            ErrorCode.SOURCE_UNTRUSTED,
        ),
        (
            HttpResponse(None, "", "https://example.test/api", error="TLS error"),
            ErrorCode.FETCH_FAILED,
        ),
        (
            HttpResponse(503, "", "https://example.test/api"),
            ErrorCode.HTTP_ERROR,
        ),
    ),
)
def test_liuiuqu_rejects_unusable_api_responses(
    response: HttpResponse,
    expected: ErrorCode,
) -> None:
    target = replace(
        source(fetcher="liuiuqu"),
        api_url="https://example.test/api",
    )

    class SingleResponseHttp:
        async def post(self, *_args, **_kwargs) -> HttpResponse:
            return response

    with pytest.raises(FetchError) as captured:
        asyncio.run(
            LiuiuquFetcher(SingleResponseHttp()).fetch(
                target,
                FetchRequest((237,), attempts=1),
            )
        )

    assert captured.value.failure.code is expected


class TrackingListDetailFetcher(ListDetailFetcher):
    def __init__(self) -> None:
        super().__init__(StubBrowser(()))
        self.detail_urls: list[str] = []

    async def _list_links(self, *_args) -> tuple[Link, ...]:
        return (
            Link("https://example.test/236.html", "236期 目标九肖"),
            Link("https://example.test/235.html", "235期 目标九肖"),
        )

    async def _detail_documents(
        self,
        _source: Source,
        _request: FetchRequest,
        detail_url: str,
    ) -> tuple[Document, ...]:
        self.detail_urls.append(detail_url)
        return (
            Document(
                label=detail_url,
                url=detail_url,
                text="detail",
                method=DocumentMethod.BROWSER_DOM,
            ),
        )


def test_list_detail_history_fetches_each_requested_issue() -> None:
    target = Source(
        name="目标",
        url="https://example.test/list?page=1",
        position=Position.TOP,
        section_marker="目标九肖",
        fetcher="list_detail",
        parser="direct_nine",
        detail_link_keyword="目标九肖",
    )
    fetcher = TrackingListDetailFetcher()

    documents = asyncio.run(
        fetcher.fetch(target, FetchRequest((236, 235), history_mode=True))
    )

    assert len(documents) == 2
    assert fetcher.detail_urls == [
        "https://example.test/236.html",
        "https://example.test/235.html",
    ]


class TrackingCurrentFetcher(ListDetailCurrentFetcher):
    def __init__(self) -> None:
        super().__init__(StubBrowser(()))
        self.detail_urls: list[str] = []

    async def _list_links(self, *_args) -> tuple[Link, ...]:
        return (
            Link("https://example.test/237.html", "237期 目标九肖"),
            Link("https://example.test/231.html", "231期 目标九肖"),
        )

    async def _detail_documents(
        self,
        _source: Source,
        _request: FetchRequest,
        detail_url: str,
    ) -> tuple[Document, ...]:
        self.detail_urls.append(detail_url)
        return (
            Document(
                label=detail_url,
                url=detail_url,
                text="detail",
                method=DocumentMethod.BROWSER_DOM,
            ),
        )


def test_current_detail_fetches_latest_named_detail_for_older_issue() -> None:
    target = Source(
        name="目标",
        url="https://example.test/list?page=1",
        position=Position.TOP,
        section_marker="目标九肖",
        fetcher="list_detail_current",
        parser="direct_nine",
        detail_link_keyword="目标九肖",
    )
    fetcher = TrackingCurrentFetcher()

    documents = asyncio.run(fetcher.fetch(target, FetchRequest((236,))))

    assert len(documents) == 1
    assert fetcher.detail_urls == ["https://example.test/237.html"]
    assert fetcher.max_pages == 20


@pytest.mark.parametrize(
    ("candidate", "expected"),
    (
        ("https://example.test/list?id=75&page=2", True),
        ("https://example.test/list?page=3&id=75", True),
        ("https://example.test/list?id=75&page=x", False),
        ("https://example.test/list?id=76&page=2", False),
        ("https://other.test/list?id=75&page=2", False),
        ("https://example.test/other?id=75&page=2", False),
    ),
)
def test_list_page_url_keeps_only_the_same_catalog(
    candidate: str,
    expected: bool,
) -> None:
    assert (
        is_list_page_url(
            candidate,
            "https://example.test/list?id=75&page=1",
        )
        is expected
    )


def test_list_links_follow_pagination_until_requested_title_is_found() -> None:
    class PagingBrowser:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def links(self, url: str, **_kwargs) -> tuple[Link, ...]:
            self.calls.append(url)
            if "page=2" in url:
                return (
                    Link(
                        "https://example.test/236.html",
                        "236期 目标九肖",
                    ),
                )
            return (
                Link("https://example.test/237.html", "237期 目标九肖"),
                Link(
                    "https://example.test/list?id=75&page=2",
                    "下一页",
                ),
                Link(
                    "https://example.test/list?id=76&page=2",
                    "其他栏目",
                ),
            )

    target = Source(
        name="目标",
        url="https://example.test/list?id=75&page=1",
        position=Position.TOP,
        section_marker="目标九肖",
        fetcher="list_detail",
        parser="direct_nine",
        detail_link_keyword="目标九肖",
    )
    browser = PagingBrowser()

    links = asyncio.run(
        ListDetailFetcher(browser, max_pages=3)._list_links(
            target,
            FetchRequest((236,)),
        )
    )

    assert [link.text for link in links] == [
        "237期 目标九肖",
        "下一页",
        "其他栏目",
        "236期 目标九肖",
    ]
    assert len(browser.calls) == 2


def test_same_origin_normalizes_default_ports() -> None:
    assert same_origin(
        "https://EXAMPLE.test/topic",
        "https://example.test:443/other",
    )
    assert same_origin(
        "http://example.test/topic",
        "http://example.test:80/other",
    )


class DisposableResponse:
    status = 200
    url = "https://example.test/data"

    def __init__(self, text: str) -> None:
        self._text = text
        self.disposed = False

    async def text(self) -> str:
        return self._text

    async def dispose(self) -> None:
        self.disposed = True


class RequestContext:
    def __init__(self) -> None:
        self.responses: list[DisposableResponse] = []

    async def get(self, *_args, **_kwargs) -> DisposableResponse:
        response = DisposableResponse("get")
        self.responses.append(response)
        return response

    async def post(self, *_args, **_kwargs) -> DisposableResponse:
        response = DisposableResponse("post")
        self.responses.append(response)
        return response


def test_http_client_disposes_get_and_post_responses() -> None:
    request = RequestContext()
    client = PlaywrightHttpClient(type("Context", (), {"request": request})())

    async def exercise() -> None:
        await client.get("https://example.test", timeout_ms=1000, headers=())
        await client.post(
            "https://example.test",
            timeout_ms=1000,
            headers=(),
            form=(),
        )

    asyncio.run(exercise())

    assert len(request.responses) == 2
    assert all(response.disposed for response in request.responses)


def test_http_client_preserves_the_network_error_detail() -> None:
    class FailingRequest:
        async def get(self, *_args, **_kwargs):
            raise RuntimeError("TLS handshake rejected")

    client = PlaywrightHttpClient(
        type("Context", (), {"request": FailingRequest()})()
    )

    response = asyncio.run(
        client.get("https://example.test", timeout_ms=1000, headers=())
    )

    assert response.error == "RuntimeError: TLS handshake rejected"


def test_unapproved_document_cannot_override_primary_document() -> None:
    target = source()
    documents = (
        Document(
            label="primary",
            url=target.url,
            text="九肖中特\n236期：九肖【鼠牛虎兔龙蛇马羊猴】",
            method=DocumentMethod.STATIC_PAGE,
        ),
        Document(
            label="script",
            url=target.url,
            text="九肖中特\n236期：九肖【鸡狗猪鼠牛虎兔龙蛇】",
            method=DocumentMethod.SCRIPT,
        ),
    )
    records = DirectNineParser().parse(target, documents, (236,))

    verified = Validator().validate(target, records, (236,))

    assert verified.history.records[0].zodiac_text == "鼠牛虎兔龙蛇马羊猴"


def test_image_ocr_rejects_unlinked_image_text() -> None:
    target = replace(
        source(),
        parser="image_ocr",
        source_policy=("image_ocr",),
    )
    document = Document(
        label="image-ocr:0",
        url=target.url,
        text="九肖中特\n236期：九肖【鼠牛虎兔龙蛇马羊猴】",
        method=DocumentMethod.IMAGE_OCR,
    )

    with pytest.raises(ParseError) as captured:
        ImageOcrParser().parse(target, (document,), (236,))

    assert captured.value.failure.code is ErrorCode.SOURCE_UNTRUSTED


def test_formula_ocr_rejects_unlinked_image_text() -> None:
    target = replace(
        source(),
        parser="formula_next_issue_ocr",
        source_policy=("browser_dom", "image_ocr"),
    )
    document = Document(
        label="image-ocr:0",
        url=target.url,
        text=(
            "九肖中特\n"
            "235期：九肖 公式：+0 下期：鼠牛虎兔龙蛇马羊猴"
        ),
        method=DocumentMethod.IMAGE_OCR,
    )

    with pytest.raises(ParseError) as captured:
        FormulaNextIssueOcrParser().parse(target, (document,), (236,))

    assert captured.value.failure.code is ErrorCode.SOURCE_UNTRUSTED


class StubCrawl:
    def __init__(self, results: tuple[Result, ...]) -> None:
        self.results = results

    async def crawl_many(self, *_args, **_kwargs) -> tuple[Result, ...]:
        return self.results


class StubReports:
    calls = 0

    def write_issue(self, _issue: int, _results: tuple[Result, ...]):
        self.calls += 1
        return Path("success.txt"), Path("failure.txt")


class StubCacheSync:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls = 0
        self.error = error

    def sync_single(self, *_args) -> object:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return object()


def test_single_crawl_persists_failure_status_even_at_zero_success() -> None:
    target = source()
    result = Result.failed(target, (236,), Failure(ErrorCode.ISSUE_MISSING))
    cache = StubCacheSync()
    service = CrawlRunService(StubCrawl((result,)), StubReports(), cache)

    run = asyncio.run(service.crawl((target,), 236, concurrency=1))

    assert cache.calls == 1
    assert run.cache_updated


def test_cache_failure_keeps_completed_reports_and_returns_run() -> None:
    target = source()
    record = Record(
        issue=236,
        zodiacs=tuple("鼠牛虎兔龙蛇马羊猴"),
        evidence=Evidence(
            method="test",
            source_line="",
            directory_anchor="",
            document_label="test",
        ),
    )
    result = Result.succeeded(target, (236,), History((record,), 236))
    reports = StubReports()
    cache = StubCacheSync(OSError("disk full"))
    service = CrawlRunService(StubCrawl((result,)), reports, cache)

    run = asyncio.run(service.crawl((target,), 236, concurrency=1))

    assert reports.calls == 1
    assert not run.cache_updated
    assert "disk full" in run.cache_error


def test_repair_appends_success_without_replacing_existing_report(
    tmp_path: Path,
) -> None:
    target = source()
    record = Record(
        236,
        tuple("牛虎兔龙蛇马羊猴鸡"),
        Evidence("test", "牛虎兔龙蛇马羊猴鸡", target.name, "test"),
    )
    result = Result.succeeded(target, (236,), History((record,), 236))
    reports = ReportRepository(tmp_path)
    success_path = tmp_path / "236.txt"
    failure_path = tmp_path / "236-failures.txt"
    success_path.write_text("鼠牛虎兔龙蛇马羊猴 已有目录\n", encoding="utf-8")
    failure_path.write_text(
        (
            f"失败 {target.name} {target.url} 方向: top 期数: 236 "
            "阶段: 指定期数校验 原因: 没有找到目标期记录\n\n"
            "失败 其他目录 https://example.test/other 方向: bottom "
            "期数: 236 阶段: 网络抓取 原因: 页面抓取失败\n"
        ),
        encoding="utf-8",
    )

    class SelectedCache:
        def sync_single(self, *_args) -> object:
            raise AssertionError("repair must not replace the full cache")

        def sync_selected_single(self, *_args) -> object:
            return object()

    run = asyncio.run(
        CrawlRunService(
            StubCrawl((result,)),
            reports,
            SelectedCache(),
        ).repair((target,), 236, concurrency=1)
    )

    assert success_path.read_text(encoding="utf-8").splitlines() == [
        "鼠牛虎兔龙蛇马羊猴 已有目录",
        "牛虎兔龙蛇马羊猴鸡 测试目录",
    ]
    failure_text = failure_path.read_text(encoding="utf-8")
    assert f"失败 {target.name} " not in failure_text
    assert "失败 其他目录 " in failure_text
    assert run.cache_updated


def test_range_summary_contains_only_sources_failed_in_every_issue(
    tmp_path: Path,
) -> None:
    first = source()
    second = replace(
        first,
        name="另一目录",
        url="https://example.test/topic/2.html",
    )
    first_236 = Result.failed(
        first,
        (236,),
        Failure(ErrorCode.ISSUE_MISSING),
    )
    first_235 = Result.failed(
        first,
        (235,),
        Failure(ErrorCode.ISSUE_MISSING),
    )
    second_236 = Result.failed(
        second,
        (236,),
        Failure(ErrorCode.ISSUE_MISSING),
    )
    second_record = Record(
        issue=235,
        zodiacs=tuple("鼠牛虎兔龙蛇马羊猴"),
        evidence=Evidence(
            method="test",
            source_line="",
            directory_anchor="",
            document_label="test",
        ),
    )
    second_235 = Result.succeeded(
        second,
        (235,),
        History((second_record,), 235),
    )
    reports = ReportRepository(tmp_path)

    path = reports.write_range_failures(
        (
            (236, (first_236, second_236)),
            (235, (first_235, second_235)),
        )
    )
    text = path.read_text(encoding="utf-8")

    assert first.name in text
    assert second.name not in text


def test_range_summary_uses_period_specific_project_output_path(
    tmp_path: Path,
) -> None:
    target = source()
    failed_236 = Result.failed(
        target,
        (236,),
        Failure(ErrorCode.ISSUE_MISSING),
    )
    failed_235 = Result.failed(
        target,
        (235,),
        Failure(ErrorCode.ISSUE_MISSING),
    )
    reports = ReportRepository(
        tmp_path / "single",
        range_failure_dir=tmp_path / "outputs",
        range_failure_filename=(
            "{start_issue}-{end_issue}-all-failures.txt"
        ),
    )

    path = reports.write_range_failures(
        ((236, (failed_236,)), (235, (failed_235,)))
    )

    assert path == tmp_path / "outputs" / "236-235-all-failures.txt"
    assert path.is_file()


def cache_document(zodiac: str) -> dict:
    return {
        "schema_version": 2,
        "latest_issue": 236,
        "issues": [236],
        "sources": [
            {
                "source": source_to_dict(source()),
                "current_issue": 236,
                "records": {"236": zodiac},
                "errors": {},
            }
        ],
    }


def test_cache_rejects_invalid_nine_zodiac_payload() -> None:
    with pytest.raises(ValueError, match="invalid zodiac record"):
        CacheRepository._from_document(cache_document("鼠牛虎兔龙蛇马羊羊"))


def test_cache_rejects_same_issue_as_success_and_failure() -> None:
    document = cache_document("鼠牛虎兔龙蛇马羊猴")
    document["sources"][0]["errors"] = {"236": "ISSUE_MISSING"}

    with pytest.raises(ValueError, match="overlap"):
        CacheRepository._from_document(document)


def test_source_identity_changes_with_business_parser_configuration() -> None:
    original = source()
    changed = replace(original, parser="grouped")

    assert source_identity(original).key != source_identity(changed).key


def test_missing_main_list_override_file_fails_closed(tmp_path: Path) -> None:
    catalog = MainListCatalog(StubBrowser(()), tmp_path / "directions.json")

    with pytest.raises(ValueError, match="parser overrides"):
        catalog._load_parser_overrides()


class SuccessfulHistoryCrawl:
    def __init__(self, result: Result) -> None:
        self.result = result

    async def crawl_one(self, *_args, **_kwargs) -> Result:
        return self.result


class TrackingSourceRepository:
    def __init__(self) -> None:
        self.add_calls = 0

    def add(self, *_args, **_kwargs) -> None:
        self.add_calls += 1


def test_onboarding_without_comparable_baseline_never_adds_source() -> None:
    target = source()
    issues = tuple(range(236, 226, -1))
    records = tuple(
        Record(
            issue=issue,
            zodiacs=tuple("鼠牛虎兔龙蛇马羊猴"),
            evidence=Evidence(
                method="test",
                source_line="",
                directory_anchor="",
                document_label="test",
            ),
        )
        for issue in issues
    )
    result = Result.succeeded(target, issues, History(records, 236))
    repository = TrackingSourceRepository()
    service = OnboardingService(
        SuccessfulHistoryCrawl(result),
        DuplicateChecker(),
        repository,
    )

    decision = asyncio.run(service.onboard(target, (), issues))

    assert decision.state is OnboardingState.FAILED
    assert decision.duplicate is not None
    assert decision.duplicate.state is DuplicateState.INCOMPLETE
    assert repository.add_calls == 0


@pytest.mark.parametrize(
    ("match_count", "expected_state", "expected_adds"),
    (
        (2, OnboardingState.ACCEPTED, 1),
        (3, OnboardingState.MANUAL_REVIEW, 0),
        (6, OnboardingState.REJECTED, 0),
    ),
)
def test_onboarding_preserves_project_total_match_thresholds(
    match_count: int,
    expected_state: OnboardingState,
    expected_adds: int,
) -> None:
    target = source()
    issues = tuple(range(236, 226, -1))
    value = "鼠牛虎兔龙蛇马羊猴"
    candidate_records = tuple(
        Record(issue, tuple(value), Evidence("test", value, "test", "test"))
        for issue in issues
    )
    result = Result.succeeded(
        target,
        issues,
        History(candidate_records, 236),
    )
    baseline = BaselineHistory(
        "baseline",
        "基准",
        History(candidate_records[:match_count], 236),
    )
    repository = TrackingSourceRepository()

    decision = asyncio.run(
        OnboardingService(
            SuccessfulHistoryCrawl(result),
            DuplicateChecker(),
            repository,
        ).onboard(target, (baseline,), issues)
    )

    assert decision.state is expected_state
    assert repository.add_calls == expected_adds


class RangeCrawl:
    async def crawl_many(self, sources, issues, **_kwargs):
        issue = issues[0]
        return tuple(
            Result.failed(
                item,
                (issue,),
                Failure(ErrorCode.ISSUE_MISSING),
            )
            for item in sources
        )


class RangeReports:
    def __init__(self) -> None:
        self.written: list[int] = []

    def write_issue(self, issue, _results):
        self.written.append(issue)
        return Path(f"{issue}.txt"), Path(f"{issue}-failures.txt")

    def write_range_failures(self, batches):
        assert tuple(issue for issue, _results in batches) == (236, 235)
        return Path("range-failures.txt")


class ForbiddenRangeCache:
    def sync_single(self, *_args):
        raise AssertionError("range mode must not update cache")


def test_range_mode_writes_each_report_but_never_updates_cache() -> None:
    target = source()
    reports = RangeReports()
    service = CrawlRunService(RangeCrawl(), reports, ForbiddenRangeCache())

    run = asyncio.run(
        service.crawl_range((target,), (236, 235), concurrency=1)
    )

    assert reports.written == [236, 235]
    assert run.failure_summary_path == Path("range-failures.txt")


class FakeContext:
    def __init__(self, *, close_error: bool = False) -> None:
        self.close_error = close_error

    async def close(self) -> None:
        if self.close_error:
            raise RuntimeError("context close failed")


class FakeBrowser:
    def __init__(
        self,
        *,
        context: FakeContext | None = None,
        context_error: bool = False,
    ) -> None:
        self.context = context
        self.context_error = context_error
        self.closed = False

    async def new_context(self, **_kwargs) -> FakeContext:
        if self.context_error:
            raise RuntimeError("context creation failed")
        assert self.context is not None
        return self.context

    async def close(self) -> None:
        self.closed = True


class FakeChromium:
    def __init__(self, browser: FakeBrowser) -> None:
        self.browser = browser

    async def launch(self, **_kwargs) -> FakeBrowser:
        return self.browser


class FakePlaywrightManager:
    def __init__(self, browser: FakeBrowser) -> None:
        self.playwright = type(
            "Playwright",
            (),
            {"chromium": FakeChromium(browser)},
        )()

    async def __aenter__(self):
        return self.playwright

    async def __aexit__(self, *_args) -> None:
        return None


def test_browser_closes_when_context_creation_fails(monkeypatch) -> None:
    browser = FakeBrowser(context_error=True)
    monkeypatch.setattr(
        runtime,
        "async_playwright",
        lambda: FakePlaywrightManager(browser),
    )

    with pytest.raises(RuntimeError, match="context creation failed"):
        asyncio.run(runtime.run_crawl(PROJECT_ROOT, 236, concurrency=1))

    assert browser.closed


def test_browser_closes_even_when_context_cleanup_fails(monkeypatch) -> None:
    browser = FakeBrowser(context=FakeContext(close_error=True))
    monkeypatch.setattr(
        runtime,
        "async_playwright",
        lambda: FakePlaywrightManager(browser),
    )

    async def fail_sources(*_args, **_kwargs):
        raise RuntimeError("source loading failed")

    monkeypatch.setattr(runtime, "daily_sources", fail_sources)

    with pytest.raises(RuntimeError):
        asyncio.run(runtime.run_crawl(PROJECT_ROOT, 236, concurrency=1))

    assert browser.closed


def test_split_line_never_borrows_the_next_issues_payload() -> None:
    target = replace(source(), parser="split_line")
    document = Document(
        label="page",
        url=target.url,
        text=(
            "九肖中特\n"
            "223期 九肖\n"
            "224期【鼠牛虎兔龙蛇马羊猴】"
        ),
        method=DocumentMethod.STATIC_PAGE,
    )

    parsed = SplitLineParser().parse(target, (document,), (223,))

    with pytest.raises(ValidationError) as captured:
        Validator().validate(target, parsed, (223,))

    assert captured.value.failure.code is ErrorCode.ISSUE_MISSING


@pytest.mark.parametrize("marker", LOCKED_MARKERS)
def test_validator_rejects_locked_content_from_every_parser(marker: str) -> None:
    target = source()
    document = Document(
        label="page",
        url=target.url,
        text="九肖中特\n236期：九肖【鼠牛虎兔龙蛇马羊猴】",
        method=DocumentMethod.STATIC_PAGE,
    )
    parsed = DirectNineParser().parse(target, (document,), (236,))
    record = parsed.records[0]
    locked = replace(
        record,
        evidence=replace(
            record.evidence,
            source_line=f"{record.evidence.source_line} {marker}",
        ),
    )

    with pytest.raises(ValidationError) as captured:
        Validator().validate(
            target,
            RecordSet((locked,), parsed.blocks),
            (236,),
        )

    assert captured.value.failure.code is ErrorCode.LOCKED_CONTENT


@pytest.mark.parametrize("value", (223.9, True, 0, -1))
def test_liuiuqu_rejects_non_positive_integer_issues(value) -> None:
    assert LiuiuquParser._issue(value) is None


def test_valid_ocr_payload_is_not_vetoed_by_open_result_zodiac() -> None:
    target = replace(
        source(),
        parser="image_ocr",
        source_policy=("image_ocr",),
    )
    document = Document(
        label="image-ocr:0",
        url=target.url,
        text="236期 九肖【鼠牛虎兔龙蛇马羊猴】开:鼠",
        method=DocumentMethod.IMAGE_OCR,
        metadata=(
            ("image_index", "0"),
            ("parent_url", target.url),
            ("anchor_line", "九肖中特 九肖"),
            ("anchor_term", "九肖中特"),
            ("data_marker_line", "九肖中特 九肖"),
            ("anchor_index", "0"),
            ("block_start", "0"),
            ("block_end", "2"),
        ),
    )

    parsed = ImageOcrParser().parse(target, (document,), (236,))
    verified = Validator().validate(target, parsed, (236,))

    assert verified.history.records[0].zodiac_text == "鼠牛虎兔龙蛇马羊猴"


def test_identical_duplicate_blocks_are_deduplicated() -> None:
    target = source()
    document = Document(
        label="page",
        url=target.url,
        text=(
            "九肖中特\n"
            "236期：九肖【鼠牛虎兔龙蛇马羊猴】\n"
            "其他栏目\n"
            "九肖中特\n"
            "236期：九肖【鼠牛虎兔龙蛇马羊猴】"
        ),
        method=DocumentMethod.STATIC_PAGE,
    )

    parsed = DirectNineParser().parse(target, (document,), (236,))
    verified = Validator().validate(target, parsed, (236,))

    assert verified.history.records[0].zodiac_text == "鼠牛虎兔龙蛇马羊猴"


def test_different_duplicate_blocks_remain_ambiguous() -> None:
    target = source()
    document = Document(
        label="page",
        url=target.url,
        text=(
            "九肖中特\n"
            "236期：九肖【鼠牛虎兔龙蛇马羊猴】\n"
            "其他栏目\n"
            "九肖中特\n"
            "236期：九肖【鸡狗猪鼠牛虎兔龙蛇】"
        ),
        method=DocumentMethod.STATIC_PAGE,
    )
    parsed = DirectNineParser().parse(target, (document,), (236,))

    with pytest.raises(ValidationError) as captured:
        Validator().validate(target, parsed, (236,))

    assert captured.value.failure.code is ErrorCode.BLOCK_AMBIGUOUS


def test_grouped_evidence_must_match_the_configured_mapping() -> None:
    target = replace(
        source(),
        parser="grouped",
        group_map=(
            ("琴", "鼠牛虎"),
            ("棋", "兔龙蛇"),
            ("书", "马羊猴"),
            ("画", "鸡狗猪"),
        ),
        data_marker="琴棋书画",
    )
    document = Document(
        label="page",
        url=target.url,
        text="九肖中特\n236期：【琴棋书】",
        method=DocumentMethod.STATIC_PAGE,
    )
    parsed = GroupedParser().parse(target, (document,), (236,))
    record = parsed.records[0]
    tampered_metadata = tuple(
        (key, "琴=鸡狗猪" if key == "group_mapping" else value)
        for key, value in record.evidence.metadata
    )
    tampered = replace(
        record,
        evidence=replace(record.evidence, metadata=tampered_metadata),
    )

    with pytest.raises(ValidationError) as captured:
        Validator().validate(
            target,
            RecordSet((tampered,), parsed.blocks),
            (236,),
        )

    assert captured.value.failure.code is ErrorCode.SOURCE_UNTRUSTED


def test_single_season_complement_uses_canonical_zodiac_order() -> None:
    target = Source(
        name="橘色日落",
        url="https://example.test/topic/466135.html",
        position=Position.BOTTOM,
        section_marker="绝杀一季",
        fetcher="browser_page",
        parser="single_season_complement_canonical",
        group_map=(
            ("春", "虎兔龙"),
            ("夏", "蛇马羊"),
            ("秋", "猴鸡狗"),
            ("冬", "鼠牛猪"),
        ),
    )
    document = Document(
        label="browser-dom",
        url=target.url,
        text=(
            "237期【绝杀一季】\n"
            "橘色日落\n"
            "236期：绝杀一季【秋】开猴11对"
        ),
        method=DocumentMethod.BROWSER_DOM,
    )
    parsed = SingleSeasonComplementParser(
        "single_season_complement_canonical"
    ).parse(target, (document,), (236,))

    verified = Validator().validate(target, parsed, (236,))

    assert verified.history.records[0].zodiac_text == "鼠牛虎兔龙蛇马羊猪"


def test_verified_single_season_sources_use_canonical_parser() -> None:
    active = SourceRepository(
        PROJECT_ROOT / "config" / "sources.json",
        PROJECT_ROOT / "config" / "archived_sources.json",
    ).load_active()
    parsers = {
        item.name: item.parser
        for item in active
        if item.name in {"橘色日落", "物微志信"}
    }

    assert parsers == {
        "橘色日落": "single_season_complement_canonical",
        "物微志信": "single_season_complement_canonical",
    }


@pytest.mark.parametrize("current_issue", (True, 223.5))
def test_history_rejects_non_integer_current_issue(current_issue) -> None:
    with pytest.raises((TypeError, ValueError)):
        History(current_issue=current_issue)


def test_success_result_rejects_failures_hidden_inside_history() -> None:
    with pytest.raises(ValueError, match="成功结果"):
        Result(
            source=source(),
            requested_issues=(236,),
            history=History(failures=(Failure(ErrorCode.ISSUE_MISSING),)),
            state=ResultState.SUCCESS,
        )


def test_suiyueran_list_detail_uses_its_own_section() -> None:
    active = SourceRepository(
        PROJECT_ROOT / "config" / "sources.json",
        PROJECT_ROOT / "config" / "archived_sources.json",
    ).load_active()
    target = next(item for item in active if item.name == "随遇而安")

    assert target.url == "https://a.ttss.vip/listam.aspx?id=75&page=1"
    assert target.section_marker == "随遇而安㊣㊣九肖"
    assert target.detail_link_keyword == "随遇而安㊣㊣九肖"


def test_suiyueran_cache_preserves_verified_history() -> None:
    cached = CacheRepository(
        PROJECT_ROOT / "cache" / "recent_10_cache.json"
    ).load()
    target = next(item for item in cached.sources if item.source.name == "随遇而安")

    assert target.source.section_marker == "随遇而安㊣㊣九肖"
    assert target.source.detail_link_keyword == "随遇而安㊣㊣九肖"
    verified_records = {
        237: "鸡猴兔羊猪马虎牛狗",
        236: "鸡鼠猴虎猪兔龙牛马",
        235: "羊鼠兔猪蛇牛龙鸡虎",
        234: "牛猪虎龙羊蛇鼠鸡兔",
        233: "鼠狗龙猪虎牛马鸡羊",
        232: "虎鼠兔龙牛蛇羊鸡狗",
        231: "猪狗牛羊猴龙虎鸡马",
    }
    verified_errors = {
        230: ErrorCode.ISSUE_MISSING,
        229: ErrorCode.ISSUE_MISSING,
        228: ErrorCode.ISSUE_MISSING,
        227: ErrorCode.ISSUE_MISSING,
    }
    records = dict(target.records)
    errors = dict(target.errors)
    retained_records = records.keys() & verified_records.keys()
    retained_errors = errors.keys() & verified_errors.keys()

    assert retained_records
    assert {issue: records[issue] for issue in retained_records} == {
        issue: verified_records[issue] for issue in retained_records
    }
    assert {issue: errors[issue] for issue in retained_errors} == {
        issue: verified_errors[issue] for issue in retained_errors
    }


def test_shuangshichongfei_uses_current_detail_fetcher_in_cache() -> None:
    active = SourceRepository(
        PROJECT_ROOT / "config" / "sources.json",
        PROJECT_ROOT / "config" / "archived_sources.json",
    ).load_active()
    configured = next(item for item in active if item.name == "双世宠妃")
    cached = CacheRepository(
        PROJECT_ROOT / "cache" / "recent_10_cache.json"
    ).load()
    cached_source = next(
        item.source for item in cached.sources if item.source.name == "双世宠妃"
    )

    assert configured.fetcher == "list_detail_current"
    assert source_identity(configured).key == source_identity(cached_source).key
