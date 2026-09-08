from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from v2.config.repository import SourceRepository
from v2.domain.models import Result, Source
from v2.services.duplicate import (
    BaselineHistory,
    DuplicateChecker,
    DuplicateDecision,
    DuplicateState,
)


class CrawlOne(Protocol):
    async def crawl_one(
        self,
        source: Source,
        issues: tuple[int, ...],
        *,
        history_mode: bool = False,
    ) -> Result: ...


class OnboardingState(str, Enum):
    ACCEPTED = "accepted"
    MANUAL_REVIEW = "manual_review"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class OnboardingDecision:
    state: OnboardingState
    result: Result
    duplicate: DuplicateDecision | None = None


class OnboardingService:
    def __init__(
        self,
        crawl: CrawlOne,
        duplicate_checker: DuplicateChecker,
        repository: SourceRepository,
    ) -> None:
        self._crawl = crawl
        self._duplicate_checker = duplicate_checker
        self._repository = repository

    async def onboard(
        self,
        candidate: Source,
        baselines: tuple[BaselineHistory, ...],
        issues: tuple[int, ...],
        *,
        allow_shared_url: bool = False,
    ) -> OnboardingDecision:
        if len(issues) != 10 or len(set(issues)) != 10:
            raise ValueError("onboarding requires exactly ten distinct issues")
        result = await self._crawl.crawl_one(
            candidate,
            issues,
            history_mode=True,
        )
        if not result.successful:
            return OnboardingDecision(OnboardingState.FAILED, result)
        record_issues = tuple(record.issue for record in result.history.records)
        if (
            result.requested_issues != issues
            or len(record_issues) != 10
            or set(record_issues) != set(issues)
        ):
            raise ValueError("onboarding history is incomplete")

        duplicate = self._duplicate_checker.compare(
            result.history,
            baselines,
            issues,
        )
        if duplicate.state is DuplicateState.DUPLICATE:
            return OnboardingDecision(
                OnboardingState.REJECTED,
                result,
                duplicate,
            )
        if duplicate.state is DuplicateState.MANUAL_REVIEW:
            return OnboardingDecision(
                OnboardingState.MANUAL_REVIEW,
                result,
                duplicate,
            )
        self._repository.add(
            candidate,
            allow_shared_url=allow_shared_url,
        )
        return OnboardingDecision(OnboardingState.ACCEPTED, result, duplicate)
