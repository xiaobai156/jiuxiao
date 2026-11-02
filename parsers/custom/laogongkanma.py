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


# 老恭看马（wwlhc.com）正文「回复可见」，需登录态抓取。每期一行：
#   299 牛羊马鼠猪狗猴鸡虎
#   298 虎马牛鼠龙兔猴蛇羊 猪(08) ❌
# 期号后**没有「期」字**，九肖裸写无括号，行尾可能带开奖结果与对错标记；
# 中间还夹着「264-265 没空更新」「271 没更新」这类说明行，必须跳过而不是当数据。
ROW = re.compile(
    r"^\s*(\d{3})\s+([鼠牛虎兔龙蛇马羊猴鸡狗猪]{9})(?:\s|$)"
)
ZODIACS = frozenset("鼠牛虎兔龙蛇马羊猴鸡狗猪")


class LaogongkanmaParser:
    """老恭看马：`NNN <九肖>` 逐行提取，行尾开奖结果不得并入九肖。"""

    parser_id = "laogongkanma"

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
            # 严格满足 `NNN + 9 生肖` 的行，其它内容行一律跳过（不是边界）。
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
                block_id=f"{document.label}:laogongkanma:{start_local + offset}-{len(lines) + offset}",
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
                            method="laogongkanma",
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
