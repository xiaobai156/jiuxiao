from __future__ import annotations

import json
import unittest
import tempfile
from pathlib import Path

from v2.domain.errors import ErrorCode, Failure
from v2.domain.identity import source_identity
from v2.domain.models import (
    Document,
    DocumentMethod,
    Evidence,
    Position,
    Record,
    Source,
)
from v2.fetchers.registry import FetchError, FetchRequest, FetcherRegistry
from v2.parsers.registry import ParserRegistry
from v2.services.golden import (
    GoldenComparator,
    GoldenEntry,
    GoldenSnapshot,
    GoldenSource,
    snapshot_from_v2,
    snapshot_from_v1_document,
)
from v2.services.history import HistoricalAuditService
from v2.storage.golden import GoldenReportRepository, GoldenRepository
from v2.tests.golden.export_v2 import _ocr_documents_from_cache
from v2.validator import Validator


def source(name: str = "甲", suffix: str = "a") -> Source:
    return Source(
        name=name,
        url=f"https://example.test/{suffix}",
        position=Position.BOTTOM,
        section_marker=name,
        fetcher="fake",
        parser="fake",
    )


def record(issue: int, zodiac: str, name: str, line_index: int) -> Record:
    return Record(
        issue=issue,
        zodiacs=tuple(zodiac),
        evidence=Evidence(
            method="fixture",
            source_line=f"{issue}期：{zodiac}",
            directory_anchor=name,
            document_label="fixture",
            metadata=(
                ("document_index", "0"),
                ("line_index", str(line_index)),
                ("group_text", "棋书琴"),
            ),
        ),
    )


class FakeFetcher:
    def __init__(self, failure: Failure | None = None) -> None:
        self.failure = failure
        self.calls: list[tuple[int, ...]] = []
        self.history_modes: list[bool] = []

    async def fetch(
        self,
        source: Source,
        request: FetchRequest,
    ) -> tuple[Document, ...]:
        self.calls.append(request.issues)
        self.history_modes.append(request.history_mode)
        if self.failure:
            raise FetchError(self.failure)
        return (
            Document(
                "fixture",
                source.url,
                "history",
                DocumentMethod.STATIC_PAGE,
            ),
        )


class FakeParser:
    def __init__(self, records: tuple[Record, ...]) -> None:
        self.records = records
        self.calls = 0

    def parse(
        self,
        source: Source,
        documents: tuple[Document, ...],
        issues: tuple[int, ...],
    ) -> tuple[Record, ...]:
        self.calls += 1
        return self.records


class HistoricalAuditTests(unittest.IsolatedAsyncioTestCase):
    async def test_fixed_history_range_is_not_displaced_by_newer_issue(
        self,
    ) -> None:
        item = source()
        records = tuple(
            record(
                issue,
                "鼠牛虎兔龙蛇马羊猴",
                item.name,
                line_index,
            )
            for line_index, issue in enumerate(range(201, 212))
        )
        fetchers = FetcherRegistry()
        fetchers.register("fake", FakeFetcher())
        parsers = ParserRegistry()
        parsers.register("fake", FakeParser(records))
        service = HistoricalAuditService(fetchers, parsers, Validator())
        issues = tuple(range(210, 200, -1))

        audit = await service.audit_one(item, issues)

        self.assertTrue(all(result.successful for result in audit.results))

    async def test_audit_many_preserves_order_and_rejects_zero_concurrency(
        self,
    ) -> None:
        item = source()
        fetcher = FakeFetcher()
        parser = FakeParser(
            (record(210, "鼠牛虎兔龙蛇马羊猴", item.name, 0),)
        )
        fetchers = FetcherRegistry()
        fetchers.register("fake", fetcher)
        parsers = ParserRegistry()
        parsers.register("fake", parser)
        service = HistoricalAuditService(fetchers, parsers, Validator())

        with self.assertRaises(ValueError):
            await service.audit_many((item,), (210,), concurrency=0)
        audits = await service.audit_many(
            (item, item),
            (210,),
            concurrency=1,
        )

        self.assertEqual([audit.source for audit in audits], [item, item])
        self.assertEqual(fetcher.calls, [(210,), (210,)])

    async def test_unknown_registry_key_fails_every_requested_issue(self) -> None:
        item = source()
        service = HistoricalAuditService(
            FetcherRegistry(),
            ParserRegistry(),
            Validator(),
        )

        audit = await service.audit_one(item, (210, 209))

        self.assertEqual(
            [result.failures[0].code for result in audit.results],
            [ErrorCode.CONFIG_INVALID, ErrorCode.CONFIG_INVALID],
        )

    async def test_each_issue_uses_the_full_requested_history_window(self) -> None:
        item = source()
        records = tuple(
            record(
                issue,
                "鼠牛虎兔龙蛇马羊猴",
                item.name,
                line_index,
            )
            for line_index, issue in enumerate((207, 208, 209, 210))
        )
        fetchers = FetcherRegistry()
        fetchers.register("fake", FakeFetcher())
        parsers = ParserRegistry()
        parsers.register("fake", FakeParser(records))
        service = HistoricalAuditService(fetchers, parsers, Validator())

        audit = await service.audit_one(item, (210, 209, 208, 207))

        self.assertTrue(all(result.successful for result in audit.results))

    async def test_fetches_once_and_validates_each_issue_independently(self) -> None:
        item = source()
        fetcher = FakeFetcher()
        parser = FakeParser(
            (record(210, "鼠牛虎兔龙蛇马羊猴", item.name, 0),)
        )
        fetchers = FetcherRegistry()
        fetchers.register("fake", fetcher)
        parsers = ParserRegistry()
        parsers.register("fake", parser)
        service = HistoricalAuditService(fetchers, parsers, Validator())

        audit = await service.audit_one(item, (210, 209))

        self.assertEqual(fetcher.calls, [(210, 209)])
        self.assertEqual(fetcher.history_modes, [True])
        self.assertEqual(parser.calls, 1)
        self.assertTrue(audit.results[0].successful)
        self.assertFalse(audit.results[1].successful)
        self.assertIs(audit.results[1].failures[0].code, ErrorCode.ISSUE_MISSING)

    async def test_global_fetch_failure_is_copied_to_every_concrete_issue(
        self,
    ) -> None:
        item = source()
        fetchers = FetcherRegistry()
        fetchers.register(
            "fake",
            FakeFetcher(Failure(ErrorCode.FETCH_FAILED, detail="network")),
        )
        parsers = ParserRegistry()
        parsers.register("fake", FakeParser(()))
        service = HistoricalAuditService(fetchers, parsers, Validator())

        audit = await service.audit_one(item, (210, 209))

        self.assertEqual(
            [result.failures[0].code for result in audit.results],
            [ErrorCode.FETCH_FAILED, ErrorCode.FETCH_FAILED],
        )


