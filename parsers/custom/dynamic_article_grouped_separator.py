from __future__ import annotations

from v2.domain.models import DocumentMethod, Source
from v2.parsers.custom.dynamic_article_grouped import (
    DynamicArticleGroupedParser,
)
from v2.parsers.registry import group_candidate, line_issue


_IN_BLOCK_SEPARATORS = frozenset((".", "．"))


class DynamicArticleGroupedSeparatorParser(DynamicArticleGroupedParser):
    """Keep a punctuated continuation in one dynamic grouped history block."""

    def __init__(self) -> None:
        super().__init__()
        self.parser_id = "dynamic_article_grouped_separator"

    def _history_blocks(
        self,
        text: str,
        source: Source,
        *,
        document_label: str,
        line_offset: int,
        document_method: DocumentMethod,
    ):
        if (
            source.fetcher != "dynamic_article"
            or document_method is not DocumentMethod.DYNAMIC_API
            or not source.section_marker
        ):
            return super()._history_blocks(
                text,
                source,
                document_label=document_label,
                line_offset=line_offset,
                document_method=document_method,
            )

        mapping = dict(source.group_map)
        lines = text.splitlines()
        for index in range(1, len(lines) - 1):
            if lines[index].strip() not in _IN_BLOCK_SEPARATORS:
                continue
            previous = lines[index - 1]
            following = lines[index + 1]
            if (
                source.section_marker not in previous
                or source.section_marker not in following
                or line_issue(previous) is None
                or line_issue(following) is None
                or group_candidate(previous, mapping) is None
                or group_candidate(following, mapping) is None
            ):
                continue
            lines[index] = "---"

        return super()._history_blocks(
            "\n".join(lines),
            source,
            document_label=document_label,
            line_offset=line_offset,
            document_method=document_method,
        )
