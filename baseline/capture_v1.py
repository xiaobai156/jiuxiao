from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


CRITICAL_V1_FILES = (
    "AGENTS.md",
    "crawler.py",
    "detect_duplicates.py",
    "multi_issue_crawler.py",
    "verify_failed_sites.py",
    "audit_dynamic_record_ids.py",
    "audit_static_vs_dom.py",
    "test_crawler.py",
    "test_detect_duplicates.py",
    "test_verify_failed_sites.py",
    "extra_sources.json",
    "archived_extra_sources.json",
    "recent_10_cache.json",
    "recent_10_cache_audit_issues.txt",
    "baseline_top_bottom.json",
    "zodiac_spec_groups.json",
    "failed_site_targets.json",
    "duplicate_baseline_10.json",
    "爬虫-多期抓取灵蛇生肖.bat",
    "爬虫-爬取灵蛇生肖.bat",
)

SOURCE_IDENTITY_FIELDS = ("name", "url", "position", "section_marker")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ordered_source_digest(sources: list[dict[str, Any]]) -> str:
    identities = [
        {
            field: str(source.get(field, "")).strip()
            for field in SOURCE_IDENTITY_FIELDS
        }
        for source in sources
    ]
    payload = json.dumps(
        identities,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256_bytes(payload)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _require_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} 必须是 JSON 对象")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} 必须是 JSON 数组")
    return value


def _file_snapshot(project_root: Path, relative_path: str) -> dict[str, Any]:
    path = project_root / relative_path
    stat = path.stat()
    return {
        "path": relative_path,
        "size": stat.st_size,
        "mtime_utc": datetime.fromtimestamp(
            stat.st_mtime,
            ZoneInfo("UTC"),
        ).isoformat(timespec="seconds"),
        "sha256": sha256_file(path),
    }


def _default_capture_time() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


def build_manifest(
    project_root: Path,
    *,
    captured_at: str | None = None,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    for relative_path in CRITICAL_V1_FILES:
        path = project_root / relative_path
        if not path.is_file():
            raise FileNotFoundError(path)

    active_sources = _require_list(
        _read_json(project_root / "extra_sources.json"),
        "extra_sources.json",
    )
    archived_document = _require_dict(
        _read_json(project_root / "archived_extra_sources.json"),
        "archived_extra_sources.json",
    )
    archived_sources = _require_list(
        archived_document.get("sources"),
        "archived_extra_sources.json.sources",
    )
    cache = _require_dict(
        _read_json(project_root / "recent_10_cache.json"),
        "recent_10_cache.json",
    )
    cache_sources = _require_list(
        cache.get("sources"),
        "recent_10_cache.json.sources",
    )
    cache_source_specs = [
        _require_dict(item, "recent_10_cache.json.sources[]").get("source", {})
        for item in cache_sources
    ]

    return {
        "schema_version": 1,
        "captured_at": captured_at or _default_capture_time(),
        "project_root": str(project_root),
        "environment": {
            "python": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "playwright": importlib.metadata.version("playwright"),
        },
        "v1_files": [
            _file_snapshot(project_root, relative_path)
            for relative_path in CRITICAL_V1_FILES
        ],
        "active_sources": {
            "count": len(active_sources),
            "ordered_identity_sha256": ordered_source_digest(active_sources),
            "file_sha256": sha256_file(project_root / "extra_sources.json"),
        },
        "archived_sources": {
            "count": len(archived_sources),
            "ordered_identity_sha256": ordered_source_digest(archived_sources),
            "file_sha256": sha256_file(
                project_root / "archived_extra_sources.json"
            ),
        },
        "cache": {
            "latest_issue": int(cache["latest_issue"]),
            "issues": [int(issue) for issue in cache["issues"]],
            "declared_source_count": int(cache["source_count"]),
            "actual_source_count": len(cache_sources),
            "issue_basis": str(cache.get("issue_basis", "")),
            "ordered_identity_sha256": ordered_source_digest(cache_source_specs),
            "file_sha256": sha256_file(project_root / "recent_10_cache.json"),
        },
    }


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def capture_baseline(
    project_root: Path,
    output_dir: Path,
    *,
    captured_at: str | None = None,
) -> Path:
    project_root = project_root.resolve()
    output_dir = output_dir.resolve()
    manifest = build_manifest(project_root, captured_at=captured_at)
    copies = {
        "active_sources.json": project_root / "extra_sources.json",
        "archived_sources.json": project_root / "archived_extra_sources.json",
        "recent_10_cache.json": project_root / "recent_10_cache.json",
    }
    for target_name, source_path in copies.items():
        _atomic_write(output_dir / target_name, source_path.read_bytes())

    manifest_path = output_dir / "manifest.json"
    manifest_data = (
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    _atomic_write(manifest_path, manifest_data)
    return manifest_path


def parse_args() -> argparse.Namespace:
    default_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="捕获 V1 只读黄金基准。")
    parser.add_argument("--project-root", type=Path, default=default_root)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parent)
    parser.add_argument("--captured-at", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest_path = capture_baseline(
        args.project_root,
        args.output_dir,
        captured_at=args.captured_at,
    )
    print(f"V1 基准已捕获: {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
