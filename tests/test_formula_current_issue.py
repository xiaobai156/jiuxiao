from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if "v2" not in sys.modules:
    specification = importlib.util.spec_from_file_location(
        "v2",
        PROJECT_ROOT / "__init__.py",
        submodule_search_locations=[str(PROJECT_ROOT)],
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("无法加载 V2 测试包")
    package = importlib.util.module_from_spec(specification)
    sys.modules["v2"] = package
    specification.loader.exec_module(package)

from v2.domain.models import (  # noqa: E402
    Document,
    DocumentMethod,
    Position,
    Source,
)
from v2.parsers.image_ocr import ImageOcrParser  # noqa: E402
from v2.validator import Validator  # noqa: E402


class FormulaCurrentIssueTests(unittest.TestCase):
    def test_image_current_issue_wins_over_dom_title_only_block(self) -> None:
        marker = "嫦娥彩报╠无错九肖╣公式规律"
        source = Source(
            name="嫦娥公式",
            url="https://example.test/topic/544154.html",
            position=Position.BOTTOM,
            section_marker=marker,
            fetcher="browser_page",
            parser="image_ocr",
            source_policy=(
                DocumentMethod.BROWSER_DOM.value,
                DocumentMethod.IMAGE_OCR.value,
            ),
        )
        dom = Document(
            label="browser-dom",
            url=source.url,
            text=f"226期：{marker}\n作者:澳门公式",
            method=DocumentMethod.BROWSER_DOM,
        )
        image = Document(
            label="image-ocr:3",
            url=source.url,
            text=(
                "224期:251908491836+09公式：+0下期：猪狗鸡猴羊马蛇龙兔√\n"
                "225期:073427101938+01公式:+0下期:鸡猴羊马蛇龙兔虎牛v\n"
                "226期：鸡猴羊马蛇龙兔虎牛"
            ),
            method=DocumentMethod.IMAGE_OCR,
            metadata=(
                ("image_index", "3"),
                ("parent_url", source.url),
                ("anchor_line", f"226期：{marker}"),
                ("anchor_term", marker),
                ("data_marker_line", f"226期：{marker}"),
                ("anchor_index", "4"),
                ("block_start", "4"),
                ("block_end", "6"),
            ),
        )

        parsed = ImageOcrParser().parse(source, (dom, image), (226,))
        verified = Validator().validate(source, parsed, (226,))

        self.assertEqual(
            verified.history.records[0].zodiac_text,
            "鸡猴羊马蛇龙兔虎牛",
        )
        self.assertEqual(
            verified.history.records[0].evidence.document_method,
            DocumentMethod.IMAGE_OCR.value,
        )


if __name__ == "__main__":
    unittest.main()
