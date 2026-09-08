from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from v2.domain.models import Position, Source
from v2.fetchers.registry import BrowserClient


MAIN_LIST_URL = "https://jogavu.6bl6s-ilo1w-yfnvvl.work:16677/theme/1.html"
ENTRY_PATTERN = re.compile(
    r"^九肖区\s*0*(?P<issue>\d{1,3})期\s*[:：]\s*"
    r"(?P<name>.+?)[「【](?P<title>[^」】]+)[」】]"
)


class MainListCatalog:
    def __init__(self, browser: BrowserClient, directions_path: Path) -> None:
        self._browser = browser
        self._directions_path = Path(directions_path)
        self._parser_overrides_path = (
            self._directions_path.parent / "main_list_parser_overrides.json"
        )

    async def load(self) -> tuple[Source, ...]:
        directions, excluded_titles = self._load_directions()
        parser_overrides = self._load_parser_overrides()
        links = await self._browser.links(
            MAIN_LIST_URL,
            timeout_ms=60_000,
            settle_ms=4_000,
        )
        sources: list[Source] = []
        seen: set[tuple[str, str]] = set()
        for link in links:
            entry = self._parse_entry(link.text, link.url)
            if entry is None:
                continue
            if entry[1] in excluded_titles:
                continue
            key = (entry[0], entry[2])
            if key in seen:
                continue
            seen.add(key)
            position = directions.get(entry)
            if position is None:
                raise ValueError(
                    f"main list source has no fixed direction: {entry[0]}"
                )
            sources.append(
                Source(
                    name=entry[0],
                    url=entry[2],
                    position=position,
                    section_marker=entry[1],
                    fetcher="browser_page",
                    parser=parser_overrides.get(entry, "direct_nine"),
                    aliases=(entry[0],),
                )
            )
        return tuple(sources)

    def _load_parser_overrides(self) -> dict[tuple[str, str, str], str]:
        path = self._parser_overrides_path
        if not path.is_file():
            return {}
        try:
            document: Any = json.loads(path.read_text(encoding="utf-8"))
            if (
                not isinstance(document, dict)
                or set(document) != {"schema_version", "overrides"}
                or document.get("schema_version") != 1
                or not isinstance(document.get("overrides"), list)
            ):
                raise ValueError
            overrides: dict[tuple[str, str, str], str] = {}
            for item in document["overrides"]:
                if not isinstance(item, dict) or set(item) != {
                    "name",
                    "title",
                    "url",
                    "parser",
                }:
                    raise ValueError
                key = tuple(str(item[field]).strip() for field in (
                    "name",
                    "title",
                    "url",
                ))
                parser = str(item["parser"]).strip()
                if not all(key) or not parser or key in overrides:
                    raise ValueError
                overrides[key] = parser
            return overrides
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("invalid main list parser overrides") from exc

    @staticmethod
    def _parse_entry(
        text: str,
        url: str,
    ) -> tuple[str, str, str] | None:
        match = ENTRY_PATTERN.search(" ".join(str(text).split()))
        if match is None:
            return None
        return (
            match.group("name").strip(),
            match.group("title").strip(),
            str(url).strip(),
        )

    def _load_directions(
        self,
    ) -> tuple[dict[tuple[str, str, str], Position], frozenset[str]]:
        try:
            document: Any = json.loads(
                self._directions_path.read_text(encoding="utf-8")
            )
            if (
                not isinstance(document, dict)
                or document.get("schema_version") != 2
                or not isinstance(document.get("sources"), list)
                or not isinstance(document.get("excluded_titles"), list)
                or set(document) != {
                    "schema_version",
                    "excluded_titles",
                    "sources",
                }
            ):
                raise ValueError
            excluded_titles = frozenset(
                str(title).strip() for title in document["excluded_titles"]
            )
            if "" in excluded_titles:
                raise ValueError
            directions: dict[tuple[str, str, str], Position] = {}
            for item in document["sources"]:
                if not isinstance(item, dict) or set(item) != {
                    "name",
                    "title",
                    "url",
                    "position",
                }:
                    raise ValueError
                key = (
                    str(item["name"]).strip(),
                    str(item["title"]).strip(),
                    str(item["url"]).strip(),
                )
                if not all(key) or key in directions:
                    raise ValueError
                directions[key] = Position(str(item["position"]))
            return directions, excluded_titles
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("invalid main list directions") from exc
