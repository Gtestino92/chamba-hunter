from dataclasses import dataclass
from html import unescape
import re
import unicodedata

from chamba_hunter.domain.enums import CompanyType


RECRUITER_SIGNALS = {
    # English
    "recruitment agency": 6,
    "staffing agency": 6,
    "recruiting firm": 6,
    "staffing firm": 6,
    "recruitment services": 5,
    "staffing services": 5,
    "executive search": 5,
    "headhunting": 5,
    "recruiting services": 5,
    "talent acquisition services": 5,
    "remote hiring": 4,
    "place candidates": 6,
    "placing candidates": 6,
    "placing a-players": 5,
    "find remote roles": 4,

    # Weak name/context signal.
    "talent partners": 2,

    # Spanish
    "reclutamiento": 5,
    "seleccion de personal": 5,
    "busqueda y seleccion": 5,
    "busqueda de talento": 5,
    "seleccion de talento": 5,
    "headhunter": 5,
    "conectamos talento": 4,
    "conectamos profesionales": 4,
}


CONSULTANCY_SIGNALS = {
    # Strong English signals
    "staff augmentation": 6,
    "outsourcing": 6,
    "nearshore": 5,
    "offshore development": 5,
    "software development services": 5,
    "custom software development": 5,
    "technology consulting": 5,
    "it consulting": 5,
    "consulting services": 4,
    "digital transformation services": 4,

    # Added in V3
    "it services firm": 6,
    "it services company": 6,
    "custom websites": 5,
    "custom apps": 5,
    "custom applications": 5,
    "digital ecosystems": 4,

    # Supporting English signals
    "client projects": 3,
    "our clients": 2,

    # Strong Spanish signals
    "consultora tecnologica": 6,
    "consultoria tecnologica": 5,
    "consultoria de ti": 6,
    "servicios de ti": 5,
    "servicios ti": 5,
    "servicios de consultoria": 5,
    "prestar servicios de consultoria": 6,
    "desarrollo de software a medida": 6,
    "software a medida": 5,
    "servicios de desarrollo de software": 6,
    "desarrollo de software para clientes": 5,

    # Medium Spanish signals
    "desarrollamos software para": 4,
    "soluciones digitales para": 4,
    "transformar digitalmente a distintas organizaciones": 4,
    "trabajamos con nuestros clientes": 3,
    "trabajamos con los clientes": 3,

    # Weak supporting signals.
    "desarrollo de software": 2,
    "desarrollamos software": 2,
    "nuestros clientes": 2,
    "partners tecnologicos": 2,
}


PRODUCT_SIGNALS = {
    # Strong English signals
    "product company": 6,
    "our product": 5,
    "our products": 5,
    "our platform": 5,
    "saas platform": 5,
    "software as a service": 5,
    "software-as-a-service": 5,
    "developer platform": 4,
    "api platform": 4,
    "fintech platform": 4,
    "our marketplace": 4,
    "our app": 3,
    "our application": 3,
    "subscription platform": 3,
    "proprietary technology": 5,
    "productization": 5,

    # Added in V3
    "operating platform": 5,
    "software platform": 4,

    # Strong Spanish signals
    "es una plataforma": 6,
    "somos una plataforma": 6,
    "plataforma que conecta": 6,
    "nuestro producto": 5,
    "nuestros productos": 5,
    "nuestra plataforma": 5,
    "producto propio": 6,
    "productos propios": 6,
    "tecnologia propia": 5,
    "tecnologia propietaria": 5,
    "productizacion": 5,

    # Supporting signal only.
    "saas": 3,
}


@dataclass(frozen=True, slots=True)
class ClassificationDecision:
    company_type: CompanyType
    confidence: float
    evidence: dict


def classify_company(
    name: str,
    description: str | None,
    long_description: str | None,
) -> ClassificationDecision:
    text = _normalize_text(
        " ".join(
            value
            for value in (
                name,
                description,
                long_description,
            )
            if value
        )
    )

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
        text=text,
        signals=PRODUCT_SIGNALS,
        scores=scores,
        matches=matches,
        company_type=CompanyType.PRODUCT,
        evidence_key="product",
    )

    _apply_signals(
        text=text,
        signals=CONSULTANCY_SIGNALS,
        scores=scores,
        matches=matches,
        company_type=CompanyType.CONSULTANCY,
        evidence_key="consultancy",
    )

    _apply_signals(
        text=text,
        signals=RECRUITER_SIGNALS,
        scores=scores,
        matches=matches,
        company_type=CompanyType.RECRUITER,
        evidence_key="recruiter",
    )

    ordered = sorted(
        scores.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    winner, winner_score = ordered[0]
    runner_up_score = ordered[1][1]

    margin = winner_score - runner_up_score

    if winner_score < 3:
        company_type = CompanyType.UNKNOWN
        confidence = 0.40

    elif margin < 2:
        company_type = CompanyType.UNKNOWN
        confidence = 0.50

    elif winner_score >= 6 and margin >= 4:
        company_type = winner
        confidence = 0.95

    elif winner_score >= 5 and margin >= 3:
        company_type = winner
        confidence = 0.90

    elif winner_score >= 4 and margin >= 2:
        company_type = winner
        confidence = 0.80

    else:
        company_type = winner
        confidence = 0.70

    return ClassificationDecision(
        company_type=company_type,
        confidence=confidence,
        evidence={
            "scores": {
                item_type.value: score
                for item_type, score
                in scores.items()
            },
            "matches": matches,
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
        normalized_phrase = _normalize_text(
            phrase
        )

        if normalized_phrase in text:
            scores[company_type] += weight
            matches[evidence_key].append(
                phrase
            )


def _normalize_text(
    value: str,
) -> str:
    value = unescape(value)

    value = re.sub(
        r"<[^>]+>",
        " ",
        value,
    )

    decomposed = unicodedata.normalize(
        "NFKD",
        value,
    )

    without_accents = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(
            character
        )
    )

    return " ".join(
        without_accents.casefold().split()
    )