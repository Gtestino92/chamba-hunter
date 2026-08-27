from urllib.parse import urlsplit

from chamba_hunter.domain.enums import (
    ContactType,
)
from chamba_hunter.domain.models import (
    PublicContact,
)


PLACEHOLDER_LOCAL_PARTS = {
    "email",
    "e-mail",
    "mail",
    "name",
    "nombre",
    "user",
    "usuario",
    "test",
    "example",
    "ejemplo",
    "yourname",
    "your-name",
}

PLACEHOLDER_DOMAINS = {
    "example.com",
    "example.org",
    "example.net",
    "empresa.com",
    "dominio.com",
    "dominio.cl",
    "domain.com",
    "company.com",
    "yourcompany.com",
}

FREE_EMAIL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "hotmail.com",
    "hotmail.com.ar",
    "outlook.com",
    "live.com",
    "live.com.ar",
    "yahoo.com",
    "yahoo.com.ar",
    "icloud.com",
    "me.com",
    "proton.me",
    "protonmail.com",
    "aol.com",
    "gmx.com",
}

LOW_VALUE_LOCAL_PARTS = {
    "support",
    "soporte",
    "help",
    "helpdesk",
    "billing",
    "invoice",
    "invoices",
    "facturacion",
    "contabilidad",
    "accounting",
    "accounts",
    "administracion",
    "administration",
    "admin",
    "legal",
    "privacy",
    "abuse",
    "security",
    "sales",
    "ventas",
    "marketing",
    "press",
    "prensa",
    "media",
    "partners",
    "partnerships",
}

GENERIC_USEFUL_LOCAL_PARTS = {
    "info",
    "contact",
    "contacto",
    "hello",
    "hola",
    "hi",
    "office",
    "general",
}

RECRUITING_TOKENS = (
    "recruit",
    "talent",
    "humanresources",
    "recursoshumanos",
    "peopleops",
    "rrhh",
)

CAREERS_TOKENS = (
    "career",
    "careers",
    "jobs",
    "job",
    "empleo",
    "empleos",
    "trabajo",
    "trabajos",
    "vacante",
    "vacantes",
    "carrera",
    "carreras",
    "resume",
)


def normalize_email(
    value: str,
) -> str:
    return (
        value.strip()
        .rstrip(".,;:)]}>")
        .casefold()
    )


def split_email(
    value: str,
) -> tuple[str, str] | None:
    email = normalize_email(
        value
    )

    if (
        email.count("@") != 1
        or " " in email
    ):
        return None

    local_part, domain = (
        email.split("@", 1)
    )

    if (
        not local_part
        or not domain
        or "." not in domain
    ):
        return None

    return (
        local_part,
        domain,
    )


def compact_local_part(
    local_part: str,
) -> str:
    return "".join(
        char
        for char in local_part
        if char.isalnum()
    )


def classify_email(
    value: str,
) -> ContactType | None:
    split = split_email(
        value
    )

    if split is None:
        return None

    local_part, _ = split

    if is_obvious_placeholder_email(
        value
    ):
        return None

    compact = compact_local_part(
        local_part
    )

    if (
        local_part
        in LOW_VALUE_LOCAL_PARTS
        or compact
        in {
            compact_local_part(item)
            for item in LOW_VALUE_LOCAL_PARTS
        }
    ):
        return ContactType.GENERAL_EMAIL

    if any(
        token in compact
        for token in RECRUITING_TOKENS
    ) or compact in {
        "hr",
        "people",
    }:
        return (
            ContactType
            .RECRUITING_EMAIL
        )

    if any(
        token in compact
        for token in CAREERS_TOKENS
    ) or compact == "cv":
        return (
            ContactType
            .CAREERS_EMAIL
        )

    return ContactType.GENERAL_EMAIL


def is_obvious_placeholder_email(
    value: str,
) -> bool:
    split = split_email(
        value
    )

    if split is None:
        return True

    local_part, domain = split

    if len(local_part) <= 1:
        return True

    if (
        local_part
        in PLACEHOLDER_LOCAL_PARTS
        or compact_local_part(
            local_part
        )
        in {
            compact_local_part(item)
            for item in (
                PLACEHOLDER_LOCAL_PARTS
            )
        }
    ):
        return True

    if (
        domain
        in PLACEHOLDER_DOMAINS
        or domain.startswith(
            "example."
        )
    ):
        return True

    return False


