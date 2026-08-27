from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
import re
from time import sleep

import httpx

from chamba_hunter.services.company_import_service import (
    normalize_company_name,
)


CESSI_DIRECTORY_URL = (
    "https://cessi.org.ar/directorio-de-empresas/"
)

DEFAULT_MAX_PAGES = 20
DEFAULT_REQUEST_DELAY_SECONDS = 0.25

EMAIL_PATTERN = re.compile(
    r"\b[A-Z0-9._%+\-]+@"
    r"[A-Z0-9.\-]+\.[A-Z]{2,}\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class CessiCompany:
    name: str
    email: str
    activity: str | None
    address: str | None
    city: str | None
    province: str | None
    page_url: str

    @property
    def external_id(
        self,
    ) -> str:
        return normalize_company_name(
            self.name
        )


@dataclass(frozen=True, slots=True)
class CessiDirectoryFetch:
    pages_fetched: int
    companies: list[CessiCompany]


class _DirectoryParser(HTMLParser):
    def __init__(
        self,
        page_url: str,
    ) -> None:
        super().__init__(
            convert_charrefs=True
        )
        self.page_url = page_url
        self._in_h3 = False
        self._heading_parts: list[
            str
        ] = []
        self._current_name: (
            str | None
        ) = None
        self._current_parts: list[
            str
        ] = []
        self._current_mailtos: list[
            str
        ] = []
        self.companies: list[
            CessiCompany
        ] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[
            tuple[
                str,
                str | None,
            ]
        ],
    ) -> None:
        normalized_tag = tag.casefold()

        if normalized_tag == "h3":
            self._flush()
            self._in_h3 = True
            self._heading_parts = []
            return

        if (
            self._current_name
            is not None
            and normalized_tag == "a"
        ):
            href = dict(attrs).get(
                "href"
            )

            if (
                href is not None
                and href.casefold()
                .startswith("mailto:")
            ):
                raw = (
                    href.split(":", 1)[1]
                    .split("?", 1)[0]
                    .strip()
                )

                if raw:
                    self._current_mailtos.append(
                        raw
                    )

    def handle_endtag(
        self,
        tag: str,
    ) -> None:
        if (
            tag.casefold() == "h3"
            and self._in_h3
        ):
            self._in_h3 = False
            self._current_name = (
                _clean_text(
                    " ".join(
                        self._heading_parts
                    )
                )
            )
            self._current_parts = []
            self._current_mailtos = []

    def handle_data(
        self,
        data: str,
    ) -> None:
        cleaned = _clean_text(
            unescape(data)
        )

        if cleaned is None:
            return

        if self._in_h3:
            self._heading_parts.append(
                cleaned
            )
            return

        if self._current_name is not None:
            self._current_parts.append(
                cleaned
            )

    def close(
        self,
    ) -> None:
        super().close()
        self._flush()

    def _flush(
        self,
    ) -> None:
        if self._current_name is None:
            return

        joined = " | ".join(
            self._current_parts
        )

        emails: list[str] = []

        for value in (
            *self._current_mailtos,
            *EMAIL_PATTERN.findall(
                joined
            ),
        ):
            cleaned = (
                value.strip()
                .rstrip(".,;:")
                .casefold()
            )

            if (
                cleaned
                and cleaned
                not in emails
            ):
                emails.append(
                    cleaned
                )

        if emails:
            activity = _value_after_label(
                self._current_parts,
                "actividad",
            )
            address = _prefixed_value(
                self._current_parts,
                "domicilio",
            )
            city = _prefixed_value(
                self._current_parts,
                "ciudad",
            )
            province = _prefixed_value(
                self._current_parts,
                "provincia",
            )

            self.companies.append(
                CessiCompany(
                    name=self._current_name,
                    email=emails[0],
                    activity=activity,
                    address=address,
                    city=city,
                    province=province,
                    page_url=self.page_url,
                )
            )

        self._current_name = None
        self._current_parts = []
        self._current_mailtos = []


class CessiDirectoryClient:
    def __init__(
        self,
        *,
        timeout_seconds: float = 20.0,
        request_delay_seconds: float = (
            DEFAULT_REQUEST_DELAY_SECONDS
        ),
    ) -> None:
        if request_delay_seconds < 0:
            raise ValueError(
                "request_delay_seconds cannot "
                "be negative."
            )

        self.timeout_seconds = (
            timeout_seconds
        )
        self.request_delay_seconds = (
            request_delay_seconds
        )

    def fetch(
        self,
        *,
        max_pages: int = (
            DEFAULT_MAX_PAGES
        ),
    ) -> CessiDirectoryFetch:
        if max_pages < 1:
            raise ValueError(
                "max_pages must be at least 1."
            )

        unique: dict[
            str,
            CessiCompany,
        ] = {}
        pages_fetched = 0

        with httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "chamba-hunter/0.1 "
                    "(public company directory)"
                ),
                "Accept": "text/html",
            },
        ) as client:
            for page_number in range(
                1,
                max_pages + 1,
            ):
                response = client.get(
                    CESSI_DIRECTORY_URL,
                    params={
                        "pagina": page_number
                    },
                )
                response.raise_for_status()
                pages_fetched += 1

                parser = _DirectoryParser(
                    page_url=str(
                        response.url
                    )
                )
                parser.feed(
                    response.text
                )
                parser.close()

                if not parser.companies:
                    break

                before = len(unique)

                for company in parser.companies:
                    unique[
                        company.external_id
                    ] = company

                # Protect against out-of-range pagination
                # repeating an already-seen page.
                if len(unique) == before:
                    break

                if (
                    page_number < max_pages
                    and self.request_delay_seconds
                    > 0
                ):
                    sleep(
                        self.request_delay_seconds
                    )

        return CessiDirectoryFetch(
            pages_fetched=pages_fetched,
            companies=list(
                unique.values()
            ),
        )


def _value_after_label(
    parts: list[str],
    label: str,
) -> str | None:
    normalized_label = label.casefold()

    for index, part in enumerate(
        parts
    ):
        if (
            part.strip()
            .rstrip(":")
            .casefold()
            != normalized_label
        ):
            continue

        for candidate in parts[
            index + 1:
        ]:
            cleaned = _clean_text(
                candidate
            )

            if cleaned is None:
                continue

            lowered = cleaned.casefold()

            if lowered in {
                "email de contacto",
                "actividad",
            }:
                return None

            if any(
                lowered.startswith(
                    f"{prefix}:"
                )
                for prefix in (
                    "domicilio",
                    "ciudad",
                    "provincia",
                )
            ):
                return None

            return cleaned

    return None


def _prefixed_value(
    parts: list[str],
    label: str,
) -> str | None:
    pattern = re.compile(
        rf"^\s*{re.escape(label)}"
        r"\s*:\s*(.+?)\s*$",
        re.IGNORECASE,
    )

    for part in parts:
        match = pattern.match(part)

        if match is not None:
            return _clean_text(
                match.group(1)
            )

    return None


def _clean_text(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    cleaned = " ".join(
        value.split()
    ).strip()

    return cleaned or None
