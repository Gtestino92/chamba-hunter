import json

import pytest

from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate
from chamba_hunter.domain.enums import SourceType
from chamba_hunter.repositories.company_repository import (
    CompanyRepository,
)
from chamba_hunter.repositories.company_source_repository import (
    CompanySourceRepository,
)
from chamba_hunter.schemas.inputs import CompanySeedInput
from chamba_hunter.services.company_import_service import (
    CompanyImportService,
)
from chamba_hunter.services.latam_enterprise_company_acquisition_service import (
    LatamEnterpriseCompanyAcquisitionService,
)
from chamba_hunter.sources.latam_enterprise_companies import (
    load_latam_enterprise_registry,
)


def test_registry_parsing_and_validation(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "entries": [
                    _entry(
                        name="Grupo Sancor Seguros",
                        external_id=(
                            "ar:grupo-sancor-seguros"
                        ),
                    )
                ],
            }
        ),
        encoding="utf-8",
    )

    registry = load_latam_enterprise_registry(
        registry_path
    )

    assert registry.schema_version == 1
    assert len(registry.entries) == 1
    assert (
        registry.entries[0].seed.source_type
        == SourceType.LATAM_ENTERPRISE
    )


def test_registry_rejects_invalid_structure(tmp_path):
    registry_path = tmp_path / "registry.json"
    invalid = _entry()
    invalid.pop("external_id")

    registry_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "entries": [invalid],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="missing fields",
    ):
        load_latam_enterprise_registry(
            registry_path
        )


def test_dry_run_does_not_persist_any_companies(tmp_path):
    service, repository, source_repository, registry = (
        _build_service(tmp_path)
    )

    summary = service.run(
        registry=registry,
        apply=False,
    )

    assert summary.selected_entries == 2
    assert summary.companies_created == 2
    assert summary.companies_existing == 0
    assert repository.list_all() == []
    assert (
        source_repository.list_by_source_type(
            SourceType.LATAM_ENTERPRISE
        )
        == []
    )


def test_dry_run_does_not_mutate_existing_company(
    tmp_path,
):
    service, repository, source_repository, registry = (
        _build_service(tmp_path)
    )

    existing = (
        service.company_import_service.import_seed(
            CompanySeedInput(
                name="Grupo Sancor Seguros",
            )
        )
    )

    assert existing.company.id is not None

    summary = service.run(
        registry=registry,
        apply=False,
        limit=1,
    )

    stored = repository.get_by_id(
        existing.company.id
    )

    assert summary.companies_created == 0
    assert summary.companies_existing == 1
    assert summary.matched_by_counts[
        "NORMALIZED_NAME_DOMAINLESS"
    ] == 1

    assert stored is not None
    assert stored.website_url is None
    assert stored.domain is None
    assert stored.careers_url is None
    assert stored.country is None

    assert (
        source_repository.list_by_source_type(
            SourceType.LATAM_ENTERPRISE
        )
        == []
    )


def test_apply_imports_companies(tmp_path):
    service, repository, _, registry = (
        _build_service(tmp_path)
    )

    summary = service.run(
        registry=registry,
        apply=True,
    )

    companies = repository.list_all()

    assert summary.companies_created == 2
    assert summary.companies_existing == 0
    assert len(companies) == 2
    assert {
        company.country
        for company in companies
    } == {
        "Argentina",
        "Uruguay",
    }


def test_rerunning_apply_is_idempotent(tmp_path):
    service, repository, source_repository, registry = (
        _build_service(tmp_path)
    )

    first = service.run(
        registry=registry,
        apply=True,
    )
    second = service.run(
        registry=registry,
        apply=True,
    )

    sources = (
        source_repository.list_by_source_type(
            SourceType.LATAM_ENTERPRISE
        )
    )

    assert first.companies_created == 2
    assert second.companies_created == 0
    assert second.companies_existing == 2
    assert second.matched_by_counts["SOURCE"] == 2
    assert len(repository.list_all()) == 2
    assert len(sources) == 2


