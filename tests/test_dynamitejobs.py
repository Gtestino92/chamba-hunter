from datetime import UTC, datetime
import json

import httpx
import pytest

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
from chamba_hunter.services.dynamitejobs_job_acquisition_service import (
    DYNAMITEJOBS_SCOPE_KEY,
    DynamiteJobsJobAcquisitionService,
)
from chamba_hunter.sources.dynamitejobs import (
    DYNAMITEJOBS_INDEX_URLS,
    DynamiteJobsClient,
    DynamiteJobsIndexEntry,
    canonical_dynamite_job_url,
    dynamite_external_id,
    parse_dynamite_detail,
    parse_dynamite_index,
)


def test_index_parser_extracts_jobs_and_ignores_navigation() -> None:
    entries = parse_dynamite_index(
        _index_html(),
        index_url=DYNAMITEJOBS_INDEX_URLS[0],
    )

    assert [
        entry.external_id
        for entry in entries
    ] == [
        (
            "phorest/"
            "senior-be-software-engineer-reporting"
        ),
        (
            "threecolts/"
            "senior-software-engineer-c-java"
        ),
    ]
    assert entries[0].title_hint == (
        "Senior BE Software Engineer - Reporting"
    )
    assert entries[0].company_hint == "Phorest"
    assert entries[0].employment_type_hint == (
        "Full Time"
    )
    assert entries[0].tags == (
        "Java",
        "Docker",
        "Backend",
    )
    assert entries[0].opened_relative == (
        "New Job!"
    )
    assert entries[1].opened_relative == (
        "Opened 9 days ago"
    )


def test_canonical_url_creates_stable_external_id() -> None:
    canonical = canonical_dynamite_job_url(
        (
            "https://www.dynamitejobs.com/company/"
            "threecolts/remote-job/"
            "senior-software-engineer-c-java"
            "?utm_source=test#section"
        )
    )

    assert canonical == (
        "https://dynamitejobs.com/company/"
        "threecolts/remote-job/"
        "senior-software-engineer-c-java"
    )
    assert dynamite_external_id(canonical) == (
        (
            "threecolts/"
            "senior-software-engineer-c-java"
        ),
        "threecolts",
        "senior-software-engineer-c-java",
    )


def test_detail_extracts_description_apply_url_and_exact_date() -> None:
    entry = _entry(
        title="Senior BE Software Engineer - Reporting",
        company="Phorest",
        opened_relative="Opened 3 days ago",
        closing_relative="Closes in 8 days",
    )

    posting = parse_dynamite_detail(
        _detail_html(
            title=(
                "Senior BE Software Engineer - Reporting"
            ),
            company="Phorest",
            description=(
                "<p>Build Java backend APIs for "
                "salon reporting.</p>"
            ),
            apply_url=(
                "https://boards.greenhouse.io/"
                "phorest/jobs/123"
            ),
            date_posted="2026-09-01T12:00:00Z",
        ),
        entry=entry,
    )

    assert posting.title == (
        "Senior BE Software Engineer - Reporting"
    )
    assert posting.company_name == "Phorest"
    assert posting.description == (
        "Build Java backend APIs for salon reporting."
    )
    assert posting.apply_url == (
        "https://boards.greenhouse.io/"
        "phorest/jobs/123"
    )
    assert posting.published_at == datetime(
        2026,
        9,
        1,
        12,
        tzinfo=UTC,
    )
    assert posting.opened_relative == (
        "Opened 3 days ago"
    )
    assert posting.closing_relative == (
        "Closes in 8 days"
    )


def test_detail_does_not_fabricate_dates_or_apply_url() -> None:
    posting = parse_dynamite_detail(
        _detail_html(
            title=(
                "Senior Software Engineer - C# / Java"
            ),
            company="Threecolts",
            description=(
                "<p>Own APIs and backend services.</p>"
            ),
            apply_url=None,
            date_posted=None,
        ),
        entry=_entry(
            title=(
                "Senior Software Engineer - C# / Java"
            ),
            company="Threecolts",
            opened_relative="Opened 9 days ago",
        ),
    )

    assert posting.apply_url is None
    assert posting.published_at is None
    assert posting.raw_payload[
        "_chamba_source_enrichment"
    ]["opened_relative"] == "Opened 9 days ago"


