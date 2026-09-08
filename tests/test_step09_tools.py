from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from v2.services.golden import (
    GoldenEntry,
    GoldenSnapshot,
    GoldenSource,
)
from v2.services.shadow import ShadowRunService
from v2.services.shadow import SubprocessSnapshotRunner
from v2.services.switching import SwitchPreflightService, SwitchService
from v2.storage.golden import GoldenRepository
from v2.storage.switching import BatSwitchStorage


SINGLE_BAT = "爬虫-爬取灵蛇生肖.bat"
RANGE_BAT = "爬虫-多期抓取灵蛇生肖.bat"
V2_SINGLE_BAT = "爬虫-爬取灵蛇生肖-V2.bat"
V2_RANGE_BAT = "爬虫-多期抓取灵蛇生肖-V2.bat"


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def snapshot(engine: str, issue: int, zodiac: str) -> GoldenSnapshot:
    return GoldenSnapshot(
        engine,
        (issue,),
        (
            GoldenSource(
                "identity-a",
                "甲",
                (GoldenEntry(issue, zodiac=zodiac),),
            ),
        ),
    )


class FakeSnapshotRunner:
    def __init__(self, guarded_path: Path | None = None) -> None:
        self.calls: list[tuple[str, int, Path]] = []
        self.guarded_path = guarded_path

    async def run(
        self,
        engine: str,
        issue: int,
        output_path: Path,
    ) -> GoldenSnapshot:
        self.calls.append((engine, issue, output_path))
        value = (
            "鼠牛虎兔龙蛇马羊猴"
            if engine == "v1"
            else "牛鼠虎兔龙蛇马羊猴"
        )
        result = snapshot(engine, issue, value)
        GoldenRepository(output_path).write(result)
        if engine == "v1" and self.guarded_path is not None:
            self.guarded_path.write_text("changed", encoding="utf-8")
        return result


class ShadowRunTests(unittest.IsolatedAsyncioTestCase):
    async def test_runs_both_engines_and_writes_identity_issue_diff(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            guarded = root / "crawler.py"
            guarded.write_text("readonly", encoding="utf-8")
            runner = FakeSnapshotRunner()
            service = ShadowRunService(
                runner,
                root / "reviews",
                readonly_paths=(guarded,),
            )

            run = await service.run(210)

            self.assertEqual(
                [(engine, issue) for engine, issue, _path in runner.calls],
                [("v1", 210), ("v2", 210)],
            )
            report = json.loads(run.report_path.read_text(encoding="utf-8"))
            self.assertFalse(report["equal"])
            self.assertEqual(report["difference_count"], 1)
            self.assertEqual(report["differences"][0]["identity_key"], "identity-a")
            self.assertEqual(report["differences"][0]["issue"], 210)
            self.assertEqual(guarded.read_text(encoding="utf-8"), "readonly")

    async def test_refuses_report_if_shadow_process_changes_v1_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            guarded = root / "crawler.py"
            guarded.write_text("readonly", encoding="utf-8")
            service = ShadowRunService(
                FakeSnapshotRunner(guarded),
                root / "reviews",
                readonly_paths=(guarded,),
            )

            with self.assertRaises(RuntimeError):
                await service.run(210)

            self.assertFalse((root / "reviews" / "shadow-210-diff.json").exists())

    async def test_rejects_non_positive_issue_before_starting_processes(self) -> None:
        runner = FakeSnapshotRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            service = ShadowRunService(runner, Path(temp_dir))
            with self.assertRaises(ValueError):
                await service.run(0)
        self.assertEqual(runner.calls, [])

    async def test_rejects_snapshot_with_wrong_engine_or_issue(self) -> None:
        class WrongRunner(FakeSnapshotRunner):
            async def run(self, engine: str, issue: int, output_path: Path):
                result = snapshot("wrong", issue + 1, "鼠牛虎兔龙蛇马羊猴")
                GoldenRepository(output_path).write(result)
                return result

        with tempfile.TemporaryDirectory() as temp_dir:
            service = ShadowRunService(WrongRunner(), Path(temp_dir))
            with self.assertRaises(ValueError):
                await service.run(210)


class SubprocessSnapshotRunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_builds_isolated_worker_command_and_loads_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "snapshot.json"
            GoldenRepository(output).write(
                snapshot("v1", 210, "鼠牛虎兔龙蛇马羊猴")
            )
            process = SimpleNamespace(
                returncode=0,
                communicate=AsyncMock(return_value=(b"ok", b"")),
            )
            with patch(
                "v2.services.shadow.asyncio.create_subprocess_exec",
                new=AsyncMock(return_value=process),
            ) as create:
                result = await SubprocessSnapshotRunner(
                    root,
                    concurrency=2,
                    retries=4,
                    executable="python-test",
                ).run("v1", 210, output)

            self.assertEqual(result.engine, "v1")
            arguments = create.await_args.args
            self.assertIn("v2.tests.golden.export_v1", arguments)
            self.assertIn("--retries", arguments)
            self.assertIn("4", arguments)

    async def test_rejects_bad_options_engine_and_failed_worker(self) -> None:
        with self.assertRaises(ValueError):
            SubprocessSnapshotRunner(Path.cwd(), concurrency=0)
        runner = SubprocessSnapshotRunner(Path.cwd())
        with self.assertRaises(ValueError):
            await runner.run("other", 210, Path("unused.json"))

        process = SimpleNamespace(
            returncode=1,
            communicate=AsyncMock(return_value=(b"stdout error", b"")),
        )
        with patch(
            "v2.services.shadow.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=process),
        ):
            with self.assertRaisesRegex(RuntimeError, "stdout error"):
                await runner.run("v2", 210, Path("unused.json"))


def write_config(path: Path, count: int, *, archived: bool) -> None:
    sources = []
    for index in range(count):
        source = {
            "name": f"站点{index}",
            "url": f"https://example.test/{index}",
            "position": "bottom",
            "section_marker": f"站点{index}",
            "fetcher": "static_page",
            "parser": "direct_nine",
            "api_url": "",
            "group_map": {},
            "detail_link_keyword": "",
            "aliases": [],
        }
        sources.append(
            {
                "source": source,
                "archived_at": "2026-07-30",
                "reason": "test",
            }
            if archived
            else source
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"schema_version": 2, "sources": sources}, ensure_ascii=False),
        encoding="utf-8",
    )


