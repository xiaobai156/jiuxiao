"""站方整域换址（旧域名 301 → 新域名 + 原路径）的回归测试。

背景（2026-10-19，292 期）：jogavu 等 34 站所属站点整体换域名，旧域名 301 到
门户首页，真实文章仍在「新域名 + 原路径」。这批站同时还有两个坑：
1) 同一批新域名里有的只是空壳（路径正确但正文未渲染）；
2) 门户域名自身还会再 301 一次，形成换址链。
因此抓取层必须沿链追下去，直到拿到含锚点与期号行的正文，且全程不放宽校验。
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

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
from v2.fetchers.browser_page import (  # noqa: E402
    BrowserPageFetcher,
    rebase_path,
    same_path,
)
from v2.fetchers.registry import FetchError, FetchRequest  # noqa: E402


OLD_URL = "https://old.example:16677/topic/622316.html"
PORTAL_HOME = "https://portal.example:16644/#5.1"
SHELL_HOME = "https://shell.example:17488/#dq"
PORTAL_TOPIC = "https://portal.example:16644/topic/622316.html"
SHELL_TOPIC = "https://shell.example:17488/topic/622316.html"
MARKER = "金阳九肖"
ARTICLE_TEXT = (
    f"{MARKER} 发表于 10月19日\n"
    "292期九肖中特【狗猴猪龙兔羊鼠鸡马】开0000准\n"
    "291期九肖中特【蛇龙狗羊兔猴牛虎马】开兔40准"
)
SHELL_TEXT = "门户首页 通知公告 澳门资料 香港资料 292期一码中特 点击查看>"


def source() -> Source:
    return Source(
        name="测试站",
        url=OLD_URL,
        position=Position.TOP,
        section_marker=MARKER,
        fetcher="browser_page",
        parser="direct_nine",
    )


def document(url: str, text: str) -> Document:
    return Document(
        label="browser-dom",
        url=url,
        text=text,
        method=DocumentMethod.BROWSER_DOM,
    )


class FakeBrowser:
    """按 URL 返回预设页面，记录每次请求。"""

    def __init__(self, pages: dict[str, tuple[str, str]]) -> None:
        self.pages = pages
        self.calls: list[str] = []

    async def collect(self, url: str, **_kwargs):
        self.calls.append(url)
        text, landing = self.pages.get(url, (SHELL_TEXT, url))
        return (document(landing, text),)


def run_fetch(browser: FakeBrowser, attempts: int = 3) -> tuple[Document, ...]:
    return asyncio.run(
        BrowserPageFetcher(browser).fetch(
            source(),
            FetchRequest((292,), attempts=attempts, timeout_ms=1000, settle_ms=0),
        )
    )


def test_same_path_ignores_host_but_not_path() -> None:
    assert same_path(OLD_URL, PORTAL_TOPIC)
    assert not same_path(OLD_URL, PORTAL_HOME)


def test_rebase_path_keeps_path_on_new_host() -> None:
    assert rebase_path(OLD_URL, PORTAL_HOME) == PORTAL_TOPIC


def test_rebase_follows_chain_through_empty_shell_to_article() -> None:
    """旧域名 → 空壳门户（topic 也空壳）→ 又一个空壳 → 最终有正文。"""
    browser = FakeBrowser(
        {
            OLD_URL: (SHELL_TEXT, PORTAL_HOME),
            PORTAL_TOPIC: (SHELL_TEXT, SHELL_HOME),
            SHELL_TOPIC: (ARTICLE_TEXT, SHELL_TOPIC),
        }
    )
    documents = run_fetch(browser)

    assert documents[0].url == SHELL_TOPIC
    assert MARKER in documents[0].text
    assert browser.calls[0] == OLD_URL
    assert len(browser.calls) >= 3


def test_rebase_fails_when_chain_never_yields_article() -> None:
    """整条链都是空壳时不得放行，必须判失败。"""
    browser = FakeBrowser({OLD_URL: (SHELL_TEXT, PORTAL_HOME)})
    try:
        run_fetch(browser, attempts=1)
    except FetchError as exc:
        assert exc.failure.code in (
            ErrorCode.CROSS_DOMAIN,
            ErrorCode.FETCH_FAILED,
        )
    else:  # pragma: no cover - 失败即测试不通过
        raise AssertionError("空壳链不得返回文档")


def test_same_origin_source_is_requested_once() -> None:
    """同源正常站不得因为换址逻辑多请求。"""
    browser = FakeBrowser({OLD_URL: (ARTICLE_TEXT, OLD_URL)})
    documents = run_fetch(browser)

    assert documents[0].url == OLD_URL
    assert browser.calls == [OLD_URL]
