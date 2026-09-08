from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Protocol

from v2.domain.errors import ErrorCode, Failure
from v2.domain.models import (
    BlockEvidence,
    Document,
    DocumentMethod,
    Evidence,
    RecordSet,
    Source,
    SourceRole,
)


CANONICAL_ZODIACS = "鼠牛虎兔龙蛇马羊猴鸡狗猪"
ZODIACS = frozenset(CANONICAL_ZODIACS)
ISSUE_PATTERN = re.compile(r"(?<!\d)(?P<issue>\d{3})期")
BRACKET_PATTERN = re.compile(
    r"[【《〖『「（(\[<〈{┣]([^】》〗』」）)\]>〉}┫]+)[】》〗』」）)\]>〉}┫]"
)
LOCKED_MARKERS = ("购买后可查看", "锁定内容", "隐藏内容", "付费可见")
GROUP_CATEGORIES = {
    "琴棋书画": {
        "琴": "兔蛇鸡",
        "棋": "鼠牛狗",
        "书": "虎龙马",
        "画": "羊猴猪",
    },
    "梅兰菊竹": {
        "梅": "鼠龙猴",
        "兰": "兔羊猪",
        "菊": "牛蛇鸡",
        "竹": "虎马狗",
    },
    "东南西北": {
        "东": "兔虎龙",
        "南": "马蛇羊",
        "西": "鸡猴狗",
        "北": "鼠猪牛",
    },
    "春夏秋冬": {
        "春": "虎兔龙",
        "夏": "蛇马羊",
        "秋": "猴鸡狗",
        "冬": "鼠牛猪",
    },
    "风雨雷电": {
        "风": "虎兔龙",
        "雨": "蛇羊马",
        "雷": "猴狗鸡",
        "电": "鼠牛猪",
    },
}
HISTORY_SEPARATOR_PATTERN = re.compile(r"[=\-＿_—－─━~～·.。 ]{3,}")
CONTINUATION_NOISE = (
    "广告",
    "客服",
    "通知",
    "免责",
    "版权所有",
    "上一篇",
    "下一篇",
    "相关推荐",
)
HISTORY_INTERSTITIAL_MARKERS = (
    "本资料最早发表",
    "欢迎转发+关注",
    "所有记录真实永不作假",
)


@dataclass(frozen=True, slots=True)
class AnchoredLine:
    index: int
    text: str


@dataclass(frozen=True, slots=True)
class AnchoredBlock:
    anchor_line: str
    anchor_term: str
    anchor_index: int
    anchor_occurrence: int
    start: int
    end: int
    block_id: str
    lines: tuple[AnchoredLine, ...]
    observed_issues: tuple[int, ...]


def split_cyclic_history_lines(
    block: AnchoredBlock,
    *,
    minimum_records: int = 20,
) -> tuple[tuple[AnchoredLine, ...], ...]:
    """Split a long topic history at the explicit 001/365 cycle seam.

    This helper is intentionally opt-in.  Ordinary anchored blocks keep their
    existing semantics, including rejecting same-issue conflicts outside the
    direction window.  The topic-specific parser uses this only when both
    resulting runs are long enough to be a real circular history rather than a
    short duplicate snippet.
    """
    if minimum_records <= 0:
        raise ValueError("minimum_records 必须大于 0")

    candidate_positions: list[tuple[int, int]] = []
    for position, line in enumerate(block.lines):
        issue = line_issue(line.text)
        if issue is None or not _looks_like_history_candidate(line.text):
            continue
        candidate_positions.append((position, issue))
    if len(candidate_positions) < minimum_records * 2:
        return (block.lines,)

    boundaries: list[int] = []
    for previous, current in zip(candidate_positions, candidate_positions[1:]):
        previous_position, previous_issue = previous
        current_position, current_issue = current
        if (previous_issue, current_issue) in ((1, 365), (365, 1)):
            boundaries.append(current_position)
    if not boundaries:
        return (block.lines,)

    starts = [0, *boundaries]
    ends = [*boundaries, len(block.lines)]
    segments = tuple(
        tuple(block.lines[start:end])
        for start, end in zip(starts, ends)
        if end > start
    )
    if len(segments) < 2:
        return (block.lines,)
    if any(
        sum(
            1
            for line in segment
            if line_issue(line.text) is not None
            and _looks_like_history_candidate(line.text)
        )
        < minimum_records
        for segment in segments
    ):
        return (block.lines,)
    return segments


