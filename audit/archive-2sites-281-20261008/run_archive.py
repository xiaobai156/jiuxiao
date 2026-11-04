r"""封存 风神九肖、炉火纯青（281 期：与既有活跃站近 10 期缓存逐期完全一致的同源镜像站）。

流程：备份 → 活跃移除 → 封存追加原始条目深拷贝 + reason
      → 缓存整条移除 → 281 失败TXT 若存在则清除这两站记录（本次两站均不在清单，内容应保持不变）。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if "v2" not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        "v2", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
    )
    pkg = importlib.util.module_from_spec(spec)
    sys.modules["v2"] = pkg
    spec.loader.exec_module(pkg)

from v2.config.schema import source_from_dict, source_to_dict  # noqa: E402
from v2.domain.identity import source_identity  # noqa: E402
from v2.storage.atomic import atomic_write_bytes  # noqa: E402

BASE = ROOT.parent
AUDIT = ROOT / "audit" / "archive-2sites-281-20261008"
ACTIVE_PATH = ROOT / "config" / "sources.json"
ARCHIVED_PATH = ROOT / "config" / "archived_sources.json"
CACHE_PATH = ROOT / "cache" / "recent_10_cache.json"
FAIL_TXT = BASE / "七类数据统一归纳失败" / "281期-生肖-失败.txt"
TARGETS = ["风神九肖", "炉火纯青"]
REASONS = {
    "风神九肖": (
        "用户明确封存，不再抓取；与活跃站「嫦娥奔月」在缓存窗口 272..281 期逐期记录完全一致"
        "（同源镜像），按用户点名保留其一并封存本站（2026-10-08 用户点名封存）"
    ),
    "炉火纯青": (
        "用户明确封存，不再抓取；与活跃站「朴斲之材」在缓存窗口 272..281 期逐期记录完全一致"
        "（同源镜像），按用户点名保留其一并封存本站（2026-10-08 用户点名封存）"
    ),
}
NAME_RE = re.compile(r"^失败\s+(\S+)\s+")


def local_stamp() -> str:
    now = datetime.now().astimezone()
    offset = now.strftime("%z")
    return now.strftime("%Y-%m-%dT%H:%M:%S") + offset[:3] + ":" + offset[3:]


def encode(document) -> bytes:
    return (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    from v2.config.repository import SourceRepository

    archived_at = local_stamp()
    AUDIT.mkdir(parents=True, exist_ok=True)
    paths = [ACTIVE_PATH, ARCHIVED_PATH, CACHE_PATH]
    for path in paths:
        if not (AUDIT / f"{path.name}.before").exists():
            (AUDIT / f"{path.name}.before").write_bytes(path.read_bytes())
    fail_existed = FAIL_TXT.exists()
    if fail_existed and not (AUDIT / f"{FAIL_TXT.name}.before").exists():
        (AUDIT / f"{FAIL_TXT.name}.before").write_bytes(FAIL_TXT.read_bytes())

    repo = SourceRepository(ACTIVE_PATH, ARCHIVED_PATH)
    active = repo.load_active()
    archived = repo.load_archived()
    print(f"改动前: 活跃 {len(active)} / 封存 {len(archived)} / 归档时间 {archived_at}")

    active_doc = json.loads(ACTIVE_PATH.read_text(encoding="utf-8"))
    archived_doc = json.loads(ARCHIVED_PATH.read_text(encoding="utf-8"))
    cache_doc = json.loads(CACHE_PATH.read_text(encoding="utf-8"))

    removed: dict[str, dict] = {}
    keys: dict[str, str] = {}
    for name in TARGETS:
        hits = [s for s in active if s.name == name]
        assert len(hits) == 1, f"{name} 活跃匹配 {len(hits)}"
        assert not [e for e in archived if e.source.name == name]
        source = hits[0]
        keys[name] = source_identity(source).key

        raw_index = [
            i for i, item in enumerate(active_doc["sources"]) if item["name"] == name
        ]
        assert len(raw_index) == 1
        raw = active_doc["sources"].pop(raw_index[0])
        assert source_from_dict(raw) == source
        removed[name] = raw

        archived_doc["sources"].append(
            {"source": raw, "archived_at": archived_at, "reason": REASONS[name]}
        )
        print(f"  移除活跃 + 追加封存: {name} ({keys[name][:12]})")

    for name in TARGETS:
        hits = [
            i
            for i, item in enumerate(cache_doc["sources"])
            if source_identity(source_from_dict(item["source"])).key == keys[name]
        ]
        assert len(hits) == 1, f"缓存 {name} 身份匹配 {len(hits)}"
        cache_doc["sources"].pop(hits[0])
        print(f"  移除缓存条目: {name}")

    remaining = tuple(source_from_dict(item) for item in active_doc["sources"])
    assert len(remaining) == len(active) - len(TARGETS)
    assert [source_to_dict(s) for s in remaining] == [
        source_to_dict(s) for s in active if s.name not in TARGETS
    ]
    assert len(archived_doc["sources"]) == len(archived) + len(TARGETS)
    before_cache_count = json.loads(CACHE_PATH.read_text("utf-8"))["sources"]
    assert len(cache_doc["sources"]) == len(before_cache_count) - len(TARGETS)

    atomic_write_bytes(ACTIVE_PATH, encode(active_doc))
    atomic_write_bytes(ARCHIVED_PATH, encode(archived_doc))
    atomic_write_bytes(CACHE_PATH, encode(cache_doc))

    kept: list[str] = []
    dropped: list[str] = []
    if fail_existed:
        fail_text = FAIL_TXT.read_text(encoding="utf-8")
        for entry in fail_text.split("\n\n"):
            if not entry.strip():
                continue
            match = NAME_RE.match(entry.splitlines()[0])
            assert match, entry[:60]
            name = match.group(1)
            if name in TARGETS:
                dropped.append(name)
            else:
                kept.append(entry)
        assert set(dropped) <= set(TARGETS), dropped
        assert kept, "其余失败记录不得被清空"
        atomic_write_bytes(FAIL_TXT, ("\n\n".join(kept) + "\n").encode("utf-8"))
        print(f"  失败TXT 清除 {sorted(dropped)}，保留 {len(kept)} 条")
    else:
        print("  281 失败TXT 当前不存在（两站本不在清单）——不新建、不写入")

    # 回读校验
    repo2 = SourceRepository(ACTIVE_PATH, ARCHIVED_PATH)
    active2 = repo2.load_active()
    archived2 = repo2.load_archived()
    assert len(active2) == len(active) - len(TARGETS)
    assert len(archived2) == len(archived) + len(TARGETS)
    assert not [s for s in active2 if s.name in TARGETS]
    assert [s.name for s in active2] == [s.name for s in active if s.name not in TARGETS]
    for name in TARGETS:
        entries = [e for e in archived2 if e.source.name == name]
        assert len(entries) == 1
        assert source_to_dict(entries[0].source) == removed[name]
        assert entries[0].reason == REASONS[name]
        assert entries[0].archived_at == archived_at
    assert [
        (e.source.name, e.archived_at, e.reason) for e in archived2[: len(archived)]
    ] == [(e.source.name, e.archived_at, e.reason) for e in archived]
    cache_after = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    assert not [i for i in cache_after["sources"] if i["source"]["name"] in TARGETS]
    assert cache_after["issues"] == cache_doc["issues"]
    assert cache_after["latest_issue"] == cache_doc["latest_issue"]
    assert len(cache_after["sources"]) == len(before_cache_count) - len(TARGETS)
    if fail_existed:
        after_fail = FAIL_TXT.read_text(encoding="utf-8")
        assert all(t not in after_fail for t in TARGETS)

    (AUDIT / "removed_entries.json").write_text(
        json.dumps(
            {
                "archived_at": archived_at,
                "reasons": REASONS,
                "entries": [{"source": removed[n]} for n in TARGETS],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (AUDIT / "after_state.json").write_text(
        json.dumps(
            {
                "active_count": len(active2),
                "archived_count": len(archived2),
                "cache_source_count": len(cache_after["sources"]),
                "failure_entries": len(kept),
                "failure_txt_present": fail_existed,
                "hashes_after": {
                    p.name: (sha(p) if p.exists() else "deleted") for p in paths
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"完成: 活跃 {len(active2)} / 封存 {len(archived2)} / 缓存 {len(cache_after['sources'])}"
    )
    print(f"审计: {AUDIT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
