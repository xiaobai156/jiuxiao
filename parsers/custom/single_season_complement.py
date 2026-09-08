from __future__ import annotations

import re

from v2.domain.errors import ErrorCode, Failure
from v2.domain.models import Document, Record, RecordSet, Source
from v2.parsers.custom.common import CANONICAL_ZODIACS
from v2.parsers.registry import (
    AnchoredBlock,
    AnchoredLine,
    ParseError,
    anchored_history_blocks,
    block_evidence_for,
    document_line_offset,
    evidence_for,
    group_mapping_text,
    line_issue,
    normalize_document_text,
)


def _article_section_blocks(
    text: str,
    source: Source,
    *,
    document_label: str,
    line_offset: int,
    data_marker: str,
) -> tuple[AnchoredBlock, ...]:
    lines = normalize_document_text(text).splitlines()
    marker = source.section_marker
    if not marker or marker != data_marker:
        return ()

    for header_index, header_line in enumerate(lines):
        if marker not in header_line or line_issue(header_line) is None:
            continue
        boundary = next(
            (
                index
                for index in range(header_index + 1, len(lines))
                if "上一篇" in lines[index] or "下一篇" in lines[index]
            ),
            len(lines),
        )
        section = tuple(lines[header_index:boundary])
        if not any(source.name in line for line in section[:12]):
            continue
        if not any(
            line_issue(line) is not None
            and data_marker in line
            and any(season in line for season in "春夏秋冬")
            for line in section
        ):
            continue

        start = header_index + line_offset
        end = boundary + line_offset
        selected = tuple(
            AnchoredLine(index + line_offset, line)
            for index, line in enumerate(lines[header_index:boundary], header_index)
        )
        observed = tuple(
            dict.fromkeys(
                issue
                for anchored_line in selected
                if (issue := line_issue(anchored_line.text)) is not None
            )
        )
        return (
            AnchoredBlock(
                anchor_line=header_line,
                anchor_term=marker,
                anchor_index=start,
                anchor_occurrence=1,
                start=start,
                end=max(start + 1, end),
                block_id=f"{document_label}:single-season:{start}-{end}",
                lines=selected,
                observed_issues=observed,
            ),
        )
    return ()


class SingleSeasonComplementParser:
    def __init__(self, parser_id: str = "single_season_complement") -> None:
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
        del issues
        mapping = dict(source.group_map)
        seasons = tuple(character for character in "春夏秋冬" if character in mapping)
        if len(seasons) != 4:
            raise ParseError(Failure(ErrorCode.GROUP_EVIDENCE_MISSING))
        data_marker = source.data_marker or "绝杀一季"
        records: list[Record] = []
        blocks = []
        for document_index, document in enumerate(documents):
            text = normalize_document_text(document.text)
            line_offset = document_line_offset(document)
            blocks_for_document = _article_section_blocks(
                text,
                source,
                document_label=document.label,
                line_offset=line_offset,
                data_marker=data_marker,
            ) or anchored_history_blocks(
                text,
                source,
                document_label=document.label,
                line_offset=line_offset,
            )
            for block in blocks_for_document:
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
                for anchored_line in block.lines:
                    line_index = anchored_line.index
                    line = anchored_line.text
                    issue = line_issue(line)
                    if issue is None or data_marker not in line:
                        continue
                    before_open = re.split(r"开|開", line, maxsplit=1)[0]
                    selected = tuple(
                        season for season in seasons if season in before_open
                    )
                    if len(selected) != 1:
                        continue
                    killed_season = selected[0]
                    killed = set(mapping[killed_season])
                    zodiac = tuple(
                        animal
                        for animal in CANONICAL_ZODIACS
                        if animal not in killed
                    )
                    records.append(
                        Record(
                            issue=issue,
                            zodiacs=zodiac,
                            evidence=evidence_for(
                                source,
                                document,
                                    document_index,
                                block,
                                parser_id=self.parser_id,
                                method="single_season_complement",
                                source_line=line,
                                raw_issue_line=line,
                                raw_zodiac_line=line,
                                line_index=line_index,
                                candidate_index_in_block=candidate_index,
                                data_marker=data_marker,
                                metadata=(
                                    ("group_type", "春夏秋冬"),
                                    ("group_text", killed_season),
                                    ("killed_season", killed_season),
                                    (
                                        "group_mapping",
                                        group_mapping_text(mapping),
                                    ),
                                    ("conversion", "".join(zodiac)),
                                ),
                            ),
                        )
                    )
                    candidate_index += 1
        if not blocks:
            raise ParseError(Failure(ErrorCode.ANCHOR_MISSING))
        return RecordSet(tuple(records), tuple(blocks))
