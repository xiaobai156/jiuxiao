from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

from v2.storage.atomic import atomic_write_many


ReplaceFunction = Callable[[Path, Path], None]


class BatSwitchStorage:
    SINGLE_BAT = "爬虫-爬取灵蛇生肖.bat"
    RANGE_BAT = "爬虫-多期抓取灵蛇生肖.bat"
    V2_SINGLE_BAT = "爬虫-爬取灵蛇生肖-V2.bat"
    V2_RANGE_BAT = "爬虫-多期抓取灵蛇生肖-V2.bat"

    def __init__(
        self,
        project_root: Path,
        *,
        _replace: ReplaceFunction | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.backup_dir = self.project_root / "v2" / "switch-backup"
        self._replace = _replace

    def switch(self) -> None:
        originals = self._official_bytes()
        self._ensure_v2_entrypoints()
        self._ensure_backup(originals)
        payloads = {
            self.project_root / self.SINGLE_BAT: self._wrapper(self.V2_SINGLE_BAT),
            self.project_root / self.RANGE_BAT: self._wrapper(self.V2_RANGE_BAT),
        }
        atomic_write_many(
            payloads,
            self.project_root / ".v2-switch-transaction.json",
            _replace=self._replace,
        )

    def rollback(self) -> None:
        originals = self._load_backup()
        atomic_write_many(
            {
                self.project_root / self.SINGLE_BAT: originals[self.SINGLE_BAT],
                self.project_root / self.RANGE_BAT: originals[self.RANGE_BAT],
            },
            self.project_root / ".v2-switch-transaction.json",
            _replace=self._replace,
        )

    def _official_bytes(self) -> dict[str, bytes]:
        result: dict[str, bytes] = {}
        for name in (self.SINGLE_BAT, self.RANGE_BAT):
            path = self.project_root / name
            if not path.is_file():
                raise FileNotFoundError(path)
            result[name] = path.read_bytes()
        return result

    def _ensure_v2_entrypoints(self) -> None:
        for name in (self.V2_SINGLE_BAT, self.V2_RANGE_BAT):
            path = self.project_root / "v2" / name
            if not path.is_file():
                raise FileNotFoundError(path)

    def _ensure_backup(self, originals: dict[str, bytes]) -> None:
        manifest_path = self.backup_dir / "manifest.json"
        if manifest_path.exists():
            existing = self._load_backup()
            if existing != originals:
                raise RuntimeError("existing V1 BAT backup does not match official BATs")
            return
        document = {
            "schema_version": 1,
            "files": {
                name: hashlib.sha256(content).hexdigest()
                for name, content in originals.items()
            },
        }
        payloads = {
            self.backup_dir / name: content
            for name, content in originals.items()
        }
        payloads[manifest_path] = (
            json.dumps(document, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
        atomic_write_many(
            payloads,
            self.backup_dir / ".backup-transaction.json",
            _replace=self._replace,
        )

    def _load_backup(self) -> dict[str, bytes]:
        manifest_path = self.backup_dir / "manifest.json"
        try:
            document = json.loads(manifest_path.read_text(encoding="utf-8"))
            if document.get("schema_version") != 1:
                raise ValueError("invalid backup schema")
            expected = document.get("files")
            if not isinstance(expected, dict) or set(expected) != {
                self.SINGLE_BAT,
                self.RANGE_BAT,
            }:
                raise ValueError("invalid backup manifest")
            result: dict[str, bytes] = {}
            for name, digest in expected.items():
                content = (self.backup_dir / name).read_bytes()
                if hashlib.sha256(content).hexdigest() != digest:
                    raise ValueError(f"invalid backup hash: {name}")
                result[name] = content
            return result
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError("V1 BAT backup is missing or invalid") from exc

    @staticmethod
    def _wrapper(v2_bat_name: str) -> bytes:
        text = (
            "@echo off\r\n"
            "chcp 65001 >nul\r\n"
            f'call "%~dp0v2\\{v2_bat_name}"\r\n'
        )
        return text.encode("utf-8")
