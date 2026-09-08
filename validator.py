from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

from v2.domain.errors import ErrorCode, Failure
from v2.domain.models import (
    BlockEvidence,
    History,
    Position,
    Record,
    RecordSet,
    Source,
    SourceRole,
)
from v2.parsers.registry import (
    CANONICAL_ZODIACS,
    LOCKED_MARKERS,
    ZODIACS,
    anchor_terms,
    candidate_has_data_semantic,
    group_mapping_text,
)


@dataclass(frozen=True, slots=True)
class VerifiedHistory:
    history: History
    requested_issues: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class _BlockWindow:
    block: BlockEvidence
    records: tuple[Record, ...]
    issue_order: tuple[int, ...]


class ValidationError(ValueError):
    def __init__(self, failure: Failure) -> None:
        super().__init__(failure.code.value)
        self.failure = failure


class Validator:
    def validate(
        self,
        source: Source,
        records: RecordSet,
        requested_issues: tuple[int, ...],
        *,
        history_mode: bool = False,
        history_limit: int | None = None,
    ) -> VerifiedHistory:
        requested = tuple(requested_issues)
        if not requested:
            raise ValueError("requested_issues 不能为空")
        if history_limit is not None and history_limit <= 0:
            raise ValueError("history_limit 必须大于 0")
        search_limit = (
            history_limit or max(3, len(requested))
            if history_mode
            else 3
        )
        if not isinstance(records, RecordSet):
            raise TypeError("records must be RecordSet")
        return self._validate_record_set(
            source,
            records,
            requested,
            search_limit,
        )

    def _validate_record_set(
        self,
        source: Source,
        record_set: RecordSet,
        requested: tuple[int, ...],
        search_limit: int,
    ) -> VerifiedHistory:
        if not record_set.blocks:
            raise ValidationError(
                Failure(
                    ErrorCode.ISSUE_MISSING,
                    context=(("issue", str(requested[0])),),
                )
            )
        blocks_by_key = {
            self._block_key(block): block for block in record_set.blocks
        }
        if len(blocks_by_key) != len(record_set.blocks):
            raise ValidationError(
                Failure(
                    ErrorCode.SOURCE_UNTRUSTED,
                    detail="duplicate block identity",
                )
            )

        requested_set = set(requested)
        valid_records: list[Record] = []
        invalid_requested: set[tuple[int, tuple[str, str, str, str]]] = set()
        for record in record_set:
            try:
                self._validate_evidence(source, record, blocks_by_key)
            except ValidationError:
                if record.issue in requested_set:
                    raise
                continue
            if not self._valid_zodiacs(record):
                if record.issue in requested_set:
                    invalid_requested.add(
                        (record.issue, self._record_block_key(record))
                    )
                continue
            valid_records.append(record)

        approved = tuple(
            block
            for block in record_set.blocks
            if block.source_role is not SourceRole.UNAPPROVED
        )
        if not approved:
            raise ValidationError(
                Failure(
                    ErrorCode.SOURCE_UNTRUSTED,
                    detail="no approved source document",
                )
            )
        selected_priority = min(block.source_priority for block in approved)
        selected_blocks = tuple(
            block
            for block in approved
            if block.source_priority == selected_priority
        )
        windows = {
            self._block_key(block): self._window_for(
                source,
                block,
                valid_records,
                search_limit,
            )
            for block in record_set.blocks
        }

        selected: list[Record] = []
        selected_windows: list[_BlockWindow] = []
        for issue in requested:
            matches = tuple(
                window
                for block in selected_blocks
                if (
                    window := windows[self._block_key(block)]
                ).records
                and any(record.issue == issue for record in window.records)
            )
            if not matches:
                selected_keys = {
                    self._block_key(block) for block in selected_blocks
                }
                invalid_target = any(
                    invalid_issue == issue and block_key in selected_keys
                    for invalid_issue, block_key in invalid_requested
                )
                window_values = tuple(
                    dict.fromkeys(
                        issue_number
                        for block in selected_blocks
                        for issue_number in windows[
                            self._block_key(block)
                        ].issue_order
                    )
                )
                raise ValidationError(
                    Failure(
                        (
                            ErrorCode.INVALID_ZODIAC_COUNT
                            if invalid_target
                            else ErrorCode.ISSUE_MISSING
                        ),
                        context=(
                            ("issue", str(issue)),
                            (
                                "direction_window",
                                ",".join(map(str, window_values)),
                            ),
                        ),
                    )
                )

            selected_candidates = tuple(
                self._select_issue_candidate(source, window, issue)
                for window in matches
            )
            self._reject_block_ambiguity(
                issue,
                matches,
                selected_candidates,
            )
            values = tuple(
                dict.fromkeys(
                    record.zodiac_text for record in selected_candidates
                )
            )
            if len(values) != 1:
                code = (
                    ErrorCode.DOCUMENT_CONFLICT
                    if len(
                        {
                            self._document_key(window.block)
                            for window in matches
                        }
                    )
                    > 1
                    else ErrorCode.CANDIDATE_CONFLICT
                )
                raise ValidationError(
                    Failure(
                        code,
                        context=(
                            ("issue", str(issue)),
                            ("values", " | ".join(values)),
                        ),
                    )
            )

            selected_value = values[0]
            self._reject_same_block_outside_window_conflicts(
                issue,
                selected_value,
                matches,
                valid_records,
            )
            self._reject_lower_source_conflicts(
                issue,
                selected_value,
                matches,
                valid_records,
            )
            chosen_window = matches[0]
            chosen = next(
                record
                for record in selected_candidates
                if self._record_block_key(record)
                == self._block_key(chosen_window.block)
                and record.zodiac_text == selected_value
            )
            selected.append(
                replace(
                    chosen,
                    evidence=replace(
                        chosen.evidence,
                        direction_window=chosen_window.issue_order,
                    ),
                )
            )
            selected_windows.append(chosen_window)

        current_window = selected_windows[0]
        current_issue = (
            current_window.issue_order[0]
            if current_window.issue_order
            else selected[0].issue
        )
        return VerifiedHistory(
            history=History(
                records=tuple(selected),
                current_issue=current_issue,
            ),
            requested_issues=requested,
        )

    def _select_issue_candidate(
        self,
        source: Source,
        window: _BlockWindow,
        issue: int,
    ) -> Record:
        candidates = tuple(
            record for record in window.records if record.issue == issue
        )
        if not candidates:
            raise ValidationError(
                Failure(
                    ErrorCode.ISSUE_MISSING,
                    context=(
                        ("issue", str(issue)),
                        ("block_id", window.block.block_id),
                    ),
                )
            )
        values = tuple(dict.fromkeys(record.zodiac_text for record in candidates))
        if len(values) != 1:
            raise ValidationError(
                Failure(
                    ErrorCode.CANDIDATE_CONFLICT,
                    context=(
                        ("issue", str(issue)),
                        ("values", " | ".join(values)),
                    ),
                )
            )
        ordered = tuple(sorted(candidates, key=self._candidate_position))
        selected_index = 0 if source.position is Position.TOP else -1
        selected = ordered[selected_index]
        return self._mark_issue_position(
            selected,
            position=(
                1
                if selected_index == 0
                else len(ordered)
            ),
            count=len(ordered),
        )

    @staticmethod
    def _mark_issue_position(
        record: Record,
        *,
        position: int,
        count: int,
    ) -> Record:
        metadata = list(record.evidence.metadata)
        updates = {
            "issue_position": str(position),
            "issue_count": str(count),
            "issue_position_order": "top_to_bottom",
        }
        existing = {key: index for index, (key, _value) in enumerate(metadata)}
        for key, value in updates.items():
            index = existing.get(key)
            if index is None:
                metadata.append((key, value))
            else:
                metadata[index] = (key, value)
        return replace(
            record,
            evidence=replace(record.evidence, metadata=tuple(metadata)),
        )

    def _validate_evidence(
        self,
        source: Source,
        record: Record,
        blocks_by_key: dict[
            tuple[str, str, str, str],
            BlockEvidence,
        ],
    ) -> None:
        evidence = record.evidence
        key = (
            evidence.document_label,
            evidence.document_url,
            evidence.document_method,
            evidence.block_id,
        )
        block = blocks_by_key.get(key)
        if block is None:
            raise ValidationError(
                Failure(
                    ErrorCode.SOURCE_UNTRUSTED,
                    detail="candidate block is missing",
                )
            )
        accepted_anchors = set(anchor_terms(source))
        metadata = dict(evidence.metadata)
        if any(
            marker in line
            for marker in LOCKED_MARKERS
            for line in (
                evidence.source_line,
                evidence.raw_issue_line,
                evidence.raw_zodiac_line,
            )
        ):
            raise ValidationError(
                Failure(
                    ErrorCode.LOCKED_CONTENT,
                    context=(("issue", str(record.issue)),),
                )
            )
        try:
            line_index = int(metadata["line_index"])
        except (KeyError, ValueError) as exc:
            raise ValidationError(
                Failure(
                    ErrorCode.SOURCE_UNTRUSTED,
                    detail="invalid candidate position",
                )
            ) from exc
        structural_match = (
            evidence.directory_anchor in accepted_anchors
            and evidence.directory_anchor == block.directory_anchor
            and evidence.directory_anchor in evidence.actual_anchor_line
            and evidence.document_label == block.document_label
            and evidence.document_url == block.document_url
            and evidence.document_method == block.document_method
            and evidence.actual_anchor_line == block.actual_anchor_line
            and evidence.anchor_index == block.anchor_index
            and evidence.anchor_occurrence == block.anchor_occurrence
            and evidence.block_start == block.block_start
            and evidence.block_end == block.block_end
            and evidence.source_role is block.source_role
            and evidence.source_priority == block.source_priority
            and evidence.parser_id == source.parser == block.parser_id
            and evidence.candidate_index_in_block >= 0
            and evidence.block_start <= line_index < evidence.block_end
            and record.issue in block.observed_issues
        )
        if not structural_match:
            raise ValidationError(
                Failure(
                    ErrorCode.SOURCE_UNTRUSTED,
                    detail="candidate evidence is inconsistent",
                    context=(("issue", str(record.issue)),),
                )
            )
        marker = evidence.data_marker
        group_text = metadata.get("group_text", "")
        if source.group_map:
            mapping = dict(source.group_map)
            single_season = (
                evidence.parser_id
                in {
                    "single_season_complement",
                    "single_season_complement_canonical",
                }
            )
            canonical_single_season = (
                evidence.parser_id
                == "single_season_complement_canonical"
            )
            expected_group_type = (
                "春夏秋冬" if single_season else "".join(mapping)
            )
            expected_conversion = (
                "".join(
                    zodiac
                    for zodiac in CANONICAL_ZODIACS
                    if zodiac not in set(mapping.get(group_text, ""))
                )
                if canonical_single_season
                else "".join(
                    mapping[key]
                    for key in "春夏秋冬"
                    if key in mapping and key != group_text
                )
                if single_season
                else "".join(mapping.get(character, "") for character in group_text)
            )
            grouped_evidence_matches = (
                metadata.get("group_type") == expected_group_type
                and metadata.get("group_mapping")
                == group_mapping_text(mapping)
                and bool(group_text)
                and all(character in mapping for character in group_text)
                and metadata.get("conversion") == expected_conversion
                and expected_conversion == record.zodiac_text
            )
            if not grouped_evidence_matches:
                raise ValidationError(
                    Failure(
                        ErrorCode.SOURCE_UNTRUSTED,
                        detail="group evidence is inconsistent",
                        context=(("issue", str(record.issue)),),
                    )
                )
        grouped_marker = (
            marker == group_text
            and len(group_text) == 3
            and len(set(group_text)) == 3
            and all(character in block.data_marker for character in group_text)
        )
        if (
            not marker
            or (
                not grouped_marker
                and (
                    marker != block.data_marker
                    or not candidate_has_data_semantic(
                        source,
                        marker,
                        directory_anchor=evidence.directory_anchor,
                        actual_anchor_line=evidence.actual_anchor_line,
                        candidate_lines=(
                            evidence.raw_issue_line,
                            evidence.raw_zodiac_line,
                            evidence.source_line,
                            metadata.get("data_marker_line", ""),
                        ),
                    )
                )
            )
        ):
            raise ValidationError(
                Failure(
                    ErrorCode.SOURCE_UNTRUSTED,
                    detail="target data marker is missing",
                    context=(("issue", str(record.issue)),),
                )
            )

    @staticmethod
    def _valid_zodiacs(record: Record) -> bool:
        return (
            len(record.zodiacs) == 9
            and len(set(record.zodiacs)) == 9
            and all(zodiac in ZODIACS for zodiac in record.zodiacs)
        )

    def _window_for(
        self,
        source: Source,
        block: BlockEvidence,
        valid_records: list[Record],
        search_limit: int,
    ) -> _BlockWindow:
        key = self._block_key(block)
        block_records = [
            record
            for record in valid_records
            if self._record_block_key(record) == key
        ]
        block_records.sort(key=self._candidate_position)
        directional = (
            block_records
            if source.position is Position.TOP
            else list(reversed(block_records))
        )
        window: list[Record] = []
        issue_order: list[int] = []
        boundary_issue: int | None = None
        for record in directional:
            if boundary_issue is not None and record.issue != boundary_issue:
                break
            window.append(record)
            if record.issue not in issue_order:
                issue_order.append(record.issue)
                if len(issue_order) == search_limit:
                    boundary_issue = record.issue
        return _BlockWindow(
            block=block,
            records=tuple(window),
            issue_order=tuple(issue_order),
        )

    def _reject_block_ambiguity(
        self,
        issue: int,
        matches: tuple[_BlockWindow, ...],
        candidates: tuple[Record, ...],
    ) -> None:
        documents: dict[
            tuple[str, str, str],
            set[str],
        ] = {}
        for window in matches:
            documents.setdefault(
                self._document_key(window.block),
                set(),
            ).add(window.block.block_id)
        ambiguous = tuple(
            block_ids
            for block_ids in documents.values()
            if len(block_ids) > 1
        )
        if ambiguous and len({record.zodiac_text for record in candidates}) > 1:
            raise ValidationError(
                Failure(
                    ErrorCode.BLOCK_AMBIGUOUS,
                    context=(
                        ("issue", str(issue)),
                        (
                            "blocks",
                            " | ".join(
                                sorted(
                                    block_id
                                    for block_ids in ambiguous
                                    for block_id in block_ids
                                )
                            ),
                        ),
                    ),
                )
            )

    def _reject_lower_source_conflicts(
        self,
        issue: int,
        selected_value: str,
        selected_windows: tuple[_BlockWindow, ...],
        all_records: Sequence[Record],
    ) -> None:
        selected_keys = {
            self._block_key(window.block) for window in selected_windows
        }
        conflicting = [
            record
            for record in all_records
            if self._record_block_key(record) not in selected_keys
            and record.evidence.source_role is not SourceRole.UNAPPROVED
            and record.issue == issue
            and record.zodiac_text != selected_value
        ]
        if conflicting:
            raise ValidationError(
                Failure(
                    ErrorCode.DOCUMENT_CONFLICT,
                    context=(
                        ("issue", str(issue)),
                        (
                            "values",
                            " | ".join(
                                dict.fromkeys(
                                    (
                                        selected_value,
                                        *(
                                            record.zodiac_text
                                            for record in conflicting
                                        ),
                                    )
                                )
                            ),
                        ),
                    ),
                )
            )

    def _reject_same_block_outside_window_conflicts(
        self,
        issue: int,
        selected_value: str,
        selected_windows: tuple[_BlockWindow, ...],
        all_records: Sequence[Record],
    ) -> None:
        for window in selected_windows:
            block_key = self._block_key(window.block)
            window_positions = {
                self._candidate_position(record)
                for record in window.records
                if record.issue == issue
            }
            conflicting = [
                record
                for record in all_records
                if (
                    record.issue == issue
                    and self._record_block_key(record) == block_key
                    and self._candidate_position(record)
                    not in window_positions
                    and record.zodiac_text != selected_value
                )
            ]
            if conflicting:
                raise ValidationError(
                    Failure(
                        ErrorCode.CANDIDATE_CONFLICT,
                        context=(
                            ("issue", str(issue)),
                            (
                                "values",
                                " | ".join(
                                    dict.fromkeys(
                                        (
                                            selected_value,
                                            *(
                                                record.zodiac_text
                                                for record in conflicting
                                            ),
                                        )
                                    )
                                ),
                            ),
                        ),
                    )
                )

    @staticmethod
    def _block_key(
        block: BlockEvidence,
    ) -> tuple[str, str, str, str]:
        return (
            block.document_label,
            block.document_url,
            block.document_method,
            block.block_id,
        )

    @staticmethod
    def _record_block_key(
        record: Record,
    ) -> tuple[str, str, str, str]:
        evidence = record.evidence
        return (
            evidence.document_label,
            evidence.document_url,
            evidence.document_method,
            evidence.block_id,
        )

    @staticmethod
    def _document_key(
        block: BlockEvidence,
    ) -> tuple[str, str, str]:
        return (
            block.document_label,
            block.document_url,
            block.document_method,
        )

    @staticmethod
    def _candidate_position(record: Record) -> tuple[int, int]:
        metadata = dict(record.evidence.metadata)
        try:
            return (
                record.evidence.candidate_index_in_block,
                int(metadata["line_index"]),
            )
        except (KeyError, ValueError) as exc:
            raise ValidationError(
                Failure(
                    ErrorCode.SOURCE_UNTRUSTED,
                    detail="invalid candidate position",
                )
            ) from exc
