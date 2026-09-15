from datetime import UTC, datetime

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
from chamba_hunter.services.hn_job_acquisition_service import (
    HN_WHO_IS_HIRING_SCOPE_KEY,
    HnJobAcquisitionService,
)
from chamba_hunter.sources.hn_who_is_hiring import (
    HnWhoIsHiringClient,
    HnWhoIsHiringError,
    parse_hn_hiring_comment,
)


def test_discovers_latest_valid_who_is_hiring_thread() -> None:
    client = _client(
        {
            "/v0/user/whoishiring.json": {
                "id": "whoishiring",
                "submitted": [
                    100,
                    200,
                    300,
                ],
            },
            "/v0/item/100.json": _story(
                100,
                "Ask HN: Who wants to be hired? (September 2026)",
                time=1_789_000_000,
            ),
            "/v0/item/200.json": _story(
                200,
                "Ask HN: Who is hiring? (August 2026)",
                time=1_785_000_000,
            ),
            "/v0/item/300.json": _story(
                300,
                "Ask HN: Who is hiring? (September 2026)",
                time=1_788_000_000,
            ),
        }
    )

    fetch = client.fetch_latest_thread()

    assert fetch.thread.id == 300
    assert fetch.thread.title == (
        "Ask HN: Who is hiring? (September 2026)"
    )


def test_explicit_valid_thread_id() -> None:
    client = _client(
        {
            "/v0/item/49522897.json": _story(
                49522897,
                "Ask HN: Who is hiring? (September 2026)",
            ),
        }
    )

    fetch = client.fetch_thread(
        49522897
    )

    assert fetch.thread.id == 49522897


def test_rejects_explicit_non_hiring_thread() -> None:
    client = _client(
        {
            "/v0/item/123.json": _story(
                123,
                "Ask HN: Who wants to be hired? (September 2026)",
            ),
        }
    )

    with pytest.raises(
        HnWhoIsHiringError
    ):
        client.fetch_thread(123)


def test_processes_top_level_comments_only_and_ignores_replies() -> None:
    client = _client(
        {
            "/v0/item/500.json": _story(
                500,
                kids=[501],
            ),
            "/v0/item/501.json": _comment(
                501,
                "Acme | Backend Engineer | REMOTE",
                kids=[999],
            ),
        }
    )

    fetch = client.fetch_thread(500)

    assert [
        post.comment_id
        for post in fetch.posts
    ] == [501]


def test_skips_deleted_dead_and_blank_comments() -> None:
    client = _client(
        {
            "/v0/item/500.json": _story(
                500,
                kids=[501, 502, 503, 504],
            ),
            "/v0/item/501.json": _comment(
                501,
                "Acme | Backend Engineer | REMOTE",
            ),
            "/v0/item/502.json": {
                "id": 502,
                "type": "comment",
                "deleted": True,
            },
            "/v0/item/503.json": {
                "id": 503,
                "type": "comment",
                "dead": True,
                "text": "DeadCo | Backend Engineer",
            },
            "/v0/item/504.json": _comment(
                504,
                "   ",
            ),
        }
    )

    fetch = client.fetch_thread(500)

    assert [
        post.company_name
        for post in fetch.posts
    ] == ["Acme"]
    assert fetch.deleted_dead_skipped == 2
    assert fetch.invalid_skipped == 1


def test_single_role_pipe_header_parsing() -> None:
    post = _parsed_post(
        (
            "Cora AI | Founding Full Stack / Applied AI "
            "Engineer | REMOTE | Full-time"
        )
    )

    assert post.company_name == "Cora AI"
    assert post.title == (
        "Founding Full Stack / Applied AI Engineer"
    )
    assert post.workplace_type == WorkplaceType.REMOTE
    assert post.employment_type == "Full-time"


def test_multi_role_header_is_one_summarized_lead() -> None:
    post = _parsed_post(
        "Company | Backend, Frontend, SRE | REMOTE"
    )

    assert post.title == "Backend, Frontend, SRE"


def test_title_falls_back_to_hiring_at_company() -> None:
    post = _parsed_post(
        "Acme | REMOTE | Full-time"
    )

    assert post.title == "Hiring at Acme"


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (
            "Acme | Backend Engineer | REMOTE",
            WorkplaceType.REMOTE,
        ),
        (
            "Acme | Backend Engineer | HYBRID | NYC",
            WorkplaceType.HYBRID,
        ),
        (
            "Acme | Backend Engineer | ON-SITE | Berlin",
            WorkplaceType.ONSITE,
        ),
    ],
)
def test_explicit_workplace_parsing(
    header: str,
    expected: WorkplaceType,
) -> None:
    assert _parsed_post(header).workplace_type == expected


