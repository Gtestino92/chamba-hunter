from collections import Counter
from dataclasses import dataclass, field
from html import unescape
from urllib.parse import urlsplit

import httpx

from chamba_hunter.domain.ats_fingerprints import (
    AtsFingerprint,
)
from chamba_hunter.domain.enums import (
    AtsDetectionMethod,
    AtsFingerprintStatus,
    AtsProvider,
    AtsScanStatus,
    AtsSupportStatus,
    RunStatus,
)
from chamba_hunter.domain.models import Company
from chamba_hunter.domain.tracing import (
    CompanyScan,
    Run,
    RunStep,
)
from chamba_hunter.repositories.ats_fingerprint_repository import (
    AtsFingerprintRepository,
)
from chamba_hunter.repositories.tracing_repository import (
    TracingRepository,
)
from chamba_hunter.services.careers_ats_detection_service import (
    BLOCKED_HTTP_STATUSES,
    RAW_URL_PATTERN,
    PageDocument,
    _detect_from_page,
    _detect_from_url,
    _discover_careers_url,
    _fetch_page,
)
from chamba_hunter.sources.hibob import (
    canonical_hibob_board_url,
    hibob_tenant_from_url,
)


SUPPORTED_PROVIDER_FAMILIES = frozenset(
    provider.value
    for provider in AtsProvider
    if provider != AtsProvider.CUSTOM
)

UNSUPPORTED_PROVIDER_FAMILIES = frozenset(
    {
        "SUCCESSFACTORS",
        "WORKDAY",
        "AVATURE",
        "ORACLE_TALEO",
        "GUPY",
        "PANDAPE",
    }
)


@dataclass(frozen=True, slots=True)
class AtsFingerprintCandidate:
    provider_family: str
    support_status: AtsSupportStatus
    confidence: float
    detection_method: str
    evidence: str
    source_url: str


@dataclass(frozen=True, slots=True)
class AtsFingerprintResult:
    company_id: int
    company_name: str
    country: str | None
    input_url: str | None
    final_url: str | None
    fingerprint_status: AtsFingerprintStatus
    support_status: AtsSupportStatus
    provider_family: str | None = None
    confidence: float | None = None
    detection_method: str | None = None
    evidence: str | None = None
    http_status: int | None = None
    error_type: str | None = None
    error_message: str | None = None


@dataclass(slots=True)
class LatamEnterpriseAtsFingerprintSummary:
    run_id: int
    selected: int

    scanned: int = 0
    detected: int = 0
    unknown: int = 0
    blocked: int = 0
    errors: int = 0
    no_careers_url: int = 0
    insufficient_evidence: int = 0
    skipped: int = 0

    by_provider_family: Counter[str] = field(
        default_factory=Counter
    )
    by_support_status: Counter[str] = field(
        default_factory=Counter
    )
    by_country: Counter[str] = field(
        default_factory=Counter
    )
    results: list[
        AtsFingerprintResult
    ] = field(default_factory=list)


