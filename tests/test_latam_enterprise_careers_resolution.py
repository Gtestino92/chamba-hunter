import httpx

from chamba_hunter.commands.fingerprint_latam_enterprise_ats import (
    select_latam_enterprise_companies,
)
from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate
from chamba_hunter.domain.enums import SourceType
from chamba_hunter.domain.models import Company
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
from chamba_hunter.services.latam_enterprise_careers_resolution_service import (
    LatamEnterpriseCareersResolutionService,
)


def test_existing_homepage_link_resolves():
    result = _service().resolve_company(
        company=_company(),
        client=_client(
            {
                "https://example.com/": (
                    200,
                    """
                    <html>
                      <a href="/trabaja-con-nosotros">
                        Trabajá con nosotros
                      </a>
                    </html>
                    """,
                ),
                "https://example.com/trabaja-con-nosotros": (
                    200,
                    """
                    <html>
                      <title>Trabajá con nosotros</title>
                      <h1>Vacantes abiertas</h1>
                      <a href="/jobs/1">Postulate</a>
                    </html>
                    """,
                ),
            }
        ),
    )

    assert result.status == "RESOLVED"
    assert result.method == "HOMEPAGE_LINK"


def test_external_ats_link_from_homepage_resolves_without_registration():
    result = _service().resolve_company(
        company=_company(),
        client=_client(
            {
                "https://example.com/": (
                    200,
                    """
                    <html>
                      <a href="https://acme.wd5.myworkdayjobs.com/jobs">
                        Empleos
                      </a>
                    </html>
                    """,
                ),
                "https://acme.wd5.myworkdayjobs.com/jobs": (
                    200,
                    "<html><h1>Careers</h1></html>",
                ),
            }
        ),
    )

    assert result.status == "RESOLVED"
    assert result.method == "HOMEPAGE_LINK"
    assert result.confidence is not None
    assert result.confidence >= 0.85


def test_common_path_success():
    result = _service().resolve_company(
        company=_company(),
        client=_client(
            {
                "https://example.com/": (
                    200,
                    "<html><p>Corporate site</p></html>",
                ),
                "https://example.com/careers": (
                    200,
                    """
                    <html>
                      <h1>Careers</h1>
                      <a href="/careers/software-engineer">
                        Software Engineer
                      </a>
                      <button>Apply now</button>
                    </html>
                    """,
                ),
            },
            default=(404, "Not found"),
        ),
    )

    assert result.status == "RESOLVED"
    assert result.method == "COMMON_PATH"


def test_common_path_false_positive_is_unresolved():
    result = _service(
        common_paths=("/careers",),
        subdomain_prefixes=(),
    ).resolve_company(
        company=_company(),
        client=_client(
            {
                "https://example.com/": (
                    200,
                    "<html><p>Corporate site</p></html>",
                ),
                "https://example.com/careers": (
                    200,
                    """
                    <html>
                      <h1>Customer stories</h1>
                      <p>Products and support.</p>
                    </html>
                    """,
                ),
                "https://example.com/robots.txt": (
                    404,
                    "Not found",
                ),
                "https://example.com/sitemap.xml": (
                    404,
                    "Not found",
                ),
            },
            default=(404, "Not found"),
        ),
    )

    assert result.status == "UNRESOLVED"


def test_sitemap_resolution():
    result = _service(
        common_paths=(),
        subdomain_prefixes=(),
    ).resolve_company(
        company=_company(),
        client=_client(
            {
                "https://example.com/": (
                    200,
                    "<html>Corporate site</html>",
                ),
                "https://example.com/robots.txt": (
                    404,
                    "Not found",
                ),
                "https://example.com/sitemap.xml": (
                    200,
                    """
                    <urlset>
                      <url>
                        <loc>https://example.com/empleos</loc>
                      </url>
                    </urlset>
                    """,
                ),
                "https://example.com/empleos": (
                    200,
                    """
                    <html>
                      <h1>Empleos</h1>
                      <a href="/empleos/analista">
                        Ver vacantes
                      </a>
                    </html>
                    """,
                ),
            },
            default=(404, "Not found"),
        ),
    )

    assert result.status == "RESOLVED"
    assert result.method == "SITEMAP"


