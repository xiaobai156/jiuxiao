"""站内用户帖（zcphjs 家族）抓取层回归测试。

站点特征：用户主页 SPA 渲染的正文来自列表接口 ``/api/v1/users/<uid>/forums``，
而那一段 ``content`` 是过期或截断的预览（曾导致丰利骨头、盐卤香灯两站 314 期
``ISSUE_MISSING``）。完整历史只出现在帖子详情接口 ``/api/v1/forums/<post_id>``，
所以抓取必须「列表定位当期帖 → 详情取权威正文」两步，且详情 id 必须与列表一致。
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
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
from v2.fetchers.registry import FetchError, FetchRequest, HttpResponse  # noqa: E402
from v2.fetchers.user_forums import UserForumsApiFetcher  # noqa: E402

HOST = "https://zcphjs.example.work:12277"
USER_URL = f"{HOST}/#/users/21928"
LIST_URL = f"{HOST}/api/v1/users/21928/forums?per_page=50"
DETAIL_URL = f"{HOST}/api/v1/forums/16368017"

# 列表接口里的正文是过期预览，只有详情接口的才是完整历史
STALE_PREVIEW = "<p>083期:九肖【马狗羊猴鸡虎牛猪鼠】</p><p>084期:九肖【蛇龙兔羊牛狗马猪虎】</p>"
FULL_CONTENT = (
    "<p>313期:九肖【虎兔马猴龙牛猪羊蛇】開:鼠43错</p>"
    "<p>314期:九肖【鸡羊猪兔牛狗猴鼠虎】開:000准</p>"
)
LIST_PAYLOAD = json.dumps(
    [
        {"id": 16300000, "draw": 313, "content": STALE_PREVIEW},
        {"id": 16368017, "draw": 314, "content": STALE_PREVIEW},
    ],
    ensure_ascii=False,
)
DETAIL_PAYLOAD = json.dumps(
    {"id": 16368017, "draw": 314, "content": FULL_CONTENT},
    ensure_ascii=False,
)


class _FakeHttp:
    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    async def get(self, url, *, timeout_ms, headers):  # noqa: ANN001
        self.calls.append(url)
        if url in self.responses:
            return HttpResponse(status=200, text=self.responses[url], url=url)
        return HttpResponse(status=404, text="", url=url)


def _source(url: str = USER_URL) -> Source:
    return Source(
        name="丰利骨头",
        url=url,
        position=Position.BOTTOM,
        section_marker="九肖",
        fetcher="user_forums_api",
        parser="direct_nine",
        data_marker="九肖",
    )


def _fetch(payloads: dict[str, str], issues: tuple[int, ...] = (314,), url: str = USER_URL):
    http = _FakeHttp(payloads)
    documents = asyncio.run(
        UserForumsApiFetcher(http).fetch(_source(url), FetchRequest(issues))
    )
    return documents, http


def test_fetch_uses_detail_content_of_requested_issue() -> None:
    documents, http = _fetch({LIST_URL: LIST_PAYLOAD, DETAIL_URL: DETAIL_PAYLOAD})

    assert http.calls == [LIST_URL, DETAIL_URL]
    assert len(documents) == 1
    document = documents[0]
    assert document.method is DocumentMethod.DYNAMIC_API
    assert document.url == DETAIL_URL
    # 详情正文才是权威数据；列表里的过期预览不能进文档
    assert "314期:九肖【鸡羊猪兔牛狗猴鼠虎】" in document.text
    assert "083期" not in document.text
    metadata = dict(document.metadata)
    assert metadata["article_id"] == "16368017"
    assert metadata["user_id"] == "21928"
    assert metadata["draw"] == "314"


def test_fetch_falls_back_to_latest_post_when_issue_absent() -> None:
    """当期帖尚未发布时取最新帖，由解析器给出 ISSUE_MISSING，而不是抓取阶段报错。"""
    documents, http = _fetch({LIST_URL: LIST_PAYLOAD, DETAIL_URL: DETAIL_PAYLOAD}, issues=(315,))

    assert http.calls == [LIST_URL, DETAIL_URL]
    assert dict(documents[0].metadata)["draw"] == "314"


def test_fetch_rejects_detail_of_another_post() -> None:
    mismatched = json.dumps({"id": 999, "draw": 314, "content": FULL_CONTENT}, ensure_ascii=False)

    with pytest.raises(FetchError) as caught:
        _fetch({LIST_URL: LIST_PAYLOAD, DETAIL_URL: mismatched})

    assert caught.value.failure.code is ErrorCode.SOURCE_UNTRUSTED


def test_fetch_rejects_source_without_user_route() -> None:
    with pytest.raises(FetchError) as caught:
        _fetch({LIST_URL: LIST_PAYLOAD}, url=f"{HOST}/topic/123.html")

    assert caught.value.failure.code is ErrorCode.CONFIG_INVALID


def test_fetch_reports_untrusted_when_list_has_no_posts() -> None:
    with pytest.raises(FetchError) as caught:
        _fetch({LIST_URL: json.dumps([])})

    assert caught.value.failure.code is ErrorCode.SOURCE_UNTRUSTED


def test_new_sources_are_wired_to_user_forums_api() -> None:
    document = json.loads((PROJECT_ROOT / "config" / "sources.json").read_text(encoding="utf-8"))
    picked = {item["name"]: item for item in document["sources"]}

    for name in ("丰利骨头", "盐卤香灯"):
        source = picked[name]
        assert source["fetcher"] == "user_forums_api"
        assert source["parser"] == "direct_nine"
        assert source["data_marker"] == "九肖"
        assert source["url"].endswith("/#/users/" + ("21928" if name == "丰利骨头" else "27764"))
