from collections import Counter
from dataclasses import dataclass, field
import html
import re
import unicodedata

from chamba_hunter.domain.common import (
    JsonObject,
    utc_now,
)
from chamba_hunter.domain.enums import RunStatus
from chamba_hunter.domain.tracing import Run, RunStep
from chamba_hunter.repositories.job_seniority_repository import (
    JobSeniorityRepository,
    SeniorityCandidateRow,
    SeniorityClassificationWrite,
)
from chamba_hunter.repositories.tracing_repository import (
    TracingRepository,
)


RULE_VERSION = "SENIORITY_V1"


@dataclass(frozen=True, slots=True)
class SeniorityDecision:
    record_kind: str
    record_id: int
    source_type: str
    origin: str
    company_name: str
    eligibility_status: str

    occupation_class: str | None
    backend_relevance: str | None

    title: str

    seniority_class: str
    leadership_class: str

    seniority_reason: str
    leadership_reason: str
    method: str

    evidence: JsonObject


@dataclass(slots=True)
class SeniorityClassificationSummary:
    apply: bool

    total: int = 0

    created: int = 0
    updated: int = 0
    deleted: int = 0

    run_id: int | None = None

    candidates: list[
        SeniorityCandidateRow
    ] = field(default_factory=list)

    decisions: list[
        SeniorityDecision
    ] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _Signal:
    label: str
    pattern: re.Pattern[str]


@dataclass(frozen=True, slots=True)
class _SeniorityResult:
    seniority_class: str | None
    reason: str
    matches: tuple[str, ...]
    classes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _LeadershipResult:
    leadership_class: str
    reason: str
    matches: tuple[str, ...]