def test_client_deduplicates_before_fetching_details() -> None:
    calls: list[str] = []

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        calls.append(str(request.url))

        if str(request.url) in DYNAMITEJOBS_INDEX_URLS:
            return httpx.Response(
                200,
                text=_index_html(),
            )

        return httpx.Response(
            200,
            text=_detail_html(
                title=(
                    "Senior BE Software Engineer - Reporting"
                ),
                company="Phorest",
                description=(
                    "<p>Build Java backend APIs.</p>"
                ),
                apply_url=None,
                date_posted=None,
            ),
        )

    client = DynamiteJobsClient(
        transport=httpx.MockTransport(
            handler
        )
    )

    fetch = client.fetch_jobs(
        max_jobs=1,
        detail_workers=1,
    )

    assert fetch.links_discovered == 8
    assert fetch.unique_jobs == 2
    assert fetch.duplicates_removed == 6
    assert fetch.details_attempted == 1
    assert len(fetch.jobs) == 1
    assert calls.count(
        (
            "https://dynamitejobs.com/company/"
            "phorest/remote-job/"
            "senior-be-software-engineer-reporting"
        )
    ) == 1


def test_client_skips_closed_and_malformed_detail_pages() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        url = str(request.url)

        if url in DYNAMITEJOBS_INDEX_URLS:
            return httpx.Response(
                200,
                text="""
                <article class="job-card">
                  <a href="/company/open/remote-job/backend">
                    Backend Engineer
                  </a>
                  <span>Open Co</span>
                  <span>Opened 3 days ago</span>
                </article>
                <article class="job-card">
                  <a href="/company/closed/remote-job/backend">
                    Closed Engineer
                  </a>
                  <span>Closed Co</span>
                </article>
                <article class="job-card">
                  <a href="/company/bad/remote-job/backend">
                    Bad Engineer
                  </a>
                  <span>Bad Co</span>
                </article>
                """,
            )

        if "/company/closed/" in url:
            return httpx.Response(
                200,
                text="""
                <html><body>
                  <h1>Closed Engineer</h1>
                  <p>Closed Co</p>
                  <p>This job is closed</p>
                </body></html>
                """,
            )

        if "/company/bad/" in url:
            return httpx.Response(
                200,
                text="<html><body>No usable fields</body></html>",
            )

        return httpx.Response(
            200,
            text=_detail_html(
                title="Backend Engineer",
                company="Open Co",
                description=(
                    "<p>Build backend services.</p>"
                ),
                apply_url=None,
                date_posted=None,
            ),
        )

    fetch = DynamiteJobsClient(
        transport=httpx.MockTransport(
            handler
        )
    ).fetch_jobs(
        max_jobs=3,
        detail_workers=1,
    )

    assert len(fetch.jobs) == 1
    assert fetch.closed_skipped == 1
    assert fetch.parse_failures == 1
    assert fetch.details_failed == 1


def test_client_fails_when_all_details_are_unusable() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        if str(request.url) in DYNAMITEJOBS_INDEX_URLS:
            return httpx.Response(
                200,
                text="""
                <article class="job-card">
                  <a href="/company/bad/remote-job/backend">
                    Bad Engineer
                  </a>
                  <span>Bad Co</span>
                </article>
                """,
            )

        return httpx.Response(
            200,
            text="<html><body>No usable fields</body></html>",
        )

    with pytest.raises(
        RuntimeError,
        match="no usable open jobs",
    ):
        DynamiteJobsClient(
            transport=httpx.MockTransport(
                handler
            )
        ).fetch_jobs(
            max_jobs=1,
            detail_workers=1,
        )


def test_preview_mode_performs_zero_persistence(
    tmp_path,
) -> None:
    database = Database(
        tmp_path / "test.db"
    )
    migrate(database)

    before = _table_counts(database)

    service = DynamiteJobsJobAcquisitionService(
        client=_StaticClient(
            _fetch_with_one_job()
        )
    )

    summary = service.preview(
        max_jobs=100,
        detail_workers=6,
    )

    assert summary.applied is False
    assert summary.normalized == 1
    assert _table_counts(database) == before


