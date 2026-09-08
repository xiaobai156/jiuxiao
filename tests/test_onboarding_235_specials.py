from pathlib import Path

from v2.config.repository import SourceRepository
from v2.domain.models import Position


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_issue_235_special_sources_are_registered_exactly_once() -> None:
    repository = SourceRepository(
        PROJECT_ROOT / "config" / "sources.json",
        PROJECT_ROOT / "config" / "archived_sources.json",
    )
    sources = repository.load_active()
    expected = {
        "风雨人生": (
            "https://4.48kk49.com:1888/Article/ar_content/id/1413/tid/81.html",
            "风雨人生【公式九肖】",
        ),
        "低调是福": (
            "https://4.48kk49.com:1888/Article/ar_content/id/1414/tid/81.html",
            "低调是福【至尊九肖】",
        ),
    }

    for name, (url, marker) in expected.items():
        matches = tuple(source for source in sources if source.name == name)
        assert len(matches) == 1
        source = matches[0]
        assert source.url == url
        assert source.position is Position.TOP
        assert source.section_marker == marker
        assert source.fetcher == "static_page"
        assert source.parser == "direct_nine"