class JobSeniorityClassificationService:
    def __init__(
        self,
        repository: JobSeniorityRepository,
        tracing_repository: TracingRepository,
    ) -> None:
        self.repository = repository
        self.tracing_repository = tracing_repository

    def run(
        self,
        apply: bool = False,
    ) -> SeniorityClassificationSummary:
        candidates = (
            self.repository.list_scoped_candidates()
        )

        summary = SeniorityClassificationSummary(
            apply=apply,
            total=len(candidates),
            candidates=candidates,
        )

        for candidate in candidates:
            summary.decisions.append(
                _classify(candidate)
            )

        if apply:
            self._apply(summary)

        return summary

    def _apply(
        self,
        summary: SeniorityClassificationSummary,
    ) -> None:
        run = self.tracing_repository.add_run(
            Run(
                command="classify_job_seniority"
            )
        )

        if run.id is None:
            raise RuntimeError(
                "Seniority classification run "
                "must have an id."
            )

        summary.run_id = run.id

        step = self.tracing_repository.add_run_step(
            RunStep(
                run_id=run.id,
                step_name="job_seniority_classification",
                items_total=summary.total,
            )
        )

        if step.id is None:
            raise RuntimeError(
                "Seniority classification run step "
                "must have an id."
            )

        try:
            writes = [
                SeniorityClassificationWrite(
                    record_kind=decision.record_kind,
                    record_id=decision.record_id,
                    seniority_class=(
                        decision.seniority_class
                    ),
                    leadership_class=(
                        decision.leadership_class
                    ),
                    seniority_reason=(
                        decision.seniority_reason
                    ),
                    leadership_reason=(
                        decision.leadership_reason
                    ),
                    method=decision.method,
                    rule_version=RULE_VERSION,
                    evidence=decision.evidence,
                )
                for decision in summary.decisions
            ]

            counts = (
                self.repository.upsert_classifications(
                    classifications=writes,
                    classified_at=utc_now(),
                )
            )

            summary.created = counts.created
            summary.updated = counts.updated
            summary.deleted = counts.deleted

            seniority_counts = Counter(
                decision.seniority_class
                for decision in summary.decisions
            )

            leadership_counts = Counter(
                decision.leadership_class
                for decision in summary.decisions
            )

            method_counts = Counter(
                decision.method
                for decision in summary.decisions
            )

            metadata = {
                "rule_version": RULE_VERSION,
                "scope": (
                    "ARGENTINA_ELIGIBLE_OR_UNKNOWN"
                ),
                "seniority_classes": dict(
                    sorted(
                        seniority_counts.items()
                    )
                ),
                "leadership_classes": dict(
                    sorted(
                        leadership_counts.items()
                    )
                ),
                "methods": dict(
                    sorted(
                        method_counts.items()
                    )
                ),
                "created": summary.created,
                "updated": summary.updated,
                "deleted": summary.deleted,
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
    candidate: SeniorityCandidateRow,
) -> SeniorityDecision:
    title = _normalize_text(
        candidate.title
    )
    description = _normalize_text(
        candidate.description
    )

    title_result = _classify_title_seniority(
        title=title,
        occupation_class=(
            candidate.occupation_class
        ),
    )

    leadership_result = _classify_leadership(
        title=title,
        occupation_class=(
            candidate.occupation_class
        ),
    )

    description_result = _SeniorityResult(
        seniority_class=None,
        reason="NO_DESCRIPTION_LEVEL_SIGNAL",
        matches=(),
        classes=(),
    )

    leadership_title_without_level = (
        title_result.seniority_class is None
        and title_result.reason != "TITLE_CONFLICT"
        and leadership_result.leadership_class
        != "NONE"
    )

    if (
        title_result.seniority_class is None
        and title_result.reason != "TITLE_CONFLICT"
        and not leadership_title_without_level
    ):
        description_result = (
            _classify_description_seniority(
                description=description,
                occupation_class=(
                    candidate.occupation_class
                ),
            )
        )

    if title_result.reason == "TITLE_CONFLICT":
        seniority_class = "UNKNOWN"
        seniority_reason = "TITLE_CONFLICT"
    elif title_result.seniority_class is not None:
        seniority_class = (
            title_result.seniority_class
        )
        seniority_reason = title_result.reason
    elif leadership_title_without_level:
        seniority_class = "UNKNOWN"
        seniority_reason = (
            "LEADERSHIP_TITLE_WITHOUT_LEVEL"
        )
    elif description_result.seniority_class is not None:
        seniority_class = (
            description_result.seniority_class
        )
        seniority_reason = (
            description_result.reason
        )
    else:
        seniority_class = "UNKNOWN"
        seniority_reason = "UNRESOLVED_SENIORITY"

    if (
        title_result.seniority_class is not None
        or title_result.reason == "TITLE_CONFLICT"
    ):
        method = "TITLE"
    elif description_result.seniority_class is not None:
        method = "DESCRIPTION"
    elif leadership_result.leadership_class != "NONE":
        method = "TITLE"
    else:
        method = "UNRESOLVED"

    experience_matches = (
        _extract_experience_signals(
            candidate.description
        )
    )

    evidence: JsonObject = {
        "source_type": candidate.source_type,
        "origin": candidate.origin,
        "company_name": candidate.company_name,
        "eligibility_status": (
            candidate.eligibility_status
        ),
        "occupation_class": (
            candidate.occupation_class
        ),
        "backend_relevance": (
            candidate.backend_relevance
        ),
        "title": candidate.title,
        "title_seniority_matches": list(
            title_result.matches
        ),
        "title_seniority_classes": list(
            title_result.classes
        ),
        "description_seniority_matches": list(
            description_result.matches
        ),
        "leadership_matches": list(
            leadership_result.matches
        ),
        "experience_years_matches": (
            experience_matches
        ),
    }

    return SeniorityDecision(
        record_kind=candidate.record_kind,
        record_id=candidate.record_id,
        source_type=candidate.source_type,
        origin=candidate.origin,
        company_name=candidate.company_name,
        eligibility_status=(
            candidate.eligibility_status
        ),
        occupation_class=(
            candidate.occupation_class
        ),
        backend_relevance=(
            candidate.backend_relevance
        ),
        title=candidate.title,
        seniority_class=seniority_class,
        leadership_class=(
            leadership_result.leadership_class
        ),
        seniority_reason=seniority_reason,
        leadership_reason=(
            leadership_result.reason
        ),
        method=method,
        evidence=evidence,
    )


