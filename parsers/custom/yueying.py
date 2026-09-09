from __future__ import annotations

import re

from v2.domain.errors import ErrorCode, Failure
from v2.domain.models import Document, Record, RecordSet, Source
from v2.parsers.registry import (
    ParseError,
    anchored_history_blocks,
    block_evidence_for,
    document_line_offset,
    evidence_for,
    normalize_document_text,
)
from v2.parsers.safety import (
    issue_scoped_segments,
    safe_zodiac_candidates,
    with_complete_observed_issues,
)


HISTORY_PATTERN = re.compile(r"(?<!\d)\d{3}期九肖中特")


class YueyingParser:
    def parse(
        self,
        source: Source,
        documents: tuple[Document, ...],
        issues: tuple[int, ...],
    ) -> RecordSet:
        del issues
        data_marker = source.data_marker or "九肖中特"
        records: list[Record] = []
        block_evidence = []
        for document_index, document in enumerate(documents):
            text = normalize_document_text(document.text)
            for original_block in anchored_history_blocks(
                text,
                source,
                document_label=document.label,
                line_offset=document_line_offset(document),
            ):
                block = with_complete_observed_issues(original_block)
                block_evidence.append(
                    block_evidence_for(
                        source,
                        document,
                        block,
                        parser_id="yueying",
                        data_marker=data_marker,
                    )
                )
                candidate_index = 0
                for anchored_line in block.lines:
                    for issue, scoped_line in issue_scoped_segments(
                        anchored_line.text
                    ):
                        if not HISTORY_PATTERN.search(scoped_line):
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
                                        parser_id="yueying",
                                        method="yueying",
                                        source_line=scoped_line,
                                        raw_issue_line=scoped_line,
                                        raw_zodiac_line=scoped_line,
                                        line_index=anchored_line.index,
                                        candidate_index_in_block=candidate_index,
                                        data_marker=data_marker,
                                        metadata=(
                                            (
                                                "source_line_index",
                                                str(anchored_line.index),
                                            ),
                                        ),
                                    ),
                                )
                            )
                            candidate_index += 1
        if not block_evidence:
            raise ParseError(Failure(ErrorCode.ANCHOR_MISSING))
        return RecordSet(tuple(records), tuple(block_evidence))
