from dataclasses import dataclass

import httpx

from chamba_hunter.domain.enums import (
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
from chamba_hunter.repositories.tracing_repository import (
    TracingRepository,
)
from chamba_hunter.services.careers_ats_detection_service import (
    CareersAtsDetectionSummary,
    CompanyAtsScanResult,
    _probe_ats_providers,
)


@dataclass(frozen=True, slots=True)
class ProviderHintTarget:
    company: Company
    provider: AtsProvider
    source_evidence: str


class ProviderHintAtsDetectionService:
    def __init__(
        self,
        tracing_repository: TracingRepository,
        company_ats_repository: CompanyAtsRepository,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.tracing_repository = (
            tracing_repository
        )
        self.company_ats_repository = (
            company_ats_repository
        )
        self.timeout_seconds = timeout_seconds

    def run(
        self,
        targets: list[ProviderHintTarget],
    ) -> CareersAtsDetectionSummary:
        run = self.tracing_repository.add_run(
            Run(
                command=(
                    "detect_provider_hint_ats"
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
                    "provider_hint_ats_detection"
                ),
                items_total=len(targets),
            )
        )

        if step.id is None:
            raise RuntimeError(
                "Run step must have an id."
            )

        summary = CareersAtsDetectionSummary(
            run_id=run.id
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
            for target in targets:
                if target.company.id is None:
                    summary.skipped += 1
                    continue

                self._scan_one(
                    client=client,
                    run_step_id=step.id,
                    target=target,
                    summary=summary,
                )

        status = _run_status(
            processed=summary.processed,
            failed=summary.failed,
        )

        self.tracing_repository.finish_run_step(
            run_step_id=step.id,
            status=status,
            items_success=(
                summary.processed
                - summary.failed
            ),
            items_failed=summary.failed,
            items_skipped=summary.skipped,
            metadata={
                "detected": summary.detected,
                "not_detected": (
                    summary.not_detected
                ),
                "blocked": summary.blocked,
                "strategy": "PROVIDER_HINT",
            },
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
        target: ProviderHintTarget,
        summary: CareersAtsDetectionSummary,
    ) -> None:
        company = target.company

        if company.id is None:
            summary.skipped += 1
            return

        scan = self.tracing_repository.add_company_scan(
            CompanyScan(
                run_step_id=run_step_id,
                company_id=company.id,
                homepage_url=company.website_url,
                expected_ats_provider=(
                    target.provider
                ),
            )
        )

        if scan.id is None:
            raise RuntimeError(
                "Company scan must have an id."
            )

        summary.processed += 1

        try:
            candidates = _probe_ats_providers(
                client=client,
                company=company,
                providers=(target.provider,),
                existing_candidates=[],
                stop_after_first=True,
            )

            selected = (
                candidates[0]
                if candidates
                else None
            )

            if selected is not None:
                evidence = (
                    "Jooble source evidence "
                    f"'{target.source_evidence}' "
                    "indicated provider "
                    f"{target.provider.value}; "
                    f"{selected.evidence}"
                )

                detection = (
                    self.tracing_repository
                    .add_ats_detection(
                        AtsDetection(
                            company_scan_id=scan.id,
                            provider=(
                                selected.provider
                            ),
                            external_identifier=(
                                selected
                                .external_identifier
                            ),
                            method=selected.method,
                            confidence=(
                                selected.confidence
                            ),
                            source_url=(
                                selected.source_url
                            ),
                            evidence=evidence,
                            selected=True,
                        )
                    )
                )

                self.company_ats_repository.upsert(
                    CompanyAts(
                        company_id=company.id,
                        provider=selected.provider,
                        external_identifier=(
                            selected
                            .external_identifier
                        ),
                        board_url=(
                            selected.board_url
                        ),
                        source_detection_id=(
                            detection.id
                        ),
                    )
                )

                ats_status = (
                    AtsScanStatus.DETECTED
                )
                summary.detected += 1

            else:
                ats_status = (
                    AtsScanStatus.NOT_DETECTED
                )
                summary.not_detected += 1

            summary.results.append(
                CompanyAtsScanResult(
                    company_name=company.name,
                    careers_url=None,
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
                )
            )

            self.tracing_repository.finish_company_scan(
                company_scan_id=scan.id,
                status=RunStatus.SUCCESS,
                homepage_http_status=None,
                careers_url_found=None,
                careers_discovery_method=(
                    "PROVIDER_HINT"
                ),
                ats_status=ats_status,
            )

        except (
            httpx.HTTPError,
            ValueError,
        ) as exc:
            summary.failed += 1

            self.tracing_repository.finish_company_scan(
                company_scan_id=scan.id,
                status=RunStatus.FAILED,
                homepage_http_status=None,
                careers_url_found=None,
                careers_discovery_method=(
                    "PROVIDER_HINT"
                ),
                ats_status=AtsScanStatus.ERROR,
                error_type=(
                    type(exc).__name__
                ),
                error_message=str(exc),
            )

            summary.results.append(
                CompanyAtsScanResult(
                    company_name=company.name,
                    careers_url=None,
                    ats_status=AtsScanStatus.ERROR,
                    error=str(exc),
                )
            )


def _run_status(
    processed: int,
    failed: int,
) -> RunStatus:
    if failed == 0:
        return RunStatus.SUCCESS

    if processed > failed:
        return RunStatus.PARTIAL

    return RunStatus.FAILED
