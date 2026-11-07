"""动态文章渲染兜底的“目标文章身份”回归（2026-11-06 复审修复）。

修复前 `_browser_fallback` 只校验 URL 里的 article id，然后把这次渲染返回的
**全部** document 交给解析器（48 站在用 `dynamic_article`）。同页如果有别篇
文章、或渲染落到了别的页面，别篇的期号就可能被当成本期值。

修复后：每篇 document 必须自己证明是目标文章（metadata 的 article_id → 正文里
带同 ID 的 JSON/属性 → 页面 URL），证明不了的文档不交；正文明确指向别篇时
即使 URL 对得上也失败（`API_RECORD_MISMATCH`）。
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
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

from v2.domain.errors import ErrorCode  # noqa: E402
from v2.domain.models import (  # noqa: E402
    Document,
    DocumentMethod,
    Position,
    Source,
)
from v2.fetchers.dynamic_article import DynamicArticleFetcher  # noqa: E402
from v2.fetchers.registry import (  # noqa: E402
    FetchError,
    FetchRequest,
    HttpResponse,
)
from v2.parsers.direct_nine import DirectNineParser  # noqa: E402
from v2.validator import ValidationError, Validator  # noqa: E402


TARGET_ID = "target1234"
OTHER_ID = "other9999"
TARGET_URL = f"https://example.test/article/admin/{TARGET_ID}?url=x"
OTHER_URL = f"https://example.test/article/admin/{OTHER_ID}?url=x"
TARGET_VALUE = "鼠牛虎兔龙蛇马羊猴"
OTHER_VALUE = "猪狗猴羊马蛇龙兔虎"


def _source() -> Source:
    return Source(
        name="测试动态",
        url=TARGET_URL,
        position=Position.TOP,
        section_marker="九肖中特",
        fetcher="dynamic_article",
        parser="direct_nine",
    )


class _StubHttp:
    """API 404：走浏览器渲染兜底。"""

    async def get(self, *_args, **_kwargs) -> HttpResponse:
        return HttpResponse(404, "", TARGET_URL)


class _StubBrowser:
    def __init__(self, documents: tuple[Document, ...]) -> None:
        self.documents = documents

    async def collect(self, *_args, **_kwargs) -> tuple[Document, ...]:
        return self.documents


def _dom(url: str, text: str, **metadata: str) -> Document:
    return Document(
        label="browser-dom",
        url=url,
        text=text,
        method=DocumentMethod.BROWSER_DOM,
        metadata=tuple(metadata.items()),
    )


def test_browser_fallback_keeps_only_the_target_article() -> None:
    target = _source()
    browser = _StubBrowser(
        (
            _dom(
                TARGET_URL,
                f"九肖中特\n236期：九肖【{TARGET_VALUE}】开:？00准",
            ),
            _dom(
                OTHER_URL,
                f"九肖中特\n236期：九肖【{OTHER_VALUE}】开:马25准",
            ),
        )
    )
    fetcher = DynamicArticleFetcher(_StubHttp(), browser)

    documents = asyncio.run(
        fetcher.fetch(target, FetchRequest((236,), attempts=1))
    )

    assert len(documents) == 1, "同页只允许交能证明是目标文章的那一篇"
    assert documents[0].url == TARGET_URL
    assert all(OTHER_VALUE not in document.text for document in documents)

    parsed = DirectNineParser().parse(target, documents, (236,))
    verified = Validator().validate(target, parsed, (236,))
    assert verified.history.records[0].zodiac_text == TARGET_VALUE


def test_missing_issue_is_not_satisfied_by_another_article() -> None:
    """目标篇没有这一期时，不得拿同页别篇的同名期号顶上（HEAD 上会静默成功）。"""
    target = _source()
    browser = _StubBrowser(
        (
            _dom(TARGET_URL, f"九肖中特\n236期：九肖【{TARGET_VALUE}】"),
            _dom(OTHER_URL, f"九肖中特\n235期：九肖【{OTHER_VALUE}】"),
        )
    )
    fetcher = DynamicArticleFetcher(_StubHttp(), browser)

    documents = asyncio.run(
        fetcher.fetch(target, FetchRequest((235,), attempts=1))
    )

    assert len(documents) == 1
    parsed = DirectNineParser().parse(target, documents, (235,))
    with pytest.raises(ValidationError) as captured:
        Validator().validate(target, parsed, (235,))
    assert captured.value.failure.code is ErrorCode.ISSUE_MISSING


def test_browser_body_pointing_at_another_article_fails() -> None:
    target = _source()
    browser = _StubBrowser(
        (
            _dom(
                TARGET_URL,
                (
                    '{"articleId":"' + OTHER_ID + '","title":"别篇"}'
                    f"\n九肖中特\n236期：九肖【{OTHER_VALUE}】"
                ),
            ),
        )
    )
    fetcher = DynamicArticleFetcher(_StubHttp(), browser)

    with pytest.raises(FetchError) as captured:
        asyncio.run(fetcher.fetch(target, FetchRequest((236,), attempts=1)))

    assert captured.value.failure.code is ErrorCode.API_RECORD_MISMATCH
    assert OTHER_ID in captured.value.failure.detail


def test_browser_metadata_article_id_proves_the_target() -> None:
    """URL 不带 ID 时，正文/元数据里的 article_id 仍可证明是哪一篇。"""
    target = _source()
    browser = _StubBrowser(
        (
            _dom(
                "https://example.test/render/topic",
                f"九肖中特\n236期：九肖【{TARGET_VALUE}】",
                article_id=TARGET_ID,
            ),
        )
    )
    fetcher = DynamicArticleFetcher(_StubHttp(), browser)

    documents = asyncio.run(
        fetcher.fetch(target, FetchRequest((236,), attempts=1))
    )

    assert len(documents) == 1
    assert dict(documents[0].metadata)["article_id"] == TARGET_ID


def test_browser_body_id_proves_the_target_without_url_id() -> None:
    """正文 JSON 里带同 ID 也认，但只交这一篇。"""
    target = _source()
    browser = _StubBrowser(
        (
            _dom(
                "https://example.test/render/topic",
                (
                    '{"articleId":"' + TARGET_ID + '"}'
                    f"\n九肖中特\n236期：九肖【{TARGET_VALUE}】"
                ),
            ),
            _dom(
                "https://example.test/render/topic2",
                f"九肖中特\n236期：九肖【{OTHER_VALUE}】",
            ),
        )
    )
    fetcher = DynamicArticleFetcher(_StubHttp(), browser)

    documents = asyncio.run(
        fetcher.fetch(target, FetchRequest((236,), attempts=1))
    )

    assert len(documents) == 1
    assert TARGET_VALUE in documents[0].text
