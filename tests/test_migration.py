from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from v2.config.migrate_v1 import (
    DEFAULT_OVERRIDES_PATH,
    build_migration,
    migrate_files,
)
from v2.config.repository import SourceRepository
from v2.parsers.factory import build_parser_registry


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
BASELINE_ROOT = PACKAGE_ROOT / "baseline"


class V1MigrationTests(unittest.TestCase):
    def build_bundle(self):
        return build_migration(
            BASELINE_ROOT / "active_sources.json",
            BASELINE_ROOT / "archived_sources.json",
            BASELINE_ROOT / "zodiac_spec_groups.json",
            DEFAULT_OVERRIDES_PATH,
        )

    def test_real_migration_preserves_all_source_order_without_manual_reentry(
        self,
    ) -> None:
        raw_active = json.loads(
            (BASELINE_ROOT / "active_sources.json").read_text(encoding="utf-8")
        )
        raw_archived = json.loads(
            (BASELINE_ROOT / "archived_sources.json").read_text(
                encoding="utf-8"
            )
        )["sources"]

        bundle = self.build_bundle()

        self.assertEqual(len(bundle.active), 320)
        self.assertEqual(len(bundle.archived), 16)
        self.assertEqual(
            [(source.name, source.url) for source in bundle.active],
            [(item["name"], item["url"]) for item in raw_active],
        )
        self.assertEqual(
            [(entry.source.name, entry.source.url) for entry in bundle.archived],
            [(item["name"], item["url"]) for item in raw_archived],
        )

    def test_migration_infers_fetchers_and_moves_special_rules_to_config(
        self,
    ) -> None:
        bundle = self.build_bundle()
        sources = {
            source.name: source
            for source in (
                *bundle.active,
                *(entry.source for entry in bundle.archived),
            )
        }

        self.assertEqual(sources["霸王码特"].fetcher, "dynamic_article")
        self.assertEqual(sources["霸王码特"].parser, "split_line")
        self.assertEqual(sources["女霸君主"].parser, "split_line")
        self.assertEqual(sources["八步毛哥"].parser, "named_section")
        self.assertEqual(sources["金瓯无缺"].fetcher, "list_detail")
        self.assertEqual(sources["月影舞华"].fetcher, "browser_page")
        self.assertEqual(sources["月影舞华"].parser, "yueying")
        self.assertEqual(sources["月影舞华"].position.value, "bottom")
        self.assertEqual(sources["风神九肖"].position.value, "bottom")
        self.assertEqual(sources["风神九肖"].parser, "white_tiger")
        self.assertEqual(sources["彩资讯网"].parser, "color_info_grouped")
        self.assertEqual(
            sources["橘色日落"].parser,
            "single_season_complement",
        )
        self.assertEqual(
            sources["物微志信"].parser,
            "single_season_complement",
        )
        self.assertEqual(sources["嫦娥公式"].parser, "image_ocr")
        self.assertEqual(sources["嫦娥奔月"].parser, "image_ocr")
        profile_sources = tuple(
            source
            for source in sources.values()
            if "#/users/" in source.url
        )
        self.assertEqual(len(profile_sources), 16)
        self.assertEqual(
            {source.parser for source in profile_sources},
            {"profile_history"},
        )
        self.assertEqual(sources["湘妹围特"].parser, "grouped")
        self.assertEqual(len(sources["湘妹围特"].group_map), 4)
        self.assertEqual(
            sources["天码行空"].aliases,
            ("天马行空", "天马九肖"),
        )
        self.assertEqual(sources["妞逼特肖"].aliases, ("牛逼特肖",))
        self.assertEqual(
            sources["东方饭店"].section_marker,
            "神庙网 【浑然九肖】",
        )
        self.assertEqual(sources["东方饭店"].data_marker, "九肖")
        self.assertEqual(sources["停止学生"].parser, "profile_history")
        self.assertEqual(sources["停止学生"].section_marker, "九肖中特")
        self.assertEqual(sources["停止学生"].data_marker, "九肖")
        for name in (
            "玩家小狐",
            "红红火火",
            "追风六合",
            "弥足珍贵",
            "森林少女",
            "澳门顺哥",
            "灵丹妙药",
        ):
            with self.subTest(complement_source=name):
                self.assertEqual(sources[name].parser, "complement_three")
                self.assertEqual(sources[name].data_marker, "绝杀三肖")

    def test_every_migrated_strategy_has_a_registered_v2_key(self) -> None:
        bundle = self.build_bundle()
        sources = (
            *bundle.active,
            *(entry.source for entry in bundle.archived),
        )

        self.assertLessEqual(
            {source.fetcher for source in sources},
            {"browser_page", "dynamic_article", "list_detail"},
        )
        registry = build_parser_registry()
        for key in {source.parser for source in sources}:
            with self.subTest(parser=key):
                self.assertIsNotNone(registry.resolve(key))

    def test_migration_writes_both_documents_atomically_and_refuses_overwrite(
        self,
    ) -> None:
        bundle = self.build_bundle()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            active_path = root / "sources.json"
            archived_path = root / "archived_sources.json"

            migrate_files(bundle, active_path, archived_path)

            repository = SourceRepository(active_path, archived_path)
            repository.initialize()
            self.assertEqual(len(repository.load_active()), 320)
            self.assertEqual(len(repository.load_archived()), 16)
            before = (active_path.read_bytes(), archived_path.read_bytes())
            with self.assertRaises(FileExistsError):
                migrate_files(bundle, active_path, archived_path)
            self.assertEqual(
                (active_path.read_bytes(), archived_path.read_bytes()),
                before,
            )

    def test_archived_metadata_is_carried_to_every_entry(self) -> None:
        bundle = self.build_bundle()

        self.assertEqual(
            {entry.archived_at for entry in bundle.archived},
            {"2026-07-25"},
        )
        self.assertEqual(len({entry.reason for entry in bundle.archived}), 1)
        self.assertIn("用户要求封存", bundle.archived[0].reason)


if __name__ == "__main__":
    unittest.main()
