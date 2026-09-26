from __future__ import annotations

from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
)
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from html import unescape
from html.parser import HTMLParser
import json
import re
import unicodedata
from typing import Any
from urllib.parse import (
    urljoin,
    urlparse,
    urlunparse,
)

import httpx


REMOTECO_BASE_URL = "https://remote.co"

REMOTECO_CATEGORY_URLS = (
    "https://remote.co/remote-jobs/back-end-developer",
    "https://remote.co/remote-jobs/java-developer",
    "https://remote.co/remote-jobs/software-engineer",
    "https://remote.co/remote-jobs/full-stack-developer",
)

DEFAULT_REMOTECO_MAX_PAGES_PER_CATEGORY = 3
MAX_REMOTECO_MAX_PAGES_PER_CATEGORY = 10
DEFAULT_REMOTECO_MAX_JOBS = 100
MAX_REMOTECO_MAX_JOBS = 500
DEFAULT_REMOTECO_DETAIL_WORKERS = 6
MAX_REMOTECO_DETAIL_WORKERS = 6
DEFAULT_REMOTECO_TIMEOUT_SECONDS = 20.0


class RemoteCoParseError(ValueError):
    pass


class RemoteCoGeoClassification(StrEnum):
    POTENTIALLY_ELIGIBLE = "POTENTIALLY_ELIGIBLE"
    EXPLICITLY_INELIGIBLE = "EXPLICITLY_INELIGIBLE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class RemoteCoListingEntry:
    external_id: str
    canonical_url: str

    title_hint: str | None = None
    company_hint: str | None = None
    posted_relative: str | None = None
    remote_work_level: str | None = None
    schedule: str | None = None
    job_type: str | None = None
    salary_text: str | None = None
    location_text: str | None = None
    geo_classification: RemoteCoGeoClassification = (
        RemoteCoGeoClassification.UNKNOWN
    )

    source_category_url: str | None = None
    source_listing_url: str | None = None
    raw_lines: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RemoteCoListingPage:
    entries: list[RemoteCoListingEntry]
    next_url: str | None


@dataclass(frozen=True, slots=True)
class RemoteCoPosting:
    external_id: str
    canonical_url: str

    title: str
    company_name: str

    description: str | None
    location_text: str | None
    workplace_type_source: str | None
    employment_type: str | None
    job_schedule: str | None
    salary_text: str | None
    career_level: str | None
    categories: tuple[str, ...]

    apply_url: str | None
    company_website_url: str | None

    published_at: datetime | None
    posted_relative: str | None
    source_job_id: str | None

    raw_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RemoteCoDetailFailure:
    external_id: str
    url: str
    error_type: str
    error_message: str


@dataclass(frozen=True, slots=True)
class RemoteCoFetch:
    category_urls: tuple[str, ...]
    categories_configured: int
    pages_fetched: int
    listing_rows: int
    unique_jobs: int
    duplicates_removed: int
    explicit_geo_rejects: int
    remote_level_rejects: int
    unknown_geography: int
    potentially_eligible: int
    details_attempted: int
    details_succeeded: int
    details_failed: int
    parse_failures: int
    normalized_jobs: int
    jobs: list[RemoteCoPosting]
    coverage_warnings: list[str] = field(
        default_factory=list
    )
    failures: list[RemoteCoDetailFailure] = field(
        default_factory=list
    )


@dataclass(slots=True)
class _Node:
    tag: str
    attrs: dict[str, str]
    parent: _Node | None = None
    children: list[_Node] = field(default_factory=list)
    text_parts: list[str] = field(default_factory=list)


class _HtmlTreeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(
            convert_charrefs=True
        )
        self.root = _Node(
            tag="document",
            attrs={},
        )
        self._stack = [self.root]

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        parent = self._stack[-1]
        node = _Node(
            tag=tag.casefold(),
            attrs={
                name.casefold(): value or ""
                for name, value in attrs
            },
            parent=parent,
        )
        parent.children.append(node)

        if tag.casefold() not in {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }:
            self._stack.append(node)

    def handle_endtag(
        self,
        tag: str,
    ) -> None:
        tag = tag.casefold()

        while len(self._stack) > 1:
            node = self._stack.pop()

            if node.tag == tag:
                break

    def handle_data(
        self,
        data: str,
    ) -> None:
        if data:
            self._stack[-1].text_parts.append(data)


