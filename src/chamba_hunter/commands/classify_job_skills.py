import argparse
from collections import Counter
import sys

from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate
from chamba_hunter.repositories.job_skill_repository import (
    JobSkillRepository,
)
from chamba_hunter.repositories.tracing_repository import (
    TracingRepository,
)
from chamba_hunter.services.job_skill_classification_service import (
    JobSkillClassificationService,
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
            "Extract explicit skill mentions from "
            "geographically viable job candidates."
        )
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Persist current skill classifications. "
            "Without this flag the command "
            "is read-only."
        ),
    )

    parser.add_argument(
        "--top-skills",
        type=int,
        default=60,
        help=(
            "Maximum top skills to print."
        ),
    )

    parser.add_argument(
        "--no-skill-samples",
        type=int,
        default=20,
        help=(
            "Maximum candidate examples with no "
            "recognized skills to print."
        ),
    )

    args = parser.parse_args()

    if args.top_skills < 0:
        parser.error(
            "--top-skills cannot be negative."
        )

    if args.no_skill_samples < 0:
        parser.error(
            "--no-skill-samples cannot be negative."
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

    service = JobSkillClassificationService(
        repository=JobSkillRepository(
            database
        ),
        tracing_repository=TracingRepository(
            database
        ),
    )

    summary = service.run(
        apply=args.apply
    )

    category_counts = Counter(
        decision.skill_category
        for decision in summary.decisions
    )

    skill_counts = Counter(
        decision.skill_key
        for decision in summary.decisions
    )

    title_counts = Counter(
        decision.skill_key
        for decision in summary.decisions
        if decision.title_match
    )

    description_counts = Counter(
        decision.skill_key
        for decision in summary.decisions
        if decision.description_match
    )

    source_counts = Counter(
        _source_method(
            decision.title_match,
            decision.description_match,
        )
        for decision in summary.decisions
    )

    occupation_candidate_keys = {}

    for candidate in summary.candidates:
        occupation = (
            candidate.occupation_class
            or "UNCLASSIFIED"
        )

        occupation_candidate_keys.setdefault(
            occupation,
            {
                "all": set(),
                "with_skills": set(),
            },
        )

        key = (
            candidate.record_kind,
            candidate.record_id,
        )

        occupation_candidate_keys[
            occupation
        ][
            "all"
        ].add(
            key
        )

    for decision in summary.decisions:
        occupation = (
            decision.occupation_class
            or "UNCLASSIFIED"
        )

        occupation_candidate_keys.setdefault(
            occupation,
            {
                "all": set(),
                "with_skills": set(),
            },
        )

        occupation_candidate_keys[
            occupation
        ][
            "with_skills"
        ].add(
            (
                decision.record_kind,
                decision.record_id,
            )
        )

    print("Job skill classification")
    print("------------------------")
    print(
        "Rule version:",
        RULE_VERSION,
    )
    print(
        "Scope:       ",
        "Argentina ELIGIBLE + UNKNOWN",
    )
    print(
        "Mode:        ",
        (
            "APPLY"
            if args.apply
            else "DRY RUN"
        ),
    )
    print(
        "Candidates:  ",
        summary.total_candidates,
    )
    print(
        "With skills: ",
        summary.candidates_with_skills,
    )
    print(
        "No skills:   ",
        summary.candidates_without_skills,
    )
    print(
        "Skill rows:  ",
        summary.total_skill_rows,
    )

    if args.apply:
        print(
            "Created:     ",
            summary.created,
        )
        print(
            "Updated:     ",
            summary.updated,
        )
        print(
            "Deleted:     ",
            summary.deleted,
        )
        print(
            "Run id:      ",
            summary.run_id,
        )

    print()
    print("CANDIDATE COVERAGE BY OCCUPATION")
    print("--------------------------------")

    for occupation in sorted(
        occupation_candidate_keys
    ):
        data = occupation_candidate_keys[
            occupation
        ]

        total = len(
            data["all"]
        )

        with_skills = len(
            data["with_skills"]
        )

        percentage = (
            with_skills
            / total
            * 100
            if total
            else 0
        )

        print(
            f"{occupation:<24} "
            f"{with_skills:>4}/{total:<4} "
            f"{percentage:>6.1f}%"
        )

    print()
    print("CATEGORIES")
    print("----------")

    for category, count in sorted(
        category_counts.items(),
        key=lambda item: (
            -item[1],
            item[0],
        ),
    ):
        print(
            f"{category:<24} {count}"
        )

    print()
    print("SOURCES")
    print("-------")

    for source, count in sorted(
        source_counts.items()
    ):
        print(
            f"{source:<20} {count}"
        )

    print()
    print("TOP SKILLS")
    print("----------")
    print(
        "rows | title | desc | "
        "category | skill"
    )

    decisions_by_skill = {
        decision.skill_key: decision
        for decision in summary.decisions
    }

    for (
        skill_key,
        count,
    ) in skill_counts.most_common(
        args.top_skills
    ):
        decision = (
            decisions_by_skill[
                skill_key
            ]
        )

        print(
            f"{count:>4} | "
            f"{title_counts[skill_key]:>5} | "
            f"{description_counts[skill_key]:>4} | "
            f"{decision.skill_category:<22} | "
            f"{skill_key}"
        )

    candidate_keys_with_skills = {
        (
            decision.record_kind,
            decision.record_id,
        )
        for decision in summary.decisions
    }

    no_skill_candidates = [
        candidate
        for candidate in summary.candidates
        if (
            candidate.record_kind,
            candidate.record_id,
        )
        not in candidate_keys_with_skills
    ]

    print()
    print("NO RECOGNIZED SKILL SAMPLES")
    print("---------------------------")

    if not no_skill_candidates:
        print("None.")
    else:
        for candidate in no_skill_candidates[
            :args.no_skill_samples
        ]:
            print(
                candidate.record_kind,
                candidate.record_id,
                "|",
                candidate.origin,
                "|",
                candidate.company_name,
                "|",
                (
                    candidate.occupation_class
                    or "UNCLASSIFIED"
                ),
                "|",
                (
                    candidate.backend_relevance
                    or "UNCLASSIFIED"
                ),
                "|",
                candidate.title,
            )


def _source_method(
    title_match: bool,
    description_match: bool,
) -> str:
    if (
        title_match
        and description_match
    ):
        return "TITLE_DESCRIPTION"

    if title_match:
        return "TITLE"

    return "DESCRIPTION"


if __name__ == "__main__":
    main()
