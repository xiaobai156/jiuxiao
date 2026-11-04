r"""独立复验：对照 audit\archive-atmaogou-278\*.before 检查「阿猫阿狗」封存结果（只读）。"""

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

AUDIT = ROOT / "audit" / "archive-atmaogou-278"
ACTIVE = ROOT / "config" / "sources.json"
ARCHIVED = ROOT / "config" / "archived_sources.json"
CACHE = ROOT / "cache" / "recent_10_cache.json"
FAIL_TXT = ROOT.parent / "七类数据统一归纳失败" / "278期-生肖-失败.txt"
SUCCESS_TXT = ROOT.parent / "七类数据统一归纳" / "278期-生肖.txt"
NAME = "阿猫阿狗"
URL = "https://4-0oufiyhcjg-ipg0ojv.xyz/read.php?tid=73957"
SUCCESS_SHA = "350531d8b8ffdede78da34dcbec9936a3e6fd2fc53298dadfef70588d705fa06"

passed: list[str] = []
failed: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (passed if ok else failed).append(f"{name}{'' if ok else ' :: ' + detail}")


def load(path: pathlib.Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    backs = {p.name: load(AUDIT / f"{p.name}.before") for p in (ACTIVE, ARCHIVED, CACHE)}
    check("三份 .before 备份齐全", set(backs) == {"sources.json", "archived_sources.json", "recent_10_cache.json"}, str(sorted(backs)))

    active_before, active_after = backs["sources.json"], load(ACTIVE)
    archived_before, archived_after = backs["archived_sources.json"], load(ARCHIVED)
    cache_before, cache_after = backs["recent_10_cache.json"], load(CACHE)

    names_before = [item["name"] for item in active_before["sources"]]
    names_after = [item["name"] for item in active_after["sources"]]
    check("活跃 438 → 437", (len(names_before), len(names_after)) == (438, 437), f"{len(names_before)}/{len(names_after)}")
    check("活跃移除后顺序与其余字段逐条一致",
          [item for item in active_before["sources"] if item["name"] != NAME] == active_after["sources"])
    check("活跃列表按站名唯一", len(set(names_after)) == len(names_after))
    check(f"活跃不再含 {NAME}", NAME not in names_after)
    check("活跃顶层不含其他改动",
          {k: v for k, v in active_before.items() if k != "sources"} ==
          {k: v for k, v in active_after.items() if k != "sources"})

    removed = [item for item in active_before["sources"] if item["name"] == NAME]
    check("移除条目唯一且 URL 一致", len(removed) == 1 and removed[0]["url"] == URL, str(removed)[:120])

    check("封存 66 → 67", (len(archived_before["sources"]), len(archived_after["sources"])) == (66, 67),
          f"{len(archived_before['sources'])}/{len(archived_after['sources'])}")
    check("原有 66 条封存条目逐字段未变",
          archived_before["sources"] == archived_after["sources"][:66])
    new_entry = archived_after["sources"][-1]
    check("新封存条目字段集合 = {source, archived_at, reason}",
          set(new_entry) == {"source", "archived_at", "reason"}, str(sorted(new_entry)))
    check("新封存条目为原始配置深拷贝", new_entry["source"] == removed[0])
    check("新封存条目 reason 合规",
          new_entry["reason"].startswith("用户明确封存，不再抓取；278期抓取失败")
          and "不再抓取" in new_entry["reason"], new_entry["reason"][:80])
    check("archived_at 为本地时间戳",
          re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}", new_entry["archived_at"]) is not None,
          new_entry["archived_at"])
    archived_names = [e["source"]["name"] for e in archived_after["sources"]]
    check("封存内无重名", len(set(archived_names)) == len(archived_names))
    check("封存与活跃无交集", not (set(archived_names) & set(names_after)))
    check("封存顶层不含其他改动",
          {k: v for k, v in archived_before.items() if k != "sources"} ==
          {k: v for k, v in archived_after.items() if k != "sources"})

    key = source_identity(source_from_dict(removed[0])).key
    check("缓存移除的正是该站身份键",
          not [i for i in cache_after["sources"] if source_identity(source_from_dict(i["source"])).key == key])
    check("缓存 438 → 437", (len(cache_before["sources"]), len(cache_after["sources"])) == (438, 437),
          f"{len(cache_before['sources'])}/{len(cache_after['sources'])}")
    check("缓存其余条目顺序与内容逐条未变",
          [i for i in cache_before["sources"]
           if source_identity(source_from_dict(i["source"])).key != key] == cache_after["sources"])
    check("缓存窗口与 latest_issue 未变",
          (cache_before["issues"], cache_before["latest_issue"]) == (cache_after["issues"], cache_after["latest_issue"]))
    check("缓存身份键唯一", len({source_identity(source_from_dict(i["source"])).key for i in cache_after["sources"]}) == 437)

    text = FAIL_TXT.read_text(encoding="utf-8")
    entries = [e for e in text.split("\n\n") if e.strip()]
    check("278 失败TXT 剩 1 条", len(entries) == 1, str(len(entries)))
    check("278 失败TXT 保留 六六大顺 且原文未变",
          entries[0].startswith("失败 六六大顺 ") and "阶段: 数据数量校验" in entries[0], entries[0][:60])
    check("278 失败TXT 已无 " + NAME, NAME not in text)
    check("278 失败TXT 以单个换行结尾", text.endswith("\n") and not text.endswith("\n\n"))

    success_raw = SUCCESS_TXT.read_bytes()
    check("278 成功报告未被封存触碰（436 行 / sha 一致）",
          len(success_raw.decode("utf-8").splitlines()) == 436
          and hashlib.sha256(success_raw).hexdigest() == SUCCESS_SHA,
          f"{len(success_raw.decode('utf-8').splitlines())} 行 sha={hashlib.sha256(success_raw).hexdigest()[:12]}")

    catalog = (ROOT / "tests" / "test_fixed_catalog.py").read_text(encoding="utf-8")
    cleanup = (ROOT / "tests" / "test_routine_cleanup.py").read_text(encoding="utf-8")
    check("目录测试已更新为 437", 'len(config["sources"]) == 437' in catalog)
    check("退役测试已纳入 阿猫阿狗", f'"{NAME}": "{URL}"' in cleanup)

    print(f"PASS {len(passed)} / FAIL {len(failed)}")
    for item in failed:
        print("  FAIL", item)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