def test_known_company_is_matched_not_duplicated(
    tmp_path,
):
    service, repository, _, registry = (
        _build_service(tmp_path)
    )

    import_service = (
        service.company_import_service
    )
    existing = import_service.import_seed(
        CompanySeedInput(
            name="Existing Sancor",
            website_url=(
                "https://www.sancorseguros.com.ar/"
            ),
        )
    )

    summary = service.run(
        registry=registry,
        apply=True,
        limit=1,
    )

    assert summary.companies_created == 0
    assert summary.companies_existing == 1
    assert summary.matched_by_counts["DOMAIN"] == 1
    assert len(repository.list_all()) == 1
    assert (
        summary.results[0].company_id
        == existing.company.id
    )


def test_country_filtering(tmp_path):
    service, _, _, registry = _build_service(
        tmp_path
    )

    summary = service.run(
        registry=registry,
        apply=False,
        country="Argentina",
    )

    assert summary.selected_entries == 1
    assert summary.skipped_entries == 1
    assert summary.results[0].country == "Argentina"


def test_limit_behavior(tmp_path):
    service, _, _, registry = _build_service(
        tmp_path
    )

    summary = service.run(
        registry=registry,
        apply=False,
        limit=1,
    )

    assert summary.selected_entries == 1
    assert summary.skipped_entries == 1
    assert summary.results[0].name == "Grupo Sancor Seguros"


def test_source_tracking_is_recorded(tmp_path):
    service, _, source_repository, registry = (
        _build_service(tmp_path)
    )

    service.run(
        registry=registry,
        apply=True,
        limit=1,
    )

    sources = (
        source_repository.list_by_source_type(
            SourceType.LATAM_ENTERPRISE
        )
    )

    assert len(sources) == 1
    assert sources[0].external_id == (
        "ar:grupo-sancor-seguros"
    )
    assert sources[0].source_url == (
        "https://sancorseguros.com.ar"
    )
    assert sources[0].metadata == {
        "curated_registry": True,
        "registry": (
            "latam_enterprise_companies"
        ),
        "sector": "insurance",
        "country": "Argentina",
    }


def _build_service(tmp_path):
    database = Database(
        tmp_path / "test.db"
    )
    migrate(database)

    repository = CompanyRepository(
        database
    )
    source_repository = (
        CompanySourceRepository(
            database
        )
    )
    import_service = CompanyImportService(
        repository,
        source_repository,
    )
    service = (
        LatamEnterpriseCompanyAcquisitionService(
            import_service
        )
    )

    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "entries": [
                    _entry(
                        name=(
                            "Grupo Sancor "
                            "Seguros"
                        ),
                        external_id=(
                            "ar:grupo-sancor-seguros"
                        ),
                        website_url=(
                            "https://www.sancorseguros.com.ar/"
                        ),
                        careers_url=(
                            "https://empleos.gruposancorseguros.com/"
                        ),
                        source_url=(
                            "https://www.sancorseguros.com.ar/"
                        ),
                        sector="insurance",
                    ),
                    _entry(
                        name="dLocal",
                        country="Uruguay",
                        external_id=(
                            "uy:dlocal"
                        ),
                        website_url=(
                            "https://www.dlocal.com/"
                        ),
                        careers_url=(
                            "https://dlocal.com/careers/"
                        ),
                        source_url=(
                            "https://www.dlocal.com/"
                        ),
                        sector="fintech",
                    ),
                ],
            }
        ),
        encoding="utf-8",
    )
    registry = load_latam_enterprise_registry(
        registry_path
    )

    return (
        service,
        repository,
        source_repository,
        registry,
    )


def _entry(
    *,
    name: str = "Example Company",
    country: str = "Argentina",
    website_url: str = "https://www.example.com/",
    careers_url: str | None = None,
    external_id: str = "ar:example-company",
    source_url: str = "https://www.example.com/",
    sector: str = "technology",
) -> dict:
    return {
        "name": name,
        "country": country,
        "website_url": website_url,
        "careers_url": careers_url,
        "external_id": external_id,
        "source_url": source_url,
        "sector": sector,
    }
