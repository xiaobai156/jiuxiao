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
from v2.parsers.safety import with_complete_observed_issues


# 该站把「期号 + 栏目 + 开奖结果」与「九肖」拆成相隔一个空行的两行，
# 九肖用【】/《》包裹：
#   298期九肖中特开？00准
#   （空行）
#   【狗猪虎羊鼠牛兔龙鸡】
# 页首标题行（`298期:49高手精选【九肖中特】太平盛世`）与作者行各命中一次锚点，
# 通用解析会把区块切碎并丢期，故用显式配对逐期截取。
ISSUE_LINE = re.compile(r"(?<!\d)(\d{3})期\s*\S*九肖中特")
ZODIAC_LINE = re.compile(r"^[【《]([鼠牛虎兔龙蛇马羊猴鸡狗猪]{9})[】》]$")
ZODIACS = frozenset("鼠牛虎兔龙蛇马羊猴鸡狗猪")
# 期号行与九肖行之间最多允许的空行数（实测为 1 行空行）
MAX_GAP_LINES = 3


class TaipingshengshiParser:
    """太平盛世：期号行与「空行 + 带括号九肖行」成对提取。"""

    parser_id = "taipingshengshi"

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
            lines = text.splitlines()
            offset = document_line_offset(document)
            raw_blocks = anchored_history_blocks(
                text,
                source,
                document_label=document.label,
                line_offset=offset,
            )
            for raw_block in raw_blocks:
                block = with_complete_observed_issues(raw_block)
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
                # 只在区块声明的行号范围内配对，禁止把区块扩张到整页：
                # 否则 observed_issues 会吞进同页其它栏目的期号 ⇒ 跨栏目借值。
                for index in range(block.start, block.end):
                    local = index - offset
                    if local < 0 or local >= len(lines):
                        continue
                    issue_match = ISSUE_LINE.search(lines[local])
                    if issue_match is None:
                        continue
                    issue = int(issue_match.group(1))
                    if issue not in block.observed_issues:
                        continue
                    values: tuple[str, ...] | None = None
                    zodiac_line = ""
                    zodiac_index = -1
                    for gap in range(1, MAX_GAP_LINES + 1):
                        probe = local + gap
                        if probe >= len(lines):
                            break
                        candidate = lines[probe].strip()
                        if not candidate:
                            continue
                        match = ZODIAC_LINE.match(candidate)
                        if match is not None:
                            values = tuple(match.group(1))
                            zodiac_line = candidate
                            zodiac_index = index + gap
                        break
                    if values is None:
                        continue
                    if (
                        len(values) != 9
                        or len(set(values)) != 9
                        or not all(v in ZODIACS for v in values)
                    ):
                        continue
                    scoped_line = f"{lines[local]} {zodiac_line}"
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
                                method="taipingshengshi",
                                source_line=scoped_line,
                                raw_issue_line=lines[local],
                                raw_zodiac_line=zodiac_line,
                                line_index=index,
                                candidate_index_in_block=candidate_index,
                                data_marker=data_marker,
                                metadata=(
                                    ("source_line_index", str(index)),
                                    ("paired_next_line", "1"),
                                    ("zodiac_line_index", str(zodiac_index)),
                                ),
                            ),
                        )
                    )
                    candidate_index += 1
        if not block_evidence:
            raise ParseError(Failure(ErrorCode.ANCHOR_MISSING))
        return RecordSet(tuple(records), tuple(block_evidence))
