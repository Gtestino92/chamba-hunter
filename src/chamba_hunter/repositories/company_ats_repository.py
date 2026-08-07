from dataclasses import replace
import sqlite3

from chamba_hunter.db.connection import Database
from chamba_hunter.db.converters import (
    datetime_from_db,
    datetime_to_db,
)
from chamba_hunter.domain.common import utc_now
from chamba_hunter.domain.enums import AtsProvider
from chamba_hunter.domain.models import CompanyAts


def _row_to_company_ats(
    row: sqlite3.Row,
) -> CompanyAts:
    return CompanyAts(
        id=row["id"],
        company_id=row["company_id"],
        provider=AtsProvider(
            row["provider"]
        ),
        external_identifier=(
            row["external_identifier"]
        ),
        board_url=row["board_url"],
        is_primary=bool(
            row["is_primary"]
        ),
        is_active=bool(
            row["is_active"]
        ),
        detected_at=datetime_from_db(
            row["detected_at"]
        ),
        last_validated_at=(
            datetime_from_db(
                row["last_validated_at"]
            )
            if row["last_validated_at"]
            is not None
            else None
        ),
        last_successful_sync_at=(
            datetime_from_db(
                row[
                    "last_successful_sync_at"
                ]
            )
            if row[
                "last_successful_sync_at"
            ] is not None
            else None
        ),
        source_detection_id=(
            row["source_detection_id"]
        ),
    )


class CompanyAtsRepository:
    def __init__(
        self,
        database: Database,
    ) -> None:
        self.database = database

    def upsert(
        self,
        company_ats: CompanyAts,
    ) -> CompanyAts:
        existing = self._find_existing(
            company_ats
        )

        validated_at = utc_now()

        if existing is not None:
            updated = replace(
                existing,
                external_identifier=(
                    company_ats.external_identifier
                    if (
                        company_ats
                        .external_identifier
                        is not None
                    )
                    else (
                        existing
                        .external_identifier
                    )
                ),
                board_url=(
                    company_ats.board_url
                    if company_ats.board_url
                    is not None
                    else existing.board_url
                ),
                is_primary=True,
                is_active=True,
                last_validated_at=(
                    validated_at
                ),
                source_detection_id=(
                    company_ats
                    .source_detection_id
                ),
            )

            with self.database.transaction() as connection:
                connection.execute(
                    """
                    UPDATE company_ats
                    SET
                        is_primary = 0,
                        is_active = 0
                    WHERE company_id = ?
                      AND id != ?
                    """,
                    (
                        company_ats.company_id,
                        existing.id,
                    ),
                )

                connection.execute(
                    """
                    UPDATE company_ats
                    SET
                        external_identifier = ?,
                        board_url = ?,
                        is_primary = 1,
                        is_active = 1,
                        last_validated_at = ?,
                        source_detection_id = ?
                    WHERE id = ?
                    """,
                    (
                        updated.external_identifier,
                        updated.board_url,
                        datetime_to_db(
                            validated_at
                        ),
                        updated.source_detection_id,
                        existing.id,
                    ),
                )

            return updated

        inserted = replace(
            company_ats,
            is_primary=True,
            is_active=True,
            last_validated_at=(
                validated_at
            ),
        )

        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE company_ats
                SET
                    is_primary = 0,
                    is_active = 0
                WHERE company_id = ?
                """,
                (
                    company_ats.company_id,
                ),
            )

            cursor = connection.execute(
                """
                INSERT INTO company_ats (
                    company_id,
                    provider,
                    external_identifier,
                    board_url,
                    is_primary,
                    is_active,
                    detected_at,
                    last_validated_at,
                    last_successful_sync_at,
                    source_detection_id
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?
                )
                """,
                (
                    inserted.company_id,
                    inserted.provider.value,
                    inserted.external_identifier,
                    inserted.board_url,
                    1,
                    1,
                    datetime_to_db(
                        inserted.detected_at
                    ),
                    datetime_to_db(
                        validated_at
                    ),
                    None,
                    inserted.source_detection_id,
                ),
            )

            company_ats_id = (
                cursor.lastrowid
            )

        if company_ats_id is None:
            raise RuntimeError(
                "SQLite did not return "
                "a company ATS id."
            )

        return replace(
            inserted,
            id=company_ats_id,
        )

    def list_active_primary_by_provider(
        self,
        provider: AtsProvider,
    ) -> list[CompanyAts]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM company_ats
                WHERE provider = ?
                  AND is_primary = 1
                  AND is_active = 1
                  AND external_identifier IS NOT NULL
                ORDER BY company_id, id
                """,
                (
                    provider.value,
                ),
            ).fetchall()

        return [
            _row_to_company_ats(row)
            for row in rows
        ]

    def mark_successful_sync(
        self,
        company_ats_id: int,
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE company_ats
                SET last_successful_sync_at = ?
                WHERE id = ?
                """,
                (
                    datetime_to_db(
                        utc_now()
                    ),
                    company_ats_id,
                ),
            )

    def _find_existing(
        self,
        company_ats: CompanyAts,
    ) -> CompanyAts | None:
        with self.database.connection() as connection:
            row = None

            if (
                company_ats
                .external_identifier
                is not None
            ):
                row = connection.execute(
                    """
                    SELECT *
                    FROM company_ats
                    WHERE company_id = ?
                      AND provider = ?
                      AND external_identifier = ?
                    LIMIT 1
                    """,
                    (
                        company_ats.company_id,
                        company_ats.provider.value,
                        (
                            company_ats
                            .external_identifier
                        ),
                    ),
                ).fetchone()

                if row is None:
                    row = connection.execute(
                        """
                        SELECT *
                        FROM company_ats
                        WHERE company_id = ?
                          AND provider = ?
                          AND external_identifier IS NULL
                        ORDER BY id
                        LIMIT 1
                        """,
                        (
                            company_ats.company_id,
                            company_ats.provider.value,
                        ),
                    ).fetchone()

            else:
                row = connection.execute(
                    """
                    SELECT *
                    FROM company_ats
                    WHERE company_id = ?
                      AND provider = ?
                    ORDER BY
                        CASE
                            WHEN external_identifier
                                 IS NOT NULL
                            THEN 0
                            ELSE 1
                        END,
                        id
                    LIMIT 1
                    """,
                    (
                        company_ats.company_id,
                        company_ats.provider.value,
                    ),
                ).fetchone()

        if row is None:
            return None

        return _row_to_company_ats(
            row
        )