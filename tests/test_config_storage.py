from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from v2.config.repository import (
    DuplicateSourceError,
    SourceNotFoundError,
    SourceRepository,
)
from v2.config.schema import ConfigValidationError, source_from_dict, source_to_dict
from v2.domain.identity import source_identity
from v2.domain.models import Position, Source
from v2.storage.atomic import (
    atomic_write_bytes,
    atomic_write_many,
    recover_atomic_batch,
)


def make_source(
    name: str = "霸王码特",
    url: str = "https://example.test/article/manager/a",
    position: Position = Position.BOTTOM,
    marker: str = "霸王码特",
) -> Source:
    return Source(
        name=name,
        url=url,
        position=position,
        section_marker=marker,
        fetcher="dynamic_article",
        parser="direct_nine",
        group_map=(("琴", "兔蛇鸡"),),
        aliases=(f"{name}别名",),
    )


class SourceSchemaTests(unittest.TestCase):
    def test_source_round_trip_keeps_all_configuration(self) -> None:
        source = make_source()

        loaded = source_from_dict(source_to_dict(source))

        self.assertEqual(loaded, source)
        self.assertEqual(loaded.position, Position.BOTTOM)
        self.assertEqual(loaded.group_map, (("琴", "兔蛇鸡"),))

    def test_schema_rejects_unknown_fields_and_noncanonical_position(self) -> None:
        document = source_to_dict(make_source())
        document["unknown"] = True
        with self.assertRaises(ConfigValidationError):
            source_from_dict(document)

        document = source_to_dict(make_source())
        document["position"] = "尾部"
        with self.assertRaises(ConfigValidationError):
            source_from_dict(document)

    def test_schema_rejects_missing_and_malformed_fields(self) -> None:
        document = source_to_dict(make_source())
        del document["fetcher"]
        with self.assertRaises(ConfigValidationError):
            source_from_dict(document)

        document = source_to_dict(make_source())
        document["group_map"] = ["not-a-map"]
        with self.assertRaises(ConfigValidationError):
            source_from_dict(document)


