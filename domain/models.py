from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import overload

from v2.domain.errors import Failure


class Position(str, Enum):
    TOP = "top"
    BOTTOM = "bottom"


class DocumentMethod(str, Enum):
    STATIC_PAGE = "static_page"
    DYNAMIC_API = "dynamic_api"
    BROWSER_DOM = "browser_dom"
    BROWSER_FRAME = "browser_frame"
    SCRIPT = "script"
    IMAGE_OCR = "image_ocr"
    LIST_DETAIL = "list_detail"


class SourceRole(str, Enum):
    PRIMARY = "primary"
    FALLBACK = "fallback"
    UNAPPROVED = "unapproved"


class ResultState(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"


def _required_text(value: str, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field_name} 不能为空")
    return normalized


def _metadata_pairs(
    values: tuple[tuple[str, str], ...],
) -> tuple[tuple[str, str], ...]:
    normalized = tuple(
        (_required_text(key, "metadata key"), str(value))
        for key, value in values
    )
    keys = [key for key, _value in normalized]
    if len(keys) != len(set(keys)):
        raise ValueError("metadata 键不能重复")
    return normalized


@dataclass(frozen=True, slots=True)
class Source:
    name: str
    url: str
    position: Position
    section_marker: str
    fetcher: str
    parser: str
    api_url: str = ""
    group_map: tuple[tuple[str, str], ...] = ()
    detail_link_keyword: str = ""
    aliases: tuple[str, ...] = ()
    data_marker: str = ""
    source_policy: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _required_text(self.name, "name"))
        object.__setattr__(self, "url", _required_text(self.url, "url"))
        if not isinstance(self.position, Position):
            raise TypeError("position 必须是 Position")
        object.__setattr__(
            self,
            "section_marker",
            str(self.section_marker).strip(),
        )
        object.__setattr__(
            self,
            "fetcher",
            _required_text(self.fetcher, "fetcher"),
        )
        object.__setattr__(
            self,
            "parser",
            _required_text(self.parser, "parser"),
        )
        object.__setattr__(self, "api_url", str(self.api_url).strip())
        normalized_group_map = tuple(
            (
                _required_text(key, "group_map key"),
                _required_text(value, "group_map value"),
            )
            for key, value in self.group_map
        )
        group_keys = [key for key, _value in normalized_group_map]
        if len(group_keys) != len(set(group_keys)):
            raise ValueError("group_map 键不能重复")
        object.__setattr__(self, "group_map", normalized_group_map)
        object.__setattr__(
            self,
            "detail_link_keyword",
            str(self.detail_link_keyword).strip(),
        )
        normalized_aliases = tuple(
            _required_text(alias, "alias") for alias in self.aliases
        )
        if len(normalized_aliases) != len(set(normalized_aliases)):
            raise ValueError("aliases 不能重复")
        object.__setattr__(self, "aliases", normalized_aliases)
        object.__setattr__(
            self,
            "data_marker",
            str(self.data_marker).strip(),
        )
        normalized_policy = tuple(
            _required_text(method, "source_policy method")
            for method in self.source_policy
        )
        supported_methods = {method.value for method in DocumentMethod}
        unsupported = tuple(
            method
            for method in normalized_policy
            if method not in supported_methods
        )
        if unsupported:
            raise ValueError(
                f"source_policy 包含未知文档类型: {', '.join(unsupported)}"
            )
        if len(normalized_policy) != len(set(normalized_policy)):
            raise ValueError("source_policy 不能重复")
        object.__setattr__(self, "source_policy", normalized_policy)


@dataclass(frozen=True, slots=True)
class Document:
    label: str
    url: str
    text: str
    method: DocumentMethod
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", _required_text(self.label, "label"))
        object.__setattr__(self, "url", _required_text(self.url, "url"))
        if not isinstance(self.method, DocumentMethod):
            raise TypeError("method 必须是 DocumentMethod")
        object.__setattr__(self, "text", str(self.text))
        object.__setattr__(self, "metadata", _metadata_pairs(self.metadata))


