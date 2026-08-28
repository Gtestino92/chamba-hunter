from dataclasses import dataclass

from chamba_hunter.db.connection import Database
from chamba_hunter.repositories.company_outreach_repository import (
    OutreachReportRow,
)


ELIGIBILITY_VERSION = "OUTREACH_ELIGIBILITY_V1"


@dataclass(frozen=True, slots=True)
class CompanyJobEligibilityEvidence:
    active_jobs: int
    eligible_jobs: int
    ineligible_jobs: int
    unknown_jobs: int


@dataclass(frozen=True, slots=True)
class OutreachEligibilityDecision:
    status: str
    reason: str

    active_jobs: int = 0
    eligible_jobs: int = 0
    ineligible_jobs: int = 0
    unknown_jobs: int = 0


class OutreachEligibilityService:
    def __init__(
        self,
        database: Database,
    ) -> None:
        self.database = database
        self._job_evidence = (
            self._load_job_evidence()
        )

    def decide(
        self,
        row: OutreachReportRow,
    ) -> OutreachEligibilityDecision:
        if row.remote_argentina is True:
            return OutreachEligibilityDecision(
                status="ELIGIBLE",
                reason="REMOTE_ARGENTINA",
            )

        if row.remote_latam is True:
            return OutreachEligibilityDecision(
                status="ELIGIBLE",
                reason="REMOTE_LATAM",
            )

        if row.cessi_source:
            return OutreachEligibilityDecision(
                status="ELIGIBLE",
                reason="ARGENTINA_COMPANY_CESSI",
            )

        if row.argentina_directory_sources:
            return OutreachEligibilityDecision(
                status="ELIGIBLE",
                reason="ARGENTINA_DIRECTORY",
            )

        country = (
            row.country
            or ""
        ).casefold()

        if "argentin" in country:
            return OutreachEligibilityDecision(
                status="ELIGIBLE",
                reason="ARGENTINA_COUNTRY",
            )

        evidence = self._job_evidence.get(
            row.company_id
        )

        if evidence is None:
            return OutreachEligibilityDecision(
                status="UNKNOWN",
                reason=(
                    "NO_ARGENTINA_ELIGIBILITY_EVIDENCE"
                ),
            )

        if evidence.eligible_jobs > 0:
            return OutreachEligibilityDecision(
                status="ELIGIBLE",
                reason="ACTIVE_ELIGIBLE_JOB",
                active_jobs=evidence.active_jobs,
                eligible_jobs=evidence.eligible_jobs,
                ineligible_jobs=(
                    evidence.ineligible_jobs
                ),
                unknown_jobs=evidence.unknown_jobs,
            )

        if (
            evidence.active_jobs > 0
            and evidence.ineligible_jobs
            == evidence.active_jobs
        ):
            return OutreachEligibilityDecision(
                status="INELIGIBLE",
                reason="ACTIVE_JOBS_INELIGIBLE",
                active_jobs=evidence.active_jobs,
                eligible_jobs=0,
                ineligible_jobs=(
                    evidence.ineligible_jobs
                ),
                unknown_jobs=0,
            )

        return OutreachEligibilityDecision(
            status="UNKNOWN",
            reason="ACTIVE_JOB_SCOPE_UNKNOWN",
            active_jobs=evidence.active_jobs,
            eligible_jobs=evidence.eligible_jobs,
            ineligible_jobs=(
                evidence.ineligible_jobs
            ),
            unknown_jobs=evidence.unknown_jobs,
        )

    def _load_job_evidence(
        self,
    ) -> dict[
        int,
        CompanyJobEligibilityEvidence,
    ]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    COALESCE(
                        ca.canonical_company_id,
                        jc.company_id
                    ) AS company_id,
                    COUNT(*) AS active_jobs,
                    SUM(
                        CASE
                            WHEN jec.status = 'ELIGIBLE'
                            THEN 1
                            ELSE 0
                        END
                    ) AS eligible_jobs,
                    SUM(
                        CASE
                            WHEN jec.status = 'INELIGIBLE'
                            THEN 1
                            ELSE 0
                        END
                    ) AS ineligible_jobs,
                    SUM(
                        CASE
                            WHEN jec.status = 'UNKNOWN'
                              OR jec.status IS NULL
                            THEN 1
                            ELSE 0
                        END
                    ) AS unknown_jobs
                FROM job_candidates jc
                LEFT JOIN company_aliases ca
                  ON ca.alias_company_id = jc.company_id
                LEFT JOIN job_eligibility_classifications jec
                  ON jec.record_kind = jc.record_kind
                 AND jec.record_id = jc.record_id
                WHERE jc.is_active = 1
                GROUP BY
                    COALESCE(
                        ca.canonical_company_id,
                        jc.company_id
                    )
                """
            ).fetchall()

        return {
            int(row["company_id"]): (
                CompanyJobEligibilityEvidence(
                    active_jobs=int(
                        row["active_jobs"]
                    ),
                    eligible_jobs=int(
                        row["eligible_jobs"]
                        or 0
                    ),
                    ineligible_jobs=int(
                        row["ineligible_jobs"]
                        or 0
                    ),
                    unknown_jobs=int(
                        row["unknown_jobs"]
                        or 0
                    ),
                )
            )
            for row in rows
        }
