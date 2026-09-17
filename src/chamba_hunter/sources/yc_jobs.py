from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
import json
import re
from time import sleep
from typing import Any
from urllib.parse import quote, urljoin, urlparse

import httpx

from chamba_hunter.domain.enums import WorkplaceType


YC_BASE_URL = "https://www.ycombinator.com"
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_REQUEST_DELAY_SECONDS = 0.10

_JOB_PATH_RE = re.compile(
    r"^/companies/([^/]+)/jobs/([^/?#]+)$"
)


class YcJobsParseError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class YcJobLink:
    job_id: str
    company_slug: str
    url: str


@dataclass(frozen=True, slots=True)
class YcJobPosting:
    external_id: str
    company_slug: str
    title: str
    description: str | None
    location_text: str | None
    workplace_type: WorkplaceType
    employment_type: str | None
    job_url: str
    apply_url: str | None
    published_at: datetime | None
    source_updated_at: datetime | None
    raw_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class YcCompanyJobsFetch:
    company_slug: str
    listing_url: str
    job_links_discovered: int
    details_fetched: int
    detail_failures: int
    skipped_invalid: int
    jobs: tuple[YcJobPosting, ...]


class YcJobsClient:
    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        request_delay_seconds: float = (
            DEFAULT_REQUEST_DELAY_SECONDS
        ),
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if request_delay_seconds < 0:
            raise ValueError(
                "request_delay_seconds cannot be negative."
            )

        self.timeout_seconds = timeout_seconds
        self.request_delay_seconds = request_delay_seconds
        self.transport = transport

    def fetch_company_jobs(
        self,
        company_slug: str,
    ) -> YcCompanyJobsFetch:
        slug = _clean_text(company_slug)

        if slug is None:
            raise ValueError(
                "company_slug cannot be empty."
            )

        listing_url = _company_jobs_url(slug)
        details_fetched = 0
        detail_failures = 0
        skipped_invalid = 0
        jobs: list[YcJobPosting] = []

        with httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            transport=self.transport,
            headers={
                "User-Agent": (
                    "chamba-hunter/0.2 "
                    "(public YC jobs page consumer)"
                ),
                "Accept": (
                    "text/html,application/xhtml+xml,"
                    "application/xml;q=0.9,*/*;q=0.8"
                ),
            },
        ) as client:
            response = client.get(
                listing_url
            )
            response.raise_for_status()

            links = parse_yc_jobs_listing(
                response.text,
                company_slug=slug,
                listing_url=listing_url,
            )

            for index, link in enumerate(
                links
            ):
                try:
                    detail_response = client.get(
                        link.url
                    )
                    detail_response.raise_for_status()
                    details_fetched += 1

                    jobs.append(
                        parse_yc_job_detail(
                            detail_response.text,
                            company_slug=slug,
                            job_url=str(
                                detail_response.url
                            ),
                            fallback_job_id=(
                                link.job_id
                            ),
                        )
                    )
                except httpx.HTTPError:
                    detail_failures += 1
                except (
                    YcJobsParseError,
                    ValueError,
                ):
                    skipped_invalid += 1

                if index < len(links) - 1:
                    self._delay()

        return YcCompanyJobsFetch(
            company_slug=slug,
            listing_url=listing_url,
            job_links_discovered=len(links),
            details_fetched=details_fetched,
            detail_failures=detail_failures,
            skipped_invalid=skipped_invalid,
            jobs=tuple(jobs),
        )

    def _delay(self) -> None:
        if self.request_delay_seconds > 0:
            sleep(
                self.request_delay_seconds
            )


