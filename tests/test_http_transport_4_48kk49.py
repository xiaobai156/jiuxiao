from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET_HOST = "4.48kk49.com"


def _target_sources() -> list[dict[str, object]]:
    document = json.loads(
        (PROJECT_ROOT / "config" / "sources.json").read_text(encoding="utf-8")
    )
    return [
        source
        for source in document["sources"]
        if urlsplit(str(source["url"])).hostname == TARGET_HOST
    ]


def test_4_48kk49_sources_use_static_http_transport() -> None:
    target = _target_sources()

    assert len(target) == 36
    assert all(source["fetcher"] == "static_page" for source in target)
