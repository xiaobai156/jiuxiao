"""缓存历史在「配置指纹变化」时不得被静默清零。

背景：`source_identity` 的指纹包含 section_marker / data_marker / parser /
aliases 等配置字段。改这些字段（例如 B 阶段给站点换独占锚点）会让身份 key
变化，旧实现直接新建 CacheSource，该站近 10 期历史随之消失——判重和滚动窗口
都会失真。本文件锁定「同一站槽（站名+规范化 URL+方向）接续历史」这条行为。
"""

from __future__ import annotations

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

from v2.domain.models import (  # noqa: E402
    Evidence,
    History,
    Position,
    Record,
    Result,
    Source,
)
from v2.services.cache_sync import CacheSyncService  # noqa: E402
from v2.storage.cache import CacheSnapshot, CacheSource  # noqa: E402

VALUE_308 = "鼠牛虎兔龙蛇马羊猴"
VALUE_309 = "牛虎兔龙蛇马羊猴鸡"
VALUE_310 = "虎兔龙蛇马羊猴鸡狗"


def _source(
    *,
    name: str = "出言不逊",
    url: str = "https://example.test/read.php?tid=1",
    marker: str = "九肖中特",
    data_marker: str = "",
    position: Position = Position.TOP,
) -> Source:
    return Source(
        name=name,
        url=url,
        position=position,
        section_marker=marker,
        fetcher="browser_page",
        parser="direct_nine",
        data_marker=data_marker,
    )


def _record(source: Source, issue: int, value: str) -> Record:
    return Record(issue, tuple(value), Evidence("test", value, source.name, "test"))


class _MemoryCacheRepository:
    def __init__(self, snapshot: CacheSnapshot) -> None:
        self.snapshot = snapshot

    class _Lock:
        def __enter__(self):
            return None

        def __exit__(self, *_args):
            return False

    def locked(self):
        return self._Lock()

    def load(self) -> CacheSnapshot:
        return self.snapshot

    def sync(self, snapshot: CacheSnapshot) -> CacheSnapshot:
        self.snapshot = snapshot
        return snapshot


def test_section_marker_change_keeps_existing_history() -> None:
    before = _source(marker="九肖中特")
    after = _source(marker="出言不逊九肖中特")
    previous = CacheSnapshot(
        latest_issue=309,
        issues=(309, 308),
        sources=(
            CacheSource(
                before,
                current_issue=309,
                records=((309, VALUE_309), (308, VALUE_308)),
            ),
        ),
    )
    service = CacheSyncService(_MemoryCacheRepository(previous))

    result = Result.succeeded(
        after,
        (310,),
        History((_record(after, 310, VALUE_310),), 310),
    )
    snapshot = service.sync_single((after,), (result,), 310)

    assert len(snapshot.sources) == 1
    entry = snapshot.sources[0]
    assert dict(entry.records) == {
        310: VALUE_310,
        309: VALUE_309,
        308: VALUE_308,
    }, "改锚点不得丢掉该站已有历史"
    assert entry.current_issue == 310
    assert entry.source.section_marker == "出言不逊九肖中特"


def test_data_marker_change_keeps_existing_history() -> None:
    before = _source(data_marker="")
    after = _source(data_marker="九肖")
    previous = CacheSnapshot(
        latest_issue=309,
        issues=(309,),
        sources=(CacheSource(before, 309, ((309, VALUE_309),)),),
    )
    service = CacheSyncService(_MemoryCacheRepository(previous))

    result = Result.succeeded(
        after,
        (310,),
        History((_record(after, 310, VALUE_310),), 310),
    )
    snapshot = service.sync_single((after,), (result,), 310)

    assert dict(snapshot.sources[0].records) == {
        310: VALUE_310,
        309: VALUE_309,
    }


def test_other_site_does_not_inherit_history() -> None:
    before = _source(name="甲站")
    other = _source(
        name="乙站",
        url="https://other.test/read.php?tid=2",
    )
    previous = CacheSnapshot(
        latest_issue=309,
        issues=(309,),
        sources=(CacheSource(before, 309, ((309, VALUE_309),)),),
    )
    service = CacheSyncService(_MemoryCacheRepository(previous))

    result = Result.succeeded(
        other,
        (310,),
        History((_record(other, 310, VALUE_310),), 310),
    )
    snapshot = service.sync_single((other,), (result,), 310)

    assert dict(snapshot.sources[0].records) == {310: VALUE_310}, (
        "另一个站点不能继承别人的历史"
    )


def test_ambiguous_stable_identity_is_not_migrated() -> None:
    """同一站槽在旧缓存里出现两次时整组不迁移，避免张冠李戴。"""
    before_a = _source(marker="九肖中特")
    before_b = _source(marker="精华九肖")
    after = _source(marker="新锚点")
    previous = CacheSnapshot(
        latest_issue=309,
        issues=(309,),
        sources=(
            CacheSource(before_a, 309, ((309, VALUE_309),)),
            CacheSource(before_b, 309, ((309, VALUE_308),)),
        ),
    )
    service = CacheSyncService(_MemoryCacheRepository(previous))

    result = Result.succeeded(
        after,
        (310,),
        History((_record(after, 310, VALUE_310),), 310),
    )
    snapshot = service.sync_single((after,), (result,), 310)

    assert dict(snapshot.sources[0].records) == {310: VALUE_310}


def test_engine_change_resets_history_instead_of_migrating() -> None:
    """换 parser/fetcher 等于换了取值引擎，旧值不可信，历史必须重置。"""
    before = _source(marker="九肖中特")
    after = Source(
        name=before.name,
        url=before.url,
        position=before.position,
        section_marker=before.section_marker,
        fetcher=before.fetcher,
        parser="grouped",
    )
    previous = CacheSnapshot(
        latest_issue=309,
        issues=(309,),
        sources=(CacheSource(before, 309, ((309, VALUE_309),)),),
    )
    service = CacheSyncService(_MemoryCacheRepository(previous))

    result = Result.succeeded(
        after,
        (310,),
        History((_record(after, 310, VALUE_310),), 310),
    )
    snapshot = service.sync_single((after,), (result,), 310)

    assert dict(snapshot.sources[0].records) == {310: VALUE_310}, (
        "换引擎后不得沿用旧引擎的历史"
    )
