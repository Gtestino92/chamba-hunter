from collections import Counter
from dataclasses import dataclass

from chamba_hunter.repositories.job_matching_repository import MatchingCandidateRow
from chamba_hunter.services.job_matching_service import (
    BACKEND_SOFTWARE_V1,
    PROFESSIONAL_RELEVANCE_FLOOR,
    SSR_SENIOR_BACKEND_SOFTWARE_V1,
    MatchDecision,
    _match,
    evaluate_candidate,
)


@dataclass(frozen=True, slots=True)
class CandidateComparison:
    candidate: MatchingCandidateRow
    legacy: MatchDecision
    target_legacy_skills: MatchDecision
    target_v3_skills: MatchDecision


@dataclass(frozen=True, slots=True)
class SearchRecallAudit:
    comparisons: tuple[CandidateComparison, ...]

    @property
    def candidate_count(self) -> int:
        return len(self.comparisons)

    def level_distribution(self, variant: str) -> dict[str, int]:
        counts = Counter(
            getattr(item, variant).match_level
            for item in self.comparisons
        )
        return {
            level: counts[level]
            for level in ("LOW", "MEDIUM", "HIGH", "VERY_HIGH")
        }


def evaluate_search_recall(
    candidates: list[MatchingCandidateRow],
) -> SearchRecallAudit:
    comparisons = []
    for candidate in candidates:
        comparisons.append(
            CandidateComparison(
                candidate=candidate,
                legacy=_match(candidate, profile=BACKEND_SOFTWARE_V1),
                target_legacy_skills=_match(
                    candidate,
                    profile=SSR_SENIOR_BACKEND_SOFTWARE_V1,
                ),
                target_v3_skills=evaluate_candidate(
                    candidate,
                    SSR_SENIOR_BACKEND_SOFTWARE_V1,
                ),
            )
        )

    return SearchRecallAudit(tuple(comparisons))


def qualifies(decision: MatchDecision) -> bool:
    return decision.score >= PROFESSIONAL_RELEVANCE_FLOOR