@dataclass(frozen=True, slots=True)
class Evidence:
    method: str
    source_line: str
    directory_anchor: str
    document_label: str
    metadata: tuple[tuple[str, str], ...] = ()
    document_url: str = ""
    document_method: str = ""
    actual_anchor_line: str = ""
    anchor_index: int = -1
    anchor_occurrence: int = 0
    block_id: str = ""
    block_start: int = -1
    block_end: int = -1
    candidate_index_in_block: int = -1
    source_role: SourceRole = SourceRole.PRIMARY
    source_priority: int = 0
    parser_id: str = ""
    raw_issue_line: str = ""
    raw_zodiac_line: str = ""
    data_marker: str = ""
    direction_window: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "method",
            _required_text(self.method, "evidence method"),
        )
        object.__setattr__(self, "source_line", str(self.source_line))
        object.__setattr__(
            self,
            "directory_anchor",
            str(self.directory_anchor).strip(),
        )
        object.__setattr__(
            self,
            "document_label",
            _required_text(self.document_label, "document_label"),
        )
        object.__setattr__(self, "metadata", _metadata_pairs(self.metadata))
        object.__setattr__(self, "document_url", str(self.document_url).strip())
        object.__setattr__(
            self,
            "document_method",
            str(self.document_method).strip(),
        )
        object.__setattr__(
            self,
            "actual_anchor_line",
            str(self.actual_anchor_line).strip(),
        )
        for field_name in (
            "anchor_index",
            "anchor_occurrence",
            "block_start",
            "block_end",
            "candidate_index_in_block",
            "source_priority",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"{field_name} 必须是整数")
        object.__setattr__(self, "block_id", str(self.block_id).strip())
        if not isinstance(self.source_role, SourceRole):
            raise TypeError("source_role 必须是 SourceRole")
        object.__setattr__(self, "parser_id", str(self.parser_id).strip())
        object.__setattr__(
            self,
            "raw_issue_line",
            str(self.raw_issue_line),
        )
        object.__setattr__(
            self,
            "raw_zodiac_line",
            str(self.raw_zodiac_line),
        )
        object.__setattr__(self, "data_marker", str(self.data_marker).strip())
        direction_window = tuple(self.direction_window)
        if any(
            not isinstance(issue, int)
            or isinstance(issue, bool)
            or issue <= 0
            for issue in direction_window
        ):
            raise ValueError("direction_window 必须只包含正整数")
        object.__setattr__(self, "direction_window", direction_window)


@dataclass(frozen=True, slots=True)
class BlockEvidence:
    document_label: str
    document_url: str
    document_method: str
    directory_anchor: str
    actual_anchor_line: str
    anchor_index: int
    anchor_occurrence: int
    block_id: str
    block_start: int
    block_end: int
    source_role: SourceRole
    source_priority: int
    parser_id: str
    data_marker: str
    observed_issues: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        for field_name in (
            "document_label",
            "document_url",
            "document_method",
            "directory_anchor",
            "actual_anchor_line",
            "block_id",
            "parser_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name),
            )
        if not isinstance(self.source_role, SourceRole):
            raise TypeError("source_role 必须是 SourceRole")
        for field_name in (
            "anchor_index",
            "anchor_occurrence",
            "block_start",
            "block_end",
            "source_priority",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"{field_name} 必须是整数")
            if value < 0:
                raise ValueError(f"{field_name} 不能小于 0")
        if self.block_end <= self.block_start:
            raise ValueError("block_end 必须大于 block_start")
        if not self.block_start <= self.anchor_index < self.block_end:
            raise ValueError("anchor_index 必须位于 block 边界内")
        object.__setattr__(self, "data_marker", str(self.data_marker).strip())
        observed = tuple(self.observed_issues)
        if any(
            not isinstance(issue, int)
            or isinstance(issue, bool)
            or issue <= 0
            for issue in observed
        ):
            raise ValueError("observed_issues 必须只包含正整数")
        object.__setattr__(
            self,
            "observed_issues",
            tuple(dict.fromkeys(observed)),
        )


@dataclass(frozen=True, slots=True)
class Record:
    issue: int
    zodiacs: tuple[str, ...]
    evidence: Evidence

    def __post_init__(self) -> None:
        if not isinstance(self.issue, int) or isinstance(self.issue, bool):
            raise TypeError("issue 必须是整数")
        if self.issue <= 0:
            raise ValueError("issue 必须大于 0")
        normalized_zodiacs = tuple(
            _required_text(zodiac, "zodiac") for zodiac in self.zodiacs
        )
        if not normalized_zodiacs:
            raise ValueError("zodiacs 不能为空")
        object.__setattr__(self, "zodiacs", normalized_zodiacs)
        if not isinstance(self.evidence, Evidence):
            raise TypeError("evidence 必须是 Evidence")

    @property
    def zodiac_text(self) -> str:
        return "".join(self.zodiacs)


