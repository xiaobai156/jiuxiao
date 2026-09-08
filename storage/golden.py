from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from v2.services.golden import (
    GoldenEntry,
    GoldenReport,
    GoldenSnapshot,
    GoldenSource,
)
from v2.storage.atomic import atomic_write_bytes


class GoldenReportRepository:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def write(self, report: GoldenReport) -> GoldenReport:
        summary = Counter(
            difference.kind for difference in report.differences
        )
        document = {
            "schema_version": 1,
            "expected_engine": report.expected_engine,
            "actual_engine": report.actual_engine,
            "equal": report.equal,
            "difference_count": len(report.differences),
            "summary": dict(sorted(summary.items())),
            "differences": [
                {
                    "identity_key": difference.identity_key,
                    "source_name": difference.source_name,
                    "issue": difference.issue,
                    "kind": difference.kind,
                    "expected": difference.expected,
                    "actual": difference.actual,
                }
                for difference in report.differences
            ],
        }
        payload = (
            json.dumps(document, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
        atomic_write_bytes(self.path, payload)
        return report


class GoldenRepository:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def write(self, snapshot: GoldenSnapshot) -> GoldenSnapshot:
        document = {
            "schema_version": 1,
            "engine": snapshot.engine,
            "issues": list(snapshot.issues),
            "sources": [
                {
                    "identity_key": source.identity_key,
                    "name": source.name,
                    "entries": [
                        {
                            "issue": entry.issue,
                            "zodiac": entry.zodiac,
                            "error": entry.error,
                            "evidence": dict(entry.evidence),
                        }
                        for entry in source.entries
                    ],
                }
                for source in snapshot.sources
            ],
        }
        payload = (
            json.dumps(document, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
        atomic_write_bytes(self.path, payload)
        return snapshot

    def load(self) -> GoldenSnapshot:
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
            return self._from_document(document)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid golden snapshot: {self.path.name}") from exc

    @staticmethod
    def _from_document(document: Any) -> GoldenSnapshot:
        if not isinstance(document, dict) or set(document) != {
            "schema_version",
            "engine",
            "issues",
            "sources",
        }:
            raise ValueError("invalid golden fields")
        if document["schema_version"] != 1:
            raise ValueError("invalid golden schema")
        if not isinstance(document["engine"], str):
            raise ValueError("invalid golden engine")
        issues = tuple(int(issue) for issue in document["issues"])
        raw_sources = document["sources"]
        if not isinstance(raw_sources, list):
            raise ValueError("invalid golden sources")
        sources: list[GoldenSource] = []
        for raw_source in raw_sources:
            if not isinstance(raw_source, dict) or set(raw_source) != {
                "identity_key",
                "name",
                "entries",
            }:
                raise ValueError("invalid golden source")
            raw_entries = raw_source["entries"]
            if not isinstance(raw_entries, list):
                raise ValueError("invalid golden entries")
            entries: list[GoldenEntry] = []
            for raw_entry in raw_entries:
                if not isinstance(raw_entry, dict) or set(raw_entry) != {
                    "issue",
                    "zodiac",
                    "error",
                    "evidence",
                }:
                    raise ValueError("invalid golden entry")
                evidence = raw_entry["evidence"]
                if not isinstance(evidence, dict):
                    raise ValueError("invalid golden evidence")
                entries.append(
                    GoldenEntry(
                        issue=int(raw_entry["issue"]),
                        zodiac=str(raw_entry["zodiac"]),
                        error=str(raw_entry["error"]),
                        evidence=tuple(
                            (str(name), str(value))
                            for name, value in evidence.items()
                        ),
                    )
                )
            sources.append(
                GoldenSource(
                    str(raw_source["identity_key"]),
                    str(raw_source["name"]),
                    tuple(entries),
                )
            )
        return GoldenSnapshot(
            document["engine"],
            issues,
            tuple(sources),
        )