class RemoteCoClient:
    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_REMOTECO_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def fetch_jobs(
        self,
        *,
        max_pages_per_category: int = (
            DEFAULT_REMOTECO_MAX_PAGES_PER_CATEGORY
        ),
        max_jobs: int = DEFAULT_REMOTECO_MAX_JOBS,
        detail_workers: int = DEFAULT_REMOTECO_DETAIL_WORKERS,
    ) -> RemoteCoFetch:
        _validate_limits(
            max_pages_per_category=max_pages_per_category,
            max_jobs=max_jobs,
            detail_workers=detail_workers,
        )

        detail_workers = min(
            detail_workers,
            MAX_REMOTECO_DETAIL_WORKERS,
            max_jobs,
        )

        with httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            transport=self.transport,
            headers={
                "User-Agent": "chamba-hunter/0.1",
                "Accept": (
                    "text/html,application/xhtml+xml,"
                    "application/xml;q=0.9,*/*;q=0.8"
                ),
            },
        ) as client:
            unique_entries: dict[
                str,
                RemoteCoListingEntry,
            ] = {}
            pages_fetched = 0
            listing_rows = 0
            duplicates_removed = 0
            explicit_geo_rejects = 0
            remote_level_rejects = 0
            unknown_geography = 0
            potentially_eligible = 0
            coverage_warnings: list[str] = []

            for category_url in REMOTECO_CATEGORY_URLS:
                page_url: str | None = category_url
                category_pages = 0
                seen_page_urls: set[str] = set()

                while (
                    page_url is not None
                    and category_pages
                    < max_pages_per_category
                    and page_url not in seen_page_urls
                ):
                    seen_page_urls.add(page_url)
                    response = client.get(page_url)

                    if response.status_code == 429:
                        raise RuntimeError(
                            "Remote.co rate limit reached."
                        )

                    response.raise_for_status()
                    pages_fetched += 1
                    category_pages += 1

                    page = parse_remoteco_listing_page(
                        response.text,
                        page_url=page_url,
                        category_url=category_url,
                    )
                    listing_rows += len(
                        page.entries
                    )

                    for entry in page.entries:
                        if _remote_level_reject(
                            entry.remote_work_level
                        ):
                            remote_level_rejects += 1
                            continue

                        if (
                            entry.geo_classification
                            == RemoteCoGeoClassification.EXPLICITLY_INELIGIBLE
                        ):
                            explicit_geo_rejects += 1
                            continue

                        if (
                            entry.geo_classification
                            == RemoteCoGeoClassification.UNKNOWN
                        ):
                            unknown_geography += 1
                        else:
                            potentially_eligible += 1

                        if (
                            entry.external_id
                            in unique_entries
                        ):
                            duplicates_removed += 1
                            continue

                        unique_entries[
                            entry.external_id
                        ] = entry

                    if (
                        category_pages
                        >= max_pages_per_category
                        and page.next_url is not None
                    ):
                        coverage_warnings.append(
                            "Reached page limit for "
                            f"{category_url}; next page "
                            f"exists: {page.next_url}"
                        )
                        break

                    page_url = page.next_url

            selected_entries = list(
                unique_entries.values()
            )[:max_jobs]

            jobs: list[RemoteCoPosting] = []
            failures: list[RemoteCoDetailFailure] = []
            parse_failures = 0

            def fetch_detail(
                entry: RemoteCoListingEntry,
            ) -> RemoteCoPosting:
                detail_response = client.get(
                    entry.canonical_url
                )

                if detail_response.status_code == 429:
                    raise RuntimeError(
                        "Remote.co rate limit reached."
                    )

                detail_response.raise_for_status()

                return parse_remoteco_detail(
                    detail_response.text,
                    entry=entry,
                )

            with ThreadPoolExecutor(
                max_workers=detail_workers
            ) as executor:
                future_by_entry = {
                    executor.submit(
                        fetch_detail,
                        entry,
                    ): entry
                    for entry in selected_entries
                }

                for future in as_completed(
                    future_by_entry
                ):
                    entry = future_by_entry[
                        future
                    ]

                    try:
                        jobs.append(
                            future.result()
                        )
                    except Exception as error:
                        if isinstance(
                            error,
                            RemoteCoParseError,
                        ):
                            parse_failures += 1

                        failures.append(
                            RemoteCoDetailFailure(
                                external_id=(
                                    entry.external_id
                                ),
                                url=(
                                    entry.canonical_url
                                ),
                                error_type=(
                                    type(error).__name__
                                ),
                                error_message=str(
                                    error
                                ),
                            )
                        )

            if (
                selected_entries
                and not jobs
            ):
                raise RuntimeError(
                    "Remote.co detail pages produced "
                    "no usable jobs."
                )

            if len(failures) > max(
                5,
                len(jobs),
            ):
                raise RuntimeError(
                    "Remote.co detail failure rate "
                    "was too high to persist safely."
                )

            jobs.sort(
                key=lambda job: job.external_id
            )

            return RemoteCoFetch(
                category_urls=REMOTECO_CATEGORY_URLS,
                categories_configured=len(
                    REMOTECO_CATEGORY_URLS
                ),
                pages_fetched=pages_fetched,
                listing_rows=listing_rows,
                unique_jobs=len(
                    unique_entries
                ),
                duplicates_removed=(
                    duplicates_removed
                ),
                explicit_geo_rejects=(
                    explicit_geo_rejects
                ),
                remote_level_rejects=(
                    remote_level_rejects
                ),
                unknown_geography=(
                    unknown_geography
                ),
                potentially_eligible=(
                    potentially_eligible
                ),
                details_attempted=len(
                    selected_entries
                ),
                details_succeeded=len(jobs),
                details_failed=len(
                    failures
                ),
                parse_failures=parse_failures,
                normalized_jobs=len(jobs),
                jobs=jobs,
                coverage_warnings=(
                    coverage_warnings
                ),
                failures=failures,
            )


