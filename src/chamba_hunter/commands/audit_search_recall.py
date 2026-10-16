import argparse
from collections import Counter
from pathlib import Path

from chamba_hunter.db.connection import DEFAULT_DB_PATH, Database
from chamba_hunter.domain.common import utc_now
from chamba_hunter.repositories.job_matching_repository import JobMatchingRepository
from chamba_hunter.services.job_matching_service import (
    MAX_PROFESSIONAL_MATCH_AGE_DAYS,
    SSR_SENIOR_BACKEND_SOFTWARE_V1,
)
from chamba_hunter.services.pipeline_snapshot_service import inspect_pipeline_snapshots
from chamba_hunter.services.search_recall_audit_service import (
    evaluate_search_recall,
    qualifies,
)


VARIANTS = (
    ("legacy", "A legacy MATCHING_V2 + persisted skills"),
    ("target_legacy_skills", "B MATCHING_V4 + legacy-equivalent skills"),
    ("target_v3_skills", "C MATCHING_V4 + full in-memory SKILLS_V3"),
)


def _print_transition(label: str, comparisons, left: str, right: str) -> None:
    transitions = Counter(
        (
            getattr(item, left).match_level,
            getattr(item, right).match_level,
        )
        for item in comparisons
    )
    print(label)
    for (before, after), count in sorted(transitions.items()):
        if before != after:
            print(f"  {before:>9} -> {after:<9} {count}")
    if not any(before != after for before, after in transitions):
        print("  No match-level transitions.")


