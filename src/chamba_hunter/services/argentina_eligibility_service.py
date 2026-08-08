from collections import Counter
from dataclasses import dataclass, field
import re
import unicodedata

from chamba_hunter.domain.common import utc_now
from chamba_hunter.domain.enums import RunStatus
from chamba_hunter.domain.tracing import Run, RunStep
from chamba_hunter.repositories.job_eligibility_repository import (
    EligibilityCandidateRow,
    EligibilityClassificationWrite,
    JobEligibilityRepository,
)
from chamba_hunter.repositories.tracing_repository import (
    TracingRepository,
)


RULE_VERSION = "ARGENTINA_V1"


@dataclass(frozen=True, slots=True)
class EligibilityDecision:
    record_kind: str
    record_id: int
    source_type: str

    title: str
    location_text: str | None
    workplace_type: str | None

    status: str
    reason: str
    method: str


@dataclass(slots=True)
class ArgentinaEligibilitySummary:
    apply: bool

    total: int = 0

    eligible: int = 0
    ineligible: int = 0
    unknown: int = 0

    created: int = 0
    updated: int = 0
    deleted: int = 0

    run_id: int | None = None

    decisions: list[
        EligibilityDecision
    ] = field(default_factory=list)


class ArgentinaEligibilityService:
    def __init__(
        self,
        repository: JobEligibilityRepository,
        tracing_repository: TracingRepository,
    ) -> None:
        self.repository = repository
        self.tracing_repository = tracing_repository

    def run(
        self,
        apply: bool = False,
    ) -> ArgentinaEligibilitySummary:
        candidates = (
            self.repository.list_active_candidates()
        )

        summary = ArgentinaEligibilitySummary(
            apply=apply,
            total=len(candidates),
        )

        for candidate in candidates:
            decision = _classify(candidate)
            summary.decisions.append(decision)

        counts = Counter(
            decision.status
            for decision in summary.decisions
        )

        summary.eligible = counts["ELIGIBLE"]
        summary.ineligible = counts["INELIGIBLE"]
        summary.unknown = counts["UNKNOWN"]

        if apply:
            self._apply(summary)

        return summary

    def _apply(
        self,
        summary: ArgentinaEligibilitySummary,
    ) -> None:
        run = self.tracing_repository.add_run(
            Run(
                command=(
                    "classify_argentina_eligibility"
                )
            )
        )

        if run.id is None:
            raise RuntimeError(
                "Eligibility run must have an id."
            )

        summary.run_id = run.id

        step = self.tracing_repository.add_run_step(
            RunStep(
                run_id=run.id,
                step_name=(
                    "argentina_job_eligibility"
                ),
                items_total=summary.total,
            )
        )

        if step.id is None:
            raise RuntimeError(
                "Eligibility run step must have "
                "an id."
            )

        try:
            writes = [
                EligibilityClassificationWrite(
                    record_kind=decision.record_kind,
                    record_id=decision.record_id,
                    status=decision.status,
                    reason=decision.reason,
                    method=decision.method,
                    rule_version=RULE_VERSION,
                    evidence={
                        "source_type": (
                            decision.source_type
                        ),
                        "title": decision.title,
                        "location_text": (
                            decision.location_text
                        ),
                        "workplace_type": (
                            decision.workplace_type
                        ),
                    },
                )
                for decision in summary.decisions
            ]

            counts = (
                self.repository
                .upsert_classifications(
                    classifications=writes,
                    classified_at=utc_now(),
                )
            )

            summary.created = counts.created
            summary.updated = counts.updated
            summary.deleted = counts.deleted

            reason_counts = Counter(
                (
                    decision.status,
                    decision.reason,
                )
                for decision in summary.decisions
            )

            metadata = {
                "rule_version": RULE_VERSION,
                "eligible": summary.eligible,
                "ineligible": summary.ineligible,
                "unknown": summary.unknown,
                "created": summary.created,
                "updated": summary.updated,
                "deleted": summary.deleted,
                "reasons": {
                    f"{status}:{reason}": count
                    for (
                        status,
                        reason,
                    ), count in sorted(
                        reason_counts.items()
                    )
                },
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
                },
                error_message=str(error),
            )

            self.tracing_repository.finish_run(
                run_id=run.id,
                status=RunStatus.FAILED,
            )

            raise


