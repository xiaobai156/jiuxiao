from __future__ import annotations

from v2.domain.models import DocumentMethod, Source
from v2.parsers.grouped import GroupedParser
from v2.parsers.registry import (
    AnchoredBlock,
    anchored_history_blocks,
    has_data_marker,
    line_issue,
)


class DynamicArticleGroupedParser(GroupedParser):
    """Keep one logical history block for a dynamic article API document."""

    def __init__(self) -> None:
        super().__init__("dynamic_article_grouped")

    def _history_blocks(
        self,
        text: str,
        source: Source,
        *,
        document_label: str,
        line_offset: int,
        document_method: DocumentMethod,
    ) -> tuple[AnchoredBlock, ...]:
        blocks = anchored_history_blocks(
            text,
            source,
            document_label=document_label,
            line_offset=line_offset,
        )
        if (
            source.fetcher != "dynamic_article"
            or document_method is not DocumentMethod.DYNAMIC_API
        ):
            return blocks

        data_marker = source.data_marker or "".join(
            key for key, _value in source.group_map
        )
        merged: list[AnchoredBlock] = []
        for block in blocks:
            if merged:
                previous = merged[-1]
                if (
                    block.start == previous.end
                    and block.anchor_term == previous.anchor_term
                    and line_issue(block.anchor_line) is not None
                    and has_data_marker(data_marker, block.anchor_line)
                ):
                    merged[-1] = AnchoredBlock(
                        anchor_line=previous.anchor_line,
                        anchor_term=previous.anchor_term,
                        anchor_index=previous.anchor_index,
                        anchor_occurrence=previous.anchor_occurrence,
                        start=previous.start,
                        end=block.end,
                        block_id=(
                            f"{document_label}:dynamic-grouped:"
                            f"{previous.start}-{block.end}"
                        ),
                        lines=(*previous.lines, *block.lines),
                        observed_issues=tuple(
                            dict.fromkeys(
                                (
                                    *previous.observed_issues,
                                    *block.observed_issues,
                                )
                            )
                        ),
                    )
                    continue
            merged.append(block)
        return tuple(merged)
