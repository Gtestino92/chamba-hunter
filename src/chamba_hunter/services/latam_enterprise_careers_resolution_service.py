from collections import Counter
from dataclasses import dataclass, field
import re
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree

import httpx

from chamba_hunter.domain.enums import (
    AtsDetectionMethod,
)
from chamba_hunter.domain.models import Company
from chamba_hunter.repositories.company_repository import (
    CompanyRepository,
)
from chamba_hunter.services.careers_ats_detection_service import (
    BLOCKED_HTTP_STATUSES,
    CAREERS_TERMS,
    RAW_URL_PATTERN,
    PageDocument,
    _discover_careers_url,
    _fetch_page,
)
from chamba_hunter.services.latam_enterprise_ats_fingerprinting_service import (
    detect_fingerprint_from_url,
    detect_fingerprints_from_page,
)


COMMON_CAREERS_PATHS = (
    "/careers",
    "/jobs",
    "/empleos",
    "/vacantes",
    "/trabaja-con-nosotros",
    "/trabajo-con-nosotros",
    "/sumate",
    "/talento",
    "/oportunidades-laborales",
)

SUBDOMAIN_PREFIXES: tuple[str, ...] = ()

MAX_REQUESTS_PER_COMPANY = 16
MAX_SITEMAP_DOCUMENTS = 4
MAX_SITEMAP_URLS = 80
MAX_SITEMAP_DEPTH = 1

CAREERS_URL_TERMS = (
    "career",
    "careers",
    "job",
    "jobs",
    "empleo",
    "empleos",
    "vacante",
    "vacantes",
    "trabaja",
    "trabajo",
    "sumate",
    "talento",
    "oportunidades-laborales",
    "join-us",
    "work-with-us",
)

NEGATIVE_TERMS = (
    "contact",
    "contacto",
    "about",
    "news",
    "noticias",
    "investor",
    "producto",
    "products",
    "support",
    "soporte",
    "privacy",
    "privacidad",
    "legal",
    "login",
    "signin",
    "training",
    "capacitacion",
    "partners",
    "search",
    "busqueda",
)

JOB_PAGE_TERMS = (
    "careers",
    "jobs",
    "open positions",
    "open roles",
    "job openings",
    "join our team",
    "work with us",
    "employment",
    "vacantes",
    "empleos",
    "oportunidades laborales",
    "trabaja con nosotros",
    "trabajá con nosotros",
    "trabajo con nosotros",
    "sumate",
    "unete",
    "únete",
    "talento",
    "postulate",
    "postúlate",
)

JOB_LISTING_PATTERNS = (
    "jobposting",
    "apply now",
    "apply for this job",
    "ver vacantes",
    "ver empleos",
    "buscar empleos",
    "buscar vacantes",
    "postular",
    "postulate",
    "job search",
    "departamento",
    "ubicación",
    "location",
)


@dataclass(frozen=True, slots=True)
class CareersResolutionResult:
    company_id: int
    company_name: str
    website_url: str | None
    existing_careers_url: str | None
    resolved_careers_url: str | None
    final_url: str | None
    status: str
    method: str | None
    confidence: float | None
    evidence: str | None
    http_status: int | None
    error_type: str | None = None
    error_message: str | None = None
    applied: bool = False


@dataclass(slots=True)
class CareersResolutionSummary:
    selected: int
    apply: bool

    resolved: int = 0
    unresolved: int = 0
    blocked: int = 0
    errors: int = 0
    skipped: int = 0
    applied: int = 0
    overwritten: int = 0

    by_method: Counter[str] = field(
        default_factory=Counter
    )
    results: list[
        CareersResolutionResult
    ] = field(default_factory=list)


