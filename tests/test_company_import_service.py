from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate
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