from dataclasses import dataclass
from pathlib import Path
import sqlite3

from chamba_hunter.db.connection import DEFAULT_DB_PATH


RETIRED_SOURCE_TYPES = (
    "REMOTECO",
    "REMOTIVE",
    "REMOTEOK",
)

RETIRED_ACQUISITION_COMMANDS = (
    "acquire_remoteco_jobs",
    "acquire_remotive_jobs",
    "acquire_remoteok_jobs",
)

LEAD_DERIVED_TABLES = (
    "job_eligibility_classifications",
    "job_occupation_classifications",
    "job_skill_classifications",
    "job_seniority_classifications",
    "job_professional_matches",
    "job_operational_priorities",
)

COMPANY_DEPENDENCY_TABLES = (
    "company_sources",
    "job_leads",
    "jobs",
    "company_ats",
    "applications",
    "public_contacts",
    "company_scans",
    "company_contact_scans",
    "ats_fingerprints",
    "company_outreach_priorities",
    "company_classifications",
)


@dataclass(frozen=True)
class SourceLeadCounts:
    source_type: str
    job_leads: int
    canonicalized_leads: int
    current_unmatched_leads: int


@dataclass(frozen=True)
class CompanyCleanupCounts:
    touched: int
    safe_orphans: int
    preserved: int


@dataclass(frozen=True)
class RetiredSourceCleanupPlan:
    source_counts: tuple[SourceLeadCounts, ...]
    lead_derived_counts: dict[str, int]
    job_ats_hints: int
    source_acquisition_states: int
    applications: int
    company_sources: int
    companies: CompanyCleanupCounts
    source_specific_runs: int
    source_specific_run_steps: int
    target_lead_ids: tuple[int, ...]
    safe_orphan_company_ids: tuple[int, ...]
    preserved_company_ids: tuple[int, ...]


def placeholders(values: tuple[object, ...]) -> str:
    return ", ".join("?" for _ in values)


def open_cleanup_connection(
    database_path: Path | str = DEFAULT_DB_PATH,
    *,
    read_only: bool,
) -> sqlite3.Connection:
    path = Path(database_path)

    if read_only:
        uri = path.resolve().as_uri() + "?mode=ro"
        connection = sqlite3.connect(
            uri,
            uri=True,
        )
    else:
        connection = sqlite3.connect(path)

    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    return connection


