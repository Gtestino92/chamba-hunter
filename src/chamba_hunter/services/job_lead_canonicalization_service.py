from collections import Counter
from dataclasses import dataclass, field
import re
import unicodedata

from chamba_hunter.domain.common import (
    utc_now,
)
from chamba_hunter.domain.enums import (
    RunStatus,
)
from chamba_hunter.domain.tracing import (
    Run,
    RunStep,
)
from chamba_hunter.repositories.job_lead_canonicalization_repository import (
    CanonicalizationJobRow,
    CanonicalizationLeadRow,
    CanonicalizationWrite,
    JobLeadCanonicalizationRepository,
)
from chamba_hunter.repositories.tracing_repository import (
    TracingRepository,
)


@dataclass(frozen=True, slots=True)
class CanonicalizationDecision:
    lead_id: int
    job_id: int

    source_type: str
    company_name: str

    title: str

    lead_location: str | None
    job_location: str | None

    lead_workplace: str | None
    job_workplace: str | None

    provider: str
    method: str


@dataclass(frozen=True, slots=True)
class CanonicalizationAmbiguity:
    lead_id: int

    source_type: str
    company_name: str
    title: str
    location_text: str | None

    candidate_job_ids: tuple[int, ...]
    candidate_locations: tuple[
        str | None,
        ...,
    ]


@dataclass(slots=True)
class JobLeadCanonicalizationSummary:
    apply: bool

    total: int = 0
    resolved: int = 0
    ambiguous: int = 0
    unmatched: int = 0

    applied: int = 0
    run_id: int | None = None

    decisions: list[
        CanonicalizationDecision
    ] = field(default_factory=list)

    ambiguities: list[
        CanonicalizationAmbiguity
    ] = field(default_factory=list)