def prepare_project(root: Path, *, approved: bool = True) -> dict[str, bytes]:
    v1_files = {
        SINGLE_BAT: b"v1-single\r\n",
        RANGE_BAT: b"v1-range\r\n",
        "crawler.py": b"v1-code\n",
    }
    for name, content in v1_files.items():
        (root / name).write_bytes(content)
    baseline = root / "v2" / "baseline"
    baseline.mkdir(parents=True)
    (baseline / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "v1_files": [
                    {"path": name, "sha256": sha256(content)}
                    for name, content in v1_files.items()
                ],
            }
        ),
        encoding="utf-8",
    )
    reviews = root / "v2" / "reviews"
    reviews.mkdir()
    (reviews / "step-08-approval-required.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "APPROVED" if approved else "PENDING",
                "user_confirmation": approved,
            }
        ),
        encoding="utf-8",
    )
    config = root / "v2" / "config"
    write_config(config / "sources.json", 1, archived=False)
    write_config(config / "archived_sources.json", 1, archived=True)
    (root / "v2" / "__main__.py").write_text("", encoding="utf-8")
    (root / "v2" / V2_SINGLE_BAT).write_text("v2 single", encoding="utf-8")
    (root / "v2" / V2_RANGE_BAT).write_text("v2 range", encoding="utf-8")
    return v1_files