class LatamEnterpriseCareersResolutionService:
    def __init__(
        self,
        *,
        company_repository: CompanyRepository,
        timeout_seconds: float = 8.0,
        max_requests_per_company: int = (
            MAX_REQUESTS_PER_COMPANY
        ),
        max_sitemap_documents: int = (
            MAX_SITEMAP_DOCUMENTS
        ),
        max_sitemap_urls: int = (
            MAX_SITEMAP_URLS
        ),
        max_sitemap_depth: int = (
            MAX_SITEMAP_DEPTH
        ),
        common_paths: tuple[str, ...] = (
            COMMON_CAREERS_PATHS
        ),
        subdomain_prefixes: tuple[str, ...] = (
            SUBDOMAIN_PREFIXES
        ),
    ) -> None:
        self.company_repository = company_repository
        self.timeout_seconds = timeout_seconds
        self.max_requests_per_company = (
            max_requests_per_company
        )
        self.max_sitemap_documents = (
            max_sitemap_documents
        )
        self.max_sitemap_urls = (
            max_sitemap_urls
        )
        self.max_sitemap_depth = (
            max_sitemap_depth
        )
        self.common_paths = common_paths
        self.subdomain_prefixes = (
            subdomain_prefixes
        )

    def run(
        self,
        companies: list[Company],
        *,
        apply: bool = False,
        client: httpx.Client | None = None,
    ) -> CareersResolutionSummary:
        summary = CareersResolutionSummary(
            selected=len(companies),
            apply=apply,
        )

        if client is None:
            with httpx.Client(
                timeout=self.timeout_seconds,
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        "chamba-hunter/0.1"
                    )
                },
            ) as owned_client:
                self._run_with_client(
                    companies=companies,
                    apply=apply,
                    client=owned_client,
                    summary=summary,
                )
        else:
            self._run_with_client(
                companies=companies,
                apply=apply,
                client=client,
                summary=summary,
            )

        return summary

    def _run_with_client(
        self,
        *,
        companies: list[Company],
        apply: bool,
        client: httpx.Client,
        summary: CareersResolutionSummary,
    ) -> None:
        for company in companies:
            result = self.resolve_company(
                company=company,
                client=client,
            )

            applied = False
            if (
                apply
                and company.id is not None
                and company.careers_url is None
                and result.status == "RESOLVED"
                and result.confidence is not None
                and result.confidence >= 0.70
                and result.resolved_careers_url
            ):
                before = (
                    self.company_repository
                    .get_by_id(company.id)
                )
                updated = (
                    self.company_repository
                    .fill_missing_discovery_fields(
                        company_id=company.id,
                        careers_url=(
                            result
                            .resolved_careers_url
                        ),
                    )
                )
                applied = (
                    before is not None
                    and before.careers_url is None
                    and updated.careers_url
                    == result.resolved_careers_url
                )
                if applied:
                    summary.applied += 1
                elif (
                    before is not None
                    and before.careers_url
                    is not None
                    and updated.careers_url
                    != before.careers_url
                ):
                    summary.overwritten += 1

            if applied:
                result = CareersResolutionResult(
                    company_id=result.company_id,
                    company_name=result.company_name,
                    website_url=result.website_url,
                    existing_careers_url=(
                        result.existing_careers_url
                    ),
                    resolved_careers_url=(
                        result.resolved_careers_url
                    ),
                    final_url=result.final_url,
                    status=result.status,
                    method=result.method,
                    confidence=result.confidence,
                    evidence=result.evidence,
                    http_status=result.http_status,
                    error_type=result.error_type,
                    error_message=(
                        result.error_message
                    ),
                    applied=True,
                )

            _add_to_summary(
                summary=summary,
                result=result,
            )

    def resolve_company(
        self,
        *,
        company: Company,
        client: httpx.Client,
    ) -> CareersResolutionResult:
        if company.id is None:
            raise ValueError(
                "Company must have an id."
            )

        if company.careers_url is not None:
            return CareersResolutionResult(
                company_id=company.id,
                company_name=company.name,
                website_url=company.website_url,
                existing_careers_url=(
                    company.careers_url
                ),
                resolved_careers_url=None,
                final_url=company.careers_url,
                status="SKIPPED",
                method=None,
                confidence=None,
                evidence=(
                    "Company already has "
                    "careers_url; resolver "
                    "does not overwrite."
                ),
                http_status=None,
            )

        if company.website_url is None:
            return CareersResolutionResult(
                company_id=company.id,
                company_name=company.name,
                website_url=None,
                existing_careers_url=None,
                resolved_careers_url=None,
                final_url=None,
                status="SKIPPED",
                method=None,
                confidence=None,
                evidence=(
                    "Company has no website_url."
                ),
                http_status=None,
            )

        budget = _RequestBudget(
            max_requests=(
                self.max_requests_per_company
            )
        )

        try:
            homepage = _budgeted_fetch(
                client=client,
                budget=budget,
                url=company.website_url,
            )
        except httpx.HTTPStatusError as exc:
            return _http_status_result(
                company=company,
                url=company.website_url,
                method=None,
                exc=exc,
            )
        except httpx.HTTPError as exc:
            return _error_result(
                company=company,
                final_url=company.website_url,
                error=exc,
            )

        result = self._resolve_from_homepage_link(
            company=company,
            client=client,
            budget=budget,
            homepage=homepage,
        )
        if result is not None:
            return result

        result = self._resolve_from_homepage_reference(
            company=company,
            client=client,
            budget=budget,
            homepage=homepage,
        )
        if result is not None:
            return result

        result = self._resolve_from_common_paths(
            company=company,
            client=client,
            budget=budget,
            homepage=homepage,
        )
        if result is not None:
            return result

        result = self._resolve_from_sitemaps(
            company=company,
            client=client,
            budget=budget,
            homepage=homepage,
        )
        if result is not None:
            return result

        result = self._resolve_from_subdomains(
            company=company,
            client=client,
            budget=budget,
            homepage=homepage,
        )
        if result is not None:
            return result

        return CareersResolutionResult(
            company_id=company.id,
            company_name=company.name,
            website_url=company.website_url,
            existing_careers_url=None,
            resolved_careers_url=None,
            final_url=homepage.final_url,
            status="UNRESOLVED",
            method=None,
            confidence=None,
            evidence=(
                "No high-confidence careers "
                "entry point found within "
                "bounded resolver layers."
            ),
            http_status=homepage.status_code,
        )

    def _resolve_from_homepage_link(
        self,
        *,
        company: Company,
        client: httpx.Client,
        budget: "_RequestBudget",
        homepage: PageDocument,
    ) -> CareersResolutionResult | None:
        careers_url = _discover_careers_url(
            homepage
        )

        if careers_url is None:
            return None

        return self._validate_candidate(
            company=company,
            client=client,
            budget=budget,
            homepage=homepage,
            url=careers_url,
            method="HOMEPAGE_LINK",
            source_evidence=(
                "Homepage careers anchor "
                "selected by existing "
                "careers-link discovery."
            ),
        )

    def _resolve_from_homepage_reference(
        self,
        *,
        company: Company,
        client: httpx.Client,
        budget: "_RequestBudget",
        homepage: PageDocument,
    ) -> CareersResolutionResult | None:
        for url in _homepage_reference_urls(
            homepage
        ):
            if (
                not _is_allowed_external_reference(
                    homepage=homepage,
                    url=url,
                )
                and not _same_site(
                    homepage.final_url,
                    url,
                )
            ):
                continue

            if not _looks_like_careers_url(
                url
            ):
                continue

            result = self._validate_candidate(
                company=company,
                client=client,
                budget=budget,
                homepage=homepage,
                url=url,
                method="HOMEPAGE_REFERENCE",
                source_evidence=(
                    "Homepage references a "
                    "careers-looking URL."
                ),
            )
            if result is not None:
                return result

        return None

    def _resolve_from_common_paths(
        self,
        *,
        company: Company,
        client: httpx.Client,
        budget: "_RequestBudget",
        homepage: PageDocument,
    ) -> CareersResolutionResult | None:
        for path in self.common_paths:
            if not budget.can_fetch:
                return None

            url = urljoin(
                homepage.final_url,
                path,
            )
            result = self._validate_candidate(
                company=company,
                client=client,
                budget=budget,
                homepage=homepage,
                url=url,
                method="COMMON_PATH",
                source_evidence=(
                    "Bounded first-party "
                    f"common path probe: {path}"
                ),
            )
            if result is not None:
                return result

        return None

    def _resolve_from_sitemaps(
        self,
        *,
        company: Company,
        client: httpx.Client,
        budget: "_RequestBudget",
        homepage: PageDocument,
    ) -> CareersResolutionResult | None:
        sitemap_urls = _default_sitemap_urls(
            homepage.final_url
        )
        robots_url = urljoin(
            homepage.final_url,
            "/robots.txt",
        )

        try:
            robots = _budgeted_get_text(
                client=client,
                budget=budget,
                url=robots_url,
            )
        except httpx.HTTPError:
            robots = None

        if robots is not None:
            sitemap_urls = (
                _robots_sitemap_urls(robots)
                + sitemap_urls
            )

        seen_documents: set[str] = set()
        inspected_urls = 0
        document_queue = [
            (url, 0)
            for url in _dedupe_strings(
                sitemap_urls
            )
        ]

        while (
            document_queue
            and len(seen_documents)
            < self.max_sitemap_documents
            and budget.can_fetch
        ):
            sitemap_url, depth = (
                document_queue.pop(0)
            )
            if sitemap_url in seen_documents:
                continue
            seen_documents.add(sitemap_url)

            try:
                text = _budgeted_get_text(
                    client=client,
                    budget=budget,
                    url=sitemap_url,
                )
            except httpx.HTTPError:
                continue

            parsed = _parse_sitemap(text)
            if parsed.kind == "index":
                if (
                    depth
                    >= self.max_sitemap_depth
                ):
                    continue

                for url in parsed.urls:
                    if (
                        len(seen_documents)
                        + len(document_queue)
                        >= self
                        .max_sitemap_documents
                    ):
                        break
                    document_queue.append(
                        (url, depth + 1)
                    )
                continue

            for url in parsed.urls:
                if (
                    inspected_urls
                    >= self.max_sitemap_urls
                ):
                    break
                inspected_urls += 1
                if (
                    not _same_site(
                        homepage.final_url,
                        url,
                    )
                    or not _looks_like_careers_url(
                        url
                    )
                ):
                    continue

                result = self._validate_candidate(
                    company=company,
                    client=client,
                    budget=budget,
                    homepage=homepage,
                    url=url,
                    method="SITEMAP",
                    source_evidence=(
                        "Bounded sitemap URL "
                        "matched careers terms."
                    ),
                )
                if result is not None:
                    return result

        return None

    def _resolve_from_subdomains(
        self,
        *,
        company: Company,
        client: httpx.Client,
        budget: "_RequestBudget",
        homepage: PageDocument,
    ) -> CareersResolutionResult | None:
        parsed = urlsplit(homepage.final_url)
        host = parsed.hostname
        if host is None:
            return None

        base_host = (
            host[4:]
            if host.startswith("www.")
            else host
        )

        for prefix in self.subdomain_prefixes:
            if not budget.can_fetch:
                return None

            url = (
                f"{parsed.scheme}://"
                f"{prefix}.{base_host}/"
            )
            result = self._validate_candidate(
                company=company,
                client=client,
                budget=budget,
                homepage=homepage,
                url=url,
                method="SUBDOMAIN",
                source_evidence=(
                    "Bounded first-party "
                    f"subdomain probe: {prefix}"
                ),
            )
            if result is not None:
                return result

        return None

    def _validate_candidate(
        self,
        *,
        company: Company,
        client: httpx.Client,
        budget: "_RequestBudget",
        homepage: PageDocument,
        url: str,
        method: str,
        source_evidence: str,
    ) -> CareersResolutionResult | None:
        if (
            not _same_site(homepage.final_url, url)
            and not _is_allowed_external_reference(
                homepage=homepage,
                url=url,
            )
        ):
            return None

        direct = detect_fingerprint_from_url(
            url=url,
            method=(
                AtsDetectionMethod
                .CAREERS_LINK
                .value
            ),
            confidence=0.98,
        )

        try:
            page = _budgeted_fetch(
                client=client,
                budget=budget,
                url=url,
            )
        except httpx.HTTPStatusError as exc:
            if (
                exc.response.status_code
                in BLOCKED_HTTP_STATUSES
            ):
                return _http_status_result(
                    company=company,
                    url=url,
                    method=method,
                    exc=exc,
                )
            return None
        except httpx.HTTPError:
            return None

        redirect = None
        if page.final_url != url:
            redirect = detect_fingerprint_from_url(
                url=page.final_url,
                method=(
                    AtsDetectionMethod
                    .REDIRECT
                    .value
                ),
                confidence=1.0,
            )

        fingerprints = [
            candidate
            for candidate in (
                [direct, redirect]
                + detect_fingerprints_from_page(
                    page
                )
            )
            if candidate is not None
        ]

        validation = _validate_careers_page(
            page=page,
            source_url=url,
            fingerprints=fingerprints,
        )

        if validation.confidence < 0.70:
            return None

        return CareersResolutionResult(
            company_id=company.id or 0,
            company_name=company.name,
            website_url=company.website_url,
            existing_careers_url=(
                company.careers_url
            ),
            resolved_careers_url=url,
            final_url=page.final_url,
            status="RESOLVED",
            method=method,
            confidence=validation.confidence,
            evidence=(
                f"{source_evidence} "
                f"{validation.evidence}"
            ),
            http_status=page.status_code,
        )


