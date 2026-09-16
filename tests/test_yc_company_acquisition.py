from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate
from chamba_hunter.domain.enums import (
    CompanyType,
    SourceType,
)
from chamba_hunter.domain.models import (
    Company,
    CompanySource,
)
from chamba_hunter.repositories.company_repository import (
    CompanyRepository,
)
from chamba_hunter.repositories.company_source_repository import (
    CompanySourceRepository,
)
from chamba_hunter.schemas.inputs import (
    CompanySeedInput,
)
from chamba_hunter.services.company_import_service import (
    CompanyImportService,
    normalize_company_name,
)
from chamba_hunter.services.yc_company_acquisition_service import (
    YcCompanyAcquisitionService,
)
from chamba_hunter.sources.yc_companies import (
    YcCompany,
    YcDirectoryFetch,
)


def test_yc_acquisition_repairs_domain_matched_company_name(
    tmp_path,
) -> None:
    database = _database(tmp_path)
    company_repository = CompanyRepository(
        database
    )
    existing = company_repository.add(
        Company(
            name="Get Started + Early YC Deal",
            normalized_name=(
                normalize_company_name(
                    "Get Started + Early YC Deal"
                )
            ),
            domain="dedaluslabs.ai",
            website_url=(
                "https://dedaluslabs.ai"
            ),
        )
    )

    summary = _service(
        database,
        [
            _yc_company(
                name="Dedalus Labs",
                slug="dedalus-labs",
                website_url=(
                    "https://dedaluslabs.ai"
                ),
            )
        ],
    ).run(
        categories=("Developer Tools",),
        max_companies=10,
    )

    assert summary.company_names_updated == 1

    repaired = company_repository.get_by_id(
        existing.id
    )

    assert repaired is not None
    assert repaired.id == existing.id
    assert repaired.name == "Dedalus Labs"
    assert repaired.normalized_name == (
        normalize_company_name(
            "Dedalus Labs"
        )
    )
    assert repaired.domain == "dedaluslabs.ai"

    source_company_id = (
        CompanySourceRepository(database)
        .find_company_id(
            SourceType.YC,
            external_id="dedalus-labs",
        )
    )

    assert source_company_id == existing.id


def test_yc_acquisition_repairs_existing_source_identity_name(
    tmp_path,
) -> None:
    database = _database(tmp_path)
    import_service = _import_service(database)
    initial = import_service.import_seed(
        CompanySeedInput(
            name="📣 Our Ask",
            website_url="https://ryvn.ai",
            source_type=SourceType.YC,
            external_id="ryvn",
            source_url=(
                "https://www.ycombinator.com/"
                "companies/ryvn"
            ),
        )
    )

    summary = _service(
        database,
        [
            _yc_company(
                name="Ryvn",
                slug="ryvn",
                website_url="https://ryvn.ai",
            )
        ],
    ).run(
        categories=("Developer Tools",),
        max_companies=10,
    )

    assert summary.company_names_updated == 1

    repaired = CompanyRepository(
        database
    ).get_by_id(
        initial.company.id
    )

    assert repaired is not None
    assert repaired.id == initial.company.id
    assert repaired.name == "Ryvn"
    assert repaired.normalized_name == (
        normalize_company_name(
            "Ryvn"
        )
    )


def test_correct_existing_yc_name_is_idempotent(
    tmp_path,
) -> None:
    database = _database(tmp_path)
    company = _add_company_with_source(
        database,
        name="Acme",
        domain="acme.com",
        slug="acme",
    )

    summary = _service(
        database,
        [
            _yc_company(
                name="Acme",
                slug="acme",
                website_url="https://acme.com",
            )
        ],
    ).run(
        categories=("Developer Tools",),
        max_companies=10,
    )

    after = CompanyRepository(
        database
    ).get_by_id(
        company.id
    )

    assert summary.company_names_updated == 0
    assert after is not None
    assert after.name == "Acme"
    assert after.normalized_name == (
        company.normalized_name
    )
    assert after.updated_at == company.updated_at


def test_yc_name_synchronization_does_not_create_second_company(
    tmp_path,
) -> None:
    database = _database(tmp_path)
    _add_company_with_source(
        database,
        name="Wrong Name",
        domain="acme.com",
        slug="acme",
    )

    summary = _service(
        database,
        [
            _yc_company(
                name="Acme",
                slug="acme",
                website_url="https://acme.com",
            )
        ],
    ).run(
        categories=("Developer Tools",),
        max_companies=10,
    )

    assert summary.companies_created == 0
    assert summary.companies_existing == 1
    assert _company_count(database) == 1