def test_robots_txt_sitemap_declaration():
    result = _service(
        common_paths=(),
        subdomain_prefixes=(),
    ).resolve_company(
        company=_company(),
        client=_client(
            {
                "https://example.com/": (
                    200,
                    "<html>Corporate site</html>",
                ),
                "https://example.com/robots.txt": (
                    200,
                    "Sitemap: https://example.com/jobs-sitemap.xml",
                ),
                "https://example.com/jobs-sitemap.xml": (
                    200,
                    """
                    <urlset>
                      <url>
                        <loc>https://example.com/vacantes</loc>
                      </url>
                    </urlset>
                    """,
                ),
                "https://example.com/vacantes": (
                    200,
                    "<html><h1>Vacantes</h1>Postulate</html>",
                ),
            },
            default=(404, "Not found"),
        ),
    )

    assert result.status == "RESOLVED"
    assert result.method == "SITEMAP"


def test_sitemap_bounding_limits_documents():
    requested: list[str] = []

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        requested.append(str(request.url))
        url = str(request.url)
        if url == "https://example.com/":
            return _response(
                request,
                200,
                "<html>Corporate</html>",
            )
        if url == "https://example.com/robots.txt":
            return _response(
                request,
                404,
                "Not found",
            )
        if url == "https://example.com/sitemap.xml":
            return _response(
                request,
                200,
                """
                <sitemapindex>
                  <sitemap><loc>https://example.com/s1.xml</loc></sitemap>
                  <sitemap><loc>https://example.com/s2.xml</loc></sitemap>
                  <sitemap><loc>https://example.com/s3.xml</loc></sitemap>
                </sitemapindex>
                """,
            )
        if url.endswith(".xml"):
            return _response(
                request,
                200,
                "<urlset></urlset>",
            )
        return _response(
            request,
            404,
            "Not found",
        )

    result = _service(
        common_paths=(),
        subdomain_prefixes=(),
        max_sitemap_documents=2,
    ).resolve_company(
        company=_company(),
        client=httpx.Client(
            transport=httpx.MockTransport(
                handler
            ),
            follow_redirects=True,
        ),
    )

    fetched_sitemaps = [
        url
        for url in requested
        if url.endswith(".xml")
    ]
    assert result.status == "UNRESOLVED"
    assert len(fetched_sitemaps) == 2


def test_blocked_page_returns_blocked():
    result = _service().resolve_company(
        company=_company(),
        client=_client(
            {
                "https://example.com/": (
                    403,
                    "Forbidden",
                )
            }
        ),
    )

    assert result.status == "BLOCKED"
    assert result.http_status == 403


def test_existing_careers_url_is_skipped():
    result = _service().resolve_company(
        company=_company(
            careers_url=(
                "https://example.com/jobs"
            )
        ),
        client=_client({}),
    )

    assert result.status == "SKIPPED"
    assert (
        result.existing_careers_url
        == "https://example.com/jobs"
    )


def test_preview_semantics_do_not_mutate(tmp_path):
    database = Database(tmp_path / "test.db")
    migrate(database)
    imported = _import_company(database)

    summary = _service(database).run(
        [imported],
        apply=False,
        client=_client(
            {
                "https://example.com/": (
                    200,
                    '<a href="/careers">Careers</a>',
                ),
                "https://example.com/careers": (
                    200,
                    "<h1>Careers</h1>Apply now",
                ),
            }
        ),
    )

    unchanged = CompanyRepository(
        database
    ).get_by_id(imported.id or 0)
    assert summary.resolved == 1
    assert unchanged is not None
    assert unchanged.careers_url is None


def test_apply_semantics_fill_once(tmp_path):
    database = Database(tmp_path / "test.db")
    migrate(database)
    imported = _import_company(database)

    service = _service(database)
    summary = service.run(
        [imported],
        apply=True,
        client=_client(
            {
                "https://example.com/": (
                    200,
                    '<a href="/careers">Careers</a>',
                ),
                "https://example.com/careers": (
                    200,
                    "<h1>Careers</h1>Apply now",
                ),
            }
        ),
    )
    refreshed = CompanyRepository(
        database
    ).get_by_id(imported.id or 0)

    assert summary.applied == 1
    assert summary.overwritten == 0
    assert refreshed is not None
    assert (
        refreshed.careers_url
        == "https://example.com/careers"
    )

    second = service.run(
        [refreshed],
        apply=True,
        client=_client({}),
    )
    assert second.applied == 0
    assert second.overwritten == 0