def parse_yc_jobs_listing(
    html: str,
    *,
    company_slug: str,
    listing_url: str,
) -> tuple[YcJobLink, ...]:
    parser = _YcHtmlParser()
    parser.feed(html)

    seen_ids: set[str] = set()
    links: list[YcJobLink] = []

    for anchor in parser.anchors:
        href = _clean_text(anchor.href)

        if href is None:
            continue

        absolute_url = urljoin(
            listing_url,
            href,
        )
        match = _job_path_match(
            absolute_url
        )

        if match is None:
            continue

        slug, job_id = match

        if slug != company_slug:
            continue

        if job_id in seen_ids:
            continue

        seen_ids.add(job_id)
        links.append(
            YcJobLink(
                job_id=job_id,
                company_slug=slug,
                url=absolute_url,
            )
        )

    if links:
        return tuple(links)

    if _looks_like_empty_jobs_page(
        parser.visible_text
    ):
        return ()

    raise YcJobsParseError(
        "YC company jobs page did not expose "
        "job links or an explicit empty-jobs state."
    )


def parse_yc_job_detail(
    html: str,
    *,
    company_slug: str,
    job_url: str,
    fallback_job_id: str | None = None,
) -> YcJobPosting:
    parser = _YcHtmlParser()
    parser.feed(html)

    parsed_job_id = _job_id_from_url(
        job_url
    )
    external_id = (
        _clean_text(parsed_job_id)
        or _clean_text(fallback_job_id)
    )

    if external_id is None:
        raise YcJobsParseError(
            "YC job detail URL does not contain "
            "a stable job id."
        )

    structured = _find_job_posting(
        parser.json_ld_payloads
    )

    title = _clean_text(
        _structured_string(
            structured,
            "title",
        )
    )

    if title is None:
        title = _clean_title_from_meta(
            parser.meta.get("og:title")
            or parser.title
        )

    if title is None:
        raise YcJobsParseError(
            "YC job detail is missing a title."
        )

    description = _html_to_text(
        _structured_string(
            structured,
            "description",
        )
    )

    if description is None:
        description = _clean_text(
            parser.meta.get("description")
            or parser.meta.get(
                "og:description"
            )
        )

    structured_location_text = (
        _location_text(structured)
        if structured is not None
        else None
    )
    location_source = (
        "json_ld"
        if structured_location_text is not None
        else None
    )

    location_text = structured_location_text

    if location_text is None:
        location_text = (
            _visible_header_location(
                parser.visible_parts,
                title=title,
            )
        )
        if location_text is not None:
            location_source = "visible_header"

    workplace_type = _workplace_type(
        structured=structured,
        location_text=location_text,
    )

    employment_type = _employment_type(
        structured
    )

    published_at = _parse_datetime(
        _structured_string(
            structured,
            "datePosted",
        )
    )
    source_updated_at = _parse_datetime(
        _structured_string(
            structured,
            "dateModified",
        )
    )

    apply_url = _apply_url_from_anchors(
        parser.anchors,
        job_url=job_url,
    )

    raw_payload: dict[str, Any] = {
        "source": "yc_public_jobs",
        "company_slug": company_slug,
        "job_id": external_id,
        "job_url": job_url,
        "json_ld": structured,
    }

    if location_source is not None:
        raw_payload["location_source"] = (
            location_source
        )

    if parser.meta:
        raw_payload["meta"] = dict(
            parser.meta
        )

    return YcJobPosting(
        external_id=external_id,
        company_slug=company_slug,
        title=title,
        description=description,
        location_text=location_text,
        workplace_type=workplace_type,
        employment_type=employment_type,
        job_url=job_url,
        apply_url=apply_url,
        published_at=published_at,
        source_updated_at=source_updated_at,
        raw_payload=raw_payload,
    )


def _company_jobs_url(
    slug: str,
) -> str:
    return (
        f"{YC_BASE_URL}/companies/"
        f"{quote(slug)}/jobs"
    )


def _job_path_match(
    url: str,
) -> tuple[str, str] | None:
    parsed = urlparse(url)
    match = _JOB_PATH_RE.match(
        parsed.path
    )

    if match is None:
        return None

    return (
        match.group(1),
        match.group(2),
    )


