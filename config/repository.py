from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from v2.config.schema import (
    ConfigValidationError,
    source_from_dict,
    source_to_dict,
)
from v2.domain.errors import ErrorCode
from v2.domain.identity import source_identity
from v2.domain.models import Source
from v2.storage.atomic import (
    atomic_write_bytes,
    atomic_write_many,
    recover_atomic_batch,
)


class DuplicateSourceError(ValueError):
    code = ErrorCode.DUPLICATE_SOURCE


class SourceNotFoundError(LookupError):
    code = ErrorCode.CONFIG_INVALID


@dataclass(frozen=True, slots=True)
class ArchivedSource:
    source: Source
    archived_at: str
    reason: str

    def __post_init__(self) -> None:
        if not self.archived_at.strip():
            raise ValueError("archived_at 不能为空")
        if not self.reason.strip():
            raise ValueError("reason 不能为空")


class SourceRepository:
    def __init__(self, active_path: Path, archived_path: Path) -> None:
        self.active_path = Path(active_path)
        self.archived_path = Path(archived_path)
        if self.active_path.parent.resolve() != self.archived_path.parent.resolve():
            raise ValueError("活跃与封存配置必须位于同一目录")
        self.journal_path = (
            self.active_path.parent / ".source-repository-transaction.json"
        )

    def initialize(self) -> None:
        self._recover()
        active_exists = self.active_path.exists()
        archived_exists = self.archived_path.exists()
        if active_exists != archived_exists:
            raise ConfigValidationError("活跃与封存配置必须同时存在或同时缺失")
        if active_exists:
            active = self.load_active()
            archived = self.load_archived()
            self._validate_sources(
                (*active, *(entry.source for entry in archived)),
                "活跃与封存配置",
            )
            return
        atomic_write_many(
            {
                self.active_path: self._active_bytes(()),
                self.archived_path: self._archived_bytes(()),
            },
            self.journal_path,
        )

    def load_active(self) -> tuple[Source, ...]:
        self._recover()
        document = self._read_document(self.active_path)
        raw_sources = self._versioned_sources(document, self.active_path.name)
        sources = tuple(source_from_dict(item) for item in raw_sources)
        self._validate_sources(sources, self.active_path.name)
        return sources

    def load_archived(self) -> tuple[ArchivedSource, ...]:
        self._recover()
        document = self._read_document(self.archived_path)
        raw_entries = self._versioned_sources(document, self.archived_path.name)
        entries: list[ArchivedSource] = []
        for value in raw_entries:
            if not isinstance(value, dict):
                raise ConfigValidationError("封存项必须是 JSON 对象")
            if set(value) != {"source", "archived_at", "reason"}:
                raise ConfigValidationError("封存项字段不完整或包含未知字段")
            archived_at = value["archived_at"]
            reason = value["reason"]
            if not isinstance(archived_at, str) or not isinstance(reason, str):
                raise ConfigValidationError("封存时间和原因必须是字符串")
            try:
                entries.append(
                    ArchivedSource(
                        source=source_from_dict(value["source"]),
                        archived_at=archived_at.strip(),
                        reason=reason.strip(),
                    )
                )
            except (TypeError, ValueError) as exc:
                raise ConfigValidationError(str(exc)) from exc
        result = tuple(entries)
        self._validate_sources(
            tuple(entry.source for entry in result),
            self.archived_path.name,
        )
        return result

    def add(
        self,
        source: Source,
        *,
        allow_shared_url: bool = False,
    ) -> Source:
        active = self.load_active()
        archived = self.load_archived()
        self._assert_unique(
            source,
            (*active, *(entry.source for entry in archived)),
            allow_shared_url=allow_shared_url,
        )
        atomic_write_bytes(
            self.active_path,
            self._active_bytes((*active, source)),
        )
        return source

    def archive(
        self,
        identity_key: str,
        *,
        reason: str,
        archived_at: str,
    ) -> ArchivedSource:
        active = self.load_active()
        archived = self.load_archived()
        matches = [
            source
            for source in active
            if source_identity(source).key == identity_key
        ]
        if len(matches) != 1:
            raise SourceNotFoundError(identity_key)
        source = matches[0]
        entry = ArchivedSource(
            source=source,
            archived_at=archived_at.strip(),
            reason=reason.strip(),
        )
        remaining = tuple(item for item in active if item is not source)
        atomic_write_many(
            {
                self.active_path: self._active_bytes(remaining),
                self.archived_path: self._archived_bytes((*archived, entry)),
            },
            self.journal_path,
        )
        return entry

    def restore(self, identity_key: str) -> Source:
        active = self.load_active()
        archived = self.load_archived()
        matches = [
            entry
            for entry in archived
            if source_identity(entry.source).key == identity_key
        ]
        if len(matches) != 1:
            raise SourceNotFoundError(identity_key)
        entry = matches[0]
        self._assert_unique(
            entry.source,
            active,
            allow_shared_url=True,
        )
        remaining = tuple(item for item in archived if item is not entry)
        atomic_write_many(
            {
                self.active_path: self._active_bytes((*active, entry.source)),
                self.archived_path: self._archived_bytes(remaining),
            },
            self.journal_path,
        )
        return entry.source

    def _recover(self) -> None:
        recover_atomic_batch(self.journal_path)

    @staticmethod
    def _read_document(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigValidationError(f"无法读取配置: {path.name}") from exc
        if not isinstance(value, dict):
            raise ConfigValidationError(f"{path.name} 必须是 JSON 对象")
        return value

    @staticmethod
    def _versioned_sources(
        document: dict[str, Any],
        label: str,
    ) -> list[Any]:
        if set(document) != {"schema_version", "sources"}:
            raise ConfigValidationError(f"{label} 字段不完整或包含未知字段")
        if document["schema_version"] != 2:
            raise ConfigValidationError(f"{label} schema_version 必须是 2")
        sources = document["sources"]
        if not isinstance(sources, list):
            raise ConfigValidationError(f"{label}.sources 必须是数组")
        return sources

    @staticmethod
    def _assert_unique(
        source: Source,
        existing: tuple[Source, ...],
        *,
        allow_shared_url: bool = False,
    ) -> None:
        candidate = source_identity(source)
        for item in existing:
            identity = source_identity(item)
            if identity.key == candidate.key or item.name == source.name:
                raise DuplicateSourceError(source.name)
            if identity.normalized_url != candidate.normalized_url:
                continue
            markers_are_distinct = bool(
                item.section_marker
                and source.section_marker
                and item.section_marker != source.section_marker
            )
            if not allow_shared_url or not markers_are_distinct:
                raise DuplicateSourceError(source.name)

    @classmethod
    def _validate_sources(
        cls,
        sources: tuple[Source, ...],
        label: str,
    ) -> None:
        accepted: list[Source] = []
        for source in sources:
            try:
                cls._assert_unique(
                    source,
                    tuple(accepted),
                    allow_shared_url=True,
                )
            except DuplicateSourceError as exc:
                raise ConfigValidationError(
                    f"{label} 包含重复站点: {source.name}"
                ) from exc
            accepted.append(source)

    @staticmethod
    def _encode(document: dict[str, Any]) -> bytes:
        return (
            json.dumps(document, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")

    @classmethod
    def _active_bytes(cls, sources: tuple[Source, ...]) -> bytes:
        return cls._encode(
            {
                "schema_version": 2,
                "sources": [source_to_dict(source) for source in sources],
            }
        )

    @classmethod
    def _archived_bytes(
        cls,
        entries: tuple[ArchivedSource, ...],
    ) -> bytes:
        return cls._encode(
            {
                "schema_version": 2,
                "sources": [
                    {
                        "source": source_to_dict(entry.source),
                        "archived_at": entry.archived_at,
                        "reason": entry.reason,
                    }
                    for entry in entries
                ],
            }
        )
