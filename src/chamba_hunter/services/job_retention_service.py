from collections import Counter
from dataclasses import dataclass

from chamba_hunter.domain.common import utc_now
from chamba_hunter.repositories.job_retention_repository import (
    JobRetentionRepository,
    RetentionCandidateRow,
    RetentionDeleteCounts,
)


PHYSICAL_RETENTION_DAYS = 180


@dataclass(frozen=True, slots=True)
class JobRetentionSummary:
    apply: bool
    candidates: tuple[RetentionCandidateRow, ...]
    deletable: tuple[RetentionCandidateRow, ...]
    protected: tuple[RetentionCandidateRow, ...]
    protection_counts: dict[str, int]
    deleted: RetentionDeleteCounts


class JobRetentionService:
    def __init__(self, repository: JobRetentionRepository) -> None:
        self.repository = repository

    def run(self, *, apply: bool = False) -> JobRetentionSummary:
        candidates = tuple(
            self.repository.list_old_candidates(
                as_of=utc_now(),
                retention_days=PHYSICAL_RETENTION_DAYS,
            )
        )
        protected = tuple(
            candidate for candidate in candidates if candidate.protections
        )
        deletable = tuple(
            candidate for candidate in candidates if not candidate.protections
        )
        protection_counts = dict(
            sorted(
                Counter(
                    reason
                    for candidate in protected
                    for reason in candidate.protections
                ).items()
            )
        )

        deleted = RetentionDeleteCounts(0, 0, 0)
        if apply and deletable:
            deleted = self.repository.delete_candidates(list(deletable))

        return JobRetentionSummary(
            apply=apply,
            candidates=candidates,
            deletable=deletable,
            protected=protected,
            protection_counts=protection_counts,
            deleted=deleted,
        )
