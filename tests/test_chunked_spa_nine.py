"""分块型纯 JS 站点（密密麻麻）的抓取层与解析器回归测试。

站点特征：页面只有一个约 1.4KB 的空壳，数据在 <script src=".../js-<site>-<id>"> 指向的
分块里，分块内容为多条 base64（raw deflate 压缩）HTML 片段；分组字写成「风雷云雨」，
其中「云」与项目权威体系的「电」同席位。
"""

from __future__ import annotations

import base64
import importlib.util
import sys
import zlib
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if "v2" not in sys.modules:
    specification = importlib.util.spec_from_file_location(
        "v2",
        PROJECT_ROOT / "__init__.py",
        submodule_search_locations=[str(PROJECT_ROOT)],
    )
    assert specification is not None and specification.loader is not None
    package = importlib.util.module_from_spec(specification)
    sys.modules["v2"] = package
    specification.loader.exec_module(package)

from v2.domain.errors import ErrorCode  # noqa: E402
from v2.domain.models import DocumentMethod, Position, Source  # noqa: E402
from v2.fetchers.chunked_spa import (  # noqa: E402
    ChunkedSpaFetcher,
    _normalize_group_notation,
    chunk_sources,
    inflate_blobs,
)
from v2.fetchers.registry import FetchError, FetchRequest  # noqa: E402
from v2.parsers.factory import build_parser_registry  # noqa: E402
from v2.validator import ValidationError, Validator  # noqa: E402

SHELL = (
    "<!doctype html><html><head>"
    '<script src="https://api.kxusu.com/assets/js/runtime.js?v=0.33d"></script>'
    '<script src="https://api.kxusu.com/js-153-10691?v=09184"></script>'
    "</head><body></body></html>"
)
MAPPING = (
    ("风", "虎兔龙"),
    ("雨", "蛇羊马"),
    ("雷", "猴狗鸡"),
    ("电", "鼠牛猪"),
)
# 站点原文写法：风雷云雨（云＝项目体系的「电」）
# 结构：数据分块按「栏目锚点行 → 期号由新到旧」排列（最新期在锚点之后 → 方向 top）
# 注：真实分块中可用的锚点行是分组栏目名「风雷云雨」；站名本身不出现在数据里。
ANCHOR_LINE = '<div class="column-title">风雷电雨</div><br>'
LINES = (
    "261期:风雷云雨╠雨风雷╣开:發00准",
    "260期:风雷云雨╠雷云风╣开:猪20错",
    "259期:风雷云雨╠风雷云╣开:鸡22准",
    "258期:风雷云雨╠雨风雷╣开:鸡46错",
    "257期:风雷云雨╠风雷雨╣开:鼠07准",
    "256期:风雷云雨╠雷风云╣开:牛30错",
)
EXPECTED = {
    261: "蛇羊马虎兔龙猴狗鸡",
    260: "猴狗鸡鼠牛猪虎兔龙",
    259: "虎兔龙猴狗鸡鼠牛猪",
    258: "蛇羊马虎兔龙猴狗鸡",
    257: "虎兔龙猴狗鸡蛇羊马",
}


def _fragment(line: str) -> str:
    if "期" not in line:
        return f'<div class="title">{line}</div>'
    groups = line.split("╠")[1].split("╣")[0]
    tail = line.split("开:")[1]
    return (
        f"{line.split('期')[0]}期:"
        '<font color="#1140cb">风雷云雨</font>╠'
        f'<font color="#FF0000">{groups}</font>╣开:{tail}<br>'
    )


def build_payload() -> str:
    """把锚点与各期压成多条 base64（raw deflate），模拟真实分块结构。"""
    blobs = []
    compressed = zlib.compress(ANCHOR_LINE.encode("utf-8"))[2:-4]
    blobs.append(base64.b64encode(compressed).decode("ascii"))
    for line in LINES:
        compressed = zlib.compress(_fragment(line).encode("utf-8"))[2:-4]
        blobs.append(base64.b64encode(compressed).decode("ascii"))
    # 掺入不能解压的噪声，验证会被跳过
    blobs.append("A" * 80)
    return "var a='" + "';var b='".join(blobs) + "';"


