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
from chamba_hunter.services.remoteok_job_acquisition_service import (
    RemoteOkJobAcquisitionService,
)
from chamba_hunter.sources.remoteok_jobs import (
    MAX_REMOTEOK_MAX_JOBS,
    REMOTEOK_API_URL,
    RemoteOkApiError,
    RemoteOkGeoClassification,
    RemoteOkJobsClient,
    classify_remoteok_geography,
)


def test_metadata_element_is_skipped_and_extra_fields_preserved() -> None:
    fetch = _fetch(
        [
            _metadata(),
            _job(
                id=123,
                extra_field="kept",
            ),
        ]
    )

    assert fetch.requests_made == 1
    assert fetch.array_elements_received == 2
    assert fetch.metadata_elements_skipped == 1
    assert fetch.job_objects_parsed == 1
    assert fetch.jobs[0].external_id == "123"
    assert fetch.jobs[0].raw_payload["extra_field"] == "kept"


def test_invalid_jobs_are_skipped_without_fabricating_required_values() -> None:
    fetch = _fetch(
        [
            _metadata(),
            _job(id=1),
            {
                "id": 2,
                "company": "Acme",
                "position": "Backend Engineer",
            },
            {
                "id": 3,
                "company": "Acme",
                "url": "https://remoteok.com/remote-jobs/3",
            },
        ]
    )

    assert fetch.job_objects_parsed == 1
    assert fetch.invalid_job_objects_skipped == 2
    assert [job.external_id for job in fetch.jobs] == ["1"]


def test_duplicate_ids_are_removed_by_authoritative_id() -> None:
    fetch = _fetch(
        [
            _metadata(),
            _job(id=7, position="Backend Engineer"),
            _job(id=7, position="Software Architect"),
        ]
    )

    assert fetch.duplicates_removed == 1
    assert [job.title for job in fetch.jobs] == [
        "Backend Engineer"
    ]


@pytest.mark.parametrize(
    ("position", "tags"),
    [
        ("Senior Software Engineer", []),
        ("Back-End Developer", []),
        ("Full-stack Engineer", []),
        ("SRE", []),
        ("Technical Lead", []),
        ("Product Engineer", ["Kubernetes"]),
        ("Frontend Engineer", []),
    ],
)
def test_broad_software_prefilter_accepts_positive_signals(
    position: str,
    tags: list[str],
) -> None:
    fetch = _fetch(
        [
            _metadata(),
            _job(
                id=position,
                position=position,
                tags=tags,
            ),
        ]
    )

    assert fetch.technical_candidates == 1
    assert fetch.normalized_jobs == 1


@pytest.mark.parametrize(
    ("position", "tags"),
    [
        ("Recruiter", ["Python"]),
        ("Customer Support Specialist", ["SQL"]),
        ("Marketing Writer", ["JavaScript"]),
        ("Product Manager", ["API"]),
        ("Designer", ["technical"]),
        ("Executive Assistant", ["remote"]),
    ],
)
def test_obvious_non_target_titles_are_rejected(
    position: str,
    tags: list[str],
) -> None:
    fetch = _fetch(
        [
            _metadata(),
            _job(
                id=position,
                position=position,
                tags=tags,
            ),
        ]
    )

    assert fetch.technical_rejects == 1
    assert fetch.normalized_jobs == 0


def test_generic_tags_are_not_sufficient() -> None:
    fetch = _fetch(
        [
            _metadata(),
            _job(
                id=1,
                position="Operations Lead",
                tags=[
                    "technical",
                    "remote",
                    "digital nomad",
                ],
            ),
        ]
    )

    assert fetch.technical_rejects == 1
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
        "UTC-3 timezone",
    ],
)
def test_potentially_eligible_locations(
    location: str,
) -> None:
    assert classify_remoteok_geography(
        location=location
    ) == (
        RemoteOkGeoClassification
        .POTENTIALLY_ELIGIBLE
    )


