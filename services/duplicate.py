from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from v2.domain.models import History


class DuplicateState(str, Enum):
    CLEAR = "clear"
    MANUAL_REVIEW = "manual_review"
    DUPLICATE = "duplicate"


@dataclass(frozen=True, slots=True)
class BaselineHistory:
    identity_key: str
    name: str
    history: History


@dataclass(frozen=True, slots=True)
class DuplicateMatch:
    identity_key: str
    name: str
    issues: tuple[int, ...]
    values: tuple[tuple[int, str], ...]


@dataclass(frozen=True, slots=True)
class DuplicateDecision:
    state: DuplicateState
    matches: tuple[DuplicateMatch, ...]


class DuplicateChecker:
    def compare(
        self,
        candidate: History,
        baselines: tuple[BaselineHistory, ...],
        issues: tuple[int, ...],
    ) -> DuplicateDecision:
        candidate_values = self._values(candidate)
        matches: list[DuplicateMatch] = []
        for baseline in baselines:
            baseline_values = self._values(baseline.history)
            matched = tuple(
                issue
                for issue in issues
                if issue in candidate_values
                and candidate_values[issue] == baseline_values.get(issue)
            )
            if len(matched) < 3:
                continue
            matches.append(
                DuplicateMatch(
                    identity_key=baseline.identity_key,
                    name=baseline.name,
                    issues=matched,
                    values=tuple((issue, candidate_values[issue]) for issue in matched),
                )
            )

        highest = max((len(match.issues) for match in matches), default=0)
        if highest >= 6:
            state = DuplicateState.DUPLICATE
        elif highest >= 3:
            state = DuplicateState.MANUAL_REVIEW
        else:
            state = DuplicateState.CLEAR
        return DuplicateDecision(state=state, matches=tuple(matches))

    @staticmethod
    def _values(history: History) -> dict[int, str]:
        values: dict[int, str] = {}
        conflicts: set[int] = set()
        for record in history.records:
            previous = values.get(record.issue)
            if previous is not None and previous != record.zodiac_text:
                conflicts.add(record.issue)
            values[record.issue] = record.zodiac_text
        for issue in conflicts:
            values.pop(issue, None)
        return values
