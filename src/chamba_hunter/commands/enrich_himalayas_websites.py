import argparse
import time

import httpx
from pydantic import (
    AnyHttpUrl,
    TypeAdapter,
    ValidationError,
)

from chamba_hunter.db.connection import (
    Database,
)
from chamba_hunter.db.migrations import (
    migrate,
)
from chamba_hunter.domain.enums import (
    CompanyStatus,
    SourceType,
)
from chamba_hunter.repositories.company_repository import (
    CompanyRepository,
)
from chamba_hunter.services.company_import_service import (
    extract_domain,
    normalize_website_url,
)
from chamba_hunter.sources.himalayas_mcp import (
    HimalayasMcpClient,
    HimalayasMcpError,
)


HTTP_URL_ADAPTER = TypeAdapter(
    AnyHttpUrl
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Fill missing company websites "
            "using Himalayas' public MCP "
            "get_company_details tool."
        )
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help=(
            "Maximum companies to enrich. "
            "Defaults to 10."
        ),
    )

    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=0.10,
        help=(
            "Delay between MCP company calls. "
            "Defaults to 0.10."
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Show eligible companies without "
            "calling the MCP server."
        ),
    )

    args = parser.parse_args()

    if args.limit < 1:
        parser.error(
            "--limit must be at least 1"
        )

    if args.delay_seconds < 0:
        parser.error(
            "--delay-seconds cannot be negative"
        )

    database = Database()
    migrate(database)

    company_repository = (
        CompanyRepository(database)
    )

    targets = _targets(
        database=database,
    )

    selected = targets[
        :args.limit
    ]

    print(
        "Enriching Himalayas company "
        "websites via MCP..."
    )
    print(
        f"Eligible companies:   "
        f"{len(targets)}"
    )
    print(
        f"Selected:             "
        f"{len(selected)}"
    )
    print()

    if args.dry_run:
        for (
            company_id,
            company_name,
            company_slug,
        ) in selected:
            print(
                f"{company_name} "
                f"[{company_slug}]"
            )

        print()
        print(
            "Dry run; no MCP calls or "
            "DB updates executed."
        )
        return

    found = 0
    not_found = 0
    conflicts = 0
    failed = 0

    try:
        with HimalayasMcpClient() as client:
            for index, (
                company_id,
                company_name,
                company_slug,
            ) in enumerate(selected):
                try:
                    details = (
                        client.get_company_details(
                            company_slug
                        )
                    )

                    if (
                        details.website_url
                        is None
                    ):
                        not_found += 1

                        print(
                            f"{company_name}: "
                            "NOT_FOUND"
                        )
                        print(
                            "  MCP returned no "
                            "Website link."
                        )
                        print()
                        continue

                    validated = (
                        HTTP_URL_ADAPTER
                        .validate_python(
                            details.website_url
                        )
                    )

                    normalized_url = (
                        normalize_website_url(
                            validated
                        )
                    )

                    domain = extract_domain(
                        validated
                    )

                    owner = (
                        company_repository
                        .get_by_domain(
                            domain
                        )
                    )

                    if (
                        owner is not None
                        and owner.id
                        != company_id
                    ):
                        conflicts += 1

                        print(
                            f"{company_name}: "
                            "DOMAIN_CONFLICT"
                        )
                        print(
                            f"  website: "
                            f"{normalized_url}"
                        )
                        print(
                            f"  domain already "
                            f"belongs to company "
                            f"{owner.id} "
                            f"({owner.name})"
                        )
                        print()
                        continue

                    (
                        company_repository
                        .fill_missing_discovery_fields(
                            company_id=company_id,
                            website_url=(
                                normalized_url
                            ),
                            domain=domain,
                        )
                    )

                    found += 1

                    print(
                        f"{company_name}: FOUND"
                    )
                    print(
                        f"  {normalized_url}"
                    )
                    print()

                except (
                    HimalayasMcpError,
                    httpx.HTTPError,
                    ValidationError,
                    ValueError,
                ) as exc:
                    failed += 1

                    print(
                        f"{company_name}: ERROR"
                    )
                    print(
                        f"  "
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    )
                    print()

                if (
                    index
                    < len(selected) - 1
                    and args.delay_seconds > 0
                ):
                    time.sleep(
                        args.delay_seconds
                    )

    except (
        HimalayasMcpError,
        httpx.HTTPError,
    ) as exc:
        print(
            "MCP initialization failed:"
        )
        print(
            f"  {type(exc).__name__}: "
            f"{exc}"
        )
        return

    print("Enrichment finished")
    print("-------------------")
    print(
        f"Processed:    "
        f"{len(selected)}"
    )
    print(
        f"Found:        "
        f"{found}"
    )
    print(
        f"Not found:    "
        f"{not_found}"
    )
    print(
        f"Conflicts:    "
        f"{conflicts}"
    )
    print(
        f"Failed:       "
        f"{failed}"
    )


def _targets(
    database: Database,
) -> list[
    tuple[int, str, str]
]:
    with database.connection() as connection:
        rows = connection.execute(
            """
            SELECT
                c.id AS company_id,
                c.name AS company_name,

                (
                    SELECT cs.external_id
                    FROM company_sources cs
                    WHERE
                        cs.company_id = c.id
                        AND cs.source_type = ?
                        AND cs.external_id
                            IS NOT NULL
                        AND TRIM(
                            cs.external_id
                        ) != ''
                    ORDER BY cs.id
                    LIMIT 1
                ) AS company_slug,

                COUNT(jl.id) AS lead_count

            FROM companies c

            JOIN job_leads jl
              ON jl.company_id = c.id
             AND jl.source_type = ?
             AND jl.is_active = 1
             AND jl.canonical_job_id
                 IS NULL

            WHERE
                c.status = ?
                AND c.website_url IS NULL
                AND NOT EXISTS (
                    SELECT 1
                    FROM company_ats ca
                    WHERE ca.company_id = c.id
                      AND ca.is_active = 1
                )

            GROUP BY
                c.id,
                c.name

            HAVING company_slug IS NOT NULL

            ORDER BY
                lead_count DESC,
                c.name COLLATE NOCASE,
                c.id
            """,
            (
                SourceType.HIMALAYAS.value,
                SourceType.HIMALAYAS.value,
                CompanyStatus.ACTIVE.value,
            ),
        ).fetchall()

    return [
        (
            int(row["company_id"]),
            str(row["company_name"]),
            str(row["company_slug"]),
        )
        for row in rows
    ]


if __name__ == "__main__":
    main()
