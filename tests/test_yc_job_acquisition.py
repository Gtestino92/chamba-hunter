from dataclasses import replace
from datetime import UTC, datetime
import json

import httpx
import pytest

from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate
from chamba_hunter.domain.enums import (
    SourceType,
    WorkplaceType,
)
from chamba_hunter.domain.job_leads import JobLead
from chamba_hunter.repositories.company_repository import (
    CompanyRepository,
)
from chamba_hunter.repositories.company_source_repository import (
    CompanySourceRepository,
)
from chamba_hunter.repositories.job_lead_repository import (
    JobLeadRepository,
)
from chamba_hunter.repositories.source_acquisition_state_repository import (
    SourceAcquisitionStateRepository,
)
from chamba_hunter.repositories.tracing_repository import (
    TracingRepository,
)
from chamba_hunter.schemas.inputs import CompanySeedInput
from chamba_hunter.services.company_import_service import (
    CompanyImportService,
)
from chamba_hunter.services.yc_job_acquisition_service import (
    YcJobAcquisitionService,
)
from chamba_hunter.sources.yc_jobs import (
    YcCompanyJobsFetch,
    YcJobPosting,
    YcJobsClient,
    YcJobsParseError,
    parse_yc_job_detail,
    parse_yc_jobs_listing,
)


def test_listing_extracts_multiple_deduped_job_ids() -> None:
    links = parse_yc_jobs_listing(
        """
        <html><body>
          <a href="/companies/acme/jobs/job-1">Backend Engineer</a>
          <a href="https://www.ycombinator.com/companies/acme/jobs/job-2">
            Platform Engineer
          </a>
          <a href="/companies/acme/jobs/job-1">Duplicate</a>
          <a href="/companies/other/jobs/job-3">Other company</a>
        </body></html>
        """,
        company_slug="acme",
        listing_url=(
            "https://www.ycombinator.com/"
            "companies/acme/jobs"
        ),
    )

    assert [
        link.job_id
        for link in links
    ] == ["job-1", "job-2"]
    assert links[0].url == (
        "https://www.ycombinator.com/"
        "companies/acme/jobs/job-1"
    )


def test_detail_normalizes_backend_remote_argentina() -> None:
    posting = parse_yc_job_detail(
        _job_detail_html(
            job_id="backend-123",
            title="Backend Engineer",
            description=(
                "<p>Build Java backend APIs for "
                "customers in Argentina.</p>"
            ),
            location_name="Remote - Argentina",
            job_location_type="TELECOMMUTE",
            employment_type="FULL_TIME",
            date_posted="2026-09-01T10:00:00Z",
            date_modified="2026-09-02T10:00:00Z",
            apply_url="https://jobs.example/apply/backend-123",
        ),
        company_slug="acme",
        job_url=(
            "https://www.ycombinator.com/"
            "companies/acme/jobs/backend-123"
        ),
    )

    assert posting.external_id == "backend-123"
    assert posting.company_slug == "acme"
    assert posting.title == "Backend Engineer"
    assert posting.description == (
        "Build Java backend APIs for customers "
        "in Argentina."
    )
    assert posting.location_text == (
        "Remote - Argentina"
    )
    assert posting.workplace_type == (
        WorkplaceType.REMOTE
    )
    assert posting.employment_type == (
        "FULL_TIME"
    )
    assert posting.apply_url == (
        "https://jobs.example/apply/backend-123"
    )
    assert posting.published_at == datetime(
        2026,
        9,
        1,
        10,
        tzinfo=UTC,
    )
    assert posting.source_updated_at == datetime(
        2026,
        9,
        2,
        10,
        tzinfo=UTC,
    )
    assert posting.raw_payload[
        "location_source"
    ] == "json_ld"


def test_structured_location_wins_over_visible_header() -> None:
    posting = parse_yc_job_detail(
        _job_detail_html(
            job_id="backend-123",
            title="Backend Engineer",
            location_name="San Francisco, CA",
            visible_location=(
                "Remote - North America"
            ),
        ),
        company_slug="acme",
        job_url=(
            "https://www.ycombinator.com/"
            "companies/acme/jobs/backend-123"
        ),
    )

    assert posting.location_text == (
        "San Francisco, CA"
    )
    assert posting.raw_payload[
        "location_source"
    ] == "json_ld"


