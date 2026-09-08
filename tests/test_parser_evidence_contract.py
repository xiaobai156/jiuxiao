from __future__ import annotations

import json
import unittest
from pathlib import Path

from v2.domain.errors import ErrorCode
from v2.domain.models import Document, DocumentMethod, Position, Source
from v2.parsers.custom.color_info_grouped import ColorInfoGroupedParser
from v2.parsers.custom.complement_three import ComplementThreeParser
from v2.parsers.custom.liuiuqu import LiuiuquParser
from v2.parsers.custom.named_section import NamedSectionParser
from v2.parsers.custom.single_season_complement import (
    SingleSeasonComplementParser,
)
from v2.parsers.custom.white_tiger import WhiteTigerParser
from v2.parsers.custom.yueying import YueyingParser
from v2.parsers.grouped import GroupedParser
from v2.parsers.image_ocr import ImageOcrParser
from v2.parsers.registry import ParseError
from v2.parsers.split_line import SplitLineParser
from v2.validator import ValidationError, Validator


GROUPS = (
    ("琴", "兔蛇鸡"),
    ("棋", "鼠牛狗"),
    ("书", "虎龙马"),
    ("画", "羊猴猪"),
)
SEASONS = (
    ("春", "虎兔龙"),
    ("夏", "蛇马羊"),
    ("秋", "猴鸡狗"),
    ("冬", "鼠牛猪"),
)


def source(
    parser: str,
    *,
    name: str = "测试站",
    marker: str = "测试站",
    position: Position = Position.TOP,
    group_map: tuple[tuple[str, str], ...] = (),
    data_marker: str = "",
) -> Source:
    return Source(
        name=name,
        url="https://example.test/page",
        position=position,
        section_marker=marker,
        fetcher="liuiuqu" if parser == "liuiuqu" else "browser_page",
        parser=parser,
        group_map=group_map,
        data_marker=data_marker,
    )


def document(
    text: str,
    method: DocumentMethod = DocumentMethod.BROWSER_DOM,
    *,
    metadata: tuple[tuple[str, str], ...] = (),
    label: str | None = None,
) -> Document:
    return Document(
        label=label or method.value,
        url="https://example.test/page",
        text=text,
        method=method,
        metadata=metadata,
    )


