from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\Administrator\Desktop\每天工具\爬虫合集\灵蛇九肖_修复版v2")
TARGETS = ("土豪劣绅", "尽心竭力", "风度翩翩")
ISSUE = 263


def load_v2():
    spec = importlib.util.spec_from_file_location(
        "v2",
        ROOT / "__init__.py",
        submodule_search_locations=[str(ROOT)],
    )
    package = importlib.util.module_from_spec(spec)
    sys.modules["v2"] = package
    spec.loader.exec_module(package)


load_v2()

from v2.storage.cache import CacheRepository  # noqa: E402


def snapshot() -> dict:
    cache = CacheRepository(ROOT / "cache" / "recent_10_cache.json").load()
    out = {
        "cycle": cache.cycle,
        "latest_issue": cache.latest_issue,
        "issues": list(cache.issues),
        "source_count": len(cache.sources),
        "targets": {},
    }
    for item in cache.sources:
        if item.source.name not in TARGETS:
            continue
        out["targets"][item.source.name] = {
            "current_issue": item.current_issue,
            "records": {str(k): v for k, v in item.records},
            "errors": {str(k): v.value for k, v in item.errors},
        }
    return out


print(json.dumps(snapshot(), ensure_ascii=False, indent=2))
