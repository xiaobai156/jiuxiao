from __future__ import annotations

from v2.parsers.custom.color_info_grouped import ColorInfoGroupedParser
from v2.parsers.custom.complement_three import ComplementThreeParser
from v2.parsers.custom.dynamic_article_grouped import (
    DynamicArticleGroupedParser,
)
from v2.parsers.custom.dynamic_article_grouped_separator import (
    DynamicArticleGroupedSeparatorParser,
)
from v2.parsers.custom.formula_article_adaptive import (
    FormulaArticleAdaptiveParser,
)
from v2.parsers.custom.formula_article_ocr_alias import (
    FormulaArticleOcrAliasParser,
)
from v2.parsers.custom.formula_dom import FormulaDomParser
from v2.parsers.custom.formula_next_issue_ocr import (
    FormulaNextIssueOcrParser,
)
from v2.parsers.custom.header_direct_nine import HeaderDirectNineParser
from v2.parsers.custom.liuiuqu import LiuiuquParser
from v2.parsers.custom.named_section import NamedSectionParser
from v2.parsers.custom.profile_history import ProfileHistoryParser
from v2.parsers.custom.single_season_complement import (
    SingleSeasonComplementParser,
)
from v2.parsers.custom.topic_cyclic import TopicCyclicParser
from v2.parsers.custom.white_tiger import WhiteTigerParser
from v2.parsers.custom.yueying import YueyingParser
from v2.parsers.direct_nine import DirectNineParser
from v2.parsers.grouped import GroupedParser
from v2.parsers.image_ocr import ImageOcrParser
from v2.parsers.registry import ParserRegistry
from v2.parsers.split_line import SplitLineParser


def build_parser_registry() -> ParserRegistry:
    registry = ParserRegistry()
    registry.register("direct_nine", DirectNineParser())
    registry.register("complement_three", ComplementThreeParser())
    registry.register("liuiuqu", LiuiuquParser())
    registry.register(
        "dynamic_article_grouped",
        DynamicArticleGroupedParser(),
    )
    registry.register(
        "dynamic_article_grouped_separator",
        DynamicArticleGroupedSeparatorParser(),
    )
    registry.register("header_direct_nine", HeaderDirectNineParser())
    registry.register("grouped", GroupedParser())
    registry.register("split_line", SplitLineParser())
    registry.register("image_ocr", ImageOcrParser())
    registry.register(
        "formula_article_adaptive",
        FormulaArticleAdaptiveParser(),
    )
    registry.register(
        "formula_article_ocr_alias",
        FormulaArticleOcrAliasParser(),
    )
    registry.register("formula_dom", FormulaDomParser())
    registry.register(
        "formula_next_issue_ocr",
        FormulaNextIssueOcrParser(),
    )
    registry.register("white_tiger", WhiteTigerParser())
    registry.register("yueying", YueyingParser())
    registry.register("color_info_grouped", ColorInfoGroupedParser())
    registry.register("named_section", NamedSectionParser())
    registry.register("profile_history", ProfileHistoryParser())
    registry.register(
        "single_season_complement",
        SingleSeasonComplementParser(),
    )
    registry.register(
        "single_season_complement_canonical",
        SingleSeasonComplementParser(
            "single_season_complement_canonical"
        ),
    )
    registry.register("topic_cyclic_nine", TopicCyclicParser())
    return registry
