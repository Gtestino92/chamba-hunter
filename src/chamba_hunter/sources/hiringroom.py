from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
)
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
import re
from typing import Any
import unicodedata
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field


TENANT_PATTERN = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?$"
)

VACANCY_PATH_PATTERN = re.compile(
    r"^/jobs/get_vacancy/([a-fA-F0-9]{24})/?$"
)

TYPE_PORTAL_PATTERN = re.compile(
    r"""const\s+typePortal\s*=\s*["']([^"']+)["']"""
)

ALIAS_ACCOUNT_PATTERN = re.compile(
    r"""const\s+aliasAccount\s*=\s*["']([^"']+)["']"""
)

MICROSITE_ID_PATTERN = re.compile(
    r"""microSiteId\s*=\s*["']([^"']*)["']"""
)

DESCRIPTION_END_MARKER = (
    "<!-- La descripción es obligatoria, "
    "no hace falta validar aquí -->"
)

DETAILS_START_PATTERN = re.compile(
    r"""<div\s+class=["'][^"']*\bmain__details\b""",
    re.IGNORECASE,
)

OG_URL_PATTERN = re.compile(
    r"""<meta\s+property=["']og:url["'][^>]+content=["']([^"']+)["']""",
    re.IGNORECASE,
)

OG_TITLE_PATTERN = re.compile(
    r"""<meta\s+property=["']og:title["'][^>]+content=["']([^"']*)["']""",
    re.IGNORECASE,
)

OG_DESCRIPTION_PATTERN = re.compile(
    r"""<meta\s+property=["']og:description["'][^>]+content=["']([^"']*)["']""",
    re.IGNORECASE | re.DOTALL,
)

APPLY_URL_PATTERN = re.compile(
    r"""href=["'](https://hiringroom\.com/jobs/get_vacancy/"""
    r"""([a-fA-F0-9]{24})/candidates/new)["']""",
    re.IGNORECASE,
)

TAG_PATTERN = re.compile(
    r"""<span\s+class=["'][^"']*\bmain__tags-item\b[^"']*["'][^>]*>"""
    r"""(.*?)</span>""",
    re.IGNORECASE | re.DOTALL,
)


class HiringRoomVacanciesData(BaseModel):
    model_config = ConfigDict(
        extra="allow"
    )

    html_content: str = Field(
        alias="htmlContent"
    )

    total_vacancies: int

    pagination: str | None = None

    pagination_label: str | None = Field(
        default=None,
        alias="paginationLabel",
    )

    filters_options: Any = Field(
        default=None,
        alias="filtersOptions",
    )


class HiringRoomVacanciesResponse(BaseModel):
    model_config = ConfigDict(
        extra="allow"
    )

    result: str
    data: HiringRoomVacanciesData


@dataclass(frozen=True, slots=True)
class HiringRoomBoardConfig:
    type_portal: str
    alias_account: str
    microsite_id: str | None


@dataclass(frozen=True, slots=True)
class HiringRoomJobCard:
    external_id: str
    title: str
    location_text: str | None
    area_text: str | None
    tags: tuple[str, ...]
    published_relative: str | None


@dataclass(frozen=True, slots=True)
class HiringRoomJobDetail:
    card: HiringRoomJobCard
    job_url: str
    apply_url: str
    description: str | None
    detail_tags: tuple[str, ...]
    raw_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class HiringRoomJobsFetch:
    http_status: int
    total: int
    jobs: list[HiringRoomJobDetail]


@dataclass(slots=True)
class _CaptureFrame:
    tag: str
    kind: str
    text: list[str]


@dataclass(slots=True)
class _MutableCard:
    external_id: str
    title: str | None = None
    location_text: str | None = None
    area_text: str | None = None
    tags: list[str] | None = None
    published_relative: str | None = None

    def __post_init__(self) -> None:
        if self.tags is None:
            self.tags = []


