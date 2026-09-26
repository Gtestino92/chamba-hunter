from datetime import UTC, datetime
import json

import httpx

from chamba_hunter.db.connection import Database
from chamba_hunter.db.converters import json_from_db
from chamba_hunter.db.migrations import migrate
from chamba_hunter.domain.enums import (
    SourceType,
    WorkplaceType,
)
from chamba_hunter.domain.job_recency import (
    evaluate_source_recency,
)
from chamba_hunter.repositories.company_repository import (
    CompanyRepository,
)
from chamba_hunter.repositories.company_source_repository import (
    CompanySourceRepository,
)
from chamba_hunter.repositories.job_ats_hint_repository import (
    JobAtsHintRepository,
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
from chamba_hunter.services.company_import_service import (
    CompanyImportService,
)
from chamba_hunter.services.remoteco_job_acquisition_service import (
    REMOTECO_SCOPE_KEY,
    RemoteCoJobAcquisitionService,
)
from chamba_hunter.sources.remoteco import (
    REMOTECO_INTERNATIONAL_CATEGORY_URL,
    REMOTECO_CATEGORY_URLS,
    RemoteCoClient,
    RemoteCoDetailStatus,
    RemoteCoGeoClassification,
    RemoteCoListingEntry,
    canonical_remoteco_job_url,
    classify_remoteco_geography,
    parse_remoteco_detail,
    parse_remoteco_listing_page,
    remoteco_external_id,
)


def test_listing_parser_extracts_metadata_and_next_page() -> None:
    page = parse_remoteco_listing_page(
        _listing_page_one(),
        page_url=REMOTECO_CATEGORY_URLS[0],
        category_url=REMOTECO_CATEGORY_URLS[0],
    )

    assert page.next_url == (
        REMOTECO_CATEGORY_URLS[0] + "/page/2"
    )
    assert [
        entry.external_id
        for entry in page.entries
    ] == [
        "123e4567-e89b-12d3-a456-426614174000",
        "job-details/backend-engineer-no-uuid",
        "223e4567-e89b-12d3-a456-426614174000",
        "323e4567-e89b-12d3-a456-426614174000",
    ]
    assert page.entries[0].title_hint == (
        "Senior Backend Engineer"
    )
    assert page.entries[0].company_hint == (
        "Globex"
    )
    assert page.entries[0].posted_relative == (
        "3 days ago"
    )
    assert page.entries[0].remote_work_level == (
        "100% Remote Work"
    )
    assert page.entries[0].schedule == "Full-Time"
    assert page.entries[0].job_type == "Employee"
    assert page.entries[0].salary_text == (
        "$120k - $150k"
    )
    assert page.entries[0].location_text == (
        "Remote in Argentina, Brazil, Chile"
    )
    assert page.entries[0].geo_classification == (
        RemoteCoGeoClassification.POTENTIALLY_ELIGIBLE
    )
    assert page.entries[1].geo_classification == (
        RemoteCoGeoClassification.UNKNOWN
    )
    assert page.entries[2].geo_classification == (
        RemoteCoGeoClassification.EXPLICITLY_INELIGIBLE
    )
    assert page.locations_found == 3
    assert page.locations_missing == 1


def test_listing_parser_associates_split_location_structure() -> None:
    page = parse_remoteco_listing_page(
        _split_listing_structure_html(),
        page_url=REMOTECO_CATEGORY_URLS[0],
        category_url=REMOTECO_CATEGORY_URLS[0],
    )

    assert [
        (
            entry.title_hint,
            entry.company_hint,
            entry.location_text,
            entry.geo_classification,
        )
        for entry in page.entries
    ] == [
        (
            "Backend Engineer",
            "US Co",
            "Remote, US National",
            RemoteCoGeoClassification.EXPLICITLY_INELIGIBLE,
        ),
        (
            "Java Developer",
            "Canada Co",
            "Remote in Canada",
            RemoteCoGeoClassification.EXPLICITLY_INELIGIBLE,
        ),
        (
            "Platform Engineer",
            "Texas Co",
            "Hybrid Remote in Austin, TX",
            RemoteCoGeoClassification.EXPLICITLY_INELIGIBLE,
        ),
        (
            "Full Stack Engineer",
            "Anywhere Co",
            "Remote from Anywhere",
            RemoteCoGeoClassification.POTENTIALLY_ELIGIBLE,
        ),
        (
            "Software Engineer",
            "Argentina Co",
            "Remote in Argentina",
            RemoteCoGeoClassification.POTENTIALLY_ELIGIBLE,
        ),
        (
            "API Engineer",
            "Americas Co",
            "Remote in Americas",
            RemoteCoGeoClassification.UNKNOWN,
        ),
    ]
    assert page.locations_found == 6
    assert page.locations_missing == 0


def test_listing_parser_does_not_cross_contaminate_adjacent_jobs() -> None:
    page = parse_remoteco_listing_page(
        _split_listing_structure_html(),
        page_url=REMOTECO_CATEGORY_URLS[0],
        category_url=REMOTECO_CATEGORY_URLS[0],
    )

    us_job = page.entries[0]
    argentina_job = page.entries[4]

    assert us_job.company_hint == "US Co"
    assert us_job.location_text == "Remote, US National"
    assert argentina_job.company_hint == "Argentina Co"
    assert argentina_job.location_text == "Remote in Argentina"


def test_missing_listing_location_is_allowed_and_counted() -> None:
    page = parse_remoteco_listing_page(
        """
        <html><body>
          <div class="remote-job-listing">
            <div class="summary">
              <a href="/job-details/backend-no-location-f23e4567-e89b-12d3-a456-426614174000">
                Backend Engineer
              </a>
              <span>No Location Co</span>
              <span>Today</span>
              <span>100% Remote Work</span>
              <span>Full-Time</span>
              <span>Employee</span>
            </div>
          </div>
        </body></html>
        """,
        page_url=REMOTECO_CATEGORY_URLS[0],
        category_url=REMOTECO_CATEGORY_URLS[0],
    )

    assert len(page.entries) == 1
    assert page.entries[0].location_text is None
    assert page.entries[0].geo_classification == (
        RemoteCoGeoClassification.UNKNOWN
    )
    assert page.locations_found == 0
    assert page.locations_missing == 1


def test_pagination_next_detected_and_normalized() -> None:
    first = parse_remoteco_listing_page(
        _pagination_html(
            next_href=(
                "/remote-jobs/full-stack-developer/"
                "page/2/?utm_source=x#jobs"
            )
        ),
        page_url=(
            "https://remote.co/remote-jobs/"
            "full-stack-developer"
        ),
        category_url=(
            "https://remote.co/remote-jobs/"
            "full-stack-developer"
        ),
    )
    second = parse_remoteco_listing_page(
        _pagination_html(
            next_href=(
                "/remote-jobs/full-stack-developer/"
                "page/3/"
            )
        ),
        page_url=(
            "https://remote.co/remote-jobs/"
            "full-stack-developer/page/2"
        ),
        category_url=(
            "https://remote.co/remote-jobs/"
            "full-stack-developer"
        ),
    )

    assert first.next_url == (
        "https://remote.co/remote-jobs/"
        "full-stack-developer/page/2"
        "?utm_source=x"
    )
    assert second.next_url == (
        "https://remote.co/remote-jobs/"
        "full-stack-developer/page/3"
    )


def test_pagination_ignores_other_category_and_domain() -> None:
    other_category = parse_remoteco_listing_page(
        _pagination_html(
            next_href="/remote-jobs/accounting/page/2/"
        ),
        page_url=REMOTECO_CATEGORY_URLS[0],
        category_url=REMOTECO_CATEGORY_URLS[0],
    )
    other_domain = parse_remoteco_listing_page(
        _pagination_html(
            next_href="https://example.com/remote-jobs/back-end-developer/page/2/"
        ),
        page_url=REMOTECO_CATEGORY_URLS[0],
        category_url=REMOTECO_CATEGORY_URLS[0],
    )

    assert other_category.next_url is None
    assert other_domain.next_url is None


def test_bounded_pagination_stops_and_warns() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        url = str(request.url).rstrip("/")

        if url == REMOTECO_CATEGORY_URLS[0]:
            return httpx.Response(
                200,
                text=_pagination_html(
                    next_href=(
                        "/remote-jobs/back-end-developer/"
                        "page/2/"
                    )
                ),
            )

        if url == REMOTECO_CATEGORY_URLS[0] + "/page/2":
            return httpx.Response(
                200,
                text=_pagination_html(
                    next_href=(
                        "/remote-jobs/back-end-developer/"
                        "page/3/"
                    )
                ),
            )

        if url == REMOTECO_CATEGORY_URLS[0] + "/page/3":
            return httpx.Response(
                200,
                text=_pagination_html(
                    next_href=(
                        "/remote-jobs/back-end-developer/"
                        "page/4/"
                    )
                ),
            )

        if url in {
            category.rstrip("/")
            for category in REMOTECO_CATEGORY_URLS
        }:
            return httpx.Response(
                200,
                text="<html><body>No jobs</body></html>",
            )

        return httpx.Response(
            404,
            text="unexpected",
        )

    fetch = RemoteCoClient(
        transport=httpx.MockTransport(
            handler
        )
    ).fetch_jobs(
        max_pages_per_category=3,
        max_jobs=1,
        detail_workers=1,
    )

    assert fetch.pages_fetched == 7
    assert fetch.coverage_warnings == [
        (
            "Reached page limit for "
            f"{REMOTECO_CATEGORY_URLS[0]}; next page "
            "exists: https://remote.co/remote-jobs/"
            "back-end-developer/page/4"
        )
    ]


def test_canonical_url_prefers_uuid_identity() -> None:
    canonical = canonical_remoteco_job_url(
        (
            "https://www.remote.co/job-details/"
            "senior-engineer-123e4567-e89b-12d3-a456-426614174000"
            "?utm_source=x#apply"
        )
    )

    assert canonical == (
        "https://remote.co/job-details/"
        "senior-engineer-123e4567-e89b-12d3-a456-426614174000"
    )
    assert remoteco_external_id(canonical) == (
        "123e4567-e89b-12d3-a456-426614174000"
    )
    assert remoteco_external_id(
        "https://remote.co/job-details/backend-engineer"
    ) == "job-details/backend-engineer"


def test_geo_classifier_is_conservative() -> None:
    assert classify_remoteco_geography(
        "Remote in Buenos Aires, Argentina"
    ) == RemoteCoGeoClassification.POTENTIALLY_ELIGIBLE
    assert classify_remoteco_geography(
        "Remote, LATAM"
    ) == RemoteCoGeoClassification.POTENTIALLY_ELIGIBLE
    assert classify_remoteco_geography(
        "Remote, US National"
    ) == RemoteCoGeoClassification.EXPLICITLY_INELIGIBLE
    assert classify_remoteco_geography(
        "Remote in Canada or US National"
    ) == RemoteCoGeoClassification.EXPLICITLY_INELIGIBLE
    assert classify_remoteco_geography(
        "Remote in Austin, TX"
    ) == RemoteCoGeoClassification.EXPLICITLY_INELIGIBLE
    assert classify_remoteco_geography(
        "Hybrid Remote in Austin, TX"
    ) == RemoteCoGeoClassification.EXPLICITLY_INELIGIBLE
    assert classify_remoteco_geography(
        "Remote in Texas"
    ) == RemoteCoGeoClassification.EXPLICITLY_INELIGIBLE
    assert classify_remoteco_geography(
        "Remote in Argentina"
    ) == RemoteCoGeoClassification.POTENTIALLY_ELIGIBLE
    assert classify_remoteco_geography(
        "Remote in Argentina, Brazil, Chile"
    ) == RemoteCoGeoClassification.POTENTIALLY_ELIGIBLE
    assert classify_remoteco_geography(
        "Remote in South America"
    ) == RemoteCoGeoClassification.POTENTIALLY_ELIGIBLE
    assert classify_remoteco_geography(
        "Worldwide"
    ) == RemoteCoGeoClassification.POTENTIALLY_ELIGIBLE
    assert classify_remoteco_geography(
        "Remote from Anywhere"
    ) == RemoteCoGeoClassification.POTENTIALLY_ELIGIBLE
    assert classify_remoteco_geography(
        "Remote in Americas"
    ) == RemoteCoGeoClassification.UNKNOWN
    assert classify_remoteco_geography(
        "Remote in Europe"
    ) == RemoteCoGeoClassification.UNKNOWN
    assert classify_remoteco_geography(
        "Remote"
    ) == RemoteCoGeoClassification.UNKNOWN
    assert classify_remoteco_geography(
        None
    ) == RemoteCoGeoClassification.UNKNOWN


def test_client_prefilters_before_fetching_details() -> None:
    calls: list[str] = []

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        url = str(request.url).rstrip("/")
        calls.append(str(request.url))

        if url == REMOTECO_CATEGORY_URLS[0]:
            return httpx.Response(
                200,
                text=_listing_page_one(),
            )

        if url == REMOTECO_CATEGORY_URLS[0] + "/page/2":
            return httpx.Response(
                200,
                text=_listing_page_two(),
            )

        if str(request.url) in REMOTECO_CATEGORY_URLS:
            return httpx.Response(
                200,
                text="<html><body>No jobs</body></html>",
            )

        return httpx.Response(
            200,
            text=_detail_html(
                title="Senior Backend Engineer",
                company="Globex",
                remote_work_level="100% Remote Work",
                location="Remote in Argentina",
                date_posted="Today",
            ),
        )

    fetch = RemoteCoClient(
        transport=httpx.MockTransport(
            handler
        )
    ).fetch_jobs(
        max_pages_per_category=2,
        max_jobs=10,
        detail_workers=1,
    )

    assert fetch.pages_fetched == 6
    assert fetch.listing_rows == 6
    assert fetch.unique_jobs == 2
    assert fetch.duplicates_removed == 1
    assert fetch.explicit_geo_rejects == 2
    assert fetch.remote_level_rejects == 1
    assert fetch.unknown_geography == 1
    assert fetch.potentially_eligible == 2
    assert fetch.details_attempted == 2
    assert fetch.details_succeeded == 2
    assert fetch.details_enriched == 2
    assert fetch.details_partial_gated == 0
    assert len(fetch.coverage_warnings) == 1
    assert all(
        "us-national" not in call
        for call in calls
    )
    assert all(
        "onsite" not in call
        for call in calls
    )


def test_client_fetches_unknown_geography_details() -> None:
    calls: list[str] = []

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        calls.append(str(request.url))

        if (
            str(request.url).rstrip("/")
            == REMOTECO_CATEGORY_URLS[0].rstrip("/")
        ):
            return httpx.Response(
                200,
                text="""
                <article class="job-card">
                  <a href="/job-details/americas-engineer-523e4567-e89b-12d3-a456-426614174000">
                    Americas Engineer
                  </a>
                  <span>Ambiguous Co</span>
                  <span>Today</span>
                  <span>100% Remote Work</span>
                  <span>Remote in Americas</span>
                  <span>Full-Time</span>
                  <span>Employee</span>
                </article>
                """,
            )

        if str(request.url).rstrip("/") in {
            url.rstrip("/")
            for url in REMOTECO_CATEGORY_URLS
        }:
            return httpx.Response(
                200,
                text="<html><body>No jobs</body></html>",
            )

        return httpx.Response(
            200,
            text=_detail_html(
                title="Americas Engineer",
                company="Ambiguous Co",
                remote_work_level="100% Remote Work",
                location="Remote in Americas",
                date_posted="Today",
            ),
        )

    fetch = RemoteCoClient(
        transport=httpx.MockTransport(
            handler
        )
    ).fetch_jobs(
        max_pages_per_category=1,
        max_jobs=1,
        detail_workers=1,
    )

    assert fetch.explicit_geo_rejects == 0
    assert fetch.unknown_geography == 1
    assert fetch.details_attempted == 1
    assert fetch.details_succeeded == 1
    assert any(
        "americas-engineer" in call
        for call in calls
    )


def test_detail_without_description_remains_valid_partial_job() -> None:
    posting = parse_remoteco_detail(
        _gated_detail_html(
            title="Backend Engineer",
            company="Canonical Co",
            remote_work_level="100% Remote Work",
            location="Remote from Anywhere",
            date_posted="Today",
        ),
        entry=_entry(
            title="Backend Engineer",
            company="Canonical Co",
        ),
    )

    assert posting.description is None
    assert posting.company_name == "Canonical Co"
    assert posting.location_text == "Remote from Anywhere"
    assert posting.detail_status in {
        RemoteCoDetailStatus.PARTIAL,
        RemoteCoDetailStatus.GATED,
    }


def test_placeholder_company_is_rejected_for_listing_company() -> None:
    posting = parse_remoteco_detail(
        _gated_detail_html(
            title="Backend Engineer",
            company="Company details here",
            remote_work_level="100% Remote Work",
            location="Remote from Anywhere",
            date_posted="Today",
        ),
        entry=_entry(
            title="Backend Engineer",
            company="Canonical",
        ),
    )

    assert posting.company_name == "Canonical"
    assert posting.raw_payload["detail"][
        "company_placeholder_rejected"
    ] is True


def test_gated_detail_is_not_a_failure_or_abort() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        if str(request.url).rstrip("/") in {
            url.rstrip("/")
            for url in REMOTECO_CATEGORY_URLS
        }:
            return httpx.Response(
                200,
                text=_listing_page_for_titles(
                    [
                        (
                            "Gated Backend Engineer",
                            "Gated Co",
                            "gated-backend-engineer-623e4567-e89b-12d3-a456-426614174000",
                        )
                    ]
                ),
            )

        return httpx.Response(
            200,
            text=_gated_detail_html(
                title="Gated Backend Engineer",
                company="Company details here",
                remote_work_level="100% Remote Work",
                location="Remote from Anywhere",
                date_posted="Today",
            ),
        )

    fetch = RemoteCoClient(
        transport=httpx.MockTransport(
            handler
        )
    ).fetch_jobs(
        max_pages_per_category=1,
        max_jobs=5,
        detail_workers=1,
    )

    assert fetch.details_failed == 0
    assert fetch.details_partial_gated == 1
    assert len(fetch.jobs) == 1
    assert fetch.jobs[0].detail_status in {
        RemoteCoDetailStatus.PARTIAL,
        RemoteCoDetailStatus.GATED,
    }


def test_http_failure_counts_but_keeps_listing_baseline() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        if str(request.url).rstrip("/") in {
            url.rstrip("/")
            for url in REMOTECO_CATEGORY_URLS
        }:
            return httpx.Response(
                200,
                text=_listing_page_for_titles(
                    [
                        (
                            "Backend Engineer",
                            "Failure Co",
                            "backend-failure-723e4567-e89b-12d3-a456-426614174000",
                        )
                    ]
                ),
            )

        return httpx.Response(500)

    fetch = RemoteCoClient(
        transport=httpx.MockTransport(
            handler
        )
    ).fetch_jobs(
        max_pages_per_category=1,
        max_jobs=1,
        detail_workers=1,
    )

    assert fetch.details_failed == 1
    assert fetch.details_succeeded == 0
    assert fetch.jobs[0].detail_status == (
        RemoteCoDetailStatus.FAILED
    )
    assert fetch.jobs[0].title == "Backend Engineer"
    assert fetch.jobs[0].company_name == "Failure Co"


def test_detail_extracts_structured_fields_and_exact_date() -> None:
    posting = parse_remoteco_detail(
        _detail_html(
            title="Senior Backend Engineer",
            company="Globex",
            remote_work_level="Hybrid Remote Work",
            location="Remote in Buenos Aires, Argentina",
            date_posted="2026-09-20",
            apply_url=(
                "https://boards.greenhouse.io/"
                "globex/jobs/123"
            ),
            company_url="https://www.globex.com",
        ),
        entry=_entry(),
    )

    assert posting.title == "Senior Backend Engineer"
    assert posting.company_name == "Globex"
    assert posting.description == (
        "Build Python and Java APIs."
    )
    assert posting.location_text == (
        "Remote in Buenos Aires, Argentina"
    )
    assert posting.workplace_type_source == (
        "Hybrid Remote Work"
    )
    assert posting.employment_type == "Employee"
    assert posting.job_schedule == "Full-Time"
    assert posting.salary_text == "$120k - $150k"
    assert posting.career_level == "Senior"
    assert posting.categories == (
        "Software Development",
        "Java",
    )
    assert posting.apply_url == (
        "https://boards.greenhouse.io/"
        "globex/jobs/123"
    )
    assert posting.company_website_url == (
        "https://www.globex.com"
    )
    assert posting.published_at == datetime(
        2026,
        9,
        20,
        tzinfo=UTC,
    )
    assert posting.detail_status == RemoteCoDetailStatus.FULL


def test_detail_preserves_relative_without_fabricating_date() -> None:
    posting = parse_remoteco_detail(
        _detail_html(
            title="Java Engineer",
            company="Initech",
            remote_work_level="100% Remote Work",
            location="Remote",
            date_posted="Yesterday",
        ),
        entry=_entry(
            title="Java Engineer",
            company="Initech",
            posted_relative="New!",
        ),
    )

    assert posting.published_at is None
    assert posting.posted_relative == "New!"
    assert posting.raw_payload[
        "_chamba_source_enrichment"
    ]["posted_relative"] == "New!"


def test_international_category_is_configured() -> None:
    assert REMOTECO_INTERNATIONAL_CATEGORY_URL in (
        REMOTECO_CATEGORY_URLS
    )
    assert len(REMOTECO_CATEGORY_URLS) == 5


def test_international_filter_retains_technical_titles() -> None:
    fetch = _fetch_international_titles(
        [
            (
                "Backend Engineer",
                "Tech Co",
                "backend-engineer-823e4567-e89b-12d3-a456-426614174000",
            ),
            (
                "Full-Stack Engineer",
                "Stack Co",
                "full-stack-engineer-923e4567-e89b-12d3-a456-426614174000",
            ),
            (
                "Postgres Engineer",
                "Data Co",
                "postgres-engineer-a23e4567-e89b-12d3-a456-426614174000",
            ),
            (
                "Translator",
                "Words Co",
                "translator-b23e4567-e89b-12d3-a456-426614174000",
            ),
            (
                "Payroll Administrator",
                "Payroll Co",
                "payroll-c23e4567-e89b-12d3-a456-426614174000",
            ),
            (
                "Recruiter",
                "People Co",
                "recruiter-d23e4567-e89b-12d3-a456-426614174000",
            ),
        ]
    )

    assert fetch.international_non_tech_rejects == 3
    assert [
        job.title
        for job in fetch.jobs
    ] == [
        "Backend Engineer",
        "Full-Stack Engineer",
        "Postgres Engineer",
    ]


def test_duplicate_across_international_and_technical_is_one_job() -> None:
    duplicate_slug = (
        "backend-engineer-e23e4567-e89b-12d3-a456-426614174000"
    )

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        url = str(request.url).rstrip("/")

        if url == REMOTECO_CATEGORY_URLS[0]:
            return httpx.Response(
                200,
                text=_listing_page_for_titles(
                    [
                        (
                            "Backend Engineer",
                            "Dup Co",
                            duplicate_slug,
                        )
                    ]
                ),
            )

        if url == REMOTECO_INTERNATIONAL_CATEGORY_URL:
            return httpx.Response(
                200,
                text=_listing_page_for_titles(
                    [
                        (
                            "Backend Engineer",
                            "Dup Co",
                            duplicate_slug,
                        )
                    ]
                ),
            )

        if url in {
            category.rstrip("/")
            for category in REMOTECO_CATEGORY_URLS
        }:
            return httpx.Response(
                200,
                text="<html><body>No jobs</body></html>",
            )

        return httpx.Response(
            200,
            text=_detail_html(
                title="Backend Engineer",
                company="Dup Co",
                remote_work_level="100% Remote Work",
                location="Remote from Anywhere",
                date_posted="Today",
            ),
        )

    fetch = RemoteCoClient(
        transport=httpx.MockTransport(
            handler
        )
    ).fetch_jobs(
        max_pages_per_category=1,
        max_jobs=10,
        detail_workers=1,
    )

    assert fetch.unique_jobs == 1
    assert fetch.duplicates_removed == 1
    assert len(fetch.jobs) == 1


def test_preview_mode_performs_zero_persistence(
    tmp_path,
) -> None:
    database = Database(
        tmp_path / "test.db"
    )
    migrate(database)
    before = _table_counts(database)

    service = RemoteCoJobAcquisitionService(
        client=_partial_fetch_client()
    )

    summary = service.preview(
        max_pages_per_category=1,
        max_jobs=1,
        detail_workers=1,
    )

    assert summary.applied is False
    assert summary.normalized_jobs == 1
    assert _table_counts(database) == before


def test_apply_with_partial_detail_persists_listing_baseline(
    tmp_path,
) -> None:
    database = Database(
        tmp_path / "test.db"
    )
    migrate(database)

    service = _service(
        database,
        _partial_fetch_client(),
    )

    summary = service.run(
        max_pages_per_category=1,
        max_jobs=1,
        detail_workers=1,
    )

    assert summary.applied is True
    assert summary.companies_created == 1
    assert summary.jobs_created == 1
    assert summary.ats_hints_created == 0
    assert summary.details_partial_gated == 1

    with database.connection() as connection:
        sources = connection.execute(
            "SELECT * FROM company_sources"
        ).fetchall()
        leads = connection.execute(
            "SELECT * FROM job_leads"
        ).fetchall()
        hints = connection.execute(
            "SELECT * FROM job_ats_hints"
        ).fetchall()

    assert len(sources) == 1
    assert sources[0]["source_type"] == (
        SourceType.REMOTECO.value
    )
    assert sources[0]["external_id"] is None
    assert len(leads) == 1
    assert leads[0]["source_type"] == (
        SourceType.REMOTECO.value
    )
    assert leads[0]["workplace_type"] == (
        WorkplaceType.REMOTE.value
    )
    assert json_from_db(
        leads[0]["raw_payload_json"]
    )["_chamba_source_enrichment"][
        "posted_relative"
    ] == "Today"
    assert leads[0]["description"] is None
    assert json_from_db(
        leads[0]["raw_payload_json"]
    )["detail"]["status"] in (
        RemoteCoDetailStatus.PARTIAL.value,
        RemoteCoDetailStatus.GATED.value,
    )
    assert len(hints) == 0

    state = SourceAcquisitionStateRepository(
        database
    ).get(
        source_type=SourceType.REMOTECO,
        scope_key=REMOTECO_SCOPE_KEY,
    )
    assert state is not None
    assert state.metadata[
        "snapshot_semantics"
    ] == "PARTIAL_CURATED_SOURCE_RESPONSE"


def test_remoteco_relative_contributes_to_recency() -> None:
    now = datetime(
        2026,
        9,
        26,
        tzinfo=UTC,
    )

    today = evaluate_source_recency(
        now=now,
        published_at=None,
        raw_payload_json=json.dumps(
            {
                "_chamba_source_enrichment": {
                    "source": "REMOTECO",
                    "posted_relative": "Today",
                }
            }
        ),
    )
    three_days = evaluate_source_recency(
        now=now,
        published_at=None,
        raw_payload_json=json.dumps(
            {
                "_chamba_source_enrichment": {
                    "source": "REMOTECO",
                    "posted_relative": "3 days ago",
                }
            }
        ),
    )
    new_only = evaluate_source_recency(
        now=now,
        published_at=None,
        raw_payload_json=json.dumps(
            {
                "_chamba_source_enrichment": {
                    "source": "REMOTECO",
                    "posted_relative": "New!",
                }
            }
        ),
    )

    assert today.bucket == "VERY_RECENT"
    assert today.evidence_type == (
        "REMOTECO_POSTED_RELATIVE"
    )
    assert three_days.bucket == "VERY_RECENT"
    assert new_only.bucket == "UNKNOWN"


def _service(
    database: Database,
    client: RemoteCoClient,
) -> RemoteCoJobAcquisitionService:
    return RemoteCoJobAcquisitionService(
        client=client,
        company_import_service=(
            CompanyImportService(
                CompanyRepository(database),
                CompanySourceRepository(database),
            )
        ),
        job_lead_repository=(
            JobLeadRepository(database)
        ),
        ats_hint_repository=(
            JobAtsHintRepository(database)
        ),
        tracing_repository=(
            TracingRepository(database)
        ),
        state_repository=(
            SourceAcquisitionStateRepository(
                database
            )
        ),
    )


def _partial_fetch_client() -> RemoteCoClient:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        if (
            str(request.url).rstrip("/")
            == REMOTECO_CATEGORY_URLS[0].rstrip("/")
        ):
            return httpx.Response(
                200,
                text=_listing_page_for_titles(
                    [
                        (
                            "Senior Backend Engineer",
                            "Globex",
                            "senior-backend-engineer-123e4567-e89b-12d3-a456-426614174000",
                        )
                    ],
                    location=(
                        "Remote in Argentina"
                    ),
                ),
            )

        if str(request.url).rstrip("/") in {
            url.rstrip("/")
            for url in REMOTECO_CATEGORY_URLS
        }:
            return httpx.Response(
                200,
                text="<html><body>No jobs</body></html>",
            )

        return httpx.Response(
            200,
            text=_gated_detail_html(
                title="Senior Backend Engineer",
                company="Company details here",
                remote_work_level="100% Remote Work",
                location="Remote in Argentina",
                date_posted="Today",
            ),
        )

    return RemoteCoClient(
        transport=httpx.MockTransport(
            handler
        )
    )


def _fetch_international_titles(
    titles: list[tuple[str, str, str]],
):
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        url = str(request.url).rstrip("/")

        if url == REMOTECO_INTERNATIONAL_CATEGORY_URL:
            return httpx.Response(
                200,
                text=_listing_page_for_titles(
                    titles,
                    location=(
                        "Remote from Anywhere"
                    ),
                ),
            )

        if url in {
            category.rstrip("/")
            for category in REMOTECO_CATEGORY_URLS
        }:
            return httpx.Response(
                200,
                text="<html><body>No jobs</body></html>",
            )

        title = "Backend Engineer"
        company = "Tech Co"

        for candidate_title, candidate_company, slug in titles:
            if slug in str(request.url):
                title = candidate_title
                company = candidate_company
                break

        return httpx.Response(
            200,
            text=_detail_html(
                title=title,
                company=company,
                remote_work_level="100% Remote Work",
                location="Remote from Anywhere",
                date_posted="Today",
            ),
        )

    return RemoteCoClient(
        transport=httpx.MockTransport(
            handler
        )
    ).fetch_jobs(
        max_pages_per_category=1,
        max_jobs=10,
        detail_workers=1,
    )


def _table_counts(
    database: Database,
) -> dict[str, int]:
    tables = [
        "companies",
        "company_sources",
        "job_leads",
        "job_ats_hints",
        "runs",
        "run_steps",
        "source_acquisition_states",
    ]

    with database.connection() as connection:
        return {
            table: connection.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]
            for table in tables
        }


