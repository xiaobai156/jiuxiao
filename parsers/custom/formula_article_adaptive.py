from __future__ import annotations

import re
from dataclasses import replace

from v2.domain.errors import ErrorCode, Failure
from v2.domain.models import Document, DocumentMethod, Source
from v2.parsers.custom.formula_next_issue_ocr import (
    FormulaNextIssueOcrParser,
)
from v2.parsers.image_ocr import ImageOcrParser
from v2.parsers.registry import ParseError, normalize_document_text


class FormulaArticleAdaptiveParser(FormulaNextIssueOcrParser):
    """Parse only the target formula article body or its linked image."""

    parser_id = "formula_article_adaptive"
    _navigation_boundary = re.compile(r"^\s*(?:上一篇|下一篇)\s*(?::|：)?")

    def parse(
        self,
        source: Source,
        documents: tuple[Document, ...],
        issues: tuple[int, ...],
    ):
        scoped_documents: list[Document] = []
        for document in documents:
            if document.method is DocumentMethod.BROWSER_DOM:
                scoped_documents.extend(
                    self._dom_article_documents(document, source)
                )
                continue
            if document.method is not DocumentMethod.IMAGE_OCR:
                continue
            normalized = normalize_document_text(document.text)
            if (
                ImageOcrParser._linked_image_block(
                    document,
                    source,
                    normalized,
                )
                is not None
            ):
                scoped_documents.append(document)

        if not scoped_documents:
            raise ParseError(
                Failure(
                    ErrorCode.ANCHOR_MISSING,
                    context=(("anchor", source.section_marker),),
                )
            )
        return super().parse(source, tuple(scoped_documents), issues)

    @classmethod
    def _dom_article_documents(
        cls,
        document: Document,
        source: Source,
    ) -> tuple[Document, ...]:
        text = normalize_document_text(document.text)
        lines = text.splitlines()
        headers = tuple(
            index
            for index, line in enumerate(lines)
            if cls._is_target_header(line, source.section_marker)
        )
        scoped: list[Document] = []
        for occurrence, start in enumerate(headers, start=1):
            end = next(
                (
                    index
                    for index in range(start + 1, len(lines))
                    if cls._navigation_boundary.search(lines[index])
                ),
                None,
            )
            if end is None or end <= start:
                continue
            metadata = tuple(
                (key, value)
                for key, value in document.metadata
                if key not in {"line_offset", "data_marker_line"}
            )
            scoped.append(
                replace(
                    document,
                    label=f"{document.label}:formula-article:{occurrence}",
                    text="\n".join(lines[start:end]),
                    metadata=(
                        *metadata,
                        ("line_offset", str(start)),
                        ("data_marker_line", lines[start]),
                    ),
                )
            )
        return tuple(scoped)

    @staticmethod
    def _is_target_header(line: str, marker: str) -> bool:
        if not marker:
            return False
        return bool(
            re.search(
                rf"^\s*\d{{1,3}}\s*期\s*(?::|：)?\s*.*{re.escape(marker)}",
                line,
            )
        )
