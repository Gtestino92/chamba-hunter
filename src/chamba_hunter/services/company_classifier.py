from dataclasses import dataclass

from chamba_hunter.domain.enums import CompanyType
from chamba_hunter.sources.himalayas import (
    HimalayasCompanyProfile,
)


RECRUITER_SIGNALS = {
    "recruitment agency": 4,
    "staffing agency": 4,
    "recruiting firm": 4,
    "staffing firm": 4,
    "recruitment services": 3,
    "staffing services": 3,
    "talent acquisition services": 3,
    "headhunting": 3,
    "executive search": 3,
}

CONSULTANCY_SIGNALS = {
    "staff augmentation": 4,
    "software development services": 3,
    "technology consulting": 3,
    "it consulting": 3,
    "consulting services": 3,
    "outsourcing": 3,
    "nearshore": 3,
    "offshore development": 3,
    "digital transformation services": 2,
    "our clients": 1,
}

PRODUCT_SIGNALS = {
    "our platform": 2,
    "our product": 2,
    "software platform": 2,
    "developer platform": 2,
    "api platform": 2,
    "we build": 1,
    "builds": 1,
}

PRODUCT_MARKETS = {
    "saas",
    "software",
    "apis",
    "api",
    "developer tools",
    "fintech",
    "marketplace",
    "platform",
}


@dataclass(frozen=True, slots=True)
class ClassificationDecision:
    company_type: CompanyType
    confidence: float
    evidence: dict


def classify_company(
    profile: HimalayasCompanyProfile,
) -> ClassificationDecision:
    text = " ".join(
        part
        for part in (
            profile.name,
            profile.description or "",
        )
        if part
    ).casefold()

    scores = {
        CompanyType.PRODUCT: 0,
        CompanyType.CONSULTANCY: 0,
        CompanyType.RECRUITER: 0,
    }

    matches: dict[str, list[str]] = {
        "product": [],
        "consultancy": [],
        "recruiter": [],
    }

    _apply_signals(
        text,
        PRODUCT_SIGNALS,
        scores,
        matches,
        CompanyType.PRODUCT,
        "product",
    )

    _apply_signals(
        text,
        CONSULTANCY_SIGNALS,
        scores,
        matches,
        CompanyType.CONSULTANCY,
        "consultancy",
    )

    _apply_signals(
        text,
        RECRUITER_SIGNALS,
        scores,
        matches,
        CompanyType.RECRUITER,
        "recruiter",
    )

    for market in profile.markets:
        if market.casefold() in PRODUCT_MARKETS:
            scores[CompanyType.PRODUCT] += 1
            matches["product"].append(
                f"market:{market}"
            )

    ordered = sorted(
        scores.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    winner, winner_score = ordered[0]
    runner_up_score = ordered[1][1]

    margin = winner_score - runner_up_score

    if winner_score < 3 or margin < 1:
        company_type = CompanyType.UNKNOWN
        confidence = 0.40
    elif winner_score >= 6 and margin >= 3:
        company_type = winner
        confidence = 0.95
    elif winner_score >= 4 and margin >= 2:
        company_type = winner
        confidence = 0.85
    else:
        company_type = winner
        confidence = 0.70

    return ClassificationDecision(
        company_type=company_type,
        confidence=confidence,
        evidence={
            "scores": {
                key.value: value
                for key, value in scores.items()
            },
            "matches": matches,
            "markets": profile.markets,
        },
    )


def _apply_signals(
    text: str,
    signals: dict[str, int],
    scores: dict[CompanyType, int],
    matches: dict[str, list[str]],
    company_type: CompanyType,
    evidence_key: str,
) -> None:
    for phrase, weight in signals.items():
        if phrase in text:
            scores[company_type] += weight
            matches[evidence_key].append(phrase)