from __future__ import annotations

from v2.domain.errors import ErrorCode, Failure
from v2.domain.models import Document, Record, RecordSet, Source
from v2.parsers.registry import (
    CANONICAL_ZODIACS,
    LOCKED_MARKERS,
    ParseError,
    anchored_history_blocks,
    block_evidence_for,
    document_line_offset,
    evidence_for,
    has_data_marker,
    joined_history_line,
    normalize_document_text,
)
from v2.parsers.safety import (
    complement_candidates,
    issue_scoped_segments,
    with_complete_observed_issues,
)


class ComplementThreeParser:
    def __init__(
        self,
        parser_id: str = "complement_three",
        data_marker: str = "绝杀三肖",
    ) -> None:
        self.parser_id = str(parser_id).strip()
        self.default_data_marker = str(data_marker).strip()
        if not self.parser_id or not self.default_data_marker:
            raise ValueError("parser_id 和 data_marker 不能为空")

    def parse(
        self,
        source: Source,
        documents: tuple[Document, ...],
        issues: tuple[int, ...],
    ) -> RecordSet:
        requested = set(issues)
        data_marker = source.data_marker or self.default_data_marker
        records: list[Record] = []
        blocks = []
        for document_index, document in enumerate(documents):
            text = normalize_document_text(document.text)
            for original_block in anchored_history_blocks(
                text,
                source,
                document_label=document.label,
                line_offset=document_line_offset(document),
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
                        if not has_data_marker(
                            data_marker,
                            scoped_line,
                            block.anchor_line,
                        ):
                            continue
                        for _raw_killed, zodiac in complement_candidates(scoped_line):
                            killed = "".join(
                                animal
                                for animal in CANONICAL_ZODIACS
                                if animal not in zodiac
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
                                        method="complement_three",
                                        source_line=scoped_line,
                                        raw_issue_line=scoped_line,
                                        raw_zodiac_line=scoped_line,
                                        line_index=anchored_line.index,
                                        candidate_index_in_block=candidate_index,
                                        data_marker=data_marker,
                                        metadata=(
                                            ("killed_zodiacs", killed),
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
        return RecordSet(tuple(records), tuple(blocks))
