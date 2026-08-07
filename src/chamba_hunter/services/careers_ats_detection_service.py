from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser
import re
import unicodedata
from urllib.parse import (
    parse_qs,
    urljoin,
    urlsplit,
)

import httpx

from chamba_hunter.domain.enums import (
    AtsDetectionMethod,
    AtsProvider,
    AtsScanStatus,
    RunStatus,
)
from chamba_hunter.domain.models import (
    Company,
    CompanyAts,
)
from chamba_hunter.domain.tracing import (
    AtsDetection,
    CompanyScan,
    Run,
    RunStep,
)
from chamba_hunter.repositories.company_ats_repository import (
    CompanyAtsRepository,
)
from chamba_hunter.repositories.company_repository import (
    CompanyRepository,
)
from chamba_hunter.repositories.tracing_repository import (
    TracingRepository,
)


MAX_HTML_CHARS = 2_000_000

BLOCKED_HTTP_STATUSES = {
    401,
    403,
    429,
}

RAW_URL_PATTERN = re.compile(
    r"https?://[^\s\"'<>]+",
    re.IGNORECASE,
)

CAREERS_TERMS = (
    "career",
    "careers",
    "job",
    "jobs",
    "open positions",
    "open roles",
    "openings",
    "join us",
    "join our team",
    "work with us",
    "work at",
    "talent",
    "vacante",
    "vacantes",
    "empleo",
    "empleos",
    "trabaja con nosotros",
    "trabaja en",
    "unete",
)

PROBE_ORDER = (
    AtsProvider.GREENHOUSE,
    AtsProvider.ASHBY,
    AtsProvider.LEVER,
    AtsProvider.SMARTRECRUITERS,
    AtsProvider.WORKABLE,
    AtsProvider.BAMBOOHR,
)


@dataclass(frozen=True, slots=True)
class AtsCandidate:
    provider: AtsProvider
    method: AtsDetectionMethod
    confidence: float

    source_url: str
    evidence: str

    external_identifier: str | None = None
    board_url: str | None = None


@dataclass(frozen=True, slots=True)
class PageDocument:
    requested_url: str
    final_url: str
    status_code: int
    html: str

    anchors: list[
        tuple[str, str]
    ]

    resources: list[
        tuple[str, str]
    ]


@dataclass(frozen=True, slots=True)
class CompanyAtsScanResult:
    company_name: str
    careers_url: str | None
    ats_status: AtsScanStatus

    provider: AtsProvider | None = None
    external_identifier: str | None = None
    method: AtsDetectionMethod | None = None
    confidence: float | None = None

    warning: str | None = None
    error: str | None = None


@dataclass(slots=True)
class CareersAtsDetectionSummary:
    run_id: int

    processed: int = 0
    detected: int = 0
    not_detected: int = 0
    blocked: int = 0
    failed: int = 0
    skipped: int = 0

    results: list[
        CompanyAtsScanResult
    ] = field(
        default_factory=list
    )


@dataclass(frozen=True, slots=True)
class _ScanOutcome:
    careers_url: str | None
    careers_discovery_method: str | None
    homepage_http_status: int | None

    candidates: list[AtsCandidate]

    warning_type: str | None = None
    warning_message: str | None = None


