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
    # 2026-10-08 接入「做贼心虚」（281 期，用户投喂）后为 438；
    # 2026-10-08 封存同源镜像「风神九肖」（对 嫦娥奔月）、「炉火纯青」（对 朴斲之材）后为 436；
    # 2026-10-08 接入「博敞花坛」（281 期，尾部，用户投喂 + 近 10 期缓存补齐）后为 437；
    # 2026-10-08 接入「如图地方」（281 期，顶部，用户投喂 + 近 10 期缓存补齐）后为 438；
    # 2026-10-09 封存「灵丹妙药」（282 期站方侧登录墙，游客不可见）后为 437；
    # 2026-10-09 接入「冰清玉洁」（282 期，顶部，用户投喂 + 近 10 期缓存补齐）后为 438；
    # 2026-10-10 封存「田乘风破」（283 期站方删帖，AdminArticle 404）后为 437；
    # 2026-10-10 接入「闻风而动」（283 期，顶部，用户投喂 + 近 10 期缓存补齐）后为 438；
    # 2026-10-12 封存「美酒咖啡」（285 期站方侧论坛登录墙，游客不可见）后为 437；
    # 2026-10-12 接入「娄底太师」（285 期，顶部，用户投喂 + 近 10 期缓存补齐）后为 438；
    # 2026-10-13 封存「海立云垂」（286 期站方数据接口异常，SPA 纯壳无内容）后为 437；
    # 2026-10-13 接入「新陈代谢」「与众不同」（286 期，顶部，用户投喂 + 近 10 期缓存补齐）后为 439；
    # 2026-10-14 封存「半斤八两」（287 期站方删文，AdminArticle 404）后为 438；
    # 2026-10-14 接入「脸红筋暴」（287 期，顶部，用户投喂 + 近 10 期缓存补齐）后为 439；
    # 2026-10-15 接入「唯一无二」（288 期，顶部，用户投喂 + 近 10 期缓存补齐）后为 440；
    # 2026-10-15 接入「孤独与酒」（288 期，顶部）、「九死一生」（288 期，尾部）（用户投喂 + 近 10 期缓存补齐）后为 442；
    # 2026-10-16 接入「顺风顺水」（289 期，顶部，用户投喂 + 近 10 期缓存补齐）后为 443；
    # 2026-10-17 封存「诗情画意」（287/288/289 连续三期站方 TLS 证书不可用，游客不可访问）后为 442；
    # 2026-10-17 接入「天马行空」（290 期，顶部，用户投喂 + 近 10 期缓存补齐）后为 443。
    # 2026-10-20 封存「红红火火」（293 期站方删除该篇文章，三种接口全部 404）后为 442。
    # 2026-10-20 解封「诗情画意」并换址后为 443；
    # 2026-10-20 接入「只争朝夕」「同舟共济」「甘棠之惠」（293 期，用户投喂 + 近 10 期缓存补齐）后为 446。
    # 2026-10-22 接入「燃烧翅膀」「大智若愚」（295 期，用户投喂 + 近 10 期缓存补齐）后为 448。
    # 2026-10-22 接入「不惜血本」（295 期，用户投喂 + 近 10 期缓存补齐）后为 449。
    # 2026-10-23 封存「否极泰来」「跷足抗首」「财富满天」「温柔三刀」（296 期站方侧问题）后为 445。
    # 2026-10-23 解封「否极泰来」并换址（新址 294~287 与封存前缓存逐期一致，判重 clear）后为 446。
    # 2026-10-23 接入「无可挑剔」「神神叨叨」（判重 clear）与「雷霆大怒」
    # （判重 manual_review，用户明确放行）后为 449。
    # 2026-10-24 接入「天下无敌」「说长道短」「世纪汇艾」「发家致富」
    # 「枪林弹雨」「废寝忘食」（296 期，判重均 clear）后为 455。
    # 2026-10-24 接入「笑眼迷人」（296 期，判重 clear）后为 456。
    # 2026-10-25 封存「青栀无梦」（298 期站方删文，接口 404）后为 455。
    # 2026-10-25 接入「七口八嘴」（298 期，判重 clear）后为 456。
    # 2026-10-26 封存「神圣好料」（299 期站方删文，页面空壳）后为 455。
    # 2026-10-26 接入「老恭看马」（299 期，判重 clear，requires_login=true）后为 456。
    # 2026-10-29 封存「古今中外」（302 期站方改为全站会员可见，游客无权限）后为 455。
    # 2026-10-29 接入「千人一面」（302 期，判重 clear）后为 456。
    # 2026-10-30 封存「出言不逊」（303 期正文改为金币售卖，游客不可读）后为 455。
    # 2026-10-30 接入「云涌风飞」「九肖美妞」（303 期，判重均 clear）后为 457。
    # 2026-10-30 封存「CC琴棋」「CC春秋」（303 期站方整站 HTTP 522，源站不可达）后为 455。
    # 2026-10-31 接入「风铃歌」（304 期，判重 clear，requires_login=true）后为 456。
    # 2026-11-02 封存「奔向富豪」（306 期站方删文，manager-articles 接口 404）后为 455。
    # 2026-11-02 接入「路叟之忧」（306 期，判重 clear）后为 456。
    assert len(config["sources"]) == 456
    assert [configured[item["url"]]["name"] for item in dynamic] == [
        item["name"] for item in dynamic
    ]
