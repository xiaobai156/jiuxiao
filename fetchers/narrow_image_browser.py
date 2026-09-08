from __future__ import annotations

from v2.fetchers.browser_page import PlaywrightBrowserClient


class NarrowImagePlaywrightBrowserClient(PlaywrightBrowserClient):
    """Browser client for a verified formula image rendered at 480px wide."""

    IMAGE_MIN_WIDTH = 400

    @staticmethod
    def _rank_image_candidates(candidates):
        return tuple(
            sorted(
                candidates,
                key=lambda item: (
                    bool(
                        str(item.get("anchorLine", "")).strip()
                        and str(item.get("anchorTerm", "")).strip()
                        and str(item.get("dataMarkerLine", "")).strip()
                    ),
                    int(item["width"]) * int(item["height"]),
                ),
                reverse=True,
            )
        )