def parse_remoteco_listing_page(
    html: str,
    *,
    page_url: str,
    category_url: str,
) -> RemoteCoListingPage:
    root = _parse_html(html)
    entries_by_url: dict[
        str,
        RemoteCoListingEntry,
    ] = {}

    for anchor in _iter_nodes(root):
        if anchor.tag != "a":
            continue

        canonical = canonical_remoteco_job_url(
            anchor.attrs.get("href"),
            base_url=page_url,
        )

        if canonical is None:
            continue

        external_id = remoteco_external_id(
            canonical
        )
        title_hint = _clean_text(
            _node_text(anchor)
        )
        card = _card_node(anchor)
        lines = _visible_lines(
            _node_text(card)
        )
        hints = _listing_hints(
            lines=lines,
            title_hint=title_hint,
        )
        location_text = hints[
            "location_text"
        ]

        entries_by_url.setdefault(
            canonical,
            RemoteCoListingEntry(
                external_id=external_id,
                canonical_url=canonical,
                title_hint=title_hint,
                company_hint=(
                    hints["company_hint"]
                ),
                posted_relative=(
                    hints["posted_relative"]
                ),
                remote_work_level=(
                    hints["remote_work_level"]
                ),
                schedule=hints["schedule"],
                job_type=hints["job_type"],
                salary_text=(
                    hints["salary_text"]
                ),
                location_text=location_text,
                geo_classification=(
                    classify_remoteco_geography(
                        location_text
                    )
                ),
                source_category_url=(
                    category_url
                ),
                source_listing_url=page_url,
                raw_lines=tuple(lines),
            ),
        )

    return RemoteCoListingPage(
        entries=list(
            entries_by_url.values()
        ),
        next_url=_next_page_url(
            root,
            page_url=page_url,
            category_url=category_url,
        ),
    )


def parse_remoteco_detail(
    html: str,
    *,
    entry: RemoteCoListingEntry,
) -> RemoteCoPosting:
    root = _parse_html(html)
    lines = _visible_lines(
        _node_text(root)
    )
    json_ld = _jobposting_json_ld(root)

    title = (
        _json_string(json_ld, "title")
        or entry.title_hint
        or _heading_text(root, "h1")
    )
    company_name = (
        _organization_name(
            json_ld.get(
                "hiringOrganization"
            )
            if isinstance(json_ld, dict)
            else None
        )
        or _labeled_value(
            lines,
            "Company",
        )
        or entry.company_hint
    )

    if title is None:
        raise RemoteCoParseError(
            "Remote.co detail page has no title."
        )

    if company_name is None:
        raise RemoteCoParseError(
            "Remote.co detail page has no company."
        )

    description = (
        _html_to_text(
            _json_string(
                json_ld,
                "description",
            )
        )
        or _section_text(
            lines,
            "About the Role",
        )
        or _section_text(
            lines,
            "Job Description",
        )
    )

    if description is None:
        raise RemoteCoParseError(
            "Remote.co detail page has no "
            "description."
        )

    date_posted_text = _labeled_value(
        lines,
        "Date Posted",
    )
    remote_work_level = (
        _labeled_value(
            lines,
            "Remote Work Level",
        )
        or entry.remote_work_level
    )
    location_text = (
        _location_from_json_ld(json_ld)
        or _labeled_value(lines, "Location")
        or entry.location_text
    )
    job_schedule = (
        _labeled_value(
            lines,
            "Job Schedule",
        )
        or entry.schedule
    )
    salary_text = (
        _labeled_value(lines, "Salary")
        or _salary_from_json_ld(json_ld)
        or entry.salary_text
    )
    categories = tuple(
        _unique_strings(
            [
                *_split_list(
                    _labeled_value(
                        lines,
                        "Categories",
                    )
                ),
                *_json_list(
                    json_ld,
                    "occupationalCategory",
                ),
            ]
        )
    )
    job_type = (
        _labeled_value(lines, "Job Type")
        or _employment_type_from_json_ld(
            json_ld
        )
        or entry.job_type
    )
    career_level = _labeled_value(
        lines,
        "Career Level",
    )
    apply_url = _apply_url(
        root,
        canonical_url=entry.canonical_url,
    )
    organization = _organization_dict(json_ld)
    company_website_url = (
        _external_url(
            _json_string(
                organization,
                "sameAs",
            )
        )
        or _external_url(
            _json_string(
                organization,
                "url",
            )
        )
    )
    json_date_posted = _json_string(
        json_ld,
        "datePosted",
    )
    published_at = _parse_source_datetime(
        json_date_posted
    ) or _parse_source_datetime(
        date_posted_text
    )
    posted_relative = (
        entry.posted_relative
        or (
            date_posted_text
            if _relative_age_range(
                date_posted_text
            )
            is not None
            else None
        )
    )
    source_job_id = _source_job_id(
        json_ld
    )

    raw_payload = {
        "external_id": entry.external_id,
        "canonical_url": entry.canonical_url,
        "index": {
            "source_category_url": (
                entry.source_category_url
            ),
            "source_listing_url": (
                entry.source_listing_url
            ),
            "title_hint": entry.title_hint,
            "company_hint": entry.company_hint,
            "posted_relative": (
                entry.posted_relative
            ),
            "remote_work_level": (
                entry.remote_work_level
            ),
            "schedule": entry.schedule,
            "job_type": entry.job_type,
            "salary_text": (
                entry.salary_text
            ),
            "location_text": (
                entry.location_text
            ),
            "geo_classification": (
                entry.geo_classification.value
            ),
            "raw_lines": list(
                entry.raw_lines
            ),
        },
        "detail": {
            "structured_json_ld_present": bool(
                json_ld
            ),
            "date_posted": date_posted_text,
            "remote_work_level": (
                remote_work_level
            ),
            "location": location_text,
            "job_schedule": job_schedule,
            "salary": salary_text,
            "categories": list(categories),
            "job_type": job_type,
            "career_level": career_level,
            "source_job_id": source_job_id,
            "company_website_url": (
                company_website_url
            ),
        },
        "_chamba_source_enrichment": {
            "source": "REMOTECO",
            "posted_relative": (
                posted_relative
            ),
        },
    }

    return RemoteCoPosting(
        external_id=entry.external_id,
        canonical_url=entry.canonical_url,
        title=title,
        company_name=company_name,
        description=description,
        location_text=location_text,
        workplace_type_source=(
            remote_work_level
        ),
        employment_type=job_type,
        job_schedule=job_schedule,
        salary_text=salary_text,
        career_level=career_level,
        categories=categories,
        apply_url=apply_url,
        company_website_url=(
            company_website_url
        ),
        published_at=published_at,
        posted_relative=posted_relative,
        source_job_id=source_job_id,
        raw_payload=raw_payload,
    )


