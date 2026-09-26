from datetime import UTC, datetime

import httpx
import pytest

from chamba_hunter.db.connection import Database
from chamba_hunter.db.converters import json_from_db
from chamba_hunter.db.migrations import migrate
from chamba_hunter.domain.enums import (
    SourceType,
    WorkplaceType,
)
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
from chamba_hunter.services.company_import_service import (
    CompanyImportService,
)
from chamba_hunter.services.remotive_job_acquisition_service import (
    REMOTIVE_SCOPE_KEY,
    RemotiveJobAcquisitionService,
)
from chamba_hunter.sources.remotive_jobs import (
    MAX_REMOTIVE_MAX_JOBS,
    REMOTIVE_REMOTE_JOBS_URL,
    RemotiveApiError,
    RemotiveGeoClassification,
    RemotiveJobsClient,
    classify_remotive_geography,
)


def test_valid_response_parses_stable_ids_and_extra_fields() -> None:
    fetch = _fetch(
        [
            _job(
                id=123,
                category="Software Development",
                location="Argentina",
                extra_field="ignored",
            )
        ],
        top_level_notice="Remotive legal text",
    )

    assert fetch.requests_made == 1
    assert fetch.jobs_reported_by_api == 1
    assert fetch.jobs[0].external_id == "123"
    assert fetch.jobs[0].raw_payload["extra_field"] == (
        "ignored"
    )


def test_duplicate_ids_deduplicate() -> None:
    fetch = _fetch(
        [
            _job(id=1, title="First"),
            _job(id=1, title="Duplicate"),
        ]
    )

    assert fetch.duplicates_removed == 1
    assert [job.title for job in fetch.jobs] == [
        "First"
    ]


@pytest.mark.parametrize(
    "category",
    [
        "Software Development",
        "DevOps / Sysadmin",
        "DevOps/Sysadmin",
        "Devops",
        "DevOps",
    ],
)
def test_target_categories_retained(
    category: str,
) -> None:
    fetch = _fetch(
        [
            _job(
                id=category,
                category=category,
            )
        ]
    )

    assert fetch.category_candidates == 1
    assert fetch.normalized_jobs == 1


def test_unrelated_category_rejected() -> None:
    fetch = _fetch(
        [
            _job(
                id=1,
                category="Marketing",
            )
        ]
    )

    assert fetch.category_rejects == 1
    assert fetch.normalized_jobs == 0


@pytest.mark.parametrize(
    "location",
    [
        "Argentina",
        "Buenos Aires",
        "LATAM",
        "Latin America",
        "South America",
        "Worldwide",
        "Anywhere",
        "Global",
        "Americas",
        "Chile, Argentina, Uruguay",
        "UTC-3 timezone",
    ],
)
def test_potentially_eligible_locations(
    location: str,
) -> None:
    assert classify_remotive_geography(location) == (
        RemotiveGeoClassification
        .POTENTIALLY_ELIGIBLE
    )


@pytest.mark.parametrize(
    "location",
    [
        "USA only",
        "Canada only",
        "Europe only",
        "Germany only",
        "India",
        "Australia",
        "New Zealand",
        "Brazil only",
        "Mexico only",
        "Colombia only",
        "Austin, Texas",
    ],
)
def test_explicitly_ineligible_locations(
    location: str,
) -> None:
    assert classify_remotive_geography(location) == (
        RemotiveGeoClassification
        .EXPLICITLY_INELIGIBLE
    )


@pytest.mark.parametrize(
    "location",
    [
        None,
        "",
        "Remote",
        "Selected countries",
    ],
)
def test_unknown_location_is_retained(
    location: str | None,
) -> None:
    fetch = _fetch(
        [
            _job(
                id=1,
                location=location,
            )
        ]
    )

    assert fetch.unknown_geography == 1
    assert fetch.normalized_jobs == 1


def test_publication_date_parsing_and_malformed_dates() -> None:
    fetch = _fetch(
        [
            _job(
                id=1,
                publication_date=(
                    "2026-09-25T10:11:12Z"
                ),
            ),
            _job(
                id=2,
                publication_date="not a date",
            ),
        ]
    )

    by_id = {
        job.external_id: job
        for job in fetch.jobs
    }
    assert by_id["1"].published_at == datetime(
        2026,
        9,
        25,
        10,
        11,
        12,
        tzinfo=UTC,
    )
    assert by_id["2"].published_at is None
    assert fetch.publication_dates_parsed == 1
    assert fetch.publication_dates_missing == 1


