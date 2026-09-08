from __future__ import annotations

import re

from v2.domain.errors import ErrorCode, Failure
from v2.domain.models import Document, RecordSet, Source
from v2.parsers.direct_nine import DirectNineParser
from v2.parsers.grouped import GroupedParser
from v2.parsers.registry import ParseError, normalize_document_text


POST_DATE_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$"
)


class ProfileHistoryParser:
    def parse(
        self,
        source: Source,
        documents: tuple[Document, ...],
        issues: tuple[int, ...],
    ) -> RecordSet:
        selected: list[Document] = []
        for document in documents:
            for start, section in self._matching_posts(document.text, source):
                selected.append(
                    Document(
                        label=document.label,
                        url=document.url,
                        text="\n".join(section),
                        method=document.method,
                        metadata=(
                            *(
                                (key, value)
                                for key, value in document.metadata
                                if key != "line_offset"
                            ),
                            ("line_offset", str(start)),
                        ),
                    )
                )
        if not selected:
            raise ParseError(
                Failure(
                    ErrorCode.ANCHOR_MISSING,
                    context=(
                        ("author", source.name),
                        ("anchor", source.section_marker or source.name),
                    ),
                )
            )
        parser = (
            GroupedParser("profile_history")
            if source.group_map
            else DirectNineParser("profile_history")
        )
        parsed_posts: list[tuple[Document, RecordSet]] = []
        for document in selected:
            parsed = parser.parse(source, (document,), issues)
            parsed_posts.append((document, parsed))
        return self._deduplicate_identical_posts(parsed_posts, issues)

    @staticmethod
    def _deduplicate_identical_posts(
        parsed_posts: list[tuple[Document, RecordSet]],
        issues: tuple[int, ...],
    ) -> RecordSet:
        if len(parsed_posts) <= 1:
            return parsed_posts[0][1] if parsed_posts else RecordSet()

        signatures = tuple(
            (
                parsed,
                tuple(
                    tuple(
                        record.zodiac_text
                        for record in parsed.records
                        if record.issue == issue
                    )
                    for issue in issues
                ),
            )
            for _document, parsed in parsed_posts
        )
        complete = tuple(
            item
            for item in signatures
            if all(values for values in item[1])
        )
        if complete and all(item[1] == complete[0][1] for item in complete):
            return complete[0][0]

        return RecordSet(
            tuple(
                record
                for _document, parsed in parsed_posts
                for record in parsed.records
            ),
            tuple(
                block
                for _document, parsed in parsed_posts
                for block in parsed.blocks
            ),
        )

    @staticmethod
    def _matching_posts(
        text: str,
        source: Source,
    ) -> tuple[tuple[int, tuple[str, ...]], ...]:
        lines = normalize_document_text(text).splitlines()
        date_indexes = tuple(
            index
            for index, line in enumerate(lines)
            if POST_DATE_PATTERN.fullmatch(line)
        )
        author_terms = (source.name, *source.aliases)
        matches: list[tuple[int, tuple[str, ...]]] = []
        for position, date_index in enumerate(date_indexes):
            start = max(0, date_index - 1)
            next_date = (
                date_indexes[position + 1]
                if position + 1 < len(date_indexes)
                else len(lines) + 1
            )
            end = max(start + 1, next_date - 1)
            section = tuple(lines[start:end])
            author = section[0] if section else ""
            if not any(
                term
                and re.fullmatch(
                    rf"(?:作者\s*[:：]\s*)?{re.escape(term)}",
                    author,
                    re.IGNORECASE,
                )
                for term in author_terms
            ):
                continue
            if source.section_marker and not any(
                source.section_marker in line for line in section
            ):
                continue
            matches.append((start, section))
        return tuple(matches)
