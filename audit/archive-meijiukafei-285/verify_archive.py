# -*- coding: utf-8 -*-
r"""封存「美酒咖啡」的独立复验（只读，对照 audit\archive-meijiukafei-285\*.before）。"""

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

NAME = "美酒咖啡"
URL = "https://6yrtfjghvnb-0978dtuxfyh.xyz/read.php?tid=54123"
ISSUE = 285
SOURCES = ROOT / "config" / "sources.json"
ARCHIVED = ROOT / "config" / "archived_sources.json"
CACHE = ROOT / "cache" / "recent_10_cache.json"
BASE = ROOT.parent
COLLECT = BASE / "七类数据统一归纳" / f"{ISSUE}期-生肖.txt"
FAIL = BASE / "七类数据统一归纳失败" / f"{ISSUE}期-生肖-失败.txt"
FAIL_SHA = "102e4ec0f8633a2c6ba16c3b3a9915a47b845b0c57c1eaf5e48dce8c2286ce64"

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
    # 1) 活跃配置：438 → 437，且恰为「原文去掉该站」，其余逐字段未变
    before_active = json.loads((AUDIT / "sources.json.before").read_text(encoding="utf-8"))["sources"]
    now_active = json.loads(SOURCES.read_text(encoding="utf-8"))["sources"]
    check("活跃 438 → 437", (len(before_active), len(now_active)) == (438, 437),
          f"{(len(before_active), len(now_active))}")
    expected = [s for s in before_active if s["name"] != NAME]
    check("恰为原文去掉该站（顺序与逐字段不变）", expected == now_active)
    check("活跃内已无该站", all(s["name"] != NAME for s in now_active))
    check("该站原条目 URL 正确",
          [s for s in before_active if s["name"] == NAME][0]["url"] == URL)

    # 2) 封存：73 → 74，尾部为原条目深拷贝 + archived_at + reason
    before_arch = json.loads(
        (AUDIT / "archived_sources.json.before").read_text(encoding="utf-8")
    )["sources"]
    now_arch = json.loads(ARCHIVED.read_text(encoding="utf-8"))["sources"]
    check("封存 73 → 74", (len(before_arch), len(now_arch)) == (73, 74),
          f"{(len(before_arch), len(now_arch))}")
    check("既有 73 条逐字段未变", before_arch == now_arch[: len(before_arch)])
    added = now_arch[-1]
    check("末条为 美酒咖啡", added["source"]["name"] == NAME,
          str(added["source"]["name"]))
    check("末条 source 为原条目深拷贝",
          added["source"] == [s for s in before_active if s["name"] == NAME][0])
    check("末条带 archived_at", bool(added.get("archived_at")), str(added.get("archived_at")))
    check("末条 reason 记录站方登录墙证据",
          "登录" in str(added.get("reason", "")) and "157" in str(added.get("reason", "")),
          str(added.get("reason", ""))[:60])
    check("封存内该站唯一",
          sum(1 for e in now_arch if e["source"]["name"] == NAME) == 1)

    # 3) 缓存：438 → 437，按身份键恰移除该站，其余逐字段未变
    before_cache = json.loads((AUDIT / "recent_10_cache.json.before").read_text(encoding="utf-8"))
    now_cache = json.loads(CACHE.read_text(encoding="utf-8"))

    def key_of(entry: dict) -> str:
        return source_identity(source_from_dict(entry["source"])).key

    before_map = {key_of(e): e for e in before_cache["sources"]}
    now_map = {key_of(e): e for e in now_cache["sources"]}
    check("缓存 438 → 437", (len(before_cache["sources"]), len(now_cache["sources"])) == (438, 437),
          f"{(len(before_cache['sources']), len(now_cache['sources']))}")
    check("缓存窗口 / latest / schema / cycle 未变",
          now_cache["issues"] == before_cache["issues"]
          and now_cache["latest_issue"] == before_cache["latest_issue"]
          and now_cache["schema_version"] == before_cache["schema_version"]
          and now_cache["cycle"] == before_cache["cycle"])
    gone = set(before_map) - set(now_map)
    check("缓存恰移除 1 条且为该站",
          len(gone) == 1 and before_map[gone.pop()]["source"]["name"] == NAME,
          str(len(gone)))
    check("其余 437 条缓存条目逐字段未变",
          all(before_map[k] == v for k, v in now_map.items()))

    # 4) 失败清单：335 B/2 站 → 1 站（仅 赚钱之道），原文逐字、顺序不变
    original = entries_of((AUDIT / f"{ISSUE}期-生肖-失败.txt.before").read_text(encoding="utf-8"))
    check("开工前失败清单为投喂原文（sha 一致 / 2 站）",
          hashlib.sha256((AUDIT / f"{ISSUE}期-生肖-失败.txt.before").read_bytes()).hexdigest()
          == FAIL_SHA and [e.splitlines()[0].split()[1] for e in original] == [NAME, "赚钱之道"],
          str([e.splitlines()[0].split()[1] for e in original]))
    text = FAIL.read_text(encoding="utf-8")
    now_entries = entries_of(text)
    check("失败清单剩 1 站（赚钱之道）",
          [e.splitlines()[0].split()[1] for e in now_entries] == ["赚钱之道"],
          str([e.splitlines()[0].split()[1] for e in now_entries]))
    check("失败清单恰为原文去掉该站（逐字）",
          now_entries == [e for e in original if not e.startswith(f"失败 {NAME}")])
    check("失败清单已无该站", NAME not in text)
    check("失败清单单换行结尾", text.endswith("\n") and not text.endswith("\n\n"))

    # 5) 成功报告未被触碰；配置已提交
    check("成功报告未被本轮改动（字节一致）",
          COLLECT.read_bytes() == (AUDIT / f"{ISSUE}期-生肖.txt.before").read_bytes())
    diff = subprocess.run(["git", "diff", "--quiet", "--", "config/sources.json"],
                          cwd=ROOT)
    check("config 改动已暂存/提交（工作区无未提交差异）", diff.returncode == 0,
          str(diff.returncode))

    # 6) 按站对账：活跃 = 报告站行 + 失败站
    lines = [l for l in COLLECT.read_text(encoding="utf-8").splitlines() if l.strip()]
    inrep = {l.rsplit(" ", 1)[1] for l in lines if " " in l}
    check("活跃 437 = 报告 436 + 失败 1", len(now_active) == len(lines) + len(now_entries),
          f"{len(now_active)} vs {len(lines)}+{len(now_entries)}")
    check("报告缺失站恰为失败站",
          {s["name"] for s in now_active} - inrep == {"赚钱之道"},
          str({s["name"] for s in now_active} - inrep))

    print(f"\nPASS {PASS} / FAIL {FAILED}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
