from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from v2.config.repository import SourceRepository
from v2.storage.switching import BatSwitchStorage


@dataclass(frozen=True, slots=True)
class PreflightCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class PreflightReport:
    checks: tuple[PreflightCheck, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)


class SwitchPreflightService:
    def __init__(
        self,
        project_root: Path,
        *,
        expected_active: int = 320,
        expected_archived: int = 16,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.expected_active = expected_active
        self.expected_archived = expected_archived

    def check(self) -> PreflightReport:
        return PreflightReport(
            (
                self._approval_check(),
                self._source_count_check(),
                self._v1_hash_check(),
                self._v2_entrypoint_check(),
                self._transaction_check(),
            )
        )

    def _approval_check(self) -> PreflightCheck:
        path = (
            self.project_root
            / "v2"
            / "reviews"
            / "step-08-approval-required.json"
        )
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            passed = (
                document.get("status") == "APPROVED"
                and document.get("user_confirmation") is True
            )
        except (OSError, json.JSONDecodeError):
            passed = False
        return PreflightCheck(
            "step_08_approval",
            passed,
            "Step 08 approved" if passed else "Step 08 approval missing",
        )

    def _source_count_check(self) -> PreflightCheck:
        try:
            repository = SourceRepository(
                self.project_root / "v2" / "config" / "sources.json",
                self.project_root / "v2" / "config" / "archived_sources.json",
            )
            active = len(repository.load_active())
            archived = len(repository.load_archived())
            passed = (
                active == self.expected_active
                and archived == self.expected_archived
            )
            detail = f"active={active}, archived={archived}"
        except Exception as exc:
            passed = False
            detail = f"configuration invalid: {type(exc).__name__}"
        return PreflightCheck("source_counts", passed, detail)

    def _v1_hash_check(self) -> PreflightCheck:
        manifest_path = self.project_root / "v2" / "baseline" / "manifest.json"
        try:
            document = json.loads(manifest_path.read_text(encoding="utf-8"))
            entries = document["v1_files"]
            if not isinstance(entries, list) or not entries:
                raise ValueError("empty manifest")
            mismatches: list[str] = []
            for item in entries:
                relative = Path(str(item["path"]))
                target = (self.project_root / relative).resolve()
                if self.project_root not in target.parents:
                    raise ValueError("manifest path escaped project root")
                actual = (
                    hashlib.sha256(target.read_bytes()).hexdigest()
                    if target.is_file()
                    else "MISSING"
                )
                if actual != str(item["sha256"]):
                    mismatches.append(str(relative))
            passed = not mismatches
            detail = (
                f"checked={len(entries)}, mismatches=0"
                if passed
                else "mismatches=" + ", ".join(mismatches)
            )
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            passed = False
            detail = f"manifest invalid: {type(exc).__name__}"
        return PreflightCheck("v1_hashes", passed, detail)

    def _v2_entrypoint_check(self) -> PreflightCheck:
        names = (
            "__main__.py",
            BatSwitchStorage.V2_SINGLE_BAT,
            BatSwitchStorage.V2_RANGE_BAT,
        )
        missing = [name for name in names if not (self.project_root / "v2" / name).is_file()]
        passed = not missing
        detail = "all V2 entrypoints exist" if passed else "missing=" + ", ".join(missing)
        return PreflightCheck("v2_entrypoints", passed, detail)

    def _transaction_check(self) -> PreflightCheck:
        residues = sorted(
            path.relative_to(self.project_root).as_posix()
            for path in self.project_root.rglob(".*transaction*.json")
            if path.is_file()
        )
        passed = not residues
        detail = "no transaction residue" if passed else "residue=" + ", ".join(residues)
        return PreflightCheck("transaction_residue", passed, detail)


class SwitchService:
    def __init__(
        self,
        preflight: SwitchPreflightService,
        storage: BatSwitchStorage,
    ) -> None:
        self._preflight = preflight
        self._storage = storage

    def switch(self) -> PreflightReport:
        report = self._preflight.check()
        if not report.passed:
            raise RuntimeError("switch preflight failed")
        self._storage.switch()
        return report

    def rollback(self) -> None:
        self._storage.rollback()
