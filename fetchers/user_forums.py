from __future__ import annotations

import asyncio
import html
import json
import re
from urllib.parse import urlsplit

from v2.domain.errors import ErrorCode, Failure
from v2.domain.models import Document, DocumentMethod, Source
from v2.fetchers.browser_page import same_origin
from v2.fetchers.registry import FetchError, FetchRequest, HttpClient
from v2.fetchers.static_page import RECOVERABLE_HTTP_STATUSES


USER_ROUTE_PATTERN = re.compile(r"/users/(?P<user_id>\d+)")
BLOCK_BREAK_PATTERN = re.compile(r"(?i)</p\s*>|<br\s*/?>|</div\s*>")
TAG_PATTERN = re.compile(r"<[^>]+>")
LIST_PATH = "/api/v1/users/{user_id}/forums?per_page={per_page}"
DETAIL_PATH = "/api/v1/forums/{post_id}"


class UserForumsApiFetcher:
    """站内用户帖：先查列表接口定位当期帖子，再取该帖详情接口的权威正文。

    这类站点（zcphjs 家族）的用户主页只渲染列表接口里被截断或过期的正文，
    真实历史只出现在帖子详情接口的 ``content`` 里，因此抓取必须走两步。
    """

    fetcher_id = "user_forums_api"

    def __init__(self, http: HttpClient, per_page: int = 50) -> None:
        if per_page <= 0:
            raise ValueError("per_page 必须大于 0")
        self._http = http
        self._per_page = per_page

    async def fetch(
        self,
        source: Source,
        request: FetchRequest,
    ) -> tuple[Document, ...]:
        origin = self._origin(source)
        user_id = self._user_id(source)
        list_url = origin + LIST_PATH.format(
            user_id=user_id,
            per_page=self._per_page,
        )
        payload = await self._get_json(source, list_url, request, stage="列表")
        posts = self._posts(payload, list_url)
        target = max(request.issues)
        chosen = next(
            (post for post in posts if self._draw(post) == target),
            None,
        )
        if chosen is None or not str(chosen.get("id") or "").strip():
            chosen = max(posts, key=self._draw)
        post_id = str(chosen.get("id")).strip()
        detail_url = origin + DETAIL_PATH.format(post_id=post_id)
        detail = await self._get_json(source, detail_url, request, stage="详情")
        if not isinstance(detail, dict):
            raise FetchError(
                Failure(
                    ErrorCode.SOURCE_UNTRUSTED,
                    detail="详情接口返回结构异常",
                    context=(("api_url", detail_url),),
                )
            )
        resolved_id = str(detail.get("id") or "").strip()
        if resolved_id and resolved_id != post_id:
            raise FetchError(
                Failure(
                    ErrorCode.SOURCE_UNTRUSTED,
                    detail="详情接口返回了另一篇帖子",
                    context=(
                        ("api_url", detail_url),
                        ("expect", post_id),
                        ("actual", resolved_id),
                    ),
                )
            )
        lines = self._content_lines(detail.get("content"))
        if not lines:
            raise FetchError(
                Failure(
                    ErrorCode.SOURCE_UNTRUSTED,
                    detail="详情正文为空",
                    context=(("api_url", detail_url),),
                )
            )
        return (
            Document(
                label="api:user-forums",
                url=detail_url,
                text="\n".join(lines),
                method=DocumentMethod.DYNAMIC_API,
                metadata=(
                    ("article_id", post_id),
                    ("user_id", user_id),
                    ("draw", str(self._draw(chosen))),
                ),
            ),
        )

    @staticmethod
    def _origin(source: Source) -> str:
        parsed = urlsplit(source.url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise FetchError(
                Failure(
                    ErrorCode.CONFIG_INVALID,
                    detail="user_forums_api 需要有效的站点 URL",
                    context=(("url", source.url),),
                )
            )
        port = f":{parsed.port}" if parsed.port else ""
        return f"{parsed.scheme}://{parsed.hostname}{port}"

    @staticmethod
    def _user_id(source: Source) -> str:
        match = USER_ROUTE_PATTERN.search(source.url)
        if match is None:
            raise FetchError(
                Failure(
                    ErrorCode.CONFIG_INVALID,
                    detail="URL 里没有 /users/<id>",
                    context=(("url", source.url),),
                )
            )
        return match.group("user_id")

    async def _get_json(
        self,
        source: Source,
        url: str,
        request: FetchRequest,
        *,
        stage: str,
    ) -> object:
        last_error = ""
        for attempt in range(1, request.attempts + 1):
            response = await self._http.get(
                url,
                timeout_ms=request.timeout_ms,
                headers=(
                    ("Accept", "application/json,text/plain,*/*"),
                    ("X-Requested-With", "XMLHttpRequest"),
                    ("Connection", "close"),
                ),
            )
            if response.url and not same_origin(url, response.url):
                raise FetchError(
                    Failure(
                        ErrorCode.CROSS_DOMAIN,
                        context=(
                            ("api_url", url),
                            ("document_url", response.url),
                        ),
                    )
                )
            if response.status == 200 and response.text.strip():
                try:
                    return json.loads(response.text)
                except json.JSONDecodeError as exc:
                    last_error = "响应不是 JSON"
                    if attempt < request.attempts:
                        if request.retry_delay_ms:
                            await asyncio.sleep(request.retry_delay_ms / 1000)
                        continue
                    raise FetchError(
                        Failure(
                            ErrorCode.SOURCE_UNTRUSTED,
                            detail=f"{stage}接口响应不是 JSON",
                            context=(("api_url", url),),
                        )
                    ) from exc
            retryable = (
                response.status is None
                or response.status in RECOVERABLE_HTTP_STATUSES
            )
            if retryable and attempt < request.attempts:
                if request.retry_delay_ms:
                    await asyncio.sleep(request.retry_delay_ms / 1000)
                continue
            if response.status is None:
                raise FetchError(
                    Failure(
                        ErrorCode.FETCH_FAILED,
                        detail=response.error or last_error,
                        context=(("api_url", url), ("source", source.name)),
                    )
                )
            if response.status == 200:
                raise FetchError(
                    Failure(
                        ErrorCode.SOURCE_UNTRUSTED,
                        detail=f"{stage}接口返回空正文",
                        context=(("api_url", url),),
                    )
                )
            raise FetchError(
                Failure(
                    ErrorCode.HTTP_ERROR,
                    context=(
                        ("api_url", url),
                        ("status", str(response.status)),
                    ),
                )
            )
        raise AssertionError("unreachable")

    @staticmethod
    def _posts(payload: object, list_url: str) -> tuple[dict[str, object], ...]:
        items = payload
        if isinstance(payload, dict):
            items = payload.get("data") or payload.get("items") or ()
        if not isinstance(items, (list, tuple)) or not items:
            raise FetchError(
                Failure(
                    ErrorCode.SOURCE_UNTRUSTED,
                    detail="列表接口没有帖子",
                    context=(("api_url", list_url),),
                )
            )
        posts = tuple(item for item in items if isinstance(item, dict))
        if not posts:
            raise FetchError(
                Failure(
                    ErrorCode.SOURCE_UNTRUSTED,
                    detail="列表接口没有可解析的帖子",
                    context=(("api_url", list_url),),
                )
            )
        return posts

    @staticmethod
    def _draw(post: dict[str, object]) -> int:
        try:
            return int(str(post.get("draw") or "0").strip() or 0)
        except ValueError:
            return 0

    @staticmethod
    def _content_lines(content: object) -> tuple[str, ...]:
        raw = str(content or "").strip()
        if not raw:
            return ()
        text = BLOCK_BREAK_PATTERN.sub("\n", raw)
        text = TAG_PATTERN.sub("", text)
        return tuple(
            line.strip()
            for line in html.unescape(text).splitlines()
            if line.strip()
        )
