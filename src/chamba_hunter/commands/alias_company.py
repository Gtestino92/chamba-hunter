import argparse
import sys

from chamba_hunter.db.connection import Database
from chamba_hunter.db.converters import datetime_to_db
from chamba_hunter.db.migrations import migrate
from chamba_hunter.domain.common import utc_now
from chamba_hunter.repositories.company_repository import (
    CompanyRepository,
)
from chamba_hunter.services.company_import_service import (
    normalize_company_name,
)


def _resolve_company(
    repository: CompanyRepository,
    name: str,
):
    company = repository.get_unique_by_normalized_name(
        normalize_company_name(name)
    )

    if company is None or company.id is None:
        raise SystemExit(
            "Could not resolve a unique company: "
            f"{name!r}"
        )

    return company


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(
            encoding="utf-8",
            errors="replace",
        )

    parser = argparse.ArgumentParser(
        description=(
            "Declare one duplicate company row as an alias "
            "of a canonical company."
        )
    )
    parser.add_argument(
        "--canonical",
        required=True,
        help="Canonical company name.",
    )
    parser.add_argument(
        "--alias",
        required=True,
        help="Duplicate/alias company name.",
    )
    parser.add_argument(
        "--reason",
        default="Manual company identity alias.",
    )
    args = parser.parse_args()

    database = Database()
    migrate(database)

    repository = CompanyRepository(database)
    canonical = _resolve_company(
        repository,
        args.canonical,
    )
    alias = _resolve_company(
        repository,
        args.alias,
    )

    if canonical.id == alias.id:
        raise SystemExit(
            "Canonical company and alias resolve to the same row."
        )

    with database.transaction() as connection:
        canonical_parent = connection.execute(
            """
            SELECT canonical_company_id
            FROM company_aliases
            WHERE alias_company_id = ?
            """,
            (canonical.id,),
        ).fetchone()

        if canonical_parent is not None:
            raise SystemExit(
                "The selected canonical company is itself an alias. "
                "Use its canonical company instead."
            )

        child_aliases = connection.execute(
            """
            SELECT alias_company_id
            FROM company_aliases
            WHERE canonical_company_id = ?
              AND alias_company_id != ?
            LIMIT 1
            """,
            (
                alias.id,
                canonical.id,
            ),
        ).fetchone()

        if child_aliases is not None:
            raise SystemExit(
                "The selected alias is already a canonical company "
                "for another alias. Flatten that group first."
            )

        connection.execute(
            """
            INSERT INTO company_aliases (
                alias_company_id,
                canonical_company_id,
                reason,
                created_at
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(alias_company_id)
            DO UPDATE SET
                canonical_company_id = excluded.canonical_company_id,
                reason = excluded.reason
            """,
            (
                alias.id,
                canonical.id,
                args.reason.strip() or None,
                datetime_to_db(utc_now()),
            ),
        )

    print("Company alias saved")
    print("-------------------")
    print(
        f"Canonical: {canonical.name} (id={canonical.id})"
    )
    print(
        f"Alias:     {alias.name} (id={alias.id})"
    )


if __name__ == "__main__":
    main()
