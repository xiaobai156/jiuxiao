from __future__ import annotations

from dataclasses import replace

from v2.domain.errors import ErrorCode, Failure
from v2.domain.models import Document, DocumentMethod, Position, RecordSet, Source
from v2.parsers.direct_nine import DirectNineParser
from v2.parsers.grouped import GroupedParser
from v2.parsers.registry import (
    ParseError,
    anchored_history_blocks,
    document_line_offset,
    line_issue,
    normalize_document_text,
    split_cyclic_history_lines,
    _looks_like_history_candidate,
)


class TopicCyclicParser:
    """Parse topic pages that visibly contain two circular history runs.

    A long, explicit 001/365 seam is the only accepted boundary.  The source's
    fixed top/bottom direction then selects the upper/lower run; short or
    non-cyclic duplicates remain one block and still fail as conflicts.
    """

    parser_id = "topic_cyclic_nine"

    def parse(
        self,
        source: Source,
        documents: tuple[Document, ...],
        issues: tuple[int, ...],
    ) -> RecordSet:
        selected_documents: list[Document] = []
        primary_documents = tuple(
            document
            for document in documents
            if document.method is DocumentMethod.BROWSER_DOM
        )
        if not primary_documents:
            raise ParseError(
                Failure(
                    ErrorCode.SOURCE_UNTRUSTED,
                    detail="topic_cyclic_nine requires primary browser DOM",
                )
            )
        for document in primary_documents:
            text = normalize_document_text(document.text)
            base_blocks = anchored_history_blocks(
                text,
                source,
                document_label=document.label,
                line_offset=document_line_offset(document),
            )
            for block in base_blocks:
                if not any(
                    line_issue(line.text) is not None
                    and _looks_like_history_candidate(line.text)
                    for line in block.lines
                ):
                    continue
                segments = split_cyclic_history_lines(block)
                if len(segments) == 1:
                    selected_documents.append(document)
                    continue
                segment_documents = tuple(
                    self._segment_document(document, block, segment, index)
                    for index, segment in enumerate(segments, start=1)
                )
                selected_documents.append(
                    (
                        segment_documents[0]
                        if source.position is Position.TOP
                        else segment_documents[-1]
                    )
                )

        if not selected_documents:
            raise ParseError(
                Failure(
                    ErrorCode.ANCHOR_MISSING,
                    context=((
                        "anchor",
                        source.section_marker or source.name,
                    ),),
                )
            )
        parser = (
            GroupedParser(self.parser_id)
            if source.group_map
            else DirectNineParser(self.parser_id)
        )
        return parser.parse(
            source,
            tuple(selected_documents),
            issues,
        )

    @staticmethod
    def _segment_document(
        document: Document,
        block,
        segment,
        segment_index: int,
    ) -> Document:
        # Repeat the verified page anchor in each synthetic document so the
        # parser can prove that the selected segment belongs to this栏目.
        segment_lines = tuple(line.text for line in segment)
        lines = (
            segment_lines
            if segment_lines and segment_lines[0] == block.anchor_line
            else (block.anchor_line, *segment_lines)
        )
        metadata = tuple(
            (key, value)
            for key, value in document.metadata
            if key != "line_offset"
        )
        metadata += (
            ("line_offset", "0"),
            ("original_block_id", block.block_id),
            ("cycle_segment", str(segment_index)),
        )
        return replace(
            document,
            label=f"{document.label}:cycle-{segment_index}",
            text="\n".join(lines),
            metadata=metadata,
        )
