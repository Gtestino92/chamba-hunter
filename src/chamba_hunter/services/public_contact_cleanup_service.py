from dataclasses import dataclass

from chamba_hunter.db.connection import (
    Database,
)
from chamba_hunter.domain.enums import (
    ContactType,
)
from chamba_hunter.services.public_contact_quality import (
    classify_email,
    email_domain_compatible,
    is_obvious_placeholder_email,
)


CRAWLER_NOTE = (
    "Discovered on the company's "
    "public website."
)

RULE_VERSION = (
    "CONTACT_QUALITY_V2_3"
)


@dataclass(frozen=True, slots=True)
class PublicContactCleanupSummary:
    inspected: int
    invalidated: int
    placeholder: int
    domain_mismatch: int
    reclassified: int
    merged: int


class PublicContactCleanupService:
    def __init__(
        self,
        database: Database,
    ) -> None:
        self.database = database

    def run(
        self,
    ) -> PublicContactCleanupSummary:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    pc.id,
                    pc.company_id,
                    pc.value,
                    pc.contact_type,
                    pc.source_url,
                    pc.last_seen_at,
                    pc.notes,
                    c.website_url
                FROM public_contacts pc
                JOIN companies c
                  ON c.id = pc.company_id
                WHERE
                    pc.is_active = 1
                    AND pc.review_status
                        != 'INVALID'
                    AND pc.contact_type IN (
                        'RECRUITING_EMAIL',
                        'CAREERS_EMAIL',
                        'GENERAL_EMAIL'
                    )
                ORDER BY pc.id
                """
            ).fetchall()

        invalid: list[
            tuple[int, str]
        ] = []

        reclassifications: list[
            tuple[
                int,
                int,
                str,
                str,
                str | None,
                str,
                str | None,
            ]
        ] = []

        placeholders = 0
        domain_mismatches = 0

        for row in rows:
            contact_id = int(
                row["id"]
            )

            value = str(
                row["value"]
            )

            if is_obvious_placeholder_email(
                value
            ):
                placeholders += 1

                invalid.append(
                    (
                        contact_id,
                        (
                            f"{RULE_VERSION}: "
                            "obvious placeholder."
                        ),
                    )
                )
                continue

            notes = (
                str(row["notes"])
                if row["notes"]
                is not None
                else ""
            )

            if (
                CRAWLER_NOTE in notes
                and not email_domain_compatible(
                    value,
                    row["website_url"],
                )
            ):
                domain_mismatches += 1

                invalid.append(
                    (
                        contact_id,
                        (
                            f"{RULE_VERSION}: "
                            "crawler email domain "
                            "does not match company "
                            "website."
                        ),
                    )
                )
                continue

            desired_type = (
                classify_email(
                    value
                )
            )

            if desired_type is None:
                continue

            current_type = (
                ContactType(
                    row["contact_type"]
                )
            )

            if desired_type == current_type:
                continue

            reclassifications.append(
                (
                    contact_id,
                    int(
                        row["company_id"]
                    ),
                    value,
                    desired_type.value,
                    row["source_url"],
                    str(
                        row["last_seen_at"]
                    ),
                    (
                        str(row["notes"])
                        if row["notes"]
                        is not None
                        else None
                    ),
                )
            )

        reclassified = 0
        merged = 0

        with self.database.transaction() as connection:
            for contact_id, reason in invalid:
                _invalidate_contact(
                    connection=connection,
                    contact_id=contact_id,
                    reason=reason,
                )

            for (
                contact_id,
                company_id,
                value,
                desired_type,
                source_url,
                last_seen_at,
                notes,
            ) in reclassifications:
                existing = connection.execute(
                    """
                    SELECT
                        id,
                        source_url,
                        last_seen_at,
                        review_status,
                        notes
                    FROM public_contacts
                    WHERE
                        company_id = ?
                        AND contact_type = ?
                        AND value = ?
                        AND id != ?
                    ORDER BY id
                    LIMIT 1
                    """,
                    (
                        company_id,
                        desired_type,
                        value,
                        contact_id,
                    ),
                ).fetchone()

                if existing is None:
                    connection.execute(
                        """
                        UPDATE public_contacts
                        SET
                            contact_type = ?,
                            notes = ?
                        WHERE id = ?
                        """,
                        (
                            desired_type,
                            _append_note(
                                notes,
                                (
                                    f"{RULE_VERSION}: "
                                    "reclassified email "
                                    f"as {desired_type}."
                                ),
                            ),
                            contact_id,
                        ),
                    )

                    reclassified += 1
                    continue

                existing_id = int(
                    existing["id"]
                )

                final_source_url = (
                    existing["source_url"]
                    or source_url
                )

                final_last_seen = max(
                    str(
                        existing["last_seen_at"]
                    ),
                    last_seen_at,
                )

                existing_notes = (
                    str(existing["notes"])
                    if existing["notes"]
                    is not None
                    else None
                )

                final_notes = _append_note(
                    existing_notes,
                    (
                        f"{RULE_VERSION}: merged "
                        f"duplicate classification "
                        f"from contact {contact_id}."
                    ),
                )

                final_review = (
                    "UNREVIEWED"
                    if (
                        existing[
                            "review_status"
                        ]
                        == "INVALID"
                    )
                    else existing[
                        "review_status"
                    ]
                )

                connection.execute(
                    """
                    UPDATE public_contacts
                    SET
                        source_url = ?,
                        last_seen_at = ?,
                        is_active = 1,
                        review_status = ?,
                        notes = ?
                    WHERE id = ?
                    """,
                    (
                        final_source_url,
                        final_last_seen,
                        final_review,
                        final_notes,
                        existing_id,
                    ),
                )

                _invalidate_contact(
                    connection=connection,
                    contact_id=contact_id,
                    reason=(
                        f"{RULE_VERSION}: "
                        "superseded by "
                        f"reclassified contact "
                        f"{existing_id}."
                    ),
                )

                merged += 1

        return (
            PublicContactCleanupSummary(
                inspected=len(rows),
                invalidated=len(
                    invalid
                ),
                placeholder=(
                    placeholders
                ),
                domain_mismatch=(
                    domain_mismatches
                ),
                reclassified=(
                    reclassified
                ),
                merged=merged,
            )
        )


def _append_note(
    previous: str | None,
    reason: str,
) -> str:
    cleaned = (
        previous.strip()
        if previous
        else ""
    )

    if reason in cleaned:
        return cleaned

    return (
        f"{cleaned}; {reason}"
        if cleaned
        else reason
    )


def _invalidate_contact(
    *,
    connection,
    contact_id: int,
    reason: str,
) -> None:
    row = connection.execute(
        """
        SELECT notes
        FROM public_contacts
        WHERE id = ?
        """,
        (contact_id,),
    ).fetchone()

    previous = (
        str(row["notes"])
        if (
            row is not None
            and row["notes"]
            is not None
        )
        else None
    )

    connection.execute(
        """
        UPDATE public_contacts
        SET
            is_active = 0,
            review_status = 'INVALID',
            notes = ?
        WHERE id = ?
        """,
        (
            _append_note(
                previous,
                reason,
            ),
            contact_id,
        ),
    )