class RetiredSourceCleanupService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def build_plan(self) -> RetiredSourceCleanupPlan:
        target_lead_ids = self._target_lead_ids()
        touched_company_ids = self._touched_company_ids()
        safe_orphan_company_ids = self._safe_orphan_company_ids(
            touched_company_ids
        )
        preserved_company_ids = tuple(
            company_id
            for company_id in touched_company_ids
            if company_id not in set(safe_orphan_company_ids)
        )

        return RetiredSourceCleanupPlan(
            source_counts=self._source_counts(),
            lead_derived_counts=self._lead_derived_counts(
                target_lead_ids
            ),
            job_ats_hints=self._count_job_ats_hints(
                target_lead_ids
            ),
            source_acquisition_states=self._count_by_sources(
                "source_acquisition_states"
            ),
            applications=self._count_applications(
                target_lead_ids
            ),
            company_sources=self._count_by_sources(
                "company_sources"
            ),
            companies=CompanyCleanupCounts(
                touched=len(touched_company_ids),
                safe_orphans=len(safe_orphan_company_ids),
                preserved=len(preserved_company_ids),
            ),
            source_specific_runs=self._source_specific_runs(),
            source_specific_run_steps=self._source_specific_run_steps(),
            target_lead_ids=target_lead_ids,
            safe_orphan_company_ids=safe_orphan_company_ids,
            preserved_company_ids=preserved_company_ids,
        )

    def apply(
        self,
        *,
        fail_after_derived_cleanup: bool = False,
    ) -> RetiredSourceCleanupPlan:
        try:
            self.connection.execute("BEGIN IMMEDIATE")

            plan = self.build_plan()
            if plan.applications:
                raise RuntimeError(
                    "Retired-source cleanup aborted: "
                    f"{plan.applications} tracked application(s) "
                    "reference target job leads. No application "
                    "history was deleted."
                )

            self._delete_lead_derived_rows(
                plan.target_lead_ids
            )

            if fail_after_derived_cleanup:
                raise RuntimeError(
                    "Simulated cleanup failure."
                )

            self._delete_source_acquisition_states()
            self._delete_company_sources()
            self._delete_source_specific_runs()
            self._delete_target_job_leads()
            self._delete_safe_orphan_companies(
                plan.safe_orphan_company_ids
            )

            self.connection.commit()
            return plan
        except Exception:
            self.connection.rollback()
            raise

    def _source_counts(self) -> tuple[SourceLeadCounts, ...]:
        return tuple(
            SourceLeadCounts(
                source_type=source_type,
                job_leads=self._count_job_leads(
                    source_type,
                    "",
                ),
                canonicalized_leads=self._count_job_leads(
                    source_type,
                    "AND canonical_job_id IS NOT NULL",
                ),
                current_unmatched_leads=self._count_job_leads(
                    source_type,
                    """
                    AND (
                        canonical_job_id IS NULL
                        OR NOT EXISTS (
                            SELECT 1
                            FROM jobs
                            WHERE jobs.id =
                                job_leads.canonical_job_id
                              AND jobs.is_active = 1
                        )
                    )
                    """,
                ),
            )
            for source_type in RETIRED_SOURCE_TYPES
        )

    def _count_job_leads(
        self,
        source_type: str,
        extra_where: str,
    ) -> int:
        row = self.connection.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM job_leads
            WHERE source_type = ?
            {extra_where}
            """,
            (source_type,),
        ).fetchone()
        return int(row["count"])

    def _target_lead_ids(self) -> tuple[int, ...]:
        rows = self.connection.execute(
            f"""
            SELECT id
            FROM job_leads
            WHERE source_type IN (
                {placeholders(RETIRED_SOURCE_TYPES)}
            )
            ORDER BY id
            """,
            RETIRED_SOURCE_TYPES,
        ).fetchall()
        return tuple(int(row["id"]) for row in rows)

    def _touched_company_ids(self) -> tuple[int, ...]:
        rows = self.connection.execute(
            f"""
            SELECT company_id
            FROM job_leads
            WHERE source_type IN (
                {placeholders(RETIRED_SOURCE_TYPES)}
            )
            UNION
            SELECT company_id
            FROM company_sources
            WHERE source_type IN (
                {placeholders(RETIRED_SOURCE_TYPES)}
            )
            ORDER BY company_id
            """,
            (*RETIRED_SOURCE_TYPES, *RETIRED_SOURCE_TYPES),
        ).fetchall()
        return tuple(int(row["company_id"]) for row in rows)

    def _lead_derived_counts(
        self,
        target_lead_ids: tuple[int, ...],
    ) -> dict[str, int]:
        return {
            table: self._count_lead_derived_table(
                table,
                target_lead_ids,
            )
            for table in LEAD_DERIVED_TABLES
        }

    def _count_lead_derived_table(
        self,
        table: str,
        target_lead_ids: tuple[int, ...],
    ) -> int:
        if not target_lead_ids:
            return 0

        row = self.connection.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM {table}
            WHERE record_kind = 'LEAD'
              AND record_id IN (
                  {placeholders(target_lead_ids)}
              )
            """,
            target_lead_ids,
        ).fetchone()
        return int(row["count"])

    def _count_job_ats_hints(
        self,
        target_lead_ids: tuple[int, ...],
    ) -> int:
        if not target_lead_ids:
            return 0

        row = self.connection.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM job_ats_hints
            WHERE job_lead_id IN (
                {placeholders(target_lead_ids)}
            )
            """,
            target_lead_ids,
        ).fetchone()
        return int(row["count"])

    def _count_applications(
        self,
        target_lead_ids: tuple[int, ...],
    ) -> int:
        if not target_lead_ids:
            return 0

        row = self.connection.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM applications
            WHERE application_type = 'JOB'
              AND record_kind = 'LEAD'
              AND record_id IN (
                  {placeholders(target_lead_ids)}
              )
            """,
            target_lead_ids,
        ).fetchone()
        return int(row["count"])

    def _count_by_sources(self, table: str) -> int:
        row = self.connection.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM {table}
            WHERE source_type IN (
                {placeholders(RETIRED_SOURCE_TYPES)}
            )
            """,
            RETIRED_SOURCE_TYPES,
        ).fetchone()
        return int(row["count"])

    def _source_specific_runs(self) -> int:
        row = self.connection.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM runs
            WHERE command IN (
                {placeholders(RETIRED_ACQUISITION_COMMANDS)}
            )
            """,
            RETIRED_ACQUISITION_COMMANDS,
        ).fetchone()
        return int(row["count"])

    def _source_specific_run_steps(self) -> int:
        row = self.connection.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM run_steps
            JOIN runs
              ON runs.id = run_steps.run_id
            WHERE runs.command IN (
                {placeholders(RETIRED_ACQUISITION_COMMANDS)}
            )
            """,
            RETIRED_ACQUISITION_COMMANDS,
        ).fetchone()
        return int(row["count"])

    def _safe_orphan_company_ids(
        self,
        touched_company_ids: tuple[int, ...],
    ) -> tuple[int, ...]:
        return tuple(
            company_id
            for company_id in touched_company_ids
            if self._is_safe_orphan_company(company_id)
        )

    def _is_safe_orphan_company(self, company_id: int) -> bool:
        for table in COMPANY_DEPENDENCY_TABLES:
            if table in {"company_sources", "job_leads"}:
                if self._company_has_non_retired_source_rows(
                    table,
                    company_id,
                ):
                    return False
            elif self._company_has_rows(table, company_id):
                return False

        if self._company_has_alias_rows(company_id):
            return False

        return True

    def _company_has_non_retired_source_rows(
        self,
        table: str,
        company_id: int,
    ) -> bool:
        row = self.connection.execute(
            f"""
            SELECT 1
            FROM {table}
            WHERE company_id = ?
              AND source_type NOT IN (
                  {placeholders(RETIRED_SOURCE_TYPES)}
              )
            LIMIT 1
            """,
            (company_id, *RETIRED_SOURCE_TYPES),
        ).fetchone()
        return row is not None

    def _company_has_rows(
        self,
        table: str,
        company_id: int,
    ) -> bool:
        row = self.connection.execute(
            f"""
            SELECT 1
            FROM {table}
            WHERE company_id = ?
            LIMIT 1
            """,
            (company_id,),
        ).fetchone()
        return row is not None

    def _company_has_alias_rows(self, company_id: int) -> bool:
        row = self.connection.execute(
            """
            SELECT 1
            FROM company_aliases
            WHERE alias_company_id = ?
               OR canonical_company_id = ?
            LIMIT 1
            """,
            (company_id, company_id),
        ).fetchone()
        return row is not None

    def _delete_lead_derived_rows(
        self,
        target_lead_ids: tuple[int, ...],
    ) -> None:
        if not target_lead_ids:
            return

        for table in LEAD_DERIVED_TABLES:
            self.connection.execute(
                f"""
                DELETE FROM {table}
                WHERE record_kind = 'LEAD'
                  AND record_id IN (
                      {placeholders(target_lead_ids)}
                  )
                """,
                target_lead_ids,
            )

    def _delete_source_acquisition_states(self) -> None:
        self.connection.execute(
            f"""
            DELETE FROM source_acquisition_states
            WHERE source_type IN (
                {placeholders(RETIRED_SOURCE_TYPES)}
            )
            """,
            RETIRED_SOURCE_TYPES,
        )

    def _delete_company_sources(self) -> None:
        self.connection.execute(
            f"""
            DELETE FROM company_sources
            WHERE source_type IN (
                {placeholders(RETIRED_SOURCE_TYPES)}
            )
            """,
            RETIRED_SOURCE_TYPES,
        )

    def _delete_source_specific_runs(self) -> None:
        self.connection.execute(
            f"""
            DELETE FROM runs
            WHERE command IN (
                {placeholders(RETIRED_ACQUISITION_COMMANDS)}
            )
            """,
            RETIRED_ACQUISITION_COMMANDS,
        )

    def _delete_target_job_leads(self) -> None:
        self.connection.execute(
            f"""
            DELETE FROM job_leads
            WHERE source_type IN (
                {placeholders(RETIRED_SOURCE_TYPES)}
            )
            """,
            RETIRED_SOURCE_TYPES,
        )

    def _delete_safe_orphan_companies(
        self,
        safe_orphan_company_ids: tuple[int, ...],
    ) -> None:
        if not safe_orphan_company_ids:
            return

        self.connection.execute(
            f"""
            DELETE FROM companies
            WHERE id IN (
                {placeholders(safe_orphan_company_ids)}
            )
            """,
            safe_orphan_company_ids,
        )
