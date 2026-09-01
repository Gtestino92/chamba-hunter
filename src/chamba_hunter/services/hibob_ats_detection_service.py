from dataclasses import dataclass, field
from html.parser import HTMLParser
import re
from urllib.parse import urljoin

import httpx

from chamba_hunter.domain.enums import (
    AtsDetectionMethod,
    AtsProvider,
    AtsScanStatus,
    RunStatus,
)
from chamba_hunter.domain.models import Company, CompanyAts
from chamba_hunter.domain.tracing import AtsDetection, CompanyScan, Run, RunStep
from chamba_hunter.repositories.company_ats_repository import CompanyAtsRepository
from chamba_hunter.repositories.tracing_repository import TracingRepository
from chamba_hunter.sources.hibob import (
    canonical_hibob_board_url,
    hibob_tenant_from_url,
)


RAW_URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.urls: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = {key.casefold(): value for key, value in attrs}
        for key in ("href", "src"):
            value = attributes.get(key)
            if value:
                self.urls.append(value)


@dataclass(frozen=True, slots=True)
class HiBobDetectionResult:
    company_id: int
    company_name: str
    detected: bool
    tenant: str | None = None
    board_url: str | None = None
    source_url: str | None = None
    error: str | None = None


@dataclass(slots=True)
class HiBobDetectionSummary:
    run_id: int
    processed: int = 0
    detected: int = 0
    not_detected: int = 0
    failed: int = 0
    skipped: int = 0
    results: list[HiBobDetectionResult] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _Candidate:
    tenant: str
    source_url: str
    method: AtsDetectionMethod
    confidence: float


