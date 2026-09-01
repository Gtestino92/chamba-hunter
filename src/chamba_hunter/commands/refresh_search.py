import argparse
from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys


@dataclass(frozen=True, slots=True)
class RefreshStep:
    name: str
    module: str
    arguments: tuple[str, ...] = ()


ATS_SYNC_MODULES = (
    "sync_greenhouse_jobs",
    "sync_lever_jobs",
    "sync_ashby_jobs",
    "sync_workable_jobs",
    "sync_smartrecruiters_jobs",
    "sync_bamboohr_jobs",
    "sync_hiringroom_jobs",
    "sync_teamtailor_jobs",
    "sync_hibob_jobs",
)


def build_plan(
    *,
    skip_broad: bool,
    skip_himalayas: bool,
    skip_ats: bool,
    skip_export: bool,
    discover_known_ats_limit: int,
    discover_broad_ats_limit: int,
    himalayas_backfill_days: int,
    himalayas_overlap_hours: int,
    getonboard_max_pages: int,
    jobicy_max_jobs: int,
    wwr_max_jobs: int,
    jooble_max_pages_per_query: int,
    output: Path,
) -> list[RefreshStep]:
    steps: list[RefreshStep] = []

    if not skip_broad:
        broad_arguments = [
            "--himalayas-backfill-days",
            str(himalayas_backfill_days),
            "--himalayas-overlap-hours",
            str(himalayas_overlap_hours),
            "--getonboard-max-pages",
            str(getonboard_max_pages),
            "--jobicy-max-jobs",
            str(jobicy_max_jobs),
            "--wwr-max-jobs",
            str(wwr_max_jobs),
            "--jooble-max-pages-per-query",
            str(jooble_max_pages_per_query),
        ]
        if skip_himalayas:
            broad_arguments.append("--skip-himalayas")
        steps.append(
            RefreshStep(
                name="Acquire broad sources V2",
                module="acquire_sources_v2",
                arguments=tuple(broad_arguments),
            )
        )

    if discover_known_ats_limit > 0:
        steps.append(
            RefreshStep(
                name="Discover ATS for known companies",
                module="discover_known_ats",
                arguments=("--limit", str(discover_known_ats_limit)),
            )
        )

    if discover_broad_ats_limit > 0:
        steps.append(
            RefreshStep(
                name="Discover ATS from broad-source evidence",
                module="discover_broad_ats",
                arguments=("--limit", str(discover_broad_ats_limit)),
            )
        )

    if not skip_ats:
        for module in ATS_SYNC_MODULES:
            provider = (
                module
                .removeprefix("sync_")
                .removesuffix("_jobs")
                .replace("_", " ")
                .title()
            )
            steps.append(
                RefreshStep(
                    name=f"Sync {provider} jobs",
                    module=module,
                )
            )

    steps.extend(
        [
            RefreshStep(
                name="Canonicalize broad leads",
                module="canonicalize_job_leads",
                arguments=("--apply",),
            ),
            RefreshStep(
                name="Classify Argentina eligibility",
                module="classify_argentina_eligibility",
                arguments=("--apply",),
            ),
            RefreshStep(
                name="Classify occupation/backend",
                module="classify_job_occupations",
                arguments=("--apply",),
            ),
            RefreshStep(
                name="Classify skills",
                module="classify_job_skills",
                arguments=("--apply",),
            ),
            RefreshStep(
                name="Classify seniority",
                module="classify_job_seniority",
                arguments=("--apply",),
            ),
            RefreshStep(
                name="Professional matching",
                module="match_jobs",
                arguments=("--apply", "--top", "0"),
            ),
            RefreshStep(
                name="Operational priority",
                module="prioritize_jobs",
                arguments=("--apply", "--top", "0"),
            ),
        ]
    )

    if not skip_export:
        steps.append(
            RefreshStep(
                name="Export XLSX shortlist",
                module="export_shortlist",
                arguments=("--output", str(output)),
            )
        )
    return steps


