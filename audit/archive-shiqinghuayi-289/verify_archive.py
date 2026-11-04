# -*- coding: utf-8 -*-
r"""「诗情画意」289 期封存的独立复验（只读）。

py -3.10 audit\archive-shiqinghuayi-289\verify_archive.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDIT = Path(__file__).resolve().parent
BASE = ROOT.parent
ISSUE = 289
NAME = "诗情画意"
ARCHIVED_AT = "2026-10-17T11:57:38+08:00"
IDENTITY_PREFIX = "5352098a9785"

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

SOURCES = ROOT / "config" / "sources.json"
ARCHIVED = ROOT / "config" / "archived_sources.json"
CACHE = ROOT / "cache" / "recent_10_cache.json"
REPORT = BASE / "七类数据统一归纳" / f"{ISSUE}期-生肖.txt"
FAILED = BASE / "七类数据统一归纳失败" / f"{ISSUE}期-生肖-失败.txt"

BEFORE_ACTIVE = 443
AFTER_ACTIVE = 442
BEFORE_ARCHIVED = 76
AFTER_ARCHIVED = 77

checks: list[tuple[bool, str]] = []


def ck(ok: bool, label: str) -> None:
    checks.append((bool(ok), label))


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


config = load(SOURCES)
archived = load(ARCHIVED)
cache = load(CACHE)
before_config = load(AUDIT / "sources.json.before")
before_archived = load(AUDIT / "archived_sources.json.before")
before_cache = load(AUDIT / "recent_10_cache.json.before")
removed = load(AUDIT / "removed_entries.json")

ck(len(before_config["sources"]) == BEFORE_ACTIVE,
   f"开工前活跃 == {BEFORE_ACTIVE}（实 {len(before_config['sources'])}）")
ck(len(before_archived["sources"]) == BEFORE_ARCHIVED,
   f"开工前封存 == {BEFORE_ARCHIVED}（实 {len(before_archived['sources'])}）")
ck(len(config["sources"]) == AFTER_ACTIVE, f"活跃 == {AFTER_ACTIVE}（实 {len(config['sources'])}）")
ck(len(archived["sources"]) == AFTER_ARCHIVED, f"封存 == {AFTER_ARCHIVED}（实 {len(archived['sources'])}）")
ck(len(cache["sources"]) == AFTER_ACTIVE, f"缓存 == {AFTER_ACTIVE}（实 {len(cache['sources'])}）")

# 1. 活跃：只少了该站，其余逐字段、顺序不变
expected = [item for item in before_config["sources"] if item["name"] != NAME]
ck(config["sources"] == expected, "活跃 = 开工前 − 该站（其余逐字段与顺序不变）")
ck(not [item for item in config["sources"] if item["name"] == NAME], "活跃中已无该站")
names = [item["name"] for item in config["sources"]]
ck(len(set(names)) == len(names), "活跃站名唯一")

# 2. 封存：尾部深拷贝 + 时间 + 理由，前 76 条未动
ck(archived["sources"][:BEFORE_ARCHIVED] == before_archived["sources"], "封存前 76 条逐字段未动")
tail = archived["sources"][-1]
raw_before = [item for item in before_config["sources"] if item["name"] == NAME]
ck(len(raw_before) == 1, "开工前该站活跃条目恰 1 条")
ck(tail["source"] == raw_before[0], "封存条目为原始条目深拷贝（逐字段一致）")
ck(tail["archived_at"] == ARCHIVED_AT, f"archived_at == {ARCHIVED_AT}")
ck("TLS" in tail["reason"] and "用户点名封存" in tail["reason"], "reason 含封存依据与 TLS 证据")
ck(len([e for e in archived["sources"] if e["source"]["name"] == NAME]) == 1, "封存中该站恰 1 条")
ck(removed["entries"][0]["source"] == raw_before[0], "removed_entries.json 与原始条目一致")

# 3. 缓存：整条移除，窗口与既有站点未动
ck(cache["issues"] == before_cache["issues"], "缓存窗口未变")
ck(cache["latest_issue"] == before_cache["latest_issue"] == ISSUE, "latest_issue 未变")
before_keys = [
    source_identity(source_from_dict(item["source"])).key for item in before_cache["sources"]
]
target_key = [k for k in before_keys if k.startswith(IDENTITY_PREFIX)]
ck(len(target_key) == 1, f"身份键前缀 {IDENTITY_PREFIX} 在开工前缓存中恰 1 条")
expected_cache = [
    item
    for item, key in zip(before_cache["sources"], before_keys)
    if key != target_key[0]
]
ck(cache["sources"] == expected_cache, "缓存 = 开工前 − 该站（其余条目逐字段未动）")
ck(not [item for item in cache["sources"] if item["source"]["name"] == NAME], "缓存中已无该站")

# 4. 回读
repo = SourceRepository(SOURCES, ARCHIVED)
active = repo.load_active()
archived_models = repo.load_archived()
ck(len(active) == AFTER_ACTIVE, f"回读活跃 == {AFTER_ACTIVE}")
ck(len(archived_models) == AFTER_ARCHIVED, f"回读封存 == {AFTER_ARCHIVED}")
ck(not [s for s in active if s.name == NAME], "回读活跃无该站")
keys = [source_identity(s).key for s in active]
ck(len(set(keys)) == len(keys), "活跃身份键唯一")
model_tail = [e for e in archived_models if e.source.name == NAME]
ck(len(model_tail) == 1 and source_to_dict(model_tail[0].source) == raw_before[0],
   "回读封存条目与原始条目一致")

# 5. 报告未纳入改动：不含该站成功行
if REPORT.exists():
    report_lines = [line for line in REPORT.read_text(encoding="utf-8").splitlines() if line.strip()]
    ck(not [line for line in report_lines if line.endswith(f" {NAME}")],
       "成功报告不含该站行（封存不写成功）")
else:
    print("NOTE 289 成功报告当前不存在")

# 6. 失败清单：开工前缺失/为空，封存未创建内容
if FAILED.exists():
    ck(FAILED.stat().st_size == 0, f"失败清单为空或未含该站（实 {FAILED.stat().st_size}B）")
    ck(NAME not in FAILED.read_text(encoding="utf-8"), "失败清单不含该站")
else:
    print("NOTE 289 失败清单当前不存在（外部工具维护，封存未创建）")

fail = 0
for ok, label in checks:
    print(f"{'PASS' if ok else 'FAIL'} {label}")
    if not ok:
        fail += 1
print(f"\n合计 {len(checks)} 项：PASS {len(checks) - fail} / FAIL {fail}")
raise SystemExit(1 if fail else 0)
