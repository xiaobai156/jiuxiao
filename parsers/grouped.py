from __future__ import annotations

from v2.domain.errors import ErrorCode, Failure
from v2.domain.models import Document, DocumentMethod, Record, RecordSet, Source
from v2.parsers.registry import (
    LOCKED_MARKERS,
    AnchoredBlock,
    ParseError,
    anchored_history_blocks,
    block_evidence_for,
    document_line_offset,
    evidence_for,
    group_mapping_text,
    has_data_marker,
    joined_history_line,
    normalize_document_text,
)
from v2.parsers.safety import (
    group_candidates,
    issue_scoped_segments,
    with_complete_observed_issues,
)


class GroupedParser:
    def __init__(self, parser_id: str = "grouped") -> None:
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
        if not source.group_map:
            raise ParseError(Failure(ErrorCode.GROUP_EVIDENCE_MISSING))
        mapping = dict(source.group_map)
        group_type = "".join(mapping)
        data_marker = source.data_marker or group_type
        normalized_documents = tuple(
            normalize_document_text(document.text) for document in documents
        )
        records: list[Record] = []
        blocks = []
        requested = set(issues)
        for document_index, (document, text) in enumerate(
            zip(documents, normalized_documents, strict=True)
        ):
            for original_block in self._history_blocks(
                text,
                source,
                document_label=document.label,
                line_offset=document_line_offset(document),
                document_method=document.method,
            ):
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
                        for method, _category, groups, zodiac in group_candidates(
                            scoped_line,
                            mapping,
                        ):
                            candidate_marker = (
                                data_marker
                                if has_data_marker(
                                    data_marker,
                                    scoped_line,
                                    block.anchor_line,
                                )
                                else groups
                            )
                            records.append(
                                Record(
                                    issue=issue,
                                    zodiacs=tuple(zodiac),
                                    evidence=evidence_for(
                                        source,
                                        document,
                                        document_index,
                                        block,
                                        parser_id=self.parser_id,
                                        method=method,
                                        source_line=scoped_line,
                                        raw_issue_line=scoped_line,
                                        raw_zodiac_line=scoped_line,
                                        line_index=anchored_line.index,
                                        candidate_index_in_block=candidate_index,
                                        data_marker=candidate_marker,
                                        metadata=(
                                            ("group_type", group_type),
                                            ("group_text", groups),
                                            (
                                                "group_mapping",
                                                group_mapping_text(mapping),
                                            ),
                                            ("conversion", zodiac),
                                        ),
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
        if not records:
            raise ParseError(Failure(ErrorCode.GROUP_EVIDENCE_MISSING))
        return RecordSet(tuple(records), tuple(blocks))

    def _history_blocks(
        self,
        text: str,
        source: Source,
        *,
        document_label: str,
        line_offset: int,
        document_method: DocumentMethod,
    ) -> tuple[AnchoredBlock, ...]:
        del document_method
        return anchored_history_blocks(
            text,
            source,
            document_label=document_label,
            line_offset=line_offset,
        )
