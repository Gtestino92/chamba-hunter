import argparse
from pathlib import Path
import sys

from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate
from chamba_hunter.repositories.company_outreach_repository import (
    CompanyOutreachRepository,
)
from chamba_hunter.repositories.public_contact_repository import (
    PublicContactRepository,
)
from chamba_hunter.services.outreach_batch_service import (
    BATCH_VERSION,
    prepare_generic_outreach_batch,
)


DEFAULT_PROFILE = "BACKEND_SOFTWARE_V1"
DEFAULT_MIN_SCORE = 35.0
DEFAULT_LIMIT = 20
DEFAULT_OUTPUT = Path(
    "output/outreach-generic-batch.json"
)
DEFAULT_ATTACHMENT = (
    "Giuliano Testino Resume EN.pdf"
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
            "Prepare a generic outreach batch "
            "for Gmail draft creation. Does not "
            "send email or persist SENT state."
        )
    )
    parser.add_argument(
        "--profile",
        default=DEFAULT_PROFILE,
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=DEFAULT_MIN_SCORE,
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
    )
    parser.add_argument(
        "--language",
        choices=["ES", "EN"],
        default=None,
    )
    parser.add_argument(
        "--include-unknown",
        action="store_true",
    )
    parser.add_argument(
        "--attachment-name",
        default=DEFAULT_ATTACHMENT,
        help=(
            "Attachment name recorded in the "
            "batch manifest. V1 draft creation "
            "uses the English CV from ChatGPT."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
    )

    args = parser.parse_args()

    if not 0 <= args.min_score <= 100:
        parser.error(
            "--min-score must be between 0 and 100"
        )

    if args.limit < 1:
        parser.error(
            "--limit must be at least 1"
        )

    database = Database()
    migrate(database)

    contacts = PublicContactRepository(
        database
    )
    repository = CompanyOutreachRepository(
        database,
        contacts,
    )

    batch = prepare_generic_outreach_batch(
        repository=repository,
        search_profile_name=args.profile,
        min_score=args.min_score,
        limit=args.limit,
        language=args.language,
        attachment_name=(
            args.attachment_name
        ),
        include_unknown=(
            args.include_unknown
        ),
    )

    batch.write_json(
        args.output
    )

    print("Generic outreach batch")
    print("----------------------")
    print(f"Version:     {BATCH_VERSION}")
    print(f"Profile:     {args.profile}")
    print(f"Min score:   {args.min_score:.0f}")
    print(
        "Language:    "
        + (args.language or "ALL")
    )
    print(
        f"Attachment:  {args.attachment_name}"
    )
    print(f"Candidates:  {len(batch.items)}")
    print(
        f"Output:      {args.output.resolve()}"
    )
    print()

    for index, item in enumerate(
        batch.items,
        start=1,
    ):
        print(
            f"{index:>2}. {item.company}"
        )
        print(f"    To:       {item.to}")
        print(
            f"    Strategy: {item.strategy}"
        )
        print(
            f"    Language: {item.language}"
        )
        print(
            f"    State:    {item.state}"
        )
        print()


if __name__ == "__main__":
    main()
