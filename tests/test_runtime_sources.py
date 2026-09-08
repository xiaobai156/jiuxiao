from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from v2.domain.models import Position, Source


def source(name: str, index: int, *, marker: str | None = None) -> Source:
    return Source(
        name=name,
        url=f"https://example.test/topic/{index}.html",
        position=Position.TOP,
        section_marker=marker or name,
        fetcher="browser_page",
        parser="direct_nine",
    )


class RuntimeSourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_daily_sources_are_34_list_plus_six_plus_318_fixed(self) -> None:
        from v2 import runtime

        catalog = Mock()
        catalog.load = AsyncMock(
            return_value=tuple(source(f"列表{index}", index) for index in range(34))
        )
        repository = Mock()
        repository.load_active.return_value = tuple(
            source(f"固定{index}", index + 1000) for index in range(318)
        )
        with patch.object(runtime, "MainListCatalog", return_value=catalog):
            sources = await runtime.daily_sources(
                Path("."), Mock(), repository
            )

        self.assertEqual(len(sources), 353)
        self.assertEqual(len({item.name for item in sources}), 353)
        self.assertEqual(sources[0].name, "列表0")
        self.assertEqual(sources[34].name, "六爱趣")
        self.assertEqual(sources[34].fetcher, "liuiuqu")
        self.assertEqual(sources[-1].name, "固定317")

    async def test_daily_sources_reject_duplicate_name_before_crawl(self) -> None:
        from v2 import runtime

        catalog = Mock()
        catalog.load = AsyncMock(return_value=(source("重复", 1),))
        repository = Mock()
        repository.load_active.return_value = (source("重复", 2),)
        with patch.object(runtime, "MainListCatalog", return_value=catalog):
            with self.assertRaises(ValueError):
                await runtime.daily_sources(Path("."), Mock(), repository)


if __name__ == "__main__":
    unittest.main()
