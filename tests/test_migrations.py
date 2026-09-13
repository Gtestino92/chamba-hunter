from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import (
    DEFAULT_MIGRATIONS_DIR,
    MIGRATION_FILENAME_PATTERN,
    migrate,
)


def test_migrations_are_applied_once(tmp_path):
    database = Database(tmp_path / "test.db")
    expected_migrations = [
        path.name
        for path in sorted(
            DEFAULT_MIGRATIONS_DIR.glob(
                "*.sql"
            )
        )
        if MIGRATION_FILENAME_PATTERN.match(
            path.name
        )
    ]

    first_run = migrate(database)
    second_run = migrate(database)

    assert first_run == expected_migrations
    assert second_run == []

    with database.connection() as connection:
        companies_table = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'companies'
            """
        ).fetchone()

        applied_migrations = connection.execute(
            """
            SELECT version
            FROM schema_migrations
            ORDER BY version
            """
        ).fetchall()

    assert companies_table is not None
    assert [
        row["version"]
        for row in applied_migrations
    ] == expected_migrations
