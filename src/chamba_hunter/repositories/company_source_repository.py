from dataclasses import replace
import sqlite3

from chamba_hunter.db.connection import Database
from chamba_hunter.db.converters import (
    datetime_from_db,
    datetime_to_db,
    json_from_db,
    json_to_db,
)
from chamba_hunter.domain.enums import SourceType
from chamba_hunter.domain.models import CompanySource


def _row_to_company_source(row: sqlite3.Row) -> CompanySource:
    return CompanySource(
        id=row["id"],
        company_id=row["company_id"],
        source_type=SourceType(row["source_type"]),
        external_id=row["external_id"],
        source_url=row["source_url"],
        raw_name=row["raw_name"],
        metadata=json_from_db(row["metadata_json"]),
        first_seen_at=datetime_from_db(row["first_seen_at"]),
        last_seen_at=datetime_from_db(row["last_seen_at"]),
    )


class CompanySourceRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def find_company_id(
        self,
        source_type: SourceType,
        external_id: str | None = None,
        source_url: str | None = None,
    ) -> int | None:
        if external_id is None and source_url is None:
            return None

        with self.database.connection() as connection:
            if external_id is not None:
                row = connection.execute(
                    """
                    SELECT company_id
                    FROM company_sources
                    WHERE source_type = ?
                      AND external_id = ?
                    LIMIT 1
                    """,
                    (
                        source_type.value,
                        external_id,
                    ),
                ).fetchone()

            else:
                row = connection.execute(
                    """
                    SELECT company_id
                    FROM company_sources
                    WHERE source_type = ?
                      AND source_url = ?
                    LIMIT 1
                    """,
                    (
                        source_type.value,
                        source_url,
                    ),
                ).fetchone()

        if row is None:
            return None

        return row["company_id"]

    def add_or_touch(
        self,
        source: CompanySource,
    ) -> CompanySource:
        existing = self._find_existing(source)

        if existing is not None:
            if existing.company_id != source.company_id:
                raise ValueError(
                    "Source identity is already associated with "
                    f"company {existing.company_id}, but import tried "
                    f"to associate it with company {source.company_id}."
                )

            with self.database.transaction() as connection:
                connection.execute(
                    """
                    UPDATE company_sources
                    SET
                        last_seen_at = ?,
                        raw_name = ?,
                        metadata_json = ?
                    WHERE id = ?
                    """,
                    (
                        datetime_to_db(source.last_seen_at),
                        source.raw_name,
                        json_to_db(source.metadata),
                        existing.id,
                    ),
                )

            return replace(
                existing,
                raw_name=source.raw_name,
                metadata=source.metadata,
                last_seen_at=source.last_seen_at,
            )

        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO company_sources (
                    company_id,
                    source_type,
                    external_id,
                    source_url,
                    raw_name,
                    metadata_json,
                    first_seen_at,
                    last_seen_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source.company_id,
                    source.source_type.value,
                    source.external_id,
                    source.source_url,
                    source.raw_name,
                    json_to_db(source.metadata),
                    datetime_to_db(source.first_seen_at),
                    datetime_to_db(source.last_seen_at),
                ),
            )

            source_id = cursor.lastrowid

        if source_id is None:
            raise RuntimeError(
                "SQLite did not return an id for the inserted source."
            )

        return replace(
            source,
            id=source_id,
        )

    def list_for_company(
        self,
        company_id: int,
    ) -> list[CompanySource]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM company_sources
                WHERE company_id = ?
                ORDER BY id
                """,
                (company_id,),
            ).fetchall()

        return [
            _row_to_company_source(row)
            for row in rows
        ]

    def _find_existing(
        self,
        source: CompanySource,
    ) -> CompanySource | None:
        with self.database.connection() as connection:
            if source.external_id is not None:
                row = connection.execute(
                    """
                    SELECT *
                    FROM company_sources
                    WHERE source_type = ?
                      AND external_id = ?
                    LIMIT 1
                    """,
                    (
                        source.source_type.value,
                        source.external_id,
                    ),
                ).fetchone()

            elif source.source_url is not None:
                row = connection.execute(
                    """
                    SELECT *
                    FROM company_sources
                    WHERE company_id = ?
                      AND source_type = ?
                      AND source_url = ?
                    LIMIT 1
                    """,
                    (
                        source.company_id,
                        source.source_type.value,
                        source.source_url,
                    ),
                ).fetchone()

            else:
                row = connection.execute(
                    """
                    SELECT *
                    FROM company_sources
                    WHERE company_id = ?
                      AND source_type = ?
                      AND external_id IS NULL
                      AND source_url IS NULL
                    LIMIT 1
                    """,
                    (
                        source.company_id,
                        source.source_type.value,
                    ),
                ).fetchone()

        if row is None:
            return None

        return _row_to_company_source(row)

    def list_by_source_type(
        self,
        source_type: SourceType,
    ) -> list[CompanySource]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM company_sources
                WHERE source_type = ?
                ORDER BY id
                """,
                (source_type.value,),
            ).fetchall()

        return [
            _row_to_company_source(row)
            for row in rows
        ]