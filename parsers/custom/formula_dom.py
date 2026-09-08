from __future__ import annotations

import re
from dataclasses import replace

from v2.domain.errors import ErrorCode, Failure
from v2.domain.models import Document, DocumentMethod, Record, RecordSet, Source
from v2.parsers.custom.common import select_current_content_mode
from v2.parsers.direct_nine import DirectNineParser
from v2.parsers.image_ocr import ImageOcrParser
from v2.parsers.registry import ParseError, normalize_document_text

SEMANTIC_IDENTITY = "__formula_dom_identity__"


class FormulaDomParser:
    """Parse formula history from the block's actual DOM/OCR presentation.

    These pages also contain advertising images, scripts and frames.  The
    target block is selected from its current DOM or linked-image evidence;
    unrelated page images never become candidates.
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
        source_documents = tuple(
            document
            for document in documents
            if document.method
            in (DocumentMethod.BROWSER_DOM, DocumentMethod.IMAGE_OCR)
        )
        if not source_documents:
            raise ParseError(
                Failure(
                    ErrorCode.SOURCE_UNTRUSTED,
                    detail=(
                        "formula_dom requires browser DOM or image OCR "
                        "document"
                    ),
                )
            )

        data_marker = source.data_marker or "九肖"
        records: list[Record] = []
        blocks = []
        for document in source_documents:
            document_text = normalize_document_text(document.text)
            parse_document = document
            if document.method is DocumentMethod.IMAGE_OCR:
                linked = ImageOcrParser._linked_image_block(
                    document,
                    source,
                    document_text,
                )
                if linked is None:
                    continue
                header_lines = (linked.anchor_line,)
                parse_document = replace(
                    document,
                    text=f"{linked.anchor_line}\n{document_text}",
                )
            else:
                header_lines = self._header_lines(
                    document_text,
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
                    (parse_document,),
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

        selected = select_current_content_mode(
            RecordSet(tuple(records), tuple(blocks)),
            issues,
        )
        records = list(selected.records)
        blocks = list(selected.blocks)
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