@dataclass(slots=True)
class _RequestBudget:
    max_requests: int
    used: int = 0

    @property
    def can_fetch(self) -> bool:
        return self.used < self.max_requests

    def consume(self) -> None:
        if not self.can_fetch:
            raise httpx.RequestError(
                "Request budget exceeded."
            )
        self.used += 1


@dataclass(frozen=True, slots=True)
class _Validation:
    confidence: float
    evidence: str


@dataclass(frozen=True, slots=True)
class _ParsedSitemap:
    kind: str
    urls: list[str]


def _budgeted_fetch(
    *,
    client: httpx.Client,
    budget: _RequestBudget,
    url: str,
) -> PageDocument:
    budget.consume()
    return _fetch_page(
        client=client,
        url=url,
    )


def _budgeted_get_text(
    *,
    client: httpx.Client,
    budget: _RequestBudget,
    url: str,
) -> str:
    budget.consume()
    response = client.get(url)
    response.raise_for_status()
    return response.text[:200_000]


def _validate_careers_page(
    *,
    page: PageDocument,
    source_url: str,
    fingerprints: list[object],
) -> _Validation:
    score = 0
    evidence: list[str] = []

    if fingerprints:
        score += 70
        provider = getattr(
            fingerprints[0],
            "provider_family",
            "ATS",
        )
        evidence.append(
            f"ATS/recruiting fingerprint: "
            f"{provider}."
        )

    if _looks_like_careers_url(
        source_url
    ) or _looks_like_careers_url(
        page.final_url
    ):
        score += 20
        evidence.append(
            "URL/path contains careers terms."
        )

    focused_text = _focused_page_text(
        page.html
    )
    if any(
        term in focused_text
        for term in JOB_PAGE_TERMS
    ):
        score += 30
        evidence.append(
            "Title/header/body contains "
            "careers terminology."
        )

    if any(
        marker in focused_text
        for marker in JOB_LISTING_PATTERNS
    ):
        score += 25
        evidence.append(
            "Page contains job-listing or "
            "application UI markers."
        )

    if any(
        term in _url_text(href)
        or term in text.casefold()
        for href, text in page.anchors
        for term in JOB_PAGE_TERMS
    ):
        score += 15
        evidence.append(
            "Page links include careers/job "
            "listing terms."
        )

    if _looks_negative(
        source_url=source_url,
        page=page,
    ) and not fingerprints:
        score -= 35
        evidence.append(
            "Negative corporate/legal/login "
            "signals reduced confidence."
        )

    confidence = min(
        0.99,
        max(
            0.0,
            score / 100,
        ),
    )

    return _Validation(
        confidence=confidence,
        evidence=(
            " ".join(evidence)
            if evidence
            else "No positive careers evidence."
        ),
    )


