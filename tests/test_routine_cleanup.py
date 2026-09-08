from __future__ import annotations

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
    if specification is None or specification.loader is None:
        raise RuntimeError("无法加载 V2 测试包")
    package = importlib.util.module_from_spec(specification)
    sys.modules["v2"] = package
    specification.loader.exec_module(package)

from v2.domain.errors import ErrorCode, Failure  # noqa: E402
from v2.config.repository import SourceRepository  # noqa: E402
from v2.domain.models import (  # noqa: E402
    Evidence,
    History,
    Position,
    Record,
    Result,
    Source,
)
from v2.services.cache_sync import CacheSyncService  # noqa: E402
from v2.storage.cache import CacheRepository  # noqa: E402
from v2.validator import Validator  # noqa: E402


def _source(name: str) -> Source:
    return Source(
        name=name,
        url=f"https://example.test/{name}",
        position=Position.TOP,
        section_marker=name,
        fetcher="static_page",
        parser="direct_nine",
    )


def _result(source: Source, issue: int, value: str) -> Result:
    record = Record(
        issue,
        tuple(value),
        Evidence("test", value, source.name, "test"),
    )
    return Result.succeeded(source, (issue,), History((record,), issue))


def test_validator_requires_record_set() -> None:
    source = _source("甲")
    record = _result(source, 236, "鼠牛虎兔龙蛇马羊猴").history.records[0]

    with pytest.raises(TypeError, match="RecordSet"):
        Validator().validate(source, (record,), (236,))


def test_cache_sync_keeps_full_and_selected_semantics(tmp_path: Path) -> None:
    first, second, third = (_source(name) for name in "甲乙丙")
    service = CacheSyncService(CacheRepository(tmp_path / "cache.json"))
    service.sync_single(
        (first, second),
        (
            _result(first, 235, "鼠牛虎兔龙蛇马羊猴"),
            _result(second, 235, "牛虎兔龙蛇马羊猴鸡"),
        ),
        235,
    )

    selected = service.sync_selected_single(
        (first, third),
        (
            _result(first, 236, "虎兔龙蛇马羊猴鸡狗"),
            _result(third, 236, "兔龙蛇马羊猴鸡狗猪"),
        ),
        236,
    )
    assert [item.source.name for item in selected.sources] == ["甲", "乙", "丙"]
    assert dict(selected.sources[0].records)[236] == "虎兔龙蛇马羊猴鸡狗"
    assert dict(selected.sources[1].records)[235] == "牛虎兔龙蛇马羊猴鸡"

    failed = Result.failed(first, (236,), Failure(ErrorCode.FETCH_FAILED))
    full = service.sync_single((first,), (failed,), 236)
    assert [item.source.name for item in full.sources] == ["甲"]
    assert 236 not in dict(full.sources[0].records)
    assert dict(full.sources[0].errors)[236] is ErrorCode.FETCH_FAILED


def test_selected_sync_replaces_changed_config_in_the_same_slot(
    tmp_path: Path,
) -> None:
    original = _source("甲")
    changed = replace(original, parser="grouped")
    service = CacheSyncService(CacheRepository(tmp_path / "cache.json"))
    service.sync_single(
        (original,),
        (_result(original, 235, "鼠牛虎兔龙蛇马羊猴"),),
        235,
    )

    snapshot = service.sync_selected_single(
        (changed,),
        (_result(changed, 236, "牛虎兔龙蛇马羊猴鸡"),),
        236,
    )

    assert [item.source for item in snapshot.sources] == [changed]
    assert dict(snapshot.sources[0].records) == {
        236: "牛虎兔龙蛇马羊猴鸡"
    }


def test_cache_clears_a_current_issue_that_ages_out_of_the_window(
    tmp_path: Path,
) -> None:
    target = _source("甲")
    repository = CacheRepository(tmp_path / "cache.json")
    service = CacheSyncService(repository)
    service.sync_single(
        (target,),
        (_result(target, 227, "鼠牛虎兔龙蛇马羊猴"),),
        227,
    )

    for issue in range(228, 238):
        failure = Result.failed(
            target,
            (issue,),
            Failure(ErrorCode.ISSUE_MISSING),
        )
        service.sync_single((target,), (failure,), issue)

    loaded = repository.load()
    assert loaded.sources[0].current_issue is None


def test_retired_sources_are_archived_and_absent_from_cache() -> None:
    expected = {
        "取长补短": "https://18118.73829.com/read.php?tid=504",
        "异军突起": (
            "https://hcsuuoy.nimo7-9bgj4-fmspxt.xyz:29466/article/manager/"
            "6a3b3ddf018539c611cbfecb?url=cww"
        ),
        "码赢铁面": (
            "https://czcvzk.4n5g7-o871g-hqmkwz.work:29422/article/admin/"
            "6a1cd89dc8b23672c8140715?url=tsp"
        ),
    }
    sources = SourceRepository(
        PROJECT_ROOT / "config" / "sources.json",
        PROJECT_ROOT / "config" / "archived_sources.json",
    )
    active = sources.load_active()
    archived = sources.load_archived()
    cache = CacheRepository(
        PROJECT_ROOT / "cache" / "recent_10_cache.json"
    ).load()

    assert not any(source.name in expected for source in active)
    assert not any(item.source.name in expected for item in cache.sources)
    for name, url in expected.items():
        matches = tuple(item for item in archived if item.source.name == name)
        assert len(matches) == 1
        assert matches[0].source.url == url
