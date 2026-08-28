from dataclasses import dataclass
from urllib.parse import urlsplit

from chamba_hunter.domain.enums import (
    ContactType,
)
from chamba_hunter.repositories.company_outreach_repository import (
    OutreachReportRow,
)
from chamba_hunter.services.public_contact_quality import (
    contact_quality_score_for,
)


DECISION_VERSION = "OUTREACH_DECISION_V1_1"

EMAIL_STRATEGIES = frozenset(
    {
        "DIRECT_PERSON",
        "RECRUITING_MAILBOX",
        "CAREERS_MAILBOX",
        "GENERAL_MAILBOX",
    }
)

DIRECT_LABELS = frozenset(
    {
        "DIRECT_RECRUITING",
        "DIRECT_TECH_LEADER",
        "DIRECT_ENGINEERING",
        "DIRECT_LEADER",
        "DIRECT_HIRING",
        "DIRECT_OPERATIONS",
        "DIRECT_PERSON",
    }
)

SPANISH_COUNTRY_TERMS = (
    "argentin",
    "bolivia",
    "chile",
    "colombia",
    "costa rica",
    "ecuador",
    "el salvador",
    "guatemala",
    "honduras",
    "mexic",
    "méxic",
    "nicaragua",
    "panama",
    "panamá",
    "paraguay",
    "peru",
    "perú",
    "spain",
    "españa",
    "uruguay",
    "venezuela",
)

SPANISH_HOST_SUFFIXES = (
    ".ar",
    ".cl",
    ".co",
    ".mx",
    ".pe",
    ".uy",
    ".py",
    ".bo",
    ".ec",
    ".ve",
    ".es",
)


@dataclass(frozen=True, slots=True)
class OutreachDecision:
    strategy: str
    language: str
    confidence: str

    contact_score: float
    role_hint: str | None

    rationale: tuple[str, ...]

    @property
    def is_email(self) -> bool:
        return self.strategy in EMAIL_STRATEGIES


def decide_outreach(
    row: OutreachReportRow,
) -> OutreachDecision:
    contact_score = _contact_score(
        row
    )

    strategy = _strategy(
        row
    )

    language, language_reason = (
        _language(
            row
        )
    )

    confidence = _confidence(
        strategy=strategy,
        contact_score=contact_score,
        language_reason=language_reason,
    )

    rationale = [
        f"channel={strategy}",
        f"contact_score={contact_score:.0f}",
        f"language={language_reason}",
    ]

    if row.contact_intelligence_role_hint:
        rationale.append(
            "role="
            + row.contact_intelligence_role_hint
        )

    return OutreachDecision(
        strategy=strategy,
        language=language,
        confidence=confidence,
        contact_score=contact_score,
        role_hint=(
            row.contact_intelligence_role_hint
        ),
        rationale=tuple(
            rationale
        ),
    )


def _strategy(
    row: OutreachReportRow,
) -> str:
    if (
        row.contact_type is None
        or row.contact_value is None
    ):
        return "SKIP"

    contact_type = ContactType(
        row.contact_type
    )

    if (
        contact_type
        == ContactType.RECRUITING_EMAIL
    ):
        return "RECRUITING_MAILBOX"

    if (
        contact_type
        == ContactType.CAREERS_EMAIL
    ):
        return "CAREERS_MAILBOX"

    if (
        contact_type
        == ContactType.GENERAL_APPLICATION_URL
    ):
        return "GENERAL_FORM"

    label = (
        row.contact_intelligence_label
        or ""
    )

    if label in DIRECT_LABELS:
        return "DIRECT_PERSON"

    return "GENERAL_MAILBOX"


def _language(
    row: OutreachReportRow,
) -> tuple[str, str]:
    if row.cessi_source:
        return (
            "ES",
            "CESSI/Argentina evidence",
        )

    if row.argentina_directory_sources:
        return (
            "ES",
            "Argentina directory evidence",
        )

    country = (
        row.country
        or ""
    ).casefold()

    if any(
        term in country
        for term in SPANISH_COUNTRY_TERMS
    ):
        return (
            "ES",
            "Spanish-speaking country",
        )

    for url in (
        row.website_url,
        row.contact_source_url,
    ):
        hostname = _hostname(
            url
        )

        if hostname and any(
            hostname.endswith(
                suffix
            )
            for suffix in (
                SPANISH_HOST_SUFFIXES
            )
        ):
            return (
                "ES",
                "Spanish-language country domain",
            )

    return (
        "EN",
        "international/default",
    )


def _confidence(
    *,
    strategy: str,
    contact_score: float,
    language_reason: str,
) -> str:
    if strategy == "SKIP":
        return "LOW"

    if strategy == "DIRECT_PERSON":
        if contact_score >= 25:
            return "HIGH"
        if contact_score >= 15:
            return "MEDIUM"
        return "LOW"

    if strategy in {
        "RECRUITING_MAILBOX",
        "CAREERS_MAILBOX",
    }:
        return (
            "HIGH"
            if contact_score >= 18
            else "MEDIUM"
        )

    if strategy == "GENERAL_MAILBOX":
        return (
            "MEDIUM"
            if contact_score >= 10
            else "LOW"
        )

    if strategy == "GENERAL_FORM":
        return "MEDIUM"

    if (
        language_reason
        == "international/default"
    ):
        return "LOW"

    return "MEDIUM"


def _contact_score(
    row: OutreachReportRow,
) -> float:
    if (
        row.contact_type is None
        or row.contact_value is None
    ):
        return 0.0

    if (
        row.contact_intelligence_score
        is not None
    ):
        return float(
            row.contact_intelligence_score
        )

    return contact_quality_score_for(
        ContactType(
            row.contact_type
        ),
        row.contact_value,
    )


def _hostname(
    value: str | None,
) -> str | None:
    if not value:
        return None

    hostname = urlsplit(
        value
    ).hostname

    if hostname is None:
        return None

    return (
        hostname.casefold()
        .removeprefix("www.")
    )