class LatamEnterpriseAtsFingerprintingService:
    def __init__(
        self,
        *,
        tracing_repository: TracingRepository,
        fingerprint_repository: (
            AtsFingerprintRepository
        ),
        timeout_seconds: float = 20.0,
    ) -> None:
        self.tracing_repository = (
            tracing_repository
        )
        self.fingerprint_repository = (
            fingerprint_repository
        )
        self.timeout_seconds = (
            timeout_seconds
        )

    def run(
        self,
        companies: list[Company],
        *,
        client: httpx.Client | None = None,
    ) -> LatamEnterpriseAtsFingerprintSummary:
        run = self.tracing_repository.add_run(
            Run(
                command=(
                    "fingerprint_latam_enterprise_ats"
                )
            )
        )

        if run.id is None:
            raise RuntimeError(
                "Run must have an id."
            )

        step = self.tracing_repository.add_run_step(
            RunStep(
                run_id=run.id,
                step_name=(
                    "latam_enterprise_ats_fingerprinting"
                ),
                items_total=len(companies),
            )
        )

        if step.id is None:
            raise RuntimeError(
                "Run step must have an id."
            )

        summary = (
            LatamEnterpriseAtsFingerprintSummary(
                run_id=run.id,
                selected=len(companies),
            )
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
                    client=owned_client,
                    run_step_id=step.id,
                    summary=summary,
                )
        else:
            self._run_with_client(
                companies=companies,
                client=client,
                run_step_id=step.id,
                summary=summary,
            )

        status = _run_status(
            scanned=summary.scanned,
            errors=summary.errors,
        )

        self.tracing_repository.finish_run_step(
            run_step_id=step.id,
            status=status,
            items_success=(
                summary.scanned
                - summary.errors
            ),
            items_failed=summary.errors,
            items_skipped=summary.skipped,
            metadata={
                "detected": summary.detected,
                "unknown": summary.unknown,
                "blocked": summary.blocked,
                "no_careers_url": (
                    summary.no_careers_url
                ),
                "insufficient_evidence": (
                    summary
                    .insufficient_evidence
                ),
                "by_provider_family": dict(
                    summary.by_provider_family
                ),
                "by_support_status": dict(
                    summary.by_support_status
                ),
                "by_country": dict(
                    summary.by_country
                ),
            },
        )

        self.tracing_repository.finish_run(
            run_id=run.id,
            status=status,
        )

        return summary

    def _run_with_client(
        self,
        *,
        companies: list[Company],
        client: httpx.Client,
        run_step_id: int,
        summary: LatamEnterpriseAtsFingerprintSummary,
    ) -> None:
        for company in companies:
            if company.id is None:
                summary.skipped += 1
                continue

            result = self._scan_one(
                client=client,
                run_step_id=run_step_id,
                company=company,
            )

            _add_to_summary(
                summary=summary,
                result=result,
            )

    def _scan_one(
        self,
        *,
        client: httpx.Client,
        run_step_id: int,
        company: Company,
    ) -> AtsFingerprintResult:
        if company.id is None:
            raise ValueError(
                "Company must have an id."
            )

        scan = self.tracing_repository.add_company_scan(
            CompanyScan(
                run_step_id=run_step_id,
                company_id=company.id,
                homepage_url=(
                    company.careers_url
                    or company.website_url
                ),
            )
        )

        if scan.id is None:
            raise RuntimeError(
                "Company scan must have an id."
            )

        result = fingerprint_company(
            client=client,
            company=company,
        )

        self.fingerprint_repository.add(
            _fingerprint_from_result(
                result=result,
                run_step_id=run_step_id,
                company_scan_id=scan.id,
            )
        )

        self.tracing_repository.finish_company_scan(
            company_scan_id=scan.id,
            status=(
                RunStatus.FAILED
                if result.fingerprint_status
                == AtsFingerprintStatus.ERROR
                else RunStatus.SUCCESS
            ),
            homepage_http_status=(
                result.http_status
            ),
            careers_url_found=(
                result.final_url
            ),
            careers_discovery_method=(
                result.detection_method
            ),
            ats_status=(
                _scan_status(
                    result.fingerprint_status
                )
            ),
            error_type=result.error_type,
            error_message=result.error_message,
        )

        return result


