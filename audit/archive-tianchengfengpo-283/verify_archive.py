r"""独立复验：对照 audit\archive-tianchengfengpo-283\*.before 检查「田乘风破」封存结果（只读）。"""

from __future__ import annotations

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

AUDIT = ROOT / "audit" / "archive-tianchengfengpo-283"
ACTIVE = ROOT / "config" / "sources.json"
ARCHIVED = ROOT / "config" / "archived_sources.json"
CACHE = ROOT / "cache" / "recent_10_cache.json"
FAIL_TXT = ROOT.parent / "七类数据统一归纳失败" / "283期-生肖-失败.txt"
SUCCESS_TXT = ROOT.parent / "七类数据统一归纳" / "283期-生肖.txt"
NAME = "田乘风破"
URL = (
    "https://hcsuuoy.nimo7-9bgj4-fmspxt.xyz:29466/article/manager/"
    "6a3146cf32c7c4bb3c056f95?url=cww"
)
REMAIN = "否极泰来"

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
    check("283 失败TXT 备份齐全且为封存前原文",
          (AUDIT / "283期-生肖-失败.txt.before").exists()
          and NAME in (AUDIT / "283期-生肖-失败.txt.before").read_text(encoding="utf-8"))

    active_before, active_after = backs["sources.json"], load(ACTIVE)
    archived_before, archived_after = backs["archived_sources.json"], load(ARCHIVED)
    cache_before, cache_after = backs["recent_10_cache.json"], load(CACHE)

    names_before = [item["name"] for item in active_before["sources"]]
    names_after = [item["name"] for item in active_after["sources"]]
    check("活跃 438 → 437", (len(names_before), len(names_after)) == (438, 437),
          f"{len(names_before)}/{len(names_after)}")
    check("活跃移除后其余条目逐条一致",
          [i for i in active_before["sources"] if i["name"] != NAME] == active_after["sources"])
    check("活跃列表按站名唯一", len(set(names_after)) == len(names_after))
    check(f"活跃不再含 {NAME}", NAME not in names_after)
    check("活跃顶层不含其他改动",
          {k: v for k, v in active_before.items() if k != "sources"} ==
          {k: v for k, v in active_after.items() if k != "sources"})

    removed = [i for i in active_before["sources"] if i["name"] == NAME]
    check("移除条目唯一且 URL 一致", len(removed) == 1 and removed[0]["url"] == URL,
          str(removed)[:150])

    check("封存 72 → 73",
          (len(archived_before["sources"]), len(archived_after["sources"])) == (72, 73),
          f"{len(archived_before['sources'])}/{len(archived_after['sources'])}")
    check("原有 72 条封存条目逐字段未变",
          archived_before["sources"] == archived_after["sources"][:72])
    new_entry = archived_after["sources"][-1]
    check("新封存条目字段集合 = {source, archived_at, reason}",
          set(new_entry) == {"source", "archived_at", "reason"}, str(sorted(new_entry)))
    check("新封存条目为原始配置深拷贝", new_entry["source"] == removed[0])
    check("新封存条目 reason 合规",
          new_entry["reason"].startswith("用户明确封存，不再抓取；283期抓取失败")
          and "AdminArticle 不存在" in new_entry["reason"], new_entry["reason"][:80])
    check("archived_at 为本地时间戳",
          re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}",
                       new_entry["archived_at"]) is not None,
          new_entry["archived_at"])
    archived_names = [e["source"]["name"] for e in archived_after["sources"]]
    check("封存内无重名", len(set(archived_names)) == len(archived_names))
    check("封存与活跃无交集", not (set(archived_names) & set(names_after)))
    check("封存顶层不含其他改动",
          {k: v for k, v in archived_before.items() if k != "sources"} ==
          {k: v for k, v in archived_after.items() if k != "sources"})

    key = source_identity(source_from_dict(removed[0])).key
    check("缓存移除的正是该站身份键",
          not [i for i in cache_after["sources"]
               if source_identity(source_from_dict(i["source"])).key == key])
    check("缓存 438 → 437",
          (len(cache_before["sources"]), len(cache_after["sources"])) == (438, 437),
          f"{len(cache_before['sources'])}/{len(cache_after['sources'])}")
    check("缓存其余条目顺序与内容逐条未变",
          [i for i in cache_before["sources"]
           if source_identity(source_from_dict(i["source"])).key != key] == cache_after["sources"])
    check("缓存窗口与 latest_issue 未变",
          (cache_before["issues"], cache_before["latest_issue"]) ==
          (cache_after["issues"], cache_after["latest_issue"]),
          str(cache_after["latest_issue"]))
    check("缓存身份键唯一 437",
          len({source_identity(source_from_dict(i["source"])).key
               for i in cache_after["sources"]}) == 437)

    text = FAIL_TXT.read_text(encoding="utf-8")
    entries = [e for e in text.split("\n\n") if e.strip()]
    check("283 失败TXT 剩 2 条", len(entries) == 2, str(len(entries)))
    check(f"283 失败TXT 首条仍为 {REMAIN} 且原文未变",
          entries[0].startswith(f"失败 {REMAIN} ") and "阶段: 网络抓取" in entries[0],
          entries[0][:60])
    check("283 失败TXT 第二条仍为 依然公主九肖",
          entries[1].startswith("失败 依然公主九肖 "), entries[1][:40])
    check("283 失败TXT 已无 " + NAME, NAME not in text)
    check("283 失败TXT 以单个换行结尾", text.endswith("\n") and not text.endswith("\n\n"))
    before_entries = [e.strip() for e in
                      (AUDIT / "283期-生肖-失败.txt.before").read_text(encoding="utf-8").split("\n\n")
                      if e.strip()]
    check("失败TXT 恰为原文 − 该站且顺序不变",
          [e.strip() for e in entries] ==
          [e for e in before_entries if NAME not in e.splitlines()[0]],
          str([e.splitlines()[0] for e in entries]))

    report_lines = [l for l in SUCCESS_TXT.read_text(encoding="utf-8").splitlines() if l.strip()]
    check("283 成功报告未含该站（失败站本无成功行）",
          not any(l.endswith(" " + NAME) for l in report_lines))
    check("283 成功报告带站名行均 9 个互不重复生肖",
          all(len(set(l.split(" ")[0])) == 9 for l in report_lines
              if " " in l and len(l.split(" ")[0]) == 9))
    check("报告 + 失败清单 = 活跃站数",
          len(report_lines) + len(entries) == len(names_after),
          f"{len(report_lines)} + {len(entries)} vs {len(names_after)}")

    catalog = (ROOT / "tests" / "test_fixed_catalog.py").read_text(encoding="utf-8")
    cleanup = (ROOT / "tests" / "test_routine_cleanup.py").read_text(encoding="utf-8")
    check("目录测试已更新为 437", 'len(config["sources"]) == 437' in catalog)
    check("退役测试已纳入 " + NAME, f'"{NAME}":' in cleanup)

    print(f"PASS {len(passed)} / FAIL {len(failed)}")
    for item in failed:
        print("  FAIL", item)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