def _classify(
    candidate: EligibilityCandidateRow,
) -> EligibilityDecision:
    location = _normalize_text(
        candidate.location_text
    )
    title = _normalize_text(
        candidate.title
    )

    workplace = (
        candidate.workplace_type
        or "UNKNOWN"
    )

    remoteish = (
        workplace == "REMOTE"
        or bool(
            _REMOTE_SIGNAL.search(location)
        )
    )

    location_scope = _location_scope(
        location
    )

    if location_scope == "ARGENTINA":
        return _decision(
            candidate,
            "ELIGIBLE",
            "ARGENTINA_LOCATION",
            "LOCATION",
        )

    if location_scope == "GLOBAL":
        return _decision(
            candidate,
            "ELIGIBLE",
            "REMOTE_GLOBAL",
            "LOCATION",
        )

    if location_scope == "LATAM":
        return _decision(
            candidate,
            "ELIGIBLE",
            "REMOTE_LATAM",
            "LOCATION",
        )

    if location_scope == "FOREIGN_REGION":
        return _decision(
            candidate,
            "INELIGIBLE",
            "FOREIGN_REGION_SCOPE",
            "LOCATION",
        )

    if location_scope == "FOREIGN":
        if remoteish:
            reason = (
                "REMOTE_FOREIGN_LOCATION"
            )
        elif (
            workplace in {
                "ONSITE",
                "HYBRID",
            }
            or _ONSITE_SIGNAL.search(
                location
            )
        ):
            reason = (
                "FOREIGN_ONSITE_HYBRID"
            )
        else:
            reason = "FOREIGN_LOCATION"

        return _decision(
            candidate,
            "INELIGIBLE",
            reason,
            "LOCATION",
        )

    title_scope = _strong_title_scope(
        title
    )

    if title_scope == "ARGENTINA":
        return _decision(
            candidate,
            "ELIGIBLE",
            "ARGENTINA_TITLE",
            "TITLE_FALLBACK",
        )

    if title_scope == "LATAM":
        return _decision(
            candidate,
            "ELIGIBLE",
            "REMOTE_LATAM_TITLE",
            "TITLE_FALLBACK",
        )

    if title_scope == "GLOBAL":
        return _decision(
            candidate,
            "ELIGIBLE",
            "REMOTE_GLOBAL_TITLE",
            "TITLE_FALLBACK",
        )

    if (
        workplace in {
            "ONSITE",
            "HYBRID",
        }
        or _ONSITE_SIGNAL.search(location)
    ):
        return _decision(
            candidate,
            "UNKNOWN",
            "LOCALITY_UNRECOGNIZED",
            "UNRESOLVED",
        )

    if remoteish:
        return _decision(
            candidate,
            "UNKNOWN",
            "REMOTE_SCOPE_UNKNOWN",
            "UNRESOLVED",
        )

    if not location:
        return _decision(
            candidate,
            "UNKNOWN",
            "NO_LOCATION",
            "UNRESOLVED",
        )

    return _decision(
        candidate,
        "UNKNOWN",
        "LOCATION_UNRECOGNIZED",
        "UNRESOLVED",
    )


