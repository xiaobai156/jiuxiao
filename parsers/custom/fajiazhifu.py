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


# 该站正文把「期号 + 栏目 + 开奖结果」与「九肖」拆成相邻两行，且九肖没有括号：
#   296期:【皇帝九肖】开:？00准
#   马牛蛇狗龙虎猴鼠兔
# 页首标题行（`296期:49姜子牙【皇帝九肖】发家致富`）同样以三位期号开头，
# 但其下一行不是纯九肖行，不会误配。
ISSUE_LINE = re.compile(r"(?<!\d)(\d{3})期")
ZODIAC_LINE = re.compile(r"^([鼠牛虎兔龙蛇马羊猴鸡狗猪]{9})$")
ZODIACS = frozenset("鼠牛虎兔龙蛇马羊猴鸡狗猪")
# 允许出现在历史中间、但不结束本栏目区块的干扰行（与 registry 的 interstitial
# 策略保持一致）：图例行、裸域名、固定说明语、纯符号分隔。
DOMAIN_LINE = re.compile(
    r"^\s*(?:www\.)?[a-z0-9](?:[a-z0-9-]*[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+"
    r"(?:\s+[\u4e00-\u9fff]{1,12})?\s*$",
    re.IGNORECASE,
)
GROUP_LEGEND_LINE = re.compile(
    r"^(?:[\u4e00-\u9fff]\s*[:：]\s*[\u4e00-\u9fff]{2,6}\s*)+$"
)
SEPARATOR_LINE = re.compile(r"^[=\-＿_—－─━~～·.。 ]{3,}$")
INTERSTITIAL_MARKERS = ("本资料最早发表", "欢迎转发+关注", "所有记录真实永不作假")


def _is_interstitial(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if SEPARATOR_LINE.match(stripped):
        return True
    if DOMAIN_LINE.match(stripped):
        return True
    if GROUP_LEGEND_LINE.match(stripped):
        return True
    return any(marker in stripped for marker in INTERSTITIAL_MARKERS)


def _is_pure_zodiac_line(line: str) -> bool:
    match = ZODIAC_LINE.match(line.strip())
    if match is None:
        return False
    values = match.group(1)
    return len(set(values)) == 9 and all(v in ZODIACS for v in values)


class FajiazhifuParser:
    """发家致富：期号行与下一行纯九肖成对提取（九肖无括号包裹）。

    区块由本解析器自建：从锚点行起，只要「期号行 + 纯九肖行」继续成立就延伸，
    遇到既非期号行、也非纯九肖行、也不属于已知干扰行时才结束。这样
    「区块边界」与「实际配对范围」是同一套事实，不存在区块偏大导致的
    跨栏目借值，也不会被通用区块构建的 12 行上限截断（那样只能解析 6 期）。
    """

    parser_id = "fajiazhifu"

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
            seen: set[tuple[int, int]] = set()
            for anchor_block in anchor_blocks:
                block = self._build_block(
                    anchor_block,
                    lines,
                    offset,
                    document_label=document.label,
                )
                if block is None:
                    continue
                key = (block.start, block.end)
                if key in seen:
                    continue
                seen.add(key)
                block_evidence.append(
                    block_evidence_for(
                        source,
                        document,
                        block,
                        parser_id=self.parser_id,
                        data_marker=data_marker,
                    )
                )
                records.extend(
                    self._records(
                        source,
                        document,
                        document_index,
                        block,
                        lines,
                        offset,
                        data_marker,
                    )
                )
        if not block_evidence:
            raise ParseError(Failure(ErrorCode.ANCHOR_MISSING))
        return RecordSet(tuple(records), tuple(block_evidence))

    @staticmethod
    def _build_block(
        anchor_block: AnchoredBlock,
        lines: list[str],
        offset: int,
        *,
        document_label: str,
    ) -> AnchoredBlock | None:
        """从锚点行起向下延伸，构造「只含本栏目历史」的区块。"""
        # anchor_index 已是文档内绝对行号；lines 是归一化后的本文件行，
        # 两者通过 offset 换算（line_offset 来自 document.metadata）。
        start = anchor_block.anchor_index - offset
        if start < 0 or start >= len(lines):
            return None
        # 先定位第一条「期号行 + 纯九肖行」配对；找不到就说明本锚点下无数据。
        first_pair = None
        for index in range(start, len(lines) - 1):
            if not ISSUE_LINE.search(lines[index]):
                continue
            if not _is_pure_zodiac_line(lines[index + 1]):
                continue
            first_pair = index
            break
        if first_pair is None:
            return None
        # 再向后延伸：允许空行与已知干扰行，遇到其它内容行即结束。
        end = first_pair
        cursor = first_pair
        while cursor < len(lines) - 1:
            current = lines[cursor]
            if ISSUE_LINE.search(current):
                if _is_pure_zodiac_line(lines[cursor + 1]):
                    end = cursor + 2
                    cursor += 2
                    continue
                # 期号行但下一行不是纯九肖：视为栏目边界
                break
            if _is_interstitial(current):
                cursor += 1
                continue
            break
        observed: list[int] = []
        selected: list[AnchoredLine] = []
        for local in range(start, end):
            line = lines[local]
            issue_match = ISSUE_LINE.search(line)
            if issue_match is not None:
                observed.append(int(issue_match.group(1)))
            if local >= first_pair:
                selected.append(AnchoredLine(local + offset, line))
        return AnchoredBlock(
            anchor_line=anchor_block.anchor_line,
            anchor_term=anchor_block.anchor_term,
            anchor_index=anchor_block.anchor_index,
            anchor_occurrence=anchor_block.anchor_occurrence,
            start=start + offset,
            end=end + offset,
            block_id=f"{document_label}:fajiazhifu:{start + offset}-{end + offset}",
            lines=tuple(selected),
            observed_issues=tuple(dict.fromkeys(observed)),
        )

    @staticmethod
    def _records(
        source: Source,
        document: Document,
        document_index: int,
        block: AnchoredBlock,
        lines: list[str],
        offset: int,
        data_marker: str,
    ) -> list[Record]:
        records: list[Record] = []
        candidate_index = 0
        start = block.start - offset
        end = block.end - offset
        for local in range(start, end - 1):
            current_text = lines[local]
            issue_match = ISSUE_LINE.search(current_text)
            if issue_match is None:
                continue
            following_text = lines[local + 1]
            if not _is_pure_zodiac_line(following_text):
                continue
            values = tuple(ZODIAC_LINE.match(following_text.strip()).group(1))
            issue = int(issue_match.group(1))
            if issue not in block.observed_issues:
                continue
            scoped_line = f"{current_text} {following_text}"
            records.append(
                Record(
                    issue=issue,
                    zodiacs=values,
                    evidence=evidence_for(
                        source,
                        document,
                        document_index,
                        block,
                        parser_id=FajiazhifuParser.parser_id,
                        method="fajiazhifu",
                        source_line=scoped_line,
                        raw_issue_line=current_text,
                        raw_zodiac_line=following_text,
                        line_index=local + offset,
                        candidate_index_in_block=candidate_index,
                        data_marker=data_marker,
                        metadata=(
                            ("source_line_index", str(local + offset)),
                            ("paired_next_line", "1"),
                        ),
                    ),
                )
            )
            candidate_index += 1
        return records
