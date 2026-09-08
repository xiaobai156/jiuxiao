from __future__ import annotations

import asyncio
import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from v2.domain.identity import source_identity
from v2.domain.models import Result
from v2.services.golden import (
    GoldenComparator,
    GoldenSnapshot,
)
from v2.storage.golden import GoldenReportRepository, GoldenRepository


@dataclass(frozen=True, slots=True)
class ShadowDifference:
    identity_key: str
    source_name: str
    issue: int
    expected: str
    actual: str


@dataclass(frozen=True, slots=True)
class ShadowReport:
    differences: tuple[ShadowDifference, ...]

    @property
    def equal(self) -> bool:
        return not self.differences


class ShadowComparator:
    def compare(
        self,
        expected: tuple[Result, ...],
        actual: tuple[Result, ...],
        issues: tuple[int, ...],
    ) -> ShadowReport:
        expected_by_key = self._by_identity(expected)
        actual_by_key = self._by_identity(actual)
        ordered_keys = tuple(
            dict.fromkeys((*expected_by_key.keys(), *actual_by_key.keys()))
        )
        differences: list[ShadowDifference] = []
        for key in ordered_keys:
            expected_result = expected_by_key.get(key)
            actual_result = actual_by_key.get(key)
            source = (
                expected_result.source
                if expected_result is not None
                else actual_result.source
            )
            for issue in issues:
                left = self._value(expected_result, issue)
                right = self._value(actual_result, issue)
                if left != right:
                    differences.append(
                        ShadowDifference(key, source.name, issue, left, right)
                    )
        return ShadowReport(tuple(differences))

    @staticmethod
    def _by_identity(results: tuple[Result, ...]) -> dict[str, Result]:
        indexed: dict[str, Result] = {}
        for result in results:
            key = source_identity(result.source).key
            if key in indexed:
                raise ValueError("duplicate result identity")
            indexed[key] = result
        return indexed

    @staticmethod
    def _value(result: Result | None, issue: int) -> str:
        if result is None:
            return "MISSING_SOURCE"
        records = result.history.records_for(issue)
        if len(records) == 1:
            return records[0].zodiac_text
        for failure in result.failures:
            context = dict(failure.context)
            if "issue" not in context or context["issue"] == str(issue):
                return failure.code.value
        return "ISSUE_MISSING"


class SnapshotRunner(Protocol):
    async def run(
        self,
        engine: str,
        issue: int,
        output_path: Path,
    ) -> GoldenSnapshot: ...


@dataclass(frozen=True, slots=True)
class ShadowRun:
    issue: int
    v1_snapshot_path: Path
    v2_snapshot_path: Path
    report_path: Path
    equal: bool
    difference_count: int


class ShadowRunService:
    def __init__(
        self,
        runner: SnapshotRunner,
        report_dir: Path,
        *,
        readonly_paths: tuple[Path, ...] = (),
    ) -> None:
        self._runner = runner
        self._report_dir = Path(report_dir)
        self._readonly_paths = tuple(Path(path) for path in readonly_paths)

    async def run(self, issue: int) -> ShadowRun:
        if not isinstance(issue, int) or isinstance(issue, bool) or issue <= 0:
            raise ValueError("issue must be a positive integer")
        before = self._readonly_digest()
        v1_path = self._report_dir / f"shadow-{issue}-v1.json"
        v2_path = self._report_dir / f"shadow-{issue}-v2.json"
        report_path = self._report_dir / f"shadow-{issue}-diff.json"
        v1, v2 = await asyncio.gather(
            self._runner.run("v1", issue, v1_path),
            self._runner.run("v2", issue, v2_path),
        )
        if before != self._readonly_digest():
            raise RuntimeError("shadow run changed a read-only V1 file")
        self._validate_snapshot(v1, "v1", issue)
        self._validate_snapshot(v2, "v2", issue)
        report = GoldenComparator().compare(v1, v2)
        GoldenReportRepository(report_path).write(report)
        return ShadowRun(
            issue=issue,
            v1_snapshot_path=v1_path,
            v2_snapshot_path=v2_path,
            report_path=report_path,
            equal=report.equal,
            difference_count=len(report.differences),
        )

    def _readonly_digest(self) -> tuple[tuple[str, str], ...]:
        return tuple(
            (
                str(path.resolve()),
                hashlib.sha256(path.read_bytes()).hexdigest()
                if path.exists()
                else "MISSING",
            )
            for path in self._readonly_paths
        )

    @staticmethod
    def _validate_snapshot(
        snapshot: GoldenSnapshot,
        engine: str,
        issue: int,
    ) -> None:
        if snapshot.engine != engine or snapshot.issues != (issue,):
            raise ValueError(f"invalid {engine} shadow snapshot")


class SubprocessSnapshotRunner:
    MODULES = {
        "v1": "v2.tests.golden.export_v1",
        "v2": "v2.tests.golden.export_v2",
    }

    def __init__(
        self,
        project_root: Path,
        *,
        concurrency: int = 10,
        retries: int = 3,
        executable: str | None = None,
    ) -> None:
        if concurrency <= 0 or retries <= 0:
            raise ValueError("concurrency and retries must be positive")
        self._project_root = Path(project_root).resolve()
        self._concurrency = concurrency
        self._retries = retries
        self._executable = executable or sys.executable

    async def run(
        self,
        engine: str,
        issue: int,
        output_path: Path,
    ) -> GoldenSnapshot:
        try:
            module = self.MODULES[engine]
        except KeyError as exc:
            raise ValueError(f"unsupported shadow engine: {engine}") from exc
        command = [
            self._executable,
            "-m",
            module,
            "--project-root",
            str(self._project_root),
            "--output",
            str(output_path),
            "--concurrency",
            str(self._concurrency),
            "--issue",
            str(issue),
        ]
        if engine == "v1":
            command.extend(("--retries", str(self._retries)))
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=self._project_root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            detail = stderr.decode("utf-8", errors="replace").strip()
            if not detail:
                detail = stdout.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"{engine} shadow process failed: {detail}")
        return GoldenRepository(output_path).load()
