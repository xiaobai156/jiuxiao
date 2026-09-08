from __future__ import annotations

from v2.domain.errors import ErrorCode, Failure
from v2.domain.models import Document, Record, RecordSet, Source
from v2.parsers.registry import (
    LOCKED_MARKERS,
    ParseError,
    anchored_history_blocks,
    block_evidence_for,
    document_line_offset,
    evidence_for,
    has_data_marker,
    line_issue,
    normalize_document_text,
    zodiac_candidates,
)


class SplitLineParser:
    def parse(
        self,
        source: Source,
        documents: tuple[Document, ...],
        issues: tuple[int, ...],
    ) -> RecordSet:
        normalized_documents = tuple(
            normalize_document_text(document.text) for document in documents
        )
        data_marker = source.data_marker or "九肖"
        requested = set(issues)
        records: list[Record] = []
        blocks = []
        for document_index, (document, text) in enumerate(
            zip(documents, normalized_documents, strict=True)
        ):
            lines = text.splitlines()
            line_offset = document_line_offset(document)
            for block in anchored_history_blocks(
                text,
                source,
                document_label=document.label,
                line_offset=line_offset,
            ):
                blocks.append(
                    block_evidence_for(
                        source,
                        document,
                        block,
                        parser_id="split_line",
                        data_marker=data_marker,
                    )
                )
                candidate_index = 0
                for anchored_line in block.lines:
                    line_index = anchored_line.index
                    local_index = line_index - line_offset
                    line = anchored_line.text
                    issue = line_issue(line)
                    if issue is None or local_index + 1 >= len(lines):
                        continue
                    if not has_data_marker(
                        data_marker,
                        line,
                        block.anchor_line,
                    ):
                        continue
                    if issue in requested and any(
                        marker in line for marker in LOCKED_MARKERS
                    ):
                        raise ParseError(
                            Failure(
                                ErrorCode.LOCKED_CONTENT,
                                context=(("issue", str(issue)),),
                            )
                        )
                    if local_index + 1 + line_offset >= block.end:
                        continue
                    next_line = lines[local_index + 1]
                    next_issue = line_issue(next_line)
                    if next_issue is not None and next_issue != issue:
                        continue
                    for values in zodiac_candidates(next_line):
                        records.append(
                            Record(
                                issue=issue,
                                zodiacs=values,
                                evidence=evidence_for(
                                    source,
                                    document,
                                    document_index,
                                    block,
                                    parser_id="split_line",
                                    method="split_line",
                                    source_line=f"{line}\n{next_line}",
                                    raw_issue_line=line,
                                    raw_zodiac_line=next_line,
                                    line_index=line_index,
                                    candidate_index_in_block=candidate_index,
                                    data_marker=data_marker,
                                ),
                            )
                        )
                        candidate_index += 1
        if not blocks:
            raise ParseError(
                Failure(
                    ErrorCode.ANCHOR_MISSING,
                    context=(("anchor", source.section_marker or source.name),),
                )
            )
        return RecordSet(tuple(records), tuple(blocks))
