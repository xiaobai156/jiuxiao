from __future__ import annotations

from dataclasses import replace

from v2.domain.errors import ErrorCode, Failure
from v2.domain.models import Document, RecordSet, Source
from v2.parsers.direct_nine import DirectNineParser
from v2.parsers.registry import (
    ParseError,
    document_line_offset,
    normalize_document_text,
)


HEADER_MARKER = "九肖中特"


class HeaderDirectNineParser:
    """Use a verified header as the data semantic and the author as anchor."""

    parser_id = "header_direct_nine"

    def parse(
        self,
        source: Source,
        documents: tuple[Document, ...],
        issues: tuple[int, ...],
    ) -> RecordSet:
        data_marker = source.data_marker or "九肖"
        internal_source = replace(
            source,
            parser=self.parser_id,
            section_marker=HEADER_MARKER,
            data_marker=data_marker,
        )
        parsed = DirectNineParser(self.parser_id).parse(
            internal_source,
            documents,
            issues,
        )

        updated_blocks = []
        contexts: dict[tuple[str, str, str, str], tuple[str, int, str]] = {}
        for block in parsed.blocks:
            document = self._document_for_block(documents, block)
            anchor_line, anchor_index, data_marker_line = self._context(
                source,
                document,
                block.block_start,
                block.block_end,
                data_marker,
            )
            updated = replace(
                block,
                directory_anchor=source.section_marker or source.name,
                actual_anchor_line=anchor_line,
                anchor_index=anchor_index,
                data_marker=data_marker,
            )
            updated_blocks.append(updated)
            contexts[self._block_key(block)] = (
                anchor_line,
                anchor_index,
                data_marker_line,
            )

        records = []
        for record in parsed.records:
            context = contexts.get(self._record_block_key(record))
            if context is None:
                raise ParseError(
                    Failure(
                        ErrorCode.SOURCE_UNTRUSTED,
                        detail="header direct candidate block is missing",
                    )
                )
            anchor_line, anchor_index, data_marker_line = context
            metadata = tuple(record.evidence.metadata)
            metadata = (
                *metadata,
                ("data_marker_line", data_marker_line),
            )
            records.append(
                replace(
                    record,
                    evidence=replace(
                        record.evidence,
                        directory_anchor=source.section_marker or source.name,
                        actual_anchor_line=anchor_line,
                        anchor_index=anchor_index,
                        data_marker=data_marker,
                        metadata=metadata,
                    ),
                )
            )
        return RecordSet(tuple(records), tuple(updated_blocks))

    @staticmethod
    def _document_for_block(
        documents: tuple[Document, ...],
        block,
    ) -> Document:
        for document in documents:
            if (
                document.label == block.document_label
                and document.url == block.document_url
                and document.method.value == block.document_method
            ):
                return document
        raise ParseError(
            Failure(
                ErrorCode.SOURCE_UNTRUSTED,
                detail="header direct document is missing",
            )
        )

    @staticmethod
    def _context(
        source: Source,
        document: Document,
        block_start: int,
        block_end: int,
        data_marker: str,
    ) -> tuple[str, int, str]:
        offset = document_line_offset(document)
        lines = normalize_document_text(document.text).splitlines()
        start = max(0, block_start - offset)
        end = min(len(lines), block_end - offset)
        section = tuple(
            (index + offset, line)
            for index, line in enumerate(lines[start:end], start)
        )
        author = next(
            (
                (index, line)
                for index, line in section
                if source.name in line
            ),
            None,
        )
        header = next(
            (
                line
                for _index, line in section
                if HEADER_MARKER in line
            ),
            "",
        )
        if author is None or not header:
            raise ParseError(
                Failure(
                    ErrorCode.ANCHOR_MISSING,
                    context=(
                        ("anchor", source.section_marker or source.name),
                    ),
                )
            )
        return author[1], author[0], header

    @staticmethod
    def _block_key(block) -> tuple[str, str, str, str]:
        return (
            block.document_label,
            block.document_url,
            block.document_method,
            block.block_id,
        )

    @classmethod
    def _record_block_key(cls, record) -> tuple[str, str, str, str]:
        evidence = record.evidence
        return (
            evidence.document_label,
            evidence.document_url,
            evidence.document_method,
            evidence.block_id,
        )