def test_hn_unix_time_becomes_published_at() -> None:
    post = _parsed_post(
        "Acme | Backend Engineer",
        time=1_788_480_000,
    )

    assert post.posted_at == datetime(
        2026,
        9,
        4,
        0,
        0,
        tzinfo=UTC,
    )


def test_extracts_public_urls_conservatively() -> None:
    post = _parsed_post(
        (
            'Acme | Backend Engineer | <a href="https://acme.example">'
            "https://acme.example</a><p>"
            'Apply at <a href="https://jobs.lever.co/acme/123">'
            "careers</a>"
        )
    )

    assert post.extracted_urls == (
        "https://acme.example",
        "https://jobs.lever.co/acme/123",
    )
    assert post.website_url == "https://acme.example"


def test_explicit_apply_url_where_clear() -> None:
    post = _parsed_post(
        (
            "Acme | Backend Engineer | REMOTE<p>"
            "Apply: https://acme.example/careers/backend"
        )
    )

    assert post.apply_url == (
        "https://acme.example/careers/backend"
    )


def test_service_resolves_company_through_import_service(
    tmp_path,
) -> None:
    database = _database(tmp_path)
    service = _service(
        database,
        _client(
            {
                "/v0/item/500.json": _story(
                    500,
                    kids=[501],
                ),
                "/v0/item/501.json": _comment(
                    501,
                    (
                        "Acme | Backend Engineer | REMOTE<p>"
                        "https://acme.example"
                    ),
                ),
            }
        ),
    )

    summary = service.run(
        thread_id=500
    )

    company = CompanyRepository(
        database
    ).get_by_domain("acme.example")
    sources = (
        CompanySourceRepository(
            database
        )
        .list_by_source_type(
            SourceType.HACKERNEWS
        )
    )

    assert company is not None
    assert summary.companies_resolved == 1
    assert [
        source.external_id
        for source in sources
    ] == ["501"]


def test_service_idempotent_second_ingestion_updates(
    tmp_path,
) -> None:
    database = _database(tmp_path)
    service = _service(
        database,
        _client(
            {
                "/v0/item/500.json": _story(
                    500,
                    kids=[501],
                ),
                "/v0/item/501.json": _comment(
                    501,
                    "Acme | Backend Engineer | REMOTE",
                ),
            }
        ),
    )

    first = service.run(
        thread_id=500
    )
    first_row = _job_lead_row(
        database,
        "501",
    )
    second = service.run(
        thread_id=500
    )
    second_row = _job_lead_row(
        database,
        "501",
    )

    assert first.jobs_created == 1
    assert first.jobs_updated == 0
    assert second.jobs_created == 0
    assert second.jobs_updated == 1
    assert _job_lead_count(database) == 1
    assert second_row["first_seen_at"] == (
        first_row["first_seen_at"]
    )


def test_missing_later_comment_does_not_deactivate_existing_lead(
    tmp_path,
) -> None:
    database = _database(tmp_path)
    first_client = _client(
        {
            "/v0/item/500.json": _story(
                500,
                kids=[501, 502],
            ),
            "/v0/item/501.json": _comment(
                501,
                "Acme | Backend Engineer",
            ),
            "/v0/item/502.json": _comment(
                502,
                "Beta | Platform Engineer",
            ),
        }
    )
    second_client = _client(
        {
            "/v0/item/500.json": _story(
                500,
                kids=[501],
            ),
            "/v0/item/501.json": _comment(
                501,
                "Acme | Backend Engineer",
            ),
        }
    )

    _service(
        database,
        first_client,
    ).run(thread_id=500)
    _service(
        database,
        second_client,
    ).run(thread_id=500)

    assert _job_lead_count(database) == 2
    assert _job_lead_row(
        database,
        "502",
    )["is_active"] == 1


def test_repository_accepts_hackernews_and_rejects_unsupported(
    tmp_path,
) -> None:
    database = _database(tmp_path)
    company_id = _import_company(
        database,
        "Acme",
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
        SourceType.HACKERNEWS,
        [
            JobLead(
                company_id=company_id,
                source_type=(
                    SourceType.HACKERNEWS
                ),
                external_id="501",
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
                    external_id="other",
                    title="Other Engineer",
                    first_seen_at=seen_at,
                    last_seen_at=seen_at,
                )
            ],
            seen_at,
        )


