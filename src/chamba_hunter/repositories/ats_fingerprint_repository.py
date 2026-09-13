from dataclasses import replace
import sqlite3

from chamba_hunter.db.connection import Database
from chamba_hunter.db.converters import (
    datetime_from_db,
    datetime_to_db,
    json_from_db,
    json_to_db,
)
from chamba_hunter.domain.ats_fingerprints import (
    AtsFingerprint,
)
from chamba_hunter.domain.enums import (
    AtsFingerprintStatus,
    AtsSupportStatus,
)


def _row_to_fingerprint(
    row: sqlite3.Row,
) -> AtsFingerprint:
    return AtsFingerprint(
        id=row["id"],
        run_step_id=row["run_step_id"],
        company_scan_id=row["company_scan_id"],
        company_id=row["company_id"],
        input_url=row["input_url"],
        final_url=row["final_url"],
        fingerprint_status=(
            AtsFingerprintStatus(
                row["fingerprint_status"]
            )
        ),
        provider_family=(
            row["provider_family"]
        ),
        support_status=(
            AtsSupportStatus(
                row["support_status"]
            )
        ),
        confidence=row["confidence"],
        detection_method=(
            row["detection_method"]
        ),
        evidence=row["evidence"],
        http_status=row["http_status"],
        error_type=row["error_type"],
        error_message=row["error_message"],
        scanned_at=datetime_from_db(
            row["scanned_at"]
        ),
        metadata=json_from_db(
            row["metadata_json"]
        ),
    )


class AtsFingerprintRepository:
    def __init__(
        self,
        database: Database,
    ) -> None:
        self.database = database

    def add(
        self,
        fingerprint: AtsFingerprint,
    ) -> AtsFingerprint:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO ats_fingerprints (
                    run_step_id,
                    company_scan_id,
                    company_id,
                    input_url,
                    final_url,
                    fingerprint_status,
                    provider_family,
                    support_status,
                    confidence,
                    detection_method,
                    evidence,
                    http_status,
                    error_type,
                    error_message,
                    scanned_at,
                    metadata_json
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    fingerprint.run_step_id,
                    fingerprint.company_scan_id,
                    fingerprint.company_id,
                    fingerprint.input_url,
                    fingerprint.final_url,
                    (
                        fingerprint
                        .fingerprint_status
                        .value
                    ),
                    fingerprint.provider_family,
                    (
                        fingerprint
                        .support_status
                        .value
                    ),
                    fingerprint.confidence,
                    fingerprint.detection_method,
                    fingerprint.evidence,
                    fingerprint.http_status,
                    fingerprint.error_type,
                    fingerprint.error_message,
                    datetime_to_db(
                        fingerprint.scanned_at
                    ),
                    json_to_db(
                        fingerprint.metadata
                    ),
                ),
            )

            fingerprint_id = cursor.lastrowid

        if fingerprint_id is None:
            raise RuntimeError(
                "SQLite did not return an "
                "ATS fingerprint id."
            )

        return replace(
            fingerprint,
            id=fingerprint_id,
        )

    def list_for_company(
        self,
        company_id: int,
    ) -> list[AtsFingerprint]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM ats_fingerprints
                WHERE company_id = ?
                ORDER BY scanned_at, id
                """,
                (company_id,),
            ).fetchall()

        return [
            _row_to_fingerprint(row)
            for row in rows
        ]

    def latest_for_company(
        self,
        company_id: int,
    ) -> AtsFingerprint | None:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM ats_fingerprints
                WHERE company_id = ?
                ORDER BY scanned_at DESC, id DESC
                LIMIT 1
                """,
                (company_id,),
            ).fetchone()

        if row is None:
            return None

        return _row_to_fingerprint(row)