def fingerprint_company(
    *,
    client: httpx.Client,
    company: Company,
) -> AtsFingerprintResult:
    if company.id is None:
        raise ValueError(
            "Company must have an id."
        )

    input_url = (
        company.careers_url
        or company.website_url
    )

    if input_url is None:
        return AtsFingerprintResult(
            company_id=company.id,
            company_name=company.name,
            country=company.country,
            input_url=None,
            final_url=None,
            fingerprint_status=(
                AtsFingerprintStatus
                .NO_CAREERS_URL
            ),
            support_status=(
                AtsSupportStatus.UNKNOWN
            ),
            evidence=(
                "Company has neither "
                "careers_url nor website_url."
            ),
        )

    direct = detect_fingerprint_from_url(
        url=input_url,
        method=(
            AtsDetectionMethod
            .CAREERS_LINK
            .value
        ),
        confidence=0.99,
    )

    page: PageDocument | None = None
    http_status: int | None = None
    final_url: str | None = None

    try:
        page = _fetch_page(
            client=client,
            url=input_url,
        )
        http_status = page.status_code
        final_url = page.final_url

    except httpx.HTTPStatusError as exc:
        http_status = exc.response.status_code
        final_url = str(exc.response.url)

        if direct is not None:
            return _detected_result(
                company=company,
                input_url=input_url,
                final_url=final_url,
                http_status=http_status,
                candidate=direct,
                evidence_suffix=(
                    "Fetch failed after "
                    "direct URL evidence."
                ),
            )

        if http_status in BLOCKED_HTTP_STATUSES:
            return _status_result(
                company=company,
                input_url=input_url,
                final_url=final_url,
                status=(
                    AtsFingerprintStatus
                    .BLOCKED
                ),
                http_status=http_status,
                error_type=(
                    type(exc).__name__
                ),
                error_message=str(exc),
            )

        return _status_result(
            company=company,
            input_url=input_url,
            final_url=final_url,
            status=AtsFingerprintStatus.ERROR,
            http_status=http_status,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )

    except httpx.HTTPError as exc:
        if direct is not None:
            return _detected_result(
                company=company,
                input_url=input_url,
                final_url=input_url,
                http_status=None,
                candidate=direct,
                evidence_suffix=(
                    "Fetch errored after "
                    "direct URL evidence."
                ),
            )

        return _status_result(
            company=company,
            input_url=input_url,
            final_url=input_url,
            status=AtsFingerprintStatus.ERROR,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )

    if page is None:
        return _status_result(
            company=company,
            input_url=input_url,
            final_url=input_url,
            status=AtsFingerprintStatus.ERROR,
            error_type="RuntimeError",
            error_message="No page was fetched.",
        )

    candidates: list[
        AtsFingerprintCandidate
    ] = []

    if direct is not None:
        candidates.append(direct)

    if page.final_url != input_url:
        redirect = detect_fingerprint_from_url(
            url=page.final_url,
            method=(
                AtsDetectionMethod
                .REDIRECT
                .value
            ),
            confidence=1.0,
        )
        if redirect is not None:
            candidates.append(redirect)

    candidates.extend(
        detect_fingerprints_from_page(page)
    )

    if (
        company.careers_url is None
        and company.website_url is not None
    ):
        careers_url = _discover_careers_url(
            page
        )

        if careers_url is not None:
            try:
                careers_page = _fetch_page(
                    client=client,
                    url=careers_url,
                )
                http_status = (
                    careers_page.status_code
                )
                final_url = (
                    careers_page.final_url
                )

                careers_direct = (
                    detect_fingerprint_from_url(
                        url=careers_url,
                        method=(
                            AtsDetectionMethod
                            .HOMEPAGE_LINK
                            .value
                        ),
                        confidence=0.97,
                    )
                )
                if careers_direct is not None:
                    candidates.append(
                        careers_direct
                    )

                if (
                    careers_page.final_url
                    != careers_url
                ):
                    careers_redirect = (
                        detect_fingerprint_from_url(
                            url=(
                                careers_page
                                .final_url
                            ),
                            method=(
                                AtsDetectionMethod
                                .REDIRECT
                                .value
                            ),
                            confidence=1.0,
                        )
                    )
                    if (
                        careers_redirect
                        is not None
                    ):
                        candidates.append(
                            careers_redirect
                        )

                candidates.extend(
                    detect_fingerprints_from_page(
                        careers_page
                    )
                )

            except httpx.HTTPStatusError as exc:
                http_status = (
                    exc.response.status_code
                )
                final_url = str(
                    exc.response.url
                )

                if (
                    http_status
                    in BLOCKED_HTTP_STATUSES
                    and not candidates
                ):
                    return _status_result(
                        company=company,
                        input_url=input_url,
                        final_url=final_url,
                        status=(
                            AtsFingerprintStatus
                            .BLOCKED
                        ),
                        http_status=http_status,
                        error_type=(
                            type(exc).__name__
                        ),
                        error_message=str(exc),
                    )

            except httpx.HTTPError as exc:
                if not candidates:
                    return _status_result(
                        company=company,
                        input_url=input_url,
                        final_url=careers_url,
                        status=(
                            AtsFingerprintStatus
                            .ERROR
                        ),
                        error_type=(
                            type(exc).__name__
                        ),
                        error_message=str(exc),
                    )

        elif not candidates:
            return _status_result(
                company=company,
                input_url=input_url,
                final_url=page.final_url,
                status=(
                    AtsFingerprintStatus
                    .INSUFFICIENT_EVIDENCE
                ),
                http_status=http_status,
                evidence=(
                    "Website fetched but no "
                    "careers URL or ATS "
                    "fingerprint was found."
                ),
            )

    selected = _select_candidate(
        candidates
    )

    if selected is not None:
        return _detected_result(
            company=company,
            input_url=input_url,
            final_url=(
                final_url
                or selected.source_url
            ),
            http_status=http_status,
            candidate=selected,
        )

    return _status_result(
        company=company,
        input_url=input_url,
        final_url=page.final_url,
        status=AtsFingerprintStatus.UNKNOWN,
        http_status=http_status,
        evidence=(
            "Page fetched but no supported "
            "or known unsupported ATS "
            "fingerprint was found."
        ),
    )