def test_html_description_and_missing_description() -> None:
    fetch = _fetch(
        [
            _job(
                id=1,
                description=(
                    "<p>Build &amp; ship "
                    "<strong>APIs</strong>.</p>"
                ),
            ),
            _job(
                id=2,
                description=None,
            ),
        ]
    )

    by_id = {
        job.external_id: job
        for job in fetch.jobs
    }
    assert by_id["1"].description == (
        "Build & ship APIs."
    )
    assert by_id["2"].description is None


def test_job_type_workplace_urls_salary_and_tags() -> None:
    service = RemotiveJobAcquisitionService(
        client=_client(
            [
                _job(
                    id=7,
                    job_type="full_time",
                    salary="$100k",
                    tags=["Python", "API"],
                )
            ]
        )
    )

    summary = service.preview(max_jobs=10)
    fetch = service.client.fetch_jobs(max_jobs=10)
    job = fetch.jobs[0]

    assert summary.ats_hints_detected == 0
    assert job.job_type == "full_time"
    assert job.job_url == (
        "https://remotive.com/remote-jobs/"
        "software-dev/example-7"
    )
    assert job.raw_payload["salary"] == "$100k"
    assert job.raw_payload["tags"] == [
        "Python",
        "API",
    ]


def test_filtering_happens_before_max_jobs() -> None:
    fetch = _fetch(
        [
            _job(
                id=1,
                category="Marketing",
            ),
            _job(
                id=2,
                location="USA only",
            ),
            _job(id=3, title="Keep One"),
            _job(id=4, title="Keep Two"),
        ],
        max_jobs=1,
    )

    assert fetch.category_rejects == 1
    assert fetch.explicit_geo_rejects == 1
    assert fetch.selected_after_max_jobs == 1
    assert fetch.jobs[0].external_id == "3"


@pytest.mark.parametrize(
    "max_jobs",
    [0, MAX_REMOTIVE_MAX_JOBS + 1],
)
def test_max_jobs_is_bounded(
    max_jobs: int,
) -> None:
    with pytest.raises(ValueError):
        _fetch([_job(id=1)], max_jobs=max_jobs)


def test_only_one_http_request_per_acquisition() -> None:
    calls: list[str] = []
    client = _client(
        [
            _job(id=1),
            _job(
                id=2,
                category="Marketing",
            ),
            _job(
                id=3,
                location="USA only",
            ),
        ],
        calls=calls,
    )

    fetch = client.fetch_jobs(max_jobs=1)

    assert fetch.requests_made == 1
    assert calls == [
        REMOTIVE_REMOTE_JOBS_URL
    ]


def test_preview_performs_zero_persistence() -> None:
    class ExplodingPersistence:
        def __getattr__(self, name):
            raise AssertionError(
                "preview touched persistence"
            )

    service = RemotiveJobAcquisitionService(
        client=_client([_job(id=1)]),
        company_import_service=ExplodingPersistence(),
        job_lead_repository=ExplodingPersistence(),
        tracing_repository=ExplodingPersistence(),
        state_repository=ExplodingPersistence(),
    )

    summary = service.preview(max_jobs=10)

    assert summary.normalized_jobs == 1
    assert summary.applied is False


