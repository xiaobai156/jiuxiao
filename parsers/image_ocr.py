from __future__ import annotations

import re

from v2.domain.errors import ErrorCode, Failure
from v2.domain.models import Document, DocumentMethod, Record, RecordSet, Source
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
    line_issue,
    normalize_document_text,
    zodiac_candidates,
)


ZODIAC_TEXT = "鼠牛虎兔龙蛇马羊猴鸡狗猪"
DIRECT_NINE_PATTERN = re.compile(
    rf"(?<![{ZODIAC_TEXT}])([{ZODIAC_TEXT}]{{1,12}})(?![{ZODIAC_TEXT}])"
)


class ImageOcrParser:
    def parse(
        self,
        source: Source,
        documents: tuple[Document, ...],
        issues: tuple[int, ...],
    ) -> RecordSet:
        ocr_documents = tuple(
            document
            for document in documents
            if document.method is DocumentMethod.IMAGE_OCR
        )
        if not ocr_documents:
            raise ParseError(
                Failure(
                    ErrorCode.SOURCE_UNTRUSTED,
                    detail="image ocr document is required",
                )
            )
        requested = set(issues)
        data_marker = source.data_marker or "九肖"
        records: list[Record] = []
        block_evidence = []
        for document_index, document in enumerate(ocr_documents):
            text = normalize_document_text(document.text)
            blocks = anchored_history_blocks(
                text,
                source,
                document_label=document.label,
                line_offset=document_line_offset(document),
            )
            if not blocks:
                linked = self._linked_image_block(document, source, text)
                blocks = (linked,) if linked is not None else ()
            if not blocks:
                observed = {
                    issue
                    for line in text.splitlines()
                    if (issue := line_issue(line)) is not None
                }
                if requested & observed:
                    raise ParseError(
                        Failure(
                            ErrorCode.SOURCE_UNTRUSTED,
                            detail="ocr target is not linked to its image anchor",
                        )
                    )
                continue
            for block in blocks:
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
                    issue = line_issue(anchored_line.text)
                    if issue is None:
                        continue
                    source_line = joined_history_line(
                        block.lines,
                        anchored_index,
                    )
                    if issue in requested and any(
                        marker in source_line for marker in LOCKED_MARKERS
                    ):
                        raise ParseError(
                            Failure(
                                ErrorCode.LOCKED_CONTENT,
                                context=(("issue", str(issue)),),
                            )
                        )
                    if not has_data_marker(
                        data_marker,
                        source_line,
                        block.anchor_line,
                    ):
                        continue
                    candidates = [*zodiac_candidates(source_line)]
                    candidates.extend(
                        tuple(match.group(1))
                        for match in DIRECT_NINE_PATTERN.finditer(source_line)
                    )
                    for values in dict.fromkeys(candidates):
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
                                    source_line=source_line,
                                    raw_issue_line=anchored_line.text,
                                    raw_zodiac_line=source_line,
                                    line_index=anchored_line.index,
                                    candidate_index_in_block=candidate_index,
                                    data_marker=data_marker,
                                ),
                            )
                        )
                        candidate_index += 1
        if not block_evidence:
            raise ParseError(Failure(ErrorCode.ANCHOR_MISSING))
        return RecordSet(tuple(records), tuple(block_evidence))

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
        lines = text.splitlines()
        anchored_lines = tuple(
            AnchoredLine(
                min(block_start + local_index, block_end - 1),
                line,
            )
            for local_index, line in enumerate(lines)
            if line_issue(line) is not None
        )
        observed = tuple(
            dict.fromkeys(
                issue
                for line in lines
                if (issue := line_issue(line)) is not None
            )
        )
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
            end=block_end,
            block_id=(
                f"{document.label}:linked-image:{image_index}:"
                f"{block_start}-{block_end}"
            ),
            lines=anchored_lines,
            observed_issues=observed,
        )
