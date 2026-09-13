import httpx

from chamba_hunter.commands.fingerprint_latam_enterprise_ats import (
    select_latam_enterprise_companies,
)
from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate
from chamba_hunter.domain.enums import (
    AtsFingerprintStatus,
    AtsProvider,
    AtsSupportStatus,
    SourceType,
)
from chamba_hunter.domain.models import CompanyAts
from chamba_hunter.repositories.ats_fingerprint_repository import (
    AtsFingerprintRepository,
)
from chamba_hunter.repositories.company_ats_repository import (
    CompanyAtsRepository,
)
from chamba_hunter.repositories.company_repository import (
    CompanyRepository,
)
from chamba_hunter.repositories.company_source_repository import (
    CompanySourceRepository,
)
from chamba_hunter.repositories.tracing_repository import (
    TracingRepository,
)
from chamba_hunter.schemas.inputs import CompanySeedInput
from chamba_hunter.services.company_import_service import (
    CompanyImportService,
)
from chamba_hunter.services.careers_ats_detection_service import (
    PageDocument,
)
from chamba_hunter.services.latam_enterprise_ats_fingerprinting_service import (
    LatamEnterpriseAtsFingerprintingService,
    detect_fingerprint_from_url,
    detect_fingerprints_from_page,
    fingerprint_company,
)


def test_direct_successfactors_url_detection():
    candidate = detect_fingerprint_from_url(
        url=(
            "https://hcm19.sapsf.com/"
            "career?company=claro"
        ),
        method="CAREERS_LINK",
        confidence=0.99,
    )

    assert candidate is not None
    assert (
        candidate.provider_family
        == "SUCCESSFACTORS"
    )
    assert (
        candidate.support_status
        == AtsSupportStatus.SUPPORTED
    )
    assert "SuccessFactors" in candidate.evidence


def test_custom_domain_page_linking_to_successfactors():
    candidates = detect_fingerprints_from_page(
        _page(
            final_url="https://claroempleos-aup.com/",
            anchors=[
                (
                    "https://hcm19.sapsf.com/"
                    "career?company=claro",
                    "Ver empleos",
                )
            ],
        )
    )

    assert candidates[0].provider_family == (
        "SUCCESSFACTORS"
    )
    assert candidates[0].confidence >= 0.90


def test_direct_workday_url_detection():
    candidate = detect_fingerprint_from_url(
        url=(
            "https://example.wd5."
            "myworkdayjobs.com/jobs"
        ),
        method="CAREERS_LINK",
        confidence=0.99,
    )

    assert candidate is not None
    assert candidate.provider_family == "WORKDAY"
    assert (
        candidate.support_status
        == AtsSupportStatus.UNSUPPORTED
    )
    assert "Workday" in candidate.evidence


def test_custom_domain_page_linking_to_workday():
    candidates = detect_fingerprints_from_page(
        _page(
            final_url="https://careers.example.com/",
            anchors=[
                (
                    "https://example.wd3."
                    "myworkdayjobs.com/jobs",
                    "Open roles",
                )
            ],
        )
    )

    assert candidates[0].provider_family == "WORKDAY"


def test_avature_fingerprint():
    candidate = detect_fingerprint_from_url(
        url="https://careers.avature.net/jobs",
        method="CAREERS_LINK",
        confidence=0.99,
    )

    assert candidate is not None
    assert candidate.provider_family == "AVATURE"


def test_oracle_taleo_fingerprint():
    taleo = detect_fingerprint_from_url(
        url=(
            "https://company.taleo.net/"
            "careersection/ex/jobsearch.ftl"
        ),
        method="CAREERS_LINK",
        confidence=0.99,
    )
    oracle = detect_fingerprint_from_url(
        url=(
            "https://eeho.fa.us2.oraclecloud.com/"
            "hcmUI/CandidateExperience/en/sites/CX/jobs"
        ),
        method="CAREERS_LINK",
        confidence=0.99,
    )

    assert taleo is not None
    assert oracle is not None
    assert taleo.provider_family == "ORACLE_TALEO"
    assert oracle.provider_family == "ORACLE_TALEO"


def test_gupy_fingerprint():
    candidate = detect_fingerprint_from_url(
        url="https://company.gupy.io/",
        method="CAREERS_LINK",
        confidence=0.99,
    )

    assert candidate is not None
    assert candidate.provider_family == "GUPY"


def test_pandape_fingerprint():
    candidate = detect_fingerprint_from_url(
        url="https://company.pandape.com.br/",
        method="CAREERS_LINK",
        confidence=0.99,
    )

    assert candidate is not None
    assert candidate.provider_family == "PANDAPE"


def test_existing_supported_ats_classification():
    candidate = detect_fingerprint_from_url(
        url="https://jobs.lever.co/example",
        method="CAREERS_LINK",
        confidence=0.99,
    )

    assert candidate is not None
    assert candidate.provider_family == "LEVER"
    assert (
        candidate.support_status
        == AtsSupportStatus.SUPPORTED
    )


def test_unknown_custom_page():
    company = _company(
        careers_url="https://careers.example.com/"
    )
    result = fingerprint_company(
        client=_client(
            {
                "https://careers.example.com/": (
                    200,
                    "<html><h1>Careers</h1></html>",
                )
            }
        ),
        company=company,
    )

    assert (
        result.fingerprint_status
        == AtsFingerprintStatus.UNKNOWN
    )
    assert (
        result.support_status
        == AtsSupportStatus.UNKNOWN
    )


