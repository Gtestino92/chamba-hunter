from dataclasses import replace

from chamba_hunter.db.connection import Database
from chamba_hunter.db.converters import (
    bool_to_db,
    datetime_to_db,
    json_to_db,
)
from chamba_hunter.domain.common import utc_now
from chamba_hunter.domain.enums import (
    AtsScanStatus,
    RunStatus,
)
from chamba_hunter.domain.tracing import (
    AtsDetection,
    AtsSync,
    CompanyScan,
    Run,
    RunStep,
)


class TracingRepository:
    def __init__(
        self,
        database: Database,
    ) -> None:
        self.database = database

    def add_run(
        self,
        run: Run,
    ) -> Run:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO runs (
                    command,
                    started_at,
                    finished_at,
                    status,
                    created_by,
                    notes
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run.command,
                    datetime_to_db(
                        run.started_at
                    ),
                    (
                        datetime_to_db(
                            run.finished_at
                        )
                        if run.finished_at
                        is not None
                        else None
                    ),
                    run.status.value,
                    run.created_by.value,
                    run.notes,
                ),
            )

            run_id = cursor.lastrowid

        if run_id is None:
            raise RuntimeError(
                "SQLite did not return "
                "a run id."
            )

        return replace(
            run,
            id=run_id,
        )

    def finish_run(
        self,
        run_id: int,
        status: RunStatus,
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE runs
                SET
                    finished_at = ?,
                    status = ?
                WHERE id = ?
                """,
                (
                    datetime_to_db(
                        utc_now()
                    ),
                    status.value,
                    run_id,
                ),
            )

    def add_run_step(
        self,
        step: RunStep,
    ) -> RunStep:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO run_steps (
                    run_id,
                    step_name,
                    started_at,
                    finished_at,
                    status,
                    items_total,
                    items_success,
                    items_failed,
                    items_skipped,
                    metadata_json,
                    error_message
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?
                )
                """,
                (
                    step.run_id,
                    step.step_name,
                    datetime_to_db(
                        step.started_at
                    ),
                    (
                        datetime_to_db(
                            step.finished_at
                        )
                        if step.finished_at
                        is not None
                        else None
                    ),
                    step.status.value,
                    step.items_total,
                    step.items_success,
                    step.items_failed,
                    step.items_skipped,
                    json_to_db(
                        step.metadata
                    ),
                    step.error_message,
                ),
            )

            step_id = cursor.lastrowid

        if step_id is None:
            raise RuntimeError(
                "SQLite did not return "
                "a run step id."
            )

        return replace(
            step,
            id=step_id,
        )

    def finish_run_step(
        self,
        run_step_id: int,
        status: RunStatus,
        items_success: int,
        items_failed: int,
        items_skipped: int,
        metadata: dict | None = None,
        error_message: str | None = None,
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE run_steps
                SET
                    finished_at = ?,
                    status = ?,
                    items_success = ?,
                    items_failed = ?,
                    items_skipped = ?,
                    metadata_json = ?,
                    error_message = ?
                WHERE id = ?
                """,
                (
                    datetime_to_db(
                        utc_now()
                    ),
                    status.value,
                    items_success,
                    items_failed,
                    items_skipped,
                    json_to_db(metadata),
                    error_message,
                    run_step_id,
                ),
            )

    def add_company_scan(
        self,
        scan: CompanyScan,
    ) -> CompanyScan:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO company_scans (
                    run_step_id,
                    company_id,
                    started_at,
                    finished_at,
                    status,
                    homepage_url,
                    homepage_http_status,
                    careers_url_found,
                    careers_discovery_method,
                    contacts_found_count,
                    ats_status,
                    review_status,
                    expected_ats_provider,
                    review_notes,
                    error_type,
                    error_message
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?
                )
                """,
                (
                    scan.run_step_id,
                    scan.company_id,
                    datetime_to_db(
                        scan.started_at
                    ),
                    (
                        datetime_to_db(
                            scan.finished_at
                        )
                        if scan.finished_at
                        is not None
                        else None
                    ),
                    scan.status.value,
                    scan.homepage_url,
                    scan.homepage_http_status,
                    scan.careers_url_found,
                    scan.careers_discovery_method,
                    scan.contacts_found_count,
                    (
                        scan.ats_status.value
                        if scan.ats_status
                        is not None
                        else None
                    ),
                    scan.review_status.value,
                    (
                        scan.expected_ats_provider.value
                        if scan.expected_ats_provider
                        is not None
                        else None
                    ),
                    scan.review_notes,
                    scan.error_type,
                    scan.error_message,
                ),
            )

            scan_id = cursor.lastrowid

        if scan_id is None:
            raise RuntimeError(
                "SQLite did not return "
                "a company scan id."
            )

        return replace(
            scan,
            id=scan_id,
        )

    def finish_company_scan(
        self,
        company_scan_id: int,
        status: RunStatus,
        homepage_http_status: int | None,
        careers_url_found: str | None,
        careers_discovery_method: str | None,
        ats_status: AtsScanStatus,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE company_scans
                SET
                    finished_at = ?,
                    status = ?,
                    homepage_http_status = ?,
                    careers_url_found = ?,
                    careers_discovery_method = ?,
                    ats_status = ?,
                    error_type = ?,
                    error_message = ?
                WHERE id = ?
                """,
                (
                    datetime_to_db(
                        utc_now()
                    ),
                    status.value,
                    homepage_http_status,
                    careers_url_found,
                    careers_discovery_method,
                    ats_status.value,
                    error_type,
                    error_message,
                    company_scan_id,
                ),
            )

    def add_ats_detection(
        self,
        detection: AtsDetection,
    ) -> AtsDetection:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO ats_detections (
                    company_scan_id,
                    provider,
                    external_identifier,
                    method,
                    source_url,
                    evidence,
                    confidence,
                    selected,
                    created_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    detection.company_scan_id,
                    detection.provider.value,
                    detection.external_identifier,
                    detection.method.value,
                    detection.source_url,
                    detection.evidence,
                    detection.confidence,
                    bool_to_db(
                        detection.selected
                    ),
                    datetime_to_db(
                        detection.created_at
                    ),
                ),
            )

            detection_id = (
                cursor.lastrowid
            )

        if detection_id is None:
            raise RuntimeError(
                "SQLite did not return "
                "an ATS detection id."
            )

        return replace(
            detection,
            id=detection_id,
        )

    def add_ats_sync(
        self,
        ats_sync: AtsSync,
    ) -> AtsSync:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO ats_syncs (
                    run_step_id,
                    company_ats_id,
                    started_at,
                    finished_at,
                    status,
                    http_status,
                    jobs_received,
                    jobs_created,
                    jobs_updated,
                    jobs_deactivated,
                    error_type,
                    error_message
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    ats_sync.run_step_id,
                    ats_sync.company_ats_id,
                    datetime_to_db(
                        ats_sync.started_at
                    ),
                    (
                        datetime_to_db(
                            ats_sync.finished_at
                        )
                        if ats_sync.finished_at
                        is not None
                        else None
                    ),
                    ats_sync.status.value,
                    ats_sync.http_status,
                    ats_sync.jobs_received,
                    ats_sync.jobs_created,
                    ats_sync.jobs_updated,
                    ats_sync.jobs_deactivated,
                    ats_sync.error_type,
                    ats_sync.error_message,
                ),
            )

            ats_sync_id = cursor.lastrowid

        if ats_sync_id is None:
            raise RuntimeError(
                "SQLite did not return "
                "an ATS sync id."
            )

        return replace(
            ats_sync,
            id=ats_sync_id,
        )

    def finish_ats_sync(
        self,
        ats_sync_id: int,
        status: RunStatus,
        http_status: int | None,
        jobs_received: int,
        jobs_created: int,
        jobs_updated: int,
        jobs_deactivated: int,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE ats_syncs
                SET
                    finished_at = ?,
                    status = ?,
                    http_status = ?,
                    jobs_received = ?,
                    jobs_created = ?,
                    jobs_updated = ?,
                    jobs_deactivated = ?,
                    error_type = ?,
                    error_message = ?
                WHERE id = ?
                """,
                (
                    datetime_to_db(
                        utc_now()
                    ),
                    status.value,
                    http_status,
                    jobs_received,
                    jobs_created,
                    jobs_updated,
                    jobs_deactivated,
                    error_type,
                    error_message,
                    ats_sync_id,
                ),
            )