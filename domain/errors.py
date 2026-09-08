from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ErrorCode(str, Enum):
    CONFIG_INVALID = "CONFIG_INVALID"
    DUPLICATE_SOURCE = "DUPLICATE_SOURCE"
    FETCH_FAILED = "FETCH_FAILED"
    HTTP_ERROR = "HTTP_ERROR"
    API_RECORD_MISMATCH = "API_RECORD_MISMATCH"
    ANCHOR_MISSING = "ANCHOR_MISSING"
    DIRECTION_INVALID = "DIRECTION_INVALID"
    ISSUE_MISSING = "ISSUE_MISSING"
    LOCKED_CONTENT = "LOCKED_CONTENT"
    INVALID_ZODIAC_COUNT = "INVALID_ZODIAC_COUNT"
    GROUP_EVIDENCE_MISSING = "GROUP_EVIDENCE_MISSING"
    CANDIDATE_CONFLICT = "CANDIDATE_CONFLICT"
    BLOCK_AMBIGUOUS = "BLOCK_AMBIGUOUS"
    DOCUMENT_CONFLICT = "DOCUMENT_CONFLICT"
    SOURCE_UNTRUSTED = "SOURCE_UNTRUSTED"
    CROSS_DOMAIN = "CROSS_DOMAIN"
    WRITE_FAILED = "WRITE_FAILED"


@dataclass(frozen=True, slots=True)
class Failure:
    code: ErrorCode
    detail: str = ""
    context: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.code, ErrorCode):
            raise TypeError("code 必须是 ErrorCode")
        normalized_context = tuple(
            (str(key).strip(), str(value))
            for key, value in self.context
        )
        if any(not key for key, _value in normalized_context):
            raise ValueError("context 键不能为空")
        object.__setattr__(self, "context", normalized_context)
