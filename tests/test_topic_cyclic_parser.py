from __future__ import annotations

import unittest

from v2.domain.errors import ErrorCode
from v2.domain.models import Document, DocumentMethod, Position, Source
from v2.parsers.custom.topic_cyclic import TopicCyclicParser
from v2.validator import ValidationError, Validator


def _source(position: Position) -> Source:
    return Source(
        name="测试站",
        url="https://example.test/topic/1.html",
        position=position,
        section_marker="测试站",
        fetcher="browser_page",
        parser="topic_cyclic_nine",
        data_marker="九肖",
    )


def _document(position: Position) -> Document:
    if position is Position.TOP:
        first = ["测试站"] + [
            f"{issue:03d}期 九肖【鼠牛虎兔龙蛇马羊猴】"
            for issue in range(212, 0, -1)
        ]
        second = [
            f"{issue:03d}期 九肖【蛇马羊猴鸡狗猪鼠牛】"
            for issue in range(365, 209, -1)
        ]
    else:
        first = ["测试站"] + [
            f"{issue:03d}期 九肖【鼠牛虎兔龙蛇马羊猴】"
            for issue in range(11, 366)
        ]
        second = [
            f"{issue:03d}期 九肖【蛇马羊猴鸡狗猪鼠牛】"
            for issue in range(1, 213)
        ]
    if position is Position.TOP:
        first[1] = "212期 九肖【鼠牛虎兔龙蛇马羊猴】"
        second[153] = "212期 九肖【蛇马羊猴鸡狗猪鼠牛】"
    else:
        second[211] = "212期 九肖【蛇马羊猴鸡狗猪鼠牛】"
    return Document(
        label="browser-dom",
        url="https://example.test/topic/1.html",
        text="\n".join((*first, *second)),
        method=DocumentMethod.BROWSER_DOM,
    )


class TopicCyclicParserTests(unittest.TestCase):
    def test_top_selects_the_upper_cycle_segment(self) -> None:
        source = _source(Position.TOP)
        records = TopicCyclicParser().parse(
            source,
            (_document(Position.TOP),),
            (212,),
        )

        verified = Validator().validate(source, records, (212,))

        self.assertEqual(
            verified.history.records[0].zodiac_text,
            "鼠牛虎兔龙蛇马羊猴",
        )
        self.assertEqual(
            verified.history.records[0].evidence.direction_window,
            (212, 211, 210),
        )

    def test_top_selects_upper_group_cycle_when_lower_cycle_repeats_issue(
        self,
    ) -> None:
        source = Source(
            name="翻天覆地",
            url="https://example.test/topic/508793.html",
            position=Position.TOP,
            section_marker="翻天覆地",
            fetcher="browser_page",
            parser="topic_cyclic_nine",
            group_map=(
                ("琴", "兔蛇鸡"),
                ("棋", "鼠牛狗"),
                ("书", "虎龙马"),
                ("画", "羊猴猪"),
            ),
            data_marker="琴棋书画",
        )
        upper = [
            f"{issue:03d}期：琴棋书画☸☸{groups}☸☸(开:0000准)"
            for issue, groups in (
                (214, "棋琴书"),
                (213, "画棋琴"),
                (212, "书画棋"),
                *(
                    (issue, "琴棋书")
                    for issue in range(211, 0, -1)
                ),
            )
        ]
        lower = [
            f"{issue:03d}期：琴棋书画☸☸琴画书☸☸(开:0000准)"
            for issue in range(365, 209, -1)
        ]
        document = Document(
            label="browser-dom",
            url=source.url,
            text="\n".join(("翻天覆地", *upper, *lower)),
            method=DocumentMethod.BROWSER_DOM,
        )

        records = TopicCyclicParser().parse(
            source,
            (document,),
            (214, 213, 212),
        )
        verified = Validator().validate(source, records, (214, 213, 212))

        self.assertEqual(
            [item.zodiac_text for item in verified.history.records],
            [
                "鼠牛狗兔蛇鸡虎龙马",
                "羊猴猪鼠牛狗兔蛇鸡",
                "虎龙马羊猴猪鼠牛狗",
            ],
        )
        self.assertEqual(
            verified.history.records[0].evidence.direction_window,
            (214, 213, 212),
        )

    def test_bottom_selects_the_lower_cycle_segment(self) -> None:
        source = _source(Position.BOTTOM)
        records = TopicCyclicParser().parse(
            source,
            (_document(Position.BOTTOM),),
            (212,),
        )

        verified = Validator().validate(source, records, (212,))

        self.assertEqual(
            verified.history.records[0].zodiac_text,
            "蛇马羊猴鸡狗猪鼠牛",
        )
        self.assertEqual(
            verified.history.records[0].evidence.direction_window,
            (212, 211, 210),
        )

    def test_short_duplicate_without_cycle_boundary_still_fails(self) -> None:
        source = _source(Position.TOP)
        document = Document(
            label="browser-dom",
            url=source.url,
            text=(
                "测试站\n"
                "212期 九肖【鼠牛虎兔龙蛇马羊猴】\n"
                "211期 九肖【牛虎兔龙蛇马羊猴鸡】\n"
                "212期 九肖【蛇马羊猴鸡狗猪鼠牛】"
            ),
            method=DocumentMethod.BROWSER_DOM,
        )

        records = TopicCyclicParser().parse(source, (document,), (212,))

        with self.assertRaises(ValidationError) as raised:
            Validator().validate(source, records, (212,))
        self.assertEqual(
            raised.exception.failure.code,
            ErrorCode.CANDIDATE_CONFLICT,
        )

    def test_script_cannot_override_the_primary_topic_document(self) -> None:
        source = _source(Position.TOP)
        script = Document(
            label="script:0",
            url=source.url,
            text=(
                "测试站\n"
                "212期 九肖【蛇马羊猴鸡狗猪鼠牛】\n"
                "211期 九肖【马羊猴鸡狗猪鼠牛虎】\n"
                "210期 九肖【羊猴鸡狗猪鼠牛虎兔】"
            ),
            method=DocumentMethod.SCRIPT,
        )

        records = TopicCyclicParser().parse(
            source,
            (_document(Position.TOP), script),
            (212,),
        )
        verified = Validator().validate(source, records, (212,))

        self.assertEqual(
            verified.history.records[0].zodiac_text,
            "鼠牛虎兔龙蛇马羊猴",
        )