def test_blocked_http_response():
    company = _company(
        careers_url="https://careers.example.com/"
    )
    result = fingerprint_company(
        client=_client(
            {
                "https://careers.example.com/": (
                    403,
                    "Forbidden",
                )
            }
        ),
        company=company,
    )

    assert (
        result.fingerprint_status
        == AtsFingerprintStatus.BLOCKED
    )
    assert result.http_status == 403


def test_network_error_result():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(
            "boom",
            request=request,
        )

    company = _company(
        careers_url="https://careers.example.com/"
    )
    result = fingerprint_company(
        client=httpx.Client(
            transport=httpx.MockTransport(handler)
        ),
        company=company,
    )

    assert (
        result.fingerprint_status
        == AtsFingerprintStatus.ERROR
    )
    assert result.error_type == "ConnectError"


def test_no_careers_url_no_usable_website_case():
    company = _company(
        careers_url=None,
        website_url=None,
    )

    result = fingerprint_company(
        client=_client({}),
        company=company,
    )

    assert result.fingerprint_status == (
        AtsFingerprintStatus.NO_CAREERS_URL
    )


def test_no_company_ats_mutation_during_scan(tmp_path):
    database = Database(tmp_path / "test.db")
    migrate(database)
    repository = CompanyRepository(database)
    source_repository = (
        CompanySourceRepository(database)
    )
    import_service = CompanyImportService(
        repository,
        source_repository,
    )
    imported = import_service.import_seed(
        CompanySeedInput(
            name="LATAM Company",
            country="Argentina",
            website_url="https://example.com/",
            careers_url="https://careers.example.com/",
            source_type=(
                SourceType.LATAM_ENTERPRISE
            ),
            external_id="ar:latam-company",
        )
    )
    assert imported.company.id is not None

    CompanyAtsRepository(database).upsert(
        CompanyAts(
            company_id=imported.company.id,
            provider=AtsProvider.GREENHOUSE,
            external_identifier="existing",
            board_url=(
                "https://boards.greenhouse.io/"
                "existing"
            ),
        )
    )

    service = (
        LatamEnterpriseAtsFingerprintingService(
            tracing_repository=(
                TracingRepository(database)
            ),
            fingerprint_repository=(
                AtsFingerprintRepository(
                    database
                )
            ),
        )
    )

    summary = service.run(
        [imported.company],
        client=_client(
            {
                "https://careers.example.com/": (
                    200,
                    "<html>Custom careers</html>",
                )
            }
        ),
    )

    with database.connection() as connection:
        rows = connection.execute(
            """
            SELECT provider,
                   external_identifier,
                   board_url
            FROM company_ats
            WHERE company_id = ?
            """,
            (imported.company.id,),
        ).fetchall()

    assert summary.scanned == 1
    latest = (
        service.fingerprint_repository
        .latest_for_company(
            imported.company.id
        )
    )
    assert latest is not None
    assert latest.fingerprint_status == (
        AtsFingerprintStatus.UNKNOWN
    )
    assert len(rows) == 1
    assert rows[0]["provider"] == "GREENHOUSE"
    assert rows[0]["external_identifier"] == (
        "existing"
    )


def test_cohort_filtering_by_latam_enterprise(tmp_path):
    database = Database(tmp_path / "test.db")
    migrate(database)
    repository = CompanyRepository(database)
    source_repository = (
        CompanySourceRepository(database)
    )
    import_service = CompanyImportService(
        repository,
        source_repository,
    )

    latam = import_service.import_seed(
        CompanySeedInput(
            name="LATAM Company",
            country="Argentina",
            website_url="https://latam.example/",
            source_type=(
                SourceType.LATAM_ENTERPRISE
            ),
            external_id="ar:latam-company",
        )
    )
    import_service.import_seed(
        CompanySeedInput(
            name="Manual Company",
            country="Argentina",
            website_url="https://manual.example/",
            source_type=SourceType.MANUAL,
        )
    )

    selected = select_latam_enterprise_companies(
        company_repository=repository,
        source_repository=source_repository,
        country="Argentina",
    )

    assert [company.id for company in selected] == [
        latam.company.id
    ]


def _page(
    *,
    final_url: str,
    anchors: list[
        tuple[str, str]
    ] | None = None,
    resources: list[
        tuple[str, str]
    ] | None = None,
    html: str = "<html></html>",
) -> PageDocument:
    return PageDocument(
        requested_url=final_url,
        final_url=final_url,
        status_code=200,
        html=html,
        anchors=anchors or [],
        resources=resources or [],
    )


def _company(
    *,
    careers_url: str | None,
    website_url: str | None = "https://example.com/",
):
    from chamba_hunter.domain.models import Company

    return Company(
        id=1,
        name="Example",
        normalized_name="example",
        website_url=website_url,
        careers_url=careers_url,
        country="Argentina",
    )


def _client(
    responses: dict[str, tuple[int, str]],
) -> httpx.Client:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        request_url = str(request.url)
        status_code, text = (
            responses.get(request_url)
            or responses.get(
                request_url.rstrip("/")
            )
            or responses[
                request_url.rstrip("/") + "/"
            ]
        )
        return httpx.Response(
            status_code=status_code,
            text=text,
            request=request,
        )

    return httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )
