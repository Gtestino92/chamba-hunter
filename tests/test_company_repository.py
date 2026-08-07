from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate


def test_migrations_are_applied_once(tmp_path):
    database = Database(tmp_path / "test.db")

    first_run = migrate(database)
    second_run = migrate(database)

    assert first_run == ["001_initial_schema.sql"]
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

        applied_migration = connection.execute(
            """
            SELECT version
            FROM schema_migrations
            """
        ).fetchone()

    assert companies_table is not None
    assert applied_migration["version"] == "001_initial_schema.sql"