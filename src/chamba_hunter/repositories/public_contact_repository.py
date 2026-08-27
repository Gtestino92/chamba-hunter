from dataclasses import replace
import sqlite3
from urllib.parse import urlsplit, urlunsplit

from chamba_hunter.db.connection import Database
from chamba_hunter.db.converters import (
    bool_from_db,
    bool_to_db,
    datetime_from_db,
    datetime_to_db,
)
from chamba_hunter.domain.common import utc_now
from chamba_hunter.domain.enums import (
    ContactReviewStatus,
    ContactType,
)
from chamba_hunter.domain.models import PublicContact


EMAIL_TYPES = frozenset(
    {
        ContactType.CAREERS_EMAIL,
        ContactType.RECRUITING_EMAIL,
        ContactType.GENERAL_EMAIL,
    }
)


def normalize_contact_value(
    contact_type: ContactType,
    value: str,
) -> str:
    cleaned = value.strip()

    if not cleaned:
        raise ValueError(
            "Public contact value cannot be empty."
        )

    if contact_type in EMAIL_TYPES:
        return cleaned.casefold()

    parsed = urlsplit(cleaned)

    if parsed.scheme.casefold() not in {
        "http",
        "https",
    }:
        raise ValueError(
            "General application contact must "
            "be an HTTP(S) URL."
        )

    hostname = (
        parsed.hostname.casefold()
        if parsed.hostname
        else None
    )

    if hostname is None:
        raise ValueError(
            "General application URL must "
            "contain a hostname."
        )

    netloc = hostname

    if parsed.port is not None:
        is_default = (
            parsed.scheme.casefold() == "http"
            and parsed.port == 80
        ) or (
            parsed.scheme.casefold() == "https"
            and parsed.port == 443
        )

        if not is_default:
            netloc = (
                f"{netloc}:{parsed.port}"
            )

    return urlunsplit(
        (
            parsed.scheme.casefold(),
            netloc,
            parsed.path.rstrip("/"),
            parsed.query,
            "",
        )
    )


def _row_to_contact(
    row: sqlite3.Row,
) -> PublicContact:
    return PublicContact(
        id=int(row["id"]),
        company_id=int(row["company_id"]),
        contact_type=ContactType(
            row["contact_type"]
        ),
        value=str(row["value"]),
        source_url=row["source_url"],
        first_seen_at=datetime_from_db(
            row["first_seen_at"]
        ),
        last_seen_at=datetime_from_db(
            row["last_seen_at"]
        ),
        is_active=bool_from_db(
            row["is_active"]
        )
        is True,
        review_status=ContactReviewStatus(
            row["review_status"]
        ),
        notes=row["notes"],
    )


class PublicContactRepository:
    def __init__(
        self,
        database: Database,
    ) -> None:
        self.database = database

    def add_or_touch(
        self,
        contact: PublicContact,
    ) -> tuple[PublicContact, bool]:
        if contact.id is not None:
            raise ValueError(
                "Cannot add a PublicContact "
                "that already has an id."
            )

        normalized_value = (
            normalize_contact_value(
                contact.contact_type,
                contact.value,
            )
        )

        now = utc_now()

        with self.database.transaction() as connection:
            existing = connection.execute(
                """
                SELECT *
                FROM public_contacts
                WHERE company_id = ?
                  AND contact_type = ?
                  AND value = ?
                """,
                (
                    contact.company_id,
                    contact.contact_type.value,
                    normalized_value,
                ),
            ).fetchone()

            if existing is not None:
                source_url = (
                    existing["source_url"]
                    or contact.source_url
                )
                notes = (
                    existing["notes"]
                    or contact.notes
                )

                connection.execute(
                    """
                    UPDATE public_contacts
                    SET
                        source_url = ?,
                        last_seen_at = ?,
                        is_active = 1,
                        notes = ?
                    WHERE id = ?
                    """,
                    (
                        source_url,
                        datetime_to_db(now),
                        notes,
                        int(existing["id"]),
                    ),
                )

                return (
                    replace(
                        _row_to_contact(
                            existing
                        ),
                        source_url=source_url,
                        last_seen_at=now,
                        is_active=True,
                        notes=notes,
                    ),
                    False,
                )

            cursor = connection.execute(
                """
                INSERT INTO public_contacts (
                    company_id,
                    contact_type,
                    value,
                    source_url,
                    first_seen_at,
                    last_seen_at,
                    is_active,
                    review_status,
                    notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    contact.company_id,
                    contact.contact_type.value,
                    normalized_value,
                    contact.source_url,
                    datetime_to_db(now),
                    datetime_to_db(now),
                    bool_to_db(True),
                    contact.review_status.value,
                    contact.notes,
                ),
            )

            contact_id = cursor.lastrowid

        if contact_id is None:
            raise RuntimeError(
                "SQLite did not return a public "
                "contact id."
            )

        return (
            replace(
                contact,
                id=int(contact_id),
                value=normalized_value,
                first_seen_at=now,
                last_seen_at=now,
                is_active=True,
            ),
            True,
        )

    def list_active_for_company(
        self,
        company_id: int,
    ) -> list[PublicContact]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM public_contacts
                WHERE company_id = ?
                  AND is_active = 1
                  AND review_status != 'INVALID'
                ORDER BY id
                """,
                (company_id,),
            ).fetchall()

        return [
            _row_to_contact(row)
            for row in rows
        ]


    def import_company_general_application_urls(
        self,
    ) -> int:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    general_application_url
                FROM companies
                WHERE general_application_url
                    IS NOT NULL
                  AND TRIM(
                      general_application_url
                  ) != ''
                """
            ).fetchall()

        created = 0

        for row in rows:
            _, was_created = self.add_or_touch(
                PublicContact(
                    company_id=int(
                        row["id"]
                    ),
                    contact_type=(
                        ContactType
                        .GENERAL_APPLICATION_URL
                    ),
                    value=str(
                        row[
                            "general_application_url"
                        ]
                    ),
                    source_url=str(
                        row[
                            "general_application_url"
                        ]
                    ),
                    notes=(
                        "Imported from existing "
                        "company general application "
                        "URL."
                    ),
                )
            )

            if was_created:
                created += 1

        return created

    def find_active_value(
        self,
        company_id: int,
        value: str,
    ) -> PublicContact | None:
        cleaned = value.strip().casefold()

        for contact in (
            self.list_active_for_company(
                company_id
            )
        ):
            if (
                contact.value.casefold()
                == cleaned
            ):
                return contact

        return None
