from __future__ import annotations

import re
from dataclasses import replace

from v2.domain.errors import ErrorCode, Failure
from v2.domain.models import Document, DocumentMethod, Record, RecordSet, Source
from v2.parsers.direct_nine import DirectNineParser
from v2.parsers.registry import ParseError, normalize_document_text


SEMANTIC_IDENTITY = "__formula_dom_identity__"


class FormulaDomParser:
    """Parse the visible formula history from the primary browser DOM.

    These pages also contain advertising images, scripts and frames.  The
    formula table is ordinary text immediately under a stable section marker;
    only the primary browser DOM is authoritative for this parser.
    """

    parser_id = "formula_dom"

    def parse(
        self,
        source: Source,
        documents: tuple[Document, ...],
        issues: tuple[int, ...],
    ) -> RecordSet:
        if not source.section_marker:
            raise ParseError(
                Failure(
                    ErrorCode.CONFIG_INVALID,
                    detail="formula_dom requires section_marker",
                )
            )
        dom_documents = tuple(
            document
            for document in documents
            if document.method is DocumentMethod.BROWSER_DOM
        )
        if not dom_documents:
            raise ParseError(
                Failure(
                    ErrorCode.SOURCE_UNTRUSTED,
                    detail="formula_dom requires primary browser DOM",
                )
            )

        data_marker = source.data_marker or "九肖"
        records: list[Record] = []
        blocks = []
        for document in dom_documents:
            header_lines = self._header_lines(
                normalize_document_text(document.text),
                source.section_marker,
            )
            for header_line in header_lines:
                # The section title for 风神九肖 contains the source name
                # itself. Keep the semantic marker in the full heading
                # without letting the generic helper strip that name.
                internal_source = replace(
                    source,
                    name=SEMANTIC_IDENTITY,
                    section_marker=header_line,
                    parser=self.parser_id,
                    aliases=(),
                    data_marker=data_marker,
                )
                parsed = DirectNineParser(self.parser_id).parse(
                    internal_source,
                    (document,),
                    issues,
                )
                blocks.extend(parsed.blocks)
                records.extend(parsed.records)

        if not blocks:
            raise ParseError(
                Failure(
                    ErrorCode.ANCHOR_MISSING,
                    context=(("anchor", source.section_marker),),
                )
            )

        updated_blocks = tuple(
            replace(
                block,
                directory_anchor=source.section_marker,
                data_marker=data_marker,
            )
            for block in blocks
        )
        updated_records: list[Record] = []
        for record in records:
            metadata = tuple(record.evidence.metadata)
            if not any(
                key == "data_marker_line" for key, _value in metadata
            ):
                metadata = (
                    *metadata,
                    ("data_marker_line", record.evidence.actual_anchor_line),
                )
            updated_records.append(
                replace(
                    record,
                    evidence=replace(
                        record.evidence,
                        directory_anchor=source.section_marker,
                        metadata=metadata,
                    ),
                )
            )
        return RecordSet(tuple(updated_records), updated_blocks)

    @staticmethod
    def _header_lines(text: str, marker: str) -> tuple[str, ...]:
        pattern = re.compile(
            rf"^\s*\d{{1,3}}期\s*(?::|：)?\s*{re.escape(marker)}(?:\s|$)"
        )
        return tuple(
            line
            for line in text.splitlines()
            if pattern.search(line)
        )
