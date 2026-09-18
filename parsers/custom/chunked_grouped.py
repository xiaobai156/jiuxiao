"""解析器：分块型纯 JS 站点的分组九肖。

这类站点把分组字写成「风雷云雨」（项目权威体系为「风雨雷电」），
其中「云」与「电」同席位；本解析器只做这一处站点写法归一化，
其余校验（恰好 3 个分组字、映射完整性、9 个互不重复生肖）仍由统一校验器裁决。
"""

from __future__ import annotations

from dataclasses import replace

from v2.domain.models import Document, RecordSet, Source
from v2.parsers.grouped import GroupedParser


SITE_VARIANT = "云"
CANONICAL_EQUIVALENT = "电"


class ChunkedGroupedParser:
    """chunked_data 文档的分组解析（站点变体归一化后交给 GroupedParser）。

    归一化只作用于文本：站点的「云」在校验前写成「电」，因此 group_map 保持
    项目权威的 4 个分组字；分组字与生肖的对应关系不做任何改动。
    """

    parser_id = "chunked_grouped"

    def parse(
        self,
        source: Source,
        documents: tuple[Document, ...],
        issues: tuple[int, ...],
    ) -> RecordSet:
        normalized_documents = tuple(
            replace(
                document,
                text=document.text.replace(SITE_VARIANT, CANONICAL_EQUIVALENT),
            )
            for document in documents
        )
        effective_source = replace(source, parser=self.parser_id)
        return GroupedParser(self.parser_id).parse(
            effective_source,
            normalized_documents,
            issues,
        )