class _FakeHttp:
    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    async def get(self, url, *, timeout_ms, headers):  # noqa: ANN001
        from v2.fetchers.registry import HttpResponse

        self.calls.append(url)
        if url in self.responses:
            return HttpResponse(status=200, text=self.responses[url], url=url)
        return HttpResponse(status=404, text="", url=url)


class _StaticGroupedParser:
    """让分块文档也能通过解析：委托真实 group_map 解析器。"""


def _source(parser: str = "chunked_grouped") -> Source:
    return Source(
        name="密密麻麻",
        url="https://dh81162.0gln642de8.cyou/TwldclGzSC.html",
        position=Position.TOP,
        # 数据分块中实际存在的栏目锚点（站名本身不在数据里）；
        # 解析器会把站点的「云」归一为「电」，故锚点也按归一后的写法给出
        section_marker="风雷电雨",
        fetcher="chunked_spa",
        parser=parser,
        api_url="https://api.kxusu.com",
        group_map=MAPPING,
        # 页面实际显示为「风雷电雨」；校验器对 4 字数据标记按子序列比较顺序差异
        data_marker="风雷电雨",
    )


def test_shell_chunk_id_and_url_are_detected() -> None:
    chunks = chunk_sources(SHELL)
    assert len(chunks) == 1
    chunk_id, path = chunks[0]
    assert chunk_id == "10691"
    assert path == "/js-153-10691"


def test_inflate_blobs_skips_undecodable_noise() -> None:
    text = inflate_blobs(build_payload())
    assert "261期" in text
    # 归一化后分组写成紧邻三字，HTML 标签与 <br> 均被处理
    assert "╠雨风雷╣" in text
    assert "<font" not in text


def test_inflate_blobs_returns_empty_for_garbage() -> None:
    assert inflate_blobs("not-base64-and-no-blobs") == ""


def _escaped_payload() -> str:
    """分块是 JS 字符串：Base64 中的 "/" 被转义成 "\\/"，必须能还原。"""
    blobs = []
    for line in LINES:
        compressed = zlib.compress(ANCHOR_LINE.encode("utf-8"))[2:-4]
        blobs.append(base64.b64encode(compressed).decode("ascii"))
        break
    for line in LINES:
        compressed = zlib.compress(_fragment(line).encode("utf-8"))[2:-4]
        blobs.append(base64.b64encode(compressed).decode("ascii"))
    joined = "';var b='".join(blobs)
    return joined.replace("/", "\\/")


def test_inflate_blobs_restores_escaped_slashes() -> None:
    """\\/ 转义不还原会把 Base64 截断，导致解压片段缺失。"""
    text = inflate_blobs(_escaped_payload())
    assert "261期" in text
    # 未还原转义时，含 "/" 的串会被截断，解出的期数明显更少
    assert sum(1 for line in LINES if line.split("期")[0] in text) == len(LINES)


def test_escaped_slash_is_not_silently_dropped() -> None:
    """转义串在还原前不应被当成完整 Base64 直接解压出错误内容。"""
    escaped = build_payload().replace("/", "\\/")
    restored = inflate_blobs(escaped)
    assert "261期" in restored
    assert "╠雨风雷╣" in restored


@pytest.mark.parametrize(
    ("raw", "expected"),
    (
        ("╠琴肖,书肖,画肖╣", "╠琴书画╣"),
        ("╠琴肖 书肖 画肖╣", "╠琴书画╣"),
        ("╠琴肖,画肖,棋肖╣", "╠琴画棋╣"),
        ("╠画棋书╣", "╠画棋书╣"),
    ),
)
def test_group_notation_is_normalized(raw: str, expected: str) -> None:
    line = f"261期琴棋书画{raw}开:發00准"
    assert expected in _normalize_group_notation(line)


def test_group_notation_keeps_unrelated_lines_untouched() -> None:
    other = "作者:自求多福更新:1789681349000"
    assert _normalize_group_notation(other) == other