@pytest.mark.parametrize(
    "location",
    [
        "USA only",
        "Canada only",
        "Europe only",
        "Germany only",
        "India only",
        "Austin, Texas",
    ],
)
def test_explicitly_ineligible_locations(
    location: str,
) -> None:
    assert classify_remoteok_geography(
        location=location
    ) == (
        RemoteOkGeoClassification
        .EXPLICITLY_INELIGIBLE
    )


def test_global_description_overrides_country_location() -> None:
    assert classify_remoteok_geography(
        location="Germany",
        description=(
            "<p>We hire globally and support "
            "worldwide remote work.</p>"
        ),
    ) == (
        RemoteOkGeoClassification
        .POTENTIALLY_ELIGIBLE
    )


@pytest.mark.parametrize(
    "description",
    [
        "We are a global company building APIs.",
        "We serve global customers.",
        "Our European customers love the product.",
        "We have an office in New York.",
        "We are headquartered in California.",
        "Our team is based in Germany.",
    ],
)
def test_incidental_description_geography_is_ignored(
    description: str,
) -> None:
    assert classify_remoteok_geography(
        location=None,
        description=description,
    ) == RemoteOkGeoClassification.UNKNOWN


def test_incidental_office_in_new_york_does_not_reject() -> None:
    fetch = _fetch(
        [
            _metadata(),
            _job(
                id=1,
                location="Remote",
                description=(
                    "Build APIs. We have an office "
                    "in New York."
                ),
            ),
        ]
    )

    assert fetch.explicit_geo_rejects == 0
    assert fetch.unknown_geography == 1
    assert fetch.normalized_jobs == 1


def test_explicit_global_hiring_description_is_eligible() -> None:
    assert classify_remoteok_geography(
        location="Germany",
        description="We hire globally for this role.",
    ) == (
        RemoteOkGeoClassification
        .POTENTIALLY_ELIGIBLE
    )


def test_explicit_candidate_location_restriction_rejects() -> None:
    assert classify_remoteok_geography(
        location="Remote",
        description=(
            "Candidates must be located in the "
            "United States."
        ),
    ) == (
        RemoteOkGeoClassification
        .EXPLICITLY_INELIGIBLE
    )


@pytest.mark.parametrize(
    "location",
    [
        "Germany",
        "Canada",
        "Brazil",
    ],
)
def test_bare_foreign_country_location_is_unknown(
    location: str,
) -> None:
    assert classify_remoteok_geography(
        location=location
    ) == RemoteOkGeoClassification.UNKNOWN


def test_unknown_location_is_retained() -> None:
    fetch = _fetch(
        [
            _metadata(),
            _job(
                id=1,
                location="Remote",
            ),
        ]
    )

    assert fetch.unknown_geography == 1
    assert fetch.normalized_jobs == 1


def test_date_beats_valid_conflicting_epoch() -> None:
    fetch = _fetch(
        [
            _metadata(),
            _job(
                id=1,
                epoch=1790330400,
                date="2026-09-26T10:00:00Z",
            ),
        ]
    )

    assert fetch.jobs[0].published_at == datetime(
        2026,
        9,
        26,
        10,
        tzinfo=UTC,
    )
    assert fetch.publication_dates_from_date == 1
    assert fetch.publication_dates_from_epoch_fallback == 0


