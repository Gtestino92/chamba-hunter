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
from chamba_hunter.repositories.job_occupation_repository import (
    JobOccupationRepository,
    OccupationCandidateRow,
    OccupationClassificationWrite,
)
from chamba_hunter.repositories.tracing_repository import (
    TracingRepository,
)


RULE_VERSION = "OCCUPATION_V1"


@dataclass(frozen=True, slots=True)
class OccupationDecision:
    record_kind: str
    record_id: int
    source_type: str
    origin: str
    company_name: str
    eligibility_status: str

    title: str

    occupation_class: str
    backend_relevance: str

    reason: str
    method: str
    evidence: JsonObject


@dataclass(slots=True)
class OccupationClassificationSummary:
    apply: bool

    total: int = 0

    software_engineering: int = 0
    it_technical: int = 0
    tech_adjacent: int = 0
    non_technical: int = 0
    unknown: int = 0

    created: int = 0
    updated: int = 0
    deleted: int = 0

    run_id: int | None = None

    decisions: list[
        OccupationDecision
    ] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _TitleResult:
    occupation_class: str | None
    backend_relevance: str | None
    reason: str | None
    matches: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _DescriptionResult:
    occupation_class: str | None
    matches: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _BackendResult:
    backend_relevance: str
    matches: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Signal:
    label: str
    pattern: re.Pattern[str]