def _classify_title_seniority(
    title: str,
    occupation_class: str | None,
) -> _SeniorityResult:
    if not title:
        return _SeniorityResult(
            seniority_class=None,
            reason="NO_TITLE_LEVEL_SIGNAL",
            matches=(),
            classes=(),
        )

    grouped: dict[str, tuple[str, ...]] = {}

    for seniority_class, signals in (
        _TITLE_SENIORITY_SIGNALS.items()
    ):
        if (
            seniority_class == "STAFF"
            and occupation_class
            not in {
                "SOFTWARE_ENGINEERING",
                "IT_TECHNICAL",
            }
        ):
            continue

        matches = _matches(
            title,
            signals,
        )

        if matches:
            grouped[seniority_class] = matches

    return _resolve_seniority_grouped(
        grouped=grouped,
        prefix="TITLE",
    )


def _classify_description_seniority(
    description: str,
    occupation_class: str | None,
) -> _SeniorityResult:
    if not description:
        return _SeniorityResult(
            seniority_class=None,
            reason="NO_DESCRIPTION_LEVEL_SIGNAL",
            matches=(),
            classes=(),
        )

    grouped: dict[str, tuple[str, ...]] = {}

    for seniority_class, signals in (
        _DESCRIPTION_SENIORITY_SIGNALS.items()
    ):
        if (
            seniority_class == "STAFF"
            and occupation_class
            not in {
                "SOFTWARE_ENGINEERING",
                "IT_TECHNICAL",
            }
        ):
            continue

        matches = _matches(
            description,
            signals,
        )

        if matches:
            grouped[seniority_class] = matches

    return _resolve_seniority_grouped(
        grouped=grouped,
        prefix="DESCRIPTION",
    )


def _resolve_seniority_grouped(
    grouped: dict[str, tuple[str, ...]],
    prefix: str,
) -> _SeniorityResult:
    classes = tuple(
        seniority_class
        for seniority_class
        in _SENIORITY_ORDER
        if seniority_class in grouped
    )

    matches = tuple(
        match
        for seniority_class in classes
        for match in grouped[seniority_class]
    )

    if not classes:
        return _SeniorityResult(
            seniority_class=None,
            reason=f"NO_{prefix}_LEVEL_SIGNAL",
            matches=(),
            classes=(),
        )

    if len(classes) == 1:
        seniority_class = classes[0]

        return _SeniorityResult(
            seniority_class=seniority_class,
            reason=(
                f"{prefix}_{seniority_class}"
            ),
            matches=matches,
            classes=classes,
        )

    class_set = set(classes)

    for advanced in (
        "STAFF",
        "PRINCIPAL",
        "LEAD",
    ):
        if class_set == {
            "SENIOR",
            advanced,
        }:
            return _SeniorityResult(
                seniority_class=advanced,
                reason=(
                    f"{prefix}_COMPOSITE_{advanced}"
                ),
                matches=matches,
                classes=classes,
            )

    return _SeniorityResult(
        seniority_class=None,
        reason=f"{prefix}_CONFLICT",
        matches=matches,
        classes=classes,
    )


def _classify_leadership(
    title: str,
    occupation_class: str | None,
) -> _LeadershipResult:
    if not title:
        return _LeadershipResult(
            leadership_class="NONE",
            reason="NO_LEADERSHIP_TITLE_SIGNAL",
            matches=(),
        )

    for leadership_class in (
        "C_LEVEL",
        "VP",
        "HEAD",
        "DIRECTOR",
    ):
        matches = _matches(
            title,
            _LEADERSHIP_SIGNALS[
                leadership_class
            ],
        )

        if matches:
            return _LeadershipResult(
                leadership_class=(
                    leadership_class
                ),
                reason=(
                    f"TITLE_{leadership_class}"
                ),
                matches=matches,
            )

    manager_matches = _matches(
        title,
        _LEADERSHIP_SIGNALS[
            "MANAGER"
        ],
    )

    if manager_matches:
        if (
            occupation_class
            in {
                "SOFTWARE_ENGINEERING",
                "IT_TECHNICAL",
            }
            or _EXPLICIT_PEOPLE_MANAGER.search(
                title
            )
        ):
            return _LeadershipResult(
                leadership_class="MANAGER",
                reason="TITLE_MANAGER",
                matches=manager_matches,
            )

        return _LeadershipResult(
            leadership_class="UNKNOWN",
            reason="AMBIGUOUS_MANAGER_TITLE",
            matches=manager_matches,
        )

    return _LeadershipResult(
        leadership_class="NONE",
        reason="NO_LEADERSHIP_TITLE_SIGNAL",
        matches=(),
    )


