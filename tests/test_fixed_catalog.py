from __future__ import annotations

import asyncio
import importlib.util
import json
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

from v2 import runtime  # noqa: E402
from v2.domain.models import Position, Source  # noqa: E402


class _Repository:
    def __init__(self, sources: tuple[Source, ...]) -> None:
        self._sources = sources

    def load_active(self) -> tuple[Source, ...]:
        return self._sources


def test_daily_sources_uses_formal_repository_without_dynamic_browser() -> None:
    source = Source(
        name="固定站点",
        url="https://example.test/topic/1.html",
        position=Position.TOP,
        section_marker="九肖中特",
        fetcher="browser_page",
        parser="direct_nine",
    )

    assert asyncio.run(
        runtime.daily_sources(Path("."), repository=_Repository((source,)))
    ) == (source,)


def test_dynamic_catalog_definitions_are_migrated_to_formal_config() -> None:
    cache = json.loads(
        (PROJECT_ROOT / "cache" / "recent_10_cache.json").read_text(
            encoding="utf-8"
        )
    )
    config = json.loads(
        (PROJECT_ROOT / "config" / "sources.json").read_text(encoding="utf-8")
    )
    dynamic = [
        item["source"]
        for item in cache["sources"]
        if "jogavu.6bl6s-ilo1w-yfnvvl.work" in item["source"]["url"]
    ]
    configured = {item["url"]: item for item in config["sources"]}

    assert len(dynamic) == 34
    # 437 起为 f045ed7 固定目录基线；2026-10-02 接入「止痛水路」后为 438；
    # 2026-10-05 封存「阿猫阿狗」（278 期站方侧拒绝访客）后为 437；
    # 2026-10-05 接入「后会无期」（278 期，用户投喂）后为 438；
    # 2026-10-06 封存「宝刀不老」（279 期站方侧登录墙，游客不可见）后为 437；
    # 2026-10-06 接入「火烧眉毛」（279 期，用户投喂）后为 438；
    # 2026-10-08 封存「一语破特」（281 期站方侧登录墙，游客不可见）后为 437；
    # 2026-10-08 接入「做贼心虚」（281 期，用户投喂）后为 438。
    assert len(config["sources"]) == 438
    assert [configured[item["url"]]["name"] for item in dynamic] == [
        item["name"] for item in dynamic
    ]