class Parser(Protocol):
    def parse(
        self,
        source: Source,
        documents: tuple[Document, ...],
        issues: tuple[int, ...],
    ) -> RecordSet: ...


class ParseError(ValueError):
    def __init__(self, failure: Failure) -> None:
        super().__init__(failure.code.value)
        self.failure = failure


class ParserRegistry:
    def __init__(self) -> None:
        self._parsers: dict[str, Parser] = {}

    def register(self, key: str, parser: Parser) -> None:
        normalized = str(key).strip()
        if not normalized:
            raise ValueError("parser key 不能为空")
        if normalized in self._parsers:
            raise ValueError(f"parser 已注册: {normalized}")
        self._parsers[normalized] = parser

    def resolve(self, key: str) -> Parser:
        normalized = str(key).strip()
        if normalized not in self._parsers:
            raise KeyError(normalized)
        return self._parsers[normalized]


def normalize_document_text(value: str) -> str:
    text = str(value).replace("\xa0", " ")
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(?:p|div|li|tr|h[1-6])>", "\n", text)
    text = re.sub(r"</?[A-Za-z][^>]*>", " ", text)
    text = html.unescape(text)
    lines = [
        re.sub(r"\s+", " ", line).strip()
        for line in text.splitlines()
    ]
    return "\n".join(line for line in lines if line)


def anchor_terms(source: Source) -> tuple[str, ...]:
    if source.section_marker:
        return (source.section_marker,)
    return tuple(dict.fromkeys((source.name, *source.aliases)))


def line_issue(line: str) -> int | None:
    match = ISSUE_PATTERN.search(line)
    return int(match.group("issue")) if match else None


def line_has_anchor(line: str, source: Source) -> bool:
    return any(term and term in line for term in anchor_terms(source))


def document_has_anchor(text: str, source: Source) -> bool:
    return any(term and term in text for term in anchor_terms(source))


def matched_anchor(line: str, source: Source) -> str:
    return next(
        (term for term in anchor_terms(source) if term and term in line),
        "",
    )


def effective_source_policy(source: Source) -> tuple[str, ...]:
    if source.source_policy:
        return source.source_policy
    if source.parser == "image_ocr":
        return (DocumentMethod.IMAGE_OCR.value,)
    if source.fetcher == "static_page":
        return (DocumentMethod.STATIC_PAGE.value,)
    if source.fetcher == "dynamic_article":
        return (
            DocumentMethod.DYNAMIC_API.value,
            DocumentMethod.BROWSER_DOM.value,
        )
    if source.fetcher == "liuiuqu":
        return (DocumentMethod.DYNAMIC_API.value,)
    return (DocumentMethod.BROWSER_DOM.value,)


def document_authority(
    source: Source,
    document: Document,
) -> tuple[SourceRole, int]:
    policy = effective_source_policy(source)
    try:
        priority = policy.index(document.method.value)
    except ValueError:
        return SourceRole.UNAPPROVED, len(policy) + 100
    return (
        SourceRole.PRIMARY if priority == 0 else SourceRole.FALLBACK,
        priority,
    )