class CareersAtsDetectionService:
    def __init__(
        self,
        company_repository: CompanyRepository,
        tracing_repository: TracingRepository,
        company_ats_repository: CompanyAtsRepository,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.company_repository = (
            company_repository
        )

        self.tracing_repository = (
            tracing_repository
        )

        self.company_ats_repository = (
            company_ats_repository
        )

        self.timeout_seconds = (
            timeout_seconds
        )

    def run(
        self,
        companies: list[Company],
    ) -> CareersAtsDetectionSummary:
        run = (
            self.tracing_repository
            .add_run(
                Run(
                    command=(
                        "detect_careers_ats"
                    )
                )
            )
        )

        if run.id is None:
            raise RuntimeError(
                "Run must have an id."
            )

        step = (
            self.tracing_repository
            .add_run_step(
                RunStep(
                    run_id=run.id,
                    step_name=(
                        "careers_ats_detection"
                    ),
                    items_total=len(
                        companies
                    ),
                )
            )
        )

        if step.id is None:
            raise RuntimeError(
                "Run step must have an id."
            )

        summary = (
            CareersAtsDetectionSummary(
                run_id=run.id
            )
        )

        with httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "chamba-hunter/0.1"
                )
            },
        ) as client:
            for company in companies:
                if company.id is None:
                    summary.skipped += 1
                    continue

                self._scan_one(
                    client=client,
                    run_step_id=step.id,
                    company=company,
                    summary=summary,
                )

        status = _run_status(
            processed=summary.processed,
            failed=summary.failed,
        )

        (
            self.tracing_repository
            .finish_run_step(
                run_step_id=step.id,
                status=status,
                items_success=(
                    summary.processed
                    - summary.failed
                ),
                items_failed=(
                    summary.failed
                ),
                items_skipped=(
                    summary.skipped
                ),
                metadata={
                    "detected": (
                        summary.detected
                    ),
                    "not_detected": (
                        summary.not_detected
                    ),
                    "blocked": (
                        summary.blocked
                    ),
                },
            )
        )

        self.tracing_repository.finish_run(
            run_id=run.id,
            status=status,
        )

        return summary

    def _scan_one(
        self,
        client: httpx.Client,
        run_step_id: int,
        company: Company,
        summary: CareersAtsDetectionSummary,
    ) -> None:
        if company.id is None:
            summary.skipped += 1
            return

        scan = (
            self.tracing_repository
            .add_company_scan(
                CompanyScan(
                    run_step_id=run_step_id,
                    company_id=company.id,
                    homepage_url=(
                        company.website_url
                    ),
                )
            )
        )

        if scan.id is None:
            raise RuntimeError(
                "Company scan must have "
                "an id."
            )

        summary.processed += 1

        try:
            outcome = self._scan_company(
                client=client,
                company=company,
            )

            selected = (
                outcome.candidates[0]
                if outcome.candidates
                else None
            )

            selected_detection_id: (
                int | None
            ) = None

            for candidate in (
                outcome.candidates
            ):
                detection = (
                    self.tracing_repository
                    .add_ats_detection(
                        AtsDetection(
                            company_scan_id=(
                                scan.id
                            ),
                            provider=(
                                candidate.provider
                            ),
                            external_identifier=(
                                candidate
                                .external_identifier
                            ),
                            method=(
                                candidate.method
                            ),
                            confidence=(
                                candidate.confidence
                            ),
                            source_url=(
                                candidate.source_url
                            ),
                            evidence=(
                                candidate.evidence
                            ),
                            selected=(
                                candidate
                                is selected
                            ),
                        )
                    )
                )

                if (
                    candidate is selected
                    and detection.id
                    is not None
                ):
                    selected_detection_id = (
                        detection.id
                    )

            if selected is not None:
                (
                    self.company_ats_repository
                    .upsert(
                        CompanyAts(
                            company_id=(
                                company.id
                            ),
                            provider=(
                                selected.provider
                            ),
                            external_identifier=(
                                selected
                                .external_identifier
                            ),
                            board_url=(
                                selected.board_url
                            ),
                            source_detection_id=(
                                selected_detection_id
                            ),
                        )
                    )
                )

                ats_status = (
                    AtsScanStatus.DETECTED
                )

                summary.detected += 1

            elif (
                outcome.warning_type
                == "CAREERS_FETCH_BLOCKED"
            ):
                ats_status = (
                    AtsScanStatus.BLOCKED
                )

                summary.blocked += 1

            else:
                ats_status = (
                    AtsScanStatus
                    .NOT_DETECTED
                )

                summary.not_detected += 1

            summary.results.append(
                CompanyAtsScanResult(
                    company_name=(
                        company.name
                    ),
                    careers_url=(
                        outcome.careers_url
                    ),
                    ats_status=ats_status,
                    provider=(
                        selected.provider
                        if selected
                        is not None
                        else None
                    ),
                    external_identifier=(
                        selected
                        .external_identifier
                        if selected
                        is not None
                        else None
                    ),
                    method=(
                        selected.method
                        if selected
                        is not None
                        else None
                    ),
                    confidence=(
                        selected.confidence
                        if selected
                        is not None
                        else None
                    ),
                    warning=(
                        outcome.warning_message
                    ),
                )
            )

            if (
                company.careers_url
                is None
                and outcome.careers_url
                is not None
            ):
                (
                    self.company_repository
                    .fill_missing_discovery_fields(
                        company_id=company.id,
                        careers_url=(
                            outcome.careers_url
                        ),
                    )
                )

            (
                self.tracing_repository
                .finish_company_scan(
                    company_scan_id=(
                        scan.id
                    ),
                    status=(
                        RunStatus.SUCCESS
                    ),
                    homepage_http_status=(
                        outcome
                        .homepage_http_status
                    ),
                    careers_url_found=(
                        outcome.careers_url
                    ),
                    careers_discovery_method=(
                        outcome
                        .careers_discovery_method
                    ),
                    ats_status=ats_status,
                    error_type=(
                        outcome.warning_type
                    ),
                    error_message=(
                        outcome.warning_message
                    ),
                )
            )

        except (
            httpx.HTTPError,
            ValueError,
        ) as exc:
            summary.failed += 1

            (
                self.tracing_repository
                .finish_company_scan(
                    company_scan_id=(
                        scan.id
                    ),
                    status=(
                        RunStatus.FAILED
                    ),
                    homepage_http_status=None,
                    careers_url_found=(
                        company.careers_url
                    ),
                    careers_discovery_method=(
                        "KNOWN"
                        if company.careers_url
                        else None
                    ),
                    ats_status=(
                        AtsScanStatus.ERROR
                    ),
                    error_type=(
                        type(exc).__name__
                    ),
                    error_message=str(exc),
                )
            )

            summary.results.append(
                CompanyAtsScanResult(
                    company_name=(
                        company.name
                    ),
                    careers_url=(
                        company.careers_url
                    ),
                    ats_status=(
                        AtsScanStatus.ERROR
                    ),
                    error=str(exc),
                )
            )

    def _scan_company(
        self,
        client: httpx.Client,
        company: Company,
    ) -> _ScanOutcome:
        homepage_status: (
            int | None
        ) = None

        careers_url = (
            company.careers_url
        )

        careers_method = (
            "KNOWN"
            if careers_url is not None
            else None
        )

        candidates: list[
            AtsCandidate
        ] = []

        warning_type: (
            str | None
        ) = None

        warning_message: (
            str | None
        ) = None

        if careers_url is None:
            if company.website_url is None:
                return _ScanOutcome(
                    careers_url=None,
                    careers_discovery_method=None,
                    homepage_http_status=None,
                    candidates=[],
                )

            try:
                homepage = _fetch_page(
                    client=client,
                    url=(
                        company.website_url
                    ),
                )

            except httpx.HTTPStatusError as exc:
                if (
                    exc.response.status_code
                    in BLOCKED_HTTP_STATUSES
                ):
                    return _ScanOutcome(
                        careers_url=None,
                        careers_discovery_method=None,
                        homepage_http_status=(
                            exc.response
                            .status_code
                        ),
                        candidates=[],
                        warning_type=(
                            "CAREERS_FETCH_BLOCKED"
                        ),
                        warning_message=(
                            "Homepage fetch "
                            "blocked with HTTP "
                            f"{exc.response.status_code}"
                        ),
                    )

                raise

            homepage_status = (
                homepage.status_code
            )

            careers_url = (
                _discover_careers_url(
                    homepage
                )
            )

            if careers_url is None:
                return _ScanOutcome(
                    careers_url=None,
                    careers_discovery_method=None,
                    homepage_http_status=(
                        homepage_status
                    ),
                    candidates=[],
                )

            careers_method = (
                "HOMEPAGE_LINK"
            )

        direct_candidate = (
            _detect_from_url(
                url=careers_url,
                method=(
                    AtsDetectionMethod
                    .CAREERS_LINK
                ),
                confidence=0.99,
            )
        )

        if direct_candidate is not None:
            candidates.append(
                direct_candidate
            )

        careers_page: (
            PageDocument | None
        ) = None

        try:
            careers_page = _fetch_page(
                client=client,
                url=careers_url,
            )

        except httpx.HTTPStatusError as exc:
            if (
                exc.response.status_code
                not in BLOCKED_HTTP_STATUSES
            ):
                raise

            warning_type = (
                "CAREERS_FETCH_BLOCKED"
            )

            warning_message = (
                "Careers page fetch "
                "blocked with HTTP "
                f"{exc.response.status_code}"
            )

        if careers_page is not None:
            if (
                careers_page.final_url
                != careers_url
            ):
                redirect_candidate = (
                    _detect_from_url(
                        url=(
                            careers_page
                            .final_url
                        ),
                        method=(
                            AtsDetectionMethod
                            .REDIRECT
                        ),
                        confidence=1.0,
                    )
                )

                if (
                    redirect_candidate
                    is not None
                ):
                    candidates.append(
                        redirect_candidate
                    )

            candidates.extend(
                _detect_from_page(
                    careers_page
                )
            )

        candidates = (
            _deduplicate_candidates(
                candidates
            )
        )

        provider_hints = {
            candidate.provider
            for candidate
            in candidates
        }

        if provider_hints:
            candidates.extend(
                _probe_ats_providers(
                    client=client,
                    company=company,
                    providers=tuple(
                        sorted(
                            provider_hints,
                            key=lambda item: (
                                item.value
                            ),
                        )
                    ),
                    existing_candidates=(
                        candidates
                    ),
                )
            )

        else:
            candidates.extend(
                _probe_ats_providers(
                    client=client,
                    company=company,
                    providers=(
                        PROBE_ORDER
                    ),
                    existing_candidates=[],
                    stop_after_first=True,
                )
            )

        return _ScanOutcome(
            careers_url=careers_url,
            careers_discovery_method=(
                careers_method
            ),
            homepage_http_status=(
                homepage_status
            ),
            candidates=(
                _deduplicate_candidates(
                    candidates
                )
            ),
            warning_type=warning_type,
            warning_message=(
                warning_message
            ),
        )


