from __future__ import annotations

import re

from v2.domain.errors import ErrorCode, Failure
from v2.domain.models import Document, Record, RecordSet, Source
from v2.parsers.registry import (
    BRACKET_PATTERN,
    ParseError,
    anchored_history_blocks,
    block_evidence_for,
    document_line_offset,
    evidence_for,
    group_mapping_text,
    line_issue,
    normalize_document_text,
)


class ColorInfoGroupedParser:
    def parse(
        self,
        source: Source,
        documents: tuple[Document, ...],
        issues: tuple[int, ...],
    ) -> RecordSet:
        del issues
        mapping = dict(source.group_map)
        if not mapping:
            raise ParseError(Failure(ErrorCode.GROUP_EVIDENCE_MISSING))
        group_type = "".join(mapping)
        data_marker = source.data_marker or group_type
        records: list[Record] = []
        block_evidence = []
        for document_index, document in enumerate(documents):
            text = normalize_document_text(document.text)
            for block in anchored_history_blocks(
                text,
                source,
                document_label=document.label,
                line_offset=document_line_offset(document),
            ):
                block_evidence.append(
                    block_evidence_for(
                        source,
                        document,
                        block,
                        parser_id="color_info_grouped",
                        data_marker=data_marker,
                    )
                )
                candidate_index = 0
                for anchored_line in block.lines:
                    line = anchored_line.text
                    issue = line_issue(line)
                    if issue is None:
                        continue
                    group_texts = [
                        "".join(char for char in content if char in mapping)
                        for content in BRACKET_PATTERN.findall(line)
                    ]
                    if not any(group_texts):
                        before_open = re.split(r"开|開", line, maxsplit=1)[0]
                        _prefix, _separator, tail = before_open.partition("期")
                        group_texts.append(
                            "".join(char for char in tail if char in mapping)
                        )
                    for group_text in dict.fromkeys(group_texts):
                        zodiac = "".join(mapping[char] for char in group_text)
                        if len(zodiac) != 9:
                            continue
                        records.append(
                            Record(
                                issue=issue,
                                zodiacs=tuple(zodiac),
                                evidence=evidence_for(
                                    source,
                                    document,
                                    document_index,
                                    block,
                                    parser_id="color_info_grouped",
                                    method="color_info_grouped",
                                    source_line=line,
                                    raw_issue_line=line,
                                    raw_zodiac_line=line,
                                    line_index=anchored_line.index,
                                    candidate_index_in_block=candidate_index,
                                    data_marker=data_marker,
                                    metadata=(
                                        ("group_type", group_type),
                                        ("group_text", group_text),
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
        if not block_evidence:
            raise ParseError(Failure(ErrorCode.ANCHOR_MISSING))
        return RecordSet(tuple(records), tuple(block_evidence))
