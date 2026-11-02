from __future__ import annotations

import re

from v2.domain.errors import ErrorCode, Failure
from v2.domain.models import Document, Record, RecordSet, Source
from v2.parsers.registry import (
    AnchoredBlock,
    AnchoredLine,
    ParseError,
    anchored_history_blocks,
    block_evidence_for,
    document_line_offset,
    evidence_for,
    normalize_document_text,
)


# 风铃歌（wwlhc.com，正文「回复可见」，需登录态抓取）。每期一行，格式固定：
#   304期：风铃歌 新澳九肖▂ ▂▂▃ 蛇兔龙猪马牛鼠狗羊 ▅▃▂▂ 开:??
#   303期：风铃歌 新澳九肖▂ ▂▂▃ 猴马猪鸡虎蛇狗鼠兔 ▅▃▂▂ 开:虎17
# 与老恭看马的区别：期号后带「期」字，站名与「新澳九肖」夹在期号与九肖之间，
# 九肖两侧有 ▂▃ 装饰符，行尾可能带开奖结果（开奖结果不得并入九肖）。
ROW = re.compile(
    r"^\s*(\d{3})\s*期?\s*[：:]\s*风铃歌\s*新澳九肖.*?"
    r"([鼠牛虎兔龙蛇马羊猴鸡狗猪]{9})(?=\s|$)"
)
ZODIACS = frozenset("鼠牛虎兔龙蛇马羊猴鸡狗猪")


class FenglinggeParser:
    """风铃歌：`NNN期：风铃歌 新澳九肖 … <九肖> … 开:XX` 逐行提取。"""

    parser_id = "fenglingge"

    def parse(
        self,
        source: Source,
        documents: tuple[Document, ...],
        issues: tuple[int, ...],
    ) -> RecordSet:
        del issues
        data_marker = source.data_marker or "九肖"
        records: list[Record] = []
        block_evidence = []
        for document_index, document in enumerate(documents):
            text = normalize_document_text(document.text)
            lines = text.splitlines()
            offset = document_line_offset(document)
            anchor_blocks = anchored_history_blocks(
                text,
                source,
                document_label=document.label,
                line_offset=offset,
            )
            if not anchor_blocks:
                continue
            # 正文整体是一个数据块：从首个锚点行起覆盖到文末，但配对范围只认
            # 严格满足 `NNN期：风铃歌 新澳九肖 … 9 生肖` 的行，其它内容行一律跳过。
            first = anchor_blocks[0]
            start_local = max(0, first.anchor_index - offset)
            selected: list[AnchoredLine] = []
            observed: list[int] = []
            for local in range(start_local, len(lines)):
                match = ROW.match(lines[local])
                if match is None:
                    continue
                values = match.group(2)
                if len(set(values)) != 9 or not all(v in ZODIACS for v in values):
                    continue
                observed.append(int(match.group(1)))
                selected.append(AnchoredLine(local + offset, lines[local]))
            if not selected:
                continue
            block = AnchoredBlock(
                anchor_line=first.anchor_line,
                anchor_term=first.anchor_term,
                anchor_index=first.anchor_index,
                anchor_occurrence=first.anchor_occurrence,
                start=start_local + offset,
                end=len(lines) + offset,
                block_id=f"{document.label}:fenglingge:{start_local + offset}-{len(lines) + offset}",
                lines=tuple(selected),
                observed_issues=tuple(dict.fromkeys(observed)),
            )
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
                match = ROW.match(anchored_line.text)
                if match is None:
                    continue
                values = tuple(match.group(2))
                records.append(
                    Record(
                        issue=int(match.group(1)),
                        zodiacs=values,
                        evidence=evidence_for(
                            source,
                            document,
                            document_index,
                            block,
                            parser_id=self.parser_id,
                            method="fenglingge",
                            source_line=anchored_line.text,
                            raw_issue_line=anchored_line.text,
                            raw_zodiac_line=match.group(2),
                            line_index=anchored_line.index,
                            candidate_index_in_block=candidate_index,
                            data_marker=data_marker,
                            metadata=(
                                ("source_line_index", str(anchored_line.index)),
                            ),
                        ),
                    )
                )
                candidate_index += 1
        if not block_evidence:
            raise ParseError(Failure(ErrorCode.ANCHOR_MISSING))
        return RecordSet(tuple(records), tuple(block_evidence))