def _focused_page_text(html: str) -> str:
    text = re.sub(
        r"<script\b[^>]*>.*?</script>",
        " ",
        html,
        flags=(
            re.IGNORECASE
            | re.DOTALL
        ),
    )
    text = re.sub(
        r"<style\b[^>]*>.*?</style>",
        " ",
        text,
        flags=(
            re.IGNORECASE
            | re.DOTALL
        ),
    )
    text = re.sub(
        r"<[^>]+>",
        " ",
        text,
    )
    return re.sub(
        r"\s+",
        " ",
        text,
    ).casefold()


def _homepage_reference_urls(
    page: PageDocument,
) -> list[str]:
    urls: list[str] = []
    urls.extend(
        href
        for href, _text in page.anchors
    )
    urls.extend(
        url
        for _resource_type, url in page.resources
    )
    urls.extend(
        match.group(0).rstrip(
            ".,);]}\"'\\"
        )
        for match in RAW_URL_PATTERN.finditer(
            page.html.replace("\\/", "/")
        )
    )
    return _dedupe_strings(urls)


def _is_allowed_external_reference(
    *,
    homepage: PageDocument,
    url: str,
) -> bool:
    if _same_site(homepage.final_url, url):
        return True

    if (
        url
        not in _homepage_reference_urls(homepage)
    ):
        return False

    return (
        detect_fingerprint_from_url(
            url=url,
            method=(
                AtsDetectionMethod
                .HTML_LINK
                .value
            ),
            confidence=0.98,
        )
        is not None
    )


