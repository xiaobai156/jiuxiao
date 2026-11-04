# -*- coding: utf-8 -*-
r"""封存「半斤八两」的独立复验（只读，对照 audit\archive-banjinbaliang-287\*.before）。"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDIT = Path(__file__).resolve().parent
if "v2" not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        "v2", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
    )
    pkg = importlib.util.module_from_spec(spec)
    sys.modules["v2"] = pkg
    spec.loader.exec_module(pkg)

from v2.config.schema import source_from_dict  # noqa: E402
from v2.domain.identity import source_identity  # noqa: E402

NAME = "半斤八两"
URL = (
    "https://xozgdo.um2zi-vbge0-emngyq.work:29422/article/admin/"
    "6a3a0ec4018539c611cb9d94?url=sgnn"
)
ISSUE = 287
SOURCES = ROOT / "config" / "sources.json"
ARCHIVED = ROOT / "config" / "archived_sources.json"
CACHE = ROOT / "cache" / "recent_10_cache.json"
BASE = ROOT.parent
COLLECT = BASE / "七类数据统一归纳" / f"{ISSUE}期-生肖.txt"
FAIL = BASE / "七类数据统一归纳失败" / f"{ISSUE}期-生肖-失败.txt"
FAIL_SHA = "6c493abc851947f6445731fdafd77f15b0bac0cd9712885aba00d96d8d0074f3"
BEFORE_STATIONS = ["勇闯无畏", "半斤八两", "诗情画意"]
AFTER_STATIONS = ["勇闯无畏", "诗情画意"]

PASS = FAILED = 0


def check(label: str, condition: bool, extra: str = "") -> None:
    global PASS, FAILED
    if condition:
        PASS += 1
        print(f"PASS {label}")
    else:
        FAILED += 1
        print(f"FAIL {label} {extra}")


def entries_of(text: str) -> list[str]:
    return [e.strip() for e in text.split("\n\n") if e.strip()]


def main() -> int:
    # 1) 活跃配置：439 → 438，且恰为「原文去掉该站」，其余逐字段未变
    before_active = json.loads((AUDIT / "sources.json.before").read_text(encoding="utf-8"))["sources"]
    now_active = json.loads(SOURCES.read_text(encoding="utf-8"))["sources"]
    check("活跃 439 → 438", (len(before_active), len(now_active)) == (439, 438),
          f"{(len(before_active), len(now_active))}")
    expected = [s for s in before_active if s["name"] != NAME]
    check("恰为原文去掉该站（顺序与逐字段不变）", expected == now_active)
    check("活跃内已无该站", all(s["name"] != NAME for s in now_active))
    check("该站原条目 URL 正确",
          [s for s in before_active if s["name"] == NAME][0]["url"] == URL)

    # 2) 封存：75 → 76，尾部为原条目深拷贝 + archived_at + reason
    before_arch = json.loads(
        (AUDIT / "archived_sources.json.before").read_text(encoding="utf-8")
    )["sources"]
    now_arch = json.loads(ARCHIVED.read_text(encoding="utf-8"))["sources"]
    check("封存 75 → 76", (len(before_arch), len(now_arch)) == (75, 76),
          f"{(len(before_arch), len(now_arch))}")
    check("既有 75 条逐字段未变", before_arch == now_arch[: len(before_arch)])
    added = now_arch[-1]
    check("末条为 半斤八两", added["source"]["name"] == NAME, str(added["source"]["name"]))
    check("末条 source 为原条目深拷贝",
          added["source"] == [s for s in before_active if s["name"] == NAME][0])
    check("末条带 archived_at", bool(added.get("archived_at")), str(added.get("archived_at")))
    reason = str(added.get("reason", ""))
    check("末条 reason 记录删文证据（404 / AdminArticle 不存在）",
          "404" in reason and "AdminArticle" in reason and "195729" in reason, reason[:60])
    check("封存内该站唯一", sum(1 for e in now_arch if e["source"]["name"] == NAME) == 1)

    # 3) 缓存：439 → 438，按身份键恰移除该站，其余逐字段未变
    before_cache = json.loads((AUDIT / "recent_10_cache.json.before").read_text(encoding="utf-8"))
    now_cache = json.loads(CACHE.read_text(encoding="utf-8"))

    def key_of(entry: dict) -> str:
        return source_identity(source_from_dict(entry["source"])).key

    before_map = {key_of(e): e for e in before_cache["sources"]}
    now_map = {key_of(e): e for e in now_cache["sources"]}
    check("缓存 439 → 438", (len(before_cache["sources"]), len(now_cache["sources"])) == (439, 438),
          f"{(len(before_cache['sources']), len(now_cache['sources']))}")
    check("缓存窗口 / latest / schema / cycle 未变",
          now_cache["issues"] == before_cache["issues"]
          and now_cache["latest_issue"] == before_cache["latest_issue"]
          and now_cache["schema_version"] == before_cache["schema_version"]
          and now_cache["cycle"] == before_cache["cycle"])
    gone = set(before_map) - set(now_map)
    check("缓存恰移除 1 条且为该站",
          len(gone) == 1 and before_map[next(iter(gone))]["source"]["name"] == NAME,
          str(len(gone)))
    check("其余 438 条缓存条目逐字段未变",
          all(before_map[k] == v for k, v in now_map.items()))

    # 4) 失败清单：758 B / 3 站 → 557 B / 2 站，原文逐字、顺序不变
    before_path = AUDIT / f"{ISSUE}期-生肖-失败.txt.before"
    original = entries_of(before_path.read_text(encoding="utf-8"))
    check("开工前失败清单为投喂原文（sha 一致 / 3 站）",
          hashlib.sha256(before_path.read_bytes()).hexdigest() == FAIL_SHA
          and [e.splitlines()[0].split()[1] for e in original] == BEFORE_STATIONS,
          str([e.splitlines()[0].split()[1] for e in original]))
    text = FAIL.read_text(encoding="utf-8")
    now_entries = entries_of(text)
    check("失败清单剩 2 站",
          [e.splitlines()[0].split()[1] for e in now_entries] == AFTER_STATIONS,
          str([e.splitlines()[0].split()[1] for e in now_entries]))
    check("失败清单恰为原文去掉该站（逐字、顺序不变）",
          now_entries == [e for e in original if not e.startswith(f"失败 {NAME}")])
    check("失败清单已无该站", NAME not in text)
    check("失败清单单换行结尾", text.endswith("\n") and not text.endswith("\n\n"))

    # 5) 成功报告：未写入该站，且本轮救回的两站在册、其余失败站不在册
    report = COLLECT.read_text(encoding="utf-8")
    rlines = [l.strip() for l in report.splitlines() if l.strip()]
    check("报告无该站行", not [l for l in rlines if l.endswith(f" {NAME}")])
    check("报告保留本轮救回两站行",
          [l for l in rlines if l.endswith(" 赢码公司")] == ["狗猴虎龙马鼠兔羊猪 赢码公司"]
          and [l for l in rlines if l.endswith(" 月影舞华")] == ["鸡猪虎鼠牛兔狗蛇龙 月影舞华"])
    check("报告仍无其余失败站行",
          not [l for l in rlines if l.endswith(tuple(f" {n}" for n in AFTER_STATIONS))])

    # 6) 按站对账：活跃 = 报告命中活跃站 + 失败站
    active_names = {s["name"] for s in now_active}
    inrep = {l.rsplit(" ", 1)[1] for l in rlines if " " in l}
    missing = active_names - inrep
    check("报告缺失站恰为 2 个失败站", missing == set(AFTER_STATIONS), str(sorted(missing)))
    check("活跃 438 = 报告命中活跃站 + 失败 2",
          len(now_active) == len(inrep & active_names) + len(now_entries),
          f"{len(now_active)} vs {len(inrep & active_names)}+{len(now_entries)}")

    # 7) 配置改动已提交
    diff = subprocess.run(["git", "diff", "--quiet", "--", "config/sources.json",
                           "config/archived_sources.json"], cwd=ROOT)
    check("config 改动已暂存/提交（工作区无未提交差异）", diff.returncode == 0, str(diff.returncode))

    print(f"\nPASS {PASS} / FAIL {FAILED}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
