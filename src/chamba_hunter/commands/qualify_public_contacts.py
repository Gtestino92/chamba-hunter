import argparse
import sys

from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate
from chamba_hunter.repositories.contact_intelligence_repository import (
    ContactIntelligenceRepository,
)
from chamba_hunter.services.contact_intelligence_service import (
    ContactIntelligenceService,
    DEFAULT_LIMIT,
    DEFAULT_TIMEOUT_SECONDS,
    RULE_VERSION,
)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(
            encoding="utf-8",
            errors="replace",
        )

    parser = argparse.ArgumentParser(
        description=(
            "Evaluate public contacts for direct-outreach usefulness."
        )
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--force",
        action="store_true",
    )
    args = parser.parse_args()

    if args.limit < 1:
        parser.error("--limit must be at least 1")

    if args.timeout <= 0:
        parser.error("--timeout must be greater than 0")

    database = Database()
    migrate(database)

    summary = ContactIntelligenceService(
        ContactIntelligenceRepository(
            database
        ),
        timeout_seconds=args.timeout,
    ).run(
        limit=args.limit,
        force=args.force,
    )

    print("Public contact intelligence")
    print("---------------------------")
    print(f"Rule version:    {RULE_VERSION}")
    print(f"Inspected:       {summary.inspected}")
    print(f"Evaluated:       {summary.evaluated}")
    print(f"Named contacts:  {summary.named_contacts}")
    print(f"Direct > 20:     {summary.direct_contacts}")
    print(f"Page fetches:    {summary.page_fetches}")
    print(f"Fetch failures:  {summary.fetch_failures}")


if __name__ == "__main__":
    main()