def test_epoch_used_only_when_date_missing_or_malformed() -> None:
    fetch = _fetch(
        [
            _metadata(),
            _job(
                id=1,
                epoch=1790330400,
                date=None,
            ),
            _job(
                id=2,
                epoch=1790330400,
                date="not a date",
            ),
            _job(
                id=3,
                epoch="bad",
                date="not a date",
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
        tzinfo=UTC,
    )
    assert by_id["2"].published_at == datetime(
        2026,
        9,
        25,
        10,
        tzinfo=UTC,
    )
    assert by_id["3"].published_at is None
    assert fetch.publication_dates_parsed == 2
    assert fetch.publication_dates_from_date == 0
    assert fetch.publication_dates_from_epoch_fallback == 2
    assert fetch.publication_dates_missing == 1


def test_only_one_http_request_per_acquisition() -> None:
    calls: list[str] = []
    client = _client(
        [
            _metadata(),
            _job(id=1),
            _job(id=2, location="USA only"),
        ],
        calls=calls,
    )

    fetch = client.fetch_jobs(max_jobs=1)

    assert fetch.requests_made == 1
    assert calls == [REMOTEOK_API_URL]


@pytest.mark.parametrize(
    "max_jobs",
    [0, MAX_REMOTEOK_MAX_JOBS + 1],
)
def test_max_jobs_is_bounded(
    max_jobs: int,
) -> None:
    with pytest.raises(ValueError):
        _fetch([_metadata(), _job(id=1)], max_jobs=max_jobs)


def test_preview_performs_zero_persistence() -> None:
    class ExplodingPersistence:
        def __getattr__(self, name):
            raise AssertionError(
                "preview touched persistence"
            )

    service = RemoteOkJobAcquisitionService(
        client=_client([_metadata(), _job(id=1)]),
        company_import_service=ExplodingPersistence(),
        job_lead_repository=ExplodingPersistence(),
        tracing_repository=ExplodingPersistence(),
        state_repository=ExplodingPersistence(),
    )

    summary = service.preview(max_jobs=10)

    assert summary.normalized_jobs == 1
    assert summary.applied is False
    assert summary.jobs_skipped_during_persistence == 0


def test_apply_persists_companies_and_leads(
    tmp_path,
) -> None:
    database = _database(tmp_path)
    service = _service(
        database,
        _client(
            [
                _metadata(),
                _job(
                    id=10,
                    company="Acme",
                    position="Backend Engineer",
                    apply_url=(
                        "https://example.com/apply"
                    ),
                    salary_min=120000,
                    tags=["Java"],
                ),
                _job(
                    id=11,
                    company="Acme",
                    position="Platform Engineer",
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
            (SourceType.REMOTEOK.value,),
        ).fetchall()
        company_sources = connection.execute(
            """
            SELECT source_type, source_url
            FROM company_sources
            WHERE source_type = ?
            """,
            (SourceType.REMOTEOK.value,),
        ).fetchall()

    assert len(rows) == 2
    assert rows[0]["external_id"] == "10"
    assert rows[0]["title"] == "Backend Engineer"
    assert rows[0]["workplace_type"] == (
        WorkplaceType.REMOTE.value
    )
    assert rows[0]["job_url"] == (
        "https://remoteok.com/remote-jobs/10"
    )
    assert rows[0]["apply_url"] == (
        "https://example.com/apply"
    )
    raw_payload = json_from_db(
        rows[0]["raw_payload_json"]
    )
    assert raw_payload["salary_min"] == 120000
    assert raw_payload["tags"] == ["Java"]
    assert raw_payload[
        "_chamba_source_metadata"
    ]["source"] == SourceType.REMOTEOK.value
    assert len(company_sources) == 2


def test_repeated_apply_is_idempotent(
    tmp_path,
) -> None:
    database = _database(tmp_path)
    service = _service(
        database,
        _client(
            [
                _metadata(),
                _job(
                    id=10,
                    company="Acme",
                ),
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


def test_persistence_skip_counter_increments(
    tmp_path,
) -> None:
    database = _database(tmp_path)
    real_import_service = CompanyImportService(
        CompanyRepository(database),
        CompanySourceRepository(database),
    )

    class FailingCompanyImportService:
        def import_seed(
            self,
            seed,
            *,
            source_metadata,
        ):
            if seed.name == "BadCo":
                raise ValueError(
                    "intentional test import failure"
                )

            return real_import_service.import_seed(
                seed,
                source_metadata=source_metadata,
            )

    service = RemoteOkJobAcquisitionService(
        client=_client(
            [
                _metadata(),
                _job(id=10, company="GoodCo"),
                _job(id=11, company="BadCo"),
            ]
        ),
        company_import_service=(
            FailingCompanyImportService()
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

    summary = service.run(max_jobs=10)

    assert summary.jobs_created == 1
    assert summary.jobs_skipped_during_persistence == 1

    with database.connection() as connection:
        state = connection.execute(
            """
            SELECT metadata_json
            FROM source_acquisition_states
            WHERE source_type = ?
            """,
            (SourceType.REMOTEOK.value,),
        ).fetchone()

    metadata = json_from_db(
        state["metadata_json"]
    )
    assert metadata[
        "jobs_skipped_during_persistence"
    ] == 1


def test_malformed_api_shape_fails() -> None:
    client = _raw_client({"jobs": []})

    with pytest.raises(RemoteOkApiError, match="top-level array"):
        client.fetch_jobs(max_jobs=10)


def test_metadata_only_payload_fails() -> None:
    client = _client([_metadata()])

    with pytest.raises(
        RemoteOkApiError,
        match="no valid job objects",
    ):
        client.fetch_jobs(max_jobs=10)


def test_valid_feed_with_all_jobs_technically_filtered_is_successful() -> None:
    fetch = _fetch(
        [
            _metadata(),
            _job(
                id=1,
                position="Marketing Manager",
                tags=["remote"],
            ),
        ]
    )

    assert fetch.job_objects_parsed == 1
    assert fetch.technical_rejects == 1
    assert fetch.normalized_jobs == 0


def test_429_produces_clear_failure() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(429, json={})

    client = RemoteOkJobsClient(
        transport=httpx.MockTransport(handler)
    )

    with pytest.raises(RemoteOkApiError, match="rate limit"):
        client.fetch_jobs(max_jobs=10)


def _fetch(
    payload: list[object],
    max_jobs: int = 100,
):
    return _client(payload).fetch_jobs(
        max_jobs=max_jobs
    )


def _client(
    payload: list[object],
    calls: list[str] | None = None,
) -> RemoteOkJobsClient:
    return _raw_client(payload, calls=calls)


def _raw_client(
    payload,
    calls: list[str] | None = None,
) -> RemoteOkJobsClient:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        if calls is not None:
            calls.append(str(request.url))

        return httpx.Response(
            200,
            json=payload,
        )

    return RemoteOkJobsClient(
        transport=httpx.MockTransport(handler)
    )


def _metadata() -> dict:
    return {
        "last_updated": "2026-09-25T10:00:00Z",
        "legal": "Preserve Remote OK attribution.",
    }


def _job(
    *,
    id,
    company: str = "Acme",
    position: str = "Backend Engineer",
    tags: list[str] | None = None,
    location: str | None = "Argentina",
    description: str | None = "<p>Build backend APIs.</p>",
    epoch: int | float | str | None = None,
    date: str | None = "2026-09-25T10:00:00Z",
    apply_url: str | None = None,
    salary_min: int | None = None,
    salary_max: int | None = None,
    **extra,
) -> dict:
    return {
        "id": id,
        "slug": f"example-{id}",
        "epoch": epoch,
        "date": date,
        "company": company,
        "company_logo": (
            "https://example.com/logo.png"
        ),
        "position": position,
        "tags": tags or ["backend", "api"],
        "description": description,
        "location": location,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "apply_url": apply_url,
        "url": (
            "https://remoteok.com/remote-jobs/"
            f"{id}"
        ),
        "original": True,
        "logo": "https://example.com/logo2.png",
        **extra,
    }


def _database(tmp_path) -> Database:
    database = Database(tmp_path / "test.db")
    migrate(database)
    return database


def _service(
    database: Database,
    client: RemoteOkJobsClient,
) -> RemoteOkJobAcquisitionService:
    return RemoteOkJobAcquisitionService(
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
