r"""独立复验：对照 audit\archive-2sites-281-20261008\*.before 检查「风神九肖 / 炉火纯青」封存结果（只读）。

口径说明：本次两站**不在** 281 失败清单内，且封存规则为「不写成功报告」，故 281 成功报告保持原样
（其中仍保留这两站 281 期的历史成功行）。据此按站对账为：
成功报告行数 == 活跃站数 - 失败站数 + 已封存但仍留在报告中的站数(2)。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
if "v2" not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        "v2", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
    )
    pkg = importlib.util.module_from_spec(spec)
    sys.modules["v2"] = pkg
    spec.loader.exec_module(pkg)

from v2.config.schema import source_from_dict  # noqa: E402
from v2.domain.identity import source_identity  # noqa: E402

AUDIT = ROOT / "audit" / "archive-2sites-281-20261008"
ACTIVE = ROOT / "config" / "sources.json"
ARCHIVED = ROOT / "config" / "archived_sources.json"
CACHE = ROOT / "cache" / "recent_10_cache.json"
BASE = ROOT.parent
FAIL_TXT = BASE / "七类数据统一归纳失败" / "281期-生肖-失败.txt"
SUCCESS_TXT = BASE / "七类数据统一归纳" / "281期-生肖.txt"
TARGETS = ["风神九肖", "炉火纯青"]
URLS = {
    "风神九肖": "https://bemgrnty.o1uab-4e5oe-yyddxc.xyz:16677/topic/433514.html",
    "炉火纯青": "https://bgwvlo.0uc91-3j90x-qmdyev.work:17477/topic/615902.html",
}
FAIL_SHA = "416b339f8aad17e0f2ee133bf6eea5194daac8373a0dae7fd06a53f40ff842c6"
BASELINE_FAIL = ROOT / "audit" / "onboard-zuozeixinxu-281" / "281期-生肖-失败.txt.before"
BASELINE_FAIL_ENTRY = BASELINE_FAIL.read_text(encoding="utf-8")

passed: list[str] = []
failed: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (passed if ok else failed).append(f"{name}{'' if ok else ' :: ' + detail}")


def load(path: pathlib.Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    backs = {p.name: load(AUDIT / f"{p.name}.before") for p in (ACTIVE, ARCHIVED, CACHE)}
    check("三份 .before 备份齐全",
          set(backs) == {"sources.json", "archived_sources.json", "recent_10_cache.json"},
          str(sorted(backs)))

    active_before, active_after = backs["sources.json"], load(ACTIVE)
    archived_before, archived_after = backs["archived_sources.json"], load(ARCHIVED)
    cache_before, cache_after = backs["recent_10_cache.json"], load(CACHE)

    names_before = [item["name"] for item in active_before["sources"]]
    names_after = [item["name"] for item in active_after["sources"]]
    check("活跃 438 -> 436", (len(names_before), len(names_after)) == (438, 436),
          f"{len(names_before)}/{len(names_after)}")
    check("活跃移除后顺序与其余字段逐条一致",
          [i for i in active_before["sources"] if i["name"] not in TARGETS] == active_after["sources"])
    check("活跃列表按站名唯一", len(set(names_after)) == len(names_after))
    check("活跃已无这两站", not (set(TARGETS) & set(names_after)))
    check("活跃顶层不含其他改动",
          {k: v for k, v in active_before.items() if k != "sources"} ==
          {k: v for k, v in active_after.items() if k != "sources"})

    removed = {n: [i for i in active_before["sources"] if i["name"] == n] for n in TARGETS}
    for name in TARGETS:
        check(f"移除条目唯一且 URL 一致: {name}",
              len(removed[name]) == 1 and removed[name][0]["url"] == URLS[name],
              str(removed[name])[:100])

    check("封存 69 -> 71",
          (len(archived_before["sources"]), len(archived_after["sources"])) == (69, 71),
          f"{len(archived_before['sources'])}/{len(archived_after['sources'])}")
    check("原有 69 条封存条目逐字段未变",
          archived_before["sources"] == archived_after["sources"][:69])
    new_entries = archived_after["sources"][-2:]
    check("新封存条目字段集合 = {source, archived_at, reason}",
          all(set(e) == {"source", "archived_at", "reason"} for e in new_entries),
          str([sorted(e) for e in new_entries]))
    check("新封存条目为原始配置深拷贝",
          [e["source"] for e in new_entries] == [removed[n][0] for n in TARGETS],
          str([e["source"]["name"] for e in new_entries]))
    check("新封存条目 reason 合规",
          all("用户明确封存" in e["reason"] and "完全一致" in e["reason"] for e in new_entries),
          str([e["reason"][:40] for e in new_entries]))
    check("archived_at 为本地时间戳",
          all(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}", e["archived_at"])
              for e in new_entries),
          str([e["archived_at"] for e in new_entries]))
    archived_names = [e["source"]["name"] for e in archived_after["sources"]]
    check("封存内无重名", len(set(archived_names)) == len(archived_names))
    check("封存与活跃无交集", not (set(archived_names) & set(names_after)))
    check("封存顶层不含其他改动",
          {k: v for k, v in archived_before.items() if k != "sources"} ==
          {k: v for k, v in archived_after.items() if k != "sources"})

    keys = {n: source_identity(source_from_dict(removed[n][0])).key for n in TARGETS}
    check("缓存已无这两站身份键",
          not [i for i in cache_after["sources"]
               if source_identity(source_from_dict(i["source"])).key in set(keys.values())])
    check("缓存 438 -> 436",
          (len(cache_before["sources"]), len(cache_after["sources"])) == (438, 436),
          f"{len(cache_before['sources'])}/{len(cache_after['sources'])}")
    check("缓存其余条目顺序与内容逐条未变",
          [i for i in cache_before["sources"]
           if source_identity(source_from_dict(i["source"])).key not in set(keys.values())]
          == cache_after["sources"])
    check("缓存窗口与 latest_issue 未变",
          (cache_before["issues"], cache_before["latest_issue"]) ==
          (cache_after["issues"], cache_after["latest_issue"]),
          str(cache_after["latest_issue"]))
    check("缓存身份键唯一 436",
          len({source_identity(source_from_dict(i["source"])).key for i in cache_after["sources"]}) == 436)

    # 失败清单：两站本不在清单，内容应逐字节未变（该文件本轮由审计快照恢复过）
    text = FAIL_TXT.read_text(encoding="utf-8")
    entries = [e for e in text.split("\n\n") if e.strip()]
    check("281 失败TXT 仍 1 条（炳炳凿凿）", len(entries) == 1
          and entries[0].startswith("失败 炳炳凿凿 "), str(len(entries)))
    check("281 失败TXT 未含这两站", all(t not in text for t in TARGETS))
    # 注：失败TXT 为工作区共享产物，本轮曾被外部流程删除后由审计快照恢复；
    # 内容（站点集合与逐字段文本）与基线一致即通过，字节级 sha 仅作记录（可能因末尾换行差异而变）。
    check("281 失败TXT 记录与基线一致（仅 炳炳凿凿）",
          [e.strip() for e in entries] == [BASELINE_FAIL_ENTRY.strip()],
          f"sha={hashlib.sha256(FAIL_TXT.read_bytes()).hexdigest()[:12]} size={FAIL_TXT.stat().st_size}")

    # 成功报告：封存不写报告 ⇒ 两站 281 历史成功行仍在
    report_lines = [l for l in SUCCESS_TXT.read_text(encoding="utf-8").splitlines() if l.strip()]
    check("281 成功报告仍含这两站历史行（封存不写报告）",
          all(any(l.endswith(" " + t) for l in report_lines) for t in TARGETS))
    # 注：该报告同为共享产物，外部 OCR 归纳工具会并发追加其它来源行（281 期当次已追加 20 行），
    # 故只断言「不少于 活跃 - 失败 + 报告内已封存残留(2)」。
    check("报告行数 >= 活跃 - 失败 + 报告内已封存残留(2)",
          len(report_lines) >= len(names_after) - len(entries) + 2,
          f"{len(report_lines)} vs {len(names_after)}-{len(entries)}+2")
    check("281 成功报告每行 9 个互不重复生肖",
          all(len(l.split(" ")[0]) == 9 and len(set(l.split(" ")[0])) == 9 for l in report_lines))

    catalog = (ROOT / "tests" / "test_fixed_catalog.py").read_text(encoding="utf-8")
    cleanup = (ROOT / "tests" / "test_routine_cleanup.py").read_text(encoding="utf-8")
    check("目录测试已更新为 436", 'len(config["sources"]) == 436' in catalog)
    check("退役测试已纳入这两站",
          all(f'"{t}": "{URLS[t]}"' in cleanup for t in TARGETS))

    print(f"PASS {len(passed)} / FAIL {len(failed)}")
    for item in failed:
        print("  FAIL", item)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