class SwitchPreflightTests(unittest.TestCase):
    def test_passes_only_when_every_gate_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            prepare_project(root)

            report = SwitchPreflightService(
                root,
                expected_active=1,
                expected_archived=1,
            ).check()

            self.assertTrue(report.passed)
            self.assertTrue(all(check.passed for check in report.checks))

    def test_approval_hash_count_entrypoint_and_residue_are_hard_gates(self) -> None:
        mutations = ("approval", "hash", "count", "entrypoint", "residue")
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                prepare_project(root, approved=mutation != "approval")
                if mutation == "hash":
                    (root / "crawler.py").write_text("tampered", encoding="utf-8")
                elif mutation == "count":
                    write_config(
                        root / "v2" / "config" / "sources.json",
                        0,
                        archived=False,
                    )
                elif mutation == "entrypoint":
                    (root / "v2" / "__main__.py").unlink()
                elif mutation == "residue":
                    (root / ".v2-switch-transaction.json").write_text(
                        "{}",
                        encoding="utf-8",
                    )

                report = SwitchPreflightService(
                    root,
                    expected_active=1,
                    expected_archived=1,
                ).check()

                self.assertFalse(report.passed)

    def test_invalid_documents_and_escaped_manifest_paths_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            prepare_project(root)
            (root / "v2" / "reviews" / "step-08-approval-required.json").write_text(
                "not-json",
                encoding="utf-8",
            )
            (root / "v2" / "baseline" / "manifest.json").write_text(
                json.dumps(
                    {
                        "v1_files": [
                            {"path": "../outside.py", "sha256": "invalid"}
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (root / "v2" / "config" / "sources.json").write_text(
                "not-json",
                encoding="utf-8",
            )

            report = SwitchPreflightService(
                root,
                expected_active=1,
                expected_archived=1,
            ).check()

            checks = {check.name: check for check in report.checks}
            self.assertFalse(checks["step_08_approval"].passed)
            self.assertFalse(checks["source_counts"].passed)
            self.assertFalse(checks["v1_hashes"].passed)


class SwitchServiceTests(unittest.TestCase):
    def test_switch_requires_preflight_and_delegates_rollback(self) -> None:
        storage = Mock()
        failed_preflight = Mock()
        failed_preflight.check.return_value = SimpleNamespace(passed=False)
        with self.assertRaises(RuntimeError):
            SwitchService(failed_preflight, storage).switch()
        storage.switch.assert_not_called()

        passed_report = SimpleNamespace(passed=True)
        passed_preflight = Mock()
        passed_preflight.check.return_value = passed_report
        service = SwitchService(passed_preflight, storage)
        self.assertIs(service.switch(), passed_report)
        service.rollback()
        storage.switch.assert_called_once_with()
        storage.rollback.assert_called_once_with()


class BatSwitchStorageTests(unittest.TestCase):
    def test_switch_and_one_click_rollback_preserve_exact_v1_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            originals = prepare_project(root)
            storage = BatSwitchStorage(root)

            storage.switch()

            self.assertIn(
                V2_SINGLE_BAT,
                (root / SINGLE_BAT).read_text(encoding="utf-8"),
            )
            self.assertIn(
                V2_RANGE_BAT,
                (root / RANGE_BAT).read_text(encoding="utf-8"),
            )
            storage.rollback()
            self.assertEqual((root / SINGLE_BAT).read_bytes(), originals[SINGLE_BAT])
            self.assertEqual((root / RANGE_BAT).read_bytes(), originals[RANGE_BAT])

    def test_failed_atomic_switch_leaves_both_official_bats_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            originals = prepare_project(root)
            replacements = 0

            def fail_second_replace(staged: Path, target: Path) -> None:
                nonlocal replacements
                replacements += 1
                if replacements == 2:
                    raise OSError("simulated")
                staged.replace(target)

            storage = BatSwitchStorage(root, _replace=fail_second_replace)
            with self.assertRaises(OSError):
                storage.switch()

            self.assertEqual((root / SINGLE_BAT).read_bytes(), originals[SINGLE_BAT])
            self.assertEqual((root / RANGE_BAT).read_bytes(), originals[RANGE_BAT])
            self.assertFalse((root / ".v2-switch-transaction.json").exists())

    def test_missing_entrypoints_and_invalid_backup_fail_without_official_write(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            originals = prepare_project(root)
            (root / "v2" / V2_SINGLE_BAT).unlink()
            storage = BatSwitchStorage(root)
            with self.assertRaises(FileNotFoundError):
                storage.switch()
            self.assertEqual((root / SINGLE_BAT).read_bytes(), originals[SINGLE_BAT])

            backup = root / "v2" / "switch-backup"
            backup.mkdir()
            (backup / "manifest.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                storage.rollback()

    def test_existing_backup_must_match_current_v1_bats(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            prepare_project(root)
            storage = BatSwitchStorage(root)
            storage.switch()
            with self.assertRaises(RuntimeError):
                storage.switch()


class RuntimeEntrypointTests(unittest.TestCase):
    """Daily operators see a paused window for blank input or crawl errors."""

    def test_standalone_project_root_is_the_v2_directory_itself(self) -> None:
        from v2.runtime import project_root

        self.assertEqual(
            project_root(),
            Path(__file__).resolve().parents[1],
        )

    def test_runtime_cli_parses_crawl_range_shadow_and_switch_tools(self) -> None:
        from v2.__main__ import parse_args

        cases = (
            (
                ["crawl", "210", "--concurrency", "3"],
                {"command": "crawl", "issue": 210, "concurrency": 3},
            ),
            (
                ["crawl-range", "210", "201", "--concurrency", "4"],
                {
                    "command": "crawl-range",
                    "start_issue": 210,
                    "end_issue": 201,
                    "concurrency": 4,
                },
            ),
            (
                ["shadow", "210"],
                {"command": "shadow", "issue": 210, "concurrency": 10},
            ),
            (["preflight"], {"command": "preflight"}),
            (["switch"], {"command": "switch"}),
            (["rollback"], {"command": "rollback"}),
        )
        for arguments, expected in cases:
            with self.subTest(arguments=arguments):
                args = parse_args(arguments)
                self.assertEqual(
                    {name: getattr(args, name) for name in expected},
                    expected,
                )

    def test_independent_v2_bats_call_v2_module_not_v1_scripts(self) -> None:
        package_root = Path(__file__).resolve().parents[1]
        for name, command in (
            (V2_SINGLE_BAT, "run_v2.py crawl"),
            (V2_RANGE_BAT, "run_v2.py crawl-range"),
        ):
            with self.subTest(name=name):
                text = (package_root / name).read_text(encoding="utf-8")
                self.assertIn(command, text)
                self.assertNotIn("crawler.py", text)
                self.assertNotIn("multi_issue_crawler.py", text)

    def test_single_v2_bat_never_exits_before_the_final_pause(self) -> None:
        package_root = Path(__file__).resolve().parents[1]
        path = package_root / V2_SINGLE_BAT
        payload = path.read_bytes()
        text = payload.decode("utf-8")

        self.assertNotIn(b"\n", payload.replace(b"\r\n", b""))
        self.assertNotIn('if "%ISSUE%"=="" exit /b', text)
        self.assertIn('if "%ISSUE%"=="" goto :finish', text)
        self.assertIn("if errorlevel 1 goto :finish", text)
        self.assertIn(":finish", text)
        self.assertEqual(text.count("pause"), 1)

    def test_shadow_workers_select_one_requested_issue(self) -> None:
        from v2.tests.golden.export_v1 import selected_issues as v1_issues
        from v2.tests.golden.export_v2 import selected_issues as v2_issues

        self.assertEqual(v1_issues(211), (211,))
        self.assertEqual(v2_issues(211), (211,))
        self.assertEqual(v1_issues(None), tuple(range(210, 200, -1)))
        self.assertEqual(v2_issues(None), tuple(range(210, 200, -1)))

    def test_rejects_non_positive_and_reversed_range(self) -> None:
        from v2.__main__ import parse_args, positive_int

        with self.assertRaises(Exception):
            positive_int("0")
        with self.assertRaises(SystemExit):
            parse_args(["crawl-range", "201", "210"])

    def test_progress_line_matches_daily_console_style(self) -> None:
        from v2.__main__ import render_progress
        from v2.services.crawl import CrawlProgress

        progress = CrawlProgress(
            completed=1,
            total=318,
            succeeded=1,
            failed=0,
            elapsed_seconds=2.2,
            result=SimpleNamespace(
                source=SimpleNamespace(name="一舟白鹤"),
            ),
        )

        self.assertEqual(
            render_progress(progress),
            "进度 1/318 0% 成功 1 失败 0 用时 2.2s 当前：一舟白鹤",
        )


class RuntimeCliExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_executes_each_runtime_command(self) -> None:
        from v2 import __main__ as cli

        issue_run = SimpleNamespace(
            output_path=Path("ok.txt"),
            failure_path=Path("fail.txt"),
            success_count=0,
            total_count=0,
            cache_updated=False,
        )
        range_run = SimpleNamespace(failure_summary_path=Path("range.txt"))
        shadow_run = SimpleNamespace(difference_count=0, report_path=Path("shadow.json"))
        checks = (
            SimpleNamespace(passed=True, name="one", detail="ok"),
            SimpleNamespace(passed=False, name="two", detail="failed"),
        )
        with (
            patch.object(cli, "project_root", return_value=Path("root")),
            patch.object(cli, "run_crawl", new=AsyncMock(return_value=issue_run)) as crawl,
            patch.object(
                cli,
                "run_crawl_range",
                new=AsyncMock(return_value=range_run),
            ) as crawl_range,
            patch.object(cli, "run_shadow", new=AsyncMock(return_value=shadow_run)) as shadow,
            patch.object(
                cli,
                "run_preflight",
                return_value=SimpleNamespace(checks=checks, passed=False),
            ),
            patch.object(cli, "run_switch") as switch,
            patch.object(cli, "run_rollback") as rollback,
        ):
            self.assertEqual(await cli.async_main(["crawl", "210"]), 0)
            self.assertEqual(
                await cli.async_main(["crawl-range", "210", "209"]),
                0,
            )
            self.assertEqual(await cli.async_main(["shadow", "210"]), 0)
            self.assertEqual(await cli.async_main(["preflight"]), 2)
            self.assertEqual(await cli.async_main(["switch"]), 0)
            self.assertEqual(await cli.async_main(["rollback"]), 0)

        crawl.assert_awaited_once()
        crawl_range.assert_awaited_once()
        shadow.assert_awaited_once()
        switch.assert_called_once()
        rollback.assert_called_once()


class RuntimeAssemblyTests(unittest.IsolatedAsyncioTestCase):
    async def test_crawl_and_range_assemble_runtime_and_close_browser(self) -> None:
        from v2 import runtime

        sources = (Mock(name="source"),)
        repository = Mock()
        repository.load_active.return_value = sources
        context = Mock()
        context.close = AsyncMock()
        browser = Mock()
        browser.new_context = AsyncMock(return_value=context)
        browser.close = AsyncMock()
        playwright = SimpleNamespace(
            chromium=SimpleNamespace(launch=AsyncMock(return_value=browser))
        )

        class Manager:
            async def __aenter__(self):
                return playwright

            async def __aexit__(self, *_args):
                return None

        run_service = Mock()
        run_service.crawl = AsyncMock(return_value="single")
        run_service.crawl_range = AsyncMock(return_value="range")

        def progress(_update) -> None:
            return None

        with (
            patch.object(runtime, "_source_repository", return_value=repository),
            patch.object(
                runtime,
                "daily_sources",
                new=AsyncMock(return_value=sources),
            ),
            patch.object(runtime, "async_playwright", return_value=Manager()),
            patch.object(runtime, "CrawlRunService", return_value=run_service),
        ):
            self.assertEqual(
                await runtime.run_crawl(Path("."), 210, concurrency=2),
                "single",
            )
            self.assertEqual(
                await runtime.run_crawl(
                    Path("."),
                    210,
                    concurrency=2,
                    on_progress=progress,
                ),
                "single",
            )
            self.assertEqual(
                await runtime.run_crawl_range(Path("."), 210, 209, concurrency=3),
                "range",
            )

        self.assertEqual(run_service.crawl.await_count, 2)
        self.assertEqual(
            run_service.crawl.await_args_list[0].kwargs,
            {"concurrency": 2},
        )
        self.assertEqual(
            run_service.crawl.await_args_list[1].kwargs,
            {"concurrency": 2, "on_progress": progress},
        )
        run_service.crawl_range.assert_awaited_once_with(
            sources,
            (210, 209),
            concurrency=3,
        )
        self.assertEqual(context.close.await_count, 3)
        self.assertEqual(browser.close.await_count, 3)

    async def test_manifest_shadow_preflight_switch_and_rollback_wiring(self) -> None:
        from v2 import runtime

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            (root / "v2" / "baseline").mkdir(parents=True)
            (root / "crawler.py").write_text("v1", encoding="utf-8")
            (root / "v2" / "baseline" / "manifest.json").write_text(
                json.dumps({"v1_files": [{"path": "crawler.py"}]}),
                encoding="utf-8",
            )
            self.assertEqual(runtime._v1_manifest_paths(root), (root / "crawler.py",))

            shadow_service = Mock()
            shadow_service.run = AsyncMock(return_value="shadow")
            with (
                patch.object(runtime, "ShadowRunService", return_value=shadow_service),
                patch.object(runtime, "SubprocessSnapshotRunner"),
            ):
                self.assertEqual(
                    await runtime.run_shadow(root, 210, concurrency=2),
                    "shadow",
                )

            preflight = Mock()
            preflight.check.return_value = "preflight"
            switch = Mock()
            switch.switch.return_value = "switched"
            storage = Mock()
            with (
                patch.object(runtime, "SwitchPreflightService", return_value=preflight),
                patch.object(runtime, "SwitchService", return_value=switch),
                patch.object(runtime, "BatSwitchStorage", return_value=storage),
            ):
                self.assertEqual(runtime.run_preflight(root), "preflight")
                self.assertEqual(runtime.run_switch(root), "switched")
                runtime.run_rollback(root)
            storage.rollback.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