def test_apply_persists_company_lead_hint_and_state(
    tmp_path,
) -> None:
    database = Database(
        tmp_path / "test.db"
    )
    migrate(database)

    service = _service(
        database,
        _fetch_with_one_job(),
    )

    summary = service.run(
        max_jobs=100,
        detail_workers=6,
    )

    assert summary.applied is True
    assert summary.companies_created == 1
    assert summary.jobs_created == 1
    assert summary.ats_hints_created == 1

    with database.connection() as connection:
        companies = connection.execute(
            "SELECT * FROM companies"
        ).fetchall()
        sources = connection.execute(
            "SELECT * FROM company_sources"
        ).fetchall()
        leads = connection.execute(
            "SELECT * FROM job_leads"
        ).fetchall()
        hints = connection.execute(
            "SELECT * FROM job_ats_hints"
        ).fetchall()

    assert len(companies) == 1
    assert len(sources) == 1
    assert sources[0]["source_type"] == (
        SourceType.DYNAMITEJOBS.value
    )
    assert sources[0]["external_id"] == "phorest"
    assert len(leads) == 1
    assert leads[0]["source_type"] == (
        SourceType.DYNAMITEJOBS.value
    )
    assert leads[0]["external_id"] == (
        "phorest/"
        "senior-be-software-engineer-reporting"
    )
    assert leads[0]["workplace_type"] == (
        WorkplaceType.REMOTE.value
    )
    assert leads[0]["published_at"] is None
    assert json_from_db(
        leads[0]["raw_payload_json"]
    )["_chamba_source_enrichment"][
        "opened_relative"
    ] == "New Job!"
    assert len(hints) == 1
    assert hints[0]["provider"] == (
        AtsProvider.GREENHOUSE.value
    )
    assert hints[0]["external_identifier"] == (
        "phorest"
    )

    state = SourceAcquisitionStateRepository(
        database
    ).get(
        source_type=SourceType.DYNAMITEJOBS,
        scope_key=DYNAMITEJOBS_SCOPE_KEY,
    )
    assert state is not None
    assert state.metadata["strategy"] == (
        "CURATED_REMOTE_HTML_PAGES"
    )
    assert state.metadata["links_discovered"] == 8
    assert state.metadata[
        "snapshot_semantics"
    ] == "PARTIAL_CURATED_SOURCE_RESPONSE"


def test_apply_is_idempotent_for_leads_companies_and_hints(
    tmp_path,
) -> None:
    database = Database(
        tmp_path / "test.db"
    )
    migrate(database)

    service = _service(
        database,
        _fetch_with_one_job(),
    )

    first = service.run(
        max_jobs=100,
        detail_workers=6,
    )
    second = service.run(
        max_jobs=100,
        detail_workers=6,
    )

    assert first.jobs_created == 1
    assert second.companies_existing == 1
    assert second.jobs_created == 0
    assert second.jobs_updated == 1
    assert second.ats_hints_created == 0

    with database.connection() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM companies"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM job_leads"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM job_ats_hints"
        ).fetchone()[0] == 1


def test_dynamite_opened_relative_contributes_to_recency() -> None:
    now = datetime(
        2026,
        9,
        26,
        tzinfo=UTC,
    )

    new_job = evaluate_source_recency(
        now=now,
        published_at=None,
        raw_payload_json=json.dumps(
            {
                "_chamba_source_enrichment": {
                    "source": "DYNAMITEJOBS",
                    "opened_relative": "New Job!",
                    "closing_relative": None,
                }
            }
        ),
    )
    opened_three = evaluate_source_recency(
        now=now,
        published_at=None,
        raw_payload_json=json.dumps(
            {
                "_chamba_source_enrichment": {
                    "source": "DYNAMITEJOBS",
                    "opened_relative": (
                        "Opened 3 days ago"
                    ),
                    "closing_relative": None,
                }
            }
        ),
    )
    opened_nine = evaluate_source_recency(
        now=now,
        published_at=None,
        raw_payload_json=json.dumps(
            {
                "_chamba_source_enrichment": {
                    "source": "DYNAMITEJOBS",
                    "opened_relative": (
                        "Opened 9 days ago"
                    ),
                    "closing_relative": None,
                }
            }
        ),
    )
    closing_only = evaluate_source_recency(
        now=now,
        published_at=None,
        raw_payload_json=json.dumps(
            {
                "_chamba_source_enrichment": {
                    "source": "DYNAMITEJOBS",
                    "opened_relative": None,
                    "closing_relative": (
                        "Closes in 8 days"
                    ),
                }
            }
        ),
    )

    assert new_job.bucket == "VERY_RECENT"
    assert opened_three.bucket == "VERY_RECENT"
    assert opened_nine.bucket == "RECENT"
    assert closing_only.bucket == "UNKNOWN"


