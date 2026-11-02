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
from v2.parsers.safety import issue_scoped_segments, with_complete_observed_issues


# 该站每期形如：`294期：【九肖中特】鼠鸡羊龙猴兔狗虎马：兔28准`
# 九肖紧跟在【九肖中特】之后、正好 9 个生肖，随后用「：」接开奖结果。
# 通用 safe_zodiac_candidates 会把开奖结果里的生肖（本例「兔」）并入，
# 变成 10 个生肖而判 INVALID_ZODIAC_COUNT，故用边界明确的正则截取。
HISTORY_PATTERN = re.compile(
    r"(?<!\d)\d{3}期\s*[：:]?\s*【九肖中特】\s*([鼠牛虎兔龙蛇马羊猴鸡狗猪]{9})"
)
ZODIACS = frozenset("鼠牛虎兔龙蛇马羊猴鸡狗猪")


class DazhiruoyuParser:
    """大智若愚：`NNN期：【九肖中特】<九肖>：<开奖结果>`，九肖无括号包裹。"""

    parser_id = "dazhiruoyu"

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
                        parser_id=self.parser_id,
                        data_marker=data_marker,
                    )
                )
                candidate_index = 0
                for anchored_line in block.lines:
                    for issue, scoped_line in issue_scoped_segments(
                        anchored_line.text
                    ):
                        match = HISTORY_PATTERN.search(scoped_line)
                        if match is None:
                            continue
                        values = tuple(match.group(1))
                        if (
                            len(values) != 9
                            or len(set(values)) != 9
                            or not all(v in ZODIACS for v in values)
                        ):
                            continue
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
                                    method="dazhiruoyu",
                                    source_line=scoped_line,
                                    raw_issue_line=scoped_line,
                                    raw_zodiac_line=match.group(1),
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