class _HtmlReferenceParser(
    HTMLParser
):
    def __init__(self) -> None:
        super().__init__(
            convert_charrefs=True
        )

        self.anchors: list[
            tuple[str, str]
        ] = []

        self.resources: list[
            tuple[str, str]
        ] = []

        self._anchor_href: (
            str | None
        ) = None

        self._anchor_text: list[
            str
        ] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[
            tuple[str, str | None]
        ],
    ) -> None:
        attributes = {
            key.casefold(): value
            for key, value in attrs
        }

        normalized_tag = (
            tag.casefold()
        )

        if normalized_tag == "a":
            href = attributes.get(
                "href"
            )

            if href:
                self._anchor_href = href
                self._anchor_text = []

                for key in (
                    "title",
                    "aria-label",
                ):
                    value = (
                        attributes.get(key)
                    )

                    if value:
                        self._anchor_text.append(
                            value
                        )

        elif normalized_tag in {
            "iframe",
            "script",
        }:
            src = attributes.get(
                "src"
            )

            if src:
                self.resources.append(
                    (
                        normalized_tag,
                        src,
                    )
                )

        elif normalized_tag == "form":
            action = attributes.get(
                "action"
            )

            if action:
                self.resources.append(
                    (
                        "form",
                        action,
                    )
                )

    def handle_data(
        self,
        data: str,
    ) -> None:
        if (
            self._anchor_href
            is None
        ):
            return

        cleaned = data.strip()

        if cleaned:
            self._anchor_text.append(
                cleaned
            )

    def handle_endtag(
        self,
        tag: str,
    ) -> None:
        if (
            tag.casefold() != "a"
            or self._anchor_href
            is None
        ):
            return

        self.anchors.append(
            (
                self._anchor_href,
                " ".join(
                    self._anchor_text
                ),
            )
        )

        self._anchor_href = None
        self._anchor_text = []


