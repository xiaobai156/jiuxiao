r"""封存 半斤八两（287 期失败：站方删除文章，接口 404 AdminArticle 不存在）。

流程：备份 → 活跃移除 → 封存追加原始条目深拷贝 + reason
      → 缓存整条移除 → 287 失败TXT 清除该站记录（保留其他记录及其顺序）。
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
AUDIT = ROOT / "audit" / "archive-banjinbaliang-287"
ACTIVE_PATH = ROOT / "config" / "sources.json"
ARCHIVED_PATH = ROOT / "config" / "archived_sources.json"
CACHE_PATH = ROOT / "cache" / "recent_10_cache.json"
FAIL_TXT = BASE / "七类数据统一归纳失败" / "287期-生肖-失败.txt"
TARGETS = ["半斤八两"]
REASONS = {
    "半斤八两": (
        "用户点名封存，不再抓取；287期抓取失败：站方删除文章，接口返回 404。"
        "证据：manager-articles 接口 /api/proxy/manager-articles/6a3a0ec4018539c611cb9d94 → "
        "HTTP 404 / 73 B {\"message\":\"AdminArticle 不存在\",\"error\":\"Not Found\",\"statusCode\":404}；"
        "浏览器渲染后正文仅 45 字符「Failed to fetch」，8 个 script 文档对「风雨雷电/287/286/九肖/开」命中全为 0；"
        "同宿主对照站「攻城略地」接口正常（HTTP 200 / 195729 B，缓存 current_issue=287）⇒ 属该篇被站方删除，非站点整体故障。"
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
    paths = [ACTIVE_PATH, ARCHIVED_PATH, CACHE_PATH, FAIL_TXT]
    for path in paths:
        if not (AUDIT / f"{path.name}.before").exists():
            (AUDIT / f"{path.name}.before").write_bytes(path.read_bytes())

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

    fail_text = FAIL_TXT.read_text(encoding="utf-8")
    kept, dropped = [], []
    for entry in fail_text.split("\n\n"):
        if not entry.strip():
            continue
        match = NAME_RE.match(entry.splitlines()[0])
        assert match, entry[:60]
        name = match.group(1)
        if name in TARGETS:
            dropped.append(name)
        else:
            # 必须 strip：split("\n\n") 会让「末条目」带上自己的尾换行，
            # 若删除的是首条目、保留末条目，直接 join 会写出多余空行（\n\n 结尾）。
            kept.append(entry.strip())
    assert sorted(dropped) == sorted(TARGETS), dropped
    assert kept, "其余失败记录不得被清空"
    atomic_write_bytes(FAIL_TXT, ("\n\n".join(kept) + "\n").encode("utf-8"))
    print(f"  失败TXT 清除 {sorted(dropped)}，保留 {len(kept)} 条")

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
    after_fail = FAIL_TXT.read_text(encoding="utf-8")
    assert "半斤八两" not in after_fail and after_fail.strip()

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
        f"完成: 活跃 {len(active2)} / 封存 {len(archived2)} / "
        f"缓存 {len(cache_after['sources'])} / 失败TXT {len(kept)} 条"
    )
    print(f"审计: {AUDIT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
