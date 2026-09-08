from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from v2.domain.errors import ErrorCode
from v2.domain.models import Document, DocumentMethod, Position, Source
from v2.fetchers.registry import FetcherRegistry
from v2.parsers.custom.profile_history import ProfileHistoryParser
from v2.parsers.direct_nine import DirectNineParser
from v2.parsers.registry import ParserRegistry
from v2.services.cache_sync import CacheSyncService, CacheWriteForbiddenError
from v2.services.crawl import CrawlService
from v2.storage.cache import CacheRepository
from v2.storage.reports import ReportRepository
from v2.validator import ValidationError, Validator


def source(
    *,
    position: Position = Position.BOTTOM,
    fetcher: str = "browser_page",
    parser: str = "direct_nine",
    name: str = "测试站",
    marker: str = "测试站",
    aliases: tuple[str, ...] = (),
    data_marker: str = "九肖",
    source_policy: tuple[str, ...] = (),
) -> Source:
    return Source(
        name=name,
        url="https://example.test/page",
        position=position,
        section_marker=marker,
        fetcher=fetcher,
        parser=parser,
        aliases=aliases,
        data_marker=data_marker,
        source_policy=source_policy,
    )


def document(
    text: str,
    method: DocumentMethod = DocumentMethod.BROWSER_DOM,
    *,
    label: str | None = None,
    url: str = "https://example.test/page",
    metadata: tuple[tuple[str, str], ...] = (),
) -> Document:
    return Document(
        label=label or method.value,
        url=url,
        text=text,
        method=method,
        metadata=metadata,
    )


