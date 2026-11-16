# -*- coding: utf-8 -*-
"""`content-visibility: auto` 展开的回归测试。

背景（317 期）：三个站的正文容器带 `content-visibility: auto`，浏览器跳过屏幕外
渲染，`innerText` 只返回首屏的一部分（门户页 1285 行 / 真实 3690 行），锚点与
当期数据行全部落在未渲染区，导致 CROSS_DOMAIN / ANCHOR_MISSING / ISSUE_MISSING。
抓取层因此在「首屏文本里找不到锚点」时把这类容器强制展开后重读。
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

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

from v2.fetchers.browser_page import (  # noqa: E402
    REVEAL_LAZY_SETTLE_MS,
    PlaywrightBrowserClient,
)


class FakePage:
    """只实现 `_reveal_lazy_content` 用到的两个方法。"""

    def __init__(self, changed: object) -> None:
        self.changed = changed
        self.waits: list[int] = []
        self.scripts: list[str] = []

    async def evaluate(self, script: str):
        self.scripts.append(script)
        if isinstance(self.changed, Exception):
            raise self.changed
        return self.changed

    async def wait_for_timeout(self, milliseconds: int) -> None:
        self.waits.append(milliseconds)


def reveal(page: FakePage) -> int:
    return asyncio.run(PlaywrightBrowserClient._reveal_lazy_content(page))


def test_reveal_reports_changed_elements_and_waits_for_layout() -> None:
    page = FakePage(30)

    assert reveal(page) == 30
    assert page.waits == [REVEAL_LAZY_SETTLE_MS]
    assert "contentVisibility" in page.scripts[0]


def test_reveal_is_noop_when_page_has_no_lazy_containers() -> None:
    """普通页面（0 个容器）不得引入额外等待，保持原有耗时。"""
    page = FakePage(0)

    assert reveal(page) == 0
    assert page.waits == []


def test_reveal_tolerates_evaluate_failure() -> None:
    """脚本不可用时按原样返回 0，抓取继续走原来的单次读取路径。"""
    page = FakePage(RuntimeError("evaluation failed"))

    assert reveal(page) == 0
    assert page.waits == []