def _extract_experience_signals(
    raw_text: str | None,
) -> list[JsonObject]:
    cleaned = _clean_text(raw_text)

    if not cleaned:
        return []

    candidates: list[tuple[int, int, JsonObject]] = []

    for pattern in _EXPERIENCE_PATTERNS:
        for match in pattern.finditer(cleaned):
            minimum = int(
                match.group("min")
            )

            maximum_group = (
                match.groupdict().get("max")
            )

            maximum = (
                int(maximum_group)
                if maximum_group
                else None
            )

            if minimum <= 0 or minimum > 40:
                continue

            if (
                maximum is not None
                and (
                    maximum < minimum
                    or maximum > 40
                )
            ):
                continue

            span = match.span()
            context_start = max(
                0,
                span[0] - 110,
            )
            context_end = min(
                len(cleaned),
                span[1] + 110,
            )

            candidates.append(
                (
                    span[0],
                    span[1],
                    {
                        "min_years": minimum,
                        "max_years": maximum,
                        "text": match.group(0),
                        "context": cleaned[
                            context_start:context_end
                        ],
                    },
                )
            )

    candidates.sort(
        key=lambda item: (
            item[0],
            -(item[1] - item[0]),
        )
    )

    found: list[JsonObject] = []
    accepted_spans: list[tuple[int, int]] = []

    for start, end, evidence in candidates:
        overlaps = any(
            start < accepted_end
            and end > accepted_start
            for accepted_start, accepted_end
            in accepted_spans
        )

        if overlaps:
            continue

        accepted_spans.append(
            (start, end)
        )
        found.append(evidence)

        if len(found) >= 10:
            break

    return found


def _matches(
    text: str,
    signals: tuple[_Signal, ...],
) -> tuple[str, ...]:
    matches: list[str] = []

    for signal in signals:
        if signal.pattern.search(text):
            matches.append(signal.label)

    return tuple(matches)


def _normalize_text(
    raw_text: str | None,
) -> str:
    cleaned = _clean_text(raw_text)

    if not cleaned:
        return ""

    normalized = unicodedata.normalize(
        "NFKD",
        cleaned,
    )

    normalized = "".join(
        character
        for character in normalized
        if not unicodedata.combining(
            character
        )
    )

    return normalized.lower()


def _clean_text(
    raw_text: str | None,
) -> str:
    if not raw_text:
        return ""

    value = html.unescape(raw_text)
    value = re.sub(
        r"<[^>]+>",
        " ",
        value,
    )
    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def _compile(
    pattern: str,
) -> re.Pattern[str]:
    return re.compile(
        pattern,
        re.IGNORECASE,
    )


_SENIORITY_ORDER = (
    "INTERN",
    "ENTRY",
    "JUNIOR",
    "MID",
    "SENIOR",
    "STAFF",
    "PRINCIPAL",
    "LEAD",
)


