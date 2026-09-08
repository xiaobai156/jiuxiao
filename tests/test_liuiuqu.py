from __future__ import annotations

import json
import unittest

from v2.domain.errors import ErrorCode
from v2.domain.models import Document, DocumentMethod, Position, Source
from v2.fetchers.liuiuqu import LiuiuquFetcher
from v2.fetchers.registry import FetchError, FetchRequest, HttpResponse
from v2.parsers.custom.liuiuqu import LiuiuquParser
from v2.parsers.registry import ParseError
from v2.validator import ValidationError, Validator


def make_source() -> Source:
    return Source(
        name="六爱趣",
        url="https://kef5b.6hgsiyutapp1.com/index/index/videoExplain.html",
        api_url="https://kef5b.6hgsiyutapp1.com/index/index/getziliaoExplain",
        position=Position.TOP,
        section_marker="六爱趣",
        fetcher="liuiuqu",
        parser="liuiuqu",
    )


def payload(*, lottery_type: int = 5, details: list[dict] | None = None) -> str:
    return json.dumps(
        {
            "data": {
                "lotteryType": lottery_type,
                "recommendList": [
                    {
                        "period": 211,
                        "detailList": details
                        or [
                            {
                                "name": "六肖",
                                "valueList": ["鼠牛虎兔龙蛇"],
                            },
                            {
                                "name": "九肖",
                                "valueList": ["鼠牛虎兔龙蛇马羊猴"],
                            },
                        ],
                    }
                ],
            }
        },
        ensure_ascii=False,
    )


class FakePostClient:
    def __init__(self, response: HttpResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, tuple[tuple[str, str], ...]]] = []

    async def post(
        self,
        url: str,
        *,
        timeout_ms: int,
        headers: tuple[tuple[str, str], ...],
        form: tuple[tuple[str, str], ...],
    ) -> HttpResponse:
        self.calls.append((url, form))
        return self.response


class LiuiuquFetcherTests(unittest.IsolatedAsyncioTestCase):
    async def test_posts_the_fixed_type_and_returns_api_document(self) -> None:
        source = make_source()
        client = FakePostClient(
            HttpResponse(200, payload(), source.api_url, "")
        )

        documents = await LiuiuquFetcher(client).fetch(
            source, FetchRequest((211,), attempts=1)
        )

        self.assertEqual(client.calls, [(source.api_url, (("type", "3"),))])
        self.assertEqual(documents[0].method, DocumentMethod.DYNAMIC_API)
        self.assertEqual(documents[0].text, payload())

    async def test_rejects_http_failure_without_page_fallback(self) -> None:
        source = make_source()
        client = FakePostClient(HttpResponse(500, "bad", source.api_url, ""))

        with self.assertRaises(FetchError) as raised:
            await LiuiuquFetcher(client).fetch(
                source, FetchRequest((211,), attempts=1)
            )

        self.assertEqual(raised.exception.failure.code, ErrorCode.HTTP_ERROR)


class LiuiuquParserTests(unittest.TestCase):
    def _parse(self, raw: str):
        source = make_source()
        records = LiuiuquParser().parse(
            source,
            (
                Document(
                    label="liuiuqu-api",
                    url=source.api_url,
                    text=raw,
                    method=DocumentMethod.DYNAMIC_API,
                ),
            ),
            (211,),
        )
        return Validator().validate(source, records, (211,)).history.records

    def test_reads_only_the_requested_issue_and_nine_zodiacs(self) -> None:
        records = self._parse(payload())

        self.assertEqual(records[0].issue, 211)
        self.assertEqual(records[0].zodiac_text, "鼠牛虎兔龙蛇马羊猴")

    def test_rejects_an_unexpected_lottery_type(self) -> None:
        with self.assertRaises(ParseError) as raised:
            self._parse(payload(lottery_type=3))

        self.assertEqual(raised.exception.failure.code, ErrorCode.SOURCE_UNTRUSTED)

    def test_rejects_missing_requested_period(self) -> None:
        raw = json.dumps(
            {"data": {"lotteryType": 5, "recommendList": []}},
            ensure_ascii=False,
        )
        with self.assertRaises(ValidationError) as raised:
            self._parse(raw)

        self.assertEqual(raised.exception.failure.code, ErrorCode.ISSUE_MISSING)

    def test_rejects_conflicting_nine_zodiac_values_for_one_period(self) -> None:
        details = [
            {"name": "九肖", "valueList": ["鼠牛虎兔龙蛇马羊猴"]},
            {"name": "九肖", "valueList": ["鼠牛虎兔龙蛇马羊鸡"]},
        ]
        with self.assertRaises(ValidationError) as raised:
            self._parse(payload(details=details))

        self.assertEqual(raised.exception.failure.code, ErrorCode.CANDIDATE_CONFLICT)


if __name__ == "__main__":
    unittest.main()
