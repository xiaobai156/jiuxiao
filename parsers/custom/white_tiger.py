from __future__ import annotations

from v2.domain.errors import ErrorCode, Failure
from v2.domain.models import Document, Record, RecordSet, Source
from v2.parsers.registry import (
    AnchoredBlock,
    AnchoredLine,
    ParseError,
    block_evidence_for,
    document_has_anchor,
    document_line_offset,
    evidence_for,
    has_data_marker,
    line_issue,
    matched_anchor,
    normalize_document_text,
    zodiac_candidates,
)


WHITE_TIGER_ANCHOR = "澳门-白虎"


class WhiteTigerParser:
    def parse(
        self,
        source: Source,
        documents: tuple[Document, ...],
        issues: tuple[int, ...],
    ) -> RecordSet:
        del issues
        data_marker = source.data_marker or "九肖"
        records: list[Record] = []
        block_evidence = []
        source_anchor_found = False
        for document_index, document in enumerate(documents):
            text = normalize_document_text(document.text)
            if not document_has_anchor(text, source):
                continue
            source_anchor_found = True
            lines = text.splitlines()
            offset = document_line_offset(document)
            source_anchors = tuple(
                (index, line, term)
                for index, line in enumerate(lines)
                if (term := matched_anchor(line, source))
            )
            starts = tuple(
                index
                for index, line in enumerate(lines)
                if WHITE_TIGER_ANCHOR in line
            )
            for occurrence, start in enumerate(starts, start=1):
                preceding_anchors = tuple(
                    anchor for anchor in source_anchors if anchor[0] <= start
                )
                if not preceding_anchors:
                    continue
                anchor_index, anchor_line, anchor_term = preceding_anchors[-1]
                anchor_occurrence = (
                    source_anchors.index(preceding_anchors[-1]) + 1
                )
                end = (
                    starts[occurrence]
                    if occurrence < len(starts)
                    else len(lines)
                )
                for index in range(start + 1, end):
                    if "点击" in lines[index] and "加载全部记录" in lines[index]:
                        end = index
                        break
                candidate_lines = tuple(
                    AnchoredLine(index + offset, lines[index])
                    for index in range(start + 1, end)
                    if line_issue(lines[index]) is not None
                    and has_data_marker(data_marker, lines[index])
                )
                observed = tuple(
                    dict.fromkeys(
                        issue
                        for index in range(start + 1, end)
                        if (issue := line_issue(lines[index])) is not None
                    )
                )
                block = AnchoredBlock(
                    anchor_line=anchor_line,
                    anchor_term=anchor_term,
                    anchor_index=anchor_index + offset,
                    anchor_occurrence=anchor_occurrence,
                    start=anchor_index + offset,
                    end=max(start + offset + 1, end + offset),
                    block_id=(
                        f"{document.label}:white-tiger:{occurrence}:"
                        f"{anchor_index + offset}-{end + offset}"
                    ),
                    lines=candidate_lines,
                    observed_issues=observed,
                )
                block_evidence.append(
                    block_evidence_for(
                        source,
                        document,
                        block,
                        parser_id="white_tiger",
                        data_marker=data_marker,
                    )
                )
                candidate_index = 0
                for anchored_line in candidate_lines:
                    issue = line_issue(anchored_line.text)
                    if issue is None:
                        continue
                    for values in zodiac_candidates(anchored_line.text):
                        records.append(
                            Record(
                                issue=issue,
                                zodiacs=values,
                                evidence=evidence_for(
                                    source,
                                    document,
                                    document_index,
                                    block,
                                    parser_id="white_tiger",
                                    method="white_tiger",
                                    source_line=anchored_line.text,
                                    raw_issue_line=anchored_line.text,
                                    raw_zodiac_line=anchored_line.text,
                                    line_index=anchored_line.index,
                                    candidate_index_in_block=candidate_index,
                                    data_marker=data_marker,
                                    metadata=(
                                        ("block_marker", lines[start]),
                                    ),
                                ),
                            )
                        )
                        candidate_index += 1
        if not source_anchor_found or not block_evidence:
            raise ParseError(Failure(ErrorCode.ANCHOR_MISSING))
        return RecordSet(tuple(records), tuple(block_evidence))