def is_free_email(
    value: str,
) -> bool:
    split = split_email(
        value
    )

    if split is None:
        return False

    _, domain = split

    return (
        domain.casefold()
        in FREE_EMAIL_DOMAINS
    )


def is_low_value_email(
    value: str,
) -> bool:
    split = split_email(
        value
    )

    if split is None:
        return True

    local_part, _ = split

    compact = compact_local_part(
        local_part
    )

    return (
        local_part
        in LOW_VALUE_LOCAL_PARTS
        or compact
        in {
            compact_local_part(item)
            for item in (
                LOW_VALUE_LOCAL_PARTS
            )
        }
    )


def email_domain_compatible(
    email: str,
    website_url: str | None,
) -> bool:
    if website_url is None:
        return True

    split = split_email(
        email
    )

    if split is None:
        return False

    _, email_domain = split

    website_host = urlsplit(
        website_url
    ).hostname

    if website_host is None:
        return True

    website_host = (
        website_host.casefold()
        .removeprefix("www.")
    )

    email_domain = (
        email_domain.casefold()
        .removeprefix("www.")
    )

    return (
        email_domain == website_host
        or email_domain.endswith(
            "." + website_host
        )
        or website_host.endswith(
            "." + email_domain
        )
    )


def contact_quality_score_for(
    contact_type: ContactType,
    value: str,
) -> float:
    if (
        contact_type
        == ContactType
        .GENERAL_APPLICATION_URL
    ):
        return 16.0

    if (
        contact_type
        not in {
            ContactType.RECRUITING_EMAIL,
            ContactType.CAREERS_EMAIL,
            ContactType.GENERAL_EMAIL,
        }
    ):
        return 0.0

    if is_obvious_placeholder_email(
        value
    ):
        return 0.0

    if is_low_value_email(
        value
    ):
        return 0.0

    free_email = is_free_email(
        value
    )

    if (
        contact_type
        == ContactType
        .RECRUITING_EMAIL
    ):
        return (
            12.0
            if free_email
            else 20.0
        )

    if (
        contact_type
        == ContactType
        .CAREERS_EMAIL
    ):
        return (
            10.0
            if free_email
            else 18.0
        )

    split = split_email(
        value
    )

    if split is None:
        return 0.0

    local_part, _ = split

    if free_email:
        return 6.0

    compact = compact_local_part(
        local_part
    )

    if (
        local_part
        in GENERIC_USEFUL_LOCAL_PARTS
        or compact
        in {
            compact_local_part(item)
            for item in (
                GENERIC_USEFUL_LOCAL_PARTS
            )
        }
    ):
        return 10.0

    # A named/person-specific mailbox publicly exposed by
    # the company/directory is stronger than a generic inbox.
    return 15.0


def contact_quality_label_for(
    contact_type: ContactType,
    value: str,
) -> str:
    score = contact_quality_score_for(
        contact_type,
        value,
    )

    if score <= 0:
        return "LOW_VALUE"

    if (
        contact_type
        == ContactType
        .GENERAL_APPLICATION_URL
    ):
        return "GENERAL_APPLICATION"

    if is_free_email(
        value
    ):
        return "FREE_MAIL"

    if (
        contact_type
        == ContactType
        .RECRUITING_EMAIL
    ):
        return "RECRUITING"

    if (
        contact_type
        == ContactType
        .CAREERS_EMAIL
    ):
        return "CAREERS"

    split = split_email(
        value
    )

    if split is None:
        return "LOW_VALUE"

    local_part, _ = split

    compact = compact_local_part(
        local_part
    )

    if (
        local_part
        in GENERIC_USEFUL_LOCAL_PARTS
        or compact
        in {
            compact_local_part(item)
            for item in (
                GENERIC_USEFUL_LOCAL_PARTS
            )
        }
    ):
        return "GENERIC"

    return "NAMED_PUBLIC"


def contact_quality_score(
    contact: PublicContact,
) -> float:
    return contact_quality_score_for(
        contact.contact_type,
        contact.value,
    )
