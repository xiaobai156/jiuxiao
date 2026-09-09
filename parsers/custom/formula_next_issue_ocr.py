from __future__ import annotations

from dataclasses import replace

from v2.domain.errors import ErrorCode, Failure
from v2.domain.models import Document, DocumentMethod, Record, RecordSet, Source
from v2.parsers.custom.common import select_current_content_mode
from v2.parsers.image_ocr import ImageOcrParser
from v2.parsers.registry import (
    LOCKED_MARKERS,
    ParseError,
    anchored_history_blocks,
    block_evidence_for,
    document_line_offset,
    evidence_for,
    joined_history_line,
    normalize_document_text,
)
from v2.parsers.safety import (
    issue_scoped_segments,
    joined_issue_content,
    observed_issues,
    with_complete_observed_issues,
    zodiac_fields,
)


class FormulaNextIssueOcrParser:
    """Parse current DOM/OCR formula blocks with ``N期 下期`` mapping."""

    parser_id = "formula_next_issue_ocr"

    def parse(
        self,
        source: Source,
        documents: tuple[Document, ...],
        issues: tuple[int, ...],
    ) -> RecordSet:
        source_documents = tuple(
            document
            for document in documents
            if document.method
            in (DocumentMethod.BROWSER_DOM, DocumentMethod.IMAGE_OCR)
        )
        if not source_documents:
            raise ParseError(
                Failure(
                    ErrorCode.SOURCE_UNTRUSTED,
                    detail=(
                        "formula next-issue parser requires browser DOM or "
                        "image OCR document"
                    ),
                )
            )

        requested = set(issues)
        data_marker = source.data_marker or "九肖"
        records: list[Record] = []
        blocks_evidence = []
        malformed_requested: set[int] = set()

        for document_index, document in enumerate(source_documents):
            text = normalize_document_text(document.text)
            if document.method is DocumentMethod.IMAGE_OCR:
                linked = ImageOcrParser._linked_image_block(document, source, text)
                blocks = (linked,) if linked is not None else ()
            else:
                blocks = anchored_history_blocks(
                    text,
                    source,
                    document_label=document.label,
                    line_offset=document_line_offset(document),
                )
            if not blocks:
                observed = self._observed_target_issues(text)
                if requested & observed:
                    raise ParseError(
                        Failure(
                            ErrorCode.SOURCE_UNTRUSTED,
                            detail="ocr target is not linked to its image anchor",
                        )
                    )
                continue

            for original_block in blocks:
                block = with_complete_observed_issues(original_block)
                parsed: list[
                    tuple[int, tuple[str, ...], str, str, int, str]
                ] = []
                invalid_lines: list[str] = []
                derived_issues: list[int] = []

                for anchored_index, anchored_line in enumerate(block.lines):
                    source_line = (
                        joined_issue_content(block.lines, anchored_index)
                        if document.method is DocumentMethod.IMAGE_OCR
                        else joined_history_line(block.lines, anchored_index)
                    )
                    for _printed_issue, scoped_line in issue_scoped_segments(
                        source_line
                    ):
                        candidates = self._candidates(scoped_line)
                        for target_issue, values, payload, mapping in candidates:
                            derived_issues.append(target_issue)
                            if target_issue in requested and any(
                                marker in scoped_line for marker in LOCKED_MARKERS
                            ):
                                raise ParseError(
                                    Failure(
                                        ErrorCode.LOCKED_CONTENT,
                                        context=(("issue", str(target_issue)),),
                                    )
                                )
                            if len(values) != 9 or len(set(values)) != 9:
                                invalid_lines.append(scoped_line)
                                if target_issue in requested:
                                    malformed_requested.add(target_issue)
                                continue
                            parsed.append(
                                (
                                    target_issue,
                                    values,
                                    scoped_line,
                                    payload,
                                    anchored_line.index,
                                    mapping,
                                )
                            )

                block = replace(
                    block,
                    observed_issues=tuple(
                        dict.fromkeys((*block.observed_issues, *derived_issues))
                    ),
                )
                blocks_evidence.append(
                    block_evidence_for(
                        source,
                        document,
                        block,
                        parser_id=self.parser_id,
                        data_marker=data_marker,
                    )
                )
                invalid_count = str(len(invalid_lines))
                for candidate_index, (
                    target_issue,
                    values,
                    source_line,
                    payload,
                    line_index,
                    mapping,
                ) in enumerate(parsed):
                    records.append(
                        Record(
                            issue=target_issue,
                            zodiacs=values,
                            evidence=evidence_for(
                                source,
                                document,
                                document_index,
                                block,
                                parser_id=self.parser_id,
                                method="image_ocr_formula",
                                source_line=source_line,
                                raw_issue_line=source_line,
                                raw_zodiac_line=payload,
                                line_index=line_index,
                                candidate_index_in_block=candidate_index,
                                data_marker=data_marker,
                                metadata=(
                                    ("issue_mapping", mapping),
                                    ("invalid_candidate_count", invalid_count),
                                ),
                            ),
                        )
                    )

        if not blocks_evidence:
            raise ParseError(Failure(ErrorCode.ANCHOR_MISSING))
        valid_requested = {record.issue for record in records} & requested
        if malformed_requested - valid_requested:
            issue = min(malformed_requested - valid_requested)
            raise ParseError(
                Failure(
                    ErrorCode.INVALID_ZODIAC_COUNT,
                    context=(("issue", str(issue)),),
                )
            )
        return select_current_content_mode(
            RecordSet(tuple(records), tuple(blocks_evidence)),
            issues,
        )

    @staticmethod
    def _candidates(
        source_line: str,
    ) -> tuple[tuple[int, tuple[str, ...], str, str], ...]:
        segments = issue_scoped_segments(source_line)
        if len(segments) != 1:
            return ()
        printed_issue, scoped_line = segments[0]
        marker = f"{printed_issue:03d}期"
        marker_index = scoped_line.find(marker)
        if marker_index < 0:
            return ()
        tail = scoped_line[marker_index + len(marker) :]
        if "下期" in tail:
            payload = tail.split("下期", maxsplit=1)[1]
            target_issue = printed_issue + 1
            mapping = "next_issue"
        else:
            payload = tail
            target_issue = printed_issue
            mapping = "explicit_issue"
        fields = zodiac_fields(payload)
        return tuple(
            (target_issue, values, payload, mapping)
            for values in fields
        )

    @classmethod
    def _candidate(
        cls,
        source_line: str,
    ) -> tuple[int, tuple[str, ...], str, str] | None:
        candidates = cls._candidates(source_line)
        return candidates[0] if len(candidates) == 1 else None

    @classmethod
    def _observed_target_issues(cls, text: str) -> set[int]:
        observed: set[int] = set()
        for line in text.splitlines():
            for _issue, scoped_line in issue_scoped_segments(line):
                observed.update(
                    candidate[0] for candidate in cls._candidates(scoped_line)
                )
        return observed
