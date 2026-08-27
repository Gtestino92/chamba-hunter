import argparse
from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys


@dataclass(frozen=True, slots=True)
class OutreachStep:
    name: str
    module: str
    arguments: tuple[str, ...] = ()


DEFAULT_PROFILE = "BACKEND_SOFTWARE_V1"


def _command(
    step: OutreachStep,
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
            "Plan or execute direct company "
            "outreach discovery and scoring."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
    )
    parser.add_argument(
        "--profile",
        default=DEFAULT_PROFILE,
    )
    parser.add_argument(
        "--skip-cessi",
        action="store_true",
    )
    parser.add_argument(
        "--skip-yc",
        action="store_true",
    )
    parser.add_argument(
        "--yc-max-companies",
        type=int,
        default=150,
    )
    parser.add_argument(
        "--skip-argentina-discovery",
        action="store_true",
    )
    parser.add_argument(
        "--argentina-max-companies",
        type=int,
        default=250,
    )
    parser.add_argument(
        "--skip-contact-scan",
        action="store_true",
    )
    parser.add_argument(
        "--contact-limit",
        type=int,
        default=75,
    )
    parser.add_argument(
        "--contact-max-pages",
        type=int,
        default=6,
    )
    parser.add_argument(
        "--force-contact-rescan",
        action="store_true",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=45.0,
    )
    parser.add_argument(
        "--min-explore-score",
        type=float,
        default=35.0,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "output/"
            "chamba-outreach.xlsx"
        ),
    )
    args = parser.parse_args()

    if args.argentina_max_companies < 1:
        parser.error(
            "--argentina-max-companies "
            "must be at least 1"
        )

    if args.yc_max_companies < 1:
        parser.error(
            "--yc-max-companies must be "
            "at least 1"
        )

    if args.contact_limit < 1:
        parser.error(
            "--contact-limit must be "
            "at least 1"
        )

    if args.contact_max_pages < 1:
        parser.error(
            "--contact-max-pages must "
            "be at least 1"
        )

    for argument_name, value in (
        ("--min-score", args.min_score),
        (
            "--min-explore-score",
            args.min_explore_score,
        ),
    ):
        if (
            value < 0
            or value > 100
        ):
            parser.error(
                f"{argument_name} must be "
                "between 0 and 100"
            )

    if (
        args.min_explore_score
        > args.min_score
    ):
        parser.error(
            "--min-explore-score cannot "
            "be greater than --min-score"
        )

    plan: list[
        OutreachStep
    ] = []

    if not args.skip_cessi:
        plan.append(
            OutreachStep(
                name=(
                    "Acquire CESSI companies "
                    "and public contacts"
                ),
                module=(
                    "acquire_cessi_companies"
                ),
            )
        )

    if not args.skip_yc:
        plan.append(
            OutreachStep(
                name=(
                    "Acquire YC technology "
                    "companies"
                ),
                module=(
                    "acquire_yc_companies"
                ),
                arguments=(
                    "--max-companies",
                    str(
                        args.yc_max_companies
                    ),
                ),
            )
        )

    if not args.skip_argentina_discovery:
        plan.append(
            OutreachStep(
                name=(
                    "Discover Argentina "
                    "software companies"
                ),
                module=(
                    "discover_argentina_companies"
                ),
                arguments=(
                    "--max-companies",
                    str(
                        args.argentina_max_companies
                    ),
                ),
            )
        )

    if not args.skip_contact_scan:
        contact_arguments = [
            "--profile",
            args.profile,
            "--limit",
            str(
                args.contact_limit
            ),
            "--max-pages-per-company",
            str(
                args.contact_max_pages
            ),
        ]

        if args.force_contact_rescan:
            contact_arguments.append(
                "--force"
            )

        plan.append(
            OutreachStep(
                name=(
                    "Discover public company "
                    "contacts"
                ),
                module=(
                    "discover_public_contacts"
                ),
                arguments=tuple(
                    contact_arguments
                ),
            )
        )

    plan.append(
        OutreachStep(
            name=(
                "Clean public contact quality"
            ),
            module=(
                "clean_public_contacts"
            ),
        )
    )

    plan.append(
        OutreachStep(
            name=(
                "Prioritize company outreach"
            ),
            module=(
                "prioritize_outreach"
            ),
            arguments=(
                "--profile",
                args.profile,
                "--apply",
                "--top",
                "20",
            ),
        )
    )

    plan.append(
        OutreachStep(
            name=(
                "Export outreach shortlist"
            ),
            module=(
                "export_outreach_shortlist"
            ),
            arguments=(
                "--profile",
                args.profile,
                "--min-score",
                str(
                    args.min_score
                ),
                "--min-explore-score",
                str(
                    args.min_explore_score
                ),
                "--output",
                str(
                    args.output
                ),
            ),
        )
    )

    print("Chamba Hunter outreach refresh")
    print("==============================")
    print(
        "Mode:",
        (
            "APPLY"
            if args.apply
            else "PLAN ONLY"
        ),
    )
    print(
        "Steps:",
        len(plan),
    )
    print()

    for index, step in enumerate(
        plan,
        start=1,
    ):
        print(
            f"{index:>2}. "
            f"{step.name}"
        )
        print(
            "    "
            + " ".join(
                _command(step)
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

    for index, step in enumerate(
        plan,
        start=1,
    ):
        print()
        print("=" * 72)
        print(
            f"[{index}/{len(plan)}] "
            f"{step.name}"
        )
        print("=" * 72)

        result = subprocess.run(
            _command(step),
            check=False,
        )

        if result.returncode != 0:
            raise SystemExit(
                "Outreach refresh stopped "
                f"at step {index}: "
                f"{step.module} "
                f"(exit {result.returncode})"
            )

    print()
    print(
        "Outreach refresh completed "
        "successfully."
    )
    print(
        "Shortlist:",
        args.output,
    )


if __name__ == "__main__":
    main()
