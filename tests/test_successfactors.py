from datetime import datetime, timezone
from pathlib import Path

import httpx

from chamba_hunter.db.connection import (
    Database,
)
from chamba_hunter.db.migrations import (
    migrate,
)
from chamba_hunter.domain.enums import (
    AtsDetectionMethod,
    AtsFingerprintStatus,
    AtsProvider,
    AtsSupportStatus,
    RunStatus,
)
from chamba_hunter.domain.models import (
    Company,
    CompanyAts,
    Job,
)
from chamba_hunter.repositories.company_ats_repository import (
    CompanyAtsRepository,
)
from chamba_hunter.repositories.company_repository import (
    CompanyRepository,
)
from chamba_hunter.repositories.job_repository import (
    JobRepository,
)
from chamba_hunter.repositories.tracing_repository import (
    TracingRepository,
)
from chamba_hunter.services.careers_ats_detection_service import (
    PageDocument,
    _detect_from_page,
    _detect_from_url,
)
from chamba_hunter.services.latam_enterprise_ats_fingerprinting_service import (
    fingerprint_company,
)
from chamba_hunter.services.successfactors_job_ingestion_service import (
    SuccessFactorsJobIngestionService,
)
from chamba_hunter.sources.successfactors import (
    SuccessFactorsClient,
    SuccessFactorsJobDetail,
    SuccessFactorsJobsFetch,
    extract_job_id,
    successfactors_external_identifier,
)


def test_successfactors_is_ats_provider():
    assert AtsProvider.SUCCESSFACTORS.value == (
        "SUCCESSFACTORS"
    )


def test_direct_sapsf_detection():
    candidate = _detect_from_url(
        "https://career17.sapsf.com/career"
        "?company=CLAROPROD",
        method=AtsDetectionMethod.CAREERS_LINK,
        confidence=0.99,
    )

    assert candidate is not None
    assert (
        candidate.provider
        == AtsProvider.SUCCESSFACTORS
    )
    assert candidate.external_identifier == (
        "career17.sapsf.com/career"
        "?company=CLAROPROD"
    )


def test_direct_successfactors_detection():
    candidate = _detect_from_url(
        "https://career4.successfactors.com/"
        "career?company=edenor",
        method=AtsDetectionMethod.CAREERS_LINK,
        confidence=0.99,
    )

    assert candidate is not None
    assert (
        candidate.provider
        == AtsProvider.SUCCESSFACTORS
    )
    assert candidate.board_url == (
        "https://career4.successfactors.com/"
        "career?company=edenor"
    )


def test_custom_domain_career_site_builder_detection():
    page = PageDocument(
        requested_url=(
            "https://claroempleos-aup.com/"
        ),
        final_url=(
            "https://claroempleos-aup.com/"
        ),
        status_code=200,
        html=(
            "<html><script src=\"https://"
            "hcm17.sapsf.com/platform/js/"
            "j2w/core.js\"></script>"
            "<ul id=\"job-tile-list\"></ul>"
            "</html>"
        ),
        anchors=[],
        resources=[
            (
                "script",
                "https://hcm17.sapsf.com/"
                "platform/js/j2w/core.js",
            )
        ],
    )

    candidates = _detect_from_page(page)

    assert candidates[0].provider == (
        AtsProvider.SUCCESSFACTORS
    )
    assert candidates[0].board_url == (
        "https://claroempleos-aup.com/"
    )
    assert candidates[0].external_identifier == (
        "claroempleos-aup.com"
    )


def test_fingerprint_successfactors_is_supported():
    company = Company(
        id=1,
        name="Claro Argentina",
        normalized_name="claro argentina",
        careers_url=(
            "https://career17.sapsf.com/career"
            "?company=CLAROPROD"
        ),
    )
    result = fingerprint_company(
        client=_client(
            {
                (
                    "https://career17.sapsf.com/"
                    "career?company=CLAROPROD"
                ): (
                    403,
                    "Forbidden",
                )
            }
        ),
        company=company,
    )

    assert result.fingerprint_status == (
        AtsFingerprintStatus.DETECTED
    )
    assert result.provider_family == (
        "SUCCESSFACTORS"
    )
    assert result.support_status == (
        AtsSupportStatus.SUPPORTED
    )


