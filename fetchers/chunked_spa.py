"""抓取层：纯 JS 站点（壳 + 服务端数据分块 + deflate 压缩）。

站点结构（2026-09 实测）：
  1. 页面 HTML 仅约 1.4KB 空壳，其中 <script src=".../js-<site>-<id>"> 指向数据分块；
  2. 分块体积约 12 万字符，内含数百条 base64 串；
  3. 每条 base64 解码后是 raw deflate 压缩的 HTML 片段（期号 + 分组原文）。

本抓取层只取回原始文档：解压片段按原序拼接为 chunked_data 文档；不裁决、不写文件。
数据分块基址优先取配置 api_url（形如 https://api.kxusu.com/js-153-），否则用壳内脚本地址推断。
"""

from __future__ import annotations

import base64
import binascii
import re
import zlib
from urllib.parse import urljoin, urlsplit

from v2.domain.errors import ErrorCode, Failure
from v2.domain.models import Document, DocumentMethod, Source
from v2.fetchers.registry import (
    FetchError,
    FetchRequest,
    HttpClient,
)
from v2.parsers.registry import normalize_document_text


CHUNK_SRC_PATTERN = re.compile(
    r"""/js-\d+-\d+""",
    re.IGNORECASE,
)
PAYLOAD_PATTERN = re.compile(r"[A-Za-z0-9+/]{60,}={0,2}")


def inflate_blobs(payload: str) -> str:
    """还原分块中全部可解压片段，按出现顺序拼接。"""
    fragments: list[str] = []
    seen: set[str] = set()
    for blob in PAYLOAD_PATTERN.findall(payload):
        if blob in seen:
            continue
        seen.add(blob)
        padded = blob + "=" * ((4 - len(blob) % 4) % 4)
        try:
            raw = base64.b64decode(padded, validate=True)
        except (binascii.Error, ValueError):
            continue
        for decoder in (zlib.decompress, lambda data: zlib.decompress(data, -15)):
            try:
                fragments.append(decoder(raw).decode("utf-8", "ignore"))
                break
            except (zlib.error, UnicodeDecodeError, ValueError):
                continue
    # 片段是定长切分（常见每段 300 字符），会从行中间截断，
    # 必须无缝拼接还原原始流；若插入换行会把被截断的期拆成两半而丢数据。
    return "".join(fragments)


def chunk_sources(shell: str) -> tuple[tuple[str, str], ...]:
    """从壳 HTML 取 (chunk_id, 分块绝对地址) 列表，去重保序。"""
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for match in CHUNK_SRC_PATTERN.finditer(shell):
        path = match.group(0)
        chunk_id = path.rsplit("-", 1)[-1]
        if chunk_id in seen:
            continue
        seen.add(chunk_id)
        result.append((chunk_id, path))
    return tuple(result)


class ChunkedSpaFetcher:
    """取回「壳 → 数据分块 → 解压片段」型站点的原始文档。"""

    def __init__(self, http: HttpClient) -> None:
        self.http = http

    async def fetch(
        self,
        source: Source,
        request: FetchRequest,
    ) -> tuple[Document, ...]:
        shell = await self._get(
            source.url,
            timeout_ms=request.timeout_ms,
            context=(("url", source.url),),
        )
        candidates = chunk_sources(shell)
        documents: list[Document] = []
        errors: list[str] = []
        for chunk_id, chunk_url in candidates:
            resolved = self._with_base(source, chunk_url)
            try:
                payload = await self._get(
                    resolved,
                    timeout_ms=request.timeout_ms,
                    context=(
                        ("url", source.url),
                        ("chunk_url", resolved),
                    ),
                )
            except FetchError as exc:
                errors.append(f"{chunk_id}: {exc.failure.detail}")
                continue
            text = normalize_document_text(inflate_blobs(payload))
            if not text:
                errors.append(f"{chunk_id}: 无可用解压片段")
                continue
            documents.append(
                Document(
                    label=f"chunk:{chunk_id}",
                    url=resolved,
                    text=text,
                    method=DocumentMethod.CHUNKED_DATA,
                    metadata=(
                        ("chunk_id", chunk_id),
                        ("source_url", source.url),
                    ),
                )
            )
        if not documents:
            raise FetchError(
                Failure(
                    ErrorCode.FETCH_FAILED,
                    detail="; ".join(errors) or "no data chunk in shell",
                    context=(("url", source.url),),
                )
            )
        return tuple(documents)

    @staticmethod
    def _with_base(source: Source, chunk_url: str) -> str:
        """把壳内分块地址落到配置的 api_url 基址上（去掉查询参数）。"""
        base = (source.api_url or "").strip().rstrip("/")
        parts = urlsplit(chunk_url)
        filename = parts.path.rsplit("/", 1)[-1]
        if not base:
            return f"{parts.scheme}://{parts.netloc}/{filename}"
        return f"{base}/{filename}"

    async def _get(
        self,
        url: str,
        *,
        timeout_ms: int,
        context: tuple[tuple[str, str], ...],
    ) -> str:
        response = await self.http.get(
            url,
            timeout_ms=timeout_ms,
            headers=(("Accept", "text/html,*/*"),),
        )
        if response.error:
            raise FetchError(
                Failure(
                    ErrorCode.FETCH_FAILED,
                    detail=response.error,
                    context=context,
                )
            )
        if response.status is None or response.status >= 400:
            raise FetchError(
                Failure(
                    ErrorCode.HTTP_ERROR,
                    detail=f"status={response.status}",
                    context=context,
                )
            )
        return response.text or ""
