"""封存 人多人少、宝藏神料 的独立复验（只读）。"""

from __future__ import annotations

import importlib
import importlib.util
import json
import re
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
from v2.config.schema import source_from_dict, source_to_dict  # noqa: E402
from v2.domain.identity import source_identity  # noqa: E402
from v2.storage.cache import CacheRepository  # noqa: E402

BASE = ROOT.parent
AUDIT = ROOT / "audit" / "archive-two-266"
ACTIVE_PATH = ROOT / "config" / "sources.json"
ARCHIVED_PATH = ROOT / "config" / "archived_sources.json"
CACHE_PATH = ROOT / "cache" / "recent_10_cache.json"
FAIL_TXT = BASE / "七类数据统一归纳失败" / "266期-生肖-失败.txt"
OK_TXT = BASE / "七类数据统一归纳" / "266期-生肖.txt"
WINDOW = [266, 265, 264, 263, 262, 261, 260, 259, 258, 257]
ZODIACS = set("鼠牛虎兔龙蛇马羊猴鸡狗猪")
TARGETS = ["人多人少", "宝藏神料"]
NAME_RE = re.compile(r"^失败\s+(\S+)\s+")

checks: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'} {name}" + (f"  [{detail}]" if detail else ""))


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def fail_names(text: str) -> list[str]:
    return [
        NAME_RE.match(e.splitlines()[0]).group(1)
        for e in text.split("\n\n")
        if e.strip()
    ]


before_active = load(AUDIT / "sources.json.before")
before_archived = load(AUDIT / "archived_sources.json.before")
before_cache = load(AUDIT / "recent_10_cache.json.before")
before_fail = (AUDIT / "266期-生肖-失败.txt.before").read_text(encoding="utf-8")
after_active = load(ACTIVE_PATH)
after_archived = load(ARCHIVED_PATH)
cache = CacheRepository(CACHE_PATH).load()
after_fail = FAIL_TXT.read_text(encoding="utf-8")

# 活跃
check("活跃 347 -> 345", len(before_active["sources"]) == 347 and len(after_active["sources"]) == 345)
check("活跃中已无这两站", not [s for s in after_active["sources"] if s["name"] in TARGETS])
check(
    "其余活跃条目逐字段且顺序一致",
    [s for s in before_active["sources"] if s["name"] not in TARGETS] == after_active["sources"],
)

# 封存
check("封存 57 -> 59", len(before_archived["sources"]) == 57 and len(after_archived["sources"]) == 59)
check("原有 57 条逐字段未变", before_archived["sources"] == after_archived["sources"][:57])
for i, name in enumerate(TARGETS):
    entry = after_archived["sources"][57 + i]
    original = next(s for s in before_active["sources"] if s["name"] == name)
    check(f"封存新增 {name} 为原始条目深拷贝", entry["source"] == original)
    check(f"封存新增 {name} 字段集合正确", set(entry) == {"source", "archived_at", "reason"})
    check(f"封存新增 {name} 含封存缘由", "266期" in entry["reason"] and "不再抓取" in entry["reason"])
    check(f"封存新增 {name} archived_at 已刷新", entry["archived_at"] == "2026-09-23T18:06:47+08:00")
check("封存内无重名", len({e["source"]["name"] for e in after_archived["sources"]}) == 59)

# 缓存
check("缓存 381 -> 379", len(before_cache["sources"]) == 381 and len(cache.sources) == 379)
check("缓存已无这两站", not [i for i in cache.sources if i.source.name in TARGETS])
check("缓存窗口未变", list(cache.issues) == WINDOW, str(cache.issues))
before_other = [
    {
        "source": i["source"],
        "current_issue": i["current_issue"],
        "records": i["records"],
        "errors": i["errors"],
    }
    for i in before_cache["sources"]
    if i["source"]["name"] not in TARGETS
]
after_other = [
    {
        "source": source_to_dict(i.source),
        "current_issue": i.current_issue,
        "records": {str(k): v for k, v in i.records},
        "errors": {str(k): e.value for k, e in i.errors},
    }
    for i in cache.sources
]
check("其余缓存条目逐字段且顺序一致", before_other == after_other)
check("缓存身份唯一", len({source_identity(i.source).key for i in cache.sources}) == 379)
outside = overlap = bad = 0
window = set(WINDOW)
for i in cache.sources:
    rec = {int(k) for k in dict(i.records)}
    err = {int(k) for k in dict(i.errors)}
    if rec & err:
        overlap += 1
    if (rec | err) - window:
        outside += 1
    if i.current_issue is not None and i.current_issue not in window:
        outside += 1
    for value in dict(i.records).values():
        if len(value) != 9 or len(set(value)) != 9 or not set(value) <= ZODIACS:
            bad += 1
check("缓存无越界期", outside == 0, str(outside))
check("缓存无记录/错误重叠", overlap == 0, str(overlap))
check("缓存九肖值全合法", bad == 0, str(bad))

# 报告
check("失败TXT 已无这两站", not (set(TARGETS) & set(fail_names(after_fail))))
check(
    "失败TXT 仅剩大言不惭/归隐山林 且顺序保留",
    fail_names(after_fail) == [n for n in fail_names(before_fail) if n not in TARGETS],
    str(fail_names(after_fail)),
)
check("失败TXT 无多余空段", "\n\n\n" not in after_fail)
ok_lines = OK_TXT.read_text(encoding="utf-8").splitlines()
check("成功TXT 仍 377 行未受影响", len(ok_lines) == 377, str(len(ok_lines)))

# 加载器
repo = SourceRepository(ACTIVE_PATH, ARCHIVED_PATH)
a2 = repo.load_active()
ar2 = repo.load_archived()
check("load_active 通过", len(a2) == 345, str(len(a2)))
check("load_archived 通过", len(ar2) == 59, str(len(ar2)))
check("load_active 与文件逐字段一致", [source_to_dict(s) for s in a2] == after_active["sources"])
check("封存站点不在活跃中", not [s for s in a2 if s.name in TARGETS])
ok_names = {line.rsplit(" ", 1)[-1] for line in ok_lines if line.strip()}
check(
    "成功TXT 站数 + 失败TXT 站数 = 缓存源数",
    len(ok_names) + len(fail_names(after_fail)) == len(cache.sources) == 379,
    f"{len(ok_names)} + {len(fail_names(after_fail))} = {len(ok_names) + len(fail_names(after_fail))}",
)

baks = sorted(p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*.bak"))
check("项目内无 .bak", not baks, ",".join(baks))

passed = sum(1 for _n, ok, _d in checks if ok)
failed = [n for n, ok, _d in checks if not ok]
print(f"\n{passed}/{len(checks)} 通过")
if failed:
    print("失败项:", failed)
    raise SystemExit(1)
print("复验全部通过")