def _fetch_page(
    client: httpx.Client,
    url: str,
) -> PageDocument:
    response = client.get(url)

    response.raise_for_status()

    html = response.text[
        :MAX_HTML_CHARS
    ]

    parser = (
        _HtmlReferenceParser()
    )

    parser.feed(html)

    final_url = str(
        response.url
    )

    anchors = [
        (
            resolved,
            text,
        )
        for href, text
        in parser.anchors
        if (
            resolved
            := _resolve_http_url(
                final_url,
                href,
            )
        )
        is not None
    ]

    resources = [
        (
            resource_type,
            resolved,
        )
        for resource_type, raw_url
        in parser.resources
        if (
            resolved
            := _resolve_http_url(
                final_url,
                raw_url,
            )
        )
        is not None
    ]

    return PageDocument(
        requested_url=url,
        final_url=final_url,
        status_code=(
            response.status_code
        ),
        html=html,
        anchors=anchors,
        resources=resources,
    )


def _discover_careers_url(
    page: PageDocument,
) -> str | None:
    candidates: list[
        tuple[int, str]
    ] = []

    for href, text in page.anchors:
        normalized = (
            f"{text} {href}"
            .casefold()
        )

        score = 0

        if any(
            term in normalized
            for term in CAREERS_TERMS
        ):
            score += 10

        if (
            _detect_from_url(
                url=href,
                method=(
                    AtsDetectionMethod
                    .HOMEPAGE_LINK
                ),
                confidence=0.95,
            )
            is not None
        ):
            score += 8

        path = (
            urlsplit(href)
            .path
            .casefold()
        )

        if "/careers" in path:
            score += 5

        if "/jobs" in path:
            score += 4

        if "/vacantes" in path:
            score += 5

        if "/trabaja" in path:
            score += 5

        if score > 0:
            candidates.append(
                (
                    score,
                    href,
                )
            )

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: (
            -item[0],
            len(item[1]),
        )
    )

    return candidates[0][1]


def _detect_from_page(
    page: PageDocument,
) -> list[AtsCandidate]:
    candidates: list[
        AtsCandidate
    ] = []

    for href, _ in page.anchors:
        candidate = (
            _detect_from_url(
                url=href,
                method=(
                    AtsDetectionMethod
                    .HTML_LINK
                ),
                confidence=0.96,
            )
        )

        if candidate is not None:
            candidates.append(
                candidate
            )

    for (
        resource_type,
        resource_url,
    ) in page.resources:
        if resource_type == "iframe":
            method = (
                AtsDetectionMethod
                .EMBED_URL
            )

            confidence = 0.98

        elif resource_type == "script":
            method = (
                AtsDetectionMethod
                .SCRIPT_REFERENCE
            )

            confidence = 0.90

        else:
            method = (
                AtsDetectionMethod
                .EMBED_URL
            )

            confidence = 0.93

        candidate = (
            _detect_from_url(
                url=resource_url,
                method=method,
                confidence=confidence,
            )
        )

        if candidate is not None:
            candidates.append(
                candidate
            )

    raw_html = (
        unescape(page.html)
        .replace(
            "\\/",
            "/",
        )
    )

    for match in (
        RAW_URL_PATTERN
        .finditer(raw_html)
    ):
        raw_url = (
            match.group(0)
            .rstrip(
                ".,);]}\\"
            )
        )

        candidate = (
            _detect_from_url(
                url=raw_url,
                method=(
                    AtsDetectionMethod
                    .OTHER
                ),
                confidence=0.85,
            )
        )

        if candidate is not None:
            candidates.append(
                candidate
            )

    lower_html = (
        raw_html.casefold()
    )

    if "ashby_jid" in lower_html:
        candidates.append(
            AtsCandidate(
                provider=(
                    AtsProvider.ASHBY
                ),
                method=(
                    AtsDetectionMethod
                    .URL_PARAMETER
                ),
                confidence=0.88,
                source_url=(
                    page.final_url
                ),
                evidence=(
                    "HTML contains "
                    "ashby_jid"
                ),
                board_url=(
                    page.final_url
                ),
            )
        )

    if "gh_jid" in lower_html:
        candidates.append(
            AtsCandidate(
                provider=(
                    AtsProvider
                    .GREENHOUSE
                ),
                method=(
                    AtsDetectionMethod
                    .URL_PARAMETER
                ),
                confidence=0.88,
                source_url=(
                    page.final_url
                ),
                evidence=(
                    "HTML contains gh_jid"
                ),
                board_url=(
                    page.final_url
                ),
            )
        )

    if (
        "greenhouse job board"
        in lower_html
    ):
        candidates.append(
            AtsCandidate(
                provider=(
                    AtsProvider
                    .GREENHOUSE
                ),
                method=(
                    AtsDetectionMethod
                    .OTHER
                ),
                confidence=0.80,
                source_url=(
                    page.final_url
                ),
                evidence=(
                    "HTML identifies "
                    "Greenhouse Job Board"
                ),
                board_url=(
                    page.final_url
                ),
            )
        )

    return candidates