def anchored_history_blocks(
    text: str,
    source: Source,
    *,
    document_label: str,
    line_offset: int = 0,
    exact_anchor: bool = False,
) -> tuple[AnchoredBlock, ...]:
    lines = text.splitlines()
    matches: list[tuple[int, str, str]] = []
    for index, line in enumerate(lines):
        term = matched_anchor(line, source)
        if not term:
            continue
        if exact_anchor and line != term:
            continue
        matches.append((index, line, term))
    if not matches:
        return ()

    header_matches = tuple(
        match
        for match in matches
        if not _looks_like_history_at(lines, match[0])
    )
    anchors = header_matches or (matches[0],)
    blocks: list[AnchoredBlock] = []
    for occurrence, (anchor_index, anchor_line, anchor_term) in enumerate(
        anchors,
        start=1,
    ):
        natural_end = (
            anchors[occurrence][0]
            if occurrence < len(anchors)
            else len(lines)
        )
        selected: list[AnchoredLine] = []
        observed: list[int] = []
        found_candidate = False
        end = natural_end
        for index in range(anchor_index, natural_end):
            line = lines[index]
            issue = line_issue(line)
            if issue is not None:
                observed.append(issue)
                selected.append(
                    AnchoredLine(index + line_offset, line)
                )
                found_candidate = (
                    found_candidate or _looks_like_history_candidate(line)
                )
                continue
            if index == anchor_index:
                continue
            if not found_candidate:
                if (
                    index > 0
                    and line_issue(lines[index - 1]) is not None
                    and _is_history_continuation(line, lines[index - 1])
                ):
                    selected.append(
                        AnchoredLine(index + line_offset, line)
                    )
                    found_candidate = _looks_like_history_candidate(
                        f"{lines[index - 1]} {line}"
                    )
                    continue
                if index - anchor_index >= 12:
                    end = index
                    break
                continue
            previous = lines[index - 1] if index > 0 else ""
            if _is_history_continuation(line, previous):
                selected.append(
                    AnchoredLine(index + line_offset, line)
                )
                continue
            if any(marker in line for marker in HISTORY_INTERSTITIAL_MARKERS):
                continue
            if not line or HISTORY_SEPARATOR_PATTERN.fullmatch(line):
                continue
            if _looks_like_history_candidate(line):
                continue
            end = index
            break

        absolute_anchor = anchor_index + line_offset
        absolute_start = anchor_index + line_offset
        absolute_end = max(absolute_start + 1, end + line_offset)
        blocks.append(
            AnchoredBlock(
                anchor_line=anchor_line,
                anchor_term=anchor_term,
                anchor_index=absolute_anchor,
                anchor_occurrence=occurrence,
                start=absolute_start,
                end=absolute_end,
                block_id=(
                    f"{document_label}:{occurrence}:"
                    f"{absolute_start}-{absolute_end}"
                ),
                lines=tuple(selected),
                observed_issues=tuple(dict.fromkeys(observed)),
            )
        )
    return tuple(blocks)


def anchored_history_lines(text: str, source: Source) -> tuple[AnchoredLine, ...]:
    selected: dict[int, AnchoredLine] = {}
    for block in anchored_history_blocks(
        text,
        source,
        document_label="document",
    ):
        for line in block.lines:
            selected[line.index] = line
    return tuple(selected[index] for index in sorted(selected))


def _looks_like_history_candidate(line: str) -> bool:
    if group_candidate(line) is not None or complement_candidate(line):
        return True
    return any(len(values) == 9 for values in zodiac_candidates(line))


def _looks_like_history_at(lines: list[str], index: int) -> bool:
    line = lines[index]
    if _looks_like_history_candidate(line):
        return True
    if (
        line_issue(line) is not None
        and index + 1 < len(lines)
        and line_issue(lines[index + 1]) is None
    ):
        return _looks_like_history_candidate(
            f"{line} {lines[index + 1]}"
        )
    return False


def has_data_marker(marker: str, *values: str) -> bool:
    normalized_marker = _normalize_data_marker(marker)
    for value in values:
        normalized_value = _normalize_data_marker(value)
        if normalized_marker in normalized_value:
            return True
        if (
            len(normalized_marker) == 4
            and len(set(normalized_marker)) == 4
            and all(character in normalized_value for character in normalized_marker)
        ):
            return True
    return False


