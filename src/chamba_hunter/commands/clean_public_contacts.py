import sys

from chamba_hunter.db.connection import (
    Database,
)
from chamba_hunter.db.migrations import (
    migrate,
)
from chamba_hunter.services.public_contact_cleanup_service import (
    PublicContactCleanupService,
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

    database = Database()
    migrate(
        database
    )

    summary = (
        PublicContactCleanupService(
            database
        )
        .run()
    )

    print(
        "Public contact quality cleanup"
    )
    print(
        "------------------------------"
    )
    print(
        f"Rule version:      "
        f"{RULE_VERSION}"
    )
    print(
        f"Inspected:         "
        f"{summary.inspected}"
    )
    print(
        f"Invalidated:       "
        f"{summary.invalidated}"
    )
    print(
        f"Placeholders:      "
        f"{summary.placeholder}"
    )
    print(
        f"Domain mismatch:   "
        f"{summary.domain_mismatch}"
    )
    print(
        f"Reclassified:      "
        f"{summary.reclassified}"
    )
    print(
        f"Merged duplicates: "
        f"{summary.merged}"
    )


if __name__ == "__main__":
    main()