class _HiringRoomBoardParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(
            convert_charrefs=True
        )
        self.cards: list[
            HiringRoomJobCard
        ] = []
        self._card: _MutableCard | None = None
        self._frames: list[
            _CaptureFrame
        ] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[
            tuple[str, str | None]
        ],
    ) -> None:
        attributes = {
            key.casefold(): value
            for key, value in attrs
        }
        normalized_tag = tag.casefold()

        if (
            normalized_tag == "a"
            and self._card is None
        ):
            href = attributes.get("href")

            if href:
                try:
                    path = urlsplit(
                        href
                    ).path
                except ValueError:
                    path = ""

                match = (
                    VACANCY_PATH_PATTERN
                    .fullmatch(path)
                )

                if match is not None:
                    self._card = (
                        _MutableCard(
                            external_id=(
                                match.group(1)
                                .casefold()
                            )
                        )
                    )
            return

        if self._card is None:
            return

        class_value = (
            attributes.get("class")
            or ""
        )
        classes = set(
            class_value.split()
        )

        if (
            normalized_tag == "h4"
            and "name__vacancy"
            in classes
        ):
            self._frames.append(
                _CaptureFrame(
                    tag="h4",
                    kind="title",
                    text=[],
                )
            )
            return

        if normalized_tag == "p":
            if "vacancy-time" in classes:
                kind = "published_relative"
            else:
                kind = "paragraph"

            self._frames.append(
                _CaptureFrame(
                    tag="p",
                    kind=kind,
                    text=[],
                )
            )
            return

        if (
            normalized_tag == "span"
            and "tag-vacancy"
            in classes
        ):
            self._frames.append(
                _CaptureFrame(
                    tag="span",
                    kind="tag",
                    text=[],
                )
            )
            return

        if normalized_tag == "i":
            icon_classes = classes

            for frame in reversed(
                self._frames
            ):
                if frame.tag != "p":
                    continue

                if (
                    "hr-Location-pin"
                    in icon_classes
                ):
                    frame.kind = "location"
                elif (
                    "hr-Work-area"
                    in icon_classes
                ):
                    frame.kind = "area"
                break

    def handle_data(
        self,
        data: str,
    ) -> None:
        if self._card is None:
            return

        for frame in self._frames:
            frame.text.append(data)

    def handle_endtag(
        self,
        tag: str,
    ) -> None:
        normalized_tag = tag.casefold()

        if self._card is None:
            return

        if (
            self._frames
            and self._frames[-1].tag
            == normalized_tag
        ):
            frame = self._frames.pop()
            self._apply_frame(frame)

        if normalized_tag == "a":
            self._finish_card()

    def _apply_frame(
        self,
        frame: _CaptureFrame,
    ) -> None:
        if self._card is None:
            return

        value = _clean_visible_text(
            " ".join(frame.text)
        )

        if value is None:
            return

        if frame.kind == "title":
            self._card.title = value
        elif frame.kind == "location":
            self._card.location_text = (
                value
            )
        elif frame.kind == "area":
            self._card.area_text = value
        elif (
            frame.kind
            == "published_relative"
        ):
            if (
                self._card
                .published_relative
                is None
            ):
                self._card.published_relative = (
                    value
                )
        elif frame.kind == "tag":
            if value not in self._card.tags:
                self._card.tags.append(
                    value
                )

    def _finish_card(self) -> None:
        card = self._card
        self._card = None
        self._frames.clear()

        if card is None:
            return

        title = _clean_visible_text(
            card.title
        )

        if title is None:
            raise ValueError(
                "Hiring Room returned a "
                "vacancy card without a title "
                f"for id {card.external_id}."
            )

        self.cards.append(
            HiringRoomJobCard(
                external_id=(
                    card.external_id
                ),
                title=title,
                location_text=(
                    _clean_visible_text(
                        card.location_text
                    )
                ),
                area_text=(
                    _clean_visible_text(
                        card.area_text
                    )
                ),
                tags=tuple(
                    card.tags or []
                ),
                published_relative=(
                    _clean_visible_text(
                        card
                        .published_relative
                    )
                ),
            )
        )


