from dataclasses import dataclass

from chamba_hunter.domain.common import (
    utc_now,
)
from chamba_hunter.domain.enums import (
    CompanyType,
    TargetPriority,
)
from chamba_hunter.domain.models import (
    PublicContact,
)
from chamba_hunter.repositories.company_outreach_repository import (
    CompanyOutreachCandidate,
    CompanyOutreachRepository,
    OutreachPriorityWrite,
)
from chamba_hunter.services.public_contact_quality import (
    contact_quality_score,
)


RULE_VERSION = (
    "COMPANY_OUTREACH_V3_1"
)

DEFAULT_MIN_ACTIONABLE_SCORE = 45.0


@dataclass(frozen=True, slots=True)
class OutreachEvaluation:
    company_id: int
    company_name: str

    score: float
    level: str

    best_contact: (
        PublicContact
        | None
    )

    contact_score: float

    current_max_match: float | None
    historical_max_match: float | None

    contacted: bool

    reasons: tuple[
        str,
        ...
    ]


@dataclass(frozen=True, slots=True)
class OutreachPrioritySummary:
    search_profile_name: str
    evaluated: int

    actionable: int
    already_contacted: int

    very_high: int
    high: int
    medium: int
    low: int

    evaluations: tuple[
        OutreachEvaluation,
        ...
    ]


class CompanyOutreachPriorityService:
    def __init__(
        self,
        repository: (
            CompanyOutreachRepository
        ),
    ) -> None:
        self.repository = repository

    def run(
        self,
        *,
        search_profile_name: str,
        apply: bool,
    ) -> OutreachPrioritySummary:
        (
            profile_id,
            candidates,
        ) = (
            self.repository
            .list_priority_candidates(
                search_profile_name=(
                    search_profile_name
                )
            )
        )

        evaluations: list[
            OutreachEvaluation
        ] = []

        counts = {
            "VERY_HIGH": 0,
            "HIGH": 0,
            "MEDIUM": 0,
            "LOW": 0,
        }

        actionable = 0
        already_contacted = 0
        evaluated_at = utc_now()

        current_company_ids = {
            candidate.company_id
            for candidate in candidates
        }

        if apply:
            self.repository.delete_priorities_not_in_company_ids(
                search_profile_id=profile_id,
                company_ids=current_company_ids,
            )

        for candidate in candidates:
            evaluation = _evaluate(
                candidate
            )

            evaluations.append(
                evaluation
            )

            counts[
                evaluation.level
            ] += 1

            if evaluation.contacted:
                already_contacted += 1

            if (
                not evaluation.contacted
                and evaluation.best_contact
                is not None
                and evaluation.contact_score
                > 0
                and evaluation.score
                >= DEFAULT_MIN_ACTIONABLE_SCORE
            ):
                actionable += 1

            if apply:
                self.repository.upsert_priority(
                    OutreachPriorityWrite(
                        company_id=(
                            candidate.company_id
                        ),
                        search_profile_id=(
                            profile_id
                        ),
                        current_max_match=(
                            candidate
                            .current_max_match
                        ),
                        historical_max_match=(
                            _max_optional(
                                candidate
                                .historical_max_match,
                                candidate
                                .current_max_match,
                            )
                        ),
                        current_relevant_jobs=(
                            candidate
                            .current_relevant_jobs
                        ),
                        best_contact_id=(
                            evaluation.best_contact.id
                            if (
                                evaluation.best_contact
                                is not None
                            )
                            else None
                        ),
                        score=(
                            evaluation.score
                        ),
                        level=(
                            evaluation.level
                        ),
                        reasons=list(
                            evaluation.reasons
                        ),
                        rule_version=(
                            RULE_VERSION
                        ),
                        evaluated_at=(
                            evaluated_at
                        ),
                    )
                )

        evaluations.sort(
            key=lambda item: (
                item.contacted,
                -item.score,
                item.company_name.casefold(),
            )
        )

        return (
            OutreachPrioritySummary(
                search_profile_name=(
                    search_profile_name
                ),
                evaluated=len(
                    evaluations
                ),
                actionable=actionable,
                already_contacted=(
                    already_contacted
                ),
                very_high=counts[
                    "VERY_HIGH"
                ],
                high=counts[
                    "HIGH"
                ],
                medium=counts[
                    "MEDIUM"
                ],
                low=counts[
                    "LOW"
                ],
                evaluations=tuple(
                    evaluations
                ),
            )
        )