def test_apply_persists_companies_and_leads(
    tmp_path,
) -> None:
    database = _database(tmp_path)
    service = _service(
        database,
        _client(
            [
                _job(
                    id=10,
                    company_name="Acme",
                    title="Backend Engineer",
                    job_type="contract",
                    salary="$120k",
                    tags=["Java"],
                ),
                _job(
                    id=11,
                    company_name="Acme",
                    title="Platform Engineer",
                ),
            ]
        ),
    )

    summary = service.run(max_jobs=10)

    assert summary.companies_created == 1
    assert summary.companies_existing == 0
    assert summary.jobs_created == 2
    assert summary.jobs_updated == 0

    with database.connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM job_leads
            WHERE source_type = ?
            ORDER BY external_id
            """,
            (SourceType.REMOTIVE.value,),
        ).fetchall()
        company_sources = connection.execute(
            """
            SELECT source_type, source_url
            FROM company_sources
            WHERE source_type = ?
            """,
            (SourceType.REMOTIVE.value,),
        ).fetchall()

    assert len(rows) == 2
    assert rows[0]["external_id"] == "10"
    assert rows[0]["title"] == "Backend Engineer"
    assert rows[0]["workplace_type"] == (
        WorkplaceType.REMOTE.value
    )
    assert rows[0]["employment_type"] == "contract"
    assert rows[0]["job_url"].startswith(
        "https://remotive.com/"
    )
    assert rows[0]["apply_url"] is None
    raw_payload = json_from_db(
        rows[0]["raw_payload_json"]
    )
    assert raw_payload["salary"] == "$120k"
    assert raw_payload["tags"] == ["Java"]
    assert raw_payload[
        "_chamba_source_metadata"
    ]["source"] == SourceType.REMOTIVE.value
    assert len(company_sources) == 2


def test_repeated_apply_is_idempotent(
    tmp_path,
) -> None:
    database = _database(tmp_path)
    service = _service(
        database,
        _client(
            [
                _job(
                    id=10,
                    company_name="Acme",
                )
            ]
        ),
    )

    first = service.run(max_jobs=10)
    second = service.run(max_jobs=10)

    assert first.jobs_created == 1
    assert second.jobs_created == 0
    assert second.jobs_updated == 1
    assert second.companies_created == 0
    assert second.companies_existing == 1


def test_malformed_api_shape_fails() -> None:
    client = _raw_client({"job-count": 0})

    with pytest.raises(RemotiveApiError, match="jobs array"):
        client.fetch_jobs(max_jobs=10)


def test_429_produces_clear_failure() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(429, json={})

    client = RemotiveJobsClient(
        transport=httpx.MockTransport(handler)
    )

    with pytest.raises(RemotiveApiError, match="rate limit"):
        client.fetch_jobs(max_jobs=10)


def _fetch(
    jobs: list[dict],
    max_jobs: int = 100,
    **extra: object,
):
    return _client(jobs, **extra).fetch_jobs(
        max_jobs=max_jobs
    )


def _client(
    jobs: list[dict],
    calls: list[str] | None = None,
    **extra: object,
) -> RemotiveJobsClient:
    payload = {
        "job-count": len(jobs),
        "jobs": jobs,
        **extra,
    }

    return _raw_client(payload, calls=calls)


def _raw_client(
    payload: dict,
    calls: list[str] | None = None,
) -> RemotiveJobsClient:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        if calls is not None:
            calls.append(str(request.url))

        return httpx.Response(
            200,
            json=payload,
        )

    return RemotiveJobsClient(
        transport=httpx.MockTransport(handler)
    )


def _job(
    *,
    id,
    title: str | None = None,
    company_name: str = "Acme",
    category: str = "Software Development",
    location: str | None = "Argentina",
    publication_date: str | None = (
        "2026-09-25T10:00:00Z"
    ),
    description: str | None = (
        "<p>Build backend APIs.</p>"
    ),
    job_type: str | None = "full_time",
    salary: str | None = None,
    tags: list[str] | None = None,
    **extra,
) -> dict:
    return {
        "id": id,
        "url": (
            "https://remotive.com/remote-jobs/"
            f"software-dev/example-{id}"
        ),
        "title": title or f"Engineer {id}",
        "company_name": company_name,
        "company_logo": (
            "https://example.com/logo.png"
        ),
        "category": category,
        "job_type": job_type,
        "publication_date": publication_date,
        "candidate_required_location": (
            location
        ),
        "salary": salary,
        "description": description,
        "tags": tags,
        **extra,
    }


def _database(tmp_path) -> Database:
    database = Database(tmp_path / "test.db")
    migrate(database)
    return database


def _service(
    database: Database,
    client: RemotiveJobsClient,
) -> RemotiveJobAcquisitionService:
    return RemotiveJobAcquisitionService(
        client=client,
        company_import_service=CompanyImportService(
            CompanyRepository(database),
            CompanySourceRepository(database),
        ),
        job_lead_repository=JobLeadRepository(
            database
        ),
        tracing_repository=TracingRepository(
            database
        ),
        state_repository=(
            SourceAcquisitionStateRepository(
                database
            )
        ),
    )
