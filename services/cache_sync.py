from __future__ import annotations

from v2.domain.identity import normalize_url, source_identity
from v2.domain.models import Result, Source
from v2.storage.cache import CacheRepository, CacheSnapshot, CacheSource


class CacheWriteForbiddenError(RuntimeError):
    pass


class CacheSyncService:
    def __init__(
        self,
        repository: CacheRepository,
        *,
        history_limit: int = 10,
    ) -> None:
        if history_limit <= 0:
            raise ValueError("history_limit must be greater than zero")
        self._repository = repository
        self._history_limit = history_limit

    @staticmethod
    def _stable_key(source: Source) -> tuple[str, str, str]:
        """配置指纹之外的「站槽」身份：站名 + 规范化 URL + 方向。

        改 ``section_marker`` / ``data_marker`` / ``parser`` / ``aliases`` 都会让
        ``source_identity`` 的指纹变化，但站点本身没变。用这个身份把上一轮的
        缓存历史接续过来，否则一改锚点，该站近 10 期历史会被静默清零。
        """
        return (
            source.name.strip(),
            normalize_url(source.url),
            source.position.value,
        )

    @staticmethod
    def _same_engine(previous: Source, current: Source) -> bool:
        """解析/抓取引擎是否未变。

        换 ``parser`` 或 ``fetcher`` 意味着取值来源本身换了（旧值可能是错引擎
        产出的），历史必须重置；只换锚点/数据词/别名则站点与引擎都没变，
        历史必须接续。
        """
        return (
            previous.parser == current.parser
            and previous.fetcher == current.fetcher
        )

    @classmethod
    def _stable_entries(
        cls,
        entries: tuple[CacheSource, ...],
    ) -> dict[tuple[str, str, str], CacheSource]:
        """按稳定身份索引旧缓存；同一身份出现多次时整组不迁移，避免张冠李戴。"""
        unique: dict[tuple[str, str, str], CacheSource] = {}
        duplicated: set[tuple[str, str, str]] = set()
        for entry in entries:
            key = cls._stable_key(entry.source)
            if key in unique:
                duplicated.add(key)
            else:
                unique[key] = entry
        for key in duplicated:
            unique.pop(key, None)
        return unique

    def sync_single(
        self,
        sources: tuple[Source, ...],
        results: tuple[Result, ...],
        issue: int,
        *,
        cycle: str = "",
    ) -> CacheSnapshot:
        self._validate_batch(sources, results, issue)
        with self._repository.locked():
            return self._sync_single_locked(sources, results, issue, cycle=cycle)

    def _sync_single_locked(
        self,
        sources: tuple[Source, ...],
        results: tuple[Result, ...],
        issue: int,
        *,
        cycle: str,
    ) -> CacheSnapshot:
        previous = self._repository.load()
        requested_cycle = self._normalize_cycle(cycle)
        cycle_changed = bool(
            requested_cycle and requested_cycle != previous.cycle
        )
        effective_cycle = requested_cycle or previous.cycle
        old_by_identity = {
            source_identity(item.source).key: item
            for item in (() if cycle_changed else previous.sources)
        }
        old_by_stable = self._stable_entries(
            () if cycle_changed else previous.sources
        )
        result_by_identity: dict[str, Result] = {}
        for result in results:
            key = source_identity(result.source).key
            if key in result_by_identity:
                raise ValueError("duplicate result identity")
            result_by_identity[key] = result

        retained_issues = (
            [issue]
            if cycle_changed
            else sorted({issue, *previous.issues}, reverse=True)[
                : self._history_limit
            ]
        )
        snapshots: list[CacheSource] = []
        for source in sources:
            key = source_identity(source).key
            old = old_by_identity.get(key)
            if old is None:
                # 配置指纹变了但站点与引擎没变：接续它自己的历史，且只允许领用一次。
                stable = self._stable_key(source)
                candidate = old_by_stable.get(stable)
                if candidate is not None and self._same_engine(
                    candidate.source, source
                ):
                    old = candidate
                    del old_by_stable[stable]
            if old is None:
                old = CacheSource(source)
            result = result_by_identity.get(key)
            if result is None:
                raise AssertionError("validated result is missing")
            snapshots.append(
                self._updated_cache_source(
                    source,
                    old,
                    result,
                    issue,
                    retained_issues,
                )
            )
        snapshot = CacheSnapshot(
            latest_issue=max(retained_issues),
            issues=tuple(retained_issues),
            sources=tuple(snapshots),
            cycle=effective_cycle,
        )
        return self._repository.sync(snapshot)

    def sync_selected_single(
        self,
        sources: tuple[Source, ...],
        results: tuple[Result, ...],
        issue: int,
        *,
        cycle: str = "",
    ) -> CacheSnapshot:
        """Synchronize only the selected sources for one single-period run."""
        self._validate_batch(sources, results, issue)
        if len({source_identity(source).key for source in sources}) != len(sources):
            raise ValueError("duplicate source identity")
        if len({source.name for source in sources}) != len(sources):
            raise ValueError("duplicate source name")
        with self._repository.locked():
            return self._sync_selected_locked(sources, results, issue, cycle=cycle)

    def _sync_selected_locked(
        self,
        sources: tuple[Source, ...],
        results: tuple[Result, ...],
        issue: int,
        *,
        cycle: str,
    ) -> CacheSnapshot:
        previous = self._repository.load()
        requested_cycle = self._normalize_cycle(cycle)
        if requested_cycle and requested_cycle != previous.cycle:
            raise ValueError(
                f"cache cycle mismatch: cache={previous.cycle} "
                f"request={requested_cycle}"
            )
        effective_cycle = requested_cycle or previous.cycle
        result_by_identity = {
            source_identity(result.source).key: result for result in results
        }
        retained_issues = sorted({issue, *previous.issues}, reverse=True)[
            : self._history_limit
        ]
        selected_keys = set(result_by_identity)
        selected_by_name = {source.name: source for source in sources}
        snapshots: list[CacheSource] = []
        seen_keys: set[str] = set()
        seen_names: set[str] = set()

        for cached in previous.sources:
            key = source_identity(cached.source).key
            if key in seen_keys or cached.source.name in seen_names:
                raise ValueError("duplicate cached source identity or name")
            seen_keys.add(key)
            seen_names.add(cached.source.name)
            result = result_by_identity.get(key)
            if result is None:
                replacement = selected_by_name.get(cached.source.name)
                if replacement is not None:
                    replacement_key = source_identity(replacement).key
                    keep = (
                        cached
                        if self._stable_key(replacement)
                        == self._stable_key(cached.source)
                        and self._same_engine(cached.source, replacement)
                        else CacheSource(replacement)
                    )
                    snapshots.append(
                        self._updated_cache_source(
                            replacement,
                            keep,
                            result_by_identity[replacement_key],
                            issue,
                            retained_issues,
                        )
                    )
                    seen_keys.add(replacement_key)
                    continue
                snapshots.append(
                    self._retain_cache_source(cached, retained_issues)
                )
                continue
            snapshots.append(
                self._updated_cache_source(
                    result.source,
                    cached,
                    result,
                    issue,
                    retained_issues,
                )
            )

        for source in sources:
            key = source_identity(source).key
            if key in seen_keys:
                continue
            result = result_by_identity.get(key)
            if result is None:
                raise AssertionError("validated result is missing")
            snapshots.append(
                self._updated_cache_source(
                    source,
                    CacheSource(source),
                    result,
                    issue,
                    retained_issues,
                )
            )
            seen_keys.add(key)

        if selected_keys != {source_identity(source).key for source in sources}:
            raise AssertionError("selected result identities are incomplete")
        snapshot = CacheSnapshot(
            latest_issue=max(retained_issues),
            issues=tuple(retained_issues),
            sources=tuple(snapshots),
            cycle=effective_cycle,
        )
        return self._repository.sync(snapshot)

    @staticmethod
    def _normalize_cycle(value: str) -> str:
        normalized = str(value).strip()
        if len(normalized) > 64 or any(
            character.isspace() for character in normalized
        ):
            raise ValueError("invalid cache cycle")
        return normalized

    @staticmethod
    def _retain_cache_source(
        cached: CacheSource,
        retained_issues: list[int],
    ) -> CacheSource:
        records = dict(cached.records)
        errors = dict(cached.errors)
        return CacheSource(
            source=cached.source,
            current_issue=(
                cached.current_issue if cached.current_issue in retained_issues else None
            ),
            records=tuple(
                (item_issue, records[item_issue])
                for item_issue in retained_issues
                if item_issue in records
            ),
            errors=tuple(
                (item_issue, errors[item_issue])
                for item_issue in retained_issues
                if item_issue in errors
            ),
        )

    @staticmethod
    def _updated_cache_source(
        source: Source,
        cached: CacheSource,
        result: Result,
        issue: int,
        retained_issues: list[int],
    ) -> CacheSource:
        records = dict(cached.records)
        errors = dict(cached.errors)
        current_issue = cached.current_issue
        if result.successful:
            candidates = result.history.records_for(issue)
            if len(candidates) != 1:
                raise ValueError("successful result must contain one issue record")
            records[issue] = candidates[0].zodiac_text
            errors.pop(issue, None)
            current_issue = result.history.current_issue
        else:
            records.pop(issue, None)
            errors[issue] = result.failures[0].code
        if current_issue not in retained_issues:
            current_issue = None
        return CacheSource(
            source=source,
            current_issue=current_issue,
            records=tuple(
                (item_issue, records[item_issue])
                for item_issue in retained_issues
                if item_issue in records
            ),
            errors=tuple(
                (item_issue, errors[item_issue])
                for item_issue in retained_issues
                if item_issue in errors
            ),
        )

    @staticmethod
    def _validate_batch(
        sources: tuple[Source, ...],
        results: tuple[Result, ...],
        issue: int,
    ) -> None:
        expected = tuple(source_identity(source).key for source in sources)
        actual = tuple(source_identity(result.source).key for result in results)
        if expected != actual:
            raise ValueError("result identities or order do not match sources")
        if any(result.requested_issues != (issue,) for result in results):
            raise ValueError("result issue does not match cache issue")

    def sync_range(self) -> None:
        raise CacheWriteForbiddenError("range mode cannot write cache")
