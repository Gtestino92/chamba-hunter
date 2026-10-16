from collections import Counter
from dataclasses import dataclass, replace

from chamba_hunter.repositories.job_matching_repository import MatchingCandidateRow
from chamba_hunter.repositories.job_skill_repository import SkillCandidateRow
from chamba_hunter.services.job_matching_service import (
    BACKEND_SOFTWARE_V1,
    PROFESSIONAL_RELEVANCE_FLOOR,
    SENIOR_BACKEND_SOFTWARE_V1,
    MatchDecision,
    _match,
)
from chamba_hunter.services.job_skill_classification_service import (
    extract_v3_additional_skill_keys,
    extract_v3_domain_evidence,
)


@dataclass(frozen=True, slots=True)
class CandidateComparison:
    candidate: MatchingCandidateRow
    legacy: MatchDecision
    senior_legacy_skills: MatchDecision
    senior_v3_skills: MatchDecision


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
        skill_candidate = SkillCandidateRow(
            record_kind=candidate.record_kind,
            record_id=candidate.record_id,
            source_type=candidate.source_type,
            origin=candidate.origin,
            company_name=candidate.company_name,
            eligibility_status=candidate.eligibility_status,
            occupation_class=candidate.occupation_class,
            backend_relevance=candidate.backend_relevance,
            title=candidate.title,
            description=candidate.description,
        )
        v3_skills = set(candidate.skills)
        v3_skills.update(extract_v3_additional_skill_keys(skill_candidate))
        v3_skills.update(extract_v3_domain_evidence(skill_candidate))
        v3_candidate = replace(candidate, skills=tuple(sorted(v3_skills)))

        comparisons.append(
            CandidateComparison(
                candidate=candidate,
                legacy=_match(candidate, profile=BACKEND_SOFTWARE_V1),
                senior_legacy_skills=_match(
                    candidate,
                    profile=SENIOR_BACKEND_SOFTWARE_V1,
                ),
                senior_v3_skills=_match(
                    v3_candidate,
                    profile=SENIOR_BACKEND_SOFTWARE_V1,
                ),
            )
        )

    return SearchRecallAudit(tuple(comparisons))


def qualifies(decision: MatchDecision) -> bool:
    return decision.score >= PROFESSIONAL_RELEVANCE_FLOOR