def test_low_confidence_candidate_is_not_persisted(tmp_path):
    database = Database(tmp_path / "test.db")
    migrate(database)
    imported = _import_company(database)

    summary = _service(
        database,
        common_paths=("/careers",),
        subdomain_prefixes=(),
    ).run(
        [imported],
        apply=True,
        client=_client(
            {
                "https://example.com/": (
                    200,
                    "<html>Corporate</html>",
                ),
                "https://example.com/careers": (
                    200,
                    "<html>Generic corporate content</html>",
                ),
                "https://example.com/robots.txt": (
                    404,
                    "Not found",
                ),
                "https://example.com/sitemap.xml": (
                    404,
                    "Not found",
                ),
            },
            default=(404, "Not found"),
        ),
    )
    refreshed = CompanyRepository(
        database
    ).get_by_id(imported.id or 0)

    assert summary.applied == 0
    assert refreshed is not None
    assert refreshed.careers_url is None


def test_unrelated_external_url_is_not_accepted():
    result = _service(
        common_paths=(),
        subdomain_prefixes=(),
    ).resolve_company(
        company=_company(),
        client=_client(
            {
                "https://example.com/": (
                    200,
                    """
                    <html>
                      <a href="https://other.example/jobs">
                        Jobs article
                      </a>
                    </html>
                    """,
                ),
                "https://other.example/jobs": (
                    200,
                    "<html><h1>Jobs</h1>Apply now</html>",
                ),
                "https://example.com/robots.txt": (
                    404,
                    "Not found",
                ),
                "https://example.com/sitemap.xml": (
                    404,
                    "Not found",
                ),
            },
            default=(404, "Not found"),
        ),
    )

    assert result.status == "UNRESOLVED"


def test_default_selection_excludes_existing_careers_url(tmp_path):
    database = Database(tmp_path / "test.db")
    migrate(database)
    first = _import_company(database)
    second = _import_company(
        database,
        name="Has Careers",
        external_id="ar:has-careers",
        website_url="https://has.example/",
        careers_url="https://has.example/jobs",
    )

    companies = select_latam_enterprise_companies(
        company_repository=CompanyRepository(
            database
        ),
        source_repository=CompanySourceRepository(
            database
        ),
    )
    missing = [
        company
        for company in companies
        if (
            company.careers_url is None
            and company.website_url
            is not None
        )
    ]

    assert [company.id for company in missing] == [
        first.id
    ]
    assert second.id not in [
        company.id
        for company in missing
    ]


def _company(
    *,
    careers_url: str | None = None,
) -> Company:
    return Company(
        id=1,
        name="Example",
        normalized_name="example",
        website_url="https://example.com/",
        careers_url=careers_url,
        country="Argentina",
    )


def _service(
    database: Database | None = None,
    **kwargs,
) -> LatamEnterpriseCareersResolutionService:
    if database is None:
        database = Database(":memory:")
        migrate(database)
    return LatamEnterpriseCareersResolutionService(
        company_repository=CompanyRepository(
            database
        ),
        **kwargs,
    )


def _client(
    responses: dict[str, tuple[int, str]],
    *,
    default: tuple[int, str] | None = None,
) -> httpx.Client:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        request_url = str(request.url)
        response = (
            responses.get(request_url)
            or responses.get(
                request_url.rstrip("/")
            )
            or responses.get(
                request_url.rstrip("/") + "/"
            )
            or default
        )
        if response is None:
            raise AssertionError(
                f"Unexpected request: "
                f"{request_url}"
            )
        status_code, text = response
        return _response(
            request,
            status_code,
            text,
        )

    return httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )


def _response(
    request: httpx.Request,
    status_code: int,
    text: str,
) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        text=text,
        request=request,
    )


def _import_company(
    database: Database,
    *,
    name: str = "Example",
    external_id: str = "ar:example",
    website_url: str = "https://example.com/",
    careers_url: str | None = None,
) -> Company:
    imported = CompanyImportService(
        CompanyRepository(database),
        CompanySourceRepository(database),
    ).import_seed(
        CompanySeedInput(
            name=name,
            country="Argentina",
            website_url=website_url,
            careers_url=careers_url,
            source_type=(
                SourceType.LATAM_ENTERPRISE
            ),
            external_id=external_id,
        )
    )
    assert imported.company.id is not None
    return imported.company
