from __future__ import annotations

import unittest

from v2.domain.errors import ErrorCode
from v2.domain.models import (
    Document,
    DocumentMethod,
    Evidence,
    Position,
    Record,
    Source,
)
from v2.parsers.custom.complement_three import ComplementThreeParser
from v2.parsers.direct_nine import DirectNineParser
from v2.parsers.grouped import GroupedParser
from v2.parsers.image_ocr import ImageOcrParser
from v2.parsers.registry import ParseError, ParserRegistry
from v2.parsers.split_line import SplitLineParser
from v2.validator import ValidationError, Validator


def make_source(
    *,
    name: str = "测试站",
    position: Position = Position.BOTTOM,
    parser: str = "direct_nine",
    marker: str = "测试站",
    group_map: tuple[tuple[str, str], ...] = (),
    aliases: tuple[str, ...] = (),
) -> Source:
    return Source(
        name=name,
        url="https://example.test/page",
        position=position,
        section_marker=marker,
        fetcher="static_page",
        parser=parser,
        group_map=group_map,
        aliases=aliases,
    )


def document(text: str, method: DocumentMethod = DocumentMethod.STATIC_PAGE) -> Document:
    return Document(
        label=method.value,
        url="https://example.test/page",
        text=text,
        method=method,
    )


def record(
    issue: int,
    zodiac: str,
    *,
    line_index: int,
    anchor: str = "测试站",
) -> Record:
    return Record(
        issue=issue,
        zodiacs=tuple(zodiac),
        evidence=Evidence(
            method="direct",
            source_line=f"{issue}期:【{zodiac}】",
            directory_anchor=anchor,
            document_label="body",
            metadata=(
                ("document_index", "0"),
                ("line_index", str(line_index)),
            ),
        ),
    )


class ParserRegistryTests(unittest.TestCase):
    def test_registry_rejects_duplicate_and_unknown_parser_keys(self) -> None:
        registry = ParserRegistry()
        parser = DirectNineParser()
        registry.register("direct_nine", parser)

        self.assertIs(registry.resolve("direct_nine"), parser)
        with self.assertRaises(ValueError):
            registry.register("direct_nine", parser)
        with self.assertRaises(KeyError):
            registry.resolve("missing")


