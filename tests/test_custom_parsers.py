from __future__ import annotations

import unittest

from v2.domain.errors import ErrorCode
from v2.domain.models import Document, DocumentMethod, Position, Source
from v2.parsers.custom.color_info_grouped import ColorInfoGroupedParser
from v2.parsers.custom.named_section import NamedSectionParser
from v2.parsers.custom.formula_dom import FormulaDomParser
from v2.parsers.custom.profile_history import ProfileHistoryParser
from v2.parsers.custom.single_season_complement import (
    SingleSeasonComplementParser,
)
from v2.parsers.custom.white_tiger import WhiteTigerParser
from v2.parsers.custom.yueying import YueyingParser
from v2.parsers.direct_nine import DirectNineParser
from v2.parsers.registry import ParseError
from v2.validator import ValidationError, Validator


def source(
    name: str,
    parser: str,
    *,
    marker: str = "",
    position: Position = Position.TOP,
    group_map: tuple[tuple[str, str], ...] = (),
    data_marker: str = "",
) -> Source:
    return Source(
        name=name,
        url=f"https://example.test/{parser}",
        position=position,
        section_marker=marker,
        fetcher="browser_page",
        parser=parser,
        group_map=group_map,
        data_marker=data_marker,
    )


def document(text: str) -> tuple[Document, ...]:
    return (
        Document(
            label="fixture",
            url="https://example.test/page",
            text=text,
            method=DocumentMethod.BROWSER_DOM,
        ),
    )


