from pathlib import Path
import re
import sqlite3

from chamba_hunter.db.connection import Database, PROJECT_ROOT
from chamba_hunter.domain.common import utc_now


DEFAULT_MIGRATIONS_DIR = PROJECT_ROOT / "migrations"

MIGRATION_FILENAME_PATTERN = re.compile(r"^\d{3}_.+\.sql$")


def _to_db_datetime() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _ensure_migrations_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    connection.commit()


def _get_applied_migrations(
    connection: sqlite3.Connection,
) -> set[str]:
    rows = connection.execute(
        """
        SELECT version
        FROM schema_migrations
        """
    ).fetchall()

    return {row["version"] for row in rows}


def migrate(
    database: Database | None = None,
    migrations_dir: Path = DEFAULT_MIGRATIONS_DIR,
) -> list[str]:
    database = database or Database()

    if not migrations_dir.exists():
        raise RuntimeError(
            f"Migrations directory does not exist: {migrations_dir}"
        )

    migration_files = sorted(
        path
        for path in migrations_dir.glob("*.sql")
        if MIGRATION_FILENAME_PATTERN.match(path.name)
    )

    applied_now: list[str] = []

    with database.connection() as connection:
        _ensure_migrations_table(connection)

        already_applied = _get_applied_migrations(connection)

        for migration_file in migration_files:
            if migration_file.name in already_applied:
                continue

            migration_sql = migration_file.read_text(encoding="utf-8")

            version = _sql_literal(migration_file.name)
            applied_at = _sql_literal(_to_db_datetime())

            script = f"""
            BEGIN IMMEDIATE;

            {migration_sql}

            INSERT INTO schema_migrations (
                version,
                applied_at
            )
            VALUES (
                {version},
                {applied_at}
            );

            COMMIT;
            """

            try:
                connection.executescript(script)
            except Exception:
                connection.rollback()
                raise

            applied_now.append(migration_file.name)

    return applied_now


def main() -> None:
    database = Database()

    applied = migrate(database)

    if applied:
        for migration in applied:
            print(f"Applied migration: {migration}")
    else:
        print("Database is already up to date.")

    print(f"Database: {database.path}")


if __name__ == "__main__":
    main()