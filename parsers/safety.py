from __future__ import annotations

import re
from dataclasses import replace
from typing import Iterable

CANONICAL_ZODIACS = "鼠牛虎兔龙蛇马羊猴鸡狗猪"
ZODIACS = frozenset(CANONICAL_ZODIACS)
ISSUE_PATTERN = re.compile(r"(?<!\d)(?P<issue>\d{3})期")
BRACKET_PATTERN = re.compile(
    r"[【《〖『「（(\[<〈{┣]([^】》〗』」）)\]>〉}┫]+)[】》〗』」）)\]>〉}┫]"
)
GROUP_CATEGORIES = {
    "琴棋书画": {"琴": "兔蛇鸡", "棋": "鼠牛狗", "书": "虎龙马", "画": "羊猴猪"},
    "梅兰菊竹": {"梅": "鼠龙猴", "兰": "兔羊猪", "菊": "牛蛇鸡", "竹": "虎马狗"},
    "东南西北": {"东": "兔虎龙", "南": "马蛇羊", "西": "鸡猴狗", "北": "鼠猪牛"},
    "春夏秋冬": {"春": "虎兔龙", "夏": "蛇马羊", "秋": "猴鸡狗", "冬": "鼠牛猪"},
    "风雨雷电": {"风": "虎兔龙", "雨": "蛇羊马", "雷": "猴狗鸡", "电": "鼠牛猪"},
}

_ZODIAC_SEPARATOR = r"\s,，、.。·•|/\\\-—_+=:：;；~～"
_ZODIAC_RUN_PATTERN = re.compile(
    rf"(?<![{CANONICAL_ZODIACS}])"
    rf"([{CANONICAL_ZODIACS}](?:[{_ZODIAC_SEPARATOR}]*[{CANONICAL_ZODIACS}]){{0,11}})"
    rf"(?![{CANONICAL_ZODIACS}])"
)
_CONTINUATION_BOUNDARIES = (
    "上一篇",
    "下一篇",
    "相关推荐",
    "广告",
    "客服",
    "免责声明",
    "版权所有",
)


def issue_scoped_segments(line: str) -> tuple[tuple[int, str], ...]:
    text = str(line)
    matches = tuple(
        (match, int(match.group("issue")))
        for match in ISSUE_PATTERN.finditer(text)
        if int(match.group("issue")) > 0
    )
    if not matches:
        return ()
    if len(matches) == 1:
        return ((matches[0][1], text),)
    prefix = text[: matches[0][0].start()]
    segments: list[tuple[int, str]] = []
    for index, (match, issue) in enumerate(matches):
        end = matches[index + 1][0].start() if index + 1 < len(matches) else len(text)
        segments.append((issue, f"{prefix}{text[match.start():end]}".strip()))
    return tuple(segments)


def observed_issues(lines: Iterable[object]) -> tuple[int, ...]:
    values: list[int] = []
    for item in lines:
        text = str(getattr(item, "text", item))
        values.extend(issue for issue, _segment in issue_scoped_segments(text))
    return tuple(dict.fromkeys(values))


def with_complete_observed_issues(block):
    return replace(
        block,
        observed_issues=tuple(
            dict.fromkeys((*block.observed_issues, *observed_issues(block.lines)))
        ),
    )


def before_opening_result(line: str) -> str:
    text = str(line)
    opening = re.search(
        rf"(?:开|開)(?=\s*(?:[:：=]|奖|獎|码|碼|特|[{CANONICAL_ZODIACS}]|\d))",
        text,
    )
    return text[: opening.start()] if opening is not None else text


def safe_zodiac_candidates(line: str) -> tuple[tuple[str, ...], ...]:
    text = before_opening_result(line)
    candidates: list[tuple[str, ...]] = []
    for bracket_text in BRACKET_PATTERN.findall(text):
        if any(
            "\u4e00" <= character <= "\u9fff" and character not in ZODIACS
            for character in bracket_text
        ):
            continue
        values = tuple(character for character in bracket_text if character in ZODIACS)
        if values and values not in candidates:
            candidates.append(values)
    for match in _ZODIAC_RUN_PATTERN.finditer(text):
        values = tuple(character for character in match.group(1) if character in ZODIACS)
        if values and values not in candidates:
            candidates.append(values)
    return tuple(candidates)