def test_custom_csb_listing_and_detail_parsing():
    fetch = _fetch(
        board_url="https://claroempleos-aup.com/",
        responses={
            "https://claroempleos-aup.com/": (
                200,
                _board_html(),
            ),
            (
                "https://claroempleos-aup.com/"
                "search/?createNewAlert=false"
            ): (
                200,
                _search_html(
                    total=1,
                    links=[
                        (
                            "603583417",
                            "Jefe de Producto",
                            "Buenos Aires",
                        )
                    ],
                ),
            ),
            (
                "https://claroempleos-aup.com/job/"
                "Jefe-de-Producto/603583417/"
            ): (
                200,
                _detail_html(
                    job_id="603583417",
                    title="Jefe de Producto",
                    location="Buenos Aires",
                    description=(
                        "Equipo digital híbrido."
                    ),
                ),
            ),
        },
    )

    assert fetch.snapshot_complete is True
    assert fetch.variant == (
        "CAREER_SITE_BUILDER"
    )
    assert fetch.total == 1
    assert fetch.jobs[0].external_id == (
        "603583417"
    )
    assert fetch.jobs[0].title == (
        "Jefe de Producto"
    )
    assert fetch.jobs[0].apply_url == (
        "https://claroempleos-aup.com/"
        "talentcommunity/apply/603583417/"
    )
    assert fetch.jobs[0].description == (
        "Equipo digital h\u00edbrido."
    )


def test_nested_csb_description_is_complete():
    description = _fetch_single_description(
        _detail_html_with_description(
            (
                "<span class=\"jobdescription\">"
                "<span>Generic intro</span>"
                "<div>Tu rol sera desarrollar "
                "servicios backend.</div>"
                "<div>Requisitos: Java, Spring "
                "Boot, APIs REST.</div>"
                "</span>"
                "<footer>Privacy / navigation / "
                "corporate text</footer>"
            )
        )
    )

    assert description == (
        "Generic intro Tu rol sera desarrollar "
        "servicios backend. Requisitos: Java, "
        "Spring Boot, APIs REST."
    )


def test_nested_itemprop_description_is_complete():
    description = _fetch_single_description(
        _detail_html_with_description(
            (
                "<div itemprop=\"description\">"
                "<p>Generic intro</p>"
                "<div><strong>Tu rol sera:</strong> "
                "desarrollar servicios backend.</div>"
                "<div><strong>Requisitos:</strong> "
                "Java, Spring Boot, APIs REST.</div>"
                "</div>"
            )
        )
    )

    assert description == (
        "Generic intro Tu rol sera: desarrollar "
        "servicios backend. Requisitos: Java, "
        "Spring Boot, APIs REST."
    )


def test_description_lists_remain_readable():
    description = _fetch_single_description(
        _detail_html_with_description(
            (
                "<div itemprop=\"description\">"
                "<p>Requisitos:</p>"
                "<ul><li>Java</li>"
                "<li>Spring Boot</li></ul>"
                "</div>"
            )
        )
    )

    assert description == (
        "Requisitos: Java Spring Boot"
    )


def test_description_boundary_excludes_footer():
    description = _fetch_single_description(
        _detail_html_with_description(
            (
                "<div itemprop=\"description\">"
                "<p>Role-specific responsibilities.</p>"
                "</div>"
                "<footer>Privacy / navigation / "
                "corporate text</footer>"
            )
        )
    )

    assert description == (
        "Role-specific responsibilities."
    )
    assert "Privacy" not in description


