from __future__ import annotations

import base64
import json
import os
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any


ReplaceFunction = Callable[[Path, Path], None]


def _stage_bytes(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        staged = Path(handle.name)
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    return staged


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path = Path(path)
    staged = _stage_bytes(path, data)
    try:
        os.replace(staged, path)
    finally:
        if staged.exists():
            staged.unlink()


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(Path(path), text.encode("utf-8"))


def _journal_document(paths: tuple[Path, ...]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "files": [
            {
                "name": path.name,
                "existed": path.exists(),
                "before": (
                    base64.b64encode(path.read_bytes()).decode("ascii")
                    if path.exists()
                    else ""
                ),
            }
            for path in paths
        ],
    }


def recover_atomic_batch(journal_path: Path) -> bool:
    journal_path = Path(journal_path)
    if not journal_path.exists():
        return False
    try:
        document = json.loads(journal_path.read_text(encoding="utf-8"))
        if document.get("schema_version") != 1:
            raise ValueError("不支持的事务日志版本")
        files = document.get("files")
        if not isinstance(files, list):
            raise ValueError("事务日志缺少 files")
        for item in files:
            if not isinstance(item, dict):
                raise ValueError("事务日志文件项无效")
            name = item.get("name")
            if (
                not isinstance(name, str)
                or not name
                or Path(name).name != name
            ):
                raise ValueError("事务日志文件名无效")
            target = journal_path.parent / name
            if item.get("existed") is True:
                encoded = item.get("before")
                if not isinstance(encoded, str):
                    raise ValueError("事务日志原始内容无效")
                atomic_write_bytes(target, base64.b64decode(encoded))
            elif target.exists():
                target.unlink()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("无法恢复原子事务") from exc
    journal_path.unlink()
    return True


def atomic_write_many(
    payloads: Mapping[Path, bytes],
    journal_path: Path,
    *,
    _replace: ReplaceFunction | None = None,
) -> None:
    if not payloads:
        raise ValueError("payloads 不能为空")
    journal_path = Path(journal_path)
    root = journal_path.parent.resolve()
    normalized = tuple(
        (Path(path), bytes(data)) for path, data in payloads.items()
    )
    if len({path.resolve() for path, _data in normalized}) != len(normalized):
        raise ValueError("目标路径不能重复")
    if any(path.parent.resolve() != root for path, _data in normalized):
        raise ValueError("批量原子写入要求所有文件位于同一目录")
    if journal_path.exists():
        recover_atomic_batch(journal_path)

    staged: dict[Path, Path] = {}
    paths = tuple(path for path, _data in normalized)
    try:
        for path, data in normalized:
            staged[path] = _stage_bytes(path, data)
        journal_data = (
            json.dumps(
                _journal_document(paths),
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        ).encode("utf-8")
        atomic_write_bytes(journal_path, journal_data)
        replace = _replace or os.replace
        for path in paths:
            replace(staged[path], path)
        journal_path.unlink()
    except Exception:
        if journal_path.exists():
            recover_atomic_batch(journal_path)
        raise
    finally:
        for temporary_path in staged.values():
            if temporary_path.exists():
                temporary_path.unlink()
