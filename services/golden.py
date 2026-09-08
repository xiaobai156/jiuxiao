from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from v2.domain.errors import ErrorCode
from v2.domain.identity import normalize_url, source_identity
from v2.domain.models import Source
from v2.services.history import HistoricalSourceAudit


EVIDENCE_KEYS = (
    "source_line",
    "directory_anchor",
    "group_type",
    "group_text",
    "article_id",
    "record_path",
    "api_url",
    "image_index",
)
GROUP_MAPPING_NOTE = re.compile(
    r"\s+(?:琴|棋|书|画|梅|兰|菊|竹|东|南|西|北|春|夏|秋|冬|风|雨|雷|电)"
    r"(?:天生肖|肖)?\s*[:：]"
)


@dataclass(frozen=True, slots=True)
class GoldenEntry:
    issue: int
    zodiac: str = ""
    error: str = ""
    evidence: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class GoldenSource:
    identity_key: str
    name: str
    entries: tuple[GoldenEntry, ...]


@dataclass(frozen=True, slots=True)
class GoldenSnapshot:
    engine: str
    issues: tuple[int, ...]
    sources: tuple[GoldenSource, ...]


@dataclass(frozen=True, slots=True)
class GoldenDifference:
    identity_key: str
    source_name: str
    issue: int
    kind: str
    expected: str
    actual: str


@dataclass(frozen=True, slots=True)
class GoldenReport:
    expected_engine: str
    actual_engine: str
    differences: tuple[GoldenDifference, ...]

    @property
    def equal(self) -> bool:
        return not self.differences


def snapshot_from_v2(
    audits: tuple[HistoricalSourceAudit, ...],
    issues: tuple[int, ...],
) -> GoldenSnapshot:
    sources: list[GoldenSource] = []
    for audit in audits:
        by_issue = {
            result.requested_issues[0]: result for result in audit.results
        }
        entries: list[GoldenEntry] = []
        for issue in issues:
            result = by_issue.get(issue)
            if result is None:
                entries.append(
                    GoldenEntry(issue, error="MISSING_RESULT")
                )
                continue
            if not result.successful:
                entries.append(
                    GoldenEntry(issue, error=result.failures[0].code.value)
                )
                continue
            records = result.history.records_for(issue)
            if len(records) != 1:
                entries.append(
                    GoldenEntry(issue, error="INVALID_RESULT")
                )
                continue
            record = records[0]
            evidence = (
                ("method", record.evidence.method),
                ("source_line", record.evidence.source_line),
                ("directory_anchor", record.evidence.directory_anchor),
                ("document_label", record.evidence.document_label),
                *record.evidence.metadata,
            )
            entries.append(
                GoldenEntry(
                    issue=issue,
                    zodiac=record.zodiac_text,
                    evidence=evidence,
                )
            )
        sources.append(
            GoldenSource(
                source_identity(audit.source).key,
                audit.source.name,
                tuple(entries),
            )
        )
    return GoldenSnapshot("v2", issues, tuple(sources))


def snapshot_from_v1_document(
    document: Any,
    sources: tuple[Source, ...],
    issues: tuple[int, ...],
) -> GoldenSnapshot:
    if not isinstance(document, dict) or set(document) != {
        "schema_version",
        "engine",
        "issues",
        "sources",
    }:
        raise ValueError("V1 golden document fields are invalid")
    if document["schema_version"] != 1 or document["engine"] != "v1":
        raise ValueError("V1 golden document version is invalid")
    if tuple(document["issues"]) != issues:
        raise ValueError("V1 golden issues do not match")
    raw_sources = document["sources"]
    if not isinstance(raw_sources, list):
        raise ValueError("V1 golden sources must be a list")
    by_source: dict[tuple[str, str], dict[str, Any]] = {}
    for item in raw_sources:
        if not isinstance(item, dict):
            raise ValueError("V1 golden source must be an object")
        raw_source = item.get("source")
        if not isinstance(raw_source, dict):
            raise ValueError("V1 golden source identity is invalid")
        name = str(raw_source.get("name", "")).strip()
        url = normalize_url(str(raw_source.get("url", "")))
        key = (name, url)
        if key in by_source:
            raise ValueError("duplicate V1 golden source")
        by_source[key] = item

    golden_sources: list[GoldenSource] = []
    for source in sources:
        key = (source.name, normalize_url(source.url))
        raw = by_source.get(key)
        entries: list[GoldenEntry] = []
        if raw is None:
            entries = [
                GoldenEntry(issue, error="SOURCE_MISSING") for issue in issues
            ]
        else:
            records = raw.get("records", {})
            audit = raw.get("audit", {})
            errors = raw.get("errors", [])
            if (
                not isinstance(records, dict)
                or not isinstance(audit, dict)
                or not isinstance(errors, list)
            ):
                raise ValueError("V1 golden history is invalid")
            error = classify_v1_error(" | ".join(map(str, errors)))
            for issue in issues:
                zodiac = records.get(str(issue), records.get(issue, ""))
                if zodiac:
                    raw_evidence = audit.get(str(issue), audit.get(issue, {}))
                    if not isinstance(raw_evidence, dict):
                        raise ValueError("V1 golden evidence is invalid")
                    entries.append(
                        GoldenEntry(
                            issue,
                            zodiac=str(zodiac),
                            evidence=tuple(
                                (str(name), str(value))
                                for name, value in raw_evidence.items()
                            ),
                        )
                    )
                else:
                    entries.append(
                        GoldenEntry(
                            issue,
                            error=error or ErrorCode.ISSUE_MISSING.value,
                        )
                    )
        golden_sources.append(
            GoldenSource(
                source_identity(source).key,
                source.name,
                tuple(entries),
            )
        )
    return GoldenSnapshot("v1", issues, tuple(golden_sources))