class _PlainTextParser(HTMLParser):
    BLOCK_TAGS = {
        "br",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "ol",
        "p",
        "ul",
    }

    def __init__(self) -> None:
        super().__init__(
            convert_charrefs=True
        )
        self.parts: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[
            tuple[str, str | None]
        ],
    ) -> None:
        if tag.casefold() == "li":
            self.parts.append("\n- ")

    def handle_endtag(
        self,
        tag: str,
    ) -> None:
        if tag.casefold() in (
            self.BLOCK_TAGS
            - {"li"}
        ):
            self.parts.append("\n")

    def handle_data(
        self,
        data: str,
    ) -> None:
        self.parts.append(data)

    def text(self) -> str | None:
        value = "\n".join(
            line.strip()
            for line in (
                " ".join(self.parts)
                .splitlines()
            )
            if line.strip()
        )

        value = re.sub(
            r"[ \t]+",
            " ",
            value,
        )

        value = re.sub(
            r"\n{3,}",
            "\n\n",
            value,
        ).strip()

        return value or None


class HiringRoomClient:
    def __init__(
        self,
        timeout_seconds: float = 20.0,
        max_detail_workers: int = 6,
    ) -> None:
        if max_detail_workers < 1:
            raise ValueError(
                "max_detail_workers must "
                "be at least 1."
            )

        self.timeout_seconds = (
            timeout_seconds
        )
        self.max_detail_workers = (
            max_detail_workers
        )

    def fetch_jobs(
        self,
        tenant_subdomain: str,
    ) -> HiringRoomJobsFetch:
        tenant = _clean_tenant(
            tenant_subdomain
        )
        base_url = (
            f"https://{tenant}"
            ".hiringroom.com"
        )
        board_url = f"{base_url}/jobs"

        with httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            limits=httpx.Limits(
                max_connections=(
                    self.max_detail_workers
                ),
                max_keepalive_connections=(
                    self.max_detail_workers
                ),
            ),
            headers={
                "User-Agent": (
                    "chamba-hunter/0.1"
                ),
                "Accept": (
                    "text/html,"
                    "application/json;q=0.9,"
                    "*/*;q=0.8"
                ),
            },
        ) as client:
            board_response = client.get(
                board_url
            )
            board_response.raise_for_status()

            final_host = (
                urlsplit(
                    str(
                        board_response.url
                    )
                ).hostname
                or ""
            ).casefold()

            expected_host = (
                f"{tenant.casefold()}"
                ".hiringroom.com"
            )

            if final_host != expected_host:
                raise ValueError(
                    "Hiring Room board "
                    "redirected to an "
                    "unexpected host: "
                    f"{final_host}"
                )

            config = _board_config(
                board_response.text
            )

            if (
                config.alias_account
                .casefold()
                != tenant.casefold()
            ):
                raise ValueError(
                    "Hiring Room aliasAccount "
                    "does not match tenant: "
                    f"tenant={tenant}, "
                    "aliasAccount="
                    f"{config.alias_account}"
                )

            first_page = (
                self._fetch_page(
                    client=client,
                    base_url=base_url,
                    board_url=board_url,
                    config=config,
                    page=1,
                )
            )

            total = (
                first_page
                .data.total_vacancies
            )

            if total < 0:
                raise ValueError(
                    "Hiring Room returned a "
                    "negative total_vacancies."
                )

            cards = _parse_cards(
                first_page.data.html_content
            )

            seen_ids = {
                card.external_id
                for card in cards
            }

            if len(seen_ids) != len(cards):
                raise ValueError(
                    "Hiring Room returned "
                    "duplicate vacancy ids "
                    "on page 1."
                )

            page = 2

            while len(cards) < total:
                page_payload = (
                    self._fetch_page(
                        client=client,
                        base_url=base_url,
                        board_url=board_url,
                        config=config,
                        page=page,
                    )
                )

                if (
                    page_payload
                    .data.total_vacancies
                    != total
                ):
                    raise ValueError(
                        "Hiring Room board "
                        "changed total_vacancies "
                        "during pagination: "
                        f"expected={total}, "
                        "received="
                        f"{page_payload.data.total_vacancies}"
                    )

                page_cards = _parse_cards(
                    page_payload
                    .data.html_content
                )

                if not page_cards:
                    raise ValueError(
                        "Hiring Room returned "
                        "an empty page before "
                        "the declared total was "
                        "reached: "
                        f"page={page}, "
                        f"collected={len(cards)}, "
                        f"total={total}"
                    )

                for card in page_cards:
                    if (
                        card.external_id
                        in seen_ids
                    ):
                        raise ValueError(
                            "Hiring Room returned "
                            "an overlapping vacancy "
                            "id across pages: "
                            f"{card.external_id}"
                        )

                    seen_ids.add(
                        card.external_id
                    )
                    cards.append(card)

                if page > total + 1:
                    raise ValueError(
                        "Hiring Room pagination "
                        "did not converge."
                    )

                page += 1

            if len(cards) != total:
                raise ValueError(
                    "Hiring Room returned an "
                    "incomplete board snapshot: "
                    f"total_vacancies={total}, "
                    f"postings={len(cards)}."
                )

            jobs = self._fetch_details(
                client=client,
                base_url=base_url,
                tenant=tenant,
                cards=cards,
            )

        return HiringRoomJobsFetch(
            http_status=(
                first_page.http_status
            ),
            total=total,
            jobs=jobs,
        )

    def _fetch_details(
        self,
        client: httpx.Client,
        base_url: str,
        tenant: str,
        cards: list[
            HiringRoomJobCard
        ],
    ) -> list[HiringRoomJobDetail]:
        if not cards:
            return []

        worker_count = min(
            self.max_detail_workers,
            len(cards),
        )

        details: list[
            HiringRoomJobDetail | None
        ] = [
            None
            for _ in cards
        ]

        with ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix=(
                "hiringroom-detail"
            ),
        ) as executor:
            future_indexes = {
                executor.submit(
                    self._fetch_detail,
                    client=client,
                    base_url=base_url,
                    tenant=tenant,
                    card=card,
                ): index
                for index, card
                in enumerate(cards)
            }

            try:
                for future in as_completed(
                    future_indexes
                ):
                    index = (
                        future_indexes[
                            future
                        ]
                    )

                    details[index] = (
                        future.result()
                    )

            except Exception:
                for pending in (
                    future_indexes
                ):
                    pending.cancel()

                raise

        if any(
            detail is None
            for detail in details
        ):
            raise RuntimeError(
                "Hiring Room detail fetch "
                "completed without a full "
                "snapshot."
            )

        return [
            detail
            for detail in details
            if detail is not None
        ]

    @staticmethod
    def _fetch_page(
        client: httpx.Client,
        base_url: str,
        board_url: str,
        config: HiringRoomBoardConfig,
        page: int,
    ) -> "_PageFetch":
        data = {
            "selectedPage": str(page),
            "typePortal": (
                config.type_portal
            ),
        }

        if (
            config.type_portal
            == "microsite"
        ):
            if not config.microsite_id:
                raise ValueError(
                    "Hiring Room microsite "
                    "board is missing "
                    "microSiteId."
                )

            data["microSiteId"] = (
                config.microsite_id
            )

        response = client.post(
            f"{base_url}/jobs/"
            f"getVacanciesForPortal/{page}",
            data=data,
            headers={
                "X-Requested-With": (
                    "XMLHttpRequest"
                ),
                "Referer": board_url,
            },
        )
        response.raise_for_status()

        try:
            raw_payload = response.json()
        except ValueError as error:
            raise ValueError(
                "Hiring Room vacancies "
                "endpoint did not return "
                "valid JSON."
            ) from error

        payload = (
            HiringRoomVacanciesResponse
            .model_validate(raw_payload)
        )

        if payload.result != "success":
            raise ValueError(
                "Hiring Room vacancies "
                "endpoint returned "
                f"result={payload.result!r}."
            )

        return _PageFetch(
            http_status=(
                response.status_code
            ),
            data=payload.data,
        )

    @staticmethod
    def _fetch_detail(
        client: httpx.Client,
        base_url: str,
        tenant: str,
        card: HiringRoomJobCard,
    ) -> HiringRoomJobDetail:
        job_url = (
            f"{base_url}/jobs/"
            "get_vacancy/"
            f"{card.external_id}"
        )

        response = client.get(job_url)
        response.raise_for_status()

        final_url = str(response.url)

        final_host = (
            urlsplit(final_url)
            .hostname
            or ""
        ).casefold()

        expected_host = (
            f"{tenant.casefold()}"
            ".hiringroom.com"
        )

        if final_host != expected_host:
            raise ValueError(
                "Hiring Room detail "
                "redirected to an "
                "unexpected host for "
                f"job {card.external_id}: "
                f"{final_host}"
            )

        final_path = (
            urlsplit(final_url)
            .path
            .rstrip("/")
        )

        expected_path = (
            "/jobs/get_vacancy/"
            f"{card.external_id}"
        )

        if final_path != expected_path:
            raise ValueError(
                "Hiring Room detail URL "
                "does not match requested "
                "vacancy id: "
                f"requested={card.external_id}, "
                f"url={final_url}"
            )

        html = response.text

        og_url = _extract_match(
            OG_URL_PATTERN,
            html,
        )

        if og_url is not None:
            try:
                og_path = (
                    urlsplit(
                        unescape(og_url)
                    )
                    .path
                    .rstrip("/")
                )
            except ValueError as error:
                raise ValueError(
                    "Hiring Room detail "
                    "returned an invalid "
                    "og:url for job "
                    f"{card.external_id}."
                ) from error

            if og_path != expected_path:
                raise ValueError(
                    "Hiring Room detail "
                    "og:url does not match "
                    "requested vacancy id: "
                    f"requested={card.external_id}, "
                    f"og_url={og_url}"
                )

        apply_match = (
            APPLY_URL_PATTERN.search(html)
        )

        if (
            apply_match is None
            or apply_match.group(2)
            .casefold()
            != card.external_id
        ):
            raise ValueError(
                "Hiring Room detail did "
                "not expose the expected "
                "public apply URL for "
                f"job {card.external_id}."
            )

        apply_url = unescape(
            apply_match.group(1)
        )

        description = (
            _detail_description(html)
        )

        og_title = _clean_visible_text(
            unescape(
                _extract_match(
                    OG_TITLE_PATTERN,
                    html,
                )
                or ""
            )
        )

        og_description = (
            _clean_visible_text(
                unescape(
                    _extract_match(
                        OG_DESCRIPTION_PATTERN,
                        html,
                    )
                    or ""
                )
            )
        )

        detail_tags = tuple(
            dict.fromkeys(
                value
                for match
                in TAG_PATTERN.findall(
                    html
                )
                if (
                    value
                    := _html_to_text(
                        match
                    )
                )
            )
        )

        raw_payload = {
            "tenant": tenant,
            "external_id": (
                card.external_id
            ),
            "board": {
                "title": card.title,
                "location_text": (
                    card.location_text
                ),
                "area_text": (
                    card.area_text
                ),
                "tags": list(
                    card.tags
                ),
                "published_relative": (
                    card
                    .published_relative
                ),
            },
            "detail": {
                "job_url": job_url,
                "apply_url": apply_url,
                "og_title": og_title,
                "og_description": (
                    og_description
                ),
                "description": (
                    description
                ),
                "tags": list(
                    detail_tags
                ),
            },
        }

        return HiringRoomJobDetail(
            card=card,
            job_url=job_url,
            apply_url=apply_url,
            description=description,
            detail_tags=detail_tags,
            raw_payload=raw_payload,
        )