def _job_id_from_url(
    url: str,
) -> str | None:
    match = _job_path_match(url)

    if match is None:
        return None

    return match[1]


def _looks_like_empty_jobs_page(
    text: str,
) -> bool:
    normalized = text.casefold()

    empty_markers = (
        "no jobs",
        "not currently hiring",
        "no open positions",
        "no open roles",
    )

    return any(
        marker in normalized
        for marker in empty_markers
    )


def _find_job_posting(
    payloads: list[Any],
) -> dict[str, Any] | None:
    for payload in payloads:
        found = _find_job_posting_in_value(
            payload
        )

        if found is not None:
            return found

    return None


def _find_job_posting_in_value(
    value: Any,
) -> dict[str, Any] | None:
    if isinstance(value, list):
        for item in value:
            found = (
                _find_job_posting_in_value(
                    item
                )
            )

            if found is not None:
                return found

    if isinstance(value, dict):
        raw_type = value.get("@type")
        types = (
            raw_type
            if isinstance(raw_type, list)
            else [raw_type]
        )

        if any(
            str(item).casefold()
            == "jobposting"
            for item in types
            if item is not None
        ):
            return value

        graph = value.get("@graph")

        if graph is not None:
            return _find_job_posting_in_value(
                graph
            )

    return None


def _structured_string(
    structured: dict[str, Any] | None,
    key: str,
) -> str | None:
    if structured is None:
        return None

    value = structured.get(key)

    if isinstance(value, str):
        return value

    return None


def _location_text(
    structured: dict[str, Any] | None,
) -> str | None:
    if structured is None:
        return None

    parts: list[str] = []

    _extend_location_parts(
        parts,
        structured.get("jobLocation"),
    )
    _extend_location_parts(
        parts,
        structured.get(
            "applicantLocationRequirements"
        ),
    )

    return _join_unique(parts)


def _extend_location_parts(
    parts: list[str],
    value: Any,
) -> None:
    if value is None:
        return

    if isinstance(value, list):
        for item in value:
            _extend_location_parts(
                parts,
                item,
            )
        return

    if isinstance(value, str):
        cleaned = _clean_text(value)

        if cleaned is not None:
            parts.append(cleaned)
        return

    if not isinstance(value, dict):
        return

    for key in (
        "name",
        "addressLocality",
        "addressRegion",
        "addressCountry",
    ):
        cleaned = _clean_text(
            value.get(key)
        )

        if cleaned is not None:
            parts.append(cleaned)

    address = value.get("address")

    if isinstance(address, dict):
        _extend_location_parts(
            parts,
            address,
        )


def _workplace_type(
    *,
    structured: dict[str, Any] | None,
    location_text: str | None,
) -> WorkplaceType:
    if structured is not None:
        job_location_type = _clean_text(
            structured.get(
                "jobLocationType"
            )
        )

        if (
            job_location_type is not None
            and job_location_type.casefold()
            == "telecommute"
        ):
            return WorkplaceType.REMOTE

    location = (
        location_text.casefold()
        if location_text is not None
        else ""
    )

    if "remote" in location:
        return WorkplaceType.REMOTE

    if "hybrid" in location:
        return WorkplaceType.HYBRID

    if (
        "onsite" in location
        or "on-site" in location
    ):
        return WorkplaceType.ONSITE

    return WorkplaceType.UNKNOWN


def _visible_header_location(
    visible_parts: list[str],
    *,
    title: str,
) -> str | None:
    title_key = _visible_header_key(
        title
    )

    if title_key is None:
        return None

    for index, part in enumerate(
        visible_parts
    ):
        if _visible_header_key(part) != title_key:
            continue

        location_parts: list[str] = []

        for candidate in visible_parts[
            index + 1 : index + 7
        ]:
            candidate_key = (
                _visible_header_key(
                    candidate
                )
            )

            if candidate_key == "job type":
                return _join_unique(
                    location_parts
                )

            for cleaned in (
                _clean_visible_location_parts(
                    candidate
                )
            ):
                location_parts.append(
                    cleaned
                )

    return None