_TITLE_SENIORITY_SIGNALS: dict[
    str,
    tuple[_Signal, ...],
] = {
    "INTERN": (
        _Signal(
            "intern",
            _compile(
                r"\bintern(?:ship)?\b"
            ),
        ),
        _Signal(
            "pasante",
            _compile(
                r"\bpasant(?:e|ia)\b"
            ),
        ),
        _Signal(
            "practicante",
            _compile(
                r"\bpracticante\b"
            ),
        ),
    ),
    "ENTRY": (
        _Signal(
            "entry-level",
            _compile(
                r"\bentry[- ]level\b"
            ),
        ),
        _Signal(
            "new-grad",
            _compile(
                r"\bnew[- ]grad(?:uate)?\b"
            ),
        ),
        _Signal(
            "graduate",
            _compile(
                r"\bgraduate\b"
            ),
        ),
        _Signal(
            "trainee",
            _compile(
                r"\btrainee\b"
            ),
        ),
        _Signal(
            "apprentice",
            _compile(
                r"\bapprentice(?:ship)?\b"
            ),
        ),
    ),
    "JUNIOR": (
        _Signal(
            "junior",
            _compile(
                r"\bjunior\b"
            ),
        ),
        _Signal(
            "jr",
            _compile(
                r"\bjr\.?\b"
            ),
        ),
    ),
    "MID": (
        _Signal(
            "mid-level",
            _compile(
                r"\bmid[- ]level\b"
            ),
        ),
        _Signal(
            "mid",
            _compile(
                r"\bmid\b(?![- ]market)"
            ),
        ),
        _Signal(
            "semi-senior",
            _compile(
                r"\bsemi[- ]?senior\b"
            ),
        ),
        _Signal(
            "semi-sr",
            _compile(
                r"\bsemi[- ]?sr\.?\b"
            ),
        ),
        _Signal(
            "ssr",
            _compile(
                r"\bssr\.?\b"
            ),
        ),
        _Signal(
            "intermediate",
            _compile(
                r"\bintermediate\b"
            ),
        ),
    ),
    "SENIOR": (
        _Signal(
            "senior",
            _compile(
                r"(?<!semi )(?<!semi-)\bsenior\b"
            ),
        ),
        _Signal(
            "sr",
            _compile(
                r"(?<!semi )(?<!semi-)\bsr\.?\b"
            ),
        ),
    ),
    "STAFF": (
        _Signal(
            "staff",
            _compile(
                r"\bstaff\b"
            ),
        ),
    ),
    "PRINCIPAL": (
        _Signal(
            "principal",
            _compile(
                r"\bprincipal\b"
            ),
        ),
    ),
    "LEAD": (
        _Signal(
            "lead",
            _compile(
                r"\blead\b(?!\s+generation)"
            ),
        ),
        _Signal(
            "team-leader",
            _compile(
                r"\bteam\s+leader\b"
            ),
        ),
    ),
}


_DESCRIPTION_PREFIX = (
    r"(?:"
    r"we(?:'re| are)?\s+(?:looking|searching)\s+for|"
    r"we\s+are\s+hiring|"
    r"seeking|"
    r"hiring|"
    r"this\s+(?:role|position)\s+is|"
    r"the\s+(?:role|position)\s+is|"
    r"buscamos|"
    r"estamos\s+buscando"
    r")"
    r".{0,80}?"
)


_DESCRIPTION_SENIORITY_SIGNALS: dict[
    str,
    tuple[_Signal, ...],
] = {
    "INTERN": (
        _Signal(
            "role-intern",
            _compile(
                _DESCRIPTION_PREFIX
                + r"\bintern\b"
            ),
        ),
        _Signal(
            "role-pasante",
            _compile(
                _DESCRIPTION_PREFIX
                + r"\bpasante\b"
            ),
        ),
    ),
    "ENTRY": (
        _Signal(
            "role-entry-level",
            _compile(
                _DESCRIPTION_PREFIX
                + r"\bentry[- ]level\b"
            ),
        ),
        _Signal(
            "role-graduate",
            _compile(
                _DESCRIPTION_PREFIX
                + r"\bgraduate\b"
            ),
        ),
        _Signal(
            "role-trainee",
            _compile(
                _DESCRIPTION_PREFIX
                + r"\btrainee\b"
            ),
        ),
    ),
    "JUNIOR": (
        _Signal(
            "role-junior",
            _compile(
                _DESCRIPTION_PREFIX
                + r"\b(?:junior|jr\.?)\b"
            ),
        ),
    ),
    "MID": (
        _Signal(
            "role-mid",
            _compile(
                _DESCRIPTION_PREFIX
                + r"\b(?:mid[- ]level|mid|"
                r"semi[- ]?senior|ssr\.?)\b"
            ),
        ),
    ),
    "SENIOR": (
        _Signal(
            "role-senior",
            _compile(
                _DESCRIPTION_PREFIX
                + r"(?<!semi )(?<!semi-)"
                r"\b(?:senior|sr\.?)\b"
            ),
        ),
    ),
    "STAFF": (
        _Signal(
            "role-staff",
            _compile(
                _DESCRIPTION_PREFIX
                + r"\bstaff\b"
            ),
        ),
    ),
    "PRINCIPAL": (
        _Signal(
            "role-principal",
            _compile(
                _DESCRIPTION_PREFIX
                + r"\bprincipal\b"
            ),
        ),
    ),
}


