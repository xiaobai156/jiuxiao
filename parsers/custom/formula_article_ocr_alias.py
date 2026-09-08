from __future__ import annotations

from dataclasses import replace

from v2.domain.models import Document, DocumentMethod, Source
from v2.parsers.custom.formula_article_adaptive import (
    FormulaArticleAdaptiveParser,
)
from v2.parsers.registry import ZODIACS


class FormulaArticleOcrAliasParser(FormulaArticleAdaptiveParser):
    """Repair one unambiguous OCR glyph inside a linked formula image.

    PaddleOCR can read ``兔`` as the visually similar non-zodiac glyph
    ``免``.  The correction is accepted only when the payload after ``下期``
    contains exactly eight legal, unique zodiacs plus one ``免`` and replacing
    that glyph produces exactly nine legal, unique zodiacs.  Original and
    corrected lines are retained in document metadata for audit evidence.
    """

    parser_id = "formula_article_ocr_alias"

    def parse(
        self,
        source: Source,
        documents: tuple[Document, ...],
        issues: tuple[int, ...],
    ):
        repaired = tuple(self._repair_document(document) for document in documents)
        return super().parse(source, repaired, issues)

    @classmethod
    def _repair_document(cls, document: Document) -> Document:
        if document.method is not DocumentMethod.IMAGE_OCR:
            return document

        corrected_lines: list[str] = []
        originals: list[str] = []
        corrections: list[str] = []
        for line in document.text.splitlines():
            corrected = cls._repair_line(line)
            corrected_lines.append(corrected)
            if corrected != line:
                originals.append(line)
                corrections.append(corrected)
        if not originals:
            return document

        metadata = tuple(
            (key, value)
            for key, value in document.metadata
            if key
            not in {
                "ocr_correction",
                "ocr_original_line",
                "ocr_corrected_line",
            }
        )
        return replace(
            document,
            text="\n".join(corrected_lines),
            metadata=(
                *metadata,
                ("ocr_correction", "免->兔"),
                ("ocr_original_line", " || ".join(originals)),
                ("ocr_corrected_line", " || ".join(corrections)),
            ),
        )

    @staticmethod
    def _repair_line(line: str) -> str:
        if "下期" not in line:
            return line
        prefix, payload = line.split("下期", maxsplit=1)
        if payload.count("免") != 1:
            return line
        before = tuple(character for character in payload if character in ZODIACS)
        corrected_payload = payload.replace("免", "兔")
        after = tuple(
            character for character in corrected_payload if character in ZODIACS
        )
        if (
            len(before) != 8
            or len(set(before)) != 8
            or len(after) != 9
            or len(set(after)) != 9
        ):
            return line
        return f"{prefix}下期{corrected_payload}"
