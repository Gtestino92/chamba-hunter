from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit
import unicodedata

from pydantic import AnyHttpUrl

from chamba_hunter.domain.models import Company
from chamba_hunter.repositories.company_repository import CompanyRepository
from chamba_hunter.schemas.inputs import CompanySeedInput


def clean_company_name(name: str) -> str:
    """
    Cleans a company name for display/storage without changing its meaning.
    """
    return " ".join(name.split())


def normalize_company_name(name: str) -> str:
    """
    Produces a stable representation used for matching/deduplication.
    """
    cleaned = clean_company_name(name)
    normalized = unicodedata.normalize("NFKC", cleaned)

    return normalized.casefold()


def extract_domain(url: AnyHttpUrl) -> str:
    parsed = urlsplit(str(url))

    hostname = parsed.hostname

    if hostname is None:
        raise ValueError(f"URL does not contain a hostname: {url}")

    domain = hostname.casefold()

    if domain.startswith("www."):
        domain = domain[4:]

    return domain


def normalize_website_url(url: AnyHttpUrl) -> str:
    """
    Canonicalizes a company website URL.

    Examples:
        https://www.pomelo.la/ -> https://pomelo.la
        HTTPS://EXAMPLE.COM/   -> https://example.com
    """
    parsed = urlsplit(str(url))

    domain = extract_domain(url)

    port = parsed.port

    if port is not None:
        is_default_port = (
            parsed.scheme.casefold() == "http" and port == 80
        ) or (
            parsed.scheme.casefold() == "https" and port == 443
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


@dataclass(frozen=True, slots=True)
class CompanyImportResult:
    company: Company
    created: bool
    matched_by: str | None = None


class CompanyImportService:
    def __init__(
        self,
        company_repository: CompanyRepository,
    ) -> None:
        self.company_repository = company_repository

    def import_seed(
        self,
        seed: CompanySeedInput,
    ) -> CompanyImportResult:
        name = clean_company_name(seed.name)
        normalized_name = normalize_company_name(seed.name)

        website_url: str | None = None
        domain: str | None = None

        if seed.website_url is not None:
            website_url = normalize_website_url(seed.website_url)
            domain = extract_domain(seed.website_url)

        existing: Company | None = None
        matched_by: str | None = None

        if domain is not None:
            existing = self.company_repository.get_by_domain(domain)

            if existing is not None:
                matched_by = "DOMAIN"

        elif normalized_name:
            existing = self.company_repository.get_by_normalized_name(
                normalized_name
            )

            if existing is not None:
                matched_by = "NORMALIZED_NAME"

        if existing is not None:
            return CompanyImportResult(
                company=existing,
                created=False,
                matched_by=matched_by,
            )

        company = Company(
            name=name,
            normalized_name=normalized_name,
            domain=domain,
            website_url=website_url,
            country=seed.country,
            notes=seed.notes,
        )

        saved = self.company_repository.add(company)

        return CompanyImportResult(
            company=saved,
            created=True,
        )