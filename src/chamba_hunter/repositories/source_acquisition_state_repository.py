from dataclasses import dataclass
from datetime import datetime

from chamba_hunter.db.connection import Database
from chamba_hunter.db.converters import (
    datetime_from_db,
    datetime_to_db,
    json_from_db,
    json_to_db,
)
from chamba_hunter.domain.common import JsonObject
from chamba_hunter.domain.enums import SourceType


@dataclass(frozen=True, slots=True)
class SourceAcquisitionState:
    source_type: SourceType
    scope_key: str

    last_successful_started_at: datetime
    last_successful_finished_at: datetime

    last_backfill_finished_at: datetime | None

    metadata: JsonObject


class SourceAcquisitionStateRepository:
    def __init__(
        self,
        database: Database,
    ) -> None:
        self.database = database

    def get(
        self,
        *,
        source_type: SourceType,
        scope_key: str,
    ) -> SourceAcquisitionState | None:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT
                    source_type,
                    scope_key,
                    last_successful_started_at,
                    last_successful_finished_at,
                    last_backfill_finished_at,
                    metadata_json
                FROM source_acquisition_states
                WHERE source_type = ?
                  AND scope_key = ?
                """,
                (
                    source_type.value,
                    scope_key,
                ),
            ).fetchone()

        if row is None:
            return None

        raw_metadata = json_from_db(
            str(row["metadata_json"])
        )

        metadata: JsonObject = (
            raw_metadata
            if isinstance(raw_metadata, dict)
            else {}
        )

        return SourceAcquisitionState(
            source_type=SourceType(
                str(row["source_type"])
            ),
            scope_key=str(
                row["scope_key"]
            ),
            last_successful_started_at=(
                datetime_from_db(
                    str(
                        row[
                            "last_successful_started_at"
                        ]
                    )
                )
            ),
            last_successful_finished_at=(
                datetime_from_db(
                    str(
                        row[
                            "last_successful_finished_at"
                        ]
                    )
                )
            ),
            last_backfill_finished_at=(
                datetime_from_db(
                    str(
                        row[
                            "last_backfill_finished_at"
                        ]
                    )
                )
                if row[
                    "last_backfill_finished_at"
                ]
                is not None
                else None
            ),
            metadata=metadata,
        )

    def record_success(
        self,
        *,
        source_type: SourceType,
        scope_key: str,
        started_at: datetime,
        finished_at: datetime,
        is_backfill: bool,
        metadata: JsonObject,
    ) -> None:
        started_at_db = datetime_to_db(
            started_at
        )
        finished_at_db = datetime_to_db(
            finished_at
        )

        metadata_db = json_to_db(
            metadata
        )

        if metadata_db is None:
            metadata_db = "{}"

        backfill_finished_at_db = (
            finished_at_db
            if is_backfill
            else None
        )

        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO source_acquisition_states (
                    source_type,
                    scope_key,
                    last_successful_started_at,
                    last_successful_finished_at,
                    last_backfill_finished_at,
                    metadata_json,
                    created_at,
                    updated_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT (
                    source_type,
                    scope_key
                )
                DO UPDATE SET
                    last_successful_started_at =
                        excluded.last_successful_started_at,
                    last_successful_finished_at =
                        excluded.last_successful_finished_at,
                    last_backfill_finished_at =
                        COALESCE(
                            excluded.last_backfill_finished_at,
                            source_acquisition_states
                                .last_backfill_finished_at
                        ),
                    metadata_json =
                        excluded.metadata_json,
                    updated_at =
                        excluded.updated_at
                """,
                (
                    source_type.value,
                    scope_key,
                    started_at_db,
                    finished_at_db,
                    backfill_finished_at_db,
                    metadata_db,
                    finished_at_db,
                    finished_at_db,
                ),
            )
