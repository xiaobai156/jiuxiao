from __future__ import annotations

import re
import unittest
from dataclasses import FrozenInstanceError

from v2.domain.errors import ErrorCode, Failure
from v2.domain.identity import normalize_url, source_identity
from v2.domain.models import (
    Document,
    DocumentMethod,
    Evidence,
    History,
    Position,
    Record,
    Result,
    ResultState,
    Source,
)


def make_source(**overrides: object) -> Source:
    values: dict[str, object] = {
        "name": "霸王码特",
        "url": "https://Example.Test:443/article/manager/abc?b=2&a=1#fragment",
        "position": Position.BOTTOM,
        "section_marker": "霸王码特",
        "fetcher": "dynamic_article",
        "parser": "direct_nine",
        "group_map": (),
        "aliases": (),
    }
    values.update(overrides)
    return Source(**values)


class ErrorContractTests(unittest.TestCase):
    def test_error_codes_are_stable_ascii_identifiers(self) -> None:
        for code in ErrorCode:
            self.assertRegex(code.value, re.compile(r"^[A-Z][A-Z0-9_]*$"))

    def test_failure_is_deeply_immutable(self) -> None:
        failure = Failure(
            ErrorCode.ANCHOR_MISSING,
            detail="missing anchor",
            context=(("anchor", "霸王码特"),),
        )

        with self.assertRaises(FrozenInstanceError):
            failure.detail = "changed"  # type: ignore[misc]
        with self.assertRaises(TypeError):
            failure.context[0] = ("anchor", "changed")  # type: ignore[index]


class IdentityContractTests(unittest.TestCase):
    def test_spa_hash_routes_are_identity_but_page_anchors_are_not(self) -> None:
        first = make_source(
            url="https://example.test/#/users/21928",
        )
        second = make_source(
            url="https://example.test/#/users/116180",
        )

        self.assertNotEqual(
            source_identity(first).key,
            source_identity(second).key,
        )
        self.assertEqual(
            normalize_url("https://EXAMPLE.test/#/users/21928/"),
            "https://example.test/#/users/21928",
        )
        self.assertEqual(
            normalize_url("https://example.test/#page-heading"),
            "https://example.test/",
        )

    def test_url_normalization_is_stable_for_equivalent_urls(self) -> None:
        left = normalize_url(
            " HTTPS://Example.Test:443/article/manager/abc/?b=2&a=1#ignored "
        )
        right = normalize_url(
            "https://example.test/article/manager/abc?a=1&b=2"
        )

        self.assertEqual(left, right)

    def test_source_identity_is_deterministic(self) -> None:
        source = make_source()

        first = source_identity(source)
        second = source_identity(source)

        self.assertEqual(first, second)
        self.assertEqual(len(first.key), 64)
        self.assertEqual(first.position, Position.BOTTOM)

    def test_direction_and_marker_are_identity_boundaries(self) -> None:
        base = source_identity(make_source())
        changed_direction = source_identity(make_source(position=Position.TOP))
        changed_marker = source_identity(make_source(section_marker="另一栏目"))

        self.assertNotEqual(base.key, changed_direction.key)
        self.assertNotEqual(base.key, changed_marker.key)

    def test_invalid_url_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            normalize_url("not-a-url")


class ModelContractTests(unittest.TestCase):
    def test_source_is_immutable_and_keeps_tuple_configuration(self) -> None:
        source = make_source(
            group_map=(("琴", "兔蛇鸡"), ("棋", "鼠牛狗")),
            aliases=("霸王九肖",),
        )

        self.assertEqual(source.group_map[0], ("琴", "兔蛇鸡"))
        self.assertEqual(source.aliases, ("霸王九肖",))
        with self.assertRaises(FrozenInstanceError):
            source.name = "changed"  # type: ignore[misc]

    def test_record_preserves_original_zodiac_order_and_evidence(self) -> None:
        evidence = Evidence(
            method="direct",
            source_line="210期：【狗猴虎鸡龙牛蛇羊猪】",
            directory_anchor="霸王码特",
            document_label="api:$",
            metadata=(("article_id", "abc"),),
        )
        record = Record(
            issue=210,
            zodiacs=tuple("狗猴虎鸡龙牛蛇羊猪"),
            evidence=evidence,
        )

        self.assertEqual(record.zodiac_text, "狗猴虎鸡龙牛蛇羊猪")
        self.assertEqual(record.zodiacs[0], "狗")
        self.assertEqual(record.evidence.metadata, (("article_id", "abc"),))

    def test_history_keeps_conflicting_candidates_for_validator(self) -> None:
        evidence = Evidence("direct", "line", "anchor", "api")
        first = Record(210, tuple("鼠牛虎兔龙蛇马羊猴"), evidence)
        second = Record(210, tuple("牛鼠虎兔龙蛇马羊猴"), evidence)
        history = History(records=(first, second), current_issue=210)

        self.assertEqual(history.records_for(210), (first, second))

    def test_document_is_immutable_and_keeps_provenance(self) -> None:
        document = Document(
            label="api:$",
            url="https://example.test/api",
            text="210期",
            method=DocumentMethod.DYNAMIC_API,
            metadata=(("article_id", "abc"), ("record_path", "$")),
        )

        self.assertEqual(document.metadata[0], ("article_id", "abc"))
        with self.assertRaises(FrozenInstanceError):
            document.text = "changed"  # type: ignore[misc]

    def test_result_factories_enforce_success_and_failure_states(self) -> None:
        source = make_source()
        evidence = Evidence("direct", "line", "anchor", "api")
        history = History(
            records=(Record(210, tuple("鼠牛虎兔龙蛇马羊猴"), evidence),),
            current_issue=210,
        )
        success = Result.succeeded(source, (210,), history)
        failure = Result.failed(
            source,
            (210,),
            Failure(ErrorCode.ISSUE_MISSING, context=(("issue", "210"),)),
        )

        self.assertEqual(success.state, ResultState.SUCCESS)
        self.assertTrue(success.successful)
        self.assertEqual(failure.state, ResultState.FAILURE)
        self.assertFalse(failure.successful)
        self.assertEqual(failure.failures[0].code, ErrorCode.ISSUE_MISSING)

    def test_invalid_model_values_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            make_source(name="")
        with self.assertRaises(ValueError):
            Record(
                issue=0,
                zodiacs=tuple("鼠牛虎兔龙蛇马羊猴"),
                evidence=Evidence("direct", "line", "anchor", "api"),
            )
        with self.assertRaises(ValueError):
            Result.failed(make_source(), (210,))


if __name__ == "__main__":
    unittest.main()
