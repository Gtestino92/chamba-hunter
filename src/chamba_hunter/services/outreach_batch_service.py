from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re

from chamba_hunter.repositories.company_outreach_repository import (
    CompanyOutreachRepository,
    OutreachReportRow,
)
from chamba_hunter.services.outreach_decision_service import (
    decide_outreach,
)
from chamba_hunter.services.outreach_eligibility_service import (
    OutreachEligibilityService,
)


BATCH_VERSION = "OUTREACH_BATCH_V1"

GENERIC_STRATEGIES = frozenset(
    {
        "RECRUITING_MAILBOX",
        "CAREERS_MAILBOX",
        "GENERAL_MAILBOX",
    }
)

_GENERIC_LOCAL_PARTS = frozenset(
    {
        "career",
        "careers",
        "contact",
        "contacto",
        "empleo",
        "empleos",
        "hello",
        "hiring",
        "hola",
        "hr",
        "info",
        "job",
        "jobs",
        "people",
        "recruiting",
        "rrhh",
        "talent",
        "team",
        "work",
    }
)


@dataclass(frozen=True, slots=True)
class OutreachBatchItem:
    company_id: int
    contact_id: int
    company: str
    to: str
    subject: str
    body: str
    language: str
    strategy: str
    confidence: str
    eligibility_reason: str
    source_url: str | None
    attachment_name: str
    state: str = "READY_FOR_DRAFT"


@dataclass(frozen=True, slots=True)
class OutreachBatch:
    version: str
    profile: str
    minimum_score: float
    attachment_name: str
    items: tuple[OutreachBatchItem, ...]

    def write_json(self, path: Path) -> None:
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        payload = {
            "version": self.version,
            "profile": self.profile,
            "minimum_score": self.minimum_score,
            "attachment_name": self.attachment_name,
            "items": [
                asdict(item)
                for item in self.items
            ],
        }
        path.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )


def prepare_generic_outreach_batch(
    *,
    repository: CompanyOutreachRepository,
    search_profile_name: str,
    min_score: float,
    limit: int,
    language: str | None,
    attachment_name: str,
    include_unknown: bool = False,
) -> OutreachBatch:
    eligibility_service = OutreachEligibilityService(
        repository.database
    )

    selected: list[OutreachBatchItem] = []

    rows = repository.list_report_rows(
        search_profile_name=search_profile_name,
        min_score=min_score,
    )

    for row in rows:
        if row.contacted:
            continue

        eligibility = eligibility_service.decide(
            row
        )

        if eligibility.status == "INELIGIBLE":
            continue

        if (
            eligibility.status == "UNKNOWN"
            and not include_unknown
        ):
            continue

        decision = decide_outreach(
            row
        )

        if decision.strategy not in GENERIC_STRATEGIES:
            continue

        if not _is_generic_recipient(
            row,
            strategy=decision.strategy,
        ):
            continue

        if (
            language is not None
            and decision.language != language
        ):
            continue

        if (
            row.best_contact_id is None
            or row.contact_value is None
        ):
            continue

        subject, body = _render_message(
            company=row.company_name,
            language=decision.language,
        )

        selected.append(
            OutreachBatchItem(
                company_id=row.company_id,
                contact_id=row.best_contact_id,
                company=row.company_name,
                to=row.contact_value,
                subject=subject,
                body=body,
                language=decision.language,
                strategy=decision.strategy,
                confidence=decision.confidence,
                eligibility_reason=(
                    eligibility.reason
                ),
                source_url=(
                    row.contact_source_url
                ),
                attachment_name=(
                    attachment_name
                ),
            )
        )

        if len(selected) >= limit:
            break

    return OutreachBatch(
        version=BATCH_VERSION,
        profile=search_profile_name,
        minimum_score=min_score,
        attachment_name=attachment_name,
        items=tuple(selected),
    )


def _is_generic_recipient(
    row: OutreachReportRow,
    *,
    strategy: str,
) -> bool:
    if strategy in {
        "RECRUITING_MAILBOX",
        "CAREERS_MAILBOX",
    }:
        return True

    value = (
        row.contact_value
        or ""
    ).strip().casefold()

    if "@" not in value:
        return False

    local_part = value.split(
        "@",
        1,
    )[0]

    tokens = tuple(
        token
        for token in re.split(
            r"[._+\-]+",
            local_part,
        )
        if token
    )

    return bool(
        tokens
        and tokens[0]
        in _GENERIC_LOCAL_PARTS
    )


def _render_message(
    *,
    company: str,
    language: str,
) -> tuple[str, str]:
    if language == "ES":
        return (
            "Desarrollador Backend – Argentina",
            (
                "Buenas, ¿cómo están?\n\n"
                f"Encontré {company} mientras buscaba equipos "
                "de software donde mi experiencia en backend "
                "pudiera encajar.\n\n"
                "Soy desarrollador Backend en Buenos Aires, "
                "con más de 7 años de experiencia, principalmente "
                "trabajando con Java, Kotlin y Spring en servicios "
                "backend, APIs y sistemas distribuidos.\n\n"
                "Actualmente estoy buscando nuevas oportunidades "
                "y me interesaría ser tenido en cuenta para "
                "posiciones de backend/software engineering "
                "dentro del equipo.\n\n"
                "Adjunto mi CV como referencia.\n\n"
                "Saludos,\n"
                "Giuliano Testino"
            ),
        )

    return (
        "Backend Software Engineer – Argentina",
        (
            "Hi!\n\n"
            f"I came across {company} while looking for software "
            "teams where my backend experience could be a good fit.\n\n"
            "I'm a Backend Software Engineer based in Buenos Aires "
            "with 7+ years of experience, mainly working with Java, "
            "Kotlin and Spring on backend services, APIs and "
            "distributed systems.\n\n"
            "I'm currently exploring new opportunities and would "
            "be interested in being considered for backend/software "
            "engineering roles with your team.\n\n"
            "I've attached my CV for reference.\n\n"
            "Best regards,\n"
            "Giuliano Testino"
        ),
    )
