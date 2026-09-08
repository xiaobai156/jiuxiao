from __future__ import annotations

from v2.domain.errors import ErrorCode, Failure
from v2.domain.models import Document, RecordSet, Source
from v2.parsers.custom.complement_three import ComplementThreeParser
from v2.parsers.direct_nine import DirectNineParser
from v2.parsers.registry import ParseError, normalize_document_text


class NamedSectionParser:
    def parse(
        self,
        source: Source,
        documents: tuple[Document, ...],
        issues: tuple[int, ...],
    ) -> RecordSet:
        marker = source.section_marker
        if not marker:
            raise ParseError(
                Failure(
                    ErrorCode.CONFIG_INVALID,
                    detail="named_section requires section_marker",
                )
            )
        selected: list[Document] = []
        for document in documents:
            lines = normalize_document_text(document.text).splitlines()
            for start, line in enumerate(lines):
                if line != marker:
                    continue
                end = self._section_end(lines, start + 1, source)
                selected.append(
                    Document(
                        label=document.label,
                        url=document.url,
                        text="\n".join(lines[start:end]),
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
                    context=(("anchor", marker),),
                )
            )
        data_marker = source.data_marker or (
            "绝杀三肖" if "绝杀三肖" in marker else "九肖"
        )
        parser = (
            ComplementThreeParser("named_section", data_marker)
            if "绝杀" in data_marker
            else DirectNineParser("named_section")
        )
        records = []
        blocks = []
        for document in selected:
            parsed = parser.parse(source, (document,), issues)
            records.extend(parsed.records)
            blocks.extend(parsed.blocks)
        return RecordSet(tuple(records), tuple(blocks))

    @staticmethod
    def _section_end(
        lines: list[str],
        start: int,
        source: Source,
    ) -> int:
        terms = (source.name, *source.aliases)
        for index in range(start, len(lines)):
            if any(
                term
                and lines[index].startswith(f"{term}【")
                and lines[index].endswith("】")
                for term in terms
            ):
                return index
        return len(lines)