def test_missing_description_container_is_safe():
    description = _fetch_single_description(
        _detail_html_with_description(
            (
                "<main>Role text without recognized "
                "description container.</main>"
                "<footer>Privacy / navigation / "
                "corporate text</footer>"
            )
        )
    )

    assert description is None


def test_meta_itemprop_description_does_not_capture_page_text():
    description = _fetch_single_description(
        _detail_html_with_description(
            (
                "<meta itemprop=\"description\" "
                "content=\"SEO summary only\">"
                "<main>Visible page text after meta.</main>"
                "<footer>Privacy / navigation / "
                "corporate text</footer>"
            )
        )
    )

    assert description is None


def test_direct_edenor_style_listing_parsing():
    fetch = _fetch(
        board_url=(
            "https://career4.successfactors.com/"
            "career?company=edenor"
        ),
        responses={
            (
                "https://career4.successfactors.com/"
                "career?company=edenor"
            ): (
                200,
                (
                    "<html><a href=\"/career?"
                    "company=edenor&career_job_req_id="
                    "12345\">Analista Técnico</a>"
                    "</html>"
                ),
            ),
            (
                "https://career4.successfactors.com/"
                "career?company=edenor&"
                "career_job_req_id=12345"
            ): (
                200,
                _detail_html(
                    job_id="12345",
                    title="Analista Técnico",
                    location="CABA",
                    description="Puesto técnico.",
                ),
            ),
        },
    )

    assert fetch.snapshot_complete is False
    assert fetch.error_type == "PARTIAL_SNAPSHOT"
    assert fetch.variant == "DIRECT_LEGACY"
    assert fetch.jobs[0].external_id == "12345"


def test_successfactors_pagination():
    fetch = _fetch(
        board_url="https://example.jobs/",
        responses={
            "https://example.jobs/": (
                200,
                _board_html(),
            ),
            (
                "https://example.jobs/search/"
                "?createNewAlert=false"
            ): (
                200,
                _search_html(
                    total=3,
                    per_page=2,
                    links=[
                        ("1", "Uno", "AR"),
                        ("2", "Dos", "AR"),
                    ],
                ),
            ),
            (
                "https://example.jobs/search/"
                "?createNewAlert=false&startrow=2"
            ): (
                200,
                _search_html(
                    total=3,
                    per_page=2,
                    links=[
                        ("3", "Tres", "AR"),
                    ],
                ),
            ),
            "https://example.jobs/job/Uno/1/": (
                200,
                _detail_html("1", "Uno"),
            ),
            "https://example.jobs/job/Dos/2/": (
                200,
                _detail_html("2", "Dos"),
            ),
            "https://example.jobs/job/Tres/3/": (
                200,
                _detail_html("3", "Tres"),
            ),
        },
    )

    assert fetch.snapshot_complete is True
    assert [
        job.external_id
        for job in fetch.jobs
    ] == ["1", "2", "3"]


def test_stable_external_job_identity():
    assert extract_job_id(
        "https://custom.example/job/foo/123/"
    ) == "123"
    assert extract_job_id(
        "https://career4.successfactors.com/"
        "career?career_job_req_id=123"
    ) == "123"


def test_successfactors_external_identifier_strategy():
    assert successfactors_external_identifier(
        "https://claroempleos-aup.com/"
    ) == "claroempleos-aup.com"
    assert successfactors_external_identifier(
        "https://career4.successfactors.com/"
        "career?company=edenor"
    ) == (
        "career4.successfactors.com/"
        "career?company=edenor"
    )


def test_repeated_sync_is_idempotent(tmp_path):
    database, company_ats = _database_with_ats(
        tmp_path
    )
    service = _service(
        database,
        _fake_fetch(
            jobs=[
                _sf_job(
                    "1",
                    "Backend Engineer",
                    "first",
                )
            ]
        ),
    )

    first = service.run([company_ats])
    second = service.run([company_ats])

    rows = _job_rows(database)
    assert first.jobs_created == 1
    assert second.jobs_created == 0
    assert len(rows) == 1
    assert rows[0]["external_id"] == "1"