def canonical_remoteco_job_url(
    url: str | None,
    *,
    base_url: str = REMOTECO_BASE_URL,
) -> str | None:
    cleaned = _clean_text(url)

    if cleaned is None:
        return None

    absolute = urljoin(base_url, cleaned)
    parsed = urlparse(absolute)
    host = parsed.hostname.casefold() if parsed.hostname else ""

    if host not in {
        "remote.co",
        "www.remote.co",
    }:
        return None

    segments = [
        segment
        for segment in parsed.path.split("/")
        if segment
    ]

    if (
        len(segments) != 2
        or segments[0] != "job-details"
        or not segments[1]
    ):
        return None

    return urlunparse(
        (
            "https",
            "remote.co",
            "/".join(
                [
                    "",
                    "job-details",
                    segments[1].rstrip("/"),
                ]
            ),
            "",
            "",
            "",
        )
    )


def remoteco_external_id(
    canonical_url: str,
) -> str:
    parsed = urlparse(canonical_url)
    segments = [
        segment
        for segment in parsed.path.split("/")
        if segment
    ]

    if (
        len(segments) != 2
        or segments[0] != "job-details"
        or not segments[1]
    ):
        raise ValueError(
            "Not a canonical Remote.co job URL."
        )

    slug = segments[1]
    uuid_match = re.search(
        r"(?:^|-)([0-9a-f]{8}-[0-9a-f]{4}-"
        r"[0-9a-f]{4}-[0-9a-f]{4}-"
        r"[0-9a-f]{12}|[0-9a-f]{32}|"
        r"[0-9]{6,})$",
        slug,
        flags=re.IGNORECASE,
    )

    if uuid_match is not None:
        return uuid_match.group(1).casefold()

    return f"job-details/{slug}"


def classify_remoteco_geography(
    location_text: str | None,
) -> RemoteCoGeoClassification:
    normalized = _normalize_text(
        location_text
    )

    if not normalized:
        return RemoteCoGeoClassification.UNKNOWN

    if re.search(
        r"\b(argentina|buenos aires|latin america|"
        r"latam|south america|worldwide|anywhere|"
        r"global|international)\b",
        normalized,
    ):
        return (
            RemoteCoGeoClassification.POTENTIALLY_ELIGIBLE
        )

    if re.search(
        r"\b(us national|u s national|united states|"
        r"usa|canada|united kingdom|uk|india|"
        r"australia|new zealand)\b",
        normalized,
    ):
        return (
            RemoteCoGeoClassification.EXPLICITLY_INELIGIBLE
        )

    if _has_us_state_limit(
        raw_location=location_text,
        normalized=normalized,
    ):
        return (
            RemoteCoGeoClassification.EXPLICITLY_INELIGIBLE
        )

    if re.search(
        r"\b(brazil|bolivia|chile|colombia|"
        r"costa rica|dominican republic|ecuador|"
        r"el salvador|guatemala|honduras|mexico|"
        r"nicaragua|panama|paraguay|peru|uruguay|"
        r"venezuela|france|germany|ireland|"
        r"netherlands|poland|portugal|spain|"
        r"sweden|switzerland|israel|singapore|"
        r"philippines|japan|south africa)\b",
        normalized,
    ):
        return (
            RemoteCoGeoClassification.EXPLICITLY_INELIGIBLE
        )

    if re.search(
        r"\b(austin|chicago|dallas|denver|"
        r"los angeles|miami|new york|san francisco|"
        r"seattle|toronto|vancouver|london|"
        r"berlin|madrid|sydney|melbourne)\b",
        normalized,
    ):
        return (
            RemoteCoGeoClassification.EXPLICITLY_INELIGIBLE
        )

    return RemoteCoGeoClassification.UNKNOWN


