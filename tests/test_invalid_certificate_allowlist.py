from __future__ import annotations

import asyncio
import importlib.util
import json
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
    if specification is None or specification.loader is None:
        raise RuntimeError("无法加载 V2 测试包")
    package = importlib.util.module_from_spec(specification)
    sys.modules["v2"] = package
    specification.loader.exec_module(package)

from v2.config.schema import (  # noqa: E402
    ConfigValidationError,
    source_from_dict,
    source_to_dict,
)
from v2.domain.models import Position, Source  # noqa: E402
from v2.fetchers.browser_page import (  # noqa: E402
    BrowserPageFetcher,
    PlaywrightBrowserClient,
)
from v2.fetchers.registry import FetchError, FetchRequest  # noqa: E402

RAW = {
    "name": "否极泰来",
    "url": "https://jtmjfqq.ewlkg-dp3xr-hebqil.xyz:16677/topic/459584.html",
    "position": "top",
    "section_marker": "",
    "fetcher": "browser_page",
    "parser": "direct_nine",
    "api_url": "",
    "group_map": {},
    "detail_link_keyword": "",
    "aliases": [],
    "data_marker": "",
    "source_policy": [],
}


def _source(allow_invalid_certificate: bool) -> Source:
    return Source(
        name=RAW["name"],
        url=RAW["url"],
        position=Position.TOP,
        section_marker="",
        fetcher="browser_page",
        parser="direct_nine",
        allow_invalid_certificate=allow_invalid_certificate,
    )


def test_allow_invalid_certificate_defaults_to_false_and_is_opt_in() -> None:
    assert source_from_dict(dict(RAW)).allow_invalid_certificate is False
    flagged = source_from_dict({**RAW, "allow_invalid_certificate": True})
    assert flagged.allow_invalid_certificate is True
    with pytest.raises(ConfigValidationError):
        source_from_dict({**RAW, "allow_invalid_certificate": "yes"})


def test_serialisation_keeps_unflagged_sources_byte_identical() -> None:
    plain = _source(False)
    assert "allow_invalid_certificate" not in source_to_dict(plain)
    assert source_to_dict(plain) == source_to_dict(source_from_dict(dict(RAW)))
    flagged = _source(True)
    assert source_to_dict(flagged)["allow_invalid_certificate"] is True
    # 授权站点往返不丢字段
    assert source_from_dict(source_to_dict(flagged)).allow_invalid_certificate is True


def test_identity_key_ignores_the_certificate_flag() -> None:
    from v2.domain.identity import source_identity

    assert source_identity(_source(False)).key == source_identity(_source(True)).key


class _FakeContext:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


def test_insecure_context_is_created_only_for_flagged_calls() -> None:
    strict = _FakeContext()
    created: list[_FakeContext] = []

    async def factory() -> _FakeContext:
        context = _FakeContext()
        created.append(context)
        return context

    client = PlaywrightBrowserClient(strict, insecure_context_factory=factory)

    async def run() -> None:
        async with client._call_context(False) as context:
            assert context is strict
        assert created == []
        async with client._call_context(True) as context:
            assert context is created[0]
            assert context.closed is False
        assert created[0].closed is True
        assert strict.closed is False

    asyncio.run(run())


def test_insecure_context_falls_back_to_strict_context_without_factory() -> None:
    strict = _FakeContext()
    client = PlaywrightBrowserClient(strict)

    async def run() -> None:
        async with client._call_context(True) as context:
            assert context is strict

    asyncio.run(run())


class _RecordingBrowser:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def collect(self, url: str, **kwargs):
        self.calls.append(kwargs)
        return ()

    async def links(self, url: str, **kwargs):
        self.calls.append(kwargs)
        return ()


def test_browser_page_fetcher_forwards_the_certificate_flag() -> None:
    browser = _RecordingBrowser()
    fetcher = BrowserPageFetcher(browser)
    request = FetchRequest((283,), attempts=1)

    async def run() -> None:
        with pytest.raises(FetchError):
            await fetcher.fetch(_source(True), request)
        assert browser.calls[-1]["allow_invalid_certificate"] is True
        with pytest.raises(FetchError):
            await fetcher.fetch(_source(False), request)
        assert browser.calls[-1]["allow_invalid_certificate"] is False

    asyncio.run(run())


def test_formal_config_flags_only_the_authorised_station() -> None:
    config = json.loads(
        (PROJECT_ROOT / "config" / "sources.json").read_text(encoding="utf-8")
    )
    flagged = [
        item["name"]
        for item in config["sources"]
        if item.get("allow_invalid_certificate")
    ]
    assert flagged == ["否极泰来"], flagged
    # 只有该站多出这一个字段，其余站点保持原样
    extra = [
        item["name"]
        for item in config["sources"]
        if "allow_invalid_certificate" in item and item["name"] != "否极泰来"
    ]
    assert extra == [], extra


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