class ParserEvidenceContractTests(unittest.TestCase):
    def test_non_direct_data_types_use_explicit_configured_semantics(self) -> None:
        payload = json.loads(
            (
                Path(__file__).resolve().parents[1]
                / "config"
                / "sources.json"
            ).read_text(encoding="utf-8")
        )
        by_name = {item["name"]: item for item in payload["sources"]}

        self.assertEqual(by_name["玩家小狐"]["parser"], "complement_three")
        self.assertEqual(by_name["玩家小狐"]["data_marker"], "绝杀三肖")
        for name, group_type in (
            ("无可非议", "琴棋书画"),
            ("百兽率舞", "琴棋书画"),
            ("眩目震耳", "春夏秋冬"),
            ("青藤之凉", "春夏秋冬"),
        ):
            with self.subTest(name=name):
                self.assertEqual(by_name[name]["parser"], "grouped")
                self.assertEqual(by_name[name]["data_marker"], group_type)
                self.assertEqual(
                    "".join(by_name[name]["group_map"]),
                    group_type,
                )

    def test_ttss_sources_use_dynamic_three_page_list_details(self) -> None:
        payload = json.loads(
            (
                Path(__file__).resolve().parents[1]
                / "config"
                / "sources.json"
            ).read_text(encoding="utf-8")
        )
        by_name = {item["name"]: item for item in payload["sources"]}
        for name in ("金瓯无缺", "双世宠妃", "蛇蝎美人", "庄家无命"):
            with self.subTest(name=name):
                source = by_name[name]
                self.assertEqual(
                    source["url"],
                    "https://a.ttss.vip/listam.aspx?id=75",
                )
                self.assertEqual(source["fetcher"], "list_detail_top3")
                self.assertEqual(source["parser"], "direct_nine")
                self.assertEqual(
                    source["section_marker"],
                    f"{name}㊣㊣九肖",
                )
                self.assertEqual(
                    source["detail_link_keyword"],
                    f"{name}㊣㊣九肖",
                )
        self.assertEqual(by_name["强干弱枝"]["parser"], "profile_history")
        self.assertEqual(by_name["强干弱枝"]["data_marker"], "琴棋书画")
        self.assertEqual(
            "".join(by_name["强干弱枝"]["group_map"]),
            "琴棋书画",
        )
        for name, group_type in (
            ("一年四季", "春夏秋冬"),
            ("一方霸彩", "风雨雷电"),
            ("过訜喜歡", "春夏秋冬"),
            ("不苟言笑", "琴棋书画"),
            ("寻根问底", "琴棋书画"),
            ("荷香月色", "琴棋书画"),
            ("英雄财经", "琴棋书画"),
            ("致富联盟", "琴棋书画"),
            ("胆大包天", "琴棋书画"),
            ("皇家六合", "梅兰菊竹"),
            ("刻舟求剑", "梅兰菊竹"),
            ("半斤八两", "风雨雷电"),
            ("所向无敌", "风雨雷电"),
            ("络绎不绝", "春夏秋冬"),
        ):
            with self.subTest(name=name):
                self.assertEqual(by_name[name]["parser"], "grouped")
                self.assertEqual(by_name[name]["data_marker"], group_type)
                self.assertEqual("".join(by_name[name]["group_map"]), group_type)
        category_names = json.loads(
            (
                Path(__file__).resolve().parents[1]
                / "config"
                / "grouped_source_semantics.json"
            ).read_text(encoding="utf-8")
        )["categories"]
        for group_type, names in category_names.items():
            for name in names:
                with self.subTest(grouped_source=name):
                    self.assertIn(
                        by_name[name]["parser"],
                        (
                            "grouped",
                            "profile_history",
                            "topic_cyclic_nine",
                            "dynamic_article_grouped",
                        ),
                    )
                    self.assertEqual(by_name[name]["data_marker"], group_type)
                    self.assertEqual(
                        "".join(by_name[name]["group_map"]),
                        group_type,
                    )
        for name in (
            "玩家小狐",
            "红红火火",
            "追风六合",
            "弥足珍贵",
            "森林少女",
            "澳门顺哥",
            "灵丹妙药",
            "天机码彩",
            "地冻天寒",
        ):
            with self.subTest(complement_source=name):
                self.assertEqual(by_name[name]["parser"], "complement_three")
                self.assertEqual(by_name[name]["data_marker"], "绝杀三肖")
        for name, expected_mapping in (
            (
                "橘宝宝",
                {
                    "春": "兔虎龙",
                    "夏": "马蛇羊",
                    "秋": "鸡猴狗",
                    "冬": "鼠猪牛",
                },
            ),
            (
                "新竹精英",
                {
                    "春": "兔虎龙",
                    "夏": "马蛇羊",
                    "秋": "鸡猴狗",
                    "冬": "鼠猪牛",
                },
            ),
            (
                "新竹精英2",
                {
                    "风": "虎兔龙",
                    "雨": "蛇马羊",
                    "雷": "猴鸡狗",
                    "电": "鼠牛猪",
                },
            ),
        ):
            with self.subTest(group_mapping_source=name):
                self.assertEqual(by_name[name]["group_map"], expected_mapping)
        self.assertEqual(
            by_name["东方饭店"]["section_marker"],
            "神庙网 【浑然九肖】",
        )
        self.assertEqual(by_name["东方饭店"]["data_marker"], "九肖")
        self.assertEqual(by_name["停止学生"]["parser"], "profile_history")
        self.assertEqual(
            by_name["停止学生"]["section_marker"],
            "九肖中特",
        )
        self.assertEqual(by_name["停止学生"]["data_marker"], "九肖")
        self.assertEqual(
            by_name["青栀无梦"]["parser"],
            "dynamic_article_grouped",
        )
        self.assertEqual(
            by_name["雪中送炭"]["parser"],
            "dynamic_article_grouped",
        )
        self.assertEqual(by_name["雪中送炭"]["position"], "bottom")
        self.assertEqual(by_name["络绎不绝"]["position"], "top")
        self.assertEqual(by_name["翻天覆地"]["parser"], "topic_cyclic_nine")
        self.assertEqual(by_name["翻天覆地"]["position"], "top")
        self.assertEqual(
            by_name["清香权力"]["parser"],
            "header_direct_nine",
        )
        for name in ("焦唇干舌", "淑女是姐"):
            with self.subTest(topic_cyclic_source=name):
                self.assertEqual(
                    by_name[name]["parser"],
                    "topic_cyclic_nine",
                )

    def test_complement_three_accepts_only_equivalent_numeric_markers(
        self,
    ) -> None:
        item = source(
            "complement_three",
            marker="测试站",
            data_marker="绝杀三肖",
        )
        parser = ComplementThreeParser()
        for marker in ("绝杀三肖", "绝杀③肖", "绝杀3肖"):
            with self.subTest(marker=marker):
                parsed = parser.parse(
                    item,
                    (
                        document(
                            f"测试站\n211期 {marker}【鼠牛虎】开00准"
                        ),
                    ),
                    (211,),
                )
                verified = Validator().validate(item, parsed, (211,))
                self.assertEqual(
                    verified.history.records[0].zodiac_text,
                    "兔龙蛇马羊猴鸡狗猪",
                )

        unrelated = parser.parse(
            item,
            (document("测试站\n211期 九肖【鼠牛虎】开00准"),),
            (211,),
        )
        self.assertEqual(len(unrelated), 0)

    def assert_complete_evidence(self, item: Source, parsed) -> None:
        self.assertGreater(len(parsed.blocks), 0)
        for record in parsed:
            evidence = record.evidence
            self.assertEqual(evidence.parser_id, item.parser)
            self.assertEqual(evidence.document_url, "https://example.test/page")
            self.assertTrue(evidence.document_method)
            self.assertTrue(evidence.actual_anchor_line)
            self.assertIn(
                evidence.directory_anchor,
                evidence.actual_anchor_line,
            )
            self.assertGreaterEqual(evidence.anchor_index, 0)
            self.assertGreaterEqual(evidence.anchor_occurrence, 1)
            self.assertTrue(evidence.block_id)
            self.assertLess(evidence.block_start, evidence.block_end)
            self.assertGreaterEqual(evidence.candidate_index_in_block, 0)
            self.assertTrue(evidence.raw_issue_line)
            self.assertTrue(evidence.raw_zodiac_line)
            self.assertTrue(evidence.data_marker)

    def test_grouped_and_split_parsers_emit_complete_block_evidence(self) -> None:
        grouped_source = source(
            "grouped",
            marker="测试站•琴棋书画",
            group_map=GROUPS,
        )
        grouped = GroupedParser().parse(
            grouped_source,
            (
                document(
                    "测试站•琴棋书画\n"
                    "211期 琴棋书画【琴棋书】开00准"
                ),
            ),
            (211,),
        )
        split_source = source("split_line", data_marker="九肖")
        split = SplitLineParser().parse(
            split_source,
            (
                document(
                    "测试站\n211期 九肖中特\n"
                    "【鼠牛虎兔龙蛇马羊猴】"
                ),
            ),
            (211,),
        )

        self.assert_complete_evidence(grouped_source, grouped)
        self.assertEqual(
            dict(grouped[0].evidence.metadata)["group_mapping"],
            "琴=兔蛇鸡|棋=鼠牛狗|书=虎龙马|画=羊猴猪",
        )
        self.assert_complete_evidence(split_source, split)
        self.assertTrue(
            Validator().validate(grouped_source, grouped, (211,)).history.records
        )
        self.assertTrue(
            Validator().validate(split_source, split, (211,)).history.records
        )

    def test_split_line_symbol_marker_keeps_one_directional_history_block(
        self,
    ) -> None:
        item = source(
            "split_line",
            name="霸王码特",
            marker="霸王码特",
            position=Position.BOTTOM,
        )
        parsed = SplitLineParser().parse(
            item,
            (
                document(
                    "\n".join(
                        (
                            "霸王码特",
                            "208期: 《霸王码特》 ⑨肖中特 开:00准",
                            "【鼠牛虎兔龙蛇马羊猴】",
                            "209期: 《霸王码特》 ⑨肖中特 开:00准",
                            "【牛虎兔龙蛇马羊猴鸡】",
                            "210期: 《霸王码特》 ⑨肖中特 开:00准",
                            "【虎兔龙蛇马羊猴鸡狗】",
                            "211期: 《霸王码特》 ⑨肖中特 开:00准",
                            "【兔龙蛇马羊猴鸡狗猪】",
                        )
                    )
                ),
            ),
            (211,),
        )

        self.assertEqual(len(parsed.blocks), 1)
        verified = Validator().validate(item, parsed, (211,))
        self.assertEqual(
            verified.history.records[0].zodiac_text,
            "兔龙蛇马羊猴鸡狗猪",
        )
        self.assertEqual(
            verified.history.records[0].evidence.direction_window,
            (211, 210, 209),
        )

    def test_single_season_anchor_must_be_in_its_own_document(self) -> None:
        item = source(
            "single_season_complement",
            name="橘色日落",
            marker="橘色日落",
            group_map=SEASONS,
            data_marker="绝杀一季",
        )
        unrelated_anchor = document("橘色日落\n栏目说明")
        other_document = document(
            "211期 绝杀一季【春】开00准",
            DocumentMethod.SCRIPT,
        )

        parsed = SingleSeasonComplementParser().parse(
            item,
            (unrelated_anchor, other_document),
            (211,),
        )

        self.assertEqual(len(parsed), 0)
        with self.assertRaises(ValidationError):
            Validator().validate(item, parsed, (211,))

    def test_white_tiger_collects_every_matching_block(self) -> None:
        item = source(
            "white_tiger",
            name="风神九肖",
            marker="风神九肖",
            position=Position.BOTTOM,
        )
        parsed = WhiteTigerParser().parse(
            item,
            (
                document(
                    "\n".join(
                        (
                            "风神九肖",
                            "澳门-白虎",
                            "211期九肖【鼠牛虎兔龙蛇马羊猴】",
                            "澳门-白虎",
                            "211期九肖【牛虎兔龙蛇马羊猴鸡】",
                        )
                    )
                ),
            ),
            (211,),
        )

        self.assertEqual(len(parsed), 2)
        self.assert_complete_evidence(item, parsed)
        with self.assertRaises(ValidationError) as raised:
            Validator().validate(item, parsed, (211,))
        self.assertEqual(raised.exception.failure.code, ErrorCode.BLOCK_AMBIGUOUS)

    def test_color_info_collects_every_matching_section(self) -> None:
        marker = "港澳彩资讯网【琴棋书画】"
        item = source(
            "color_info_grouped",
            name="彩资讯网",
            marker=marker,
            position=Position.BOTTOM,
            group_map=GROUPS,
        )
        parsed = ColorInfoGroupedParser().parse(
            item,
            (
                document(
                    "\n".join(
                        (
                            marker,
                            "211期 琴棋书画【琴棋书】",
                            "港澳彩资讯网",
                            marker,
                            "211期 琴棋书画【画琴棋】",
                        )
                    )
                ),
            ),
            (211,),
        )

        self.assertEqual(len(parsed), 2)
        self.assert_complete_evidence(item, parsed)
        self.assertEqual(
            dict(parsed[0].evidence.metadata)["group_mapping"],
            "琴=兔蛇鸡|棋=鼠牛狗|书=虎龙马|画=羊猴猪",
        )
        with self.assertRaises(ValidationError) as raised:
            Validator().validate(item, parsed, (211,))
        self.assertEqual(raised.exception.failure.code, ErrorCode.BLOCK_AMBIGUOUS)

    def test_ocr_requires_proven_image_anchor_relationship(self) -> None:
        item = source(
            "image_ocr",
            name="嫦娥公式",
            marker="澳门公式",
            data_marker="九肖",
        )
        dom = document("澳门公式\n栏目说明")
        unlinked_ocr = document(
            "211期 九肖【鼠牛虎兔龙蛇马羊猴】",
            DocumentMethod.IMAGE_OCR,
        )
        with self.assertRaises(ParseError):
            ImageOcrParser().parse(item, (dom, unlinked_ocr), (211,))

        linked_ocr = document(
            "211期 鼠牛虎兔龙蛇马羊猴",
            DocumentMethod.IMAGE_OCR,
            metadata=(
                ("image_index", "3"),
                ("parent_url", "https://example.test/page"),
                ("anchor_line", "作者:澳门公式"),
                ("anchor_term", "澳门公式"),
                ("data_marker_line", "测试站 九肖"),
                ("anchor_index", "4"),
                ("block_start", "4"),
                ("block_end", "8"),
            ),
        )
        parsed = ImageOcrParser().parse(item, (dom, linked_ocr), (211,))

        self.assert_complete_evidence(item, parsed)
        self.assertTrue(
            Validator().validate(item, parsed, (211,)).history.records
        )

    def test_ocr_uses_linked_data_marker_line_as_evidence(self) -> None:
        item = Source(
            name="嫦娥公式",
            url="https://example.test/page",
            position=Position.BOTTOM,
            section_marker="澳门公式",
            fetcher="browser_page",
            parser="image_ocr",
            aliases=("嫦娥彩报╠无错九肖╣公式规律",),
            data_marker="九肖",
        )
        linked_ocr = document(
            "212期：狗鸡猴羊马蛇龙兔虎",
            DocumentMethod.IMAGE_OCR,
            metadata=(
                ("image_index", "3"),
                ("parent_url", "https://example.test/page"),
                ("anchor_line", "作者:澳门公式"),
                ("anchor_term", "澳门公式"),
                (
                    "data_marker_line",
                    "嫦娥彩报╠无错九肖╣公式规律",
                ),
                ("anchor_index", "4"),
                ("block_start", "4"),
                ("block_end", "6"),
            ),
        )

        parsed = ImageOcrParser().parse(item, (linked_ocr,), (212,))
        verified = Validator().validate(item, parsed, (212,))

        self.assertEqual(
            verified.history.records[0].zodiac_text,
            "狗鸡猴羊马蛇龙兔虎",
        )

    def test_named_section_collects_duplicate_exact_sections(self) -> None:
        marker = "八步毛哥【绝杀三肖】"
        item = source(
            "named_section",
            name="八步毛哥",
            marker=marker,
            data_marker="绝杀三肖",
        )
        parsed = NamedSectionParser().parse(
            item,
            (
                document(
                    "\n".join(
                        (
                            marker,
                            "211期 绝杀三肖【牛虎狗】",
                            "八步毛哥【其他栏目】",
                            marker,
                            "211期 绝杀三肖【鼠龙猴】",
                        )
                    )
                ),
            ),
            (211,),
        )

        self.assertEqual(len(parsed), 2)
        self.assert_complete_evidence(item, parsed)
        with self.assertRaises(ValidationError) as raised:
            Validator().validate(item, parsed, (211,))
        self.assertEqual(raised.exception.failure.code, ErrorCode.BLOCK_AMBIGUOUS)

    def test_yueying_and_liuiuqu_emit_complete_evidence(self) -> None:
        yueying_source = source(
            "yueying",
            name="月影舞华",
            marker="月影舞华",
            position=Position.BOTTOM,
            data_marker="九肖中特",
        )
        yueying = YueyingParser().parse(
            yueying_source,
            (
                document(
                    "月影舞华\n"
                    "210期九肖中特【牛虎兔龙蛇马羊猴鸡】\n"
                    "211期九肖中特【鼠牛虎兔龙蛇马羊猴】"
                ),
            ),
            (211,),
        )
        liuiuqu_source = source(
            "liuiuqu",
            name="六爱趣",
            marker="六爱趣",
            data_marker="九肖",
        )
        payload = {
            "data": {
                "lotteryType": 5,
                "recommendList": [
                    {
                        "period": 211,
                        "detailList": [
                            {
                                "name": "九肖",
                                "valueList": ["鼠牛虎", "兔龙蛇", "马羊猴"],
                            }
                        ],
                    }
                ],
            }
        }
        liuiuqu = LiuiuquParser().parse(
            liuiuqu_source,
            (
                document(
                    json.dumps(payload, ensure_ascii=False),
                    DocumentMethod.DYNAMIC_API,
                ),
            ),
            (211,),
        )

        self.assert_complete_evidence(yueying_source, yueying)
        self.assert_complete_evidence(liuiuqu_source, liuiuqu)
        self.assertTrue(
            Validator().validate(
                yueying_source,
                yueying,
                (211,),
            ).history.records
        )
        self.assertTrue(
            Validator().validate(
                liuiuqu_source,
                liuiuqu,
                (211,),
            ).history.records
        )


if __name__ == "__main__":
    unittest.main()