def classify_v1_error(value: str) -> str:
    text = str(value)
    rules = (
        (("隐藏内容", "锁定内容", "未公开"), ErrorCode.LOCKED_CONTENT),
        (("冲突",), ErrorCode.CANDIDATE_CONFLICT),
        (("跨域",), ErrorCode.CROSS_DOMAIN),
        (("HTTP",), ErrorCode.HTTP_ERROR),
        (("请求失败", "Failed to fetch", "浏览器未返回"), ErrorCode.FETCH_FAILED),
        (("关键字", "目录"), ErrorCode.ANCHOR_MISSING),
        (("无效位置", "位置不一致"), ErrorCode.DIRECTION_INVALID),
        (("生肖内重复", "数量"), ErrorCode.INVALID_ZODIAC_COUNT),
        (("来源不可信",), ErrorCode.SOURCE_UNTRUSTED),
    )
    for markers, code in rules:
        if any(marker in text for marker in markers):
            return code.value
    return ""


class GoldenComparator:
    def compare(
        self,
        expected: GoldenSnapshot,
        actual: GoldenSnapshot,
    ) -> GoldenReport:
        if expected.issues != actual.issues:
            raise ValueError("golden issue order does not match")
        left = self._sources(expected)
        right = self._sources(actual)
        identities = tuple(dict.fromkeys((*left, *right)))
        differences: list[GoldenDifference] = []
        for identity_key in identities:
            left_source = left.get(identity_key)
            right_source = right.get(identity_key)
            source = left_source or right_source
            if left_source is None or right_source is None:
                differences.append(
                    GoldenDifference(
                        identity_key,
                        source.name,
                        0,
                        "SOURCE_MISSING",
                        "present" if left_source else "missing",
                        "present" if right_source else "missing",
                    )
                )
                continue
            left_entries = self._entries(left_source)
            right_entries = self._entries(right_source)
            for issue in expected.issues:
                before = left_entries.get(issue)
                after = right_entries.get(issue)
                if before is None or after is None:
                    differences.append(
                        GoldenDifference(
                            identity_key,
                            source.name,
                            issue,
                            "ENTRY_MISSING",
                            "present" if before else "missing",
                            "present" if after else "missing",
                        )
                    )
                    continue
                difference = self._entry_difference(
                    identity_key,
                    source.name,
                    before,
                    after,
                )
                if difference is not None:
                    differences.append(difference)
        return GoldenReport(
            expected.engine,
            actual.engine,
            tuple(differences),
        )

    @staticmethod
    def _entry_difference(
        identity_key: str,
        source_name: str,
        expected: GoldenEntry,
        actual: GoldenEntry,
    ) -> GoldenDifference | None:
        if expected.error or actual.error:
            if expected.error != actual.error:
                return GoldenDifference(
                    identity_key,
                    source_name,
                    expected.issue,
                    "ERROR_MISMATCH",
                    expected.error or "SUCCESS",
                    actual.error or "SUCCESS",
                )
            return None
        if expected.zodiac != actual.zodiac:
            return GoldenDifference(
                identity_key,
                source_name,
                expected.issue,
                "VALUE_MISMATCH",
                expected.zodiac,
                actual.zodiac,
            )
        before = GoldenComparator._evidence(expected.evidence)
        after = GoldenComparator._evidence(actual.evidence)
        if before != after:
            return GoldenDifference(
                identity_key,
                source_name,
                expected.issue,
                "EVIDENCE_MISMATCH",
                repr(before),
                repr(after),
            )
        return None

    @staticmethod
    def _evidence(
        evidence: tuple[tuple[str, str], ...],
    ) -> tuple[tuple[str, str], ...]:
        values = dict(evidence)
        return tuple(
            (
                key,
                GoldenComparator._evidence_value(key, values[key]),
            )
            for key in EVIDENCE_KEYS
            if key in values
        )

    @staticmethod
    def _evidence_value(key: str, value: str) -> str:
        normalized = " ".join(str(value).split())
        if key == "source_line":
            normalized = GROUP_MAPPING_NOTE.split(normalized, maxsplit=1)[0]
        return normalized

    @staticmethod
    def _sources(snapshot: GoldenSnapshot) -> dict[str, GoldenSource]:
        result: dict[str, GoldenSource] = {}
        for source in snapshot.sources:
            if source.identity_key in result:
                raise ValueError("duplicate golden source identity")
            result[source.identity_key] = source
        return result

    @staticmethod
    def _entries(source: GoldenSource) -> dict[int, GoldenEntry]:
        result: dict[int, GoldenEntry] = {}
        for entry in source.entries:
            if entry.issue in result:
                raise ValueError("duplicate golden issue")
            result[entry.issue] = entry
        return result