class AtomicStorageTests(unittest.TestCase):
    def test_atomic_write_bytes_replaces_complete_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            path.write_bytes(b"old")

            atomic_write_bytes(path, b"new")

            self.assertEqual(path.read_bytes(), b"new")
            self.assertEqual(list(path.parent.glob(f".{path.name}.*.tmp")), [])

    def test_atomic_batch_failure_restores_every_original_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            active = root / "sources.json"
            archived = root / "archived_sources.json"
            journal = root / ".source-transaction.json"
            active.write_bytes(b"active-before")
            archived.write_bytes(b"archived-before")
            replacements = 0

            def fail_on_second_target(source: Path, target: Path) -> None:
                nonlocal replacements
                replacements += 1
                if replacements == 2:
                    raise OSError("simulated replacement failure")
                source.replace(target)

            with self.assertRaises(OSError):
                atomic_write_many(
                    {
                        active: b"active-after",
                        archived: b"archived-after",
                    },
                    journal,
                    _replace=fail_on_second_target,
                )

            self.assertEqual(active.read_bytes(), b"active-before")
            self.assertEqual(archived.read_bytes(), b"archived-before")
            self.assertFalse(journal.exists())
            self.assertEqual(list(root.glob(".*.tmp")), [])

    def test_atomic_batch_success_commits_all_files_and_removes_journal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            active = root / "sources.json"
            archived = root / "archived_sources.json"
            journal = root / ".source-transaction.json"

            atomic_write_many(
                {
                    active: b"active",
                    archived: b"archived",
                },
                journal,
            )

            self.assertEqual(active.read_bytes(), b"active")
            self.assertEqual(archived.read_bytes(), b"archived")
            self.assertFalse(journal.exists())

    def test_recovery_rolls_back_interrupted_batch_on_next_start(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            active = root / "sources.json"
            archived = root / "archived_sources.json"
            journal = root / ".source-transaction.json"
            active.write_bytes(b"active-before")
            archived.write_bytes(b"archived-before")
            replacements = 0

            def interrupt_on_second_target(source: Path, target: Path) -> None:
                nonlocal replacements
                replacements += 1
                if replacements == 2:
                    raise KeyboardInterrupt
                source.replace(target)

            with self.assertRaises(KeyboardInterrupt):
                atomic_write_many(
                    {
                        active: b"active-after",
                        archived: b"archived-after",
                    },
                    journal,
                    _replace=interrupt_on_second_target,
                )
            self.assertTrue(journal.exists())

            self.assertTrue(recover_atomic_batch(journal))
            self.assertEqual(active.read_bytes(), b"active-before")
            self.assertEqual(archived.read_bytes(), b"archived-before")
            self.assertFalse(journal.exists())
            self.assertFalse(recover_atomic_batch(journal))

    def test_atomic_batch_rejects_empty_or_cross_directory_targets(self) -> None:
        with tempfile.TemporaryDirectory() as first_dir:
            with tempfile.TemporaryDirectory() as second_dir:
                journal = Path(first_dir) / ".transaction.json"
                with self.assertRaises(ValueError):
                    atomic_write_many({}, journal)
                with self.assertRaises(ValueError):
                    atomic_write_many(
                        {Path(second_dir) / "outside.json": b"outside"},
                        journal,
                    )


class SourceRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.repository = SourceRepository(
            self.root / "sources.json",
            self.root / "archived_sources.json",
        )
        self.repository.initialize()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_initialize_creates_versioned_empty_documents(self) -> None:
        active = json.loads(self.repository.active_path.read_text(encoding="utf-8"))
        archived = json.loads(
            self.repository.archived_path.read_text(encoding="utf-8")
        )

        self.assertEqual(active, {"schema_version": 2, "sources": []})
        self.assertEqual(archived, {"schema_version": 2, "sources": []})

    def test_add_preserves_order_and_rejects_name_or_url_duplicates(self) -> None:
        first = make_source()
        second = make_source(
            name="女霸君主",
            url="https://example.test/article/manager/b",
            marker="女霸君主",
        )
        self.repository.add(first)
        self.repository.add(second)

        self.assertEqual(self.repository.load_active(), (first, second))
        with self.assertRaises(DuplicateSourceError):
            self.repository.add(
                make_source(
                    name=first.name,
                    url="https://example.test/article/manager/c",
                )
            )
        with self.assertRaises(DuplicateSourceError):
            self.repository.add(
                make_source(
                    name="另一个名字",
                    url=second.url,
                    marker="另一个名字",
                )
            )

    def test_archive_and_restore_move_exact_identity_without_reordering(self) -> None:
        first = make_source()
        second = make_source(
            name="女霸君主",
            url="https://example.test/article/manager/b",
            marker="女霸君主",
        )
        self.repository.add(first)
        self.repository.add(second)

        archived = self.repository.archive(
            source_identity(first).key,
            reason="用户要求封存",
            archived_at="2026-07-29T00:00:00+08:00",
        )

        self.assertEqual(archived.source, first)
        self.assertEqual(self.repository.load_active(), (second,))
        self.assertEqual(self.repository.load_archived(), (archived,))
        restored = self.repository.restore(source_identity(first).key)
        self.assertEqual(restored, first)
        self.assertEqual(self.repository.load_active(), (second, first))
        self.assertEqual(self.repository.load_archived(), ())

    def test_add_rejects_source_still_present_in_archive(self) -> None:
        source = make_source()
        self.repository.add(source)
        self.repository.archive(
            source_identity(source).key,
            reason="封存",
            archived_at="2026-07-29T00:00:00+08:00",
        )

        with self.assertRaises(DuplicateSourceError):
            self.repository.add(source)

    def test_shared_url_requires_explicit_distinct_marker_authorization(self) -> None:
        first = make_source()
        second = make_source(
            name="同页另一栏目",
            url=first.url,
            marker="另一栏目",
        )
        self.repository.add(first)

        with self.assertRaises(DuplicateSourceError):
            self.repository.add(second)
        self.repository.add(second, allow_shared_url=True)

        self.assertEqual(self.repository.load_active(), (first, second))
        with self.assertRaises(DuplicateSourceError):
            self.repository.add(
                make_source(
                    name="同页重复栏目",
                    url=first.url,
                    marker=first.section_marker,
                ),
                allow_shared_url=True,
            )

    def test_missing_archive_or_restore_identity_fails_closed(self) -> None:
        with self.assertRaises(SourceNotFoundError):
            self.repository.archive(
                "0" * 64,
                reason="missing",
                archived_at="2026-07-29T00:00:00+08:00",
            )
        with self.assertRaises(SourceNotFoundError):
            self.repository.restore("0" * 64)

    def test_invalid_json_document_fails_without_rewriting_it(self) -> None:
        invalid = b'{"schema_version": 2, "sources": ['
        self.repository.active_path.write_bytes(invalid)

        with self.assertRaises(ConfigValidationError):
            self.repository.load_active()

        self.assertEqual(self.repository.active_path.read_bytes(), invalid)

    def test_loading_rejects_duplicate_identity_already_in_json(self) -> None:
        source = make_source()
        document = {
            "schema_version": 2,
            "sources": [source_to_dict(source), source_to_dict(source)],
        }
        self.repository.active_path.write_text(
            json.dumps(document, ensure_ascii=False),
            encoding="utf-8",
        )

        with self.assertRaises(ConfigValidationError):
            self.repository.load_active()

    def test_initialize_rejects_active_and_archived_identity_overlap(self) -> None:
        source = make_source()
        self.repository.active_path.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "sources": [source_to_dict(source)],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.repository.archived_path.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "sources": [
                        {
                            "source": source_to_dict(source),
                            "archived_at": "2026-07-29T00:00:00+08:00",
                            "reason": "封存",
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        with self.assertRaises(ConfigValidationError):
            self.repository.initialize()


class ProductionSourceRegressionTests(unittest.TestCase):
    def test_requested_anchor_failures_are_archived(self) -> None:
        root = Path(__file__).resolve().parents[1]
        repository = SourceRepository(
            root / "config" / "sources.json",
            root / "config" / "archived_sources.json",
        )
        target_urls = {
            "争长论短": (
                "https://cahgjib.5blx9-z8506-ekiwxc.work:29488/"
                "article/admin/6a3ab478018539c611cbda99?url=lqz"
            ),
            "清清白白": (
                "https://nwrkkmv.rx287-rkrai-jsjccc.xyz:29499/"
                "article/manager/6a55d055f447e21b02daa606?url=ggz"
            ),
        }

        active_names = {source.name for source in repository.load_active()}
        archived = {
            entry.source.name: entry
            for entry in repository.load_archived()
            if entry.source.name in target_urls
        }

        self.assertTrue(target_urls.keys().isdisjoint(active_names))
        self.assertEqual(set(archived), set(target_urls))
        self.assertEqual(
            {name: entry.source.url for name, entry in archived.items()},
            target_urls,
        )
        self.assertTrue(
            all(entry.reason == "用户要求封存，不再抓取" for entry in archived.values())
        )

    def test_water_deep_fire_hot_direction_is_bottom(self) -> None:
        root = Path(__file__).resolve().parents[1]
        sources = SourceRepository(
            root / "config" / "sources.json",
            root / "config" / "archived_sources.json",
        ).load_active()
        selected = tuple(source for source in sources if source.name == "水深火热")

        self.assertEqual(len(selected), 1)
        self.assertEqual(
            selected[0].url,
            "https://msbqxti.zhx2n-7v5x3-ivdpud.xyz:16677/topic/678565.html",
        )
        self.assertIs(selected[0].position, Position.BOTTOM)

    def test_ttss_page_79_sources_scan_all_same_origin_pages(self) -> None:
        root = Path(__file__).resolve().parents[1]
        sources = SourceRepository(
            root / "config" / "sources.json",
            root / "config" / "archived_sources.json",
        ).load_active()
        selected = {
            source.name: source
            for source in sources
            if source.name in {"空谷足音", "甜私蜜语", "小家碧玉", "回光返照"}
        }

        self.assertEqual(set(selected), {
            "空谷足音",
            "甜私蜜语",
            "小家碧玉",
            "回光返照",
        })
        self.assertTrue(
            all(source.fetcher == "list_detail" for source in selected.values())
        )
        self.assertEqual(
            selected["回光返照"].detail_link_keyword,
            "回光返照【独家九肖】",
        )

    def test_verified_217_repairs_are_pinned_to_target_sources(self) -> None:
        root = Path(__file__).resolve().parents[1]
        sources = SourceRepository(
            root / "config" / "sources.json",
            root / "config" / "archived_sources.json",
        ).load_active()
        selected = {
            source.name: source
            for source in sources
            if source.name in {"风神九肖", "嫦娥公式", "嫦娥奔月"}
        }

        self.assertEqual(set(selected), {"风神九肖", "嫦娥公式", "嫦娥奔月"})
        self.assertEqual(selected["风神九肖"].parser, "formula_dom")
        self.assertEqual(selected["风神九肖"].data_marker, "㉿九肖㉿")
        self.assertEqual(selected["嫦娥公式"].parser, "image_ocr")
        self.assertEqual(selected["嫦娥奔月"].parser, "image_ocr")
        self.assertTrue(
            all(source.position is Position.BOTTOM for source in selected.values())
        )


if __name__ == "__main__":
    unittest.main()
