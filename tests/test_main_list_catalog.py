from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from v2.config.main_list import MainListCatalog
from v2.fetchers.registry import Link


class FakeBrowser:
    def __init__(self, links: tuple[Link, ...]) -> None:
        self.links_to_return = links

    async def links(self, *_args, **_kwargs) -> tuple[Link, ...]:
        return self.links_to_return


class MainListCatalogTests(unittest.IsolatedAsyncioTestCase):
    """Daily V2 loads every approved dynamic list site with its fixed direction."""

    async def test_builds_sources_from_current_issue_links_and_direction_config(
        self,
    ) -> None:
        links = (
            Link(
                "https://example.test/topic/1.html",
                "九肖区 211期：一舟白鹤【白鹤九肖】",
            ),
            Link(
                "https://example.test/topic/2.html",
                "不是九肖区链接",
            ),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "directions.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "excluded_titles": ["不抓九肖"],
                        "sources": [
                            {
                                "name": "一舟白鹤",
                                "title": "白鹤九肖",
                                "url": "https://example.test/topic/1.html",
                                "position": "top",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            sources = await MainListCatalog(
                FakeBrowser(links), path
            ).load()

        self.assertEqual(len(sources), 1)
        source = sources[0]
        self.assertEqual(source.name, "一舟白鹤")
        self.assertEqual(source.section_marker, "白鹤九肖")
        self.assertEqual(source.aliases, ("一舟白鹤",))
        self.assertEqual(source.position.value, "top")

    async def test_rejects_a_current_list_site_without_a_fixed_direction(
        self,
    ) -> None:
        links = (
            Link(
                "https://example.test/topic/1.html",
                "九肖区 211期：一舟白鹤【白鹤九肖】",
            ),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "directions.json"
            path.write_text(
                '{"schema_version": 2, "excluded_titles": [], "sources": []}',
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                await MainListCatalog(FakeBrowser(links), path).load()

    async def test_excludes_only_the_configured_titles_before_direction_check(
        self,
    ) -> None:
        links = (
            Link(
                "https://example.test/topic/1.html",
                "九肖区 211期：佛口蛇心【不抓九肖】",
            ),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "directions.json"
            path.write_text(
                '{"schema_version": 2, "excluded_titles": ["不抓九肖"], "sources": []}',
                encoding="utf-8",
            )
            sources = await MainListCatalog(FakeBrowser(links), path).load()

        self.assertEqual(sources, ())

    async def test_uses_current_list_sites_for_an_older_requested_period(
        self,
    ) -> None:
        links = (
            Link(
                "https://example.test/topic/1.html",
                "九肖区 211期：一舟白鹤【白鹤九肖】",
            ),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "directions.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "excluded_titles": [],
                        "sources": [
                            {
                                "name": "一舟白鹤",
                                "title": "白鹤九肖",
                                "url": "https://example.test/topic/1.html",
                                "position": "top",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            sources = await MainListCatalog(FakeBrowser(links), path).load()

        self.assertEqual([source.name for source in sources], ["一舟白鹤"])

    async def test_applies_parser_override_by_full_site_identity(self) -> None:
        links = (
            Link(
                "https://example.test/topic/1.html",
                "九肖区 211期：一舟白鹤【白鹤九肖】",
            ),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            directions = directory / "directions.json"
            directions.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "excluded_titles": [],
                        "sources": [
                            {
                                "name": "一舟白鹤",
                                "title": "白鹤九肖",
                                "url": "https://example.test/topic/1.html",
                                "position": "top",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (directory / "main_list_parser_overrides.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "overrides": [
                            {
                                "name": "一舟白鹤",
                                "title": "白鹤九肖",
                                "url": "https://example.test/topic/1.html",
                                "parser": "topic_cyclic_nine",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            sources = await MainListCatalog(
                FakeBrowser(links), directions
            ).load()

        self.assertEqual(sources[0].parser, "topic_cyclic_nine")


if __name__ == "__main__":
    unittest.main()
