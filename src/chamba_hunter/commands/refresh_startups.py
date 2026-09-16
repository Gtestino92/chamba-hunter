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


@dataclass(frozen=True, slots=True)
class StartupRefreshSettings:
    search_depth: str
    yc_limit: int | None
    hn_limit: int | None


ROUTINE_YC_LIMIT = 50
ROUTINE_HN_LIMIT = 100

DEEP_YC_LIMIT = None
DEEP_HN_LIMIT = None


DOWNSTREAM_STEPS = (
    RefreshStep(
        name="Canonicalize job leads",
        module="canonicalize_job_leads",
        arguments=(
            "--apply",
        ),
    ),
    RefreshStep(
        name="Classify Argentina eligibility",
        module="classify_argentina_eligibility",
        arguments=(
            "--apply",
        ),
    ),
    RefreshStep(
        name="Classify occupation/backend",
        module="classify_job_occupations",
        arguments=(
            "--apply",
        ),
    ),
    RefreshStep(
        name="Classify skills",
        module="classify_job_skills",
        arguments=(
            "--apply",
        ),
    ),
    RefreshStep(
        name="Classify seniority",
        module="classify_job_seniority",
        arguments=(
            "--apply",
        ),
    ),
    RefreshStep(
        name="Professional matching",
        module="match_jobs",
        arguments=(
            "--apply",
            "--top",
            "0",
        ),
    ),
    RefreshStep(
        name="Operational priority",
        module="prioritize_jobs",
        arguments=(
            "--apply",
            "--top",
            "0",
        ),
    ),
)


def _resolve_limit(
    *,
    deep: bool,
    explicit_limit: int | None,
    routine_default: int | None,
    deep_default: int | None,
) -> int | None:
    if explicit_limit is not None:
        if explicit_limit == 0:
            return None

        return explicit_limit

    return (
        deep_default
        if deep
        else routine_default
    )


def resolve_settings(
    *,
    deep: bool,
    yc_limit: int | None,
    hn_limit: int | None,
) -> StartupRefreshSettings:
    return StartupRefreshSettings(
        search_depth=(
            "DEEP"
            if deep
            else "ROUTINE"
        ),
        yc_limit=_resolve_limit(
            deep=deep,
            explicit_limit=yc_limit,
            routine_default=ROUTINE_YC_LIMIT,
            deep_default=DEEP_YC_LIMIT,
        ),
        hn_limit=_resolve_limit(
            deep=deep,
            explicit_limit=hn_limit,
            routine_default=ROUTINE_HN_LIMIT,
            deep_default=DEEP_HN_LIMIT,
        ),
    )


def _limit_arguments(
    limit: int | None,
) -> tuple[str, ...]:
    if limit is None:
        return ()

    return (
        "--limit",
        str(
            limit
        ),
    )


def build_plan(
    *,
    skip_yc: bool,
    skip_hn: bool,
    skip_export: bool,
    yc_limit: int | None,
    hn_limit: int | None,
    output: Path,
) -> list[RefreshStep]:
    steps: list[
        RefreshStep
    ] = []

    if not skip_yc:
        steps.append(
            RefreshStep(
                name="Acquire YC jobs",
                module="acquire_yc_jobs",
                arguments=_limit_arguments(
                    yc_limit
                ),
            )
        )

    if not skip_hn:
        steps.append(
            RefreshStep(
                name=(
                    "Acquire HN Who is Hiring "
                    "jobs"
                ),
                module="acquire_hn_jobs",
                arguments=_limit_arguments(
                    hn_limit
                ),
            )
        )

    steps.extend(
        DOWNSTREAM_STEPS
    )

    if not skip_export:
        steps.append(
            RefreshStep(
                name="Export XLSX shortlist",
                module="export_shortlist",
                arguments=(
                    "--output",
                    str(
                        output
                    ),
                ),
            )
        )

    return steps


def _command(
    step: RefreshStep,
) -> list[str]:
    return [
        sys.executable,
        "-m",
        (
            "chamba_hunter.commands."
            f"{step.module}"
        ),
        *step.arguments,
    ]


def _display_limit(
    limit: int | None,
) -> str:
    if limit is None:
        return "unlimited"

    return str(
        limit
    )


