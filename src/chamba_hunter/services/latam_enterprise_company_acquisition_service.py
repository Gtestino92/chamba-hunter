from collections import Counter
from dataclasses import dataclass, field

from pydantic import ValidationError

from chamba_hunter.schemas.inputs import CompanySeedInput
from chamba_hunter.services.company_import_service import (
    CompanyImportService,
)
from chamba_hunter.sources.latam_enterprise_companies import (
    LatamEnterpriseRegistry,
    LatamEnterpriseRegistryEntry,
)


@dataclass(frozen=True, slots=True)
class LatamEnterpriseCompanyResult:
    name: str
    country: str | None
    created: bool
    matched_by: str | None
    company_id: int | None
    error_type: str | None = None
    error_message: str | None = None


@dataclass(slots=True)
class LatamEnterpriseAcquisitionSummary:
    registry_entries: int
    selected_entries: int
    skipped_entries: int
    apply: bool

    companies_created: int = 0
    companies_existing: int = 0
    failed_entries: int = 0

    matched_by_counts: Counter[
        str
    ] = field(
        default_factory=Counter
    )

    results: list[
        LatamEnterpriseCompanyResult
    ] = field(
        default_factory=list
    )


class LatamEnterpriseCompanyAcquisitionService:
    def __init__(
        self,
        company_import_service: CompanyImportService,
    ) -> None:
        self.company_import_service = (
            company_import_service
        )

    def run(
        self,
        *,
        registry: LatamEnterpriseRegistry,
        apply: bool,
        country: str | None = None,
        limit: int | None = None,
    ) -> LatamEnterpriseAcquisitionSummary:
        entries = _select_entries(
            registry.entries,
            country=country,
            limit=limit,
        )

        summary = (
            LatamEnterpriseAcquisitionSummary(
                registry_entries=len(
                    registry.entries
                ),
                selected_entries=len(
                    entries
                ),
                skipped_entries=(
                    len(registry.entries)
                    - len(entries)
                ),
                apply=apply,
            )
        )

        for entry in entries:
            self._run_one(
                entry=entry,
                apply=apply,
                summary=summary,
            )

        return summary

    def _run_one(
        self,
        *,
        entry: LatamEnterpriseRegistryEntry,
        apply: bool,
        summary: LatamEnterpriseAcquisitionSummary,
    ) -> None:
        seed = entry.seed

        try:
            import_result = (
                self.company_import_service
                .import_seed(
                    seed,
                    source_metadata=(
                        _metadata_for(seed, entry)
                    ),
                )
                if apply
                else self.company_import_service
                .preview_seed(seed)
            )

            company = (
                import_result.company
            )

            if import_result.created:
                summary.companies_created += 1
            else:
                summary.companies_existing += 1

                matched_by = (
                    import_result.matched_by
                    or "UNKNOWN"
                )

                summary.matched_by_counts[
                    matched_by
                ] += 1

            summary.results.append(
                LatamEnterpriseCompanyResult(
                    name=seed.name,
                    country=seed.country,
                    created=(
                        import_result.created
                    ),
                    matched_by=(
                        import_result.matched_by
                    ),
                    company_id=company.id,
                )
            )

        except (
            ValidationError,
            ValueError,
            RuntimeError,
        ) as exc:
            summary.failed_entries += 1

            summary.results.append(
                LatamEnterpriseCompanyResult(
                    name=seed.name,
                    country=seed.country,
                    created=False,
                    matched_by=None,
                    company_id=None,
                    error_type=(
                        type(exc).__name__
                    ),
                    error_message=str(exc),
                )
            )


def _select_entries(
    entries: tuple[
        LatamEnterpriseRegistryEntry,
        ...,
    ],
    *,
    country: str | None,
    limit: int | None,
) -> list[LatamEnterpriseRegistryEntry]:
    selected = list(entries)

    if country is not None:
        normalized_country = (
            country.strip().casefold()
        )

        selected = [
            entry
            for entry in selected
            if (
                entry.seed.country
                or ""
            ).casefold()
            == normalized_country
        ]

    if limit is not None:
        selected = selected[:limit]

    return selected


def _metadata_for(
    seed: CompanySeedInput,
    entry: LatamEnterpriseRegistryEntry,
) -> dict[str, str | bool | None]:
    return {
        "curated_registry": True,
        "registry": (
            "latam_enterprise_companies"
        ),
        "sector": entry.sector,
        "country": seed.country,
    }
