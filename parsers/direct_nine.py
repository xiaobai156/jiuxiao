from __future__ import annotations

from v2.domain.errors import ErrorCode, Failure
from v2.domain.models import Document, Record, RecordSet, Source
from v2.parsers.registry import (
    LOCKED_MARKERS,
    ParseError,
    anchored_history_blocks,
    block_evidence_for,
    candidate_has_data_semantic,
    complement_candidate,
    document_line_offset,
    evidence_for,
    group_candidate,
    joined_history_line,
    line_issue,
    normalize_document_text,
    zodiac_candidates,
)


class DirectNineParser:
    def __init__(self, parser_id: str = "direct_nine") -> None:
        normalized = str(parser_id).strip()
        if not normalized:
            raise ValueError("parser_id 不能为空")
        self.parser_id = normalized

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
            document_blocks = anchored_history_blocks(
                text,
                source,
                document_label=document.label,
                line_offset=document_line_offset(document),
            )
            for block in document_blocks:
                blocks.append(
                    block_evidence_for(
                        source,
                        document,
                        block,
                        parser_id=self.parser_id,
                        data_marker=data_marker,
                    )
                )
                candidate_index = 0
                for anchored_index, anchored_line in enumerate(block.lines):
                    line_index = anchored_line.index
                    line = anchored_line.text
                    issue = line_issue(line)
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
                    if not candidate_has_data_semantic(
                        source,
                        data_marker,
                        directory_anchor=block.anchor_term,
                        actual_anchor_line=block.anchor_line,
                        candidate_lines=(source_line,),
                    ):
                        continue
                    if (
                        group_candidate(source_line) is not None
                        or complement_candidate(source_line)
                    ):
                        continue
                    for values in zodiac_candidates(source_line):
                        records.append(
                            Record(
                                issue=issue,
                                zodiacs=values,
                                evidence=evidence_for(
                                    source,
                                    document,
                                    document_index,
                                    block,
                                    parser_id=self.parser_id,
                                    method="direct",
                                    source_line=source_line,
                                    raw_issue_line=line,
                                    raw_zodiac_line=source_line,
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
                    context=((
                        "anchor",
                        source.section_marker or source.name,
                    ),),
                )
            )
        return RecordSet(
            records=tuple(records),
            blocks=tuple(blocks),
        )
