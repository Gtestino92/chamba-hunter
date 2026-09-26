from datetime import UTC, datetime
import json

import httpx

from chamba_hunter.db.connection import Database
from chamba_hunter.db.converters import json_from_db
from chamba_hunter.db.migrations import migrate
from chamba_hunter.domain.enums import (
    AtsProvider,
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
    REMOTECO_CATEGORY_URLS,
    RemoteCoClient,
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
        "Hybrid Remote in Austin, TX"
    ) == RemoteCoGeoClassification.EXPLICITLY_INELIGIBLE
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

    assert fetch.pages_fetched == 5
    assert fetch.listing_rows == 6
    assert fetch.unique_jobs == 2
    assert fetch.duplicates_removed == 1
    assert fetch.explicit_geo_rejects == 2
    assert fetch.remote_level_rejects == 1
    assert fetch.unknown_geography == 1
    assert fetch.potentially_eligible == 2
    assert fetch.details_attempted == 2
    assert fetch.details_succeeded == 2
    assert len(fetch.coverage_warnings) == 1
    assert all(
        "us-national" not in call
        for call in calls
    )
    assert all(
        "onsite" not in call
        for call in calls
    )


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


def test_apply_persists_remote_source_lead_and_hint(
    tmp_path,
) -> None:
    database = Database(
        tmp_path / "test.db"
    )
    migrate(database)

    service = _service(
        database,
        _fetch_client(),
    )

    summary = service.run(
        max_pages_per_category=1,
        max_jobs=1,
        detail_workers=1,
    )

    assert summary.applied is True
    assert summary.companies_created == 1
    assert summary.jobs_created == 1
    assert summary.ats_hints_created == 1

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
    assert len(hints) == 1
    assert hints[0]["provider"] == (
        AtsProvider.GREENHOUSE.value
    )
    assert hints[0]["external_identifier"] == (
        "globex"
    )

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


def _fetch_client() -> RemoteCoClient:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        if str(request.url).rstrip("/") in {
            url.rstrip("/")
            for url in REMOTECO_CATEGORY_URLS
        }:
            return httpx.Response(
                200,
                text="""
                <article class="job-card">
                  <a href="/job-details/senior-backend-engineer-123e4567-e89b-12d3-a456-426614174000">
                    Senior Backend Engineer
                  </a>
                  <span>Globex</span>
                  <span>Today</span>
                  <span>100% Remote Work</span>
                  <span>Remote in Argentina</span>
                  <span>Full-Time</span>
                  <span>Employee</span>
                </article>
                """,
            )

        return httpx.Response(
            200,
            text=_detail_html(
                title="Senior Backend Engineer",
                company="Globex",
                remote_work_level="100% Remote Work",
                location="Remote in Argentina",
                date_posted="Today",
                apply_url=(
                    "https://boards.greenhouse.io/"
                    "globex/jobs/123"
                ),
                company_url=(
                    "https://www.globex.com"
                ),
            ),
        )

    return RemoteCoClient(
        transport=httpx.MockTransport(
            handler
        )
    )


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