def test_empty_structured_location_falls_back_to_visible_header() -> None:
    posting = parse_yc_job_detail(
        _job_detail_html(
            job_id=(
                "HQH7Z3O-senior-software-"
                "engineer-inference"
            ),
            title=(
                "Senior Software Engineer, "
                "Inference"
            ),
            location_name=None,
            visible_location=(
                "•Remote - North America"
            ),
        ),
        company_slug="assemblyai",
        job_url=(
            "https://www.ycombinator.com/"
            "companies/assemblyai/jobs/"
            "HQH7Z3O-senior-software-"
            "engineer-inference"
        ),
    )

    assert posting.location_text == (
        "Remote - North America"
    )
    assert posting.workplace_type == (
        WorkplaceType.REMOTE
    )
    assert posting.raw_payload[
        "location_source"
    ] == "visible_header"


def test_visible_header_strips_compensation_before_remote_location() -> None:
    posting = parse_yc_job_detail(
        _job_detail_html(
            job_id=(
                "HQH7Z3O-senior-software-"
                "engineer-inference"
            ),
            title=(
                "Senior Software Engineer, "
                "Inference"
            ),
            location_name=None,
            visible_location=(
                "$190K - $225K•Remote - "
                "North America"
            ),
        ),
        company_slug="assemblyai",
        job_url=(
            "https://www.ycombinator.com/"
            "companies/assemblyai/jobs/"
            "HQH7Z3O-senior-software-"
            "engineer-inference"
        ),
    )

    assert posting.location_text == (
        "Remote - North America"
    )
    assert posting.workplace_type == (
        WorkplaceType.REMOTE
    )


def test_visible_header_strips_alternate_compensation_range() -> None:
    posting = parse_yc_job_detail(
        _job_detail_html(
            job_id="design-123",
            title="Senior Design Engineer",
            location_name=None,
            visible_location=(
                "$180K - $240K•Remote - "
                "North America"
            ),
        ),
        company_slug="assemblyai",
        job_url=(
            "https://www.ycombinator.com/"
            "companies/assemblyai/jobs/"
            "design-123"
        ),
    )

    assert posting.location_text == (
        "Remote - North America"
    )


def test_visible_header_compensation_only_is_not_location() -> None:
    posting = parse_yc_job_detail(
        _job_detail_html(
            job_id="backend-123",
            title="Backend Engineer",
            location_name=None,
            visible_location=(
                "$190K - $225K"
            ),
        ),
        company_slug="acme",
        job_url=(
            "https://www.ycombinator.com/"
            "companies/acme/jobs/backend-123"
        ),
    )

    assert posting.location_text is None
    assert posting.workplace_type == (
        WorkplaceType.UNKNOWN
    )


def test_later_company_hq_is_not_used_as_visible_job_location() -> None:
    posting = parse_yc_job_detail(
        _job_detail_html(
            job_id="backend-123",
            title="Backend Engineer",
            location_name=None,
            visible_location=None,
            body_extra="""
            <section>
              <h2>About Acme</h2>
              <p>Company headquarters: San Francisco, CA</p>
            </section>
            """,
        ),
        company_slug="acme",
        job_url=(
            "https://www.ycombinator.com/"
            "companies/acme/jobs/backend-123"
        ),
    )

    assert posting.location_text is None
    assert posting.workplace_type == (
        WorkplaceType.UNKNOWN
    )


def test_title_metadata_is_not_used_as_visible_job_header() -> None:
    posting = parse_yc_job_detail(
        _job_detail_html(
            job_id="backend-123",
            title="Backend Engineer",
            location_name=None,
            include_body_title=False,
            visible_location=(
                "Remote - North America"
            ),
        ),
        company_slug="acme",
        job_url=(
            "https://www.ycombinator.com/"
            "companies/acme/jobs/backend-123"
        ),
    )

    assert posting.location_text is None
    assert posting.workplace_type == (
        WorkplaceType.UNKNOWN
    )