def test_changed_job_updates_existing_canonical_job(
    tmp_path,
):
    database, company_ats = _database_with_ats(
        tmp_path
    )
    service = _service(
        database,
        _fake_fetch(
            jobs=[
                _sf_job(
                    "1",
                    "Backend Engineer",
                    "first",
                )
            ]
        ),
    )
    service.run([company_ats])

    service = _service(
        database,
        _fake_fetch(
            jobs=[
                _sf_job(
                    "1",
                    "Backend Engineer II",
                    "changed",
                )
            ]
        ),
    )
    summary = service.run([company_ats])

    rows = _job_rows(database)
    assert summary.jobs_updated == 1
    assert len(rows) == 1
    assert rows[0]["title"] == (
        "Backend Engineer II"
    )
    assert rows[0]["is_active"] == 1


def test_complete_snapshot_deactivates_disappeared_jobs(
    tmp_path,
):
    database, company_ats = _database_with_ats(
        tmp_path
    )
    _seed_existing_job(database, company_ats)

    summary = _service(
        database,
        _fake_fetch(
            jobs=[],
            snapshot_complete=True,
        ),
    ).run([company_ats])

    rows = _job_rows(database)
    assert summary.jobs_deactivated == 1
    assert rows[0]["is_active"] == 0


def test_partial_legacy_static_links_do_not_deactivate_unseen_jobs(
    tmp_path,
):
    database, company_ats = _database_with_ats(
        tmp_path,
        board_url=(
            "https://career4.successfactors.com/"
            "career?company=example"
        ),
        external_identifier=(
            "career4.successfactors.com/"
            "career?company=example"
        ),
    )
    _seed_existing_job(database, company_ats)
    fetch = _fetch(
        board_url=(
            "https://career4.successfactors.com/"
            "career?company=example"
        ),
        responses={
            (
                "https://career4.successfactors.com/"
                "career?company=example"
            ): (
                200,
                (
                    "<html><a href=\"/career?"
                    "company=example&"
                    "career_job_req_id=new\">"
                    "Nuevo puesto</a></html>"
                ),
            ),
            (
                "https://career4.successfactors.com/"
                "career?company=example&"
                "career_job_req_id=new"
            ): (
                200,
                _detail_html(
                    job_id="new",
                    title="Nuevo puesto",
                ),
            ),
        },
    )

    summary = _service(
        database,
        _fake_fetch(fetch=fetch),
    ).run([company_ats])

    rows = _job_rows(database)
    rows_by_id = {
        row["external_id"]: row
        for row in rows
    }
    assert fetch.snapshot_complete is False
    assert summary.partial == 1
    assert summary.jobs_created == 1
    assert summary.jobs_deactivated == 0
    assert rows_by_id["old"]["is_active"] == 1
    assert rows_by_id["new"]["is_active"] == 1


def test_incomplete_listing_prevents_deactivation(
    tmp_path,
):
    database, company_ats = _database_with_ats(
        tmp_path
    )
    _seed_existing_job(database, company_ats)

    summary = _service(
        database,
        _fake_fetch(
            jobs=[],
            snapshot_complete=False,
            error_type="PARTIAL_SNAPSHOT",
            error_message="pagination failed",
        ),
    ).run([company_ats])

    rows = _job_rows(database)
    assert summary.partial == 1
    assert summary.jobs_deactivated == 0
    assert rows[0]["is_active"] == 1


def test_explicit_empty_legacy_board_safely_reconciles(
    tmp_path,
):
    database, company_ats = _database_with_ats(
        tmp_path,
        board_url=(
            "https://career4.successfactors.com/"
            "career?company=example"
        ),
        external_identifier=(
            "career4.successfactors.com/"
            "career?company=example"
        ),
    )
    _seed_existing_job(database, company_ats)
    fetch = _fetch(
        board_url=(
            "https://career4.successfactors.com/"
            "career?company=example"
        ),
        responses={
            (
                "https://career4.successfactors.com/"
                "career?company=example"
            ): (
                200,
                "<html>No hay puestos vacantes</html>",
            ),
        },
    )

    assert fetch.snapshot_complete is True
    assert fetch.jobs == []
    summary = _service(
        database,
        _fake_fetch(fetch=fetch),
    ).run([company_ats])

    assert summary.succeeded == 1
    assert summary.jobs_deactivated == 1
    assert _job_rows(database)[0]["is_active"] == 0


