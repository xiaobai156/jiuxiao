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
    joined_history_line,
    normalize_document_text,
)
from v2.parsers.safety import (
    group_candidates,
    issue_scoped_segments,
    safe_zodiac_candidates,
    with_complete_observed_issues,
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
            for original_block in document_blocks:
                block = with_complete_observed_issues(original_block)
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
                    source_line = joined_history_line(block.lines, anchored_index)
                    for issue, scoped_line in issue_scoped_segments(source_line):
                        if issue in requested and any(
                            marker in scoped_line for marker in LOCKED_MARKERS
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
                            candidate_lines=(scoped_line,),
                        ):
                            continue
                        if (
                            group_candidates(scoped_line)
                            or complement_candidate(scoped_line)
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
                                        parser_id=self.parser_id,
                                        method="direct",
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
        return RecordSet(records=tuple(records), blocks=tuple(blocks))