def _entry(
    *,
    title: str = "Senior Backend Engineer",
    company: str = "Globex",
    posted_relative: str | None = "Today",
) -> RemoteCoListingEntry:
    return RemoteCoListingEntry(
        external_id=(
            "123e4567-e89b-12d3-a456-426614174000"
        ),
        canonical_url=(
            "https://remote.co/job-details/"
            "senior-backend-engineer-"
            "123e4567-e89b-12d3-a456-426614174000"
        ),
        title_hint=title,
        company_hint=company,
        posted_relative=posted_relative,
        remote_work_level="100% Remote Work",
        schedule="Full-Time",
        job_type="Employee",
        salary_text="$120k - $150k",
        location_text="Remote in Argentina",
        geo_classification=(
            RemoteCoGeoClassification.POTENTIALLY_ELIGIBLE
        ),
        source_category_url=(
            REMOTECO_CATEGORY_URLS[0]
        ),
        source_listing_url=(
            REMOTECO_CATEGORY_URLS[0]
        ),
    )


def _listing_page_one() -> str:
    return """
    <html><body>
      <nav>
        <a href="/remote-jobs/accounting">Accounting</a>
      </nav>
      <article class="job-card">
        <a href="/job-details/senior-backend-engineer-123e4567-e89b-12d3-a456-426614174000?utm=1">
          Senior Backend Engineer
        </a>
        <span>Globex</span>
        <span>3 days ago</span>
        <span>100% Remote Work</span>
        <span>Remote in Argentina, Brazil, Chile</span>
        <span>Full-Time</span>
        <span>Employee</span>
        <span>$120k - $150k</span>
      </article>
      <article class="job-card">
        <a href="/job-details/backend-engineer-no-uuid">
          Backend Engineer
        </a>
        <span>Initech</span>
        <span>Yesterday</span>
        <span>100% Remote Work</span>
        <span>Remote</span>
        <span>Full-Time</span>
        <span>Employee</span>
      </article>
      <article class="job-card">
        <a href="/job-details/backend-engineer-us-national-223e4567-e89b-12d3-a456-426614174000">
          Backend Engineer
        </a>
        <span>US Co</span>
        <span>Today</span>
        <span>100% Remote Work</span>
        <span>Remote, US National</span>
        <span>Full-Time</span>
        <span>Employee</span>
      </article>
      <article class="job-card">
        <a href="/job-details/onsite-engineer-323e4567-e89b-12d3-a456-426614174000">
          Onsite Engineer
        </a>
        <span>Office Co</span>
        <span>Today</span>
        <span>No Remote Work</span>
        <span>Buenos Aires, Argentina</span>
        <span>Full-Time</span>
        <span>Employee</span>
      </article>
      <a class="next page-numbers" href="/remote-jobs/back-end-developer/page/2">
        Next
      </a>
    </body></html>
    """