class JobLeadCanonicalizationService:
    def __init__(
        self,
        repository: (
            JobLeadCanonicalizationRepository
        ),
        tracing_repository: (
            TracingRepository
        ),
    ) -> None:
        self.repository = repository
        self.tracing_repository = (
            tracing_repository
        )

    def run(
        self,
        apply: bool = False,
    ) -> JobLeadCanonicalizationSummary:
        leads = (
            self.repository
            .list_active_unresolved()
        )
        jobs = (
            self.repository
            .list_active_jobs()
        )

        jobs_by_company: dict[
            int,
            list[CanonicalizationJobRow],
        ] = {}

        for job in jobs:
            jobs_by_company.setdefault(
                job.company_id,
                [],
            ).append(job)

        summary = (
            JobLeadCanonicalizationSummary(
                apply=apply,
                total=len(leads),
            )
        )

        for lead in leads:
            (
                decision,
                ambiguity,
            ) = self._resolve_lead(
                lead=lead,
                jobs=jobs_by_company.get(
                    lead.company_id,
                    [],
                ),
            )

            if decision is not None:
                summary.decisions.append(
                    decision
                )
                continue

            if ambiguity is not None:
                summary.ambiguities.append(
                    ambiguity
                )
                continue

            summary.unmatched += 1

        summary.resolved = len(
            summary.decisions
        )
        summary.ambiguous = len(
            summary.ambiguities
        )

        if not apply:
            return summary

        self._apply(summary)

        return summary

    def _apply(
        self,
        summary: JobLeadCanonicalizationSummary,
    ) -> None:
        run = (
            self.tracing_repository
            .add_run(
                Run(
                    command=(
                        "canonicalize_job_leads"
                    )
                )
            )
        )

        if run.id is None:
            raise RuntimeError(
                "Canonicalization run "
                "must have an id."
            )

        summary.run_id = run.id

        step = (
            self.tracing_repository
            .add_run_step(
                RunStep(
                    run_id=run.id,
                    step_name=(
                        "job_lead_canonicalization"
                    ),
                    items_total=summary.total,
                )
            )
        )

        if step.id is None:
            raise RuntimeError(
                "Canonicalization run step "
                "must have an id."
            )

        try:
            writes = [
                CanonicalizationWrite(
                    lead_id=decision.lead_id,
                    job_id=decision.job_id,
                    method=decision.method,
                )
                for decision
                in summary.decisions
            ]

            summary.applied = (
                self.repository.apply_links(
                    links=writes,
                    canonicalized_at=utc_now(),
                )
            )

            method_counts = Counter(
                decision.method
                for decision
                in summary.decisions
            )

            metadata = {
                "resolved": summary.resolved,
                "ambiguous": (
                    summary.ambiguous
                ),
                "unmatched": (
                    summary.unmatched
                ),
                "applied": summary.applied,
                "methods": dict(
                    sorted(
                        method_counts.items()
                    )
                ),
            }

            (
                self.tracing_repository
                .finish_run_step(
                    run_step_id=step.id,
                    status=RunStatus.SUCCESS,
                    items_success=(
                        summary.applied
                    ),
                    items_failed=0,
                    items_skipped=(
                        summary.total
                        - summary.applied
                    ),
                    metadata=metadata,
                )
            )

            (
                self.tracing_repository
                .finish_run(
                    run_id=run.id,
                    status=RunStatus.SUCCESS,
                )
            )

        except Exception as error:
            (
                self.tracing_repository
                .finish_run_step(
                    run_step_id=step.id,
                    status=RunStatus.FAILED,
                    items_success=0,
                    items_failed=1,
                    items_skipped=summary.total,
                    metadata={
                        "resolved": (
                            summary.resolved
                        ),
                        "ambiguous": (
                            summary.ambiguous
                        ),
                        "unmatched": (
                            summary.unmatched
                        ),
                    },
                    error_message=str(error),
                )
            )

            (
                self.tracing_repository
                .finish_run(
                    run_id=run.id,
                    status=RunStatus.FAILED,
                )
            )

            raise

    @staticmethod
    def _resolve_lead(
        lead: CanonicalizationLeadRow,
        jobs: list[CanonicalizationJobRow],
    ) -> tuple[
        CanonicalizationDecision | None,
        CanonicalizationAmbiguity | None,
    ]:
        title = _normalize_text(
            lead.title
        )

        candidates = [
            job
            for job in jobs
            if (
                _normalize_text(
                    job.title
                )
                == title
            )
        ]

        if len(candidates) == 1:
            return (
                _decision(
                    lead=lead,
                    job=candidates[0],
                    method="TITLE",
                ),
                None,
            )

        if not candidates:
            return (None, None)

        lead_location = _normalize_text(
            lead.location_text
        )

        location_matches: list[
            CanonicalizationJobRow
        ] = []

        if lead_location:
            location_matches = [
                job
                for job in candidates
                if (
                    lead_location
                    in _normalize_text(
                        job.location_text
                    )
                )
            ]

        if len(location_matches) == 1:
            return (
                _decision(
                    lead=lead,
                    job=location_matches[0],
                    method=(
                        "TITLE_LOCATION"
                    ),
                ),
                None,
            )

        if len(location_matches) > 1:
            lead_workplace = (
                lead.workplace_type
                or "UNKNOWN"
            )

            workplace_matches = [
                job
                for job in location_matches
                if (
                    (
                        job.workplace_type
                        or "UNKNOWN"
                    )
                    == lead_workplace
                )
            ]

            if (
                len(workplace_matches)
                == 1
            ):
                return (
                    _decision(
                        lead=lead,
                        job=(
                            workplace_matches[0]
                        ),
                        method=(
                            "TITLE_LOCATION_"
                            "WORKPLACE"
                        ),
                    ),
                    None,
                )

        return (
            None,
            CanonicalizationAmbiguity(
                lead_id=lead.id,
                source_type=(
                    lead.source_type
                ),
                company_name=(
                    lead.company_name
                ),
                title=lead.title,
                location_text=(
                    lead.location_text
                ),
                candidate_job_ids=tuple(
                    job.id
                    for job in candidates
                ),
                candidate_locations=tuple(
                    job.location_text
                    for job in candidates
                ),
            ),
        )


def _decision(
    lead: CanonicalizationLeadRow,
    job: CanonicalizationJobRow,
    method: str,
) -> CanonicalizationDecision:
    return CanonicalizationDecision(
        lead_id=lead.id,
        job_id=job.id,
        source_type=lead.source_type,
        company_name=lead.company_name,
        title=lead.title,
        lead_location=lead.location_text,
        job_location=job.location_text,
        lead_workplace=(
            lead.workplace_type
        ),
        job_workplace=(
            job.workplace_type
        ),
        provider=job.provider,
        method=method,
    )


def _normalize_text(
    value: str | None,
) -> str:
    if not value:
        return ""

    normalized = unicodedata.normalize(
        "NFKD",
        value,
    )

    normalized = "".join(
        character
        for character in normalized
        if not unicodedata.combining(
            character
        )
    )

    normalized = (
        normalized
        .casefold()
    )

    normalized = re.sub(
        r"[-_/]+",
        " ",
        normalized,
    )

    normalized = re.sub(
        r"[^\w\s]",
        " ",
        normalized,
    )

    return " ".join(
        normalized.split()
    )