def _print_samples(comparisons, left: str, right: str, limit: int) -> None:
    changed = sorted(
        (
            item
            for item in comparisons
            if getattr(item, left).score != getattr(item, right).score
        ),
        key=lambda item: abs(
            getattr(item, right).score - getattr(item, left).score
        ),
        reverse=True,
    )
    for item in changed[:limit]:
        before = getattr(item, left)
        after = getattr(item, right)
        reasons = ",".join(after.reasons["ceiling_reasons"]) or "none"
        print(
            f"  {before.score:5.1f}/{before.match_level:<9} -> "
            f"{after.score:5.1f}/{after.match_level:<9} | "
            f"{item.candidate.record_kind} {item.candidate.record_id} | "
            f"{item.candidate.company_name} | {item.candidate.title} | "
            f"ceiling={after.score_ceiling:.1f} ({reasons})"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only comparison of legacy and SSR/Senior backend matching."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument(
        "--profile",
        choices=(SSR_SENIOR_BACKEND_SOFTWARE_V1.name,),
        default=SSR_SENIOR_BACKEND_SOFTWARE_V1.name,
    )
    parser.add_argument("--samples", type=int, default=15)
    args = parser.parse_args()
    if args.samples < 0:
        parser.error("--samples cannot be negative.")
    if not args.db.exists():
        parser.error(f"Database does not exist: {args.db}")

    database = Database(args.db, read_only=True)
    as_of = utc_now()
    candidates = JobMatchingRepository(database).list_scoped_candidates(
        as_of=as_of,
        max_age_days=MAX_PROFESSIONAL_MATCH_AGE_DAYS,
    )
    audit = evaluate_search_recall(candidates)
    snapshot_report = inspect_pipeline_snapshots(
        database,
        args.profile,
        as_of=as_of,
    )

    print("Search recall audit (strictly read-only)")
    print("----------------------------------------")
    print(f"Database:   {args.db.resolve()}")
    print(f"Candidates: {audit.candidate_count}")
    print("match_jobs/audit candidate evaluator: shared (mismatches=0)")
    print()

    with database.connection() as connection:
        eligible_active_count = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM job_candidates jc
                JOIN job_eligibility_classifications eligibility
                  ON eligibility.record_kind = jc.record_kind
                 AND eligibility.record_id = jc.record_id
                WHERE jc.is_active = 1
                  AND eligibility.status IN ('ELIGIBLE', 'UNKNOWN')
                """
            ).fetchone()[0]
        )
        snapshot_versions = {
            table: dict(
                connection.execute(
                    f"SELECT rule_version, COUNT(*) FROM {table} GROUP BY rule_version"
                ).fetchall()
            )
            for table in (
                "job_occupation_classifications",
                "job_skill_classifications",
                "job_seniority_classifications",
            )
        }
    print("Persisted upstream snapshots")
    for issue in snapshot_report.issues:
        print(f"  {issue.severity}: {issue.code}={issue.count} - {issue.detail}")
    if eligible_active_count != audit.candidate_count:
        print(
            "  WARNING: "
            f"{eligible_active_count - audit.candidate_count} eligible/unknown active "
            "candidates lack required occupation or seniority snapshots."
        )
    for table, versions in snapshot_versions.items():
        rendered = ", ".join(f"{key}={value}" for key, value in sorted(versions.items()))
        print(f"  {table}: {rendered or '<empty>'}")
    if set(snapshot_versions["job_occupation_classifications"]) != {"OCCUPATION_V3"}:
        print("  WARNING: occupation snapshots are missing/stale relative to OCCUPATION_V3.")
    if set(snapshot_versions["job_skill_classifications"]) != {"SKILLS_V2"}:
        print("  WARNING: the persisted legacy skill baseline is mixed or incomplete.")
    if not snapshot_versions["job_seniority_classifications"]:
        print("  WARNING: seniority snapshots are missing.")
    print("  SKILLS_V3 evidence is recomputed in memory from stored title/description.")
    print()

    for key, label in VARIANTS:
        distribution = audit.level_distribution(key)
        qualifying = sum(
            qualifies(getattr(item, key))
            for item in audit.comparisons
        )
        rendered = ", ".join(
            f"{level}={distribution[level]}"
            for level in ("LOW", "MEDIUM", "HIGH", "VERY_HIGH")
        )
        print(f"{label}: {rendered}; qualifying>=50={qualifying}")
    print()

    _print_transition(
        "A -> B (SSR/Senior profile calibration)",
        audit.comparisons,
        "legacy",
        "target_legacy_skills",
    )
    _print_transition(
        "B -> C (additional SKILLS_V3 evidence)",
        audit.comparisons,
        "target_legacy_skills",
        "target_v3_skills",
    )

    print()
    newly = sum(
        not qualifies(item.legacy) and qualifies(item.target_v3_skills)
        for item in audit.comparisons
    )
    excluded = sum(
        qualifies(item.legacy) and not qualifies(item.target_v3_skills)
        for item in audit.comparisons
    )
    print(f"Newly qualifying A -> C: {newly}")
    print(f"Previously qualifying now excluded A -> C: {excluded}")

    print("Seniority cohort score/level changes A -> C")
    for level in ("SENIOR", "MID", "UNKNOWN", "STAFF", "LEAD", "PRINCIPAL"):
        cohort = [item for item in audit.comparisons if item.candidate.seniority_class == level]
        changed = sum(item.legacy.match_level != item.target_v3_skills.match_level for item in cohort)
        print(f"  {level:<9} candidates={len(cohort):4} level_changes={changed:4}")

    architect = [
        item for item in audit.comparisons
        if "architect" in item.candidate.title.casefold()
        or "arquitect" in item.candidate.title.casefold()
    ]
    software_other = [
        item for item in audit.comparisons
        if item.candidate.occupation_class == "SOFTWARE_ENGINEERING"
        and item.candidate.backend_relevance != "BACKEND"
    ]
    non_software = [
        item for item in audit.comparisons
        if item.candidate.occupation_class != "SOFTWARE_ENGINEERING"
    ]
    print(f"Architect candidates: {len(architect)}; level changes A -> C: {sum(item.legacy.match_level != item.target_v3_skills.match_level for item in architect)}")
    print(f"Software non-BACKEND candidates: {len(software_other)}; newly qualifying A -> C: {sum(not qualifies(item.legacy) and qualifies(item.target_v3_skills) for item in software_other)}")
    print(f"Non-software candidates: {len(non_software)}; newly qualifying A -> C: {sum(not qualifies(item.legacy) and qualifies(item.target_v3_skills) for item in non_software)}")

    print()
    print("Representative A -> C score changes")
    _print_samples(audit.comparisons, "legacy", "target_v3_skills", args.samples)


if __name__ == "__main__":
    main()