def candidate_has_data_semantic(
    source: Source,
    marker: str,
    *,
    directory_anchor: str,
    actual_anchor_line: str,
    candidate_lines: tuple[str, ...],
) -> bool:
    if has_data_marker(marker, *candidate_lines):
        return True

    identity_terms = tuple(
        dict.fromkeys(
            term
            for term in (directory_anchor, source.name, *source.aliases)
            if term
        )
    )
    anchor_remainder = actual_anchor_line
    for term in identity_terms:
        anchor_remainder = anchor_remainder.replace(term, "")
    if has_data_marker(marker, anchor_remainder):
        return True

    if not source.section_marker or directory_anchor != source.section_marker:
        return False
    section_semantic = source.section_marker
    for term in (source.name, *source.aliases):
        if term:
            section_semantic = section_semantic.replace(term, "")
    return has_data_marker(marker, section_semantic)


def _normalize_data_marker(value: str) -> str:
    return (
        str(value)
        .replace("⑨肖", "九肖")
        .replace("⒐肖", "九肖")
        .replace("9肖", "九肖")
        .replace("绝杀③肖", "绝杀三肖")
        .replace("绝杀3肖", "绝杀三肖")
    )


def _is_history_continuation(line: str, previous: str = "") -> bool:
    if not line or any(marker in line for marker in CONTINUATION_NOISE):
        return False
    if previous and _looks_like_history_candidate(previous):
        return False
    candidate = f"{previous} {line}" if previous else line
    return _looks_like_history_candidate(candidate)


def joined_history_line(
    lines: tuple[AnchoredLine, ...],
    index: int,
) -> str:
    current = lines[index]
    if _looks_like_history_candidate(current.text):
        return current.text
    if index + 1 >= len(lines):
        return current.text
    following = lines[index + 1]
    if (
        following.index == current.index + 1
        and line_issue(following.text) is None
    ):
        return f"{current.text} {following.text}"
    return current.text


def group_candidate(
    line: str,
    mapping: dict[str, str] | None = None,
) -> tuple[str, str, str, str] | None:
    before_open = re.split(r"开|開", line, maxsplit=1)[0]
    categories = (
        (("".join(mapping), mapping),)
        if mapping is not None
        else tuple(GROUP_CATEGORIES.items())
    )
    for bracket_text in reversed(BRACKET_PATTERN.findall(before_open)):
        for category, values in categories:
            candidate = _mapped_group_candidate(bracket_text, values)
            if candidate is not None:
                groups, zodiac = candidate
                return "bracket_group", category, groups, zodiac
    for category, values in categories:
        keys = "".join(re.escape(key) for key in values)
        matches = re.findall(rf"=+\s*([{keys}]{{3}})\s*=+", before_open)
        if matches:
            groups = matches[-1]
            zodiac = "".join(values[group] for group in groups)
            return "equal_wrapped_group", category, groups, zodiac
    for category, values in categories:
        keys = "".join(re.escape(key) for key in values)
        matches = re.findall(
            rf"☸\s*☸\s*([{keys}]{{3}})\s*☸\s*☸",
            before_open,
        )
        if matches:
            groups = matches[-1]
            zodiac = "".join(values[group] for group in groups)
            return "double_diamond_group", category, groups, zodiac
    tail = re.split(r"[】》〗』」）)\]>〉}┫]", before_open)[-1]
    for category, values in categories:
        candidate = _mapped_group_candidate(tail, values)
        if candidate is not None:
            groups, zodiac = candidate
            return "tail_group", category, groups, zodiac
    return None


def group_mapping_text(mapping: dict[str, str]) -> str:
    return "|".join(f"{key}={value}" for key, value in mapping.items())


def _mapped_group_candidate(
    value: str,
    mapping: dict[str, str],
) -> tuple[str, str] | None:
    groups = "".join(character for character in value if character in mapping)
    if len(groups) != 3:
        return None
    return groups, "".join(mapping[group] for group in groups)


def complement_candidate(line: str) -> str:
    before_open = re.split(r"开|開", line, maxsplit=1)[0]
    if "绝杀" not in before_open:
        return ""
    for bracket_text in reversed(BRACKET_PATTERN.findall(before_open)):
        killed = tuple(
            character for character in bracket_text if character in ZODIACS
        )
        if len(killed) == 3 and len(set(killed)) == 3:
            return "".join(
                zodiac for zodiac in CANONICAL_ZODIACS if zodiac not in killed
            )
    return ""


