from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

from chamba_hunter.domain.common import (
    JsonObject,
    utc_now,
)
from chamba_hunter.domain.enums import RunStatus
from chamba_hunter.domain.tracing import (
    Run,
    RunStep,
)
from chamba_hunter.repositories.job_freshness_repository import (
    FreshnessBaselineCounts,
    JobFreshnessRepository,
)
from chamba_hunter.repositories.job_operational_priority_repository import (
    JobOperationalPriorityRepository,
    OperationalCandidateRow,
    OperationalPriorityWrite,
)
from chamba_hunter.repositories.tracing_repository import (
    TracingRepository,
)


RULE_VERSION = "OPERATIONAL_PRIORITY_V1"
PROFILE_NAME = "BACKEND_SOFTWARE_V1"


ACTIVE_STATES = {
    "NEW",
    "UPDATED",
    "KNOWN",
}


MATCH_LEVEL_RANK = {
    "VERY_HIGH": 4,
    "HIGH": 3,
    "MEDIUM": 2,
    "LOW": 1,
}


STATE_RANK = {
    "NEW": 3,
    "UPDATED": 2,
    "KNOWN": 1,
    "INACTIVE": 0,
    "SUPERSEDED": 0,
    "OUT_OF_SCOPE": 0,
}


CHANNEL_RANK = {
    "DIRECT_APPLY_URL": 4,
    "JOB_URL": 3,
    "GENERAL_APPLICATION_URL": 2,
    "PUBLIC_CONTACT": 1,
    "NONE": 0,
}


@dataclass(frozen=True, slots=True)
class OperationalDecision:
    record_kind: str
    record_id: int

    company_id: int
    company_name: str

    source_type: str
    origin: str
    title: str

    operational_state: str

    professional_score: float
    professional_match_level: str
    professional_rule_version: str
    professional_matched_at: datetime | None

    application_channel: str
    application_target: str | None

    job_url: str | None
    apply_url: str | None
    general_application_url: str | None

    first_seen_at: datetime
    last_seen_at: datetime
    published_at: datetime | None
    last_changed_at: datetime | None

    reasons: JsonObject

    @property
    def actionable(
        self,
    ) -> bool:
        return (
            self.operational_state
            in ACTIVE_STATES
        )


@dataclass(slots=True)
class OperationalPrioritySummary:
    apply: bool

    total: int = 0

    created: int = 0
    updated: int = 0

    run_id: int | None = None
    search_profile_id: int | None = None

    previous_watermark: datetime | None = None

    freshness_baseline: (
        FreshnessBaselineCounts
        | None
    ) = None

    decisions: list[
        OperationalDecision
    ] = field(default_factory=list)


def _application_channel(
    candidate: OperationalCandidateRow,
) -> tuple[
    str,
    str | None,
]:
    if candidate.apply_url:
        return (
            "DIRECT_APPLY_URL",
            candidate.apply_url,
        )

    if candidate.job_url:
        return (
            "JOB_URL",
            candidate.job_url,
        )

    if candidate.general_application_url:
        return (
            "GENERAL_APPLICATION_URL",
            candidate.general_application_url,
        )

    if candidate.public_contact:
        return (
            "PUBLIC_CONTACT",
            candidate.public_contact,
        )

    return (
        "NONE",
        None,
    )


def _is_expired(
    candidate: OperationalCandidateRow,
    now: datetime,
) -> bool:
    return (
        candidate.expires_at
        is not None
        and candidate.expires_at
        <= now
    )