def test_generic_company_import_does_not_replace_existing_name(
    tmp_path,
) -> None:
    database = _database(tmp_path)
    company_repository = CompanyRepository(
        database
    )
    existing = company_repository.add(
        Company(
            name="Get Started + Early YC Deal",
            normalized_name=(
                normalize_company_name(
                    "Get Started + Early YC Deal"
                )
            ),
            domain="dedaluslabs.ai",
            website_url=(
                "https://dedaluslabs.ai"
            ),
        )
    )

    result = _import_service(
        database
    ).import_seed(
        CompanySeedInput(
            name="Dedalus Labs",
            website_url=(
                "https://dedaluslabs.ai"
            ),
            source_type=SourceType.OTHER,
            external_id="dedalus",
        )
    )

    after = company_repository.get_by_id(
        existing.id
    )

    assert result.company.id == existing.id
    assert after is not None
    assert after.name == (
        "Get Started + Early YC Deal"
    )
    assert after.normalized_name == (
        normalize_company_name(
            "Get Started + Early YC Deal"
        )
    )
    assert _company_count(database) == 1


def _database(tmp_path) -> Database:
    database = Database(
        tmp_path / "test.db"
    )
    migrate(database)
    return database


def _import_service(
    database: Database,
) -> CompanyImportService:
    return CompanyImportService(
        CompanyRepository(database),
        CompanySourceRepository(database),
    )


def _service(
    database: Database,
    companies: list[YcCompany],
) -> YcCompanyAcquisitionService:
    company_repository = CompanyRepository(
        database
    )

    return YcCompanyAcquisitionService(
        client=_FakeYcDirectoryClient(
            companies
        ),
        company_import_service=(
            CompanyImportService(
                company_repository,
                CompanySourceRepository(
                    database
                ),
            )
        ),
        company_repository=(
            company_repository
        ),
    )


def _add_company_with_source(
    database: Database,
    *,
    name: str,
    domain: str,
    slug: str,
) -> Company:
    company_repository = CompanyRepository(
        database
    )
    company = company_repository.add(
        Company(
            name=name,
            normalized_name=(
                normalize_company_name(
                    name
                )
            ),
            domain=domain,
            website_url=f"https://{domain}",
            company_type=CompanyType.PRODUCT,
        )
    )

    assert company.id is not None

    CompanySourceRepository(
        database
    ).add_or_touch(
        CompanySource(
            company_id=company.id,
            source_type=SourceType.YC,
            external_id=slug,
            source_url=(
                "https://www.ycombinator.com/"
                f"companies/{slug}"
            ),
            raw_name=name,
        )
    )

    return company


def _yc_company(
    *,
    name: str,
    slug: str,
    website_url: str,
) -> YcCompany:
    return YcCompany(
        yc_id=123,
        name=name,
        slug=slug,
        profile_url=(
            "https://www.ycombinator.com/"
            f"companies/{slug}"
        ),
        website_url=website_url,
        status="active",
        matched_categories=(
            "Developer Tools",
        ),
        batch="W26",
        team_size=10,
        location="San Francisco",
        industry="Developer Tools",
        subindustry=None,
        industries=(
            "Developer Tools",
        ),
        tags=(),
        regions=(),
        stage=None,
        is_hiring=True,
        top_company=False,
        directory_rank=1,
    )


def _company_count(
    database: Database,
) -> int:
    with database.connection() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS count FROM companies"
        ).fetchone()

    return int(
        row["count"]
    )


class _FakeYcDirectoryClient:
    def __init__(
        self,
        companies: list[YcCompany],
    ) -> None:
        self.companies = companies

    def fetch(
        self,
        *,
        categories: tuple[str, ...],
        max_companies: int,
    ) -> YcDirectoryFetch:
        return YcDirectoryFetch(
            feeds_requested=len(
                categories
            ),
            feeds_fetched=len(
                categories
            ),
            feeds_failed=0,
            raw_records=len(
                self.companies
            ),
            unique_candidates=len(
                self.companies
            ),
            skipped_status=0,
            skipped_missing_website=0,
            skipped_invalid=0,
            companies=tuple(
                self.companies[
                    :max_companies
                ]
            ),
        )