class LayeredCandidateValidationTests(unittest.TestCase):
    def test_bottom_selects_last_same_issue_candidate_and_marks_position(
        self,
    ) -> None:
        item = source(position=Position.BOTTOM)
        body = document(
            "\n".join(
                (
                    "测试站",
                    "212期 九肖【鼠牛虎兔龙蛇马羊猴】",
                    "212期 九肖【鼠牛虎兔龙蛇马羊猴】",
                    "211期 九肖【虎兔龙蛇马羊猴鸡狗】",
                )
            )
        )

        records = DirectNineParser().parse(item, (body,), (212,))
        verified = Validator().validate(item, records, (212,))

        selected = verified.history.records[0]
        self.assertEqual(
            selected.zodiac_text,
            "鼠牛虎兔龙蛇马羊猴",
        )
        self.assertEqual(
            dict(selected.evidence.metadata)["issue_position"],
            "2",
        )
        self.assertEqual(
            dict(selected.evidence.metadata)["issue_count"],
            "2",
        )

    def test_top_selects_first_same_issue_candidate_and_marks_position(
        self,
    ) -> None:
        item = source(position=Position.TOP)
        body = document(
            "\n".join(
                (
                    "测试站",
                    "212期 九肖【鼠牛虎兔龙蛇马羊猴】",
                    "212期 九肖【鼠牛虎兔龙蛇马羊猴】",
                    "211期 九肖【虎兔龙蛇马羊猴鸡狗】",
                )
            )
        )

        records = DirectNineParser().parse(item, (body,), (212,))
        verified = Validator().validate(item, records, (212,))

        selected = verified.history.records[0]
        self.assertEqual(
            selected.zodiac_text,
            "鼠牛虎兔龙蛇马羊猴",
        )
        self.assertEqual(
            dict(selected.evidence.metadata)["issue_position"],
            "1",
        )
        self.assertEqual(
            dict(selected.evidence.metadata)["issue_count"],
            "2",
        )

    def test_same_issue_conflict_inside_direction_window_is_rejected(self) -> None:
        item = source(position=Position.TOP)
        body = document(
            "\n".join(
                (
                    "测试站",
                    "212期 九肖【鼠牛虎兔龙蛇马羊猴】",
                    "212期 九肖【牛虎兔龙蛇马羊猴鸡】",
                    "211期 九肖【虎兔龙蛇马羊猴鸡狗】",
                )
            )
        )

        records = DirectNineParser().parse(item, (body,), (212,))

        with self.assertRaises(ValidationError) as raised:
            Validator().validate(item, records, (212,))
        self.assertEqual(
            raised.exception.failure.code,
            ErrorCode.CANDIDATE_CONFLICT,
        )

    def test_source_contract_keeps_data_semantic_and_document_policy(self) -> None:
        item = source(source_policy=("browser_dom", "browser_frame"))

        self.assertEqual(item.data_marker, "九肖")
        self.assertEqual(
            item.source_policy,
            ("browser_dom", "browser_frame"),
        )

    def test_bottom_never_treats_script_as_the_visual_page_tail(self) -> None:
        item = source(position=Position.BOTTOM)
        dom = document(
            "\n".join(
                (
                    "测试站",
                    "209期 九肖【鼠牛虎兔龙蛇马羊猴】",
                    "210期 九肖【牛虎兔龙蛇马羊猴鸡】",
                    "211期 九肖【虎兔龙蛇马羊猴鸡狗】",
                )
            )
        )
        script = document(
            "测试站\n211期 九肖【蛇马羊猴鸡狗猪鼠牛】",
            DocumentMethod.SCRIPT,
        )

        records = DirectNineParser().parse(item, (dom, script), (211,))

        with self.assertRaises(ValidationError) as raised:
            Validator().validate(item, records, (211,))
        self.assertEqual(
            raised.exception.failure.code,
            ErrorCode.DOCUMENT_CONFLICT,
        )

    def test_same_origin_iframe_conflict_is_not_a_direction_tiebreaker(
        self,
    ) -> None:
        item = source(position=Position.TOP)
        dom = document(
            "测试站\n211期 九肖【鼠牛虎兔龙蛇马羊猴】"
        )
        frame = document(
            "测试站\n211期 九肖【牛虎兔龙蛇马羊猴鸡】",
            DocumentMethod.BROWSER_FRAME,
            label="browser-frame:1",
        )

        records = DirectNineParser().parse(item, (dom, frame), (211,))

        with self.assertRaises(ValidationError) as raised:
            Validator().validate(item, records, (211,))
        self.assertEqual(
            raised.exception.failure.code,
            ErrorCode.DOCUMENT_CONFLICT,
        )

    def test_secondary_document_conflict_outside_its_window_is_rejected(
        self,
    ) -> None:
        item = source(position=Position.TOP)
        dom = document(
            "测试站\n211期 九肖【鼠牛虎兔龙蛇马羊猴】"
        )
        secondary_text = "\n".join(
            (
                "测试站",
                "210期 九肖【牛虎兔龙蛇马羊猴鸡】",
                "209期 九肖【虎兔龙蛇马羊猴鸡狗】",
                "208期 九肖【兔龙蛇马羊猴鸡狗猪】",
                "211期 九肖【蛇马羊猴鸡狗猪鼠牛】",
            )
        )

        for method in (
            DocumentMethod.BROWSER_FRAME,
            DocumentMethod.SCRIPT,
        ):
            with self.subTest(method=method):
                secondary = document(
                    secondary_text,
                    method,
                    label=f"secondary:{method.value}",
                )
                records = DirectNineParser().parse(
                    item,
                    (dom, secondary),
                    (211,),
                )

                with self.assertRaises(ValidationError) as raised:
                    Validator().validate(item, records, (211,))
                self.assertEqual(
                    raised.exception.failure.code,
                    ErrorCode.DOCUMENT_CONFLICT,
                )

    def test_invalid_tail_candidate_does_not_consume_bottom_window(self) -> None:
        item = source(position=Position.BOTTOM)
        body = document(
            "\n".join(
                (
                    "测试站",
                    "207期 九肖【猪鼠牛虎兔龙蛇马羊】",
                    "208期 九肖【鼠牛虎兔龙蛇马羊猴】",
                    "209期 九肖【牛虎兔龙蛇马羊猴鸡】",
                    "210期 九肖【虎兔龙蛇马羊猴鸡狗】",
                    "211期 九肖【鼠牛虎兔龙蛇马羊】",
                )
            )
        )

        records = DirectNineParser().parse(item, (body,), (208,))
        verified = Validator().validate(item, records, (208,))

        self.assertEqual(verified.history.records[0].issue, 208)
        self.assertEqual(
            verified.history.records[0].evidence.direction_window,
            (210, 209, 208),
        )

    def test_two_matching_author_posts_are_collected_and_rejected(self) -> None:
        item = source(
            position=Position.BOTTOM,
            parser="profile_history",
            name="目标作者",
            marker="九肖中特",
        )
        body = document(
            "\n".join(
                (
                    "目标作者",
                    "2026-07-29 23:14:27",
                    "九肖中特",
                    "211期 九肖【鼠牛虎兔龙蛇马羊猴】",
                    "目标作者",
                    "2026-07-29 22:00:00",
                    "九肖中特",
                    "211期 九肖【牛虎兔龙蛇马羊猴鸡】",
                )
            )
        )

        records = ProfileHistoryParser().parse(item, (body,), (211,))

        self.assertEqual(len(records), 2)
        with self.assertRaises(ValidationError) as raised:
            Validator().validate(item, records, (211,))
        self.assertEqual(
            raised.exception.failure.code,
            ErrorCode.BLOCK_AMBIGUOUS,
        )

    def test_identical_matching_author_posts_are_deduplicated(self) -> None:
        item = source(
            position=Position.BOTTOM,
            parser="profile_history",
            name="目标作者",
            marker="九肖中特",
        )
        body = document(
            "\n".join(
                (
                    "目标作者",
                    "2026-07-29 23:14:27",
                    "九肖中特",
                    "211期 九肖【鼠牛虎兔龙蛇马羊猴】",
                    "目标作者",
                    "2026-07-29 22:00:00",
                    "九肖中特",
                    "211期 九肖【鼠牛虎兔龙蛇马羊猴】",
                )
            )
        )

        records = ProfileHistoryParser().parse(item, (body,), (211,))

        self.assertEqual(len(records.blocks), 1)
        verified = Validator().validate(item, records, (211,))
        self.assertEqual(
            verified.history.records[0].zodiac_text,
            "鼠牛虎兔龙蛇马羊猴",
        )

    def test_two_same_named_blocks_are_ambiguous(self) -> None:
        item = source(position=Position.TOP)
        body = document(
            "\n".join(
                (
                    "测试站",
                    "211期 九肖【鼠牛虎兔龙蛇马羊猴】",
                    "测试站",
                    "211期 九肖【牛虎兔龙蛇马羊猴鸡】",
                )
            )
        )

        records = DirectNineParser().parse(item, (body,), (211,))

        with self.assertRaises(ValidationError) as raised:
            Validator().validate(item, records, (211,))
        self.assertEqual(
            raised.exception.failure.code,
            ErrorCode.BLOCK_AMBIGUOUS,
        )

    def test_two_same_named_blocks_are_ambiguous_when_only_one_has_target(
        self,
    ) -> None:
        item = source(position=Position.TOP)
        body = document(
            "\n".join(
                (
                    "测试站",
                    "211期 九肖【鼠牛虎兔龙蛇马羊猴】",
                    "测试站",
                    "210期 九肖【牛虎兔龙蛇马羊猴鸡】",
                )
            )
        )

        records = DirectNineParser().parse(item, (body,), (211,))

        with self.assertRaises(ValidationError) as raised:
            Validator().validate(item, records, (211,))
        self.assertEqual(
            raised.exception.failure.code,
            ErrorCode.BLOCK_AMBIGUOUS,
        )

    def test_anchor_in_document_a_cannot_authorize_document_b(self) -> None:
        item = source(position=Position.TOP)
        anchor_only = document("测试站\n栏目说明")
        data_only = document(
            "211期 九肖【鼠牛虎兔龙蛇马羊猴】",
            DocumentMethod.SCRIPT,
        )

        records = DirectNineParser().parse(
            item,
            (anchor_only, data_only),
            (211,),
        )

        self.assertEqual(len(records), 0)
        with self.assertRaises(ValidationError) as raised:
            Validator().validate(item, records, (211,))
        self.assertEqual(
            raised.exception.failure.code,
            ErrorCode.ISSUE_MISSING,
        )

    def test_direct_nine_requires_the_target_data_marker(self) -> None:
        item = source(position=Position.TOP, data_marker="九肖")
        body = document(
            "测试站\n211期 推荐【鼠牛虎兔龙蛇马羊猴】"
        )

        records = DirectNineParser().parse(item, (body,), (211,))

        self.assertEqual(len(records), 0)
        with self.assertRaises(ValidationError) as raised:
            Validator().validate(item, records, (211,))
        self.assertEqual(
            raised.exception.failure.code,
            ErrorCode.ISSUE_MISSING,
        )

    def test_directory_name_cannot_supply_the_candidate_data_marker(
        self,
    ) -> None:
        item = source(
            position=Position.TOP,
            name="九肖生涯",
            marker="九肖生涯",
            data_marker="九肖",
        )
        body = document(
            "九肖生涯\n211期 推荐【鼠牛虎兔龙蛇马羊猴】"
        )

        records = DirectNineParser().parse(item, (body,), (211,))

        self.assertEqual(len(records), 0)
        with self.assertRaises(ValidationError) as raised:
            Validator().validate(item, records, (211,))
        self.assertEqual(
            raised.exception.failure.code,
            ErrorCode.ISSUE_MISSING,
        )

    def test_explicit_data_section_can_supply_the_block_data_marker(
        self,
    ) -> None:
        item = source(
            position=Position.TOP,
            name="目标作者",
            marker="目标作者•九肖中特",
            data_marker="九肖",
        )
        body = document(
            "目标作者•九肖中特\n211期【鼠牛虎兔龙蛇马羊猴】"
        )

        records = DirectNineParser().parse(item, (body,), (211,))
        verified = Validator().validate(item, records, (211,))

        self.assertEqual(
            verified.history.records[0].zodiac_text,
            "鼠牛虎兔龙蛇马羊猴",
        )

    def test_validator_rejects_a_fabricated_actual_anchor(self) -> None:
        from dataclasses import replace

        item = source(position=Position.TOP)
        parsed = DirectNineParser().parse(
            item,
            (
                document(
                    "测试站\n211期 九肖【鼠牛虎兔龙蛇马羊猴】"
                ),
            ),
            (211,),
        )
        record = parsed.records[0]
        forged_record = replace(
            record,
            evidence=replace(
                record.evidence,
                actual_anchor_line="无关栏目",
            ),
        )
        forged_block = replace(
            parsed.blocks[0],
            actual_anchor_line="无关栏目",
        )

        with self.assertRaises(ValidationError) as raised:
            Validator().validate(
                item,
                type(parsed)((forged_record,), (forged_block,)),
                (211,),
            )
        self.assertEqual(
            raised.exception.failure.code,
            ErrorCode.SOURCE_UNTRUSTED,
        )

    def test_direction_uses_only_three_valid_candidates_inside_one_block(
        self,
    ) -> None:
        body = document(
            "\n".join(
                (
                    "测试站",
                    "208期 九肖【鼠牛虎兔龙蛇马羊猴】",
                    "209期 九肖【牛虎兔龙蛇马羊猴鸡】",
                    "210期 九肖【虎兔龙蛇马羊猴鸡狗】",
                    "211期 九肖【兔龙蛇马羊猴鸡狗猪】",
                )
            )
        )
        top = source(position=Position.TOP)
        bottom = source(position=Position.BOTTOM)

        top_records = DirectNineParser().parse(top, (body,), (211,))
        bottom_records = DirectNineParser().parse(bottom, (body,), (208,))

        with self.assertRaises(ValidationError):
            Validator().validate(top, top_records, (211,))
        with self.assertRaises(ValidationError):
            Validator().validate(bottom, bottom_records, (208,))

        top_ok = Validator().validate(top, top_records, (210,))
        bottom_ok = Validator().validate(bottom, bottom_records, (209,))
        self.assertEqual(
            top_ok.history.records[0].evidence.direction_window,
            (208, 209, 210),
        )
        self.assertEqual(
            bottom_ok.history.records[0].evidence.direction_window,
            (211, 210, 209),
        )

    def test_same_issue_conflict_outside_direction_window_is_rejected(
        self,
    ) -> None:
        item = source(position=Position.TOP)
        body = document(
            "\n".join(
                (
                    "测试站",
                    "211期 九肖【鼠牛虎兔龙蛇马羊猴】",
                    "210期 九肖【牛虎兔龙蛇马羊猴鸡】",
                    "209期 九肖【虎兔龙蛇马羊猴鸡狗】",
                    "208期 九肖【兔龙蛇马羊猴鸡狗猪】",
                    "211期 九肖【蛇马羊猴鸡狗猪鼠牛】",
                )
            )
        )

        records = DirectNineParser().parse(item, (body,), (211,))

        with self.assertRaises(ValidationError) as raised:
            Validator().validate(item, records, (211,))
        self.assertEqual(
            raised.exception.failure.code,
            ErrorCode.CANDIDATE_CONFLICT,
        )

    def test_incomplete_primary_target_cannot_be_filled_from_script(self) -> None:
        item = source(position=Position.BOTTOM)
        dom = document("测试站\n211期 九肖【鼠牛虎】")
        script = document(
            "测试站\n211期 九肖【鼠牛虎兔龙蛇马羊猴】",
            DocumentMethod.SCRIPT,
        )

        records = DirectNineParser().parse(item, (dom, script), (211,))

        with self.assertRaises(ValidationError) as raised:
            Validator().validate(item, records, (211,))
        self.assertEqual(
            raised.exception.failure.code,
            ErrorCode.INVALID_ZODIAC_COUNT,
        )


