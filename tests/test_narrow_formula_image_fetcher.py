from __future__ import annotations

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
    if specification is None or specification.loader is None:
        raise RuntimeError("无法加载 V2 测试包")
    package = importlib.util.module_from_spec(specification)
    sys.modules["v2"] = package
    specification.loader.exec_module(package)

from v2.config.repository import SourceRepository  # noqa: E402
from v2.fetchers.browser_page import PlaywrightBrowserClient  # noqa: E402
from v2.fetchers.narrow_image_browser import (  # noqa: E402
    NarrowImagePlaywrightBrowserClient,
)


def test_narrow_image_client_changes_only_the_width_boundary() -> None:
    assert PlaywrightBrowserClient.IMAGE_MIN_WIDTH == 600
    assert PlaywrightBrowserClient.IMAGE_MIN_HEIGHT == 200
    assert NarrowImagePlaywrightBrowserClient.IMAGE_MIN_WIDTH == 400
    assert NarrowImagePlaywrightBrowserClient.IMAGE_MIN_HEIGHT == 200


def test_formula_client_prioritizes_anchor_linked_image_over_larger_ads() -> None:
    target = {
        "index": 3,
        "width": 476,
        "height": 255,
        "anchorLine": "235期：嫦娥彩报╠无错九肖╣公式规律",
        "anchorTerm": "嫦娥彩报╠无错九肖╣公式规律",
        "dataMarkerLine": "235期：嫦娥彩报╠无错九肖╣公式规律",
    }
    first_ad = {"index": 4, "width": 800, "height": 250}
    second_ad = {"index": 15, "width": 800, "height": 250}
    candidates = (target, first_ad, second_ad)

    regular = PlaywrightBrowserClient._rank_image_candidates(candidates)
    formula = NarrowImagePlaywrightBrowserClient._rank_image_candidates(candidates)

    assert tuple(item["index"] for item in regular) == (4, 15, 3)
    assert tuple(item["index"] for item in formula) == (3, 4, 15)


def test_only_formula_target_uses_narrow_image_fetcher() -> None:
    active = SourceRepository(
        PROJECT_ROOT / "config" / "sources.json",
        PROJECT_ROOT / "config" / "archived_sources.json",
    ).load_active()
    formula = next(source for source in active if source.name == "嫦娥公式")

    assert formula.fetcher == "browser_page_narrow_image"
    assert sum(source.fetcher == "browser_page_narrow_image" for source in active) == 1