def _detect_from_url(
    url: str,
    method: AtsDetectionMethod,
    confidence: float,
) -> AtsCandidate | None:
    parsed = urlsplit(url)

    if parsed.scheme not in {
        "http",
        "https",
    }:
        return None

    host = (
        parsed.hostname
        or ""
    ).casefold()

    path_parts = [
        part
        for part
        in parsed.path.split("/")
        if part
    ]

    query = parse_qs(
        parsed.query
    )

    if "ashby_jid" in query:
        return AtsCandidate(
            provider=(
                AtsProvider.ASHBY
            ),
            method=(
                AtsDetectionMethod
                .URL_PARAMETER
            ),
            confidence=min(
                confidence,
                0.92,
            ),
            source_url=url,
            evidence=(
                "ashby_jid query "
                "parameter"
            ),
            board_url=url,
        )

    if "gh_jid" in query:
        return AtsCandidate(
            provider=(
                AtsProvider.GREENHOUSE
            ),
            method=(
                AtsDetectionMethod
                .URL_PARAMETER
            ),
            confidence=min(
                confidence,
                0.92,
            ),
            source_url=url,
            evidence=(
                "gh_jid query parameter"
            ),
            board_url=url,
        )

    if _is_greenhouse_host(
        host
    ):
        identifier = (
            _greenhouse_identifier(
                host=host,
                path_parts=(
                    path_parts
                ),
                query=query,
            )
        )

        return AtsCandidate(
            provider=(
                AtsProvider.GREENHOUSE
            ),
            method=method,
            confidence=confidence,
            source_url=url,
            evidence=(
                f"Greenhouse host: "
                f"{host}"
            ),
            external_identifier=(
                identifier
            ),
            board_url=(
                _canonical_board_url(
                    provider=(
                        AtsProvider
                        .GREENHOUSE
                    ),
                    identifier=(
                        identifier
                    ),
                    fallback=url,
                )
            ),
        )

    if host == "jobs.ashbyhq.com":
        identifier = (
            path_parts[0]
            if path_parts
            else None
        )

        return AtsCandidate(
            provider=(
                AtsProvider.ASHBY
            ),
            method=method,
            confidence=confidence,
            source_url=url,
            evidence=(
                "Ashby job board host"
            ),
            external_identifier=(
                identifier
            ),
            board_url=(
                _canonical_board_url(
                    provider=(
                        AtsProvider.ASHBY
                    ),
                    identifier=(
                        identifier
                    ),
                    fallback=url,
                )
            ),
        )

    if host == "jobs.lever.co":
        identifier = (
            path_parts[0]
            if path_parts
            else None
        )

        return AtsCandidate(
            provider=(
                AtsProvider.LEVER
            ),
            method=method,
            confidence=confidence,
            source_url=url,
            evidence=(
                "Lever job board host"
            ),
            external_identifier=(
                identifier
            ),
            board_url=(
                _canonical_board_url(
                    provider=(
                        AtsProvider.LEVER
                    ),
                    identifier=(
                        identifier
                    ),
                    fallback=url,
                )
            ),
        )

    if host in {
        "jobs.smartrecruiters.com",
        "careers.smartrecruiters.com",
    }:
        identifier = (
            path_parts[0]
            if path_parts
            else None
        )

        return AtsCandidate(
            provider=(
                AtsProvider
                .SMARTRECRUITERS
            ),
            method=method,
            confidence=confidence,
            source_url=url,
            evidence=(
                "SmartRecruiters "
                "job board host"
            ),
            external_identifier=(
                identifier
            ),
            board_url=(
                _canonical_board_url(
                    provider=(
                        AtsProvider
                        .SMARTRECRUITERS
                    ),
                    identifier=(
                        identifier
                    ),
                    fallback=url,
                )
            ),
        )

    if host in {
        "apply.workable.com",
        "jobs.workable.com",
    }:
        identifier = None

        if (
            host
            == "apply.workable.com"
            and path_parts
        ):
            identifier = (
                path_parts[0]
            )

        return AtsCandidate(
            provider=(
                AtsProvider.WORKABLE
            ),
            method=method,
            confidence=confidence,
            source_url=url,
            evidence=(
                "Workable job board host"
            ),
            external_identifier=(
                identifier
            ),
            board_url=(
                _canonical_board_url(
                    provider=(
                        AtsProvider.WORKABLE
                    ),
                    identifier=(
                        identifier
                    ),
                    fallback=url,
                )
            ),
        )

    if (
        host.endswith(
            ".bamboohr.com"
        )
        and host
        != "www.bamboohr.com"
    ):
        identifier = (
            host.split(".")[0]
        )

        return AtsCandidate(
            provider=(
                AtsProvider.BAMBOOHR
            ),
            method=method,
            confidence=confidence,
            source_url=url,
            evidence=(
                "BambooHR careers host"
            ),
            external_identifier=(
                identifier
            ),
            board_url=(
                _canonical_board_url(
                    provider=(
                        AtsProvider.BAMBOOHR
                    ),
                    identifier=(
                        identifier
                    ),
                    fallback=url,
                )
            ),
        )

    return None


