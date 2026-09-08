from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from v2.baseline.capture_v1 import (
    CRITICAL_V1_FILES,
    build_manifest,
    capture_baseline,
    ordered_source_digest,
    sha256_file,
)


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
BASELINE_ROOT = PACKAGE_ROOT / "baseline"


def prepare_v1_fixture(project_root: Path) -> None:
    captured_files = {
        "extra_sources.json": BASELINE_ROOT / "active_sources.json",
        "archived_extra_sources.json": BASELINE_ROOT / "archived_sources.json",
        "recent_10_cache.json": BASELINE_ROOT / "recent_10_cache.json",
        "zodiac_spec_groups.json": BASELINE_ROOT / "zodiac_spec_groups.json",
    }
    for relative_path in CRITICAL_V1_FILES:
        target = project_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        captured = captured_files.get(relative_path)
        if captured is not None:
            target.write_bytes(captured.read_bytes())
        else:
            target.write_bytes(f"V1 fixture: {relative_path}\n".encode("utf-8"))


class BaselineCaptureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temporary_directory.name)
        prepare_v1_fixture(self.project_root)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_build_manifest_freezes_current_v1_contract(self) -> None:
        manifest = build_manifest(
            self.project_root,
            captured_at="2026-07-29T00:00:00+08:00",
        )

        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["captured_at"], "2026-07-29T00:00:00+08:00")
        self.assertEqual(manifest["active_sources"]["count"], 320)
        self.assertEqual(manifest["archived_sources"]["count"], 16)
        self.assertEqual(manifest["cache"]["latest_issue"], 211)
        self.assertEqual(
            manifest["cache"]["issues"],
            [211, 210, 209, 208, 207, 206, 205, 204, 203, 202],
        )
        self.assertEqual(manifest["cache"]["declared_source_count"], 326)
        self.assertEqual(manifest["cache"]["actual_source_count"], 326)
        self.assertEqual(
            [item["path"] for item in manifest["v1_files"]],
            list(CRITICAL_V1_FILES),
        )

    def test_manifest_preserves_active_and_archived_source_order(self) -> None:
        active = json.loads(
            (self.project_root / "extra_sources.json").read_text(encoding="utf-8")
        )
        archived = json.loads(
            (self.project_root / "archived_extra_sources.json").read_text(
                encoding="utf-8"
            )
        )["sources"]

        manifest = build_manifest(self.project_root)

        self.assertEqual(
            manifest["active_sources"]["ordered_identity_sha256"],
            ordered_source_digest(active),
        )
        self.assertEqual(
            manifest["archived_sources"]["ordered_identity_sha256"],
            ordered_source_digest(archived),
        )

    def test_capture_writes_exact_read_only_copies(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            manifest_path = capture_baseline(
                self.project_root,
                output_dir,
                captured_at="2026-07-29T00:00:00+08:00",
            )

            self.assertEqual(manifest_path, output_dir / "manifest.json")
            self.assertEqual(
                (output_dir / "active_sources.json").read_bytes(),
                (self.project_root / "extra_sources.json").read_bytes(),
            )
            self.assertEqual(
                (output_dir / "archived_sources.json").read_bytes(),
                (self.project_root / "archived_extra_sources.json").read_bytes(),
            )
            self.assertEqual(
                (output_dir / "recent_10_cache.json").read_bytes(),
                (self.project_root / "recent_10_cache.json").read_bytes(),
            )
            captured_manifest = json.loads(
                manifest_path.read_text(encoding="utf-8")
            )
            self.assertEqual(captured_manifest["active_sources"]["count"], 320)

    def test_manifest_hashes_match_every_critical_v1_file(self) -> None:
        manifest = build_manifest(self.project_root)
        files = {item["path"]: item for item in manifest["v1_files"]}

        for relative_path in CRITICAL_V1_FILES:
            source_path = self.project_root / relative_path
            self.assertEqual(files[relative_path]["sha256"], sha256_file(source_path))
            self.assertEqual(files[relative_path]["size"], source_path.stat().st_size)

    def test_missing_v1_files_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(FileNotFoundError):
                build_manifest(Path(temp_dir))

    def test_ordered_source_digest_changes_when_order_changes(self) -> None:
        sources = [
            {
                "name": "甲",
                "url": "https://example.test/a",
                "position": "顶部",
                "section_marker": "甲",
            },
            {
                "name": "乙",
                "url": "https://example.test/b",
                "position": "尾部",
                "section_marker": "乙",
            },
        ]

        self.assertNotEqual(
            ordered_source_digest(sources),
            ordered_source_digest(list(reversed(sources))),
        )


if __name__ == "__main__":
    unittest.main()