def test_missing_structured_and_visible_location_stays_unknown() -> None:
    posting = parse_yc_job_detail(
        _job_detail_html(
            job_id="backend-123",
            title="Backend Engineer",
            location_name=None,
            visible_location=None,
        ),
        company_slug="acme",
        job_url=(
            "https://www.ycombinator.com/"
            "companies/acme/jobs/backend-123"
        ),
    )

    assert posting.location_text is None
    assert posting.workplace_type == (
        WorkplaceType.UNKNOWN
    )


def test_role_specific_apply_link_wins_over_generic_yc_apply() -> None:
    posting = parse_yc_job_detail(
        _job_detail_html(
            job_id="backend-123",
            title="Backend Engineer",
            apply_url=(
                "https://account.ycombinator.com/"
                "authenticate?continue=https%3A%2F%2F"
                "www.workatastartup.com%2Fapplication"
                "%3Fsignup_job_id%3Dbackend-123"
            ),
            include_generic_yc_apply=True,
        ),
        company_slug="acme",
        job_url=(
            "https://www.ycombinator.com/"
            "companies/acme/jobs/backend-123"
        ),
    )

    assert posting.apply_url is not None
    assert posting.apply_url.startswith(
        "https://account.ycombinator.com/"
        "authenticate?"
    )
    assert posting.apply_url != (
        "https://www.ycombinator.com/apply"
    )


def test_only_generic_yc_apply_link_is_rejected() -> None:
    posting = parse_yc_job_detail(
        _job_detail_html(
            job_id="backend-123",
            title="Backend Engineer",
            include_role_apply=False,
            include_generic_yc_apply=True,
        ),
        company_slug="acme",
        job_url=(
            "https://www.ycombinator.com/"
            "companies/acme/jobs/backend-123"
        ),
    )

    assert posting.apply_url is None


def test_role_specific_external_apply_url_is_preserved() -> None:
    posting = parse_yc_job_detail(
        _job_detail_html(
            job_id="backend-123",
            title="Backend Engineer",
            apply_url=(
                "https://jobs.example/apply/"
                "backend-123"
            ),
        ),
        company_slug="acme",
        job_url=(
            "https://www.ycombinator.com/"
            "companies/acme/jobs/backend-123"
        ),
    )

    assert posting.apply_url == (
        "https://jobs.example/apply/"
        "backend-123"
    )


def test_listing_zero_jobs_is_allowed() -> None:
    links = parse_yc_jobs_listing(
        """
        <html><body>
          <h1>No jobs at Acme</h1>
          <p>Acme is not currently hiring.</p>
        </body></html>
        """,
        company_slug="acme",
        listing_url=(
            "https://www.ycombinator.com/"
            "companies/acme/jobs"
        ),
    )

    assert links == ()


def test_malformed_listing_raises() -> None:
    with pytest.raises(YcJobsParseError):
        parse_yc_jobs_listing(
            "<html><body><nav>Companies Jobs</nav></body></html>",
            company_slug="acme",
            listing_url=(
                "https://www.ycombinator.com/"
                "companies/acme/jobs"
            ),
        )


def test_client_skips_failed_detail_while_other_jobs_succeed() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        if request.url.path == "/companies/acme/jobs":
            return httpx.Response(
                200,
                text="""
                <a href="/companies/acme/jobs/job-1">Job 1</a>
                <a href="/companies/acme/jobs/job-2">Job 2</a>
                """,
            )

        if (
            request.url.path
            == "/companies/acme/jobs/job-1"
        ):
            return httpx.Response(
                200,
                text=_job_detail_html(
                    job_id="job-1",
                    title="Backend Engineer",
                ),
            )

        return httpx.Response(
            500,
            text="broken",
        )

    client = YcJobsClient(
        request_delay_seconds=0,
        transport=httpx.MockTransport(
            handler
        ),
    )

    fetch = client.fetch_company_jobs(
        "acme"
    )

    assert fetch.job_links_discovered == 2
    assert fetch.details_fetched == 1
    assert fetch.detail_failures == 1
    assert fetch.skipped_invalid == 0
    assert [
        job.external_id
        for job in fetch.jobs
    ] == ["job-1"]