def _visible_header_key(
    value: str,
) -> str | None:
    cleaned = _clean_text(value)

    if cleaned is None:
        return None

    return _strip_cosmetic_marks(
        cleaned
    ).casefold()


def _clean_visible_location_parts(
    value: str,
) -> tuple[str, ...]:
    cleaned = _clean_text(value)

    if cleaned is None:
        return ()

    cleaned = _strip_cosmetic_marks(
        cleaned
    )

    if not cleaned:
        return ()

    parts: list[str] = []

    for segment in re.split(
        r"[•·]+",
        cleaned,
    ):
        segment = _strip_cosmetic_marks(
            segment
        )

        if (
            segment
            and not _looks_like_compensation(
                segment
            )
        ):
            parts.append(
                segment
            )

    return tuple(parts)


def _looks_like_compensation(
    value: str,
) -> bool:
    compact = " ".join(
        value.split()
    )

    return (
        re.fullmatch(
            (
                r"[$€£]\s*\d[\d,]*(?:\.\d+)?K?"
                r"\s*[-–—]\s*"
                r"[$€£]\s*\d[\d,]*(?:\.\d+)?K?"
            ),
            compact,
            flags=re.IGNORECASE,
        )
        is not None
    )


def _strip_cosmetic_marks(
    value: str,
) -> str:
    return value.strip(
        " \t\r\n•·›»→-–—"
    )


def _employment_type(
    structured: dict[str, Any] | None,
) -> str | None:
    if structured is None:
        return None

    value = structured.get(
        "employmentType"
    )

    if isinstance(value, str):
        return _clean_text(value)

    if isinstance(value, list):
        return _join_unique(
            [
                item
                for item in value
                if isinstance(item, str)
            ]
        )

    return None


def _apply_url_from_anchors(
    anchors: list["_Anchor"],
    *,
    job_url: str,
) -> str | None:
    for anchor in anchors:
        if not _is_role_specific_apply_text(
            anchor.text
        ):
            continue

        href = _clean_text(anchor.href)

        if href is None:
            continue

        url = urljoin(
            job_url,
            href,
        )

        if (
            url != job_url
            and not _is_generic_yc_apply_url(
                url
            )
        ):
            return url

    return None


def _is_role_specific_apply_text(
    value: str,
) -> bool:
    cleaned = _clean_text(value)

    if cleaned is None:
        return False

    normalized = re.sub(
        r"[›»→]+",
        "",
        cleaned,
    )
    normalized = " ".join(
        normalized.split()
    ).casefold()

    return normalized in {
        "apply to role",
        "apply for this role",
        "apply for this job",
    }


def _is_generic_yc_apply_url(
    url: str,
) -> bool:
    parsed = urlparse(url)
    host = (
        parsed.hostname.casefold()
        if parsed.hostname is not None
        else ""
    )

    return (
        host in {
            "ycombinator.com",
            "www.ycombinator.com",
        }
        and parsed.path.rstrip("/")
        == "/apply"
    )


def _parse_datetime(
    value: str | None,
) -> datetime | None:
    cleaned = _clean_text(value)

    if cleaned is None:
        return None

    try:
        parsed = datetime.fromisoformat(
            cleaned.replace("Z", "+00:00")
        )
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=UTC
        )

    return parsed.astimezone(UTC)


def _html_to_text(
    value: str | None,
) -> str | None:
    cleaned = _clean_text(value)

    if cleaned is None:
        return None

    parser = _TextExtractor()
    parser.feed(cleaned)

    text = " ".join(parser.parts)

    return _clean_text(text)