class _StaticDocuments:
    def __init__(self, documents: tuple[Document, ...]) -> None:
        self.documents = documents

    async def fetch(self, _source, _request):
        return self.documents


class ValidationWriteBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_validation_failure_never_becomes_success_output_or_cache(
        self,
    ) -> None:
        item = source(
            position=Position.BOTTOM,
            fetcher="fake",
            source_policy=("browser_dom",),
        )
        fetchers = FetcherRegistry()
        fetchers.register(
            "fake",
            _StaticDocuments(
                (
                    document("测试站\n211期 九肖【鼠牛虎】"),
                    document(
                        "测试站\n211期 九肖【鼠牛虎兔龙蛇马羊猴】",
                        DocumentMethod.SCRIPT,
                    ),
                )
            ),
        )
        parsers = ParserRegistry()
        parsers.register("direct_nine", DirectNineParser())
        result = await CrawlService(
            fetchers,
            parsers,
            Validator(),
        ).crawl_one(item, (211,))

        self.assertFalse(result.successful)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output, failures = ReportRepository(root / "outputs").write_issue(
                211,
                (result,),
            )
            cache = CacheRepository(root / "cache.json")
            snapshot = CacheSyncService(cache).sync_single(
                (item,),
                (result,),
                211,
            )

            self.assertEqual(output.read_text(encoding="utf-8"), "")
            failure_text = failures.read_text("utf-8")
            self.assertIn("阶段: 数据数量校验 原因: 九肖数量或内容无效", failure_text)
            self.assertEqual(snapshot.sources[0].records, ())
            with self.assertRaises(CacheWriteForbiddenError):
                CacheSyncService(cache).sync_range()


if __name__ == "__main__":
    unittest.main()