@dataclass(frozen=True, slots=True)
class _PageFetch:
    http_status: int
    data: HiringRoomVacanciesData


def _board_config(
    html: str,
) -> HiringRoomBoardConfig:
    type_match = (
        TYPE_PORTAL_PATTERN.search(html)
    )
    alias_match = (
        ALIAS_ACCOUNT_PATTERN.search(
            html
        )
    )

    if type_match is None:
        raise ValueError(
            "Hiring Room board did not "
            "expose typePortal."
        )

    if alias_match is None:
        raise ValueError(
            "Hiring Room board did not "
            "expose aliasAccount."
        )

    type_portal = (
        type_match.group(1)
        .strip()
        .casefold()
    )

    if type_portal not in {
        "external",
        "microsite",
    }:
        raise ValueError(
            "Unsupported Hiring Room "
            "typePortal: "
            f"{type_portal}"
        )

    microsite_id: str | None = None

    if type_portal == "microsite":
        matches = (
            MICROSITE_ID_PATTERN
            .findall(html)
        )

        for value in reversed(matches):
            cleaned = value.strip()

            if cleaned:
                microsite_id = cleaned
                break

    return HiringRoomBoardConfig(
        type_portal=type_portal,
        alias_account=(
            alias_match.group(1).strip()
        ),
        microsite_id=microsite_id,
    )