class GoldenOcrFixtureTests(unittest.TestCase):
    def test_cache_fixture_builds_oldest_first_ocr_without_image_index(
        self,
    ) -> None:
        item = Source(
            name="嫦娥公式",
            url="https://example.test/ocr",
            position=Position.BOTTOM,
            section_marker="澳门公式",
            fetcher="browser_page",
            parser="image_ocr",
        )
        cached = {
            "records": {
                "210": "羊马蛇龙兔虎牛鼠猪",
                "209": "兔虎牛鼠猪狗鸡猴羊",
            },
            "audit": {
                "210": {"source_line": "210期：羊马蛇龙兔虎牛鼠猪"},
                "209": {"source_line": "209期：兔虎牛鼠猪狗鸡猴羊"},
            },
        }

        documents = _ocr_documents_from_cache(item, cached, (210, 209))

        self.assertEqual(
            [document.method for document in documents],
            [DocumentMethod.BROWSER_DOM, DocumentMethod.IMAGE_OCR],
        )
        self.assertEqual(
            documents[1].text.splitlines(),
            [
                "209期：兔虎牛鼠猪狗鸡猴羊",
                "210期：羊马蛇龙兔虎牛鼠猪",
            ],
        )
        self.assertEqual(documents[1].metadata, ())


def entry(
    issue: int,
    zodiac: str = "鼠牛虎兔龙蛇马羊猴",
    *,
    error: str = "",
    line: str | None = None,
    anchor: str = "甲",
) -> GoldenEntry:
    return GoldenEntry(
        issue=issue,
        zodiac=zodiac if not error else "",
        error=error,
        evidence=(
            ("source_line", line or f"{issue}期：{zodiac}"),
            ("directory_anchor", anchor),
            ("group_text", "棋书琴"),
        ),
    )