class DirectNineParserTests(unittest.TestCase):
    def test_direct_parser_accepts_parenthesized_nine_symbol_marker(
        self,
    ) -> None:
        source = make_source(name="稳场浪客", marker="稳场浪客")
        parsed = DirectNineParser().parse(
            source,
            (
                document(
                    "稳场浪客\n"
                    "211期⒐肖：（猪龙狗蛇牛兔虎鸡鼠）开:00准"
                ),
            ),
            (211,),
        )

        verified = Validator().validate(source, parsed, (211,))
        self.assertEqual(
            verified.history.records[0].zodiac_text,
            "猪龙狗蛇牛兔虎鸡鼠",
        )

    def test_nine_zodiac_title_is_not_an_incomplete_result_candidate(
        self,
    ) -> None:
        source = make_source(name="天高地下", marker="天高地下")
        parsed = DirectNineParser().parse(
            source,
            (
                document(
                    "211期:【龙珠九肖】天高地下 大公開\n"
                    "作者:天高地下\n"
                    "211期: 龙珠九肖《龙鼠鸡羊牛狗虎马蛇》开:0000准"
                ),
            ),
            (211,),
        )

        self.assertEqual(len(parsed.records), 1)
        verified = Validator().validate(source, parsed, (211,))
        self.assertEqual(
            verified.history.records[0].zodiac_text,
            "龙鼠鸡羊牛狗虎马蛇",
        )

    def test_document_anchor_binds_contiguous_history_without_repeated_name(
        self,
    ) -> None:
        source = make_source(
            name="玩家小狐",
            marker="玩家小虎•绝杀三肖",
            parser="complement_three",
        )
        text = "\n".join(
            [
                "玩家小虎•绝杀三肖",
                "210期:绝杀三肖【羊马蛇】开:0000准",
                "209期:绝杀三肖【狗鸡猴】开:猪08准",
                "广告栏目",
                "208期:绝杀三肖【鼠牛虎】开:00准",
            ]
        )

        records = ComplementThreeParser().parse(
            source,
            (document(text),),
            (210, 209),
        )

        self.assertEqual([item.issue for item in records], [210, 209])
        self.assertEqual(records[0].zodiac_text, "鼠牛虎兔龙猴鸡狗猪")
        self.assertEqual(records[1].zodiac_text, "鼠牛虎兔龙蛇马羊猪")
        self.assertEqual(
            records[0].evidence.directory_anchor,
            "玩家小虎•绝杀三肖",
        )

    def test_direct_parser_converts_grouped_line_with_complete_evidence(
        self,
    ) -> None:
        source = make_source(
            name="无可非议",
            marker="",
            parser="grouped",
            group_map=tuple(
                ("琴棋书画"[index], value)
                for index, value in enumerate(
                    ("兔蛇鸡", "鼠牛狗", "虎龙马", "羊猴猪")
                )
            ),
        )
        text = "\n".join(
            [
                "无可非议",
                "210期: 『无可非议』 琴棋书画【画.琴.书】开: 马49 准",
            ]
        )

        records = GroupedParser().parse(source, (document(text),), (210,))

        self.assertEqual(records[0].zodiac_text, "羊猴猪兔蛇鸡虎龙马")
        metadata = dict(records[0].evidence.metadata)
        self.assertEqual(metadata["group_type"], "琴棋书画")
        self.assertEqual(metadata["group_text"], "画琴书")

    def test_complete_group_line_does_not_absorb_following_mapping_note(
        self,
    ) -> None:
        source = make_source(
            name="无可非议",
            marker="",
            parser="grouped",
            group_map=(
                ("琴", "兔蛇鸡"),
                ("棋", "鼠牛狗"),
                ("书", "虎龙马"),
                ("画", "羊猴猪"),
            ),
        )
        group_line = "210期: 无可非议 琴棋书画【画.琴.书】开:00准"
        text = f"无可非议\n{group_line}\n琴:兔蛇鸡 棋:鼠牛狗"

        records = GroupedParser().parse(source, (document(text),), (210,))

        self.assertEqual(records[0].evidence.source_line, group_line)

    def test_group_semantic_marker_accepts_a_reordered_four_group_legend(
        self,
    ) -> None:
        source = make_source(
            name="百兽率舞",
            marker="百兽率舞",
            parser="grouped",
            group_map=(
                ("琴", "兔蛇鸡"),
                ("棋", "鼠牛狗"),
                ("书", "虎龙马"),
                ("画", "羊猴猪"),
            ),
        )
        parsed = GroupedParser().parse(
            source,
            (
                document(
                    "百兽率舞\n"
                    "211期：(书画棋琴)棋书琴开：000准"
                ),
            ),
            (211,),
        )

        verified = Validator().validate(source, parsed, (211,))
        self.assertEqual(
            verified.history.records[0].zodiac_text,
            "鼠牛狗虎龙马兔蛇鸡",
        )

    def test_malformed_old_issue_line_does_not_truncate_newer_history(
        self,
    ) -> None:
        source = make_source(
            name="一方霸彩",
            marker="一方霸彩",
            position=Position.BOTTOM,
            parser="grouped",
            group_map=(
                ("风", "虎兔龙"),
                ("雨", "蛇羊马"),
                ("雷", "猴狗鸡"),
                ("电", "鼠牛猪"),
            ),
        )
        parsed = GroupedParser().parse(
            source,
            (
                document(
                    "一方霸彩\n"
                    "138期 风雨雷电【电雷雨】开:00准\n"
                    "1 39期 风雨雷电【电风雷】开:00准\n"
                    "209期 风雨雷电【风雷雨】开:00准\n"
                    "210期 风雨雷电【电雷雨】开:00准\n"
                    "211期 风雨雷电【风雷雨】开:00准"
                ),
            ),
            (211,),
        )

        verified = Validator().validate(source, parsed, (211,))
        self.assertEqual(
            verified.history.records[0].zodiac_text,
            "虎兔龙猴狗鸡蛇羊马",
        )
        self.assertEqual(
            verified.history.records[0].evidence.direction_window,
            (211, 210, 209),
        )

    def test_site_record_notice_does_not_truncate_bottom_history(
        self,
    ) -> None:
        source = make_source(
            name="一语破特",
            marker="一语破特",
            position=Position.BOTTOM,
            parser="grouped",
            group_map=(
                ("风", "虎兔龙"),
                ("雨", "蛇羊马"),
                ("雷", "猴狗鸡"),
                ("电", "鼠牛猪"),
            ),
        )
        parsed = GroupedParser().parse(
            source,
            (
                document(
                    "一语破特\n"
                    "208期 风雨雷电【电雷雨】开:00准\n"
                    "73261.com欢迎您，所有记录真实永不作假！\n"
                    "209期 风雨雷电【风雷雨】开:00准\n"
                    "210期 风雨雷电【电雷雨】开:00准\n"
                    "211期 风雨雷电【风雷雨】开:00准"
                ),
            ),
            (211,),
        )

        verified = Validator().validate(source, parsed, (211,))
        self.assertEqual(
            verified.history.records[0].evidence.direction_window,
            (211, 210, 209),
        )

    def test_direct_parser_reads_group_text_after_legend_brackets(self) -> None:
        source = make_source(
            name="百兽率舞",
            marker="",
            parser="grouped",
            group_map=(
                ("琴", "兔蛇鸡"),
                ("棋", "鼠牛狗"),
                ("书", "虎龙马"),
                ("画", "羊猴猪"),
            ),
        )
        text = "\n".join(
            [
                "作者:百兽率舞",
                "210期：(书画棋琴)琴书画开：000准",
            ]
        )

        records = GroupedParser().parse(source, (document(text),), (210,))

        self.assertEqual(records[0].zodiac_text, "兔蛇鸡虎龙马羊猴猪")
        self.assertEqual(
            dict(records[0].evidence.metadata)["group_text"],
            "琴书画",
        )

    def test_direct_parser_binds_continuation_and_skips_known_notice(self) -> None:
        source = make_source(name="日升月恒", marker="")
        text = "\n".join(
            [
                "作者：日升月恒",
                "208期: 日升月恒 九肖中特开:鼠19准",
                "【狗.猴.马.牛.蛇.鼠.兔.羊.猪】",
                "本资料最早发表在示例站欢迎转发+关注",
                "209期: 日升月恒 九肖中特开:猪08准",
                "【狗.猴.虎.龙.马.蛇.鼠.羊.猪】",
                "210期: 日升月恒 九肖中特开:马49准",
                "【狗.猴.龙.马.牛.蛇.鼠.羊.猪】",
            ]
        )

        records = DirectNineParser().parse(source, (document(text),), (210,))

        self.assertEqual([item.issue for item in records], [208, 209, 210])
        self.assertEqual(records[-1].zodiac_text, "狗猴龙马牛蛇鼠羊猪")
        self.assertIn("【狗.猴.龙.马.牛.蛇.鼠.羊.猪】", records[-1].evidence.source_line)

    def test_direct_parser_supports_equal_wrapped_group_text(self) -> None:
        source = make_source(
            name="强干弱枝",
            marker="",
            parser="grouped",
            group_map=(
                ("琴", "兔蛇鸡"),
                ("棋", "鼠牛狗"),
                ("书", "虎龙马"),
                ("画", "羊猴猪"),
            ),
        )
        text = "强干弱枝\n210期：琴棋书画===琴棋书===(开：马49准)"

        records = GroupedParser().parse(source, (document(text),), (210,))

        self.assertEqual(records[0].zodiac_text, "兔蛇鸡鼠牛狗虎龙马")
        self.assertEqual(
            dict(records[0].evidence.metadata)["group_text"],
            "琴棋书",
        )

    def test_anchor_section_stops_before_unrelated_history(self) -> None:
        source = make_source(marker="目标栏目")
        text = "\n".join(
            [
                "目标栏目",
                "210期九肖【鼠牛虎兔龙蛇马羊猴】",
                "其他栏目",
                "210期九肖【牛虎兔龙蛇马羊猴鸡】",
            ]
        )

        records = DirectNineParser().parse(source, (document(text),), (210,))

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].zodiac_text, "鼠牛虎兔龙蛇马羊猴")

    def test_bracketed_next_section_heading_is_not_a_continuation(self) -> None:
        source = make_source(name="青藤之凉", marker="青藤之凉")
        source = make_source(
            name="青藤之凉",
            marker="青藤之凉",
            parser="grouped",
            group_map=(
                ("春", "虎兔龙"),
                ("夏", "蛇马羊"),
                ("秋", "猴鸡狗"),
                ("冬", "鼠牛猪"),
            ),
        )
        text = "\n".join(
            [
                "青藤之凉（春夏秋冬）",
                "210期:三季【春秋夏】开:00准",
                "209期:三季【秋冬夏】开:猪08准",
                "其他栏目（琴棋书画）",
                "210期【棋书琴】开00准",
            ]
        )

        records = GroupedParser().parse(source, (document(text),), (210,))

        self.assertEqual([item.issue for item in records], [210, 209])
        self.assertEqual(records[0].zodiac_text, "虎兔龙猴鸡狗蛇马羊")

    def test_direct_parser_accepts_book_title_brackets_from_real_pages(self) -> None:
        source = make_source()
        documents = (
            document("测试站 210期九肖中特《鼠牛虎兔龙蛇马羊猴》"),
        )

        records = DirectNineParser().parse(source, documents, (210,))

        self.assertEqual(records[0].zodiac_text, "鼠牛虎兔龙蛇马羊猴")

    def test_direct_parser_keeps_all_anchored_candidates_and_original_order(
        self,
    ) -> None:
        source = make_source()
        text = "\n".join(
            [
                "测试站",
                "208期:《测试站》九肖【狗猴鸡牛蛇鼠兔羊猪】",
                "209期:《测试站》九肖【狗猴虎龙马蛇兔羊猪】",
                "210期:《测试站》九肖【狗猴虎鸡龙牛蛇羊猪】",
            ]
        )

        records = DirectNineParser().parse(source, (document(text),), (210,))

        self.assertEqual([item.issue for item in records], [208, 209, 210])
        self.assertEqual(records[-1].zodiac_text, "狗猴虎鸡龙牛蛇羊猪")
        self.assertEqual(records[-1].evidence.directory_anchor, "测试站")

    def test_missing_anchor_and_locked_issue_fail_with_structured_codes(
        self,
    ) -> None:
        source = make_source()
        with self.assertRaises(ParseError) as raised:
            DirectNineParser().parse(
                source,
                (document("其他栏目\n210期:【鼠牛虎兔龙蛇马羊猴】"),),
                (210,),
            )
        self.assertEqual(raised.exception.failure.code, ErrorCode.ANCHOR_MISSING)

        with self.assertRaises(ParseError) as raised:
            DirectNineParser().parse(
                source,
                (document("测试站\n210期:《测试站》购买后可查看"),),
                (210,),
            )
        self.assertEqual(raised.exception.failure.code, ErrorCode.LOCKED_CONTENT)

    def test_html_document_is_normalized_without_reordering_zodiac(self) -> None:
        source = make_source()
        html = (
            "<h1>测试站</h1><p>210期:《测试站》九肖"
            "【鼠.牛.虎.兔.龙.蛇.马.羊.猴】</p>"
        )

        records = DirectNineParser().parse(source, (document(html),), (210,))

        self.assertEqual(records[0].zodiac_text, "鼠牛虎兔龙蛇马羊猴")

    def test_parser_carries_document_provenance_into_record_evidence(self) -> None:
        source = make_source()
        api_document = Document(
            label="api:$",
            url="https://example.test/api/proxy/manager-articles/abc",
            text="测试站\n210期:《测试站》九肖【鼠牛虎兔龙蛇马羊猴】",
            method=DocumentMethod.DYNAMIC_API,
            metadata=(
                ("article_id", "abc"),
                ("record_path", "$"),
                ("api_url", "https://example.test/api/proxy/manager-articles/abc"),
            ),
        )

        records = DirectNineParser().parse(source, (api_document,), (210,))

        metadata = dict(records[0].evidence.metadata)
        self.assertEqual(metadata["article_id"], "abc")
        self.assertEqual(metadata["record_path"], "$")
        self.assertEqual(metadata["api_url"], api_document.url)


