import argparse
from collections import Counter, defaultdict
import sys

from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate
from chamba_hunter.repositories.job_matching_repository import (
    JobMatchingRepository,
)
from chamba_hunter.repositories.tracing_repository import (
    TracingRepository,
)
from chamba_hunter.services.job_matching_service import (
    JobMatchingService,
    PROFESSIONAL_RELEVANCE_FLOOR,
    PROFILE_NAME,
    RULE_VERSION,
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
            "Evaluate professional fit for the "
            "current backend software search profile."
        )
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Persist the backend search profile and "
            "current professional matches. "
            "Without this flag the command is read-only."
        ),
    )

    parser.add_argument(
        "--top",
        type=int,
        default=100,
        help=(
            "Maximum ranked candidates to print."
        ),
    )

    parser.add_argument(
        "--borderline",
        type=int,
        default=30,
        help=(
            "Maximum candidates around match-level "
            "thresholds to print."
        ),
    )

    args = parser.parse_args()

    if args.top < 0:
        parser.error(
            "--top cannot be negative."
        )

    if args.borderline < 0:
        parser.error(
            "--borderline cannot be negative."
        )

    database = Database()

    if args.apply:
        applied_migrations = migrate(
            database
        )

        for migration in applied_migrations:
            print(
                "Applied migration:",
                migration,
            )

        if applied_migrations:
            print()

    service = JobMatchingService(
        repository=JobMatchingRepository(
            database
        ),
        tracing_repository=TracingRepository(
            database
        ),
    )

    summary = service.run(
        apply=args.apply
    )

    level_counts = Counter(
        decision.match_level
        for decision in summary.decisions
    )

    record_kind_counts = Counter(
        decision.record_kind
        for decision in summary.decisions
    )

    occupation_counts = defaultdict(
        Counter
    )

    for decision in summary.decisions:
        key = (
            decision.occupation_class
            + "/"
            + decision.backend_relevance
        )

        occupation_counts[
            key
        ][
            decision.match_level
        ] += 1

    penalty_count = sum(
        1
        for decision in summary.decisions
        if decision.technology_penalty < 0
    )

    ceiling_count = sum(
        1
        for decision in summary.decisions
        if (
            decision.score_ceiling
            < 100
        )
    )

    title_role_mismatch_count = sum(
        1
        for decision in summary.decisions
        if any(
            reason.startswith(
                "title_role_mismatch:"
            )
            for reason in decision.reasons[
                "ceiling_reasons"
            ]
        )
    )

    title_alternate_ceiling_count = sum(
        1
        for decision in summary.decisions
        if any(
            reason.startswith(
                "title_alternate_stack:"
            )
            for reason in decision.reasons[
                "ceiling_reasons"
            ]
        )
    )

    title_seniority_risk_count = sum(
        1
        for decision in summary.decisions
        if any(
            reason.startswith(
                "title_seniority_risk:"
            )
            for reason in decision.reasons[
                "ceiling_reasons"
            ]
        )
    )

    strong_backend_boost_count = sum(
        1
        for decision in summary.decisions
        if (
            decision.reasons[
                "components"
            ][
                "role"
            ][
                "reason"
            ]
            == (
                "SOFTWARE_ENGINEERING:"
                "UNKNOWN:"
                "STRONG_BACKEND_CORE"
            )
        )
    )

    zero_skill_high = [
        decision
        for decision in summary.decisions
        if (
            decision.skills_score == 0
            and decision.match_level
            in {
                "VERY_HIGH",
                "HIGH",
            }
        )
    ]

    ranked = sorted(
        summary.decisions,
        key=lambda decision: (
            -decision.score,
            decision.company_name.lower(),
            decision.title.lower(),
            decision.record_kind,
            decision.record_id,
        ),
    )

    print("Professional matching")
    print("---------------------")
    print(
        "Rule version: ",
        RULE_VERSION,
    )
    print(
        "Search profile:",
        PROFILE_NAME,
    )
    print(
        "Scope:         ",
        "Argentina ELIGIBLE + UNKNOWN",
    )
    print(
        "Mode:          ",
        (
            "APPLY"
            if args.apply
            else "DRY RUN"
        ),
    )
    print(
        "Candidates:    ",
        summary.total,
    )
    print(
        "Relevance floor:",
        PROFESSIONAL_RELEVANCE_FLOOR,
    )
    print(
        "Relevant:      ",
        summary.relevant,
    )

    if args.apply:
        print(
            "Created:       ",
            summary.created,
        )
        print(
            "Updated:       ",
            summary.updated,
        )
        print(
            "Deleted:       ",
            summary.deleted,
        )
        print(
            "Run id:        ",
            summary.run_id,
        )
        print(
            "Profile id:    ",
            summary.search_profile_id,
        )

    print()
    print("RECORD KINDS")
    print("------------")

    for key, count in sorted(
        record_kind_counts.items()
    ):
        print(
            f"{key:<12} {count}"
        )

    print()
    print("MATCH LEVELS")
    print("------------")

    for level in [
        "VERY_HIGH",
        "HIGH",
        "MEDIUM",
        "LOW",
    ]:
        count = level_counts[
            level
        ]

        percentage = (
            count
            / summary.total
            * 100
            if summary.total
            else 0
        )

        print(
            f"{level:<12} "
            f"{count:>4} "
            f"{percentage:>6.1f}%"
        )

    print()
    print("LEVELS BY OCCUPATION/BACKEND")
    print("----------------------------")

    for key in sorted(
        occupation_counts
    ):
        counts = occupation_counts[
            key
        ]

        rendered = ", ".join(
            (
                f"{level}="
                f"{counts[level]}"
            )
            for level in [
                "VERY_HIGH",
                "HIGH",
                "MEDIUM",
                "LOW",
            ]
            if counts[level]
        )

        print(
            f"{key:<38} "
            f"{rendered}"
        )

    print()
    print("SCORING DIAGNOSTICS")
    print("-------------------")
    print(
        "Technology penalties:",
        penalty_count,
    )
    print(
        "Score ceilings:      ",
        ceiling_count,
    )
    print(
        "High with 0 skill pts:",
        len(zero_skill_high),
    )
    print(
        "Title role mismatches:",
        title_role_mismatch_count,
    )
    print(
        "Title alt-stack caps: ",
        title_alternate_ceiling_count,
    )
    print(
        "Title seniority risks:",
        title_seniority_risk_count,
    )
    print(
        "Strong backend boosts:",
        strong_backend_boost_count,
    )

    print()
    print("TOP MATCHES")
    print("-----------")

    for index, decision in enumerate(
        ranked[:args.top],
        start=1,
    ):
        print(
            f"{index:>3}. "
            f"{decision.score:>5.1f} "
            f"{decision.match_level:<9} | "
            f"{decision.record_kind} "
            f"{decision.record_id} | "
            f"{decision.company_name} | "
            f"{decision.title}"
        )

        print(
            "     "
            f"role={decision.role_score:.1f} "
            f"skills={decision.skills_score:.1f} "
            f"seniority={decision.seniority_score:.1f} "
            f"leadership={decision.leadership_score:.1f} "
            f"techPenalty={decision.technology_penalty:.1f} "
            f"ceiling={decision.score_ceiling:.1f}"
        )

        components = decision.reasons[
            "components"
        ]

        skill_data = components[
            "skills"
        ]

        print(
            "     exact:",
            ",".join(
                skill_data["exact"]
            )
            or "<none>",
        )
        print(
            "     peer:",
            ",".join(
                skill_data["peer"]
            )
            or "<none>",
        )
        print(
            "     related:",
            ",".join(
                skill_data["related"]
            )
            or "<none>",
        )
        print(
            "     secondary:",
            ",".join(
                skill_data["secondary"]
            )
            or "<none>",
        )

        alternate = components[
            "technology_penalty"
        ][
            "alternate_families"
        ]

        if alternate:
            print(
                "     alternate stack:",
                ",".join(
                    alternate
                ),
            )

        ceiling_reasons = (
            decision.reasons[
                "ceiling_reasons"
            ]
        )

        if ceiling_reasons:
            print(
                "     ceiling reasons:",
                ",".join(
                    ceiling_reasons
                ),
            )

    print()
    print("HIGH MATCHES WITH ZERO SKILL POINTS")
    print("-----------------------------------")

    if not zero_skill_high:
        print("None.")
    else:
        for decision in sorted(
            zero_skill_high,
            key=lambda item: (
                -item.score,
                item.company_name.lower(),
                item.title.lower(),
            ),
        )[:50]:
            print(
                f"{decision.score:>5.1f} | "
                f"{decision.record_kind} "
                f"{decision.record_id} | "
                f"{decision.company_name} | "
                f"{decision.backend_relevance} | "
                f"{decision.seniority_class} | "
                f"{decision.title}"
            )

    print()
    print("TECHNOLOGY PENALTY SAMPLES")
    print("--------------------------")

    penalty_samples = [
        decision
        for decision in ranked
        if decision.technology_penalty < 0
    ]

    if not penalty_samples:
        print("None.")
    else:
        for decision in penalty_samples[:50]:
            families = (
                decision.reasons[
                    "components"
                ][
                    "technology_penalty"
                ][
                    "alternate_families"
                ]
            )

            print(
                f"{decision.score:>5.1f} | "
                f"{decision.match_level:<9} | "
                f"{decision.record_kind} "
                f"{decision.record_id} | "
                f"{decision.company_name} | "
                f"{decision.title} | "
                f"{','.join(families)}"
            )

    print()
    print("BORDERLINE THRESHOLD SAMPLES")
    print("----------------------------")

    thresholds = [
        80.0,
        65.0,
        PROFESSIONAL_RELEVANCE_FLOOR,
        45.0,
    ]

    borderline = sorted(
        summary.decisions,
        key=lambda decision: min(
            abs(
                decision.score
                - threshold
            )
            for threshold in thresholds
        ),
    )

    for decision in borderline[
        :args.borderline
    ]:
        nearest = min(
            thresholds,
            key=lambda threshold: abs(
                decision.score
                - threshold
            ),
        )

        print(
            f"score={decision.score:>5.1f} "
            f"near={nearest:>4.0f} | "
            f"{decision.match_level:<9} | "
            f"{decision.record_kind} "
            f"{decision.record_id} | "
            f"{decision.company_name} | "
            f"{decision.title}"
        )


if __name__ == "__main__":
    main()