def _validate_limits(
    *,
    max_pages_per_category: int,
    max_jobs: int,
    detail_workers: int,
) -> None:
    if not (
        1
        <= max_pages_per_category
        <= MAX_REMOTECO_MAX_PAGES_PER_CATEGORY
    ):
        raise ValueError(
            "max_pages_per_category must be "
            "between 1 and "
            f"{MAX_REMOTECO_MAX_PAGES_PER_CATEGORY}."
        )

    if not 1 <= max_jobs <= MAX_REMOTECO_MAX_JOBS:
        raise ValueError(
            "max_jobs must be between 1 and "
            f"{MAX_REMOTECO_MAX_JOBS}."
        )

    if not (
        1
        <= detail_workers
        <= MAX_REMOTECO_DETAIL_WORKERS
    ):
        raise ValueError(
            "detail_workers must be between 1 and "
            f"{MAX_REMOTECO_DETAIL_WORKERS}."
        )


def _remote_level_reject(
    remote_work_level: str | None,
) -> bool:
    normalized = _normalize_text(
        remote_work_level
    )

    return normalized == "no remote work"


def _parse_html(
    html: str,
) -> _Node:
    parser = _HtmlTreeParser()
    parser.feed(html)
    parser.close()
    return parser.root


def _iter_nodes(
    node: _Node,
):
    yield node

    for child in node.children:
        yield from _iter_nodes(child)


def _node_text(
    node: _Node,
) -> str:
    parts: list[str] = []

    def visit(current: _Node) -> None:
        if current.tag in {
            "script",
            "style",
            "noscript",
        }:
            return

        if current.tag in _BLOCK_TAGS:
            parts.append("\n")

        parts.extend(current.text_parts)

        for child in current.children:
            visit(child)

        if current.tag in _BLOCK_TAGS:
            parts.append("\n")

    visit(node)
    return unescape("".join(parts))


def _visible_lines(
    text: str,
) -> list[str]:
    return [
        cleaned
        for cleaned in (
            _clean_text(line)
            for line in text.splitlines()
        )
        if cleaned is not None
    ]


def _card_node(
    anchor: _Node,
) -> _Node:
    current = anchor.parent

    while current is not None:
        class_name = current.attrs.get(
            "class",
            "",
        ).casefold()

        if current.tag in {
            "article",
            "li",
        }:
            return current

        if (
            current.tag == "div"
            and re.search(
                r"\b(job|card|listing|position)\b",
                class_name,
            )
        ):
            return current

        current = current.parent

    return anchor.parent or anchor


def _listing_hints(
    *,
    lines: list[str],
    title_hint: str | None,
) -> dict[str, str | None]:
    remote_work_level = _first_matching_text(
        lines,
        r"\b(100%\s+remote work|hybrid remote work|"
        r"no remote work)\b",
    )
    posted_relative = _first_matching_text(
        lines,
        r"^(new!|today|yesterday|\d+\s+days?\s+ago|"
        r"\d+\s+weeks?\s+ago|\d+\s+months?\s+ago)$",
    )
    schedule = _first_matching_text(
        lines,
        r"\b(full-time|part-time|flexible schedule|"
        r"alternative schedule)\b",
    )
    job_type = _first_matching_text(
        lines,
        r"\b(employee|freelance|contract|temporary)\b",
    )
    salary_text = _first_matching_text(
        lines,
        r"(\$|salary|usd|hour|year)",
    )
    location_text = _first_location_line(
        lines,
        remote_work_level=remote_work_level,
    )
    company_hint = _company_hint(
        lines=lines,
        title_hint=title_hint,
        excluded={
            remote_work_level,
            posted_relative,
            schedule,
            job_type,
            salary_text,
            location_text,
        },
    )

    return {
        "company_hint": company_hint,
        "posted_relative": posted_relative,
        "remote_work_level": remote_work_level,
        "schedule": schedule,
        "job_type": job_type,
        "salary_text": salary_text,
        "location_text": location_text,
    }


def _company_hint(
    *,
    lines: list[str],
    title_hint: str | None,
    excluded: set[str | None],
) -> str | None:
    normalized_title = _normalize_text(
        title_hint
    )
    excluded_normalized = {
        _normalize_text(value)
        for value in excluded
        if value is not None
    }

    for line in lines[:8]:
        normalized = _normalize_text(line)

        if (
            not normalized
            or normalized == normalized_title
            or normalized in excluded_normalized
            or _looks_like_metadata(line)
        ):
            continue

        return line

    return None