def _probe_ats_providers(
    client: httpx.Client,
    company: Company,
    providers: tuple[
        AtsProvider,
        ...,
    ],
    existing_candidates: list[
        AtsCandidate
    ],
    stop_after_first: bool = False,
) -> list[AtsCandidate]:
    identifiers = (
        _identifier_candidates(
            company
        )
    )

    existing_identifiers: dict[
        AtsProvider,
        list[str],
    ] = {}

    for candidate in (
        existing_candidates
    ):
        if (
            candidate
            .external_identifier
            is None
        ):
            continue

        (
            existing_identifiers
            .setdefault(
                candidate.provider,
                [],
            )
            .append(
                candidate
                .external_identifier
            )
        )

    results: list[
        AtsCandidate
    ] = []

    for provider in providers:
        provider_identifiers = (
            existing_identifiers.get(
                provider,
                [],
            )
            + identifiers
        )

        provider_identifiers = list(
            dict.fromkeys(
                provider_identifiers
            )
        )

        for identifier in (
            provider_identifiers
        ):
            candidate = (
                _probe_provider_identifier(
                    client=client,
                    company=company,
                    provider=provider,
                    identifier=(
                        identifier
                    ),
                )
            )

            if candidate is None:
                continue

            results.append(
                candidate
            )

            break

        if (
            results
            and stop_after_first
        ):
            break

    return results


def _probe_provider_identifier(
    client: httpx.Client,
    company: Company,
    provider: AtsProvider,
    identifier: str,
) -> AtsCandidate | None:
    if (
        provider
        == AtsProvider.GREENHOUSE
    ):
        return _probe_greenhouse(
            client=client,
            company=company,
            identifier=identifier,
        )

    if provider == AtsProvider.ASHBY:
        return _probe_ashby(
            client=client,
            identifier=identifier,
        )

    if provider == AtsProvider.LEVER:
        return _probe_lever(
            client=client,
            identifier=identifier,
        )

    if (
        provider
        == AtsProvider.SMARTRECRUITERS
    ):
        return _probe_smartrecruiters(
            client=client,
            identifier=identifier,
        )

    if (
        provider
        == AtsProvider.WORKABLE
    ):
        return _probe_workable(
            client=client,
            company=company,
            identifier=identifier,
        )

    if (
        provider
        == AtsProvider.BAMBOOHR
    ):
        return _probe_bamboohr(
            client=client,
            company=company,
            identifier=identifier,
        )

    return None


def _probe_greenhouse(
    client: httpx.Client,
    company: Company,
    identifier: str,
) -> AtsCandidate | None:
    api_url = (
        "https://"
        "boards-api.greenhouse.io/"
        "v1/boards/"
        f"{identifier}"
    )

    response = _safe_get(
        client,
        api_url,
    )

    if (
        response is None
        or response.status_code
        != 200
    ):
        return None

    try:
        payload = response.json()

    except ValueError:
        return None

    board_name = payload.get(
        "name"
    )

    if not isinstance(
        board_name,
        str,
    ):
        return None

    if not _names_compatible(
        company.name,
        board_name,
    ):
        return None

    return AtsCandidate(
        provider=(
            AtsProvider.GREENHOUSE
        ),
        method=(
            AtsDetectionMethod
            .PUBLIC_API_PROBE
        ),
        confidence=0.995,
        source_url=api_url,
        evidence=(
            "Greenhouse public Job "
            "Board API validated "
            f"board '{board_name}'"
        ),
        external_identifier=(
            identifier
        ),
        board_url=(
            _canonical_board_url(
                provider=(
                    AtsProvider.GREENHOUSE
                ),
                identifier=identifier,
                fallback=api_url,
            )
        ),
    )


def _probe_ashby(
    client: httpx.Client,
    identifier: str,
) -> AtsCandidate | None:
    api_url = (
        "https://api.ashbyhq.com/"
        "posting-api/job-board/"
        f"{identifier}"
    )

    response = _safe_get(
        client,
        api_url,
    )

    if (
        response is None
        or response.status_code
        != 200
    ):
        return None

    try:
        payload = response.json()

    except ValueError:
        return None

    if (
        payload.get("apiVersion")
        is None
        or not isinstance(
            payload.get("jobs"),
            list,
        )
    ):
        return None

    return AtsCandidate(
        provider=(
            AtsProvider.ASHBY
        ),
        method=(
            AtsDetectionMethod
            .PUBLIC_API_PROBE
        ),
        confidence=0.98,
        source_url=api_url,
        evidence=(
            "Ashby public Job "
            "Postings API validated "
            "job-board identifier "
            f"'{identifier}'"
        ),
        external_identifier=(
            identifier
        ),
        board_url=(
            _canonical_board_url(
                provider=(
                    AtsProvider.ASHBY
                ),
                identifier=identifier,
                fallback=api_url,
            )
        ),
    )