def detect_fingerprints_from_page(
    page: PageDocument,
) -> list[AtsFingerprintCandidate]:
    candidates: list[
        AtsFingerprintCandidate
    ] = []

    for candidate in _detect_from_page(page):
        candidates.append(
            _from_supported_candidate(
                candidate
            )
        )

    urls: list[
        tuple[str, str]
    ] = []

    urls.extend(
        ("HTML_LINK", href)
        for href, _text in page.anchors
    )
    urls.extend(
        (resource_type.upper(), url)
        for resource_type, url
        in page.resources
    )

    raw_html = (
        unescape(page.html)
        .replace("\\/", "/")
    )

    urls.extend(
        ("OTHER", match.group(0).rstrip(
            ".,);]}\"'"
        ))
        for match in RAW_URL_PATTERN.finditer(
            raw_html
        )
    )

    for method, url in urls:
        candidate = detect_fingerprint_from_url(
            url=url,
            method=method,
            confidence=(
                0.85
                if method == "OTHER"
                else 0.96
            ),
        )
        if candidate is not None:
            candidates.append(candidate)

    candidates.extend(
        _detect_from_html_markers(
            page=page,
            raw_html=raw_html,
        )
    )

    return _deduplicate_candidates(
        candidates
    )


def detect_fingerprint_from_url(
    *,
    url: str,
    method: str,
    confidence: float,
) -> AtsFingerprintCandidate | None:
    supported = _detect_from_url(
        url=url,
        method=(
            AtsDetectionMethod(method)
            if method
            in AtsDetectionMethod
            ._value2member_map_
            else AtsDetectionMethod.OTHER
        ),
        confidence=confidence,
    )

    if supported is not None:
        return _from_supported_candidate(
            supported
        )

    hibob_tenant = hibob_tenant_from_url(
        url
    )

    if hibob_tenant is not None:
        return AtsFingerprintCandidate(
            provider_family=(
                AtsProvider.HIBOB.value
            ),
            support_status=(
                AtsSupportStatus.SUPPORTED
            ),
            confidence=confidence,
            detection_method=method,
            evidence="HiBob public careers host",
            source_url=canonical_hibob_board_url(
                hibob_tenant
            ),
        )

    unsupported = (
        _unsupported_from_url(
            url=url,
            method=method,
            confidence=confidence,
        )
    )

    if unsupported is not None:
        return unsupported

    return None


def _unsupported_from_url(
    *,
    url: str,
    method: str,
    confidence: float,
) -> AtsFingerprintCandidate | None:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None

    if parsed.scheme not in {
        "http",
        "https",
    }:
        return None

    host = (
        parsed.hostname
        or ""
    ).casefold()
    path = parsed.path.casefold()

    if _is_successfactors_url(
        host=host,
        path=path,
    ):
        return _unsupported_candidate(
            family="SUCCESSFACTORS",
            method=method,
            confidence=confidence,
            source_url=url,
            evidence=(
                "SAP SuccessFactors "
                f"URL host/path: {host}{path}"
            ),
        )

    if host.endswith(
        ".myworkdayjobs.com"
    ):
        return _unsupported_candidate(
            family="WORKDAY",
            method=method,
            confidence=confidence,
            source_url=url,
            evidence=(
                "Workday careers host: "
                f"{host}"
            ),
        )

    if (
        host == "avature.net"
        or host.endswith(
            ".avature.net"
        )
    ):
        return _unsupported_candidate(
            family="AVATURE",
            method=method,
            confidence=confidence,
            source_url=url,
            evidence=(
                "Avature host: "
                f"{host}"
            ),
        )

    if (
        host.endswith(".taleo.net")
        or (
            host.endswith(
                ".oraclecloud.com"
            )
            and (
                "/hcmui/candidateexperience"
                in path
                or "/recruiting/"
                in path
            )
        )
    ):
        return _unsupported_candidate(
            family="ORACLE_TALEO",
            method=method,
            confidence=confidence,
            source_url=url,
            evidence=(
                "Oracle Recruiting/Taleo "
                f"URL host/path: {host}{path}"
            ),
        )

    if (
        host == "gupy.io"
        or host.endswith(".gupy.io")
    ):
        return _unsupported_candidate(
            family="GUPY",
            method=method,
            confidence=confidence,
            source_url=url,
            evidence=f"Gupy host: {host}",
        )

    if _is_pandape_host(host):
        return _unsupported_candidate(
            family="PANDAPE",
            method=method,
            confidence=confidence,
            source_url=url,
            evidence=f"Pandapé host: {host}",
        )

    return None