def _looks_like_metadata(
    line: str,
) -> bool:
    return any(
        predicate(line)
        for predicate in (
            lambda value: _relative_age_range(
                value
            )
            is not None,
            lambda value: _first_matching_text(
                [value],
                r"\b(remote work|remote,|remote in|"
                r"hybrid remote|full-time|part-time|"
                r"employee|freelance|contract|"
                r"temporary|salary|\$)\b",
            )
            is not None,
        )
    )


def _first_location_line(
    lines: list[str],
    *,
    remote_work_level: str | None,
) -> str | None:
    remote_normalized = _normalize_text(
        remote_work_level
    )

    for line in lines:
        normalized = _normalize_text(line)

        if not normalized or normalized == remote_normalized:
            continue

        if re.search(
            r"^(remote|hybrid remote)(,|\s+in\b)",
            normalized,
        ):
            return line

        if classify_remoteco_geography(
            line
        ) != RemoteCoGeoClassification.UNKNOWN:
            return line

    return None


def _next_page_url(
    root: _Node,
    *,
    page_url: str,
    category_url: str,
) -> str | None:
    category_path = urlparse(
        category_url
    ).path.rstrip("/")

    for anchor in _iter_nodes(root):
        if anchor.tag != "a":
            continue

        rel = anchor.attrs.get(
            "rel",
            "",
        ).casefold()
        class_name = anchor.attrs.get(
            "class",
            "",
        ).casefold()
        aria = anchor.attrs.get(
            "aria-label",
            "",
        ).casefold()
        text = _normalize_text(
            _node_text(anchor)
        )

        if not (
            "next" in rel
            or "next" in class_name
            or "next" in aria
            or text in {"next", "next page", ">"}
        ):
            continue

        href = anchor.attrs.get("href")
        cleaned = _clean_text(href)

        if cleaned is None:
            continue

        absolute = urljoin(page_url, cleaned)
        parsed = urlparse(absolute)
        host = (
            parsed.hostname.casefold()
            if parsed.hostname
            else ""
        )

        if host not in {
            "remote.co",
            "www.remote.co",
        }:
            continue

        path = parsed.path.rstrip("/")

        if not (
            path == category_path
            or path.startswith(
                f"{category_path}/"
            )
        ):
            continue

        return urlunparse(
            (
                "https",
                "remote.co",
                parsed.path.rstrip("/"),
                "",
                parsed.query,
                "",
            )
        )

    return None


def _jobposting_json_ld(
    root: _Node,
) -> dict[str, Any]:
    for node in _iter_nodes(root):
        if node.tag != "script":
            continue

        script_type = node.attrs.get(
            "type",
            "",
        ).casefold()

        if "ld+json" not in script_type:
            continue

        raw = "".join(node.text_parts).strip()

        if not raw:
            continue

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue

        posting = _find_json_ld_type(
            parsed,
            "JobPosting",
        )

        if posting is not None:
            return posting

    return {}


def _find_json_ld_type(
    value: Any,
    expected_type: str,
) -> dict[str, Any] | None:
    if isinstance(value, dict):
        raw_type = value.get("@type")
        types = (
            raw_type
            if isinstance(raw_type, list)
            else [raw_type]
        )

        if any(
            str(item).casefold()
            == expected_type.casefold()
            for item in types
            if item is not None
        ):
            return value

        graph = value.get("@graph")

        if isinstance(graph, list):
            for item in graph:
                found = _find_json_ld_type(
                    item,
                    expected_type,
                )

                if found is not None:
                    return found

    elif isinstance(value, list):
        for item in value:
            found = _find_json_ld_type(
                item,
                expected_type,
            )

            if found is not None:
                return found

    return None


def _heading_text(
    root: _Node,
    tag: str,
) -> str | None:
    for node in _iter_nodes(root):
        if node.tag == tag:
            text = _clean_text(
                _node_text(node)
            )

            if text:
                return text

    return None


def _labeled_value(
    lines: list[str],
    label: str,
) -> str | None:
    normalized_label = _normalize_text(
        label
    )
    labels = {
        _normalize_text(item)
        for item in _DETAIL_LABELS
    }

    for index, line in enumerate(lines):
        normalized = _normalize_text(line)

        if normalized == normalized_label:
            for candidate in lines[
                index + 1 :
            ]:
                if (
                    _normalize_text(candidate)
                    in labels
                ):
                    break

                return candidate

        prefix = f"{label}:"

        if line.casefold().startswith(
            prefix.casefold()
        ):
            return _clean_text(
                line[len(prefix) :]
            )

    return None


def _section_text(
    lines: list[str],
    heading: str,
) -> str | None:
    normalized_heading = _normalize_text(
        heading
    )
    labels = {
        _normalize_text(item)
        for item in _DETAIL_LABELS
    }
    collected: list[str] = []
    in_section = False

    for line in lines:
        normalized = _normalize_text(line)

        if not in_section:
            if normalized == normalized_heading:
                in_section = True
            continue

        if normalized in labels:
            break

        collected.append(line)

    return _clean_text(
        "\n".join(collected)
    )