def test_failed_detail_fetch_prevents_deactivation():
    fetch = _fetch(
        board_url="https://example.jobs/",
        responses={
            "https://example.jobs/": (
                200,
                _board_html(),
            ),
            (
                "https://example.jobs/search/"
                "?createNewAlert=false"
            ): (
                200,
                _search_html(
                    total=1,
                    links=[
                        ("1", "Uno", "AR")
                    ],
                ),
            ),
            "https://example.jobs/job/Uno/1/": (
                500,
                "error",
            ),
        },
    )

    assert fetch.snapshot_complete is False
    assert fetch.error_type == (
        "DETAIL_FETCH_ERROR"
    )
    assert fetch.total == 1
    assert fetch.jobs == []


def test_empty_valid_board_safely_reconciles(
    tmp_path,
):
    database, company_ats = _database_with_ats(
        tmp_path
    )
    _seed_existing_job(database, company_ats)
    fetch = _fetch(
        board_url="https://example.jobs/",
        responses={
            "https://example.jobs/": (
                200,
                _board_html(),
            ),
            (
                "https://example.jobs/search/"
                "?createNewAlert=false"
            ): (
                200,
                "<html>No hay puestos vacantes</html>",
            ),
        },
    )

    assert fetch.snapshot_complete is True
    summary = _service(
        database,
        _fake_fetch(fetch=fetch),
    ).run([company_ats])

    assert summary.jobs_deactivated == 1
    assert _job_rows(database)[0]["is_active"] == 0


def test_blocked_response_does_not_deactivate_existing_job(
    tmp_path,
):
    database, company_ats = _database_with_ats(
        tmp_path
    )
    _seed_existing_job(database, company_ats)

    summary = _service(
        database,
        _erroring_client(
            httpx.HTTPStatusError(
                "blocked",
                request=httpx.Request(
                    "GET",
                    company_ats.board_url or "",
                ),
                response=httpx.Response(
                    403,
                    request=httpx.Request(
                        "GET",
                        company_ats.board_url or "",
                    ),
                ),
            )
        ),
    ).run([company_ats])

    assert summary.failed == 1
    assert summary.jobs_deactivated == 0
    assert _job_rows(database)[0]["is_active"] == 1


def test_custom_domain_remains_board_url():
    candidate = _detect_from_page(
        PageDocument(
            requested_url=(
                "https://empleos.gruposancorseguros.com/"
            ),
            final_url=(
                "https://empleos.gruposancorseguros.com/"
            ),
            status_code=200,
            html=(
                "<html>rmkcdn.successfactors.com"
                "<ul id=\"job-tile-list\"></ul>"
                "</html>"
            ),
            anchors=[],
            resources=[],
        )
    )[0]

    assert candidate.board_url == (
        "https://empleos.gruposancorseguros.com/"
    )


def test_successfactors_sync_only_processes_requested_provider(
    tmp_path,
):
    database, company_ats = _database_with_ats(
        tmp_path
    )
    repository = CompanyAtsRepository(database)
    other_company = CompanyRepository(database).add(
        Company(
            name="Other",
            normalized_name="other",
        )
    )
    assert other_company.id is not None
    other = repository.upsert(
        CompanyAts(
            company_id=other_company.id,
            provider=AtsProvider.GREENHOUSE,
            external_identifier="other",
            board_url=(
                "https://job-boards.greenhouse.io/other"
            ),
        )
    )
    records = (
        repository
        .list_active_primary_by_provider(
            AtsProvider.SUCCESSFACTORS
        )
    )

    summary = _service(
        database,
        _fake_fetch(
            jobs=[
                _sf_job("1", "Uno")
            ]
        ),
    ).run(records)

    rows = _job_rows(database)
    assert other.provider == (
        AtsProvider.GREENHOUSE
    )
    assert summary.processed == 1
    assert len(rows) == 1


