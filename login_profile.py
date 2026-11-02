"""打开本项目的持久化浏览器 profile，做一次性人工登录。

背景：部分站点正文设为「回复可见」，游客抓不到正文。这类站点在
`config/sources.json` 里标 `requires_login: true`，抓取时会改用
`browser-profile/` 这个持久化上下文（见 `runtime._browser_profile_dir`）。
本脚本负责把登录态写进该 profile：运行后在弹出的浏览器里登录，
回到命令行按 Enter 保存。

用法：
    py -3.10 login_profile.py                          # 默认打开老恭看马所在论坛
    py -3.10 login_profile.py --url <登录入口URL>
    py -3.10 login_profile.py --list                   # 只列出需要登录的站点
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if "v2" not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        "v2", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
    )
    pkg = importlib.util.module_from_spec(spec)
    sys.modules["v2"] = pkg
    spec.loader.exec_module(pkg)

from v2.config.repository import SourceRepository  # noqa: E402
from v2.runtime import _browser_profile_dir  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

DEFAULT_URL = "https://wwlhc.com/"


def login_sources() -> list[tuple[str, str]]:
    repo = SourceRepository(
        ROOT / "config" / "sources.json",
        ROOT / "config" / "archived_sources.json",
    )
    return [
        (source.name, source.url)
        for source in repo.load_active()
        if source.requires_login
    ]


async def _login(url: str) -> None:
    from playwright.async_api import async_playwright

    profile = _browser_profile_dir()
    profile.mkdir(parents=True, exist_ok=True)
    print(f"profile 目录：{profile}")
    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            str(profile),
            headless=False,
            viewport={"width": 1280, "height": 900},
        )
        page = context.pages[0] if context.pages else await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        except Exception as exc:
            print(f"自动打开页面失败，请在浏览器地址栏手动输入: {type(exc).__name__}: {exc}")
        print("请在弹出的浏览器中登录；登录完成后回到此窗口按 Enter 保存登录状态。")
        await asyncio.to_thread(input)
        await context.close()
    print(f"登录状态已保存到：{profile}")


def main() -> int:
    parser = argparse.ArgumentParser(description="登录并保存本项目爬虫浏览器会话。")
    parser.add_argument("--url", default=DEFAULT_URL, help="登录入口页面")
    parser.add_argument("--list", action="store_true", help="只列出 requires_login 站点")
    args = parser.parse_args()

    sources = login_sources()
    if args.list:
        if not sources:
            print("当前没有 requires_login=true 的站点。")
        for name, url in sources:
            print(f"{name}\t{url}")
        return 0

    if sources:
        print(f"当前需要登录态的站点 {len(sources)} 个：")
        for name, url in sources:
            print(f"  {name}\t{url}")
    else:
        print("提示：当前没有 requires_login=true 的站点，登录态不会被用到。")

    asyncio.run(_login(args.url))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