def _apply_url(
    root: _Node,
    *,
    canonical_url: str,
) -> str | None:
    fallback_ats: str | None = None

    for anchor in _iter_nodes(root):
        if anchor.tag != "a":
            continue

        href = _clean_text(
            anchor.attrs.get("href")
        )

        if href is None:
            continue

        absolute = urljoin(
            canonical_url,
            href,
        )
        parsed = urlparse(absolute)
        host = (
            parsed.hostname.casefold()
            if parsed.hostname
            else ""
        )

        if host in {
            "remote.co",
            "www.remote.co",
            "",
        }:
            continue

        clean_url = urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path.rstrip("/"),
                "",
                parsed.query,
                "",
            )
        )
        anchor_text = _normalize_text(
            _node_text(anchor)
        )

        if "apply" in anchor_text:
            return clean_url

        if _is_known_ats_host(host):
            fallback_ats = (
                fallback_ats or clean_url
            )

    return fallback_ats


def _is_known_ats_host(
    host: str,
) -> bool:
    return (
        host.endswith("greenhouse.io")
        or host == "jobs.ashbyhq.com"
        or host == "jobs.lever.co"
        or host == "apply.workable.com"
        or host == "jobs.smartrecruiters.com"
        or host.endswith(".bamboohr.com")
    )


def _organization_dict(
    json_ld: dict[str, Any],
) -> dict[str, Any]:
    organization = json_ld.get(
        "hiringOrganization"
    )

    return (
        organization
        if isinstance(
            organization,
            dict,
        )
        else {}
    )


def _organization_name(
    value: Any,
) -> str | None:
    if isinstance(value, dict):
        return _json_string(value, "name")

    if isinstance(value, str):
        return _clean_text(value)

    return None


def _location_from_json_ld(
    json_ld: dict[str, Any],
) -> str | None:
    for key in (
        "applicantLocationRequirements",
        "jobLocation",
    ):
        location = json_ld.get(key)

        if isinstance(location, dict):
            parts = [
                _json_string(location, "name"),
                _json_string(location, "addressCountry"),
            ]

            address = location.get("address")

            if isinstance(address, dict):
                parts.extend(
                    [
                        _json_string(
                            address,
                            "addressLocality",
                        ),
                        _json_string(
                            address,
                            "addressRegion",
                        ),
                        _json_string(
                            address,
                            "addressCountry",
                        ),
                    ]
                )

            joined = _clean_text(
                ", ".join(
                    part
                    for part in parts
                    if part
                )
            )

            if joined:
                return joined

        if isinstance(location, list):
            parts = [
                _location_from_json_ld(
                    {"jobLocation": item}
                )
                for item in location
            ]

            return _clean_text(
                ", ".join(
                    part
                    for part in parts
                    if part
                )
            )

    return _json_string(
        json_ld,
        "jobLocationType",
    )


def _employment_type_from_json_ld(
    json_ld: dict[str, Any],
) -> str | None:
    value = json_ld.get(
        "employmentType"
    )

    if isinstance(value, list):
        return _clean_text(
            ", ".join(
                str(item)
                for item in value
                if item
            )
        )

    if isinstance(value, str):
        return _clean_text(value)

    return None


def _salary_from_json_ld(
    json_ld: dict[str, Any],
) -> str | None:
    salary = json_ld.get("baseSalary")

    if not isinstance(salary, dict):
        return None

    currency = _json_string(
        salary,
        "currency",
    )
    value = salary.get("value")

    if isinstance(value, dict):
        minimum = value.get("minValue")
        maximum = value.get("maxValue")
        unit = _json_string(
            value,
            "unitText",
        )

        if minimum and maximum:
            return _clean_text(
                f"{minimum}-{maximum} "
                f"{currency or ''} "
                f"{unit or ''}"
            )

        if minimum:
            return _clean_text(
                f"{minimum} {currency or ''} "
                f"{unit or ''}"
            )

    return None


def _source_job_id(
    json_ld: dict[str, Any],
) -> str | None:
    identifier = json_ld.get(
        "identifier"
    )

    if isinstance(identifier, dict):
        return (
            _json_string(identifier, "value")
            or _json_string(
                identifier,
                "propertyID",
            )
        )

    if isinstance(identifier, str):
        return _clean_text(identifier)

    return None


def _json_string(
    value: dict[str, Any],
    key: str,
) -> str | None:
    if not isinstance(value, dict):
        return None

    raw = value.get(key)

    if isinstance(raw, str):
        return _clean_text(raw)

    if isinstance(raw, int | float):
        return str(raw)

    return None


def _json_list(
    value: dict[str, Any],
    key: str,
) -> list[str]:
    if not isinstance(value, dict):
        return []

    raw = value.get(key)

    if isinstance(raw, list):
        return [
            cleaned
            for cleaned in (
                _clean_text(str(item))
                for item in raw
            )
            if cleaned
        ]

    if isinstance(raw, str):
        return _split_list(raw)

    return []


def _external_url(
    value: str | None,
) -> str | None:
    cleaned = _clean_text(value)

    if cleaned is None:
        return None

    parsed = urlparse(cleaned)
    host = parsed.hostname.casefold() if parsed.hostname else ""

    if (
        parsed.scheme not in {"http", "https"}
        or host in {
            "remote.co",
            "www.remote.co",
        }
    ):
        return None

    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path.rstrip("/"),
            "",
            "",
            "",
        )
    )


