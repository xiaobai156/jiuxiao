from __future__ import annotations

from v2.domain.errors import ErrorCode, Failure
from v2.domain.models import (
    Document,
    DocumentMethod,
    Record,
    RecordSet,
    Source,
)
from v2.parsers.registry import (
    LOCKED_MARKERS,
    AnchoredBlock,
    LOCKED_MARKERS,
    ParseError,
    anchored_history_blocks,
    block_evidence_for,
    document_line_offset,
    evidence_for,
    group_candidate,
    group_mapping_text,
    has_data_marker,
    joined_history_line,
    line_issue,
    normalize_document_text,
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
            raise ParseError(
                Failure(ErrorCode.GROUP_EVIDENCE_MISSING)
            )
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
            for block in self._history_blocks(
                text,
                source,
                document_label=document.label,
                line_offset=document_line_offset(document),
                document_method=document.method,
            ):
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
                    grouped = group_candidate(source_line, mapping)
                    if grouped is None:
                        continue
                    method, _category, groups, zodiac = grouped
                    candidate_marker = data_marker if has_data_marker(
                        data_marker,
                        source_line,
                        block.anchor_line,
                    ) else groups
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
                                source_line=source_line,
                                raw_issue_line=line,
                                raw_zodiac_line=source_line,
                                line_index=line_index,
                                candidate_index_in_block=candidate_index,
                                data_marker=candidate_marker,
                                metadata=(
                                    ("group_type", group_type),
                                    ("group_text", groups),
                                    ("group_mapping", group_mapping_text(mapping)),
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
            raise ParseError(
                Failure(ErrorCode.GROUP_EVIDENCE_MISSING)
            )
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