def _detect_from_html_markers(
    *,
    page: PageDocument,
    raw_html: str,
) -> list[AtsFingerprintCandidate]:
    lower_html = raw_html.casefold()
    candidates: list[
        AtsFingerprintCandidate
    ] = []

    if (
        "careersitebuilder"
        in lower_html
        or "rmkcdn.successfactors.com"
        in lower_html
        or "successfactors recruiting"
        in lower_html
    ):
        candidates.append(
            _unsupported_candidate(
                family="SUCCESSFACTORS",
                method=(
                    AtsDetectionMethod
                    .OTHER
                    .value
                ),
                confidence=0.82,
                source_url=page.final_url,
                evidence=(
                    "HTML contains "
                    "SuccessFactors "
                    "structural marker"
                ),
            )
        )

    if (
        "myworkdayjobs.com"
        in lower_html
    ):
        candidates.append(
            _unsupported_candidate(
                family="WORKDAY",
                method=(
                    AtsDetectionMethod
                    .OTHER
                    .value
                ),
                confidence=0.84,
                source_url=page.final_url,
                evidence=(
                    "HTML references "
                    "myworkdayjobs.com"
                ),
            )
        )

    return candidates


def _is_successfactors_url(
    *,
    host: str,
    path: str,
) -> bool:
    if (
        host == "sapsf.com"
        or host.endswith(".sapsf.com")
    ):
        return True

    if (
        "successfactors.com" in host
        and (
            "/career"
            in path
            or "/sfcareer"
            in path
            or "/careersection"
            in path
        )
    ):
        return True

    return False


def _is_pandape_host(
    host: str,
) -> bool:
    labels = host.split(".")
    return any(
        label == "pandape"
        for label in labels
    )


def _unsupported_candidate(
    *,
    family: str,
    method: str,
    confidence: float,
    source_url: str,
    evidence: str,
) -> AtsFingerprintCandidate:
    return AtsFingerprintCandidate(
        provider_family=family,
        support_status=(
            AtsSupportStatus.UNSUPPORTED
        ),
        confidence=confidence,
        detection_method=method,
        evidence=evidence,
        source_url=source_url,
    )


def _from_supported_candidate(
    candidate,
) -> AtsFingerprintCandidate:
    return AtsFingerprintCandidate(
        provider_family=(
            candidate.provider.value
        ),
        support_status=(
            AtsSupportStatus.SUPPORTED
        ),
        confidence=candidate.confidence,
        detection_method=(
            candidate.method.value
        ),
        evidence=candidate.evidence or (
            f"{candidate.provider.value} "
            "fingerprint"
        ),
        source_url=(
            candidate.board_url
            or candidate.source_url
        ),
    )


def _select_candidate(
    candidates: list[
        AtsFingerprintCandidate
    ],
) -> AtsFingerprintCandidate | None:
    if not candidates:
        return None

    return sorted(
        candidates,
        key=lambda item: (
            item.confidence,
            (
                1
                if item.support_status
                == AtsSupportStatus.SUPPORTED
                else 0
            ),
            item.provider_family,
        ),
        reverse=True,
    )[0]


def _deduplicate_candidates(
    candidates: list[
        AtsFingerprintCandidate
    ],
) -> list[AtsFingerprintCandidate]:
    by_key: dict[
        tuple[str, str],
        AtsFingerprintCandidate,
    ] = {}

    for candidate in candidates:
        key = (
            candidate.provider_family,
            candidate.source_url,
        )
        existing = by_key.get(key)

        if (
            existing is None
            or candidate.confidence
            > existing.confidence
        ):
            by_key[key] = candidate

    return list(
        by_key.values()
    )


