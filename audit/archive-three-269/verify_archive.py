r"""独立复验：对照 audit\archive-three-269\*.before 检查封存结果。

只读，不写任何正式文件。
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT.parent
AUDIT = ROOT / "audit" / "archive-three-269"
TARGETS = ("风铃歌", "归隐山林", "尽心竭力")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    before_active = load(AUDIT / "sources.json.before")
    after_active = load(ROOT / "config" / "sources.json")
    before_arch = load(AUDIT / "archived_sources.json.before")
    after_arch = load(ROOT / "config" / "archived_sources.json")
    before_cache = load(AUDIT / "recent_10_cache.json.before")
    after_cache = load(ROOT / "cache" / "recent_10_cache.json")

    def names(doc: dict) -> list[str]:
        return [item["name"] for item in doc["sources"]]

    expected_active = [n for n in names(before_active) if n not in TARGETS]
    assert names(after_active) == expected_active, "活跃顺序/内容不符"
    assert len(after_active["sources"]) == len(before_active["sources"]) - 3
    assert after_active["sources"] == [
        item for item in before_active["sources"] if item["name"] not in TARGETS
    ], "活跃条目有非目标改动"

    assert after_arch["sources"][: len(before_arch["sources"])] == before_arch[
        "sources"
    ], "原有封存条目被改动"
    added = after_arch["sources"][len(before_arch["sources"]) :]
    assert [entry["source"]["name"] for entry in added] == list(TARGETS)
    for entry in added:
        assert entry["archived_at"].endswith("+08:00")
        assert entry["reason"].startswith("用户明确封存，不再抓取；269期抓取失败")

    def dropped_cache() -> list[dict]:
        return [
            item
            for item in before_cache["sources"]
            if item["source"]["name"] in TARGETS
        ]

    removed = dropped_cache()
    assert len(removed) == 3, f"改动前缓存目标条目 {len(removed)}"
    kept_before = [
        item for item in before_cache["sources"] if item["source"]["name"] not in TARGETS
    ]
    assert after_cache["sources"] == kept_before, "缓存非目标条目被改动"
    assert after_cache["issues"] == before_cache["issues"]
    assert after_cache["latest_issue"] == before_cache["latest_issue"]
    assert after_cache["schema_version"] == before_cache["schema_version"]
    for item in removed:
        assert not [
            e
            for e in after_cache["sources"]
            if e["source"]["url"] == item["source"]["url"]
            and e["source"]["position"] == item["source"]["position"]
        ], f'{item["source"]["name"]} 精确身份仍在缓存'

    fail_txt = BASE / "七类数据统一归纳失败" / "269期-生肖-失败.txt"
    assert fail_txt.read_text(encoding="utf-8").strip() == "", "269 失败TXT 未清空"
    success = (BASE / "七类数据统一归纳" / "269期-生肖.txt").read_text(encoding="utf-8")
    for name in TARGETS:
        assert not any(line.endswith(" " + name) for line in success.splitlines())
    others = sorted(
        p.name
        for p in (BASE / "七类数据统一归纳失败").glob("*-失败.txt")
        if p.name != fail_txt.name
    )
    residue = {
        p: [n for n in TARGETS if n in (BASE / "七类数据统一归纳失败" / p).read_text(encoding="utf-8")]
        for p in others
    }
    residue = {k: v for k, v in residue.items() if v}
    print(
        f"复验通过: 活跃 {len(after_active['sources'])} / 封存 "
        f"{len(after_arch['sources'])} / 缓存 {len(after_cache['sources'])} / "
        f"269 失败TXT 空"
    )
    print(f"其它期失败TXT 残留（未处理，按当期口径）: {residue or '无'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