def _operational_state(
    *,
    candidate: OperationalCandidateRow,
    previous_watermark: datetime | None,
    now: datetime,
) -> tuple[
    str,
    list[str],
]:
    if not candidate.current_professional_match:
        if (
            not candidate.source_present
            or not candidate.source_is_active
            or _is_expired(
                candidate,
                now,
            )
        ):
            return (
                "INACTIVE",
                [
                    "NO_CURRENT_PROFESSIONAL_MATCH",
                    "SOURCE_INACTIVE_OR_MISSING",
                ],
            )

        if (
            candidate.record_kind
            == "LEAD"
            and candidate.canonical_job_active
        ):
            return (
                "SUPERSEDED",
                [
                    "NO_CURRENT_PROFESSIONAL_MATCH",
                    "CANONICAL_ATS_JOB_ACTIVE",
                ],
            )

        return (
            "OUT_OF_SCOPE",
            [
                "NO_CURRENT_PROFESSIONAL_MATCH",
                "SOURCE_STILL_ACTIVE",
            ],
        )

    if _is_expired(
        candidate,
        now,
    ):
        return (
            "INACTIVE",
            [
                "EXPIRES_AT_REACHED",
            ],
        )

    if (
        candidate.previous_operational_state
        in {
            "INACTIVE",
            "SUPERSEDED",
            "OUT_OF_SCOPE",
        }
    ):
        return (
            "UPDATED",
            [
                "REENTERED_CURRENT_SCOPE",
            ],
        )

    if previous_watermark is None:
        return (
            "KNOWN",
            [
                "INITIAL_BASELINE",
            ],
        )

    if (
        candidate.first_seen_at
        > previous_watermark
    ):
        return (
            "NEW",
            [
                "FIRST_SEEN_AFTER_WATERMARK",
            ],
        )

    if (
        candidate.last_changed_at
        is not None
        and candidate.last_changed_at
        > previous_watermark
    ):
        return (
            "UPDATED",
            [
                "CONTENT_CHANGED_AFTER_WATERMARK",
            ],
        )

    return (
        "KNOWN",
        [
            "SEEN_BEFORE_WATERMARK",
            "NO_RECORDED_CHANGE_AFTER_WATERMARK",
        ],
    )


def operational_sort_key(
    decision: OperationalDecision,
) -> tuple:
    return (
        -int(
            decision.actionable
        ),
        -MATCH_LEVEL_RANK.get(
            decision.professional_match_level,
            0,
        ),
        -STATE_RANK.get(
            decision.operational_state,
            0,
        ),
        -decision.professional_score,
        -CHANNEL_RANK.get(
            decision.application_channel,
            0,
        ),
        -decision.first_seen_at.timestamp(),
        decision.company_name.lower(),
        decision.title.lower(),
        decision.record_kind,
        decision.record_id,
    )