class JobOccupationClassificationService:
    def __init__(
        self,
        repository: JobOccupationRepository,
        tracing_repository: TracingRepository,
    ) -> None:
        self.repository = repository
        self.tracing_repository = tracing_repository

    def run(
        self,
        apply: bool = False,
    ) -> OccupationClassificationSummary:
        candidates = (
            self.repository.list_scoped_candidates()
        )

        summary = OccupationClassificationSummary(
            apply=apply,
            total=len(candidates),
        )

        for candidate in candidates:
            summary.decisions.append(
                _classify(candidate)
            )

        counts = Counter(
            decision.occupation_class
            for decision in summary.decisions
        )

        summary.software_engineering = counts[
            "SOFTWARE_ENGINEERING"
        ]
        summary.it_technical = counts[
            "IT_TECHNICAL"
        ]
        summary.tech_adjacent = counts[
            "TECH_ADJACENT"
        ]
        summary.non_technical = counts[
            "NON_TECHNICAL"
        ]
        summary.unknown = counts[
            "UNKNOWN"
        ]

        if apply:
            self._apply(summary)

        return summary

    def _apply(
        self,
        summary: OccupationClassificationSummary,
    ) -> None:
        run = self.tracing_repository.add_run(
            Run(
                command=(
                    "classify_job_occupations"
                )
            )
        )

        if run.id is None:
            raise RuntimeError(
                "Occupation classification run "
                "must have an id."
            )

        summary.run_id = run.id

        step = self.tracing_repository.add_run_step(
            RunStep(
                run_id=run.id,
                step_name=(
                    "job_occupation_classification"
                ),
                items_total=summary.total,
            )
        )

        if step.id is None:
            raise RuntimeError(
                "Occupation classification run step "
                "must have an id."
            )

        try:
            writes = [
                OccupationClassificationWrite(
                    record_kind=decision.record_kind,
                    record_id=decision.record_id,
                    occupation_class=(
                        decision.occupation_class
                    ),
                    backend_relevance=(
                        decision.backend_relevance
                    ),
                    reason=decision.reason,
                    method=decision.method,
                    rule_version=RULE_VERSION,
                    evidence=decision.evidence,
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

            occupation_counts = Counter(
                decision.occupation_class
                for decision in summary.decisions
            )

            backend_counts = Counter(
                decision.backend_relevance
                for decision in summary.decisions
            )

            reason_counts = Counter(
                (
                    decision.occupation_class,
                    decision.reason,
                )
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
                "occupation_classes": dict(
                    sorted(
                        occupation_counts.items()
                    )
                ),
                "backend_relevance": dict(
                    sorted(
                        backend_counts.items()
                    )
                ),
                "methods": dict(
                    sorted(
                        method_counts.items()
                    )
                ),
                "reasons": {
                    f"{occupation}:{reason}": count
                    for (
                        occupation,
                        reason,
                    ), count in sorted(
                        reason_counts.items()
                    )
                },
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
    candidate: OccupationCandidateRow,
) -> OccupationDecision:
    title = _normalize_text(candidate.title)
    description = _normalize_text(
        candidate.description
    )

    title_result = _classify_title(title)

    description_result = _DescriptionResult(
        occupation_class=None,
        matches=(),
    )

    if (
        title_result.occupation_class is None
        and _title_allows_description_fallback(
            title
        )
    ):
        description_result = (
            _classify_description(description)
        )

    occupation_class = (
        title_result.occupation_class
        or description_result.occupation_class
        or "UNKNOWN"
    )

    title_backend = (
        title_result.backend_relevance
        if occupation_class
        == "SOFTWARE_ENGINEERING"
        else None
    )

    backend_result = _BackendResult(
        backend_relevance=(
            title_backend
            or (
                _classify_backend_description(
                    description
                ).backend_relevance
                if occupation_class
                == "SOFTWARE_ENGINEERING"
                else "NOT_APPLICABLE"
            )
        ),
        matches=(),
    )

    if (
        occupation_class == "SOFTWARE_ENGINEERING"
        and title_backend is None
    ):
        backend_result = (
            _classify_backend_description(
                description
            )
        )

    if occupation_class != "SOFTWARE_ENGINEERING":
        backend_result = _BackendResult(
            backend_relevance="NOT_APPLICABLE",
            matches=(),
        )

    if title_result.occupation_class is not None:
        if (
            occupation_class == "SOFTWARE_ENGINEERING"
            and title_result.backend_relevance is None
            and backend_result.backend_relevance
            != "UNKNOWN"
        ):
            method = "TITLE_DESCRIPTION"
        else:
            method = "TITLE"

        reason = (
            title_result.reason
            or "TITLE_CLASSIFIED"
        )
    elif description_result.occupation_class is not None:
        method = "DESCRIPTION"
        reason = (
            "DESCRIPTION_"
            + description_result.occupation_class
        )
    else:
        method = "UNRESOLVED"
        reason = "UNRESOLVED_OCCUPATION"

    evidence: JsonObject = {
        "source_type": candidate.source_type,
        "origin": candidate.origin,
        "company_name": candidate.company_name,
        "eligibility_status": (
            candidate.eligibility_status
        ),
        "title": candidate.title,
        "title_matches": list(
            title_result.matches
        ),
        "description_matches": list(
            description_result.matches
        ),
        "backend_matches": list(
            backend_result.matches
        ),
    }

    return OccupationDecision(
        record_kind=candidate.record_kind,
        record_id=candidate.record_id,
        source_type=candidate.source_type,
        origin=candidate.origin,
        company_name=candidate.company_name,
        eligibility_status=(
            candidate.eligibility_status
        ),
        title=candidate.title,
        occupation_class=occupation_class,
        backend_relevance=(
            backend_result.backend_relevance
        ),
        reason=reason,
        method=method,
        evidence=evidence,
    )


def _classify_title(
    title: str,
) -> _TitleResult:
    if not title:
        return _TitleResult(
            occupation_class=None,
            backend_relevance=None,
            reason=None,
            matches=(),
        )

    backend_matches = _matches(
        title,
        _TITLE_BACKEND,
    )

    if backend_matches:
        return _TitleResult(
            occupation_class="SOFTWARE_ENGINEERING",
            backend_relevance="BACKEND",
            reason="TITLE_BACKEND",
            matches=backend_matches,
        )

    full_stack_matches = _matches(
        title,
        _TITLE_FULL_STACK,
    )

    if full_stack_matches:
        return _TitleResult(
            occupation_class="SOFTWARE_ENGINEERING",
            backend_relevance="FULL_STACK",
            reason="TITLE_FULL_STACK",
            matches=full_stack_matches,
        )

    non_backend_matches = _matches(
        title,
        _TITLE_NON_BACKEND_SOFTWARE,
    )

    if non_backend_matches:
        return _TitleResult(
            occupation_class="SOFTWARE_ENGINEERING",
            backend_relevance="NON_BACKEND",
            reason="TITLE_NON_BACKEND_SOFTWARE",
            matches=non_backend_matches,
        )

    software_matches = _matches(
        title,
        _TITLE_SOFTWARE,
    )

    if software_matches:
        return _TitleResult(
            occupation_class="SOFTWARE_ENGINEERING",
            backend_relevance=None,
            reason="TITLE_SOFTWARE",
            matches=software_matches,
        )

    it_matches = _matches(
        title,
        _TITLE_IT_TECHNICAL,
    )

    if it_matches:
        return _TitleResult(
            occupation_class="IT_TECHNICAL",
            backend_relevance="NOT_APPLICABLE",
            reason="TITLE_IT_TECHNICAL",
            matches=it_matches,
        )

    adjacent_matches = _matches(
        title,
        _TITLE_TECH_ADJACENT,
    )

    if adjacent_matches:
        return _TitleResult(
            occupation_class="TECH_ADJACENT",
            backend_relevance="NOT_APPLICABLE",
            reason="TITLE_TECH_ADJACENT",
            matches=adjacent_matches,
        )

    non_technical_matches = _matches(
        title,
        _TITLE_NON_TECHNICAL,
    )

    if non_technical_matches:
        return _TitleResult(
            occupation_class="NON_TECHNICAL",
            backend_relevance="NOT_APPLICABLE",
            reason="TITLE_NON_TECHNICAL",
            matches=non_technical_matches,
        )

    return _TitleResult(
        occupation_class=None,
        backend_relevance=None,
        reason=None,
        matches=(),
    )


def _title_allows_description_fallback(
    title: str,
) -> bool:
    if not title:
        return False

    return bool(
        _DESCRIPTION_FALLBACK_TITLE.search(
            title
        )
    )


def _classify_description(
    description: str,
) -> _DescriptionResult:
    if not description:
        return _DescriptionResult(
            occupation_class=None,
            matches=(),
        )

    grouped_matches = {
        "SOFTWARE_ENGINEERING": _matches(
            description,
            _DESCRIPTION_SOFTWARE,
        ),
        "IT_TECHNICAL": _matches(
            description,
            _DESCRIPTION_IT_TECHNICAL,
        ),
        "TECH_ADJACENT": _matches(
            description,
            _DESCRIPTION_TECH_ADJACENT,
        ),
        "NON_TECHNICAL": _matches(
            description,
            _DESCRIPTION_NON_TECHNICAL,
        ),
    }

    scores = {
        occupation_class: len(matches)
        for occupation_class, matches
        in grouped_matches.items()
    }

    ordered = sorted(
        scores.items(),
        key=lambda item: (
            -item[1],
            item[0],
        ),
    )

    if not ordered or ordered[0][1] < 2:
        return _DescriptionResult(
            occupation_class=None,
            matches=(),
        )

    best_class, best_score = ordered[0]
    second_score = (
        ordered[1][1]
        if len(ordered) > 1
        else 0
    )

    if best_score <= second_score:
        return _DescriptionResult(
            occupation_class=None,
            matches=(),
        )

    return _DescriptionResult(
        occupation_class=best_class,
        matches=grouped_matches[
            best_class
        ],
    )


def _classify_backend_description(
    description: str,
) -> _BackendResult:
    if not description:
        return _BackendResult(
            backend_relevance="UNKNOWN",
            matches=(),
        )

    full_stack = _matches(
        description,
        _DESCRIPTION_FULL_STACK,
    )

    if full_stack:
        return _BackendResult(
            backend_relevance="FULL_STACK",
            matches=full_stack,
        )

    backend_strong = _matches(
        description,
        _DESCRIPTION_BACKEND_STRONG,
    )

    frontend_strong = _matches(
        description,
        _DESCRIPTION_NON_BACKEND_STRONG,
    )

    if backend_strong and frontend_strong:
        return _BackendResult(
            backend_relevance="FULL_STACK",
            matches=(
                *backend_strong,
                *frontend_strong,
            ),
        )

    if backend_strong:
        return _BackendResult(
            backend_relevance="BACKEND",
            matches=backend_strong,
        )

    if frontend_strong:
        return _BackendResult(
            backend_relevance="NON_BACKEND",
            matches=frontend_strong,
        )

    backend_support = _matches(
        description,
        _DESCRIPTION_BACKEND_SUPPORT,
    )

    non_backend_support = _matches(
        description,
        _DESCRIPTION_NON_BACKEND_SUPPORT,
    )

    if (
        len(backend_support) >= 2
        and not non_backend_support
    ):
        return _BackendResult(
            backend_relevance="BACKEND",
            matches=backend_support,
        )

    if (
        len(non_backend_support) >= 2
        and not backend_support
    ):
        return _BackendResult(
            backend_relevance="NON_BACKEND",
            matches=non_backend_support,
        )

    return _BackendResult(
        backend_relevance="UNKNOWN",
        matches=(),
    )


def _matches(
    value: str,
    signals: tuple[_Signal, ...],
) -> tuple[str, ...]:
    return tuple(
        signal.label
        for signal in signals
        if signal.pattern.search(value)
    )


def _signal(
    label: str,
    pattern: str,
) -> _Signal:
    return _Signal(
        label=label,
        pattern=re.compile(pattern),
    )


def _normalize_text(
    value: str | None,
) -> str:
    if not value:
        return ""

    normalized = html.unescape(value)

    normalized = re.sub(
        r"<[^>]+>",
        " ",
        normalized,
    )

    normalized = unicodedata.normalize(
        "NFKD",
        normalized,
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
        r"[^\w\s.+#]",
        " ",
        normalized,
    )

    normalized = re.sub(
        r"\s+",
        " ",
        normalized,
    )

    return normalized.strip()


_TITLE_NON_TECHNICAL = (
    _signal(
        "business_development",
        r"\bbusiness development\b",
    ),
    _signal(
        "sales_role",
        r"\b("
        r"sales representative|sales executive|"
        r"sales manager|sales director|"
        r"manager .*sales|director .*sales|"
        r"solution sales|software sales|"
        r"supervisor de ventas|ejecutivo comercial"
        r")\b",
    ),
    _signal(
        "account_executive",
        r"\baccount executive\b",
    ),
    _signal(
        "relationship_manager",
        r"\brelationship manager\b",
    ),
    _signal(
        "marketing_role",
        r"\b("
        r"product marketing|marketing manager|"
        r"marketing director|marketing intern|"
        r"marketing specialist|marketing associate"
        r")\b",
    ),
    _signal(
        "recruiting_hr",
        r"\b("
        r"recruiter|talent acquisition|"
        r"human resources|hr generalist|"
        r"people operations|people analytics|"
        r"director of people"
        r")\b",
    ),
    _signal(
        "finance_accounting",
        r"\b("
        r"financial analyst|finance analyst|"
        r"treasury analyst|analista contable|"
        r"administrativo contable|facturacion|"
        r"cuenta corriente|control de gestion"
        r")\b",
    ),
    _signal(
        "legal_compliance",
        r"\b("
        r"legal counsel|legal manager|"
        r"compliance talent pool|"
        r"regulatory counsel"
        r")\b",
    ),
    _signal(
        "customer_success",
        r"\bcustomer success.*"
        r"(manager|specialist|associate|director)\b",
    ),
    _signal(
        "procurement",
        r"\bprocurement (analyst|manager|specialist)\b",
    ),
    _signal(
        "general_operations",
        r"\b("
        r"operations specialist|"
        r"business services team manager|"
        r"asistente de trafico|"
        r"jefe de administracion"
        r")\b",
    ),
    _signal(
        "revenue_leadership",
        r"\b("
        r"chief revenue officer|revenue officer|"
        r"head of revenue|revenue director"
        r")\b",
    ),
    _signal(
        "sales_development",
        r"\b("
        r"sales development representative|"
        r"business development representative|"
        r"\bbdr\b|\bsdr\b|"
        r"sales development manager|"
        r"sales development director"
        r")\b",
    ),
    _signal(
        "alliances_channels",
        r"\b("
        r"alliances? (manager|director|leader)|"
        r"channels? (manager|director|leader)|"
        r"alliances .*channels .*leader|"
        r"alliance .*director|"
        r"alliances .*director|"
        r"head .*alliances|"
        r"alliance ecosystem|"
        r"alliances ecosystem|"
        r"enterprise sales .*alliances|"
        r"sales .*alliances"
        r")\b",
    ),
    _signal(
        "broad_marketing",
        r"\bmarketing .*"
        r"(lead|manager|director|specialist|associate)\b",
    ),
    _signal(
        "broad_hr",
        r"\b("
        r"hr manager|hr director|"
        r"human resources manager|"
        r"human resources director"
        r")\b",
    ),
    _signal(
        "sales_operations",
        r"\bsales operations (analyst|manager|lead)\b",
    ),
    _signal(
        "accountant",
        r"\b(accountant|contador|contadora)\b",
    ),
    _signal(
        "occupational_safety",
        r"\bseguridad y salud ocupacional\b",
    ),
    _signal(
        "clinical_role",
        r"\b(therapist|clinical supervisor)\b",
    ),
    _signal(
        "renewals",
        r"\brenewals? manager\b",
    ),
    _signal(
        "lifecycle_people_ops",
        r"\blifecycle specialist\b",
    ),
    _signal(
        "payroll",
        r"\bpayroll (specialist|manager|lead)\b",
    ),
    _signal(
        "commercial_legal",
        r"\b(managing )?counsel\b",
    ),
    _signal(
        "talent_pool_non_tech",
        r"\b(finance|legal|operations) talent pool\b",
    ),
    _signal(
        "account_management",
        r"\b(account manager|senior account manager)\b",
    ),
    _signal(
        "risk_compliance_operations",
        r"\b("
        r"fraud prevention analyst|"
        r"transaction monitoring (lead|manager|analyst)|"
        r"business continuity associate"
        r")\b",
    ),
    _signal(
        "brand_social_media",
        r"\b("
        r"social media .*strategist|"
        r"brand strategist"
        r")\b",
    ),
    _signal(
        "investor_relations",
        r"\binvestor relations\b",
    ),
    _signal(
        "technical_recruiting",
        r"\btechnical (sourcer|recruiter)\b",
    ),
    _signal(
        "internal_controls",
        r"\binternal controls manager\b",
    ),
    _signal(
        "audit_financial_services",
        r"\b("
        r"internal auditor|fund accounting|"
        r"fund services associate|gp services associate|"
        r"benefits analyst"
        r")\b",
    ),
    _signal(
        "customer_experience",
        r"\b("
        r"customer experience (manager|specialist)|"
        r"client experience specialist|"
        r"patient experience specialist"
        r")\b",
    ),
    _signal(
        "revenue_operations",
        r"\b("
        r"revops|revenue operations|"
        r"sales enablement (manager|lead|specialist)"
        r")\b",
    ),
    _signal(
        "events_coordination",
        r"\bevents? coordinator\b",
    ),
    _signal(
        "organizational_development",
        r"\b(organisational|organizational) development\b",
    ),
    _signal(
        "mobility_people",
        r"\bmobility specialist\b",
    ),
    _signal(
        "edd_compliance",
        r"\bedd analyst\b",
    ),
    _signal(
        "recruiting_management",
        r"\brecruiting manager\b",
    ),
    _signal(
        "creative_design",
        r"\bgraphic designer\b",
    ),
    _signal(
        "manufacturing_production",
        r"\b("
        r"decoration operator|embroidery machine operator|"
        r"embroidery production lead|"
        r"production art .*digitizing lead|"
        r"production associate .*decoration|"
        r"quality control specialist .*embroidery"
        r")\b",
    ),
    _signal(
        "customer_success_prefix",
        r"\b(director|manager|head|lead).*customer success\b",
    ),
)


_TITLE_BACKEND = (
    _signal(
        "backend",
        r"\b(back ?end|backend)\b",
    ),
    _signal(
        "microservices_engineer",
        r"\bmicroservices engineer\b",
    ),
    _signal(
        "elixir_phoenix_engineer",
        r"("
        r"\bsoftware engineer\b.*\b(elixir|phoenix)\b|"
        r"\b(elixir|phoenix)\b.*\bsoftware engineer\b"
        r")",
    ),
)


_TITLE_FULL_STACK = (
    _signal(
        "full_stack",
        r"\bfull ?stack\b",
    ),
    _signal(
        "backend_frontend_framework_pair",
        r"("
        r"\b(flask|django|fastapi)\b.*\breact\b|"
        r"\breact\b.*\b(flask|django|fastapi)\b"
        r")",
    ),
)


_TITLE_NON_BACKEND_SOFTWARE = (
    _signal(
        "frontend",
        r"\b(front ?end|frontend)\b",
    ),
    _signal(
        "react_engineer",
        r"\breact engineer\b",
    ),
    _signal(
        "mobile",
        r"\b("
        r"mobile (software )?engineer|"
        r"mobile developer|android developer|"
        r"ios developer|react native developer"
        r")\b",
    ),
    _signal(
        "system_device_software",
        r"\b("
        r"linux kernel engineer|"
        r"ubuntu software engineer|"
        r"linux devices? software engineer|"
        r"embedded linux .*software engineer|"
        r"system software engineer|"
        r"open source networking software engineer|"
        r"distributed systems testing software engineer"
        r")\b",
    ),
)


_TITLE_SOFTWARE = (
    _signal(
        "software_engineering",
        r"\b("
        r"software engineer|software developer|"
        r"software architect|"
        r"software engineering manager|"
        r"software engineering director"
        r")\b",
    ),
    _signal(
        "developer",
        r"\b("
        r"developers?|desarrollador(?:a|es|as)?"
        r")\b",
    ),
    _signal(
        "language_engineer",
        r"\b("
        r"golang|go|python|rust|elixir"
        r") (software )?engineer\b",
    ),
    _signal(
        "distributed_systems",
        r"\bdistributed systems (software )?engineer\b",
    ),
    _signal(
        "system_software",
        r"\bsystem software engineer\b",
    ),
    _signal(
        "linux_kernel",
        r"\blinux kernel engineer\b",
    ),
    _signal(
        "embedded_software",
        r"\bembedded .*software engineer\b",
    ),
    _signal(
        "search_engineer",
        r"\bsearch engineer\b",
    ),
    _signal(
        "application_architect",
        r"\b("
        r"application architect|"
        r"arquitecto sr de aplicaciones|"
        r"arquitecto de aplicaciones"
        r")\b",
    ),
    _signal(
        "software_maintenance",
        r"\bsoftware maintenance engineer\b",
    ),
    _signal(
        "linux_platform_integration",
        r"\blinux platform integration\b",
    ),
    _signal(
        "technology_engineer",
        r"("
        r"\b(engineer|engineering)\b.*\b("
        r"java|kotlin|spring boot|spring|"
        r"\.net|dotnet|c#|csharp|"
        r"node\.?js|nestjs|ruby|php|scala"
        r")\b|"
        r"\b("
        r"java|kotlin|spring boot|spring|"
        r"\.net|dotnet|c#|csharp|"
        r"node\.?js|nestjs|ruby|php|scala"
        r")\b.*\b(engineer|engineering)\b"
        r")",
    ),
    _signal(
        "payments_engineering",
        r"("
        r"\bpayments? engineer\b|"
        r"\bengineer\b.*\bpayments?\b"
        r")",
    ),
)


_TITLE_IT_TECHNICAL = (
    _signal(
        "data_engineering",
        r"\b("
        r"data engineer|ingeniero de datos|"
        r"data architect|data scientist|"
        r"data analyst|analista de datos|"
        r"business intelligence analyst|bi analyst"
        r")\b",
    ),
    _signal(
        "ai_ml_engineering",
        r"\b("
        r"ai engineer|ml engineer|"
        r"machine learning engineer|"
        r"mlops .*engineer"
        r")\b",
    ),
    _signal(
        "sre_platform",
        r"\b("
        r"site reliability|sre|"
        r"platform engineer|platform engineering|"
        r"database reliability engineer"
        r")\b",
    ),
    _signal(
        "devops_infrastructure",
        r"\b("
        r"devops engineer|infrastructure engineer|"
        r"cloud engineer|cloud architect|"
        r"public cloud solution architect|"
        r"observability engineer"
        r")\b",
    ),
    _signal(
        "security_engineering",
        r"\b("
        r"security engineer|security operations engineer|"
        r"application security engineer|"
        r"cybersecurity engineer"
        r")\b",
    ),
    _signal(
        "quality_assurance",
        r"\b("
        r"quality assurance|qa automation|"
        r"qa manual|analista qa|tester"
        r")\b",
    ),
    _signal(
        "database_administration",
        r"\b("
        r"database administrator|oracle dba|sql dba|"
        r"\bdba\b"
        r")",
    ),
    _signal(
        "noc_datacenter",
        r"\b("
        r"operador de noc|noc operator|"
        r"operador data center|data center operator"
        r")\b",
    ),
    _signal(
        "it_operations",
        r"\bit operations analyst\b",
    ),
    _signal(
        "technical_support",
        r"\b("
        r"linux support engineer|cloud support engineer|"
        r"software support engineer|"
        r"application support engineer|"
        r"platform support engineer"
        r")\b",
    ),
    _signal(
        "systems_network",
        r"\b("
        r"systems engineer|network engineer|"
        r"network security engineer"
        r")\b",
    ),
    _signal(
        "cloud_field_engineering",
        r"\b("
        r"cloud field engineer|linux field engineer|"
        r"embedded linux field engineer"
        r")\b",
    ),
    _signal(
        "technical_engineering_management",
        r"\b("
        r"cloud field engineering manager|"
        r"(cloud|data|ai|ml|platform|infrastructure) "
        r"engineering manager|"
        r"engineering manager .*"
        r"(apparmor|mlops|data|public cloud|cloud|"
        r"security|iam|identity and access|linux|"
        r"ceph|storage|observability|platform|"
        r"infrastructure)|"
        r"observability engineering manager|"
        r"head of platform engineering|"
        r"devices? .*field engineering manager"
        r")\b",
    ),
    _signal(
        "security_operations",
        r"\b("
        r"head of security operations|"
        r"threat intelligence (lead|manager|analyst)|"
        r"security risk management specialist"
        r")\b",
    ),
    _signal(
        "engineering_productivity",
        r"\b("
        r"development lifecycle|"
        r"sustaining operations engineer"
        r")\b",
    ),
    _signal(
        "container_virtualization",
        r"\bcontainerization .*virtuali[sz]ation engineer\b",
    ),
    _signal(
        "support_engineering_management",
        r"\bsupport engineering manager\b",
    ),
    _signal(
        "service_desk",
        r"\bservice desk\b",
    ),
    _signal(
        "ai_engineering_management",
        r"\b("
        r"engineering manager .*ai engineering|"
        r"ai engineering manager|"
        r"director .*ai engineering|"
        r"senior director .*ai|"
        r"senior manager .*ai innovation"
        r")\b",
    ),
    _signal(
        "information_security_leadership",
        r"\b("
        r"chief information security officer|"
        r"\bciso\b"
        r")",
    ),
    _signal(
        "spanish_platform_engineering",
        r"\bingenier[oa] de plataforma\b",
    ),
    _signal(
        "systems_administration",
        r"\b("
        r"systems? administrator|"
        r"administrador de sistemas|"
        r"revenue systems administrator"
        r")\b",
    ),
    _signal(
        "data_governance_quality",
        r"\b("
        r"data governance analyst|"
        r"data quality engineer|"
        r"data analysts? qa|"
        r"data analytics intern"
        r")\b",
    ),
    _signal(
        "ai_engineering_lead",
        r"\b(ai engineering lead|lead ai engineer)\b",
    ),
    _signal(
        "customer_data_integration",
        r"\bintegration engineer .*"
        r"(customer data platform|cdp)\b",
    ),
    _signal(
        "it_intern",
        r"\b(pasante it|it intern)\b",
    ),
    _signal(
        "ai_cloud_architecture",
        r"\b("
        r"arquitect[oa].*(ai|ia|gcp|cloud)|"
        r"(ai|ia|gcp|cloud).*arquitect[oa]"
        r")\b",
    ),
)


_TITLE_TECH_ADJACENT = (
    _signal(
        "functional_analysis",
        r"\b("
        r"analista funcional|functional analyst"
        r")\b",
    ),
    _signal(
        "technical_product",
        r"\btechnical product manager\b",
    ),
    _signal(
        "technical_project",
        r"\b("
        r"technical project manager|"
        r"project manager .*cloud|"
        r"project manager .*embedded systems|"
        r"public cloud project manager"
        r")\b",
    ),
    _signal(
        "solutions_architecture",
        r"\bsolutions? architect\b",
    ),
    _signal(
        "technical_consulting",
        r"\b("
        r"technical consultant|"
        r"implementation consultant|"
        r"implementation engineer|"
        r"solutions engineer|sales engineer"
        r")\b",
    ),
    _signal(
        "workflow_architecture",
        r"\bworkflow architect\b",
    ),
    _signal(
        "technical_alliances",
        r"\b("
        r"technical alliance|isv technical alliance"
        r")\b",
    ),
    _signal(
        "technical_services_management",
        r"\b("
        r"cloud professional services manager|"
        r"iot solutions architecture manager|"
        r"solutions architecture manager|"
        r"engineering manager .*solutions engineering"
        r")\b",
    ),
    _signal(
        "community_engineering",
        r"\bcommunity engineer\b",
    ),
    _signal(
        "it_audit",
        r"\bit .*audit\b",
    ),
    _signal(
        "technical_author",
        r"\btechnical author\b",
    ),
    _signal(
        "professional_services",
        r"\b("
        r"professional services project manager|"
        r"svp .*professional services|"
        r"professional services (manager|director|lead)"
        r")\b",
    ),
    _signal(
        "technical_account_management",
        r"\btechnical account manager\b",
    ),
    _signal(
        "solution_architecture_management",
        r"\bsolutions? architecture manager\b",
    ),
    _signal(
        "technical_program_management",
        r"\btechnical program manager\b",
    ),
    _signal(
        "solutions_consulting",
        r"\bsolutions? consultant\b",
    ),
    _signal(
        "product_management_consulting",
        r"\bproduct management consultant\b",
    ),
    _signal(
        "technical_management",
        r"\btechnical manager\b",
    ),
    _signal(
        "product_design",
        r"\b(product designer|figma designer)\b",
    ),
    _signal(
        "sap_technical_lead",
        r"\b(lider tecnico sap|technical lead .*sap)\b",
    ),
    _signal(
        "it_auditor_spanish",
        r"\b(auditor(?: a)? it|auditoria it)\b",
    ),
    _signal(
        "scrum_master",
        r"\bscrum master\b",
    ),
    _signal(
        "data_project_management",
        r"\bproject manager .*data (strategy|platform|analytics)\b",
    ),
    _signal(
        "product_operations",
        r"\bproduct operations\b",
    ),
)


_DESCRIPTION_FALLBACK_TITLE = re.compile(
    r"\b("
    r"engineer|engineering|ingeniero|ingeniera|"
    r"architect|arquitecto|arquitecta|"
    r"analyst|analista|"
    r"technical|tecnico|tecnica|"
    r"technology|tecnologia|"
    r"systems|sistemas|"
    r"security|seguridad|"
    r"cloud|linux|platform|data|"
    r"consultant|consultor|consultora|"
    r"implementation|support|soporte|"
    r"operations engineer"
    r")\b"
)


_DESCRIPTION_SOFTWARE = (
    _signal(
        "software_development",
        r"\bsoftware development\b",
    ),
    _signal(
        "write_code",
        r"\b(write|writing|writes) code\b",
    ),
    _signal(
        "design_software",
        r"\bdesign(ing)? .*software\b",
    ),
    _signal(
        "develop_applications",
        r"\bdevelop(ing)? .*applications?\b",
    ),
    _signal(
        "software_engineering_team",
        r"\bsoftware engineering (team|teams|organization)\b",
    ),
    _signal(
        "programming_language",
        r"\b(code|coding|programming) in "
        r"(python|go|golang|java|kotlin|rust|c\+\+|c#)\b",
    ),
)


_DESCRIPTION_IT_TECHNICAL = (
    _signal(
        "cloud_infrastructure",
        r"\bcloud infrastructure\b",
    ),
    _signal(
        "site_reliability",
        r"\bsite reliability\b",
    ),
    _signal(
        "kubernetes_operations",
        r"\b(kubernetes|openshift)\b",
    ),
    _signal(
        "linux_operations",
        r"\blinux .*operations\b",
    ),
    _signal(
        "data_pipelines",
        r"\bdata pipelines?\b",
    ),
    _signal(
        "machine_learning",
        r"\bmachine learning\b",
    ),
    _signal(
        "security_engineering",
        r"\bsecurity engineering\b",
    ),
    _signal(
        "database_administration",
        r"\bdatabase administration\b",
    ),
    _signal(
        "network_operations",
        r"\bnetwork operations\b",
    ),
    _signal(
        "technical_support",
        r"\btechnical support\b",
    ),
    _signal(
        "incident_management",
        r"\bincident management\b",
    ),
)


_DESCRIPTION_TECH_ADJACENT = (
    _signal(
        "product_roadmap",
        r"\bproduct roadmap\b",
    ),
    _signal(
        "technical_requirements",
        r"\btechnical requirements\b",
    ),
    _signal(
        "project_delivery",
        r"\bproject delivery\b",
    ),
    _signal(
        "technical_point_of_contact",
        r"\btechnical point of contact\b",
    ),
    _signal(
        "product_demos",
        r"\bproduct demos?\b",
    ),
    _signal(
        "proof_of_concept",
        r"\bproof of concept\b",
    ),
    _signal(
        "sales_cycle",
        r"\bsales cycles?\b",
    ),
    _signal(
        "functional_requirements",
        r"\bfunctional requirements\b",
    ),
)


_DESCRIPTION_NON_TECHNICAL = (
    _signal(
        "sales_pipeline",
        r"\bsales pipeline\b",
    ),
    _signal(
        "business_development",
        r"\bbusiness development\b",
    ),
    _signal(
        "recruiting",
        r"\b(recruiting|talent acquisition)\b",
    ),
    _signal(
        "marketing_campaigns",
        r"\bmarketing campaigns?\b",
    ),
    _signal(
        "financial_planning",
        r"\b(financial planning|forecasting|budgeting)\b",
    ),
    _signal(
        "accounting",
        r"\b(accounting|bookkeeping)\b",
    ),
    _signal(
        "legal_compliance",
        r"\b(legal advice|regulatory compliance)\b",
    ),
    _signal(
        "customer_success",
        r"\bcustomer success.*"
        r"(manager|specialist|associate|director)\b",
    ),
)


_DESCRIPTION_FULL_STACK = (
    _signal(
        "full_stack",
        r"\bfull ?stack\b",
    ),
)


_DESCRIPTION_BACKEND_STRONG = (
    _signal(
        "backend",
        r"\b(back ?end|backend)\b",
    ),
    _signal(
        "server_side",
        r"\bserver side\b",
    ),
)


_DESCRIPTION_NON_BACKEND_STRONG = (
    _signal(
        "react_native",
        r"\breact native\b",
    ),
    _signal(
        "android",
        r"\bandroid\b",
    ),
    _signal(
        "ios",
        r"\bios\b",
    ),
    _signal(
        "frontend",
        r"\b(front ?end|frontend)\b",
    ),
)


_DESCRIPTION_BACKEND_SUPPORT = (
    _signal(
        "microservices",
        r"\bmicroservices?\b",
    ),
    _signal(
        "rest_api",
        r"\brest(ful)? apis?\b",
    ),
    _signal(
        "api_development",
        r"\bapi development\b",
    ),
    _signal(
        "distributed_systems",
        r"\bdistributed systems?\b",
    ),
    _signal(
        "event_driven",
        r"\bevent driven\b",
    ),
    _signal(
        "service_architecture",
        r"\bservices? architecture\b",
    ),
)


_DESCRIPTION_NON_BACKEND_SUPPORT = (
    _signal(
        "ui_components",
        r"\bui components?\b",
    ),
    _signal(
        "react_components",
        r"\breact components?\b",
    ),
    _signal(
        "mobile_applications",
        r"\bmobile applications?\b",
    ),
    _signal(
        "web_ui",
        r"\bweb ui\b",
    ),
)