class CustomParserTests(unittest.TestCase):
    def test_tingting_top_section_uses_top_three_and_stops_at_footer(self) -> None:
        item = Source(
            name="亭亭玉立",
            url="https://xmdrbud.eqpr2-6tpvi-pjqztv.xyz:16677/topic/760894.html",
            position=Position.TOP,
            section_marker="亭亭玉立【打拼九肖】",
            fetcher="browser_page",
            parser="direct_nine",
        )
        records = DirectNineParser().parse(
            item,
            document(
                "\n".join(
                    (
                        "217期: 亭亭玉立【打拼九肖】",
                        "217期 打拼九肖 : 【蛇狗鼠牛鸡羊龙虎猴】开00准",
                        "216期 打拼九肖 : 【龙鸡狗牛虎羊猪鼠马】开37准",
                        "215期 打拼九肖 : 【蛇狗虎龙鼠鸡猴马羊】开14准",
                        "214期 打拼九肖 : 【兔鸡羊蛇狗龙牛猪虎】开04准",
                        "2026年第048期启用新生肖表",
                        "琴：兔蛇鸡 棋：鼠牛狗 书：虎龙马 画：羊猴猪",
                    )
                )
            ),
            (216,),
        )
        verified = Validator().validate(item, records, (216,))
        self.assertEqual(
            verified.history.records[0].zodiac_text,
            "龙鸡狗牛虎羊猪鼠马",
        )
        self.assertEqual(
            verified.history.records[0].evidence.direction_window,
            (217, 216, 215),
        )
        with self.assertRaises(ValidationError) as raised:
            Validator().validate(item, records, (214,))
        self.assertEqual(raised.exception.failure.code, ErrorCode.ISSUE_MISSING)
        self.assertEqual(
            dict(raised.exception.failure.context)["direction_window"],
            "217,216,215",
        )

    def test_tingting_wrong_section_anchor_fails(self) -> None:
        item = Source(
            name="亭亭玉立",
            url="https://xmdrbud.eqpr2-6tpvi-pjqztv.xyz:16677/topic/760894.html",
            position=Position.TOP,
            section_marker="不存在栏目",
            fetcher="browser_page",
            parser="direct_nine",
        )
        with self.assertRaises(ParseError) as raised:
            DirectNineParser().parse(
                item,
                document(
                    "217期: 亭亭玉立【打拼九肖】\n"
                    "216期 打拼九肖 : 【龙鸡狗牛虎羊猪鼠马】开37准"
                ),
                (216,),
            )
        self.assertEqual(raised.exception.failure.code, ErrorCode.ANCHOR_MISSING)

    def test_formula_dom_uses_primary_dom_and_stops_before_footer_noise(self) -> None:
        item = source(
            "风神九肖",
            "formula_dom",
            marker="风神九肖",
            position=Position.BOTTOM,
        )
        dom = document(
            "\n".join(
                (
                    "216期风神九肖",
                    "作者:澳门公式",
                    "206期: 09 49 37 03 40 35+47 公式: +11 下期: 虎牛鼠猪狗鸡猴羊马√",
                    "207期: 09 40 26 23 44 13+31 公式: +11 下期: 猪狗鸡猴羊马蛇龙×",
                    "208期: 07 48 40 35 23 28+19 公式: +11 下期: 猴羊马蛇龙兔虎牛鼠×",
                    "209期: 44 05 39 14 21 22+08 公式: +11 下期: 虎牛鼠猪狗鸡猴羊马√",
                    "210期: 40 37 15 17 42 48+49 公式: +11 下期: 鼠猪狗鸡猴羊马蛇龙√",
                    "211期: 13 12 39 37 38 08+01 公式: +11 下期: 龙兔虎牛鼠猪狗鸡猴√",
                    "212期: 43 32 16 39 19 27+06 公式: +11 下期: 鸡猴羊马蛇龙兔虎牛√",
                    "213期: 09 05 12 22 01 15+35 公式: +11 下期: 鸡猴羊马蛇龙兔虎牛√",
                    "214期: 29 30 27 38 43 31+04 公式: +11 下期: 蛇龙兔虎牛鼠猪狗鸡√",
                    "215期: 19 38 30 13 01 11+14 公式: +11 下期: 牛鼠猪狗鸡猴羊马蛇√",
                    "216期：牛鼠猪狗鸡猴羊马蛇",
                    "上一篇：",
                    "澳门-白虎",
                    "216期㉿九肖㉿【猪虎羊兔猴马狗牛蛇】免费公开",
                )
            )
        )
        ocr = Document(
            label="image-ocr:3",
            url="https://example.test/page",
            text="216期㉿九肖㉿【猪虎羊兔猴马狗牛蛇】",
            method=DocumentMethod.IMAGE_OCR,
        )

        parsed = FormulaDomParser().parse(item, (*dom, ocr), (216,))
        verified = Validator().validate(item, parsed, (216,))

        self.assertEqual(
            verified.history.records[0].zodiac_text,
            "牛鼠猪狗鸡猴羊马蛇",
        )
        self.assertTrue(
            all(
                record.evidence.document_method == DocumentMethod.BROWSER_DOM.value
                for record in parsed.records
            )
        )
        self.assertEqual(
            dict(verified.history.records[0].evidence.metadata)[
                "data_marker_line"
            ],
            "216期风神九肖",
        )

        with self.assertRaises(ValidationError) as raised:
            Validator().validate(item, parsed, (217,))
        self.assertEqual(raised.exception.failure.code, ErrorCode.ISSUE_MISSING)
        self.assertEqual(
            dict(raised.exception.failure.context)["direction_window"],
            "216,215,214",
        )

    def test_formula_dom_requires_primary_browser_dom(self) -> None:
        item = source(
            "嫦娥公式",
            "formula_dom",
            marker="嫦娥彩报╠无错九肖╣公式规律",
        )
        ocr = Document(
            label="image-ocr:3",
            url="https://example.test/page",
            text="216期虎牛鼠猪狗鸡猴羊马",
            method=DocumentMethod.IMAGE_OCR,
        )

        with self.assertRaises(ParseError) as raised:
            FormulaDomParser().parse(item, (ocr,), (216,))
        self.assertEqual(
            raised.exception.failure.code,
            ErrorCode.SOURCE_UNTRUSTED,
        )

    def test_formula_dom_exact_nine_marker_rejects_shorter_lists(self) -> None:
        item = source(
            "风神九肖",
            "formula_dom",
            marker="风神九肖",
            position=Position.BOTTOM,
            data_marker="㉿九肖㉿",
        )
        dom = document(
            "\n".join(
                (
                    "217期风神九肖",
                    "作者:澳门公式",
                    "217期㉿一肖㉿【狗】免费公开",
                    "217期㉿三肖㉿【狗猴龙】免费公开",
                    "217期㉿五肖㉿【狗猴龙鸡羊】免费公开",
                    "217期㉿七肖㉿【狗猴龙鸡羊兔牛】免费公开",
                    "217期㉿九肖㉿【狗猴龙鸡羊兔牛鼠虎】免费公开",
                    "上一篇：",
                )
            )
        )

        parsed = FormulaDomParser().parse(item, dom, (217,))
        verified = Validator().validate(item, parsed, (217,))

        self.assertEqual(len(parsed.records), 1)
        self.assertEqual(
            verified.history.records[0].zodiac_text,
            "狗猴龙鸡羊兔牛鼠虎",
        )
        self.assertEqual(
            verified.history.records[0].evidence.direction_window,
            (217,),
        )

    def test_named_section_uses_exact_marker_and_stops_at_next_section(
        self,
    ) -> None:
        item = Source(
            name="八步毛哥",
            url="https://example.test/#62111",
            position=Position.TOP,
            section_marker="八步毛哥【绝杀三肖】",
            fetcher="browser_page",
            parser="named_section",
        )
        records = NamedSectionParser().parse(
            item,
            document(
                """八步毛哥【春夏秋冬】
209期:春夏秋冬〖夏冬秋〗开：猪08准
八步毛哥【绝杀三肖】
请记住官网
210期绝杀三肖【牛虎狗】开马49中
八步毛哥【砍杀段数】
209期九肖【鼠牛虎兔龙蛇马羊猴】"""
            ),
            (210, 209),
        )

        verified = Validator().validate(item, records, (210,))
        self.assertEqual(len(records), 1)
        self.assertEqual(
            verified.history.records[0].zodiac_text,
            "鼠兔龙蛇马羊猴鸡猪",
        )
        with self.assertRaises(ValidationError) as raised:
            Validator().validate(item, records, (209,))
        self.assertEqual(
            raised.exception.failure.code,
            ErrorCode.ISSUE_MISSING,
        )

    def test_named_section_rejects_missing_exact_marker(self) -> None:
        item = Source(
            name="八步毛哥",
            url="https://example.test/#62111",
            position=Position.TOP,
            section_marker="八步毛哥【绝杀三肖】",
            fetcher="browser_page",
            parser="named_section",
        )

        with self.assertRaises(ParseError) as raised:
            NamedSectionParser().parse(
                item,
                document(
                    "八步毛哥【春夏秋冬】\n"
                    "210期九肖【鼠牛虎兔龙蛇马羊猴】"
                ),
                (210,),
            )

        self.assertEqual(
            raised.exception.failure.code,
            ErrorCode.ANCHOR_MISSING,
        )

    def test_profile_history_selects_exact_aliased_author_post(self) -> None:
        item = Source(
            name="丰利骨头",
            url="https://example.test/#/users/21928",
            position=Position.BOTTOM,
            section_marker="九肖中特",
            fetcher="browser_page",
            parser="profile_history",
            aliases=("丰丽骨头",),
        )
        records = ProfileHistoryParser().parse(
            item,
            document(
                """用户主页
丰丽骨头
2026-07-29 23:14:27
九肖中特
208期:九肖【鼠牛虎兔龙蛇马羊猴】
209期:九肖【牛虎兔龙蛇马羊猴鸡】
210期:九肖【虎兔龙蛇马羊猴鸡狗】
其他用户
2026-07-29 22:00:00
九肖中特
208期:九肖【兔龙蛇马羊猴鸡狗猪】
209期:九肖【龙蛇马羊猴鸡狗猪鼠】
210期:九肖【蛇马羊猴鸡狗猪鼠牛】"""
            ),
            (210, 209, 208),
        )

        verified = Validator().validate(item, records, (210, 209, 208))
        self.assertEqual(len(records), 3)
        self.assertEqual(
            [record.zodiac_text for record in verified.history.records],
            [
                "虎兔龙蛇马羊猴鸡狗",
                "牛虎兔龙蛇马羊猴鸡",
                "鼠牛虎兔龙蛇马羊猴",
            ],
        )

    def test_profile_history_requires_author_and_marker_in_same_post(
        self,
    ) -> None:
        item = Source(
            name="目标作者",
            url="https://example.test/#/users/7",
            position=Position.TOP,
            section_marker="目标栏目",
            fetcher="browser_page",
            parser="profile_history",
        )
        fixtures = (
            """其他作者
2026-07-29 23:14:27
目标栏目
210期:九肖【鼠牛虎兔龙蛇马羊猴】""",
            """目标作者
2026-07-29 23:14:27
其他栏目
210期:九肖【鼠牛虎兔龙蛇马羊猴】
其他作者
2026-07-29 22:00:00
目标栏目
210期:九肖【鼠牛虎兔龙蛇马羊猴】""",
        )

        for text in fixtures:
            with self.subTest(text=text):
                with self.assertRaises(ParseError) as raised:
                    ProfileHistoryParser().parse(
                        item,
                        document(text),
                        (210,),
                    )
                self.assertEqual(
                    raised.exception.failure.code,
                    ErrorCode.ANCHOR_MISSING,
                )

    def test_white_tiger_stops_before_hidden_history_control(self) -> None:
        item = source("风神九肖", "white_tiger")
        records = WhiteTigerParser().parse(
            item,
            document(
                """风神九肖
澳门-白虎
210期㉿三肖㉿【鼠牛虎】免费公开
210期㉿五肖㉿【鼠牛虎兔龙】免费公开
210期㉿七肖㉿【鼠牛虎兔龙蛇马】免费公开
210期㉿九肖㉿【鼠牛虎兔龙蛇马羊猴】免费公开
209期九肖【牛虎兔龙蛇马羊猴鸡】
点击 加载全部记录
208期九肖【虎兔龙蛇马羊猴鸡狗】"""
            ),
            (210,),
        )

        verified = Validator().validate(item, records, (210,))
        self.assertEqual(verified.history.records[0].zodiac_text, "鼠牛虎兔龙蛇马羊猴")
        self.assertEqual(len(records), 2)
        self.assertNotIn(208, {record.issue for record in records})

    def test_yueying_keeps_oldest_first_history_for_bottom_direction(self) -> None:
        item = source(
            "月影舞华",
            "yueying",
            position=Position.BOTTOM,
        )
        records = YueyingParser().parse(
            item,
            document(
                """月影舞华
208期九肖中特【虎兔龙蛇马羊猴鸡狗】
209期九肖中特【牛虎兔龙蛇马羊猴鸡】
210期九肖中特《鼠牛虎兔龙蛇马羊猴》"""
            ),
            (210,),
        )

        verified = Validator().validate(item, records, (210,))
        self.assertEqual([record.issue for record in records], [208, 209, 210])
        self.assertEqual(verified.history.current_issue, 210)

    def test_color_info_limits_grouped_records_to_named_section(self) -> None:
        groups = (
            ("琴", "兔蛇鸡"),
            ("棋", "鼠牛狗"),
            ("书", "虎龙马"),
            ("画", "羊猴猪"),
        )
        item = source(
            "彩资讯网",
            "color_info_grouped",
            marker="港澳彩资讯网【琴棋书画】",
            group_map=groups,
        )
        records = ColorInfoGroupedParser().parse(
            item,
            document(
                """港澳彩资讯网【琴棋书画】
210期: 画 琴 棋
港澳彩资讯网
210期：四艺【画书琴】→开"""
            ),
            (210,),
        )

        verified = Validator().validate(item, records, (210,))
        record = verified.history.records[0]
        self.assertEqual(record.zodiac_text, "羊猴猪兔蛇鸡鼠牛狗")
        self.assertEqual(dict(record.evidence.metadata)["group_text"], "画琴棋")
        self.assertEqual(len(records), 1)

    def test_single_season_parser_returns_canonical_nine_complement(self) -> None:
        seasons = (
            ("春", "虎兔龙"),
            ("夏", "蛇马羊"),
            ("秋", "猴鸡狗"),
            ("冬", "鼠牛猪"),
        )
        item = source(
            "橘色日落",
            "single_season_complement",
            marker="绝杀一季",
            group_map=seasons,
        )
        records = SingleSeasonComplementParser().parse(
            item,
            document("橘色日落\n210期 绝杀一季【春】开？"),
            (210,),
        )

        verified = Validator().validate(item, records, (210,))
        record = verified.history.records[0]
        self.assertEqual(record.zodiac_text, "鼠牛蛇马羊猴鸡狗猪")
        self.assertEqual(dict(record.evidence.metadata)["killed_season"], "春")

    def test_single_season_history_uses_one_article_section_block(self) -> None:
        seasons = (
            ("春", "虎兔龙"),
            ("夏", "蛇马羊"),
            ("秋", "猴鸡狗"),
            ("冬", "鼠牛猪"),
        )
        item = source(
            "橘色日落",
            "single_season_complement",
            marker="绝杀一季",
            position=Position.BOTTOM,
            group_map=seasons,
        )
        records = SingleSeasonComplementParser().parse(
            item,
            document(
                "\n".join(
                    (
                        "214期【绝杀一季】",
                        "橘色日落",
                        "212期：绝杀一季【秋】开牛06对",
                        "213期：绝杀一季【春】开猴35对",
                        "214期：绝杀一季【秋】开？00对",
                        "春天生肖:兔、虎、龙",
                        "上一篇：",
                        "213期【绝杀二肖】",
                    )
                )
            ),
            (213,),
        )

        self.assertEqual(len(records.blocks), 1)
        verified = Validator().validate(item, records, (213,))
        self.assertEqual(
            verified.history.records[0].evidence.direction_window,
            (214, 213, 212),
        )


if __name__ == "__main__":
    unittest.main()
