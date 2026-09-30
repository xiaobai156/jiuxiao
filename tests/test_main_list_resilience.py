import asyncio
import importlib.util
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if "v2" not in sys.modules:
    specification = importlib.util.spec_from_file_location(
        "v2",
        PROJECT_ROOT / "__init__.py",
        submodule_search_locations=[str(PROJECT_ROOT)],
    )
    assert specification is not None and specification.loader is not None
    package = importlib.util.module_from_spec(specification)
    sys.modules["v2"] = package
    specification.loader.exec_module(package)


from v2.config.main_list import MainListCatalog  # noqa: E402
from v2.domain.models import Position, Source  # noqa: E402


def _write_directions(root: Path) -> None:
    (root / "main_list_directions.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "excluded_titles": [],
                "sources": [
                    {
                        "name": "固定目录",
                        "title": "九肖中特",
                        "url": "https://example.test/topic/1.html",
                        "position": "top",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (root / "main_list_parser_overrides.json").write_text(
        json.dumps({"schema_version": 1, "overrides": []}),
        encoding="utf-8",
    )


class _UnavailableMainList:
    async def links(self, *_args, **_kwargs):
        raise RuntimeError("net::ERR_CONNECTION_CLOSED")


def test_main_list_uses_last_validated_sources_when_remote_catalog_is_unavailable(
    tmp_path: Path,
) -> None:
    _write_directions(tmp_path)
    fallback = Source(
        name="固定目录",
        url="https://example.test/topic/1.html",
        position=Position.TOP,
        section_marker="九肖中特",
        fetcher="browser_page",
        parser="direct_nine",
        aliases=("固定目录",),
    )

    sources = asyncio.run(
        MainListCatalog(
            _UnavailableMainList(),
            tmp_path / "main_list_directions.json",
            fallback_sources=(fallback,),
        ).load()
    )

    assert sources == (fallback,)