def _looks_like_careers_url(
    url: str,
) -> bool:
    lowered = _url_text(url)
    return any(
        term in lowered
        for term in CAREERS_URL_TERMS
    ) or any(
        term.replace(" ", "-")
        in lowered
        for term in CAREERS_TERMS
    )


def _url_text(url: str) -> str:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return url.casefold()
    return (
        f"{parsed.hostname or ''} "
        f"{parsed.path} "
        f"{parsed.query}"
    ).casefold()


def _looks_negative(
    *,
    source_url: str,
    page: PageDocument,
) -> bool:
    text = (
        _url_text(source_url)
        + " "
        + _focused_page_text(page.html)
    )
    return any(
        term in text
        for term in NEGATIVE_TERMS
    )


def _same_site(
    left: str,
    right: str,
) -> bool:
    try:
        left_host = (
            urlsplit(left).hostname
            or ""
        ).casefold()
        right_host = (
            urlsplit(right).hostname
            or ""
        ).casefold()
    except ValueError:
        return False

    left_host = left_host.removeprefix(
        "www."
    )
    right_host = right_host.removeprefix(
        "www."
    )
    return (
        left_host == right_host
        or left_host.endswith(
            "." + right_host
        )
        or right_host.endswith(
            "." + left_host
        )
    )