@dataclass(frozen=True, slots=True)
class RecordSet(Sequence[Record]):
    records: tuple[Record, ...] = ()
    blocks: tuple[BlockEvidence, ...] = ()

    def __post_init__(self) -> None:
        records = tuple(self.records)
        blocks = tuple(self.blocks)
        if any(not isinstance(record, Record) for record in records):
            raise TypeError("records 必须只包含 Record")
        if any(not isinstance(block, BlockEvidence) for block in blocks):
            raise TypeError("blocks 必须只包含 BlockEvidence")
        object.__setattr__(self, "records", records)
        object.__setattr__(self, "blocks", blocks)

    def __len__(self) -> int:
        return len(self.records)

    @overload
    def __getitem__(self, index: int) -> Record: ...

    @overload
    def __getitem__(self, index: slice) -> tuple[Record, ...]: ...

    def __getitem__(
        self,
        index: int | slice,
    ) -> Record | tuple[Record, ...]:
        return self.records[index]

    def __iter__(self) -> Iterator[Record]:
        return iter(self.records)


@dataclass(frozen=True, slots=True)
class History:
    records: tuple[Record, ...] = ()
    current_issue: int | None = None
    failures: tuple[Failure, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "records", tuple(self.records))
        object.__setattr__(self, "failures", tuple(self.failures))
        if self.current_issue is not None and (
            not isinstance(self.current_issue, int)
            or isinstance(self.current_issue, bool)
            or self.current_issue <= 0
        ):
            raise ValueError("current_issue 必须是正整数")
        if any(not isinstance(record, Record) for record in self.records):
            raise TypeError("records 必须只包含 Record")
        if any(not isinstance(failure, Failure) for failure in self.failures):
            raise TypeError("failures 必须只包含 Failure")

    def records_for(self, issue: int) -> tuple[Record, ...]:
        return tuple(record for record in self.records if record.issue == issue)


@dataclass(frozen=True, slots=True)
class Result:
    source: Source
    requested_issues: tuple[int, ...]
    history: History
    state: ResultState
    failures: tuple[Failure, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.source, Source):
            raise TypeError("source 必须是 Source")
        issues = tuple(self.requested_issues)
        if not issues or any(
            not isinstance(issue, int)
            or isinstance(issue, bool)
            or issue <= 0
            for issue in issues
        ):
            raise ValueError("requested_issues 必须包含正整数")
        if len(issues) != len(set(issues)):
            raise ValueError("requested_issues 不能重复")
        object.__setattr__(self, "requested_issues", issues)
        if not isinstance(self.history, History):
            raise TypeError("history 必须是 History")
        if not isinstance(self.state, ResultState):
            raise TypeError("state 必须是 ResultState")
        failures = tuple(self.failures)
        if any(not isinstance(failure, Failure) for failure in failures):
            raise TypeError("failures 必须只包含 Failure")
        object.__setattr__(self, "failures", failures)
        if self.state is ResultState.SUCCESS and (
            failures or self.history.failures
        ):
            raise ValueError("成功结果不能包含 failure")
        if self.state is ResultState.FAILURE and not failures:
            raise ValueError("失败结果必须包含 failure")
        if self.state is ResultState.PARTIAL and (
            not failures or not self.history.records
        ):
            raise ValueError("部分结果必须同时包含记录和 failure")

    @property
    def successful(self) -> bool:
        return self.state is ResultState.SUCCESS

    @classmethod
    def succeeded(
        cls,
        source: Source,
        requested_issues: tuple[int, ...],
        history: History,
    ) -> Result:
        return cls(
            source=source,
            requested_issues=requested_issues,
            history=history,
            state=ResultState.SUCCESS,
        )

    @classmethod
    def failed(
        cls,
        source: Source,
        requested_issues: tuple[int, ...],
        *failures: Failure,
    ) -> Result:
        if not failures:
            raise ValueError("失败结果必须包含 failure")
        return cls(
            source=source,
            requested_issues=requested_issues,
            history=History(failures=tuple(failures)),
            state=ResultState.FAILURE,
            failures=tuple(failures),
        )