def test_service_idempotent_second_ingestion_reobserves_without_duplicates(
    tmp_path,
) -> None:
    database = _database(tmp_path)
    company_id = _import_yc_company(
        database,
        slug="acme",
    )
    posting = _posting(
        external_id="job-1",
        company_slug="acme",
    )
    service = _service(
        database,
        _FakeYcJobsClient(
            {
                "acme": YcCompanyJobsFetch(
                    company_slug="acme",
                    listing_url="https://yc/acme/jobs",
                    job_links_discovered=1,
                    details_fetched=1,
                    detail_failures=0,
                    skipped_invalid=0,
                    jobs=(posting,),
                )
            }
        ),
    )

    first = service.run()
    first_row = _job_lead_row(
        database,
        "job-1",
    )
    second = service.run()
    second_row = _job_lead_row(
        database,
        "job-1",
    )

    assert first.jobs_created == 1
    assert first.jobs_updated == 0
    assert second.jobs_created == 0
    assert second.jobs_updated == 1
    assert _job_lead_count(database) == 1
    assert first_row["company_id"] == company_id
    assert second_row["first_seen_at"] == (
        first_row["first_seen_at"]
    )
    assert second_row["is_active"] == 1


def test_missing_job_later_does_not_deactivate_existing_lead(
    tmp_path,
) -> None:
    database = _database(tmp_path)
    _import_yc_company(
        database,
        slug="acme",
    )
    client = _SequencedYcJobsClient(
        [
            YcCompanyJobsFetch(
                company_slug="acme",
                listing_url="https://yc/acme/jobs",
                job_links_discovered=2,
                details_fetched=2,
                detail_failures=0,
                skipped_invalid=0,
                jobs=(
                    _posting(
                        external_id="job-1",
                        company_slug="acme",
                    ),
                    _posting(
                        external_id="job-2",
                        company_slug="acme",
                        title="Platform Engineer",
                    ),
                ),
            ),
            YcCompanyJobsFetch(
                company_slug="acme",
                listing_url="https://yc/acme/jobs",
                job_links_discovered=1,
                details_fetched=1,
                detail_failures=0,
                skipped_invalid=0,
                jobs=(
                    _posting(
                        external_id="job-1",
                        company_slug="acme",
                    ),
                ),
            ),
        ]
    )
    service = _service(
        database,
        client,
    )

    service.run()
    service.run()

    assert _job_lead_count(database) == 2
    assert _job_lead_row(
        database,
        "job-1",
    )["is_active"] == 1
    assert _job_lead_row(
        database,
        "job-2",
    )["is_active"] == 1


def test_distinct_yc_external_ids_with_same_title_remain_distinct(
    tmp_path,
) -> None:
    database = _database(tmp_path)
    _import_yc_company(
        database,
        slug="assemblyai",
    )
    service = _service(
        database,
        _FakeYcJobsClient(
            {
                "assemblyai": YcCompanyJobsFetch(
                    company_slug="assemblyai",
                    listing_url=(
                        "https://yc/assemblyai/jobs"
                    ),
                    job_links_discovered=2,
                    details_fetched=2,
                    detail_failures=0,
                    skipped_invalid=0,
                    jobs=(
                        _posting(
                            external_id=(
                                "HQH7Z3O-senior-"
                                "software-engineer-"
                                "inference"
                            ),
                            company_slug=(
                                "assemblyai"
                            ),
                            title=(
                                "Senior Software "
                                "Engineer, Inference"
                            ),
                        ),
                        _posting(
                            external_id=(
                                "DkVxJde-senior-"
                                "software-engineer-"
                                "inference"
                            ),
                            company_slug=(
                                "assemblyai"
                            ),
                            title=(
                                "Senior Software "
                                "Engineer, Inference"
                            ),
                        ),
                    ),
                )
            }
        ),
    )

    summary = service.run()

    assert summary.jobs_created == 2
    assert _job_lead_count(database) == 2
    assert _job_lead_row(
        database,
        (
            "HQH7Z3O-senior-software-"
            "engineer-inference"
        ),
    )["title"] == (
        "Senior Software Engineer, "
        "Inference"
    )
    assert _job_lead_row(
        database,
        (
            "DkVxJde-senior-software-"
            "engineer-inference"
        ),
    )["title"] == (
        "Senior Software Engineer, "
        "Inference"
    )