def test_limit_is_deterministic(tmp_path) -> None:
    database = _database(tmp_path)
    service = _service(
        database,
        _client(
            {
                "/v0/item/500.json": _story(
                    500,
                    kids=[501, 502, 503],
                ),
                "/v0/item/501.json": _comment(
                    501,
                    "Alpha | Backend Engineer",
                ),
                "/v0/item/502.json": _comment(
                    502,
                    "Beta | Platform Engineer",
                ),
                "/v0/item/503.json": _comment(
                    503,
                    "Gamma | Data Engineer",
                ),
            }
        ),
    )

    summary = service.run(
        thread_id=500,
        limit=2,
    )

    assert summary.comments_fetched == 2
    assert _job_external_ids(database) == [
        "501",
        "502",
    ]


def test_records_acquisition_state_metadata(
    tmp_path,
) -> None:
    database = _database(tmp_path)

    _service(
        database,
        _client(
            {
                "/v0/item/500.json": _story(
                    500,
                    kids=[501],
                ),
                "/v0/item/501.json": _comment(
                    501,
                    "Acme | Backend Engineer",
                ),
            }
        ),
    ).run(thread_id=500)

    state = SourceAcquisitionStateRepository(
        database
    ).get(
        source_type=SourceType.HACKERNEWS,
        scope_key=HN_WHO_IS_HIRING_SCOPE_KEY,
    )

    assert state is not None
    assert state.metadata["thread_id"] == 500
    assert state.metadata["jobs_created"] == 1


def _client(
    responses: dict[str, dict],
) -> HnWhoIsHiringClient:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        payload = responses.get(
            request.url.path
        )

        if payload is None:
            raise AssertionError(
                f"Unexpected HN request: {request.url}"
            )

        return httpx.Response(
            200,
            json=payload,
        )

    return HnWhoIsHiringClient(
        transport=httpx.MockTransport(
            handler
        )
    )


def _story(
    item_id: int,
    title: str = "Ask HN: Who is hiring? (September 2026)",
    *,
    by: str = "whoishiring",
    time: int = 1_788_220_800,
    kids: list[int] | None = None,
) -> dict:
    return {
        "id": item_id,
        "type": "story",
        "by": by,
        "title": title,
        "time": time,
        "kids": kids or [],
    }


def _comment(
    item_id: int,
    text: str,
    *,
    time: int = 1_788_220_800,
    kids: list[int] | None = None,
) -> dict:
    payload = {
        "id": item_id,
        "type": "comment",
        "by": f"user{item_id}",
        "time": time,
        "text": text,
    }

    if kids is not None:
        payload["kids"] = kids

    return payload


def _parsed_post(
    text: str,
    *,
    time: int = 1_788_220_800,
):
    thread = _client(
        {
            "/v0/item/500.json": _story(
                500
            )
        }
    ).fetch_thread(500).thread
    post = parse_hn_hiring_comment(
        thread=thread,
        comment=_comment(
            501,
            text,
            time=time,
        ),
    )
    assert post is not None
    return post


def _database(tmp_path) -> Database:
    database = Database(
        tmp_path / "test.db"
    )
    migrate(database)
    return database


def _service(
    database: Database,
    client: HnWhoIsHiringClient,
) -> HnJobAcquisitionService:
    company_source_repository = (
        CompanySourceRepository(
            database
        )
    )

    return HnJobAcquisitionService(
        client=client,
        company_import_service=(
            CompanyImportService(
                CompanyRepository(database),
                company_source_repository,
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


def _import_company(
    database: Database,
    name: str,
) -> int:
    result = CompanyImportService(
        CompanyRepository(database),
        CompanySourceRepository(database),
    ).import_seed(
        CompanySeedInput(
            name=name,
            source_type=SourceType.MANUAL,
        )
    )

    assert result.company.id is not None
    return result.company.id


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
                SourceType.HACKERNEWS.value,
                external_id,
            ),
        ).fetchone()

    assert row is not None
    return row


def _job_lead_count(
    database: Database,
) -> int:
    with database.connection() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS count FROM job_leads"
        ).fetchone()

    return int(row["count"])


def _job_external_ids(
    database: Database,
) -> list[str]:
    with database.connection() as connection:
        rows = connection.execute(
            """
            SELECT external_id
            FROM job_leads
            WHERE source_type = ?
            ORDER BY external_id
            """,
            (
                SourceType.HACKERNEWS.value,
            ),
        ).fetchall()

    return [
        str(row["external_id"])
        for row in rows
    ]