class JobOperationalPriorityService:
    def __init__(
        self,
        *,
        repository: (
            JobOperationalPriorityRepository
        ),
        freshness_repository: (
            JobFreshnessRepository
        ),
        tracing_repository: (
            TracingRepository
        ),
    ) -> None:
        self.repository = repository
        self.freshness_repository = (
            freshness_repository
        )
        self.tracing_repository = (
            tracing_repository
        )

    def run(
        self,
        *,
        apply: bool = False,
    ) -> OperationalPrioritySummary:
        freshness_baseline = None

        if apply:
            freshness_baseline = (
                self.freshness_repository
                .initialize_missing_baseline()
            )

        search_profile_id = (
            self.repository
            .get_search_profile_id(
                PROFILE_NAME
            )
        )

        previous_watermark = (
            self.repository
            .previous_successful_watermark()
        )

        candidates = (
            self.repository
            .list_candidates(
                search_profile_id
            )
        )

        now = utc_now()

        decisions = [
            self._evaluate(
                candidate=candidate,
                previous_watermark=(
                    previous_watermark
                ),
                now=now,
            )
            for candidate in candidates
        ]

        summary = OperationalPrioritySummary(
            apply=apply,
            total=len(decisions),
            search_profile_id=(
                search_profile_id
            ),
            previous_watermark=(
                previous_watermark
            ),
            freshness_baseline=(
                freshness_baseline
            ),
            decisions=decisions,
        )

        if apply:
            self._apply(
                summary=summary,
                evaluated_at=now,
            )

        return summary

    def _evaluate(
        self,
        *,
        candidate: OperationalCandidateRow,
        previous_watermark: datetime | None,
        now: datetime,
    ) -> OperationalDecision:
        (
            operational_state,
            state_reasons,
        ) = _operational_state(
            candidate=candidate,
            previous_watermark=(
                previous_watermark
            ),
            now=now,
        )

        (
            application_channel,
            application_target,
        ) = _application_channel(
            candidate
        )

        reasons: JsonObject = {
            "rule_version": RULE_VERSION,
            "search_profile": PROFILE_NAME,
            "operational_state": (
                operational_state
            ),
            "state_reasons": (
                state_reasons
            ),
            "previous_watermark": (
                previous_watermark
                .isoformat()
                if previous_watermark
                is not None
                else None
            ),
            "source": {
                "present": (
                    candidate.source_present
                ),
                "active": (
                    candidate.source_is_active
                ),
                "canonical_job_active": (
                    candidate
                    .canonical_job_active
                ),
                "expires_at": (
                    candidate.expires_at
                    .isoformat()
                    if candidate.expires_at
                    is not None
                    else None
                ),
            },
            "freshness": {
                "first_seen_at": (
                    candidate.first_seen_at
                    .isoformat()
                ),
                "last_seen_at": (
                    candidate.last_seen_at
                    .isoformat()
                ),
                "last_changed_at": (
                    candidate.last_changed_at
                    .isoformat()
                    if candidate.last_changed_at
                    is not None
                    else None
                ),
                "published_at": (
                    candidate.published_at
                    .isoformat()
                    if candidate.published_at
                    is not None
                    else None
                ),
            },
            "professional_match": {
                "current": (
                    candidate
                    .current_professional_match
                ),
                "score": (
                    candidate
                    .professional_score
                ),
                "match_level": (
                    candidate
                    .professional_match_level
                ),
                "rule_version": (
                    candidate
                    .professional_rule_version
                ),
                "matched_at": (
                    candidate
                    .professional_matched_at
                    .isoformat()
                    if candidate
                    .professional_matched_at
                    is not None
                    else None
                ),
            },
            "application": {
                "channel": (
                    application_channel
                ),
                "target": (
                    application_target
                ),
            },
        }

        return OperationalDecision(
            record_kind=(
                candidate.record_kind
            ),
            record_id=(
                candidate.record_id
            ),
            company_id=(
                candidate.company_id
            ),
            company_name=(
                candidate.company_name
            ),
            source_type=(
                candidate.source_type
            ),
            origin=candidate.origin,
            title=candidate.title,
            operational_state=(
                operational_state
            ),
            professional_score=(
                candidate
                .professional_score
            ),
            professional_match_level=(
                candidate
                .professional_match_level
            ),
            professional_rule_version=(
                candidate
                .professional_rule_version
            ),
            professional_matched_at=(
                candidate
                .professional_matched_at
            ),
            application_channel=(
                application_channel
            ),
            application_target=(
                application_target
            ),
            job_url=candidate.job_url,
            apply_url=candidate.apply_url,
            general_application_url=(
                candidate
                .general_application_url
            ),
            first_seen_at=(
                candidate.first_seen_at
            ),
            last_seen_at=(
                candidate.last_seen_at
            ),
            published_at=(
                candidate.published_at
            ),
            last_changed_at=(
                candidate.last_changed_at
            ),
            reasons=reasons,
        )

    def _apply(
        self,
        *,
        summary: OperationalPrioritySummary,
        evaluated_at: datetime,
    ) -> None:
        if summary.search_profile_id is None:
            raise RuntimeError(
                "Operational priority requires "
                "a search profile id."
            )

        run = self.tracing_repository.add_run(
            Run(
                command="prioritize_jobs"
            )
        )

        if run.id is None:
            raise RuntimeError(
                "Operational priority run "
                "must have an id."
            )

        summary.run_id = run.id

        step = self.tracing_repository.add_run_step(
            RunStep(
                run_id=run.id,
                step_name=(
                    "operational_priority"
                ),
                items_total=summary.total,
            )
        )

        if step.id is None:
            raise RuntimeError(
                "Operational priority run step "
                "must have an id."
            )

        try:
            writes = [
                OperationalPriorityWrite(
                    record_kind=decision.record_kind,
                    record_id=decision.record_id,
                    company_id=decision.company_id,
                    company_name=decision.company_name,
                    source_type=decision.source_type,
                    origin=decision.origin,
                    title=decision.title,
                    operational_state=(
                        decision.operational_state
                    ),
                    professional_score=(
                        decision.professional_score
                    ),
                    professional_match_level=(
                        decision
                        .professional_match_level
                    ),
                    professional_rule_version=(
                        decision
                        .professional_rule_version
                    ),
                    professional_matched_at=(
                        decision
                        .professional_matched_at
                    ),
                    application_channel=(
                        decision.application_channel
                    ),
                    application_target=(
                        decision.application_target
                    ),
                    job_url=decision.job_url,
                    apply_url=decision.apply_url,
                    general_application_url=(
                        decision
                        .general_application_url
                    ),
                    first_seen_at=(
                        decision.first_seen_at
                    ),
                    last_seen_at=(
                        decision.last_seen_at
                    ),
                    published_at=(
                        decision.published_at
                    ),
                    last_changed_at=(
                        decision.last_changed_at
                    ),
                    reasons=decision.reasons,
                    rule_version=RULE_VERSION,
                )
                for decision
                in summary.decisions
            ]

            counts = (
                self.repository
                .upsert_priorities(
                    search_profile_id=(
                        summary.search_profile_id
                    ),
                    writes=writes,
                    evaluated_at=evaluated_at,
                    evaluated_run_id=run.id,
                )
            )

            summary.created = counts.created
            summary.updated = counts.updated

            state_counts = Counter(
                decision.operational_state
                for decision
                in summary.decisions
            )

            level_counts = Counter(
                decision.professional_match_level
                for decision
                in summary.decisions
            )

            channel_counts = Counter(
                decision.application_channel
                for decision
                in summary.decisions
            )

            baseline = (
                summary.freshness_baseline
            )

            metadata = {
                "rule_version": RULE_VERSION,
                "search_profile": PROFILE_NAME,
                "search_profile_id": (
                    summary.search_profile_id
                ),
                "previous_watermark": (
                    summary.previous_watermark
                    .isoformat()
                    if summary.previous_watermark
                    is not None
                    else None
                ),
                "states": dict(
                    sorted(
                        state_counts.items()
                    )
                ),
                "match_levels": dict(
                    sorted(
                        level_counts.items()
                    )
                ),
                "channels": dict(
                    sorted(
                        channel_counts.items()
                    )
                ),
                "freshness_baseline": {
                    "jobs_initialized": (
                        baseline.jobs_initialized
                        if baseline is not None
                        else 0
                    ),
                    "leads_initialized": (
                        baseline.leads_initialized
                        if baseline is not None
                        else 0
                    ),
                },
                "created": summary.created,
                "updated": summary.updated,
            }

            self.tracing_repository.finish_run_step(
                run_step_id=step.id,
                status=RunStatus.SUCCESS,
                items_success=summary.total,
                items_failed=0,
                items_skipped=0,
                metadata=metadata,
            )

            self.tracing_repository.finish_run(
                run_id=run.id,
                status=RunStatus.SUCCESS,
            )

        except Exception as error:
            self.tracing_repository.finish_run_step(
                run_step_id=step.id,
                status=RunStatus.FAILED,
                items_success=0,
                items_failed=1,
                items_skipped=summary.total,
                metadata={
                    "rule_version": RULE_VERSION,
                    "search_profile": PROFILE_NAME,
                },
                error_message=str(error),
            )

            self.tracing_repository.finish_run(
                run_id=run.id,
                status=RunStatus.FAILED,
            )

            raise
