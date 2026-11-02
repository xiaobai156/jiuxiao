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


# 该站正文把「期号 + 栏目」与「九肖」拆成相邻两行：
#   296期：枯木逢春九肖
#   【牛猪马虎鸡鼠猴狗羊】开？00准
# 锚点「雷霆大怒」只出现在页首标题行（`296期雷霆大怒【枯木逢春九肖】准`），
# 通用解析的锚点/跨行拼接拿不到稳定区块，故用显式成对正则逐期截取。
ISSUE_LINE = re.compile(r"(?<!\d)(\d{3})期\s*[：:]\s*\S*九肖")
ZODIAC_LINE = re.compile(r"[【《]([鼠牛虎兔龙蛇马羊猴鸡狗猪]{9})[】》]")
ZODIACS = frozenset("鼠牛虎兔龙蛇马羊猴鸡狗猪")


class LeitingdanuParser:
    """雷霆大怒：期号行与九肖行相邻两行，需成对提取。"""

    parser_id = "leitingdanu"

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
                # 只在区块声明的行号范围内配对，禁止扫全页：
                # 否则会取到同页其它栏目的期号 ⇒ 跨栏目借值。
                for index in range(block.start, block.end):
                    local = index - offset
                    if local < 0 or local + 1 >= len(lines):
                        continue
                    issue_match = ISSUE_LINE.search(lines[local])
                    if issue_match is None:
                        continue
                    zodiac_match = ZODIAC_LINE.search(lines[local + 1])
                    if zodiac_match is None:
                        continue
                    values = tuple(zodiac_match.group(1))
                    if (
                        len(values) != 9
                        or len(set(values)) != 9
                        or not all(v in ZODIACS for v in values)
                    ):
                        continue
                    issue = int(issue_match.group(1))
                    if issue not in block.observed_issues:
                        continue
                    scoped_line = f"{lines[local]} {lines[local + 1]}"
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
                                method="leitingdanu",
                                source_line=scoped_line,
                                raw_issue_line=lines[local],
                                raw_zodiac_line=lines[local + 1],
                                line_index=index,
                                candidate_index_in_block=candidate_index,
                                data_marker=data_marker,
                                metadata=(
                                    ("source_line_index", str(index)),
                                    ("paired_next_line", "1"),
                                ),
                            ),
                        )
                    )
                    candidate_index += 1
        if not block_evidence:
            raise ParseError(Failure(ErrorCode.ANCHOR_MISSING))
        return RecordSet(tuple(records), tuple(block_evidence))