def zodiac_fields(
    text: str,
    *,
    minimum_length: int = 6,
) -> tuple[tuple[str, ...], ...]:
    if minimum_length <= 0:
        raise ValueError("minimum_length must be greater than zero")
    candidates = safe_zodiac_candidates(text)
    substantial = tuple(
        candidate for candidate in candidates if len(candidate) >= minimum_length
    )
    return substantial or candidates


def first_zodiac_field(text: str) -> tuple[str, ...]:
    fields = zodiac_fields(text)
    return fields[0] if fields else ()


def joined_issue_content(
    lines: tuple[object, ...],
    index: int,
    *,
    max_continuations: int = 12,
) -> str:
    """Join contiguous no-issue OCR lines without crossing an issue/boundary."""
    if max_continuations <= 0:
        raise ValueError("max_continuations must be greater than zero")
    if index < 0 or index >= len(lines):
        raise IndexError(index)

    current = lines[index]
    current_text = str(getattr(current, "text", current)).strip()
    if not current_text or not issue_scoped_segments(current_text):
        return current_text

    try:
        previous_index = int(getattr(current, "index"))
    except (TypeError, ValueError, AttributeError):
        previous_index = index

    parts = [current_text]
    continuations = 0
    for following in lines[index + 1 :]:
        following_text = str(getattr(following, "text", following)).strip()
        try:
            following_index = int(getattr(following, "index"))
        except (TypeError, ValueError, AttributeError):
            following_index = previous_index + 1
        if following_index != previous_index + 1:
            break
        if not following_text:
            previous_index = following_index
            continue
        if issue_scoped_segments(following_text):
            break
        if any(marker in following_text for marker in _CONTINUATION_BOUNDARIES):
            break
        parts.append(following_text)
        previous_index = following_index
        continuations += 1
        if continuations >= max_continuations:
            break
    return " ".join(parts)


def complement_candidates(line: str) -> tuple[tuple[str, str], ...]:
    text = before_opening_result(line)
    if "绝杀" not in text:
        return ()
    candidates: list[tuple[str, str]] = []
    for bracket_text in BRACKET_PATTERN.findall(text):
        killed = tuple(character for character in bracket_text if character in ZODIACS)
        if len(killed) != 3 or len(set(killed)) != 3:
            continue
        killed_text = "".join(killed)
        zodiac = "".join(
            animal for animal in CANONICAL_ZODIACS if animal not in set(killed)
        )
        candidate = (killed_text, zodiac)
        if candidate not in candidates:
            candidates.append(candidate)
    return tuple(candidates)


def group_candidates(
    line: str,
    mapping: dict[str, str] | None = None,
) -> tuple[tuple[str, str, str, str], ...]:
    text = before_opening_result(line)
    categories = (
        (("".join(mapping), mapping),)
        if mapping is not None
        else tuple(GROUP_CATEGORIES.items())
    )
    candidates: list[tuple[str, str, str, str]] = []

    def add(method: str, category: str, raw: str, values: dict[str, str]) -> None:
        groups = "".join(character for character in raw if character in values)
        if len(groups) != 3:
            return
        candidate = (method, category, groups, "".join(values[group] for group in groups))
        if candidate not in candidates:
            candidates.append(candidate)

    for bracket_text in BRACKET_PATTERN.findall(text):
        for category, values in categories:
            add("bracket_group", category, bracket_text, values)
    for category, values in categories:
        keys = "".join(re.escape(key) for key in values)
        for raw in re.findall(rf"=+\s*([{keys}]{{3}})\s*=+", text):
            add("equal_wrapped_group", category, raw, values)
        for raw in re.findall(rf"☸\s*☸\s*([{keys}]{{3}})\s*☸\s*☸", text):
            add("double_diamond_group", category, raw, values)
    tail = re.split(r"[】》〗』」）)\]>〉}┫]", text)[-1]
    for category, values in categories:
        add("tail_group", category, tail, values)
    return tuple(candidates)