def test_normalized_group_notation_is_parsable() -> None:
    """归一化后的分组必须能被既有解析器识别（不改 parsers）。"""
    from v2.parsers.safety import group_candidates
    from v2.parsers.registry import normalize_document_text

    mapping = {"琴": "兔蛇鸡", "棋": "鼠牛狗", "书": "虎龙马", "画": "羊猴猪"}
    raw = '261期<font color="#1140cb">琴棋书画</font>╠<font>画肖,<span>棋肖</span>,书肖</font>╣开:發00准'
    normalized = normalize_document_text(_normalize_group_notation(raw))
    candidates = group_candidates(normalized, mapping)
    assert candidates, "归一化后应能识别分组"
    method, category, groups, zodiac = candidates[0]
    assert groups == "画棋书"
    assert zodiac == "羊猴猪鼠牛狗虎龙马"
    assert category == "".join(mapping)


async def _fetch(source: Source):
    payload = build_payload()
    http = _FakeHttp(
        {
            source.url: SHELL,
            "https://api.kxusu.com/js-153-10691": payload,
        }
    )
    return await ChunkedSpaFetcher(http).fetch(source, FetchRequest((261,)))


def test_fetcher_returns_chunked_document() -> None:
    import asyncio

    documents = asyncio.run(_fetch(_source()))
    assert len(documents) == 1
    document = documents[0]
    assert document.method is DocumentMethod.CHUNKED_DATA
    assert document.label == "chunk:10691"
    assert dict(document.metadata)["chunk_id"] == "10691"
    assert "261期" in document.text


def test_fetcher_fails_when_chunk_missing() -> None:
    import asyncio

    source = _source()
    http = _FakeHttp({source.url: SHELL})
    with pytest.raises(FetchError) as captured:
        asyncio.run(ChunkedSpaFetcher(http).fetch(source, FetchRequest((261,))))
    assert captured.value.failure.code is ErrorCode.FETCH_FAILED


def test_parser_maps_site_variant_and_verifies_261() -> None:
    import asyncio

    source = _source()
    documents = asyncio.run(_fetch(source))
    parser = build_parser_registry().resolve("chunked_grouped")
    parsed = parser.parse(source, documents, (261,))
    records = [r for r in parsed.records if r.issue == 261]
    assert records
    assert records[0].zodiac_text == EXPECTED[261]

    verified = Validator().validate(source, parsed, (261,))
    record = verified.history.records[0]
    assert record.zodiac_text == EXPECTED[261]
    assert record.evidence.document_method == DocumentMethod.CHUNKED_DATA.value
    assert dict(record.evidence.metadata)["group_text"] == "雨风雷"


@pytest.mark.parametrize("issue,expected", sorted(EXPECTED.items()))
def test_parser_reads_adjacent_issues(issue: int, expected: str) -> None:
    import asyncio

    source = _source()
    documents = asyncio.run(_fetch(source))
    parser = build_parser_registry().resolve("chunked_grouped")
    parsed = parser.parse(source, documents, (issue,))
    verified = Validator().validate(source, parsed, (issue,))
    assert verified.history.records[0].zodiac_text == expected


def test_parser_rejects_missing_issue() -> None:
    import asyncio

    source = _source()
    documents = asyncio.run(_fetch(source))
    parser = build_parser_registry().resolve("chunked_grouped")
    parsed = parser.parse(source, documents, (999,))
    with pytest.raises(ValidationError) as captured:
        Validator().validate(source, parsed, (999,))
    assert captured.value.failure.code is ErrorCode.ISSUE_MISSING


def test_parser_rejects_wrong_anchor() -> None:
    import asyncio
    from dataclasses import replace

    source = _source()
    documents = asyncio.run(_fetch(source))
    parser = build_parser_registry().resolve("chunked_grouped")
    from v2.parsers.registry import ParseError

    with pytest.raises(ParseError) as captured:
        parser.parse(
            replace(source, section_marker="不存在栏目"), documents, (261,)
        )
    assert captured.value.failure.code is ErrorCode.ANCHOR_MISSING