def _command(step: RefreshStep) -> list[str]:
    return [
        sys.executable,
        "-m",
        f"chamba_hunter.commands.{step.module}",
        *step.arguments,
    ]


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description=(
            "Plan or execute the routine Chamba Hunter "
            "end-to-end search refresh."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Execute the refresh. Without this flag, "
            "only print the ordered plan."
        ),
    )
    parser.add_argument("--skip-broad", action="store_true", help="Skip all broad acquisition.")
    parser.add_argument(
        "--skip-himalayas",
        action="store_true",
        help="Skip only Himalayas inside broad acquisition.",
    )
    parser.add_argument(
        "--skip-ats",
        action="store_true",
        help="Skip synchronization of all known active ATS boards.",
    )
    parser.add_argument("--skip-export", action="store_true", help="Skip final XLSX shortlist export.")
    parser.add_argument(
        "--discover-known-ats-limit",
        type=int,
        default=25,
        help=(
            "Scan up to N known companies without an active ATS, prioritizing "
            "never-scanned and least-recently-scanned companies. Defaults to 25; "
            "use 0 to disable."
        ),
    )
    parser.add_argument(
        "--discover-broad-ats-limit",
        type=int,
        default=10,
        help=(
            "Additionally inspect up to N broad-source companies for ATS/provider "
            "hints. Defaults to 10; use 0 to disable."
        ),
    )
    parser.add_argument(
        "--himalayas-backfill-days",
        type=int,
        default=30,
        help="Maximum Himalayas historical window. Defaults to 30 days.",
    )
    parser.add_argument(
        "--himalayas-overlap-hours",
        type=int,
        default=48,
        help=(
            "Himalayas overlap before the previous successful source start. "
            "Defaults to 48 hours."
        ),
    )
    parser.add_argument("--getonboard-max-pages", type=int, default=5)
    parser.add_argument("--jobicy-max-jobs", type=int, default=100)
    parser.add_argument("--wwr-max-jobs", type=int, default=300)
    parser.add_argument("--jooble-max-pages-per-query", type=int, default=2)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/chamba-shortlist.xlsx"),
    )
    args = parser.parse_args()

    if args.discover_known_ats_limit < 0:
        parser.error("--discover-known-ats-limit cannot be negative")
    if args.discover_broad_ats_limit < 0:
        parser.error("--discover-broad-ats-limit cannot be negative")
    if args.himalayas_backfill_days < 1:
        parser.error("--himalayas-backfill-days must be at least 1")
    if args.himalayas_overlap_hours < 0:
        parser.error("--himalayas-overlap-hours cannot be negative")
    if args.getonboard_max_pages < 0:
        parser.error("--getonboard-max-pages cannot be negative")
    if not 0 <= args.jobicy_max_jobs <= 100:
        parser.error("--jobicy-max-jobs must be between 0 and 100")
    if args.wwr_max_jobs < 0:
        parser.error("--wwr-max-jobs cannot be negative")
    if args.jooble_max_pages_per_query < 0:
        parser.error("--jooble-max-pages-per-query cannot be negative")

    if (
        not args.skip_broad
        and args.skip_himalayas
        and args.getonboard_max_pages == 0
        and args.jobicy_max_jobs == 0
        and args.wwr_max_jobs == 0
        and args.jooble_max_pages_per_query == 0
    ):
        parser.error(
            "At least one broad source must be enabled unless --skip-broad is used."
        )

    plan = build_plan(
        skip_broad=args.skip_broad,
        skip_himalayas=args.skip_himalayas,
        skip_ats=args.skip_ats,
        skip_export=args.skip_export,
        discover_known_ats_limit=args.discover_known_ats_limit,
        discover_broad_ats_limit=args.discover_broad_ats_limit,
        himalayas_backfill_days=args.himalayas_backfill_days,
        himalayas_overlap_hours=args.himalayas_overlap_hours,
        getonboard_max_pages=args.getonboard_max_pages,
        jobicy_max_jobs=args.jobicy_max_jobs,
        wwr_max_jobs=args.wwr_max_jobs,
        jooble_max_pages_per_query=args.jooble_max_pages_per_query,
        output=args.output,
    )

    print("Chamba Hunter refresh")
    print("====================")
    print("Mode:", "APPLY" if args.apply else "PLAN ONLY")
    print("Steps:", len(plan))
    print()
    for index, step in enumerate(plan, start=1):
        command = _command(step)
        print(f"{index:>2}. {step.name}")
        print("    " + " ".join(command))

    if not args.apply:
        print()
        print("No commands were executed.")
        print("Use --apply to run this plan.")
        return

    print()
    print("Executing refresh...")
    for index, step in enumerate(plan, start=1):
        command = _command(step)
        print()
        print("=" * 72)
        print(f"[{index}/{len(plan)}] {step.name}")
        print("=" * 72)
        result = subprocess.run(command, check=False)
        if result.returncode != 0:
            raise SystemExit(
                "Refresh stopped because step "
                f"{index} failed with exit code {result.returncode}: {step.module}"
            )

    print()
    print("Refresh completed successfully.")
    print("Shortlist:", "<skipped>" if args.skip_export else str(args.output))


if __name__ == "__main__":
    main()