_LEADERSHIP_SIGNALS: dict[
    str,
    tuple[_Signal, ...],
] = {
    "C_LEVEL": (
        _Signal(
            "chief-officer",
            _compile(
                r"\bchief\b.{0,45}\bofficer\b"
            ),
        ),
        _Signal(
            "c-level-acronym",
            _compile(
                r"\b(?:ceo|cto|cio|ciso|cfo|coo|"
                r"cmo|cro|chro|cpo|clo)\b"
            ),
        ),
    ),
    "VP": (
        _Signal(
            "vice-president",
            _compile(
                r"\bvice\s+president\b"
            ),
        ),
        _Signal(
            "vp",
            _compile(
                r"\b(?:svp|evp|avp|vp)\b"
            ),
        ),
    ),
    "HEAD": (
        _Signal(
            "head",
            _compile(
                r"\bhead(?:\s+of)?\b"
            ),
        ),
    ),
    "DIRECTOR": (
        _Signal(
            "director",
            _compile(
                r"\bdirector\b"
            ),
        ),
    ),
    "MANAGER": (
        _Signal(
            "manager",
            _compile(
                r"\bmanager\b"
            ),
        ),
    ),
}


_EXPLICIT_PEOPLE_MANAGER = _compile(
    r"\b(?:"
    r"people\s+manager|"
    r"team\s+manager|"
    r"engineering\s+manager|"
    r"software\s+(?:engineering|development)\s+manager|"
    r"development\s+manager|"
    r"service\s+desk\s+manager|"
    r"security\s+(?:operations\s+)?manager|"
    r"data\s+engineering\s+manager|"
    r"platform\s+(?:engineering\s+)?manager|"
    r"infrastructure\s+manager|"
    r"it\s+manager"
    r")\b"
)


_EXPERIENCE_PATTERNS = (
    re.compile(
        r"\b(?P<min>\d{1,2})\s*"
        r"(?:[-–—]|to)\s*"
        r"(?P<max>\d{1,2})\s*"
        r"(?:\+\s*)?"
        r"(?:years?|yrs?)\b"
        r".{0,70}?\bexperience\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?P<min>\d{1,2})\s*"
        r"\+?\s*(?:years?|yrs?)\b"
        r".{0,70}?\bexperience\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:at\s+least|minimum(?:\s+of)?|min\.?)\s*"
        r"(?P<min>\d{1,2})\s*"
        r"(?:\+\s*)?(?:years?|yrs?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?P<min>\d{1,2})\s*"
        r"(?:[-–—]|a)\s*"
        r"(?P<max>\d{1,2})\s*"
        r"a[nñ]os?\b"
        r".{0,70}?\bexperiencia\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?P<min>\d{1,2})\s*"
        r"\+?\s*a[nñ]os?\b"
        r".{0,70}?\bexperiencia\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:al\s+menos|m[ií]nimo(?:\s+de)?)\s*"
        r"(?P<min>\d{1,2})\s*"
        r"a[nñ]os?\b",
        re.IGNORECASE,
    ),
)