def _listing_page_two() -> str:
    return """
    <html><body>
      <article class="job-card">
        <a href="/job-details/senior-backend-engineer-123e4567-e89b-12d3-a456-426614174000">
          Senior Backend Engineer
        </a>
        <span>Globex</span>
        <span>Today</span>
        <span>100% Remote Work</span>
        <span>Remote in Argentina</span>
      </article>
      <article class="job-card">
        <a href="/job-details/hybrid-austin-423e4567-e89b-12d3-a456-426614174000">
          Hybrid Engineer
        </a>
        <span>Texas Co</span>
        <span>Today</span>
        <span>Hybrid Remote Work</span>
        <span>Hybrid Remote in Austin, TX</span>
      </article>
      <a class="next page-numbers" href="/remote-jobs/back-end-developer/page/3">
        Next
      </a>
    </body></html>
    """


def _split_listing_structure_html() -> str:
    return """
    <html><body>
      <div class="remote-job-listing">
        <div class="summary">
          <h3>
            <a href="/job-details/backend-us-g23e4567-e89b-12d3-a456-426614174000">
              Backend Engineer
            </a>
          </h3>
          <span>US Co</span>
          <span>Today</span>
          <span>100% Remote Work</span>
          <span>Full-Time</span>
          <span>Employee</span>
        </div>
        <div class="job-location">Remote, US National</div>
      </div>
      <div class="remote-job-listing">
        <div class="summary">
          <h3>
            <a href="/job-details/java-canada-h23e4567-e89b-12d3-a456-426614174000">
              Java Developer
            </a>
          </h3>
          <span>Canada Co</span>
          <span>Today</span>
          <span>100% Remote Work</span>
          <span>Full-Time</span>
          <span>Employee</span>
        </div>
        <div class="job-location">Remote in Canada</div>
      </div>
      <div class="remote-job-listing">
        <div class="summary">
          <h3>
            <a href="/job-details/platform-austin-i23e4567-e89b-12d3-a456-426614174000">
              Platform Engineer
            </a>
          </h3>
          <span>Texas Co</span>
          <span>Today</span>
          <span>Hybrid Remote Work</span>
          <span>Full-Time</span>
          <span>Employee</span>
        </div>
        <div class="job-location">Hybrid Remote in Austin, TX</div>
      </div>
      <div class="remote-job-listing">
        <div class="summary">
          <h3>
            <a href="/job-details/fullstack-anywhere-j23e4567-e89b-12d3-a456-426614174000">
              Full Stack Engineer
            </a>
          </h3>
          <span>Anywhere Co</span>
          <span>Today</span>
          <span>100% Remote Work</span>
          <span>Full-Time</span>
          <span>Employee</span>
        </div>
        <div class="job-location">Remote from Anywhere</div>
      </div>
      <div class="remote-job-listing">
        <div class="summary">
          <h3>
            <a href="/job-details/software-argentina-k23e4567-e89b-12d3-a456-426614174000">
              Software Engineer
            </a>
          </h3>
          <span>Argentina Co</span>
          <span>Today</span>
          <span>100% Remote Work</span>
          <span>Full-Time</span>
          <span>Employee</span>
        </div>
        <div class="job-location">Remote in Argentina</div>
      </div>
      <div class="remote-job-listing">
        <div class="summary">
          <h3>
            <a href="/job-details/api-americas-l23e4567-e89b-12d3-a456-426614174000">
              API Engineer
            </a>
          </h3>
          <span>Americas Co</span>
          <span>Today</span>
          <span>100% Remote Work</span>
          <span>Full-Time</span>
          <span>Employee</span>
        </div>
        <div class="job-location">Remote in Americas</div>
      </div>
    </body></html>
    """