def _evaluate(
    candidate: CompanyOutreachCandidate,
) -> OutreachEvaluation:
    reasons: list[
        str
    ] = []

    historical_match = (
        _max_optional(
            candidate
            .historical_max_match,
            candidate
            .current_max_match,
        )
    )

    professional_score = 0.0

    if historical_match is not None:
        professional_score = min(
            35.0,
            historical_match * 0.35,
        )

        reasons.append(
            "historical professional "
            f"match {historical_match:.1f}"
        )

    (
        best_contact,
        contact_score,
    ) = _best_contact(
        candidate.contacts
    )

    if best_contact is not None:
        reasons.append(
            "public contact: "
            f"{best_contact.contact_type.value} "
            f"(quality {contact_score:.0f})"
        )

    activity_score = (
        _cessi_activity_score(
            candidate
            .cessi_activities
        )
    )

    if activity_score:
        reasons.append(
            "CESSI software-sector "
            "company"
        )

    manual_score = (
        15.0
        if candidate.manual_reference
        else 0.0
    )

    if manual_score:
        reasons.append(
            "manually referenced company"
        )

    yc_score = min(
        25.0,
        max(
            0.0,
            candidate.yc_relevance_score,
        ),
    )

    if yc_score:
        category_text = ", ".join(
            candidate.yc_categories[
                :3
            ]
        )

        reasons.append(
            "YC technology directory"
            + (
                f": {category_text}"
                if category_text
                else ""
            )
        )

    if (
        candidate.remote_argentina
        is True
    ):
        geo_score = 15.0
        reasons.append(
            "remote Argentina evidence"
        )

    elif (
        candidate.remote_latam
        is True
    ):
        geo_score = 12.0
        reasons.append(
            "remote LATAM evidence"
        )

    elif (
        candidate.cessi_activities
        or (
            candidate.country
            is not None
            and "argentin"
            in candidate
            .country.casefold()
        )
    ):
        geo_score = 10.0
        reasons.append(
            "Argentina company/evidence"
        )

    else:
        geo_score = 0.0

    targeting_score = {
        TargetPriority.VERY_HIGH: 7.0,
        TargetPriority.HIGH: 6.0,
        TargetPriority.MEDIUM: 3.0,
        TargetPriority.LOW: 0.0,
        TargetPriority.UNKNOWN: 0.0,
    }[
        candidate.target_priority
    ]

    if targeting_score:
        reasons.append(
            "company target priority "
            f"{candidate.target_priority.value}"
        )

    type_score = {
        CompanyType.PRODUCT: 3.0,
        CompanyType.CONSULTANCY: 2.0,
        CompanyType.RECRUITER: -2.0,
        CompanyType.OTHER: 0.0,
        CompanyType.UNKNOWN: 0.0,
    }[
        candidate.company_type
    ]

    if type_score > 0:
        reasons.append(
            "company type "
            f"{candidate.company_type.value}"
        )

    score = round(
        max(
            0.0,
            min(
                100.0,
                professional_score
                + contact_score
                + activity_score
                + manual_score
                + yc_score
                + geo_score
                + targeting_score
                + type_score,
            ),
        ),
        2,
    )

    if score >= 75:
        level = "VERY_HIGH"
    elif score >= 60:
        level = "HIGH"
    elif score >= 45:
        level = "MEDIUM"
    else:
        level = "LOW"

    return OutreachEvaluation(
        company_id=(
            candidate.company_id
        ),
        company_name=(
            candidate.company_name
        ),
        score=score,
        level=level,
        best_contact=best_contact,
        contact_score=(
            contact_score
        ),
        current_max_match=(
            candidate
            .current_max_match
        ),
        historical_max_match=(
            historical_match
        ),
        contacted=(
            candidate.contacted
        ),
        reasons=tuple(
            reasons
        ),
    )


def _best_contact(
    contacts: tuple[
        PublicContact,
        ...
    ],
) -> tuple[
    PublicContact | None,
    float,
]:
    ranked = [
        (
            contact_quality_score(
                contact
            ),
            contact,
        )
        for contact in contacts
    ]

    ranked = [
        item
        for item in ranked
        if item[0] > 0
    ]

    if not ranked:
        return (
            None,
            0.0,
        )

    score, contact = max(
        ranked,
        key=lambda item: (
            item[0],
            -(
                item[1].id
                or 0
            ),
        ),
    )

    return (
        contact,
        score,
    )


def _cessi_activity_score(
    activities: tuple[
        str,
        ...
    ],
) -> float:
    if not activities:
        return 0.0

    text = " | ".join(
        activities
    ).casefold()

    high_relevance_terms = (
        "desarrollo de software",
        "aplicaciones mobile",
        "inteligencia artificial",
        "análisis de software",
        "analisis de software",
        "arquitectura de software",
        "herramientas de desarrollo",
        "infraestructura",
        "seguridad",
        "integración de soluciones",
        "integracion de soluciones",
        "servicios en la nube",
        "fintech",
        "servicios financieros",
        "iot",
        "almacenamiento de datos",
        "dbm",
        "bpm",
        "e-commerce",
        "comercio electrónico",
        "comercio electronico",
    )

    if any(
        term in text
        for term in (
            high_relevance_terms
        )
    ):
        return 20.0

    return 12.0


def _max_optional(
    first: float | None,
    second: float | None,
) -> float | None:
    values = [
        value
        for value in (
            first,
            second,
        )
        if value is not None
    ]

    return (
        max(
            values
        )
        if values
        else None
    )