def _parse_source_datetime(
    value: str | None,
) -> datetime | None:
    cleaned = _clean_text(value)

    if (
        cleaned is None
        or _relative_age_range(cleaned)
        is not None
        or _normalize_text(cleaned) == "new"
    ):
        return None

    iso_value = cleaned.replace(
        "Z",
        "+00:00",
    )

    try:
        parsed = datetime.fromisoformat(
            iso_value
        )
    except ValueError:
        parsed = None

    if parsed is not None:
        if parsed.tzinfo is None:
            parsed = parsed.replace(
                tzinfo=UTC
            )

        return parsed

    for date_format in (
        "%B %d, %Y",
        "%b %d, %Y",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(
                cleaned,
                date_format,
            ).replace(tzinfo=UTC)
        except ValueError:
            continue

    return None


def _relative_age_range(
    value: str | None,
) -> tuple[int, int] | None:
    normalized = _normalize_text(value)

    if not normalized:
        return None

    if re.fullmatch(
        r"(today)",
        normalized,
    ):
        return (0, 0)

    if re.fullmatch(
        r"(yesterday)",
        normalized,
    ):
        return (1, 1)

    match = re.fullmatch(
        r"(\d+|one|a)\s+"
        r"(day|days|week|weeks|month|months)"
        r"\s+ago",
        normalized,
    )

    if match is None:
        return None

    raw_amount = match.group(1)
    amount = (
        1
        if raw_amount in {"one", "a"}
        else int(raw_amount)
    )
    unit = match.group(2)

    if unit in {"day", "days"}:
        return (amount, amount)

    if unit in {"week", "weeks"}:
        return (
            amount * 7,
            amount * 7 + 6,
        )

    return (
        amount * 28,
        amount * 31,
    )


def _html_to_text(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    return _clean_text(
        re.sub(
            r"<[^>]+>",
            " ",
            unescape(value),
        )
    )


def _split_list(
    value: str | None,
) -> list[str]:
    if value is None:
        return []

    return [
        item
        for item in (
            _clean_text(part)
            for part in re.split(
                r"[,;/]",
                value,
            )
        )
        if item
    ]


def _unique_strings(
    values: list[str],
) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []

    for value in values:
        cleaned = _clean_text(value)

        if cleaned is None:
            continue

        key = cleaned.casefold()

        if key in seen:
            continue

        seen.add(key)
        result.append(cleaned)

    return result


def _first_matching_text(
    lines: list[str],
    pattern: str,
) -> str | None:
    for line in lines:
        if re.search(
            pattern,
            line,
            flags=re.IGNORECASE,
        ):
            return line

    return None


def _has_us_state_limit(
    *,
    raw_location: str | None,
    normalized: str,
) -> bool:
    if re.search(
        r"\b(alabama|alaska|arizona|arkansas|"
        r"california|colorado|connecticut|delaware|"
        r"florida|georgia|hawaii|idaho|illinois|"
        r"indiana|kansas|kentucky|louisiana|maine|"
        r"maryland|massachusetts|michigan|minnesota|"
        r"mississippi|missouri|montana|nebraska|"
        r"nevada|new hampshire|new jersey|new mexico|"
        r"new york|north carolina|north dakota|ohio|"
        r"oklahoma|oregon|pennsylvania|rhode island|"
        r"south carolina|south dakota|tennessee|"
        r"texas|utah|vermont|virginia|washington|"
        r"wisconsin|west virginia|wyoming)\b",
        normalized,
    ):
        return True

    if raw_location is None:
        return False

    return re.search(
        r",\s*(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|"
        r"HI|IA|ID|IL|IN|KS|KY|LA|MA|MD|ME|"
        r"MI|MN|MO|MS|MT|NC|ND|NE|NH|NJ|NM|"
        r"NV|NY|OH|OK|OR|PA|RI|SC|SD|TN|TX|"
        r"UT|VA|VT|WA|WI|WV|WY)\b",
        raw_location,
    ) is not None


def _clean_text(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    cleaned = " ".join(
        unescape(str(value)).split()
    )

    return cleaned if cleaned else None


def _normalize_text(
    value: str | None,
) -> str:
    if value is None:
        return ""

    decomposed = unicodedata.normalize(
        "NFKD",
        value,
    )
    without_accents = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(
            character
        )
    )
    words = re.findall(
        r"[a-z0-9%]+",
        without_accents.casefold(),
    )

    return " ".join(words)


_BLOCK_TAGS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "br",
    "dd",
    "details",
    "div",
    "dl",
    "dt",
    "figcaption",
    "figure",
    "footer",
    "form",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "hr",
    "li",
    "main",
    "nav",
    "ol",
    "p",
    "pre",
    "section",
    "span",
    "table",
    "td",
    "th",
    "tr",
    "ul",
}

_DETAIL_LABELS = {
    "Date Posted",
    "Remote Work Level",
    "Location",
    "Job Schedule",
    "Salary",
    "Categories",
    "Job Type",
    "Career Level",
    "About the Role",
    "Job Description",
}
