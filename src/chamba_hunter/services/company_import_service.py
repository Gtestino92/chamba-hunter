from dataclasses import dataclass
from urllib.parse import (
    urlsplit,
    urlunsplit,
)
import unicodedata

from pydantic import AnyHttpUrl

from chamba_hunter.domain.models import (
    Company,
    CompanySource,
)
from chamba_hunter.repositories.company_repository import (
    CompanyRepository,
)
from chamba_hunter.repositories.company_source_repository import (
    CompanySourceRepository,
)
from chamba_hunter.schemas.inputs import (
    CompanySeedInput,
)


def clean_company_name(
    name: str,
) -> str:
    return " ".join(name.split())


def normalize_company_name(
    name: str,
) -> str:
    cleaned = clean_company_name(name)

    normalized = unicodedata.normalize(
        "NFKC",
        cleaned,
    )

    return normalized.casefold()


def extract_domain(
    url: AnyHttpUrl,
) -> str:
    parsed = urlsplit(str(url))

    hostname = parsed.hostname

    if hostname is None:
        raise ValueError(
            f"URL does not contain a "
            f"hostname: {url}"
        )

    domain = hostname.casefold()

    if domain.startswith("www."):
        domain = domain[4:]

    return domain


def normalize_website_url(
    url: AnyHttpUrl,
) -> str:
    parsed = urlsplit(str(url))

    domain = extract_domain(url)

    port = parsed.port

    if port is not None:
        is_default_port = (
            parsed.scheme.casefold() == "http"
            and port == 80
        ) or (
            parsed.scheme.casefold() == "https"
            and port == 443
        )

        if not is_default_port:
            domain = f"{domain}:{port}"

    path = parsed.path.rstrip("/")

    return urlunsplit(
        (
            parsed.scheme.casefold(),
            domain,
            path,
            "",
            "",
        )
    )


def normalize_reference_url(
    url: AnyHttpUrl,
) -> str:
    """
    Normalizes a public reference URL while preserving
    its query string, which may be meaningful for
    careers pages or ATS links.
    """
    parsed = urlsplit(str(url))

    domain = extract_domain(url)

    port = parsed.port

    if port is not None:
        is_default_port = (
            parsed.scheme.casefold() == "http"
            and port == 80
        ) or (
            parsed.scheme.casefold() == "https"
            and port == 443
        )

        if not is_default_port:
            domain = f"{domain}:{port}"

    path = parsed.path.rstrip("/")

    return urlunsplit(
        (
            parsed.scheme.casefold(),
            domain,
            path,
            parsed.query,
            "",
        )
    )


@dataclass(frozen=True, slots=True)
class CompanyImportResult:
    company: Company
    created: bool
    matched_by: str | None = None


class CompanyImportService:
    def __init__(
        self,
        company_repository: CompanyRepository,
        company_source_repository: CompanySourceRepository,
    ) -> None:
        self.company_repository = (
            company_repository
        )
        self.company_source_repository = (
            company_source_repository
        )

    def import_seed(
        self,
        seed: CompanySeedInput,
        source_metadata: dict | None = None,
    ) -> CompanyImportResult:
        name = clean_company_name(
            seed.name
        )

        normalized_name = normalize_company_name(
            seed.name
        )

        website_url: str | None = None
        domain: str | None = None

        if seed.website_url is not None:
            website_url = normalize_website_url(
                seed.website_url
            )

            domain = extract_domain(
                seed.website_url
            )

        careers_url = (
            normalize_reference_url(
                seed.careers_url
            )
            if seed.careers_url is not None
            else None
        )

        source_url = (
            normalize_reference_url(
                seed.source_url
            )
            if seed.source_url is not None
            else None
        )

        existing: Company | None = None
        matched_by: str | None = None

        source_company_id = (
            self.company_source_repository
            .find_company_id(
                source_type=seed.source_type,
                external_id=seed.external_id,
                source_url=source_url,
            )
        )

        if source_company_id is not None:
            existing = (
                self.company_repository
                .get_by_id(
                    source_company_id
                )
            )

            if existing is None:
                raise RuntimeError(
                    "Company source references "
                    "a missing company."
                )

            matched_by = "SOURCE"

        if (
            existing is None
            and domain is not None
        ):
            existing = (
                self.company_repository
                .get_by_domain(domain)
            )

            if existing is not None:
                matched_by = "DOMAIN"

        if existing is None and normalized_name:
            name_candidate = (
                self.company_repository
                .get_unique_by_normalized_name(
                    normalized_name
                )
            )

            if name_candidate is not None:
                if domain is None:
                    existing = name_candidate
                    matched_by = (
                        "NORMALIZED_NAME"
                    )

                elif (
                    name_candidate.domain
                    is None
                ):
                    existing = name_candidate
                    matched_by = (
                        "NORMALIZED_NAME_DOMAINLESS"
                    )

        if existing is not None:
            if existing.id is None:
                raise RuntimeError(
                    "Existing company must "
                    "have an id."
                )

            company = (
                self.company_repository
                .fill_missing_discovery_fields(
                    company_id=existing.id,
                    website_url=website_url,
                    domain=domain,
                    careers_url=careers_url,
                    country=seed.country,
                )
            )

            created = False

        else:
            company = Company(
                name=name,
                normalized_name=(
                    normalized_name
                ),
                domain=domain,
                website_url=website_url,
                careers_url=careers_url,
                country=seed.country,
                notes=seed.notes,
            )

            company = (
                self.company_repository.add(
                    company
                )
            )

            created = True

        if company.id is None:
            raise RuntimeError(
                "Imported company must have "
                "an id before recording its "
                "source."
            )

        self.company_source_repository.add_or_touch(
            CompanySource(
                company_id=company.id,
                source_type=seed.source_type,
                external_id=seed.external_id,
                source_url=source_url,
                raw_name=seed.name,
                metadata=source_metadata,
            )
        )

        return CompanyImportResult(
            company=company,
            created=created,
            matched_by=matched_by,
        )