def test_refresh_search_remains_unwired():
    contents = Path(
        "src/chamba_hunter/commands/"
        "refresh_search.py"
    ).read_text(encoding="utf-8")

    assert "sync_successfactors_jobs" not in contents
    assert "SUCCESSFACTORS" not in contents


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


def _fetch(
    *,
    board_url: str,
    responses: dict[str, tuple[int, str]],
) -> SuccessFactorsJobsFetch:
    return SuccessFactorsClient().fetch_jobs(
        board_url,
        client=_client(responses),
    )


def _board_html() -> str:
    return (
        "<html><form action=\"/search/\"></form>"
        "<script src=\"https://hcm17.sapsf.com/"
        "platform/js/j2w/core.js\"></script>"
        "</html>"
    )


def _search_html(
    *,
    total: int,
    links: list[tuple[str, str, str]],
    per_page: int = 25,
) -> str:
    records = len(links)
    tiles = "".join(
        (
            "<li class=\"job-tile job-id-"
            f"{job_id}\" data-url=\"/job/"
            f"{title.replace(' ', '-')}/{job_id}/\">"
            "<span data-careersite-propertyid=\"title\">"
            f"{title}</span>"
            "<span data-careersite-propertyid=\"location\">"
            f"{location}</span></li>"
        )
        for job_id, title, location in links
    )
    return (
        "<html><p>Mostrando 1 a "
        f"{records} de {total} puestos</p>"
        "<ul id=\"job-tile-list\" "
        f"data-per-page=\"{per_page}\" "
        f"data-record-returned=\"{records}\">"
        f"{tiles}</ul></html>"
    )


def _fetch_single_description(
    detail_html: str,
) -> str | None:
    fetch = _fetch(
        board_url="https://example.jobs/",
        responses={
            "https://example.jobs/": (
                200,
                _board_html(),
            ),
            (
                "https://example.jobs/search/"
                "?createNewAlert=false"
            ): (
                200,
                _search_html(
                    total=1,
                    links=[("1", "Uno", "AR")],
                ),
            ),
            "https://example.jobs/job/Uno/1/": (
                200,
                detail_html,
            ),
        },
    )
    assert fetch.snapshot_complete is True
    return fetch.jobs[0].description


def _detail_html_with_description(
    description_html: str,
) -> str:
    return (
        "<html><div class=\"jobDisplayShell\" "
        "itemscope itemtype=\"http://schema.org/JobPosting\">"
        "<h1><span itemprop=\"title\">Uno</span></h1>"
        f"{description_html}"
        "</div></html>"
    )


def _detail_html(
    job_id: str,
    title: str,
    location: str = "Argentina",
    description: str = "Public job description.",
) -> str:
    return (
        "<html><div class=\"jobDisplayShell\" "
        "itemscope itemtype=\"http://schema.org/JobPosting\">"
        "<span itemprop=\"jobLocation\">"
        "<span itemprop=\"address\">"
        f"<meta itemprop=\"addressLocality\" content=\"{location}\">"
        "<meta itemprop=\"addressCountry\" content=\"AR\">"
        "</span></span>"
        "<meta itemprop=\"datePosted\" "
        "content=\"2026-09-13\">"
        "<h1><span itemprop=\"title\">"
        f"{title}</span></h1>"
        "<span itemprop=\"description\">"
        "<span class=\"jobdescription\">"
        f"{description}</span></span>"
        "<a class=\"btn apply\" href=\"/talentcommunity/"
        f"apply/{job_id}/\">Postularme</a>"
        "</div></html>"
    )


