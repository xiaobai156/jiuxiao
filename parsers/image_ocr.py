from __future__ import annotations

from v2.domain.errors import ErrorCode, Failure
from v2.domain.models import Document, DocumentMethod, Record, RecordSet, Source
from v2.parsers.custom.common import select_current_content_mode
from v2.parsers.registry import (
    LOCKED_MARKERS,
    AnchoredBlock,
    AnchoredLine,
    ParseError,
    anchor_terms,
    anchored_history_blocks,
    block_evidence_for,
    document_line_offset,
    evidence_for,
    has_data_marker,
    joined_history_line,
    normalize_document_text,
)
from v2.parsers.safety import (
    issue_scoped_segments,
    joined_issue_content,
    observed_issues,
    safe_zodiac_candidates,
    with_complete_observed_issues,
)


class ImageOcrParser:
    def parse(
        self,
        source: Source,
        documents: tuple[Document, ...],
        issues: tuple[int, ...],
    ) -> RecordSet:
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
                        "image ocr parser requires browser DOM or image OCR "
                        "document"
                    ),
                )
            )
        requested = set(issues)
        data_marker = source.data_marker or "九肖"
        records: list[Record] = []
        block_evidence = []
        for document_index, document in enumerate(source_documents):
            text = normalize_document_text(document.text)
            if document.method is DocumentMethod.IMAGE_OCR:
                linked = self._linked_image_block(document, source, text)
                blocks = (linked,) if linked is not None else ()
            else:
                blocks = anchored_history_blocks(
                    text,
                    source,
                    document_label=document.label,
                    line_offset=document_line_offset(document),
                )
            if not blocks:
                observed = set(observed_issues(text.splitlines()))
                if requested & observed:
                    raise ParseError(
                        Failure(
                            ErrorCode.SOURCE_UNTRUSTED,
                            detail="ocr target is not linked to its image anchor",
                        )
                    )
                continue
            for original_block in blocks:
                block = with_complete_observed_issues(original_block)
                block_evidence.append(
                    block_evidence_for(
                        source,
                        document,
                        block,
                        parser_id="image_ocr",
                        data_marker=data_marker,
                    )
                )
                candidate_index = 0
                for anchored_index, anchored_line in enumerate(block.lines):
                    source_line = (
                        joined_issue_content(block.lines, anchored_index)
                        if document.method is DocumentMethod.IMAGE_OCR
                        else joined_history_line(block.lines, anchored_index)
                    )
                    segments = issue_scoped_segments(source_line)
                    if not segments:
                        continue
                    for issue, scoped_line in segments:
                        if issue in requested and any(
                            marker in scoped_line for marker in LOCKED_MARKERS
                        ):
                            raise ParseError(
                                Failure(
                                    ErrorCode.LOCKED_CONTENT,
                                    context=(("issue", str(issue)),),
                                )
                            )
                        if not has_data_marker(
                            data_marker,
                            scoped_line,
                            block.anchor_line,
                        ):
                            continue
                        for values in safe_zodiac_candidates(scoped_line):
                            records.append(
                                Record(
                                    issue=issue,
                                    zodiacs=values,
                                    evidence=evidence_for(
                                        source,
                                        document,
                                        document_index,
                                        block,
                                        parser_id="image_ocr",
                                        method="image_ocr",
                                        source_line=scoped_line,
                                        raw_issue_line=scoped_line,
                                        raw_zodiac_line=scoped_line,
                                        line_index=anchored_line.index,
                                        candidate_index_in_block=candidate_index,
                                        data_marker=data_marker,
                                    ),
                                )
                            )
                            candidate_index += 1
        if not block_evidence:
            raise ParseError(Failure(ErrorCode.ANCHOR_MISSING))
        return select_current_content_mode(
            RecordSet(tuple(records), tuple(block_evidence)),
            issues,
        )

    @staticmethod
    def _linked_image_block(
        document: Document,
        source: Source,
        text: str,
    ) -> AnchoredBlock | None:
        metadata = dict(document.metadata)
        if metadata.get("parent_url") != document.url:
            return None
        anchor_line = metadata.get("anchor_line", "").strip()
        anchor_term = metadata.get("anchor_term", "").strip()
        data_marker_line = metadata.get("data_marker_line", "").strip()
        data_marker = source.data_marker or "九肖"
        if (
            not anchor_line
            or anchor_term not in anchor_terms(source)
            or anchor_term not in anchor_line
            or not data_marker_line
            or not has_data_marker(data_marker, data_marker_line)
        ):
            return None
        try:
            anchor_index = int(metadata["anchor_index"])
            block_start = int(metadata["block_start"])
            block_end = int(metadata["block_end"])
        except (KeyError, ValueError):
            return None
        if (
            anchor_index < 0
            or block_start < 0
            or block_end <= block_start
            or not block_start <= anchor_index < block_end
        ):
            return None

        lines = tuple(line for line in text.splitlines() if line.strip())
        if not lines:
            return None
        virtual_end = max(block_end, block_start + len(lines), anchor_index + 1)
        anchored_lines = tuple(
            AnchoredLine(block_start + local_index, line)
            for local_index, line in enumerate(lines)
        )
        observed = observed_issues(lines)
        image_index = metadata.get("image_index", "unknown")
        proven_anchor_line = (
            anchor_line
            if data_marker_line == anchor_line
            else f"{anchor_line} | {data_marker_line}"
        )
        return AnchoredBlock(
            anchor_line=proven_anchor_line,
            anchor_term=anchor_term,
            anchor_index=anchor_index,
            anchor_occurrence=1,
            start=block_start,
            end=virtual_end,
            block_id=(
                f"{document.label}:linked-image:{image_index}:"
                f"{block_start}-{virtual_end}"
            ),
            lines=anchored_lines,
            observed_issues=observed,
        )