def _probe_lever(
    client: httpx.Client,
    identifier: str,
) -> AtsCandidate | None:
    api_url = (
        "https://api.lever.co/"
        "v0/postings/"
        f"{identifier}"
    )

    response = _safe_get(
        client,
        api_url,
        params={
            "limit": 1,
            "mode": "json",
        },
    )

    if (
        response is None
        or response.status_code
        != 200
    ):
        return None

    try:
        payload = response.json()

    except ValueError:
        return None

    if not isinstance(
        payload,
        list,
    ):
        return None

    return AtsCandidate(
        provider=(
            AtsProvider.LEVER
        ),
        method=(
            AtsDetectionMethod
            .PUBLIC_API_PROBE
        ),
        confidence=0.97,
        source_url=api_url,
        evidence=(
            "Lever public Postings "
            "API validated site "
            f"identifier '{identifier}'"
        ),
        external_identifier=(
            identifier
        ),
        board_url=(
            _canonical_board_url(
                provider=(
                    AtsProvider.LEVER
                ),
                identifier=identifier,
                fallback=api_url,
            )
        ),
    )


def _probe_smartrecruiters(
    client: httpx.Client,
    identifier: str,
) -> AtsCandidate | None:
    api_url = (
        "https://"
        "api.smartrecruiters.com/"
        "v1/companies/"
        f"{identifier}/postings"
    )

    response = _safe_get(
        client,
        api_url,
        params={
            "limit": 1,
        },
    )

    if (
        response is None
        or response.status_code
        != 200
    ):
        return None

    try:
        payload = response.json()

    except ValueError:
        return None

    content = payload.get(
        "content"
    )

    total_found = payload.get(
        "totalFound"
    )

    if (
        not isinstance(
            content,
            list,
        )
        or not isinstance(
            total_found,
            int,
        )
    ):
        return None

    # Important:
    #
    # SmartRecruiters responds with
    # HTTP 200 + an empty collection
    # even for unknown company
    # identifiers.
    #
    # Therefore an empty result is
    # NOT positive ATS evidence.
    if (
        total_found < 1
        or not content
    ):
        return None

    return AtsCandidate(
        provider=(
            AtsProvider
            .SMARTRECRUITERS
        ),
        method=(
            AtsDetectionMethod
            .PUBLIC_API_PROBE
        ),
        confidence=0.95,
        source_url=api_url,
        evidence=(
            "SmartRecruiters public "
            "Posting API returned "
            f"{total_found} active "
            "posting(s) for derived "
            "company identifier "
            f"'{identifier}'"
        ),
        external_identifier=(
            identifier
        ),
        board_url=(
            _canonical_board_url(
                provider=(
                    AtsProvider
                    .SMARTRECRUITERS
                ),
                identifier=identifier,
                fallback=api_url,
            )
        ),
    )


def _probe_workable(
    client: httpx.Client,
    company: Company,
    identifier: str,
) -> AtsCandidate | None:
    board_url = (
        "https://apply.workable.com/"
        f"{identifier}/"
    )

    response = _safe_get(
        client,
        board_url,
    )

    if (
        response is None
        or response.status_code
        != 200
    ):
        return None

    final_url = str(
        response.url
    )

    final_path = (
        urlsplit(final_url)
        .path
        .casefold()
    )

    expected_prefix = (
        f"/{identifier.casefold()}"
    )

    if not final_path.startswith(
        expected_prefix
    ):
        return None

    if not _names_compatible(
        company.name,
        response.text,
    ):
        return None

    return AtsCandidate(
        provider=(
            AtsProvider.WORKABLE
        ),
        method=(
            AtsDetectionMethod
            .BOARD_PROBE
        ),
        confidence=0.96,
        source_url=board_url,
        evidence=(
            "Workable board probe "
            "validated derived "
            f"identifier '{identifier}'"
        ),
        external_identifier=(
            identifier
        ),
        board_url=board_url,
    )


def _probe_bamboohr(
    client: httpx.Client,
    company: Company,
    identifier: str,
) -> AtsCandidate | None:
    board_url = (
        f"https://{identifier}"
        ".bamboohr.com/careers"
    )

    response = _safe_get(
        client,
        board_url,
    )

    if (
        response is None
        or response.status_code
        != 200
    ):
        return None

    final_host = (
        urlsplit(
            str(response.url)
        )
        .hostname
        or ""
    ).casefold()

    expected_host = (
        f"{identifier.casefold()}"
        ".bamboohr.com"
    )

    if final_host != expected_host:
        return None

    if not _names_compatible(
        company.name,
        response.text,
    ):
        return None

    return AtsCandidate(
        provider=(
            AtsProvider.BAMBOOHR
        ),
        method=(
            AtsDetectionMethod
            .BOARD_PROBE
        ),
        confidence=0.96,
        source_url=board_url,
        evidence=(
            "BambooHR board probe "
            "validated derived "
            f"identifier '{identifier}'"
        ),
        external_identifier=(
            identifier
        ),
        board_url=board_url,
    )


def _safe_get(
    client: httpx.Client,
    url: str,
    params: dict | None = None,
) -> httpx.Response | None:
    try:
        return client.get(
            url,
            params=params,
        )

    except httpx.HTTPError:
        return None