def main() -> None:
    if hasattr(
        sys.stdout,
        "reconfigure",
    ):
        sys.stdout.reconfigure(
            encoding="utf-8",
            errors="replace",
        )

    parser = argparse.ArgumentParser(
        description=(
            "Plan or execute the Chamba Hunter "
            "startup/direct-hiring refresh."
        )
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Execute the refresh. Without this "
            "flag, only print the ordered plan."
        ),
    )

    parser.add_argument(
        "--deep",
        action="store_true",
        help=(
            "Use complete source acquisition "
            "defaults for catch-up/recovery scans."
        ),
    )

    parser.add_argument(
        "--yc-limit",
        type=int,
        default=None,
        help=(
            "Maximum persisted YC companies to "
            "consider. Defaults to 50 in routine "
            "mode and all in deep mode; use 0 "
            "for all."
        ),
    )

    parser.add_argument(
        "--hn-limit",
        type=int,
        default=None,
        help=(
            "Maximum HN top-level comments to "
            "fetch from the latest monthly thread. "
            "Defaults to 100 in routine mode and "
            "all in deep mode; use 0 for all."
        ),
    )

    parser.add_argument(
        "--skip-yc",
        action="store_true",
        help="Skip YC public jobs acquisition.",
    )

    parser.add_argument(
        "--skip-hn",
        action="store_true",
        help=(
            "Skip Hacker News Who is Hiring "
            "acquisition."
        ),
    )

    parser.add_argument(
        "--skip-export",
        action="store_true",
        help="Skip final XLSX shortlist export.",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "output/chamba-shortlist.xlsx"
        ),
    )

    args = parser.parse_args()

    if (
        args.yc_limit is not None
        and args.yc_limit < 0
    ):
        parser.error(
            "--yc-limit cannot be negative"
        )

    if (
        args.hn_limit is not None
        and args.hn_limit < 0
    ):
        parser.error(
            "--hn-limit cannot be negative"
        )

    settings = resolve_settings(
        deep=args.deep,
        yc_limit=args.yc_limit,
        hn_limit=args.hn_limit,
    )

    plan = build_plan(
        skip_yc=args.skip_yc,
        skip_hn=args.skip_hn,
        skip_export=args.skip_export,
        yc_limit=settings.yc_limit,
        hn_limit=settings.hn_limit,
        output=args.output,
    )

    print(
        "Chamba Hunter startup refresh"
    )
    print(
        "============================="
    )
    print(
        "Mode:",
        (
            "APPLY"
            if args.apply
            else "PLAN ONLY"
        ),
    )
    print(
        "Search depth:",
        settings.search_depth,
    )
    print()
    print(
        "YC limit:",
        _display_limit(
            settings.yc_limit
        ),
    )
    print(
        "HN limit:",
        _display_limit(
            settings.hn_limit
        ),
    )
    print()
    print(
        "Steps:",
        len(
            plan
        ),
    )
    print()

    for index, step in enumerate(
        plan,
        start=1,
    ):
        command = _command(
            step
        )

        print(
            f"{index:>2}. "
            f"{step.name}"
        )
        print(
            "    "
            + " ".join(
                command
            )
        )

    if not args.apply:
        print()
        print(
            "No commands were executed."
        )
        print(
            "Use --apply to run this plan."
        )
        return

    print()
    print(
        "Executing startup refresh..."
    )

    for index, step in enumerate(
        plan,
        start=1,
    ):
        command = _command(
            step
        )

        print()
        print(
            "=" * 72
        )
        print(
            f"[{index}/{len(plan)}] "
            f"{step.name}"
        )
        print(
            "=" * 72
        )

        result = subprocess.run(
            command,
            check=False,
        )

        if result.returncode != 0:
            raise SystemExit(
                "Startup refresh stopped because "
                f"step {index} failed with exit "
                f"code {result.returncode}: "
                f"{step.module}"
            )

    print()
    print(
        "Startup refresh completed successfully."
    )
    print(
        "Shortlist:",
        (
            "<skipped>"
            if args.skip_export
            else str(
                args.output
            )
        ),
    )


if __name__ == "__main__":
    main()
