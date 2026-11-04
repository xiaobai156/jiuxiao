# -*- coding: utf-8 -*-
r"""「CC琴棋 / CC春秋」303 期封存的独立复验（只读）。

py -3.10 audit\archive-cc2sites-303\verify_archive.py
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
ISSUE = 303
NAMES = ["CC琴棋", "CC春秋"]
KEPT_IN_FAIL_LIST = "云涌风飞"

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

BEFORE_ACTIVE = 457
AFTER_ACTIVE = 455
BEFORE_ARCHIVED = 84
AFTER_ARCHIVED = 86

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

# 1. 活跃：只少了这两站，其余逐字段、顺序不变
expected = [item for item in before_config["sources"] if item["name"] not in NAMES]
ck(config["sources"] == expected, "活跃 = 开工前 − 两站（其余逐字段与顺序不变）")
ck(not [item for item in config["sources"] if item["name"] in NAMES], "活跃中已无这两站")
names = [item["name"] for item in config["sources"]]
ck(len(set(names)) == len(names), "活跃站名唯一")

# 2. 封存：尾部两条深拷贝 + 时间 + 理由，前 84 条未动
ck(archived["sources"][:BEFORE_ARCHIVED] == before_archived["sources"], "封存前 84 条逐字段未动")
tail = archived["sources"][-2:]
ck([item["source"]["name"] for item in tail] == NAMES, f"封存尾部顺序 == {NAMES}")
for name, entry in zip(NAMES, tail):
    raw_before = [item for item in before_config["sources"] if item["name"] == name]
    ck(len(raw_before) == 1, f"开工前 {name} 活跃条目恰 1 条")
    ck(entry["source"] == raw_before[0], f"{name} 封存条目为原始条目深拷贝（逐字段一致）")
    ck("522" in entry["reason"] and "用户点名封存" in entry["reason"],
       f"{name} reason 含封存依据与 HTTP 522 证据")
    ck(len([e for e in archived["sources"] if e["source"]["name"] == name]) == 1,
       f"{name} 封存中恰 1 条")
archived_at = tail[0]["archived_at"]
ck(all(item["archived_at"] == archived_at for item in tail), "两站 archived_at 一致")
ck([e["source"] for e in removed["entries"]] == [item["source"] for item in tail],
   "removed_entries.json 与封存尾部一致")

# 3. 缓存：整条移除，窗口与既有站点未动
ck(cache["issues"] == before_cache["issues"], "缓存窗口未变")
ck(cache["latest_issue"] == before_cache["latest_issue"] == ISSUE, "latest_issue 未变")
before_keys = [
    source_identity(source_from_dict(item["source"])).key for item in before_cache["sources"]
]
target_keys = set()
for name in NAMES:
    raw_before = [item for item in before_config["sources"] if item["name"] == name]
    key = source_identity(source_from_dict(raw_before[0])).key
    ck(before_keys.count(key) == 1, f"{name} 身份键在开工前缓存中恰 1 条")
    target_keys.add(key)
expected_cache = [
    item
    for item, key in zip(before_cache["sources"], before_keys)
    if key not in target_keys
]
ck(cache["sources"] == expected_cache, "缓存 = 开工前 − 两站（其余条目逐字段未动）")
ck(not [item for item in cache["sources"] if item["source"]["name"] in NAMES], "缓存中已无这两站")

# 4. 回读
repo = SourceRepository(SOURCES, ARCHIVED)
active = repo.load_active()
archived_models = repo.load_archived()
ck(len(active) == AFTER_ACTIVE, f"回读活跃 == {AFTER_ACTIVE}")
ck(len(archived_models) == AFTER_ARCHIVED, f"回读封存 == {AFTER_ARCHIVED}")
ck(not [s for s in active if s.name in NAMES], "回读活跃无这两站")
keys = [source_identity(s).key for s in active]
ck(len(set(keys)) == len(keys), "活跃身份键唯一")
for name in NAMES:
    model_tail = [e for e in archived_models if e.source.name == name]
    raw_before = [item for item in before_config["sources"] if item["name"] == name][0]
    ck(len(model_tail) == 1 and source_to_dict(model_tail[0].source) == raw_before,
       f"回读封存 {name} 与原始条目一致")

# 5. 报告未纳入改动：不含这两站成功行
if REPORT.exists():
    report_lines = [line for line in REPORT.read_text(encoding="utf-8").splitlines() if line.strip()]
    for name in NAMES:
        ck(not [line for line in report_lines if line.endswith(f" {name}")],
           f"成功报告不含 {name} 行（封存不写成功）")
else:
    print("NOTE 303 成功报告当前不存在")

# 6. 失败清单：只删除这两站条目，其余条目（云涌风飞）必须原样保留
if FAILED.exists():
    fail_text = FAILED.read_text(encoding="utf-8")
    for name in NAMES:
        ck(name not in fail_text, f"失败清单不含 {name}")
    ck(KEPT_IN_FAIL_LIST in fail_text, f"失败清单保留 {KEPT_IN_FAIL_LIST} 条目")
    ck(FAILED.stat().st_size > 0, "失败清单未被误删")
else:
    ck(False, "失败清单应仍存在（云涌风飞仍在失败）")

fail = 0
for ok, label in checks:
    print(f"{'PASS' if ok else 'FAIL'} {label}")
    if not ok:
        fail += 1
print(f"\n合计 {len(checks)} 项：PASS {len(checks) - fail} / FAIL {fail}")
raise SystemExit(1 if fail else 0)