def test_partial_failing_fetch_does_not_deactivate_existing_leads(
    tmp_path,
) -> None:
    database = _database(tmp_path)
    _import_yc_company(
        database,
        slug="acme",
    )
    client = _SequencedYcJobsClient(
        [
            YcCompanyJobsFetch(
                company_slug="acme",
                listing_url="https://yc/acme/jobs",
                job_links_discovered=1,
                details_fetched=1,
                detail_failures=0,
                skipped_invalid=0,
                jobs=(
                    _posting(
                        external_id="job-1",
                        company_slug="acme",
                    ),
                ),
            ),
            RuntimeError(
                "listing failed"
            ),
        ]
    )
    service = _service(
        database,
        client,
    )

    service.run()
    summary = service.run()

    assert summary.companies_failed == 1
    assert _job_lead_count(database) == 1
    assert _job_lead_row(
        database,
        "job-1",
    )["is_active"] == 1


def test_repository_validation_accepts_yc_and_rejects_unsupported(
    tmp_path,
) -> None:
    database = _database(tmp_path)
    company_id = _import_yc_company(
        database,
        slug="acme",
    )
    repository = JobLeadRepository(
        database
    )
    seen_at = datetime(
        2026,
        9,
        1,
        tzinfo=UTC,
    )

    counts = repository.upsert_source_jobs(
        SourceType.YC,
        [
            JobLead(
                company_id=company_id,
                source_type=SourceType.YC,
                external_id="yc-job",
                title="Backend Engineer",
                first_seen_at=seen_at,
                last_seen_at=seen_at,
            )
        ],
        seen_at,
    )

    assert counts.created == 1

    with pytest.raises(ValueError):
        repository.upsert_source_jobs(
            SourceType.OTHER,
            [
                JobLead(
                    company_id=company_id,
                    source_type=SourceType.OTHER,
                    external_id="other-job",
                    title="Other Engineer",
                    first_seen_at=seen_at,
                    last_seen_at=seen_at,
                )
            ],
            seen_at,
        )


def test_explicit_existing_slug_selects_that_company(
    tmp_path,
) -> None:
    database = _database(tmp_path)
    _import_yc_company(
        database,
        slug="alpha",
    )
    _import_yc_company(
        database,
        slug="wasmer",
    )
    client = _FakeYcJobsClient(
        {
            "wasmer": _empty_fetch(
                "wasmer"
            )
        }
    )

    summary = _service(
        database,
        client,
    ).run(slugs=(" wasmer ",))

    assert client.called_slugs == [
        "wasmer"
    ]
    assert summary.requested_slugs == (
        "wasmer",
    )
    assert summary.missing_slugs == ()
    assert summary.companies_considered == 1
    assert summary.companies_fetched == 1


def test_repeated_slug_values_select_multiple_companies(
    tmp_path,
) -> None:
    database = _database(tmp_path)
    _import_yc_company(
        database,
        slug="wasmer",
    )
    _import_yc_company(
        database,
        slug="porter",
    )
    client = _FakeYcJobsClient(
        {
            "wasmer": _empty_fetch(
                "wasmer"
            ),
            "porter": _empty_fetch(
                "porter"
            ),
        }
    )

    summary = _service(
        database,
        client,
    ).run(slugs=("wasmer", "porter"))

    assert client.called_slugs == [
        "wasmer",
        "porter",
    ]
    assert summary.companies_considered == 2
    assert summary.companies_fetched == 2


def test_duplicate_requested_slug_is_deduplicated(
    tmp_path,
) -> None:
    database = _database(tmp_path)
    _import_yc_company(
        database,
        slug="wasmer",
    )
    client = _FakeYcJobsClient(
        {
            "wasmer": _empty_fetch(
                "wasmer"
            )
        }
    )

    summary = _service(
        database,
        client,
    ).run(
        slugs=(
            "Wasmer",
            " wasmer ",
            "WASMER",
        )
    )

    assert client.called_slugs == [
        "wasmer"
    ]
    assert summary.requested_slugs == (
        "Wasmer",
    )
    assert summary.companies_considered == 1