def _default_sitemap_urls(
    website_url: str,
) -> list[str]:
    return [
        urljoin(website_url, "/sitemap.xml"),
    ]


def _robots_sitemap_urls(
    robots_text: str,
) -> list[str]:
    urls: list[str] = []
    for line in robots_text.splitlines():
        if not line.casefold().startswith(
            "sitemap:"
        ):
            continue
        url = line.split(
            ":",
            1,
        )[1].strip()
        if url:
            urls.append(url)
    return urls


def _parse_sitemap(
    text: str,
) -> _ParsedSitemap:
    try:
        root = ElementTree.fromstring(
            text.encode("utf-8")
        )
    except ElementTree.ParseError:
        return _ParsedSitemap(
            kind="urlset",
            urls=[],
        )

    tag = root.tag.rsplit(
        "}",
        1,
    )[-1]
    locs = [
        element.text.strip()
        for element in root.iter()
        if element.tag.rsplit(
            "}",
            1,
        )[-1] == "loc"
        and element.text
        and element.text.strip()
    ]

    return _ParsedSitemap(
        kind=(
            "index"
            if tag == "sitemapindex"
            else "urlset"
        ),
        urls=locs,
    )


def _http_status_result(
    *,
    company: Company,
    url: str,
    method: str | None,
    exc: httpx.HTTPStatusError,
) -> CareersResolutionResult:
    status_code = exc.response.status_code
    return CareersResolutionResult(
        company_id=company.id or 0,
        company_name=company.name,
        website_url=company.website_url,
        existing_careers_url=(
            company.careers_url
        ),
        resolved_careers_url=None,
        final_url=str(exc.response.url),
        status=(
            "BLOCKED"
            if status_code
            in BLOCKED_HTTP_STATUSES
            else "ERROR"
        ),
        method=method,
        confidence=None,
        evidence=None,
        http_status=status_code,
        error_type=type(exc).__name__,
        error_message=str(exc),
    )


def _error_result(
    *,
    company: Company,
    final_url: str | None,
    error: Exception,
) -> CareersResolutionResult:
    return CareersResolutionResult(
        company_id=company.id or 0,
        company_name=company.name,
        website_url=company.website_url,
        existing_careers_url=(
            company.careers_url
        ),
        resolved_careers_url=None,
        final_url=final_url,
        status="ERROR",
        method=None,
        confidence=None,
        evidence=None,
        http_status=None,
        error_type=type(error).__name__,
        error_message=str(error),
    )


def _add_to_summary(
    *,
    summary: CareersResolutionSummary,
    result: CareersResolutionResult,
) -> None:
    summary.results.append(result)
    if result.status == "RESOLVED":
        summary.resolved += 1
        if result.method:
            summary.by_method[
                result.method
            ] += 1
    elif result.status == "UNRESOLVED":
        summary.unresolved += 1
    elif result.status == "BLOCKED":
        summary.blocked += 1
    elif result.status == "ERROR":
        summary.errors += 1
    elif result.status == "SKIPPED":
        summary.skipped += 1


def _dedupe_strings(
    values: list[str],
) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
