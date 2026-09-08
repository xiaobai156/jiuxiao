from __future__ import annotations

from v2.domain.identity import source_identity
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

    def sync_single(
        self,
        sources: tuple[Source, ...],
        results: tuple[Result, ...],
        issue: int,
    ) -> CacheSnapshot:
        self._validate_batch(sources, results, issue)
        with self._repository.locked():
            return self._sync_single_locked(sources, results, issue)

    def _sync_single_locked(
        self,
        sources: tuple[Source, ...],
        results: tuple[Result, ...],
        issue: int,
    ) -> CacheSnapshot:
        previous = self._repository.load()
        old_by_identity = {
            source_identity(item.source).key: item for item in previous.sources
        }
        result_by_identity: dict[str, Result] = {}
        for result in results:
            key = source_identity(result.source).key
            if key in result_by_identity:
                raise ValueError("duplicate result identity")
            result_by_identity[key] = result

        retained_issues = sorted({issue, *previous.issues}, reverse=True)[
            : self._history_limit
        ]
        snapshots: list[CacheSource] = []
        for source in sources:
            key = source_identity(source).key
            old = old_by_identity.get(key, CacheSource(source))
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
        )
        return self._repository.sync(snapshot)

    def sync_selected_single(
        self,
        sources: tuple[Source, ...],
        results: tuple[Result, ...],
        issue: int,
    ) -> CacheSnapshot:
        """Synchronize only the selected sources for one single-period run."""
        self._validate_batch(sources, results, issue)
        if len({source_identity(source).key for source in sources}) != len(
            sources
        ):
            raise ValueError("duplicate source identity")
        if len({source.name for source in sources}) != len(sources):
            raise ValueError("duplicate source name")
        with self._repository.locked():
            return self._sync_selected_locked(sources, results, issue)

    def _sync_selected_locked(
        self,
        sources: tuple[Source, ...],
        results: tuple[Result, ...],
        issue: int,
    ) -> CacheSnapshot:
        previous = self._repository.load()
        result_by_identity = {
            source_identity(result.source).key: result
            for result in results
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
                    snapshots.append(
                        self._updated_cache_source(
                            replacement,
                            CacheSource(replacement),
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

        if selected_keys != {
            source_identity(source).key for source in sources
        }:
            raise AssertionError("selected result identities are incomplete")
        snapshot = CacheSnapshot(
            latest_issue=max(retained_issues),
            issues=tuple(retained_issues),
            sources=tuple(snapshots),
        )
        return self._repository.sync(snapshot)

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
                cached.current_issue
                if cached.current_issue in retained_issues
                else None
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
                raise ValueError(
                    "successful result must contain one issue record"
                )
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
