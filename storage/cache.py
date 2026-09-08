from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from v2.config.schema import source_from_dict, source_to_dict
from v2.domain.errors import ErrorCode
from v2.domain.models import Source
from v2.storage.atomic import atomic_write_bytes


@dataclass(frozen=True, slots=True)
class CacheSource:
    source: Source
    current_issue: int | None = None
    records: tuple[tuple[int, str], ...] = ()
    errors: tuple[tuple[int, ErrorCode], ...] = ()


@dataclass(frozen=True, slots=True)
class CacheSnapshot:
    latest_issue: int | None = None
    issues: tuple[int, ...] = ()
    sources: tuple[CacheSource, ...] = ()


class CacheRepository:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> CacheSnapshot:
        if not self.path.exists():
            return CacheSnapshot()
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
            return self._from_document(document)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid cache: {self.path.name}") from exc

    def sync(self, snapshot: CacheSnapshot) -> CacheSnapshot:
        atomic_write_bytes(self.path, self._encode(snapshot))
        return snapshot

    @classmethod
    def _from_document(cls, document: Any) -> CacheSnapshot:
        expected = {
            "schema_version",
            "latest_issue",
            "issues",
            "sources",
        }
        if not isinstance(document, dict) or set(document) != expected:
            raise ValueError("invalid cache fields")
        if document["schema_version"] != 2:
            raise ValueError("invalid cache schema")
        raw_issues = document["issues"]
        raw_sources = document["sources"]
        if not isinstance(raw_issues, list) or not isinstance(raw_sources, list):
            raise ValueError("invalid cache collections")
        issues = tuple(cls._issue(value) for value in raw_issues)
        latest = document["latest_issue"]
        if latest is not None:
            latest = cls._issue(latest)
        sources: list[CacheSource] = []
        for item in raw_sources:
            required = {"source", "current_issue", "records", "errors"}
            if not isinstance(item, dict) or set(item) != required:
                raise ValueError("invalid cache source")
            current = item["current_issue"]
            if current is not None:
                current = cls._issue(current)
            sources.append(
                CacheSource(
                    source=source_from_dict(item["source"]),
                    current_issue=current,
                    records=cls._record_pairs(item["records"]),
                    errors=cls._error_pairs(item["errors"]),
                )
            )
        return CacheSnapshot(latest, issues, tuple(sources))

    @staticmethod
    def _issue(value: Any) -> int:
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ValueError("invalid issue")
        return value

    @classmethod
    def _record_pairs(cls, value: Any) -> tuple[tuple[int, str], ...]:
        if not isinstance(value, dict):
            raise ValueError("invalid records")
        return tuple(
            (cls._issue_key(issue), str(zodiac))
            for issue, zodiac in value.items()
        )

    @classmethod
    def _error_pairs(cls, value: Any) -> tuple[tuple[int, ErrorCode], ...]:
        if not isinstance(value, dict):
            raise ValueError("invalid errors")
        return tuple(
            (cls._issue_key(issue), ErrorCode(code))
            for issue, code in value.items()
        )

    @classmethod
    def _issue_key(cls, value: Any) -> int:
        if not isinstance(value, str) or not value.isdigit():
            raise ValueError("invalid issue key")
        return cls._issue(int(value))

    @classmethod
    def _encode(cls, snapshot: CacheSnapshot) -> bytes:
        document = {
            "schema_version": 2,
            "latest_issue": snapshot.latest_issue,
            "issues": list(snapshot.issues),
            "sources": [
                {
                    "source": source_to_dict(item.source),
                    "current_issue": item.current_issue,
                    "records": {str(issue): value for issue, value in item.records},
                    "errors": {str(issue): code.value for issue, code in item.errors},
                }
                for item in snapshot.sources
            ],
        }
        text = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
        return text.encode("utf-8")