def _identifier_candidates(
    company: Company,
) -> list[str]:
    candidates: list[str] = []

    if company.domain:
        domain = (
            company.domain
            .casefold()
            .split(":")[0]
        )

        first_label = (
            domain.split(".")[0]
        )

        _append_identifier(
            candidates,
            first_label,
        )

    normalized_name = (
        _normalize_ascii(
            company.name
        )
    )

    compact_name = re.sub(
        r"[^a-z0-9]",
        "",
        normalized_name,
    )

    hyphenated_name = re.sub(
        r"[^a-z0-9]+",
        "-",
        normalized_name,
    ).strip("-")

    _append_identifier(
        candidates,
        compact_name,
    )

    _append_identifier(
        candidates,
        hyphenated_name,
    )

    return candidates[:3]


def _append_identifier(
    values: list[str],
    value: str,
) -> None:
    if (
        not value
        or len(value) < 2
        or value in values
    ):
        return

    values.append(value)


def _names_compatible(
    company_name: str,
    value: str,
) -> bool:
    company = re.sub(
        r"[^a-z0-9]",
        "",
        _normalize_ascii(
            company_name
        ),
    )

    other = re.sub(
        r"[^a-z0-9]",
        "",
        _normalize_ascii(value),
    )

    if (
        len(company) < 3
        or len(other) < 3
    ):
        return False

    return (
        company in other
        or other in company
    )


def _normalize_ascii(
    value: str,
) -> str:
    decomposed = (
        unicodedata.normalize(
            "NFKD",
            value,
        )
    )

    without_accents = "".join(
        character
        for character
        in decomposed
        if not unicodedata.combining(
            character
        )
    )

    return (
        without_accents
        .casefold()
        .strip()
    )


def _is_greenhouse_host(
    host: str,
) -> bool:
    if not host.endswith(
        "greenhouse.io"
    ):
        return False

    return (
        host.startswith(
            "boards."
        )
        or host.startswith(
            "job-boards."
        )
        or host.startswith(
            "boards-api."
        )
    )


def _greenhouse_identifier(
    host: str,
    path_parts: list[str],
    query: dict[
        str,
        list[str],
    ],
) -> str | None:
    embedded = query.get(
        "for"
    )

    if embedded:
        return embedded[0]

    if (
        host.startswith(
            "boards-api."
        )
        and len(path_parts) >= 3
        and path_parts[0] == "v1"
        and path_parts[1] == "boards"
    ):
        return path_parts[2]

    if (
        path_parts
        and path_parts[0]
        not in {
            "embed",
            "jobs",
        }
    ):
        return path_parts[0]

    return None


def _canonical_board_url(
    provider: AtsProvider,
    identifier: str | None,
    fallback: str,
) -> str:
    if identifier is None:
        return fallback

    if (
        provider
        == AtsProvider.GREENHOUSE
    ):
        return (
            "https://"
            "job-boards.greenhouse.io/"
            f"{identifier}"
        )

    if provider == AtsProvider.ASHBY:
        return (
            "https://jobs.ashbyhq.com/"
            f"{identifier}"
        )

    if provider == AtsProvider.LEVER:
        return (
            "https://jobs.lever.co/"
            f"{identifier}"
        )

    if (
        provider
        == AtsProvider.SMARTRECRUITERS
    ):
        return (
            "https://"
            "jobs.smartrecruiters.com/"
            f"{identifier}"
        )

    if (
        provider
        == AtsProvider.WORKABLE
    ):
        return (
            "https://apply.workable.com/"
            f"{identifier}/"
        )

    if (
        provider
        == AtsProvider.BAMBOOHR
    ):
        return (
            f"https://{identifier}"
            ".bamboohr.com/careers"
        )

    return fallback


def _deduplicate_candidates(
    candidates: list[
        AtsCandidate
    ],
) -> list[AtsCandidate]:
    best_by_key: dict[
        tuple[
            AtsProvider,
            str | None,
            str,
        ],
        AtsCandidate,
    ] = {}

    for candidate in candidates:
        key = (
            candidate.provider,
            candidate.external_identifier,
            candidate.board_url
            or candidate.source_url,
        )

        existing = (
            best_by_key.get(key)
        )

        if (
            existing is None
            or candidate.confidence
            > existing.confidence
        ):
            best_by_key[key] = (
                candidate
            )

    result = list(
        best_by_key.values()
    )

    result.sort(
        key=lambda item: (
            -item.confidence,
            (
                0
                if item
                .external_identifier
                is not None
                else 1
            ),
            item.provider.value,
        )
    )

    return result


def _resolve_http_url(
    base_url: str,
    raw_url: str,
) -> str | None:
    cleaned = raw_url.strip()

    if not cleaned:
        return None

    resolved = urljoin(
        base_url,
        cleaned,
    )

    parsed = urlsplit(
        resolved
    )

    if parsed.scheme not in {
        "http",
        "https",
    }:
        return None

    return resolved


def _run_status(
    processed: int,
    failed: int,
) -> RunStatus:
    if processed == 0:
        return RunStatus.SUCCESS

    if failed == 0:
        return RunStatus.SUCCESS

    if failed < processed:
        return RunStatus.PARTIAL

    return RunStatus.FAILED