def _decision(
    candidate: EligibilityCandidateRow,
    status: str,
    reason: str,
    method: str,
) -> EligibilityDecision:
    return EligibilityDecision(
        record_kind=candidate.record_kind,
        record_id=candidate.record_id,
        source_type=candidate.source_type,
        title=candidate.title,
        location_text=candidate.location_text,
        workplace_type=(
            candidate.workplace_type
        ),
        status=status,
        reason=reason,
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

    normalized = normalized.casefold()

    normalized = re.sub(
        r"[-_/]+",
        " ",
        normalized,
    )

    normalized = re.sub(
        r"\s+",
        " ",
        normalized,
    )

    return normalized.strip()


def _location_scope(
    value: str,
) -> str | None:
    if not value:
        return None

    if _ARGENTINA.search(value):
        return "ARGENTINA"

    if _GLOBAL.search(value):
        return "GLOBAL"

    if _LATAM.search(value):
        return "LATAM"

    if _EXCLUDED_REGION.search(value):
        return "FOREIGN_REGION"

    if (
        _FOREIGN.search(value)
        or _US_STATE_SUFFIX.search(value)
    ):
        return "FOREIGN"

    return None


def _strong_title_scope(
    value: str,
) -> str | None:
    if not value:
        return None

    if _ARGENTINA.search(value):
        return "ARGENTINA"

    if _LATAM_TITLE.search(value):
        return "LATAM"

    if (
        _REMOTE_SIGNAL.search(value)
        and _GLOBAL.search(value)
    ):
        return "GLOBAL"

    return None


_ARGENTINA = re.compile(
    r"\b("
    r"argentina|"
    r"buenos aires|caba|"
    r"cordoba|rosario|mendoza|"
    r"la plata|salta|tucuman|"
    r"santa fe|mar del plata"
    r")\b"
)

_LATAM = re.compile(
    r"\b("
    r"latam|latin america|"
    r"latin america only|"
    r"latinoamerica|"
    r"south america|"
    r"americas|amer"
    r")\b"
)

_LATAM_TITLE = re.compile(
    r"\b("
    r"latam|latin america|"
    r"latinoamerica|"
    r"south america"
    r")\b"
)

_GLOBAL = re.compile(
    r"\b("
    r"worldwide|global|anywhere|"
    r"work from anywhere"
    r")\b"
)

_REMOTE_SIGNAL = re.compile(
    r"\b("
    r"remote|remoto|"
    r"home based|home based|"
    r"homeworking|"
    r"work from home"
    r")\b"
)

_ONSITE_SIGNAL = re.compile(
    r"\b("
    r"office based|"
    r"onsite|on site|hybrid"
    r")\b"
)

_EXCLUDED_REGION = re.compile(
    r"\b("
    r"emea|apac|mena|"
    r"north america|noram|central america|"
    r"europe|european|"
    r"western europe|westerneurope|"
    r"eastern europe|"
    r"iberia|dach|uki|"
    r"asia|middle east|africa|"
    r"anz|nordics"
    r")\b"
)

_FOREIGN = re.compile(
    r"\b("
    # Americas
    r"united states|usa|u\.s\.|us|"
    r"canada|mexico|cdmx|"
    r"brazil|brasil|sao paulo|"
    r"chile|santiago|"
    r"colombia|bogota|"
    r"peru|ecuador|nuevo leon|"
    r"uruguay|montevideo|"
    r"paraguay|bolivia|venezuela|"
    r"dominican republic|"
    r"costa rica|panama|guatemala|"
    r"el salvador|honduras|nicaragua|"
    r"belize|guyana|suriname|"

    # Europe
    r"united kingdom|uk|england|"
    r"ireland|"
    r"spain|madrid|barcelona|"
    r"germany|france|italy|"
    r"portugal|poland|ukraine|"
    r"hungary|serbia|"
    r"armenia|georgia|cyprus|"
    r"finland|denmark|austria|"
    r"netherlands|bulgaria|"
    r"turkey|turkiye|istanbul|"
    r"romania|bucharest|"
    r"czech|prague|"

    # Asia / Middle East
    r"india|mumbai|gurgaon|"
    r"pakistan|islamabad|lahore|"
    r"philippines|phillipines|singapore|"
    r"china|taiwan|japan|"
    r"indonesia|vietnam|hanoi|"
    r"ho chi minh city|cambodia|"
    r"malaysia|macao|"
    r"uae|united arab emirates|"
    r"ksa|saudi arabia|"
    r"qatar|israel|"

    # Oceania / Africa
    r"australia|new zealand|"
    r"south africa|cape town|cameroon|yaounde|"
    r"nigeria|lagos|"
    r"morocco|egypt|senegal|dakar|"

    # Recurrent US localities
    r"san francisco|new york|"
    r"chicago|pittsburgh|"
    r"fremont|salem|"
    r"hawaii|texas|dallas|"
    r"florida|california|"
    r"washington\s*,?\s*dc|"
    r"san diego|san jose|"
    r"seattle|tacoma|bellevue|"
    r"spokane|los angeles|"
    r"palo alto|boston|"
    r"nashville|watertown|"
    r"sacramento|anaheim|"
    r"monterey|oakland|"
    r"boulder|mclean|"

    # Other recurrent cities
    r"london|toronto|"
    r"bangalore|bengaluru|"
    r"hyderabad|pune|delhi|"
    r"helsinki|hong kong|"
    r"shanghai|shenzhen|"
    r"kuala lumpur|riyadh"
    r")\b"
)

_US_STATE_SUFFIX = re.compile(
    r",\s*("
    r"ca|tx|wa|ma|co|tn|va|"
    r"ny|nj|or|pa|fl|il"
    r")\b"
)