class _StaticClient:
    def __init__(
        self,
        fetch,
    ) -> None:
        self.fetch = fetch

    def fetch_jobs(
        self,
        *,
        max_jobs: int,
        detail_workers: int,
    ):
        return self.fetch


def _service(
    database: Database,
    fetch,
) -> DynamiteJobsJobAcquisitionService:
    return DynamiteJobsJobAcquisitionService(
        client=_StaticClient(fetch),
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


def _fetch_with_one_job():
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        if str(request.url) in DYNAMITEJOBS_INDEX_URLS:
            return httpx.Response(
                200,
                text=_index_html(),
            )

        return httpx.Response(
            200,
            text=_detail_html(
                title=(
                    "Senior BE Software Engineer - Reporting"
                ),
                company="Phorest",
                description=(
                    "<p>Build Java backend APIs.</p>"
                ),
                apply_url=(
                    "https://boards.greenhouse.io/"
                    "phorest/jobs/123"
                ),
                date_posted=None,
                company_url=(
                    "https://www.phorest.com"
                ),
            ),
        )

    return DynamiteJobsClient(
        transport=httpx.MockTransport(
            handler
        )
    ).fetch_jobs(
        max_jobs=1,
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
    title: str = "Senior BE Software Engineer - Reporting",
    company: str = "Phorest",
    opened_relative: str | None = "New Job!",
    closing_relative: str | None = None,
) -> DynamiteJobsIndexEntry:
    return DynamiteJobsIndexEntry(
        external_id=(
            "phorest/"
            "senior-be-software-engineer-reporting"
        ),
        canonical_url=(
            "https://dynamitejobs.com/company/"
            "phorest/remote-job/"
            "senior-be-software-engineer-reporting"
        ),
        company_slug="phorest",
        job_slug=(
            "senior-be-software-engineer-reporting"
        ),
        title_hint=title,
        company_hint=company,
        employment_type_hint="Full Time",
        tags=("Java", "Docker", "Backend"),
        opened_relative=opened_relative,
        closing_relative=closing_relative,
        source_index_url=DYNAMITEJOBS_INDEX_URLS[0],
    )


def _index_html() -> str:
    return """
    <html><body>
      <nav>
        <a href="/company/phorest">Phorest company</a>
        <a href="/category/remote-development-jobs">
          Development category
        </a>
        <a href="/skill/remote-java-jobs">Java</a>
      </nav>
      <article class="job-card">
        <a href="/company/phorest/remote-job/senior-be-software-engineer-reporting?utm=1">
          Senior BE Software Engineer - Reporting
        </a>
        <span>Phorest</span>
        <span>Full Time</span>
        <span>Java</span>
        <span>Docker</span>
        <span>Backend</span>
        <span>New Job!</span>
      </article>
      <article class="job-card">
        <a href="https://dynamitejobs.com/company/threecolts/remote-job/senior-software-engineer-c-java#top">
          Senior Software Engineer - C# / Java
        </a>
        <span>Threecolts</span>
        <span>Full Time</span>
        <span>APIs</span>
        <span>AWS</span>
        <span>Git</span>
        <span>Java</span>
        <span>Rest API</span>
        <span>Opened 9 days ago</span>
      </article>
    </body></html>
    """


def _detail_html(
    *,
    title: str,
    company: str,
    description: str,
    apply_url: str | None,
    date_posted: str | None,
    company_url: str | None = None,
) -> str:
    posting = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": title,
        "description": description,
        "hiringOrganization": {
            "@type": "Organization",
            "name": company,
        },
        "employmentType": "FULL_TIME",
        "applicantLocationRequirements": {
            "@type": "Country",
            "name": "Remote - LATAM",
        },
        "skills": "Java, Docker, Backend",
    }

    if date_posted is not None:
        posting["datePosted"] = date_posted

    if company_url is not None:
        posting["hiringOrganization"][
            "sameAs"
        ] = company_url

    apply = (
        f'<a href="{apply_url}">Apply for this job</a>'
        if apply_url is not None
        else ""
    )

    return f"""
    <html><body>
      <script type="application/ld+json">
        {json.dumps(posting)}
      </script>
      <main class="job-description">
        {description}
      </main>
      <p>Opened 3 days ago</p>
      <p>Closes in 8 days</p>
      {apply}
    </body></html>
    """