def _pagination_html(
    *,
    next_href: str,
) -> str:
    return f"""
    <html><body>
      <nav class="pagination">
        <a class="prev page-numbers" href="#">prev</a>
        <a class="page-numbers" href="/remote-jobs/back-end-developer/">
          1
        </a>
        <a class="next page-numbers" href="{next_href}">
          next
        </a>
      </nav>
    </body></html>
    """


def _listing_page_for_titles(
    titles: list[tuple[str, str, str]],
    *,
    location: str = "Remote from Anywhere",
) -> str:
    rows = []

    for title, company, slug in titles:
        rows.append(
            f"""
            <article class="job-card">
              <a href="/job-details/{slug}">
                {title}
              </a>
              <span>{company}</span>
              <span>Today</span>
              <span>100% Remote Work</span>
              <span>{location}</span>
              <span>Full-Time</span>
              <span>Employee</span>
            </article>
            """
        )

    return (
        "<html><body>"
        + "\n".join(rows)
        + "</body></html>"
    )


def _detail_html(
    *,
    title: str,
    company: str,
    remote_work_level: str,
    location: str,
    date_posted: str,
    apply_url: str | None = None,
    company_url: str | None = None,
) -> str:
    apply_link = (
        f'<a href="{apply_url}">Apply for this job</a>'
        if apply_url
        else ""
    )
    json_ld = json.dumps(
        {
            "@context": "https://schema.org",
            "@type": "JobPosting",
            "title": title,
            "hiringOrganization": {
                "@type": "Organization",
                "name": company,
                "url": company_url,
            },
            "datePosted": date_posted,
            "description": (
                "<p>Build Python and Java APIs.</p>"
            ),
            "employmentType": "Employee",
            "occupationalCategory": [
                "Software Development",
                "Java",
            ],
            "identifier": {
                "value": "remote-123",
            },
        }
    )

    return f"""
    <html><head>
      <script type="application/ld+json">
        {json_ld}
      </script>
    </head><body>
      <h1>{title}</h1>
      <dl>
        <dt>Date Posted</dt><dd>{date_posted}</dd>
        <dt>Remote Work Level</dt><dd>{remote_work_level}</dd>
        <dt>Location</dt><dd>{location}</dd>
        <dt>Job Schedule</dt><dd>Full-Time</dd>
        <dt>Salary</dt><dd>$120k - $150k</dd>
        <dt>Categories</dt><dd>Software Development, Java</dd>
        <dt>Job Type</dt><dd>Employee</dd>
        <dt>Career Level</dt><dd>Senior</dd>
      </dl>
      <h2>About the Role</h2>
      <p>Build Python and Java APIs.</p>
      {apply_link}
    </body></html>
    """


def _gated_detail_html(
    *,
    title: str,
    company: str,
    remote_work_level: str,
    location: str,
    date_posted: str,
) -> str:
    json_ld = json.dumps(
        {
            "@context": "https://schema.org",
            "@type": "JobPosting",
            "title": title,
            "hiringOrganization": {
                "@type": "Organization",
                "name": company,
            },
            "datePosted": date_posted,
            "employmentType": "Employee",
            "occupationalCategory": [
                "Software Development",
            ],
        }
    )

    return f"""
    <html><head>
      <script type="application/ld+json">
        {json_ld}
      </script>
    </head><body>
      <h1>{title}</h1>
      <dl>
        <dt>Date Posted</dt><dd>{date_posted}</dd>
        <dt>Remote Work Level</dt><dd>{remote_work_level}</dd>
        <dt>Location</dt><dd>{location}</dd>
        <dt>Job Schedule</dt><dd>Full-Time</dd>
        <dt>Categories</dt><dd>Software Development</dd>
        <dt>Job Type</dt><dd>Employee</dd>
        <dt>Career Level</dt><dd>Senior</dd>
      </dl>
      <h2>Company details here</h2>
      <p>Company Benefits here</p>
    </body></html>
    """
