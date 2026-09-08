from __future__ import annotations

from v2.domain.errors import ErrorCode, Failure
from v2.domain.models import Document, Record, RecordSet, Source
from v2.parsers.registry import (
    CANONICAL_ZODIACS,
    LOCKED_MARKERS,
    ParseError,
    anchored_history_blocks,
    block_evidence_for,
    complement_candidate,
    document_line_offset,
    evidence_for,
    has_data_marker,
    joined_history_line,
    line_issue,
    normalize_document_text,
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
            for block in anchored_history_blocks(
                text,
                source,
                document_label=document.label,
                line_offset=document_line_offset(document),
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
                    zodiac = complement_candidate(source_line)
                    if not zodiac:
                        continue
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
                                source_line=source_line,
                                raw_issue_line=anchored_line.text,
                                raw_zodiac_line=source_line,
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
