from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate
from chamba_hunter.domain.enums import SourceType
from chamba_hunter.repositories.company_source_repository import (
    CompanySourceRepository,
)
from chamba_hunter.schemas.inputs import CompanySeedInput
from chamba_hunter.services.company_import_service import CompanyImportService
from chamba_hunter.repositories.company_repository import CompanyRepository


def test_import_company_normalizes_and_deduplicates(tmp_path):
    database = Database(tmp_path / "test.db")
    migrate(database)

    repository = CompanyRepository(database)
    source_repository = CompanySourceRepository(database)

    service = CompanyImportService(
        repository,
        source_repository,
    )
    first = service.import_seed(
        CompanySeedInput(
            name="  Pomelo  ",
            website_url="https://www.pomelo.la/",
        )
    )

    second = service.import_seed(
        CompanySeedInput(
            name="POMELO",
            website_url="https://pomelo.la",
        )
    )

    assert first.created is True
    assert first.company.id is not None

    assert first.company.name == "Pomelo"
    assert first.company.normalized_name == "pomelo"
    assert first.company.domain == "pomelo.la"
    assert first.company.website_url == "https://pomelo.la"

    assert second.created is False
    assert second.matched_by == "DOMAIN"
    assert second.company.id == first.company.id

    assert len(repository.list_all()) == 1

    sources = source_repository.list_for_company(
        first.company.id
    )

    assert len(sources) == 1
    assert sources[0].source_type.value == "MANUAL"


def test_preview_and_import_match_by_source(tmp_path):
    service, _repository, _source_repository = (
        _build_service(tmp_path)
    )

    service.import_seed(
        CompanySeedInput(
            name="Source Match",
            source_type=SourceType.OTHER,
            external_id="source-match",
        )
    )

    seed = CompanySeedInput(
        name="Renamed Source Match",
        website_url="https://source-match.example/",
        source_type=SourceType.OTHER,
        external_id="source-match",
    )

    preview = service.preview_seed(seed)
    imported = service.import_seed(seed)

    assert preview.created is False
    assert preview.matched_by == "SOURCE"
    assert imported.created is False
    assert imported.matched_by == "SOURCE"


def test_preview_and_import_match_by_domain(tmp_path):
    service, _repository, _source_repository = (
        _build_service(tmp_path)
    )

    service.import_seed(
        CompanySeedInput(
            name="Domain Match",
            website_url="https://www.domain-match.example/",
        )
    )

    seed = CompanySeedInput(
        name="Different Domain Name",
        website_url="https://domain-match.example/",
    )

    preview = service.preview_seed(seed)
    imported = service.import_seed(seed)

    assert preview.created is False
    assert preview.matched_by == "DOMAIN"
    assert imported.created is False
    assert imported.matched_by == "DOMAIN"


def test_preview_and_import_match_by_normalized_name(
    tmp_path,
):
    service, _repository, _source_repository = (
        _build_service(tmp_path)
    )

    service.import_seed(
        CompanySeedInput(
            name="Normalized Match",
        )
    )

    seed = CompanySeedInput(
        name="normalized match",
    )

    preview = service.preview_seed(seed)
    imported = service.import_seed(seed)

    assert preview.created is False
    assert preview.matched_by == "NORMALIZED_NAME"
    assert imported.created is False
    assert imported.matched_by == "NORMALIZED_NAME"


def test_preview_and_import_match_by_domainless_name(
    tmp_path,
):
    service, _repository, _source_repository = (
        _build_service(tmp_path)
    )

    service.import_seed(
        CompanySeedInput(
            name="Domainless Match",
        )
    )

    seed = CompanySeedInput(
        name="domainless match",
        website_url="https://domainless.example/",
    )

    preview = service.preview_seed(seed)
    imported = service.import_seed(seed)

    assert preview.created is False
    assert preview.matched_by == (
        "NORMALIZED_NAME_DOMAINLESS"
    )
    assert imported.created is False
    assert imported.matched_by == (
        "NORMALIZED_NAME_DOMAINLESS"
    )


def _build_service(tmp_path):
    database = Database(tmp_path / "test.db")
    migrate(database)

    repository = CompanyRepository(database)
    source_repository = (
        CompanySourceRepository(database)
    )

    return (
        CompanyImportService(
            repository,
            source_repository,
        ),
        repository,
        source_repository,
    )
