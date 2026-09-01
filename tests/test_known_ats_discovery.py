from datetime import datetime, timezone

from chamba_hunter.commands.discover_known_ats import _target_company_ids
from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate


def _insert_company(
    database: Database,
    *,
    name: str,
    website_url: str | None,
    careers_url: str | None = None,
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with database.transaction() as connection:
        cursor = connection.execute(
            """
            INSERT INTO companies (
                name,
                normalized_name,
                website_url,
                careers_url,
                status,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, 'ACTIVE', ?, ?)
            """,
            (
                name,
                name.casefold(),
                website_url,
                careers_url,
                now,
                now,
            ),
        )
    assert cursor.lastrowid is not None
    return int(cursor.lastrowid)


def test_known_discovery_does_not_require_a_job_lead(tmp_path) -> None:
    database = Database(tmp_path / "test.db")
    migrate(database)

    target_id = _insert_company(
        database,
        name="Known Company",
        website_url="https://known.example",
    )
    _insert_company(
        database,
        name="No Entrypoint",
        website_url=None,
    )

    targets = _target_company_ids(database=database, limit=25)
    assert target_id in targets