def test_slug_filtering_occurs_before_limit(
    tmp_path,
) -> None:
    database = _database(tmp_path)
    _import_yc_company(
        database,
        slug="alpha",
    )
    _import_yc_company(
        database,
        slug="porter",
    )
    client = _FakeYcJobsClient(
        {
            "porter": _empty_fetch(
                "porter"
            )
        }
    )

    summary = _service(
        database,
        client,
    ).run(
        slugs=("porter",),
        limit=1,
    )

    assert client.called_slugs == [
        "porter"
    ]
    assert summary.companies_considered == 1
    assert summary.missing_slugs == ()


def test_explicit_not_hiring_slug_is_still_fetched(
    tmp_path,
) -> None:
    database = _database(tmp_path)
    _import_yc_company(
        database,
        slug="wasmer",
        is_hiring=False,
    )
    client = _FakeYcJobsClient(
        {
            "wasmer": _empty_fetch(
                "wasmer"
            )
        }
    )

    summary = _service(
        database,
        client,
    ).run(slugs=("wasmer",))

    assert client.called_slugs == [
        "wasmer"
    ]
    assert summary.companies_skipped_not_hiring == 0
    assert summary.companies_fetched == 1


def test_untargeted_not_hiring_skip_behavior_is_preserved(
    tmp_path,
) -> None:
    database = _database(tmp_path)
    _import_yc_company(
        database,
        slug="wasmer",
        is_hiring=False,
    )
    client = _FakeYcJobsClient({})

    summary = _service(
        database,
        client,
    ).run()

    assert client.called_slugs == []
    assert summary.companies_considered == 1
    assert summary.companies_skipped_not_hiring == 1
    assert summary.companies_fetched == 0


def test_nonexistent_slug_does_not_fall_back_to_another_company(
    tmp_path,
) -> None:
    database = _database(tmp_path)
    _import_yc_company(
        database,
        slug="alpha",
    )
    client = _FakeYcJobsClient(
        {
            "alpha": _empty_fetch(
                "alpha"
            )
        }
    )

    summary = _service(
        database,
        client,
    ).run(slugs=("missing",))

    assert client.called_slugs == []
    assert summary.requested_slugs == (
        "missing",
    )
    assert summary.missing_slugs == (
        "missing",
    )
    assert summary.companies_considered == 0
    assert summary.companies_fetched == 0


def _database(tmp_path) -> Database:
    database = Database(
        tmp_path / "test.db"
    )
    migrate(database)
    return database


def _import_yc_company(
    database: Database,
    *,
    slug: str,
    is_hiring: bool = True,
) -> int:
    service = CompanyImportService(
        CompanyRepository(database),
        CompanySourceRepository(database),
    )
    result = service.import_seed(
        CompanySeedInput(
            name=f"{slug.title()} Inc",
            website_url=(
                f"https://{slug}.example"
            ),
            source_type=SourceType.YC,
            external_id=slug,
            source_url=(
                "https://www.ycombinator.com/"
                f"companies/{slug}"
            ),
        ),
        source_metadata={
            "is_hiring": is_hiring,
            "yc_id": 123,
        },
    )

    assert result.company.id is not None
    return result.company.id


def _service(
    database: Database,
    client,
) -> YcJobAcquisitionService:
    return YcJobAcquisitionService(
        client=client,
        company_source_repository=(
            CompanySourceRepository(
                database
            )
        ),
        job_lead_repository=(
            JobLeadRepository(database)
        ),
        state_repository=(
            SourceAcquisitionStateRepository(
                database
            )
        ),
        tracing_repository=(
            TracingRepository(database)
        ),
    )


def _posting(
    *,
    external_id: str,
    company_slug: str,
    title: str = "Backend Engineer",
) -> YcJobPosting:
    return YcJobPosting(
        external_id=external_id,
        company_slug=company_slug,
        title=title,
        description="Build backend systems.",
        location_text="Remote - Argentina",
        workplace_type=WorkplaceType.REMOTE,
        employment_type="FULL_TIME",
        job_url=(
            "https://www.ycombinator.com/"
            f"companies/{company_slug}/jobs/"
            f"{external_id}"
        ),
        apply_url=(
            "https://jobs.example/apply/"
            f"{external_id}"
        ),
        published_at=None,
        source_updated_at=None,
        raw_payload={
            "job_id": external_id,
            "company_slug": company_slug,
        },
    )