class GoldenComparatorTests(unittest.TestCase):
    def test_evidence_ignores_group_mapping_note_but_not_result_change(
        self,
    ) -> None:
        expected = GoldenSnapshot(
            "v1",
            (210,),
            (
                GoldenSource(
                    "id-a",
                    "甲",
                    (
                        entry(
                            210,
                            line="210期：琴棋书画【棋书琴】开00准",
                        ),
                    ),
                ),
            ),
        )
        mapping_note = GoldenSnapshot(
            "v2",
            (210,),
            (
                GoldenSource(
                    "id-a",
                    "甲",
                    (
                        entry(
                            210,
                            line=(
                                "210期：琴棋书画【棋书琴】开00准 "
                                "琴:兔蛇鸡 棋:鼠牛狗"
                            ),
                        ),
                    ),
                ),
            ),
        )
        changed_result = GoldenSnapshot(
            "v2",
            (210,),
            (
                GoldenSource(
                    "id-a",
                    "甲",
                    (
                        entry(
                            210,
                            line="210期：琴棋书画【棋书琴】开马49准",
                        ),
                    ),
                ),
            ),
        )

        self.assertTrue(
            GoldenComparator().compare(expected, mapping_note).equal
        )
        report = GoldenComparator().compare(expected, changed_result)
        self.assertEqual(report.differences[0].kind, "EVIDENCE_MISMATCH")

    def test_difference_report_is_written_atomically_with_kind_summary(
        self,
    ) -> None:
        expected = GoldenSnapshot(
            "v1",
            (210,),
            (GoldenSource("id-a", "甲", (entry(210),)),),
        )
        actual = GoldenSnapshot(
            "v2",
            (210,),
            (
                GoldenSource(
                    "id-a",
                    "甲",
                    (entry(210, "牛鼠虎兔龙蛇马羊猴"),),
                ),
            ),
        )
        report = GoldenComparator().compare(expected, actual)

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "diff.json"
            GoldenReportRepository(path).write(report)
            document = json.loads(path.read_text(encoding="utf-8"))

        self.assertFalse(document["equal"])
        self.assertEqual(document["difference_count"], 1)
        self.assertEqual(document["summary"], {"VALUE_MISMATCH": 1})
        self.assertEqual(document["differences"][0]["source_name"], "甲")

    def test_v1_document_uses_current_identity_and_maps_chinese_errors(self) -> None:
        item = source()
        document = {
            "schema_version": 1,
            "engine": "v1",
            "issues": [210, 209],
            "sources": [
                {
                    "source": {
                        "name": item.name,
                        "url": item.url,
                        "position": "尾部",
                    },
                    "records": {"210": "鼠牛虎兔龙蛇马羊猴"},
                    "audit": {
                        "210": {
                            "source_line": "210期：鼠牛虎兔龙蛇马羊猴",
                            "directory_anchor": item.name,
                        }
                    },
                    "errors": ["article/admin 接口请求失败，未触发浏览器兜底"],
                }
            ],
        }

        snapshot = snapshot_from_v1_document(document, (item,), (210, 209))

        self.assertEqual(
            snapshot.sources[0].identity_key,
            source_identity(item).key,
        )
        self.assertEqual(snapshot.sources[0].entries[0].zodiac, "鼠牛虎兔龙蛇马羊猴")
        self.assertEqual(
            snapshot.sources[0].entries[1].error,
            ErrorCode.FETCH_FAILED.value,
        )

    def test_golden_repository_round_trip_preserves_order(self) -> None:
        snapshot = GoldenSnapshot(
            "v1",
            (210, 209),
            (
                GoldenSource("id-a", "甲", (entry(210), entry(209))),
            ),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = GoldenRepository(Path(temp_dir) / "golden.json")

            repository.write(snapshot)

            self.assertEqual(repository.load(), snapshot)

    def test_aligns_by_identity_and_issue_not_list_position(self) -> None:
        first = GoldenSource("id-a", "甲", (entry(210), entry(209)))
        second = GoldenSource("id-b", "乙", (entry(210), entry(209)))
        expected = GoldenSnapshot("v1", (210, 209), (first, second))
        actual = GoldenSnapshot("v2", (210, 209), (second, first))

        report = GoldenComparator().compare(expected, actual)

        self.assertEqual(report.differences, ())

    def test_detects_order_error_category_and_evidence_differences(self) -> None:
        expected = GoldenSnapshot(
            "v1",
            (210, 209, 208),
            (
                GoldenSource(
                    "id-a",
                    "甲",
                    (
                        entry(210),
                        entry(209, error=ErrorCode.FETCH_FAILED.value),
                        entry(208),
                    ),
                ),
            ),
        )
        actual = GoldenSnapshot(
            "v2",
            (210, 209, 208),
            (
                GoldenSource(
                    "id-a",
                    "甲",
                    (
                        entry(210, "牛鼠虎兔龙蛇马羊猴"),
                        entry(209, error=ErrorCode.HTTP_ERROR.value),
                        entry(208, line="different evidence"),
                    ),
                ),
            ),
        )

        report = GoldenComparator().compare(expected, actual)

        self.assertEqual(
            [difference.kind for difference in report.differences],
            ["VALUE_MISMATCH", "ERROR_MISMATCH", "EVIDENCE_MISMATCH"],
        )

    def test_snapshot_from_v2_keeps_original_order_and_evidence(self) -> None:
        item = source()
        value = record(210, "鼠牛虎兔龙蛇马羊猴", item.name, 0)
        fetchers = FetcherRegistry()
        fetchers.register("fake", FakeFetcher())
        parsers = ParserRegistry()
        parsers.register("fake", FakeParser((value,)))
        service = HistoricalAuditService(fetchers, parsers, Validator())

        async def build():
            audit = await service.audit_one(item, (210,))
            return snapshot_from_v2((audit,), (210,))

        snapshot = self._run(build())
        golden_entry = snapshot.sources[0].entries[0]
        self.assertEqual(golden_entry.zodiac, value.zodiac_text)
        self.assertEqual(
            dict(golden_entry.evidence)["source_line"],
            value.evidence.source_line,
        )

    @staticmethod
    def _run(coroutine):
        import asyncio

        return asyncio.run(coroutine)


if __name__ == "__main__":
    unittest.main()
