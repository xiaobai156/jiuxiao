from __future__ import annotations

import unittest

from v2.domain.models import Document, DocumentMethod, Position, Source
from v2.parsers.custom.dynamic_article_grouped import (
    DynamicArticleGroupedParser,
)
from v2.parsers.custom.header_direct_nine import HeaderDirectNineParser
from v2.validator import Validator


GROUPS = (
    ("琴", "兔蛇鸡"),
    ("棋", "鼠牛狗"),
    ("书", "虎龙马"),
    ("画", "羊猴猪"),
)


def document(text: str, method: DocumentMethod) -> Document:
    return Document(
        label=method.value,
        url="https://example.test/page",
        text=text,
        method=method,
    )


class SpecialParserTests(unittest.TestCase):
    def test_dynamic_article_grouped_merges_contiguous_history_blocks(self) -> None:
        source = Source(
            name="青栀无梦",
            url="https://example.test/article/admin/1",
            position=Position.BOTTOM,
            section_marker="",
            fetcher="dynamic_article",
            parser="dynamic_article_grouped",
            group_map=GROUPS,
            data_marker="琴棋书画",
        )
        parsed = DynamicArticleGroupedParser().parse(
            source,
            (
                document(
                    "\n".join(
                        (
                            "青栀无梦",
                            "209期: 青栀无梦 琴棋书画【画棋书】开00准",
                            "210期: 青栀无梦 琴棋书画【画琴书】开00准",
                            "211期: 青栀无梦 琴棋书画【画棋琴】开00准",
                        )
                    ),
                    DocumentMethod.DYNAMIC_API,
                ),
            ),
            (211,),
        )

        self.assertEqual(len(parsed.blocks), 1)
        verified = Validator().validate(source, parsed, (211,))
        self.assertEqual(
            verified.history.records[0].zodiac_text,
            "羊猴猪鼠牛狗兔蛇鸡",
        )

    def test_header_direct_nine_rewrites_evidence_to_author_anchor(self) -> None:
        source = Source(
            name="清香权力",
            url="https://example.test/topic/1",
            position=Position.TOP,
            section_marker="",
            fetcher="browser_page",
            parser="header_direct_nine",
        )
        parsed = HeaderDirectNineParser().parse(
            source,
            (
                document(
                    "\n".join(
                        (
                            "高手贴213期:【九肖中特】连准中",
                            "作者:清香权力",
                            "213期:〖狗蛇兔猪猴龙羊鸡马〗（開：0000）準",
                            "212期:〖龙猪羊鼠兔虎蛇马牛〗（開：牛06）準",
                            "211期:〖狗鸡马羊虎猪猴牛兔〗（開：马01）準",
                        )
                    ),
                    DocumentMethod.BROWSER_DOM,
                ),
            ),
            (213,),
        )

        self.assertEqual(parsed.blocks[0].directory_anchor, "清香权力")
        self.assertIn("清香权力", parsed.blocks[0].actual_anchor_line)
        verified = Validator().validate(source, parsed, (213,))
        self.assertEqual(
            verified.history.records[0].zodiac_text,
            "狗蛇兔猪猴龙羊鸡马",
        )


if __name__ == "__main__":
    unittest.main()
