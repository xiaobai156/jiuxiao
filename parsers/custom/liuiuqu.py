from __future__ import annotations

import json
from typing import Any

from v2.domain.errors import ErrorCode, Failure
from v2.domain.models import Document, Record, RecordSet, Source
from v2.parsers.registry import (
    CANONICAL_ZODIACS,
    AnchoredBlock,
    ParseError,
    block_evidence_for,
    evidence_for,
)


class LiuiuquParser:
    """Parse 六爱趣's structured 九肖 field without page-text fallback."""

    def parse(
        self,
        source: Source,
        documents: tuple[Document, ...],
        issues: tuple[int, ...],
    ) -> RecordSet:
        del issues
        data_marker = source.data_marker or "九肖"
        records: list[Record] = []
        block_evidence = []
        for document_index, document in enumerate(documents):
            payload = self._payload(document)
            data = payload.get("data")
            if not isinstance(data, dict) or data.get("lotteryType") != 5:
                raise ParseError(
                    Failure(
                        ErrorCode.SOURCE_UNTRUSTED,
                        detail="liuiuqu lotteryType must be 5",
                    )
                )
            recommendations = data.get("recommendList")
            if not isinstance(recommendations, list):
                raise ParseError(
                    Failure(
                        ErrorCode.SOURCE_UNTRUSTED,
                        detail="liuiuqu recommendList is missing",
                    )
                )
            parsed_details: list[tuple[int, int, int, str, dict[str, Any]]] = []
            observed_issues: list[int] = []
            for recommendation_index, recommendation in enumerate(
                recommendations
            ):
                if not isinstance(recommendation, dict):
                    continue
                issue = self._issue(recommendation.get("period"))
                if issue is None:
                    continue
                details = tuple(
                    detail
                    for detail in recommendation.get("detailList", [])
                    if isinstance(detail, dict)
                    and detail.get("name") == data_marker
                )
                if not details:
                    continue
                observed_issues.append(issue)
                for detail_index, detail in enumerate(details):
                    zodiac_text = self._zodiac_text(detail.get("valueList"))
                    if not zodiac_text:
                        continue
                    parsed_details.append(
                        (
                            recommendation_index,
                            issue,
                            detail_index,
                            zodiac_text,
                            detail,
                        )
                    )

            if not observed_issues:
                continue
            block = AnchoredBlock(
                anchor_line=(
                    f"{source.section_marker or source.name} API "
                    f'detailList.name="{data_marker}"'
                ),
                anchor_term=source.section_marker or source.name,
                anchor_index=0,
                anchor_occurrence=1,
                start=0,
                end=max(1, len(recommendations)),
                block_id=f"{document.label}:recommendations",
                lines=(),
                observed_issues=tuple(dict.fromkeys(observed_issues)),
            )
            block_evidence.append(
                block_evidence_for(
                    source,
                    document,
                    block,
                    parser_id="liuiuqu",
                    data_marker=data_marker,
                )
            )
            for candidate_index, (
                recommendation_index,
                issue,
                detail_index,
                zodiac_text,
                detail,
            ) in enumerate(parsed_details):
                raw_line = json.dumps(
                    detail,
                    ensure_ascii=False,
                    sort_keys=True,
                )
                records.append(
                    Record(
                        issue=issue,
                        zodiacs=tuple(zodiac_text),
                        evidence=evidence_for(
                            source,
                            document,
                            document_index,
                            block,
                            parser_id="liuiuqu",
                            method="liuiuqu_api",
                            source_line=raw_line,
                            raw_issue_line=f'period="{issue}"',
                            raw_zodiac_line=raw_line,
                            line_index=recommendation_index,
                            candidate_index_in_block=candidate_index,
                            data_marker=data_marker,
                            metadata=(
                                ("lottery_type", "5"),
                                (
                                    "recommendation_index",
                                    str(recommendation_index),
                                ),
                                ("detail_index", str(detail_index)),
                            ),
                        ),
                    )
                )
        return RecordSet(tuple(records), tuple(block_evidence))

    @staticmethod
    def _payload(document: Document) -> dict[str, Any]:
        try:
            payload = json.loads(document.text)
        except json.JSONDecodeError as exc:
            raise ParseError(
                Failure(ErrorCode.SOURCE_UNTRUSTED, detail="invalid liuiuqu json")
            ) from exc
        if not isinstance(payload, dict):
            raise ParseError(
                Failure(ErrorCode.SOURCE_UNTRUSTED, detail="invalid liuiuqu payload")
            )
        return payload

    @staticmethod
    def _issue(value: Any) -> int | None:
        try:
            issue = int(value)
        except (TypeError, ValueError):
            return None
        return issue if issue > 0 else None

    @staticmethod
    def _zodiac_text(value: Any) -> str:
        if not isinstance(value, list):
            return ""
        return "".join(
            character
            for character in "".join(str(item) for item in value)
            if character in CANONICAL_ZODIACS
        )