def _parse_cards(
    html: str,
) -> list[HiringRoomJobCard]:
    parser = _HiringRoomBoardParser()
    parser.feed(html)
    parser.close()
    return parser.cards


def _detail_description(
    html: str,
) -> str | None:
    marker_index = html.find(
        DESCRIPTION_END_MARKER
    )

    if marker_index < 0:
        return _clean_visible_text(
            unescape(
                _extract_match(
                    OG_DESCRIPTION_PATTERN,
                    html,
                )
                or ""
            )
        )

    start_marker = (
        '<p class="hrc-fs-14 '
        'm-0 hrc-black">'
    )

    start_index = html.rfind(
        start_marker,
        0,
        marker_index,
    )

    if start_index < 0:
        return _clean_visible_text(
            unescape(
                _extract_match(
                    OG_DESCRIPTION_PATTERN,
                    html,
                )
                or ""
            )
        )

    details_match = (
        DETAILS_START_PATTERN.search(
            html,
            marker_index,
        )
    )

    end_index = (
        details_match.start()
        if details_match is not None
        else marker_index
        + len(
            DESCRIPTION_END_MARKER
        )
    )

    fragment = html[
        start_index:end_index
    ]

    return _html_to_text(fragment)


def _html_to_text(
    html: str,
) -> str | None:
    parser = _PlainTextParser()
    parser.feed(html)
    parser.close()
    return parser.text()


def _extract_match(
    pattern: re.Pattern[str],
    value: str,
) -> str | None:
    match = pattern.search(value)

    if match is None:
        return None

    return match.group(1)


def _clean_visible_text(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    cleaned = unescape(value)

    cleaned = re.sub(
        r"\s+",
        " ",
        cleaned,
    ).strip()

    return cleaned or None


def normalize_label(
    value: str,
) -> str:
    decomposed = unicodedata.normalize(
        "NFKD",
        value,
    )

    return "".join(
        character
        for character in decomposed
        if not unicodedata.combining(
            character
        )
    ).casefold().strip()


def _clean_tenant(
    value: str,
) -> str:
    cleaned = value.strip()

    if not cleaned:
        raise ValueError(
            "Hiring Room tenant "
            "subdomain cannot be empty."
        )

    if TENANT_PATTERN.fullmatch(
        cleaned
    ) is None:
        raise ValueError(
            "Invalid Hiring Room tenant "
            f"subdomain: {value}"
        )

    return cleaned