class GroupedParserTests(unittest.TestCase):
    def test_grouped_parser_binds_heading_to_unanchored_history_lines(self) -> None:
        source = make_source(
            name="湘妹围特",
            marker="湘妹围特•琴棋书画",
            parser="grouped",
            group_map=(
                ("琴", "兔蛇鸡"),
                ("棋", "鼠牛狗"),
                ("书", "虎龙马"),
                ("画", "羊猴猪"),
            ),
        )
        text = "\n".join(
            [
                "湘妹围特•琴棋书画",
                "210期：四艺【棋书琴】→开？00中",
                "209期：四艺【画琴棋】→开猪08中",
            ]
        )

        records = GroupedParser().parse(source, (document(text),), (210, 209))

        self.assertEqual(
            [item.zodiac_text for item in records],
            ["鼠牛狗虎龙马兔蛇鸡", "羊猴猪兔蛇鸡鼠牛狗"],
        )

    def test_grouped_parser_supports_angle_wrapped_group_text(self) -> None:
        source = make_source(
            name="眩目震耳",
            marker="眩目震耳",
            parser="grouped",
            group_map=(
                ("春", "虎兔龙"),
                ("夏", "蛇马羊"),
                ("秋", "猴鸡狗"),
                ("冬", "鼠牛猪"),
            ),
        )
        text = "眩目震耳\n210期:春夏秋冬<<夏秋冬>>开0000准"

        records = GroupedParser().parse(source, (document(text),), (210,))

        self.assertEqual(records[0].zodiac_text, "蛇马羊猴鸡狗鼠牛猪")
        self.assertEqual(
            dict(records[0].evidence.metadata)["group_text"],
            "夏秋冬",
        )

    def test_grouped_parser_supports_double_diamond_group_text(self) -> None:
        source = make_source(
            name="翻天覆地",
            marker="翻天覆地",
            parser="grouped",
            position=Position.TOP,
            group_map=(
                ("琴", "兔蛇鸡"),
                ("棋", "鼠牛狗"),
                ("书", "虎龙马"),
                ("画", "羊猴猪"),
            ),
        )
        text = "\n".join(
            (
                "214期：翻天覆地【琴棋书画】",
                "提高速度,减少浏览流量,不保留大量往期记录!",
                "琴：兔蛇鸡 棋：鼠牛狗",
                "书：虎龙马 画：羊猴猪",
                "214期：琴棋书画☸☸棋琴书☸☸(开:0000准)",
                "213期：琴棋书画☸☸画棋琴☸☸(开:猴35准)",
                "212期：琴棋书画☸☸书画棋☸☸(开:牛06准)",
            )
        )

        records = GroupedParser().parse(
            source,
            (document(text),),
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

    def test_issue_bearing_directory_link_is_not_a_history_boundary(self) -> None:
        source = make_source(
            name="新竹精英",
            marker="精英榜",
            parser="grouped",
            group_map=(
                ("春", "虎兔龙"),
                ("夏", "马蛇羊"),
                ("秋", "鸡猴狗"),
                ("冬", "鼠猪牛"),
            ),
        )
        text = "\n".join(
            [
                "精英榜210期:【春夏秋冬】已公开",
                "最新资料",
                "210期：春夏秋冬『夏春秋』开0000准",
                "209期：春夏秋冬『冬夏春』开猪08准",
            ]
        )

        records = GroupedParser().parse(source, (document(text),), (210,))

        self.assertEqual(records[0].zodiac_text, "马蛇羊虎兔龙鸡猴狗")

    def test_grouped_parser_converts_source_map_and_keeps_group_evidence(
        self,
    ) -> None:
        source = make_source(
            parser="grouped",
            group_map=(
                ("琴", "兔蛇鸡"),
                ("棋", "鼠牛狗"),
                ("书", "虎龙马"),
                ("画", "羊猴猪"),
            ),
        )
        text = "测试站\n210期:《测试站》琴棋书画【棋书琴】"

        records = GroupedParser().parse(source, (document(text),), (210,))

        self.assertEqual(records[0].zodiac_text, "鼠牛狗虎龙马兔蛇鸡")
        metadata = dict(records[0].evidence.metadata)
        self.assertEqual(metadata["group_text"], "棋书琴")
        self.assertEqual(metadata["group_type"], "琴棋书画")

    def test_grouped_parser_rejects_missing_source_group_evidence(self) -> None:
        source = make_source(parser="grouped")

        with self.assertRaises(ParseError) as raised:
            GroupedParser().parse(
                source,
                (document("测试站\n210期:《测试站》【棋书琴】"),),
                (210,),
            )

        self.assertEqual(
            raised.exception.failure.code,
            ErrorCode.GROUP_EVIDENCE_MISSING,
        )


class SplitAndOcrParserTests(unittest.TestCase):
    def test_ocr_parser_binds_dom_anchor_to_unbracketed_ocr_history(self) -> None:
        source = make_source(
            name="嫦娥公式",
            marker="澳门公式",
            parser="image_ocr",
            aliases=("嫦娥彩报╠无错九肖╣公式规律",),
        )
        dom = document("211期：嫦娥彩报╠无错九肖╣公式规律")
        ocr = Document(
            label="image-ocr:0",
            url="https://example.test/page",
            text=(
                "209期：羊马蛇龙兔虎牛鼠猪\n"
                "210期：羊马蛇龙兔虎牛鼠猪"
            ),
            method=DocumentMethod.IMAGE_OCR,
            metadata=(
                ("image_index", "0"),
                ("parent_url", "https://example.test/page"),
                ("anchor_line", "澳门公式 九肖"),
                ("anchor_term", "澳门公式"),
                ("data_marker_line", "嫦娥彩报 无错九肖"),
                ("anchor_index", "0"),
                ("block_start", "0"),
                ("block_end", "3"),
            ),
        )

        records = ImageOcrParser().parse(source, (dom, ocr), (210,))

        self.assertEqual(records[-1].issue, 210)
        self.assertEqual(records[-1].zodiac_text, "羊马蛇龙兔虎牛鼠猪")
        self.assertEqual(records[-1].evidence.method, "image_ocr")
        self.assertEqual(records[-1].evidence.directory_anchor, "澳门公式")

    def test_split_parser_binds_issue_line_to_immediate_zodiac_line(self) -> None:
        source = make_source(parser="split_line")
        text = "\n".join(
            [
                "测试站",
                "210期:《测试站》九肖中特",
                "【鼠牛虎兔龙蛇马羊猴】",
                "广告",
            ]
        )

        records = SplitLineParser().parse(source, (document(text),), (210,))

        self.assertEqual(records[0].issue, 210)
        self.assertEqual(records[0].zodiac_text, "鼠牛虎兔龙蛇马羊猴")
        self.assertIn("\n", records[0].evidence.source_line)

    def test_ocr_parser_only_accepts_ocr_documents(self) -> None:
        source = make_source(parser="image_ocr")
        parser = ImageOcrParser()
        text = "测试站\n210期:《测试站》九肖【鼠牛虎兔龙蛇马羊猴】"

        with self.assertRaises(ParseError) as raised:
            parser.parse(source, (document(text),), (210,))
        self.assertEqual(
            raised.exception.failure.code,
            ErrorCode.SOURCE_UNTRUSTED,
        )

        records = parser.parse(
            source,
            (document(text, DocumentMethod.IMAGE_OCR),),
            (210,),
        )
        self.assertEqual(records[0].issue, 210)


class ValidatorTests(unittest.TestCase):
    def test_direction_selects_recent_history_block_before_conflict_check(
        self,
    ) -> None:
        source = make_source(position=Position.BOTTOM)
        records = tuple(
            record(issue, zodiac, line_index=index)
            for index, (issue, zodiac) in enumerate(
                (
                    (208, "鼠牛虎兔龙蛇马羊猴"),
                    (209, "牛虎兔龙蛇马羊猴鸡"),
                    (210, "虎兔龙蛇马羊猴鸡狗"),
                    (208, "兔龙蛇马羊猴鸡狗猪"),
                    (209, "龙蛇马羊猴鸡狗猪鼠"),
                    (210, "蛇马羊猴鸡狗猪鼠牛"),
                )
            )
        )

        verified = Validator().validate(source, records, (210, 209, 208))

        self.assertEqual(
            [item.zodiac_text for item in verified.history.records],
            [
                "蛇马羊猴鸡狗猪鼠牛",
                "龙蛇马羊猴鸡狗猪鼠",
                "兔龙蛇马羊猴鸡狗猪",
            ],
        )

    def test_identical_duplicate_does_not_consume_an_issue_window_slot(
        self,
    ) -> None:
        source = make_source(position=Position.BOTTOM)
        records = (
            record(208, "鼠牛虎兔龙蛇马羊猴", line_index=0),
            record(209, "牛虎兔龙蛇马羊猴鸡", line_index=1),
            record(210, "虎兔龙蛇马羊猴鸡狗", line_index=2),
            record(210, "虎兔龙蛇马羊猴鸡狗", line_index=3),
        )

        verified = Validator().validate(source, records, (208,))

        self.assertEqual(verified.history.records[0].issue, 208)

    def test_invalid_history_issue_does_not_fail_another_requested_issue(
        self,
    ) -> None:
        source = make_source(position=Position.BOTTOM)
        records = (
            record(207, "鼠鼠虎兔龙蛇马羊猴", line_index=0),
            record(208, "鼠牛虎兔龙蛇马羊猴", line_index=1),
            record(209, "牛虎兔龙蛇马羊猴鸡", line_index=2),
            record(210, "虎兔龙蛇马羊猴鸡狗", line_index=3),
        )

        verified = Validator().validate(
            source,
            records,
            (210,),
            history_mode=True,
            history_limit=4,
        )

        self.assertEqual(verified.history.records[0].issue, 210)
        with self.assertRaises(ValidationError) as raised:
            Validator().validate(
                source,
                records,
                (207,),
                history_mode=True,
                history_limit=4,
            )
        self.assertEqual(
            raised.exception.failure.code,
            ErrorCode.INVALID_ZODIAC_COUNT,
        )

    def test_validator_accepts_exact_nine_and_sets_bottom_current_issue(
        self,
    ) -> None:
        source = make_source()
        records = (
            record(208, "狗猴鸡牛蛇鼠兔羊猪", line_index=1),
            record(209, "狗猴虎龙马蛇兔羊猪", line_index=2),
            record(210, "狗猴虎鸡龙牛蛇羊猪", line_index=3),
        )

        verified = Validator().validate(source, records, (210, 209))

        self.assertEqual(verified.history.current_issue, 210)
        self.assertEqual(
            [item.issue for item in verified.history.records],
            [210, 209],
        )

    def test_validator_enforces_direction_recent_three_window(self) -> None:
        source = make_source(position=Position.BOTTOM)
        records = tuple(
            record(issue, "鼠牛虎兔龙蛇马羊猴", line_index=index)
            for index, issue in enumerate((207, 208, 209, 210))
        )

        with self.assertRaises(ValidationError) as raised:
            Validator().validate(source, records, (207,))
        self.assertEqual(raised.exception.failure.code, ErrorCode.ISSUE_MISSING)

        verified = Validator().validate(
            source,
            records,
            (207, 208, 209, 210),
            history_mode=True,
        )
        self.assertEqual(len(verified.history.records), 4)

    def test_validator_rejects_count_duplicates_anchor_and_conflict(self) -> None:
        source = make_source()
        invalid_values = (
            record(210, "鼠牛虎兔龙蛇马羊", line_index=1),
            record(210, "鼠鼠虎兔龙蛇马羊猴", line_index=1),
        )
        for invalid in invalid_values:
            with self.assertRaises(ValidationError) as raised:
                Validator().validate(source, (invalid,), (210,))
            self.assertEqual(
                raised.exception.failure.code,
                ErrorCode.INVALID_ZODIAC_COUNT,
            )

        wrong_anchor = record(
            210,
            "鼠牛虎兔龙蛇马羊猴",
            line_index=1,
            anchor="其他栏目",
        )
        with self.assertRaises(ValidationError) as raised:
            Validator().validate(source, (wrong_anchor,), (210,))
        self.assertEqual(
            raised.exception.failure.code,
            ErrorCode.SOURCE_UNTRUSTED,
        )

        conflict = (
            record(210, "鼠牛虎兔龙蛇马羊猴", line_index=1),
            record(210, "牛鼠虎兔龙蛇马羊猴", line_index=1),
        )
        with self.assertRaises(ValidationError) as raised:
            Validator().validate(source, conflict, (210,))
        self.assertEqual(
            raised.exception.failure.code,
            ErrorCode.CANDIDATE_CONFLICT,
        )


if __name__ == "__main__":
    unittest.main()
