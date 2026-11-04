"""封存前置检查（只读）：人多人少、宝藏神料 的活跃条目、封存状态与缓存条目。"""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if "v2" not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        "v2", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
    )
    pkg = importlib.util.module_from_spec(spec)
    sys.modules["v2"] = pkg
    spec.loader.exec_module(pkg)

from v2.config.repository import SourceRepository  # noqa: E402
from v2.config.schema import source_to_dict  # noqa: E402

TARGETS = ["人多人少", "宝藏神料"]
BASE = ROOT.parent


def main() -> int:
    repo = SourceRepository(
        ROOT / "config" / "sources.json", ROOT / "config" / "archived_sources.json"
    )
    active = repo.load_active()
    archived = repo.load_archived()
    cache = json.loads(
        (ROOT / "cache" / "recent_10_cache.json").read_text(encoding="utf-8")
    )
    print(f"活跃 {len(active)} / 封存 {len(archived)} / 缓存 {len(cache['sources'])}")
    print(f"缓存窗口 {cache['issues']} latest={cache['latest_issue']}")
    for name in TARGETS:
        print("\n" + "=" * 70)
        print(name)
        hits = [s for s in active if s.name == name]
        print(f"  活跃匹配={len(hits)}  封存匹配={len([e for e in archived if e.source.name == name])}")
        for s in hits:
            print(f"  条目: {json.dumps(source_to_dict(s), ensure_ascii=False)}")
            print(f"  身份键: {__import__('v2.domain.identity', fromlist=['x']).source_identity(s).key}")
        for item in [i for i in cache["sources"] if i["source"]["name"] == name]:
            print(
                f"  缓存: current={item['current_issue']} "
                f"records={sorted(item['records'], key=int, reverse=True)} "
                f"errors={item['errors']}"
            )
    fail = BASE / "七类数据统一归纳失败" / "266期-生肖-失败.txt"
    if fail.exists():
        text = fail.read_text(encoding="utf-8")
        print("\n266 失败TXT 含这两站:", [n for n in TARGETS if n in text])
        print("266 失败TXT 条目:")
        for entry in text.split("\n\n"):
            if entry.strip():
                print("  ", entry.splitlines()[0][:100])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