def _empty_fetch(
    slug: str,
) -> YcCompanyJobsFetch:
    return YcCompanyJobsFetch(
        company_slug=slug,
        listing_url=f"https://yc/{slug}/jobs",
        job_links_discovered=0,
        details_fetched=0,
        detail_failures=0,
        skipped_invalid=0,
        jobs=(),
    )


def _job_lead_count(
    database: Database,
) -> int:
    with database.connection() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS count FROM job_leads"
        ).fetchone()

    return int(row["count"])


def _job_lead_row(
    database: Database,
    external_id: str,
):
    with database.connection() as connection:
        row = connection.execute(
            """
            SELECT *
            FROM job_leads
            WHERE source_type = ?
              AND external_id = ?
            """,
            (
                SourceType.YC.value,
                external_id,
            ),
        ).fetchone()

    assert row is not None
    return row


class _FakeYcJobsClient:
    def __init__(
        self,
        fetches: dict[str, YcCompanyJobsFetch],
    ) -> None:
        self.fetches = fetches
        self.called_slugs: list[str] = []

    def fetch_company_jobs(
        self,
        company_slug: str,
    ) -> YcCompanyJobsFetch:
        self.called_slugs.append(
            company_slug
        )
        return self.fetches[
            company_slug
        ]


class _SequencedYcJobsClient:
    def __init__(
        self,
        results,
    ) -> None:
        self.results = list(results)

    def fetch_company_jobs(
        self,
        company_slug: str,
    ) -> YcCompanyJobsFetch:
        result = self.results.pop(0)

        if isinstance(
            result,
            Exception,
        ):
            raise result

        return replace(
            result,
            company_slug=company_slug,
        )


def _job_detail_html(
    *,
    job_id: str,
    title: str,
    description: str = "<p>Build backend systems.</p>",
    location_name: str = "San Francisco, CA",
    job_location_type: str | None = None,
    employment_type: str = "FULL_TIME",
    date_posted: str | None = None,
    date_modified: str | None = None,
    apply_url: str = "https://jobs.example/apply",
    apply_text: str = "Apply to role ›",
    include_role_apply: bool = True,
    include_generic_yc_apply: bool = False,
    include_body_title: bool = True,
    visible_location: str | None = None,
    body_extra: str = "",
) -> str:
    json_ld = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": title,
        "description": description,
        "employmentType": employment_type,
        "jobLocation": (
            {
                "@type": "Place",
                "name": location_name,
            }
            if location_name is not None
            else [
                {
                    "@type": "Place",
                    "address": {
                        "@type": (
                            "PostalAddress"
                        ),
                        "addressLocality": None,
                        "addressRegion": None,
                        "addressCountry": None,
                    },
                }
            ]
        ),
    }

    if job_location_type is not None:
        json_ld["jobLocationType"] = (
            job_location_type
        )

    if date_posted is not None:
        json_ld["datePosted"] = (
            date_posted
        )

    if date_modified is not None:
        json_ld["dateModified"] = (
            date_modified
        )

    body_title = (
        f"<h1>{title}</h1>"
        if include_body_title
        else ""
    )
    body_location = (
        f"<p>{visible_location}</p>"
        if visible_location is not None
        else ""
    )
    role_apply = (
        f'<a href="{apply_url}">{apply_text}</a>'
        if include_role_apply
        else ""
    )
    generic_apply = (
        '<a href="https://www.ycombinator.com/apply">Apply</a>'
        if include_generic_yc_apply
        else ""
    )

    return f"""
    <html>
      <head>
        <title>{title} at Acme | Y Combinator</title>
        <script type="application/ld+json">
          {json.dumps(json_ld)}
        </script>
      </head>
      <body>
        <nav>
          {generic_apply}
        </nav>
        <main>
          {body_title}
          {body_location}
          <h2>Job type</h2>
          <p>Full-time</p>
          {role_apply}
          <p>Job id {job_id}</p>
          {body_extra}
        </main>
      </body>
    </html>
    """