def _detected_result(
    *,
    company: Company,
    input_url: str,
    final_url: str | None,
    http_status: int | None,
    candidate: AtsFingerprintCandidate,
    evidence_suffix: str | None = None,
) -> AtsFingerprintResult:
    evidence = candidate.evidence

    if evidence_suffix:
        evidence = (
            f"{evidence}; {evidence_suffix}"
        )

    return AtsFingerprintResult(
        company_id=company.id or 0,
        company_name=company.name,
        country=company.country,
        input_url=input_url,
        final_url=final_url,
        fingerprint_status=(
            AtsFingerprintStatus.DETECTED
        ),
        provider_family=(
            candidate.provider_family
        ),
        support_status=(
            candidate.support_status
        ),
        confidence=candidate.confidence,
        detection_method=(
            candidate.detection_method
        ),
        evidence=evidence,
        http_status=http_status,
    )


def _status_result(
    *,
    company: Company,
    input_url: str | None,
    final_url: str | None,
    status: AtsFingerprintStatus,
    http_status: int | None = None,
    evidence: str | None = None,
    error_type: str | None = None,
    error_message: str | None = None,
) -> AtsFingerprintResult:
    return AtsFingerprintResult(
        company_id=company.id or 0,
        company_name=company.name,
        country=company.country,
        input_url=input_url,
        final_url=final_url,
        fingerprint_status=status,
        support_status=AtsSupportStatus.UNKNOWN,
        evidence=evidence,
        http_status=http_status,
        error_type=error_type,
        error_message=error_message,
    )


def _fingerprint_from_result(
    *,
    result: AtsFingerprintResult,
    run_step_id: int,
    company_scan_id: int,
) -> AtsFingerprint:
    return AtsFingerprint(
        run_step_id=run_step_id,
        company_scan_id=company_scan_id,
        company_id=result.company_id,
        input_url=result.input_url,
        final_url=result.final_url,
        fingerprint_status=(
            result.fingerprint_status
        ),
        provider_family=(
            result.provider_family
        ),
        support_status=(
            result.support_status
        ),
        confidence=result.confidence,
        detection_method=(
            result.detection_method
        ),
        evidence=result.evidence,
        http_status=result.http_status,
        error_type=result.error_type,
        error_message=result.error_message,
        metadata={
            "company_name": (
                result.company_name
            ),
            "country": result.country,
        },
    )


def _scan_status(
    status: AtsFingerprintStatus,
) -> AtsScanStatus:
    if status == AtsFingerprintStatus.DETECTED:
        return AtsScanStatus.DETECTED

    if status == AtsFingerprintStatus.BLOCKED:
        return AtsScanStatus.BLOCKED

    if status == AtsFingerprintStatus.ERROR:
        return AtsScanStatus.ERROR

    return AtsScanStatus.NOT_DETECTED


def _add_to_summary(
    *,
    summary: LatamEnterpriseAtsFingerprintSummary,
    result: AtsFingerprintResult,
) -> None:
    summary.scanned += 1
    summary.results.append(result)

    country = result.country or "UNKNOWN"
    summary.by_country[country] += 1
    summary.by_support_status[
        result.support_status.value
    ] += 1

    if result.provider_family is not None:
        summary.by_provider_family[
            result.provider_family
        ] += 1

    if (
        result.fingerprint_status
        == AtsFingerprintStatus.DETECTED
    ):
        summary.detected += 1
    elif (
        result.fingerprint_status
        == AtsFingerprintStatus.BLOCKED
    ):
        summary.blocked += 1
    elif (
        result.fingerprint_status
        == AtsFingerprintStatus.ERROR
    ):
        summary.errors += 1
    elif (
        result.fingerprint_status
        == AtsFingerprintStatus.NO_CAREERS_URL
    ):
        summary.no_careers_url += 1
    elif (
        result.fingerprint_status
        == (
            AtsFingerprintStatus
            .INSUFFICIENT_EVIDENCE
        )
    ):
        summary.insufficient_evidence += 1
    else:
        summary.unknown += 1


def _run_status(
    *,
    scanned: int,
    errors: int,
) -> RunStatus:
    if errors == 0:
        return RunStatus.SUCCESS

    if scanned > errors:
        return RunStatus.PARTIAL

    return RunStatus.FAILED