class HiBobAtsDetectionService:
    def __init__(
        self,
        *,
        company_ats_repository: CompanyAtsRepository,
        tracing_repository: TracingRepository,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.company_ats_repository = company_ats_repository
        self.tracing_repository = tracing_repository
        self.timeout_seconds = timeout_seconds

    def run(self, companies: list[Company]) -> HiBobDetectionSummary:
        run = self.tracing_repository.add_run(Run(command="detect_hibob_ats"))
        if run.id is None:
            raise RuntimeError("Run must have an id.")
        step = self.tracing_repository.add_run_step(
            RunStep(
                run_id=run.id,
                step_name="hibob_ats_detection",
                items_total=len(companies),
            )
        )
        if step.id is None:
            raise RuntimeError("Run step must have an id.")

        summary = HiBobDetectionSummary(run_id=run.id)
        with httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": "chamba-hunter/0.1"},
        ) as client:
            for company in companies:
                self._scan_one(
                    client=client,
                    run_step_id=step.id,
                    company=company,
                    summary=summary,
                )

        status = _run_status(detected=summary.detected, failed=summary.failed)
        self.tracing_repository.finish_run_step(
            run_step_id=step.id,
            status=status,
            items_success=summary.processed - summary.failed,
            items_failed=summary.failed,
            items_skipped=summary.skipped,
            metadata={
                "detected": summary.detected,
                "not_detected": summary.not_detected,
            },
        )
        self.tracing_repository.finish_run(run_id=run.id, status=status)
        return summary

    def _scan_one(
        self,
        *,
        client: httpx.Client,
        run_step_id: int,
        company: Company,
        summary: HiBobDetectionSummary,
    ) -> None:
        if company.id is None or not company.careers_url:
            summary.skipped += 1
            return

        scan = self.tracing_repository.add_company_scan(
            CompanyScan(
                run_step_id=run_step_id,
                company_id=company.id,
                homepage_url=company.careers_url,
            )
        )
        if scan.id is None:
            raise RuntimeError("Company scan must have an id.")

        summary.processed += 1
        status_code: int | None = None
        try:
            candidate = _direct_candidate(company.careers_url)
            if candidate is None:
                response = client.get(company.careers_url)
                response.raise_for_status()
                status_code = response.status_code
                candidate = _candidate_from_page(
                    page_url=str(response.url),
                    html=response.text,
                )

            if candidate is None:
                summary.not_detected += 1
                summary.results.append(
                    HiBobDetectionResult(
                        company_id=company.id,
                        company_name=company.name,
                        detected=False,
                    )
                )
                self.tracing_repository.finish_company_scan(
                    company_scan_id=scan.id,
                    status=RunStatus.SUCCESS,
                    homepage_http_status=status_code,
                    careers_url_found=company.careers_url,
                    careers_discovery_method="KNOWN",
                    ats_status=AtsScanStatus.NOT_DETECTED,
                )
                return

            board_url = canonical_hibob_board_url(candidate.tenant)
            detection = self.tracing_repository.add_ats_detection(
                AtsDetection(
                    company_scan_id=scan.id,
                    provider=AtsProvider.HIBOB,
                    external_identifier=candidate.tenant,
                    method=candidate.method,
                    confidence=candidate.confidence,
                    source_url=candidate.source_url,
                    evidence="HiBob public careers host",
                    selected=True,
                )
            )
            self.company_ats_repository.upsert(
                CompanyAts(
                    company_id=company.id,
                    provider=AtsProvider.HIBOB,
                    external_identifier=candidate.tenant,
                    board_url=board_url,
                    source_detection_id=detection.id,
                )
            )
            summary.detected += 1
            summary.results.append(
                HiBobDetectionResult(
                    company_id=company.id,
                    company_name=company.name,
                    detected=True,
                    tenant=candidate.tenant,
                    board_url=board_url,
                    source_url=candidate.source_url,
                )
            )
            self.tracing_repository.finish_company_scan(
                company_scan_id=scan.id,
                status=RunStatus.SUCCESS,
                homepage_http_status=status_code,
                careers_url_found=company.careers_url,
                careers_discovery_method="KNOWN",
                ats_status=AtsScanStatus.DETECTED,
            )
        except httpx.HTTPStatusError as error:
            self._record_failure(
                scan_id=scan.id,
                company=company,
                summary=summary,
                status_code=error.response.status_code,
                error=error,
            )
        except (httpx.RequestError, ValueError) as error:
            self._record_failure(
                scan_id=scan.id,
                company=company,
                summary=summary,
                status_code=status_code,
                error=error,
            )

    def _record_failure(
        self,
        *,
        scan_id: int,
        company: Company,
        summary: HiBobDetectionSummary,
        status_code: int | None,
        error: Exception,
    ) -> None:
        summary.failed += 1
        summary.results.append(
            HiBobDetectionResult(
                company_id=company.id or 0,
                company_name=company.name,
                detected=False,
                error=str(error),
            )
        )
        self.tracing_repository.finish_company_scan(
            company_scan_id=scan_id,
            status=RunStatus.FAILED,
            homepage_http_status=status_code,
            careers_url_found=company.careers_url,
            careers_discovery_method="KNOWN",
            ats_status=AtsScanStatus.ERROR,
            error_type=type(error).__name__,
            error_message=str(error),
        )


def _direct_candidate(value: str) -> _Candidate | None:
    tenant = hibob_tenant_from_url(value)
    if tenant is None:
        return None
    return _Candidate(
        tenant=tenant,
        source_url=value,
        method=AtsDetectionMethod.CAREERS_LINK,
        confidence=1.0,
    )


def _candidate_from_page(*, page_url: str, html: str) -> _Candidate | None:
    parser = _LinkParser()
    parser.feed(html)
    candidates = [urljoin(page_url, raw) for raw in parser.urls]
    candidates.extend(RAW_URL_PATTERN.findall(html))

    seen: set[str] = set()
    for value in candidates:
        if value in seen:
            continue
        seen.add(value)
        tenant = hibob_tenant_from_url(value)
        if tenant is None:
            continue
        return _Candidate(
            tenant=tenant,
            source_url=value,
            method=AtsDetectionMethod.HTML_LINK,
            confidence=0.99,
        )
    return None


def _run_status(*, detected: int, failed: int) -> RunStatus:
    if failed == 0:
        return RunStatus.SUCCESS
    if detected == 0:
        return RunStatus.FAILED
    return RunStatus.PARTIAL