def _clean_title_from_meta(
    value: str | None,
) -> str | None:
    cleaned = _clean_text(value)

    if cleaned is None:
        return None

    for separator in (
        " at ",
        " | ",
        " - ",
    ):
        if separator in cleaned:
            first = cleaned.split(
                separator,
                1,
            )[0].strip()

            if first:
                return first

    return cleaned


def _join_unique(
    values: list[str],
) -> str | None:
    parts: list[str] = []
    seen: set[str] = set()

    for value in values:
        cleaned = _clean_text(value)

        if cleaned is None:
            continue

        key = cleaned.casefold()

        if key in seen:
            continue

        seen.add(key)
        parts.append(cleaned)

    return (
        "; ".join(parts)
        if parts
        else None
    )


def _clean_text(
    value: Any,
) -> str | None:
    if not isinstance(value, str):
        return None

    cleaned = " ".join(
        value.split()
    ).strip()

    return cleaned or None


@dataclass(slots=True)
class _Anchor:
    href: str | None
    text: str


class _YcHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(
            convert_charrefs=True
        )
        self.anchors: list[_Anchor] = []
        self.json_ld_payloads: list[Any] = []
        self.meta: dict[str, str] = {}
        self.title: str | None = None
        self.visible_parts: list[str] = []
        self._anchor_href: str | None = None
        self._anchor_parts: list[str] = []
        self._script_type: str | None = None
        self._script_parts: list[str] = []
        self._in_title = False
        self._title_parts: list[str] = []

    @property
    def visible_text(self) -> str:
        return " ".join(
            self.visible_parts
        )

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = dict(attrs)
        normalized_tag = tag.casefold()

        if normalized_tag == "a":
            self._anchor_href = (
                attributes.get("href")
            )
            self._anchor_parts = []

        elif normalized_tag == "script":
            self._script_type = (
                attributes.get("type")
                or ""
            ).casefold()
            self._script_parts = []

        elif normalized_tag == "meta":
            key = (
                attributes.get("property")
                or attributes.get("name")
            )
            content = attributes.get(
                "content"
            )

            cleaned_key = _clean_text(
                key
            )
            cleaned_content = _clean_text(
                content
            )

            if (
                cleaned_key is not None
                and cleaned_content is not None
            ):
                self.meta[
                    cleaned_key.casefold()
                ] = cleaned_content

        elif normalized_tag == "title":
            self._in_title = True
            self._title_parts = []

    def handle_endtag(
        self,
        tag: str,
    ) -> None:
        normalized_tag = tag.casefold()

        if (
            normalized_tag == "a"
            and self._anchor_href is not None
        ):
            self.anchors.append(
                _Anchor(
                    href=self._anchor_href,
                    text=" ".join(
                        self._anchor_parts
                    ),
                )
            )
            self._anchor_href = None
            self._anchor_parts = []

        elif normalized_tag == "script":
            if (
                self._script_type
                == "application/ld+json"
            ):
                raw = "".join(
                    self._script_parts
                ).strip()

                if raw:
                    try:
                        self.json_ld_payloads.append(
                            json.loads(raw)
                        )
                    except json.JSONDecodeError:
                        pass

            self._script_type = None
            self._script_parts = []

        elif normalized_tag == "title":
            self.title = _clean_text(
                " ".join(
                    self._title_parts
                )
            )
            self._in_title = False
            self._title_parts = []

    def handle_data(
        self,
        data: str,
    ) -> None:
        cleaned = _clean_text(data)

        if cleaned is None:
            return

        if self._anchor_href is not None:
            self._anchor_parts.append(
                cleaned
            )

        if self._script_type is not None:
            self._script_parts.append(data)
            return

        if self._in_title:
            self._title_parts.append(
                cleaned
            )
            return

        self.visible_parts.append(
            cleaned
        )


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(
            convert_charrefs=True
        )
        self.parts: list[str] = []

    def handle_data(
        self,
        data: str,
    ) -> None:
        cleaned = _clean_text(data)

        if cleaned is not None:
            self.parts.append(cleaned)