class _FakeSuccessFactorsClient:
    def __init__(
        self,
        fetch: SuccessFactorsJobsFetch | None = None,
        error: Exception | None = None,
    ) -> None:
        self.fetch = fetch
        self.error = error

    def fetch_jobs(
        self,
        board_url: str,
    ) -> SuccessFactorsJobsFetch:
        if self.error is not None:
            raise self.error
        if self.fetch is None:
            raise RuntimeError(
                "No fake fetch configured."
            )
        return self.fetch


def _fake_fetch(
    *,
    jobs: list[
        SuccessFactorsJobDetail
    ] | None = None,
    snapshot_complete: bool = True,
    error_type: str | None = None,
    error_message: str | None = None,
    fetch: SuccessFactorsJobsFetch | None = None,
) -> _FakeSuccessFactorsClient:
    return _FakeSuccessFactorsClient(
        fetch=fetch
        or SuccessFactorsJobsFetch(
            http_status=200,
            total=len(jobs or []),
            jobs=jobs or [],
            snapshot_complete=(
                snapshot_complete
            ),
            variant="CAREER_SITE_BUILDER",
            error_type=error_type,
            error_message=error_message,
        )
    )


def _erroring_client(
    error: Exception,
) -> _FakeSuccessFactorsClient:
    return _FakeSuccessFactorsClient(
        error=error
    )


def _sf_job(
    external_id: str,
    title: str,
    description: str = "description",
) -> SuccessFactorsJobDetail:
    return SuccessFactorsJobDetail(
        external_id=external_id,
        title=title,
        description=description,
        location_text="Argentina",
        employment_type=None,
        published_at=datetime(
            2026,
            9,
            13,
            tzinfo=timezone.utc,
        ),
        job_url=(
            "https://example.jobs/job/"
            f"{title.replace(' ', '-')}/"
            f"{external_id}/"
        ),
        apply_url=(
            "https://example.jobs/"
            f"apply/{external_id}/"
        ),
        raw_payload={
            "provider": "SUCCESSFACTORS"
        },
    )


def _database_with_ats(
    tmp_path,
    *,
    board_url: str = "https://example.jobs/",
    external_identifier: str = "example.jobs",
) -> tuple[Database, CompanyAts]:
    database = Database(
        tmp_path / "test.db"
    )
    migrate(database)
    company = CompanyRepository(database).add(
        Company(
            name="Example",
            normalized_name="example",
            website_url="https://example.com/",
            careers_url="https://example.jobs/",
        )
    )
    assert company.id is not None
    company_ats = (
        CompanyAtsRepository(database)
        .upsert(
            CompanyAts(
                company_id=company.id,
                provider=(
                    AtsProvider
                    .SUCCESSFACTORS
                ),
                external_identifier=(
                    external_identifier
                ),
                board_url=(
                    board_url
                ),
            )
        )
    )
    return database, company_ats


def _service(
    database: Database,
    client,
) -> SuccessFactorsJobIngestionService:
    return SuccessFactorsJobIngestionService(
        successfactors_client=client,
        company_ats_repository=(
            CompanyAtsRepository(database)
        ),
        job_repository=JobRepository(database),
        tracing_repository=(
            TracingRepository(database)
        ),
    )


def _seed_existing_job(
    database: Database,
    company_ats: CompanyAts,
) -> None:
    assert company_ats.id is not None
    JobRepository(database).sync_board_jobs(
        company_ats=company_ats,
        seen_at=datetime(
            2026,
            9,
            13,
            tzinfo=timezone.utc,
        ),
        jobs=[
            Job(
                company_id=company_ats.company_id,
                company_ats_id=company_ats.id,
                external_id="old",
                title="Old Job",
            )
        ],
    )


def _job_rows(
    database: Database,
):
    with database.connection() as connection:
        return connection.execute(
            """
            SELECT external_id, title, is_active
            FROM jobs
            ORDER BY external_id
            """
        ).fetchall()
