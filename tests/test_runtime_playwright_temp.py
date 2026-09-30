import asyncio
import os
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if "v2" not in sys.modules:
    import importlib.util

    specification = importlib.util.spec_from_file_location(
        "v2",
        PROJECT_ROOT / "__init__.py",
        submodule_search_locations=[str(PROJECT_ROOT)],
    )
    assert specification is not None and specification.loader is not None
    package = importlib.util.module_from_spec(specification)
    sys.modules["v2"] = package
    specification.loader.exec_module(package)


from v2 import runtime  # noqa: E402


class _FakeContext:
    async def close(self) -> None:
        return None


class _FakeBrowser:
    async def new_context(self, **_kwargs):
        return _FakeContext()

    async def close(self) -> None:
        return None


class _FakeChromium:
    async def launch(self, **_kwargs):
        return _FakeBrowser()


class _FakePlaywrightManager:
    def __init__(self, observed_env: dict[str, str]) -> None:
        self.observed_env = observed_env
        self.playwright = type(
            "Playwright",
            (),
            {"chromium": _FakeChromium()},
        )()

    async def __aenter__(self):
        self.observed_env.update(
            {key: os.environ[key] for key in ("TEMP", "TMP")}
        )
        isolated_temp = Path(self.observed_env["TEMP"])
        assert isolated_temp.is_dir()
        probe = isolated_temp / "write-check"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return self.playwright

    async def __aexit__(self, *_args) -> None:
        return None


def test_browser_uses_isolated_writable_temp_and_restores_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    local_appdata = tmp_path / "localappdata"
    monkeypatch.setenv("LOCALAPPDATA", str(local_appdata))
    monkeypatch.setenv("TEMP", "original-temp")
    monkeypatch.setenv("TMP", "original-tmp")
    observed_env: dict[str, str] = {}
    monkeypatch.setattr(
        runtime,
        "async_playwright",
        lambda: _FakePlaywrightManager(observed_env),
    )

    asyncio.run(_use_browser())

    isolated_temp = Path(observed_env["TEMP"])
    assert observed_env["TEMP"] == observed_env["TMP"]
    assert isolated_temp.parent == (
        local_appdata / "灵蛇九肖_修复版v2" / "playwright-temp"
    )
    assert not isolated_temp.exists()
    assert os.environ["TEMP"] == "original-temp"
    assert os.environ["TMP"] == "original-tmp"


async def _use_browser() -> None:
    async with runtime._browser_clients():
        return None