def zodiac_candidates(line: str) -> tuple[tuple[str, ...], ...]:
    candidates: list[tuple[str, ...]] = []
    for bracket_text in BRACKET_PATTERN.findall(line):
        if any(
            "\u4e00" <= character <= "\u9fff"
            and character not in ZODIACS
            for character in bracket_text
        ):
            continue
        values = tuple(char for char in bracket_text if char in ZODIACS)
        if values and values not in candidates:
            candidates.append(values)
    before_open = re.split(r"开|開", line, maxsplit=1)[0]
    for match in re.finditer(
        rf"(?<![{CANONICAL_ZODIACS}])([{CANONICAL_ZODIACS}]{{9}})(?![{CANONICAL_ZODIACS}])",
        before_open,
    ):
        values = tuple(match.group(1))
        if values not in candidates:
            candidates.append(values)
    return tuple(candidates)


def metadata_for(
    document_index: int,
    line_index: int,
    document_metadata: tuple[tuple[str, str], ...] = (),
) -> tuple[tuple[str, str], ...]:
    reserved = {"document_index", "line_index"}
    return (
        ("document_index", str(document_index)),
        ("line_index", str(line_index)),
        *(
            (key, value)
            for key, value in document_metadata
            if key not in reserved
        ),
    )


def document_line_offset(document: Document) -> int:
    raw = dict(document.metadata).get("line_offset", "0")
    try:
        offset = int(raw)
    except ValueError as exc:
        raise ParseError(
            Failure(
                code=ErrorCode.SOURCE_UNTRUSTED,
                detail="invalid document line_offset",
            )
        ) from exc
    if offset < 0:
        raise ParseError(
            Failure(
                code=ErrorCode.SOURCE_UNTRUSTED,
                detail="invalid document line_offset",
            )
        )
    return offset


def block_evidence_for(
    source: Source,
    document: Document,
    block: AnchoredBlock,
    *,
    parser_id: str,
    data_marker: str,
) -> BlockEvidence:
    role, priority = document_authority(source, document)
    return BlockEvidence(
        document_label=document.label,
        document_url=document.url,
        document_method=document.method.value,
        directory_anchor=block.anchor_term,
        actual_anchor_line=block.anchor_line,
        anchor_index=block.anchor_index,
        anchor_occurrence=block.anchor_occurrence,
        block_id=block.block_id,
        block_start=block.start,
        block_end=block.end,
        source_role=role,
        source_priority=priority,
        parser_id=parser_id,
        data_marker=data_marker,
        observed_issues=block.observed_issues,
    )


def evidence_for(
    source: Source,
    document: Document,
    document_index: int,
    block: AnchoredBlock,
    *,
    parser_id: str,
    method: str,
    source_line: str,
    raw_issue_line: str,
    raw_zodiac_line: str,
    line_index: int,
    candidate_index_in_block: int,
    data_marker: str,
    metadata: tuple[tuple[str, str], ...] = (),
) -> Evidence:
    role, priority = document_authority(source, document)
    return Evidence(
        method=method,
        source_line=source_line,
        directory_anchor=block.anchor_term,
        document_label=document.label,
        metadata=(
            *metadata_for(
                document_index,
                line_index,
                document.metadata,
            ),
            *metadata,
        ),
        document_url=document.url,
        document_method=document.method.value,
        actual_anchor_line=block.anchor_line,
        anchor_index=block.anchor_index,
        anchor_occurrence=block.anchor_occurrence,
        block_id=block.block_id,
        block_start=block.start,
        block_end=block.end,
        candidate_index_in_block=candidate_index_in_block,
        source_role=role,
        source_priority=priority,
        parser_id=parser_id,
        raw_issue_line=raw_issue_line,
        raw_zodiac_line=raw_zodiac_line,
        data_marker=data_marker,
    )
