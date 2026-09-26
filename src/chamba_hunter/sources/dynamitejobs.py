from __future__ import annotations

from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
)
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html import unescape
from html.parser import HTMLParser
import json
import re
from typing import Any
from urllib.parse import (
    urljoin,
    urlparse,
    urlunparse,
)

import httpx


DYNAMITEJOBS_BASE_URL = "https://dynamitejobs.com"

DYNAMITEJOBS_INDEX_URLS = (
    "https://dynamitejobs.com/category/"
    "remote-development-jobs/remote-backend-jobs",
    "https://dynamitejobs.com/category/"
    "remote-development-jobs/remote-fullstack-jobs",
    "https://dynamitejobs.com/skill/remote-java-jobs",
    "https://dynamitejobs.com/skill/"
    "remote-backend-development-jobs",
)

DEFAULT_DYNAMITE_MAX_JOBS = 100
DEFAULT_DYNAMITE_DETAIL_WORKERS = 6
DEFAULT_DYNAMITE_TIMEOUT_SECONDS = 20.0


class DynamiteJobsParseError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DynamiteJobsIndexEntry:
    external_id: str
    canonical_url: str
    company_slug: str
    job_slug: str

    title_hint: str | None = None
    company_hint: str | None = None
    employment_type_hint: str | None = None
    salary_text: str | None = None
    tags: tuple[str, ...] = ()
    opened_relative: str | None = None
    closing_relative: str | None = None
    status_text: str | None = None
    source_index_url: str | None = None


@dataclass(frozen=True, slots=True)
class DynamiteJobsPosting:
    external_id: str
    canonical_url: str
    company_slug: str
    job_slug: str

    title: str
    company_name: str

    description: str | None
    location_text: str | None
    employment_type: str | None
    skills: tuple[str, ...]
    salary_text: str | None

    apply_url: str | None
    company_website_url: str | None

    published_at: datetime | None
    expires_at: datetime | None

    opened_relative: str | None
    closing_relative: str | None
    status_text: str | None
    is_closed: bool

    raw_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class DynamiteJobsDetailFailure:
    external_id: str
    url: str
    error_type: str
    error_message: str


@dataclass(frozen=True, slots=True)
class DynamiteJobsFetch:
    index_urls: tuple[str, ...]
    index_pages_fetched: int
    links_discovered: int
    unique_jobs: int
    duplicates_removed: int
    details_attempted: int
    details_succeeded: int
    details_failed: int
    closed_skipped: int
    parse_failures: int
    jobs: list[DynamiteJobsPosting]
    failures: list[DynamiteJobsDetailFailure] = field(
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


class DynamiteJobsClient:
    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_DYNAMITE_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def fetch_jobs(
        self,
        *,
        max_jobs: int = DEFAULT_DYNAMITE_MAX_JOBS,
        detail_workers: int = DEFAULT_DYNAMITE_DETAIL_WORKERS,
    ) -> DynamiteJobsFetch:
        if not 1 <= max_jobs <= DEFAULT_DYNAMITE_MAX_JOBS:
            raise ValueError(
                "max_jobs must be between 1 and "
                f"{DEFAULT_DYNAMITE_MAX_JOBS}."
            )

        if detail_workers < 1:
            raise ValueError(
                "detail_workers must be at least 1."
            )

        detail_workers = min(
            detail_workers,
            DEFAULT_DYNAMITE_DETAIL_WORKERS,
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
                DynamiteJobsIndexEntry,
            ] = {}
            links_discovered = 0

            for index_url in DYNAMITEJOBS_INDEX_URLS:
                response = client.get(index_url)

                if response.status_code == 429:
                    raise RuntimeError(
                        "Dynamite Jobs rate limit reached."
                    )

                response.raise_for_status()

                entries = parse_dynamite_index(
                    response.text,
                    index_url=index_url,
                )
                links_discovered += len(entries)

                for entry in entries:
                    unique_entries.setdefault(
                        entry.external_id,
                        entry,
                    )

            selected_entries = list(
                unique_entries.values()
            )[:max_jobs]

            jobs: list[
                DynamiteJobsPosting
            ] = []
            failures: list[
                DynamiteJobsDetailFailure
            ] = []
            closed_skipped = 0
            parse_failures = 0

            def fetch_detail(
                entry: DynamiteJobsIndexEntry,
            ) -> DynamiteJobsPosting | None:
                detail_response = client.get(
                    entry.canonical_url
                )

                if detail_response.status_code == 429:
                    raise RuntimeError(
                        "Dynamite Jobs rate limit reached."
                    )

                detail_response.raise_for_status()

                posting = parse_dynamite_detail(
                    detail_response.text,
                    entry=entry,
                )

                return posting

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
                        posting = future.result()
                    except Exception as error:
                        if isinstance(
                            error,
                            DynamiteJobsParseError,
                        ):
                            parse_failures += 1

                        failures.append(
                            DynamiteJobsDetailFailure(
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
                        continue

                    if posting is None:
                        parse_failures += 1
                        continue

                    if posting.is_closed:
                        closed_skipped += 1
                        continue

                    jobs.append(posting)

            details_attempted = len(
                selected_entries
            )
            details_failed = len(
                failures
            )
            details_succeeded = (
                details_attempted
                - details_failed
            )

            if (
                details_attempted > 0
                and details_succeeded == 0
            ):
                raise RuntimeError(
                    "Dynamite Jobs detail pages produced "
                    "no usable open jobs."
                )

            if details_failed > max(
                5,
                details_succeeded,
            ):
                raise RuntimeError(
                    "Dynamite Jobs detail failure rate "
                    "was too high to persist safely."
                )

            jobs.sort(
                key=lambda job: job.external_id
            )

            return DynamiteJobsFetch(
                index_urls=DYNAMITEJOBS_INDEX_URLS,
                index_pages_fetched=len(
                    DYNAMITEJOBS_INDEX_URLS
                ),
                links_discovered=(
                    links_discovered
                ),
                unique_jobs=len(
                    unique_entries
                ),
                duplicates_removed=(
                    links_discovered
                    - len(unique_entries)
                ),
                details_attempted=(
                    details_attempted
                ),
                details_succeeded=(
                    details_succeeded
                ),
                details_failed=(
                    details_failed
                ),
                closed_skipped=(
                    closed_skipped
                ),
                parse_failures=(
                    parse_failures
                ),
                jobs=jobs,
                failures=failures,
            )


def parse_dynamite_index(
    html: str,
    *,
    index_url: str,
) -> list[DynamiteJobsIndexEntry]:
    root = _parse_html(html)
    entries: list[
        DynamiteJobsIndexEntry
    ] = []

    for anchor in _iter_nodes(root):
        if anchor.tag != "a":
            continue

        canonical = canonical_dynamite_job_url(
            anchor.attrs.get("href"),
            base_url=index_url,
        )

        if canonical is None:
            continue

        (
            external_id,
            company_slug,
            job_slug,
        ) = dynamite_external_id(canonical)

        title_hint = _clean_text(
            _node_text(anchor)
        )
        card = _card_node(anchor)
        lines = _visible_lines(
            _node_text(card)
        )

        hints = _index_hints(
            lines=lines,
            title_hint=title_hint,
        )

        entries.append(
            DynamiteJobsIndexEntry(
                external_id=external_id,
                canonical_url=canonical,
                company_slug=company_slug,
                job_slug=job_slug,
                title_hint=title_hint,
                company_hint=(
                    hints["company_hint"]
                ),
                employment_type_hint=(
                    hints["employment_type_hint"]
                ),
                salary_text=(
                    hints["salary_text"]
                ),
                tags=tuple(
                    hints["tags"]
                ),
                opened_relative=(
                    hints["opened_relative"]
                ),
                closing_relative=(
                    hints["closing_relative"]
                ),
                status_text=(
                    hints["status_text"]
                ),
                source_index_url=index_url,
            )
        )

    return entries


def parse_dynamite_detail(
    html: str,
    *,
    entry: DynamiteJobsIndexEntry,
) -> DynamiteJobsPosting:
    root = _parse_html(html)
    full_text = _node_text(root)
    lines = _visible_lines(full_text)
    json_ld = _jobposting_json_ld(root)

    closed_text = _first_matching(
        lines,
        r"\bthis job is closed\b",
    )
    is_closed = closed_text is not None

    title = _clean_text(
        _json_string(
            json_ld,
            "title",
        )
    ) or entry.title_hint or _heading_text(
        root,
        "h1",
    )

    company_name = (
        _organization_name(
            json_ld.get(
                "hiringOrganization"
            )
            if isinstance(json_ld, dict)
            else None
        )
        or entry.company_hint
        or _company_from_lines(
            lines=lines,
            title=title,
        )
    )

    if title is None:
        raise DynamiteJobsParseError(
            "Dynamite detail page has no title."
        )

    if company_name is None:
        raise DynamiteJobsParseError(
            "Dynamite detail page has no company."
        )

    description = (
        _html_to_text(
            _json_string(
                json_ld,
                "description",
            )
        )
        or _description_from_html(root)
    )

    if (
        description is None
        and not is_closed
    ):
        raise DynamiteJobsParseError(
            "Dynamite detail page has no "
            "description."
        )

    location_text = (
        _location_from_json_ld(json_ld)
        or _labeled_line_value(
            lines,
            "Location",
        )
    )

    employment_type = (
        _employment_type_from_json_ld(
            json_ld
        )
        or entry.employment_type_hint
        or _first_employment_type(lines)
    )

    salary_text = (
        entry.salary_text
        or _salary_from_json_ld(json_ld)
        or _first_salary_text(lines)
    )

    opened_relative = (
        entry.opened_relative
        or _first_opened_relative(lines)
    )
    closing_relative = (
        entry.closing_relative
        or _first_closing_relative(lines)
    )
    status_text = (
        closed_text
        or entry.status_text
        or opened_relative
        or closing_relative
    )

    apply_url = _apply_url(
        root,
        canonical_url=entry.canonical_url,
    )

    company_website_url = (
        _external_url(
            _json_string(
                _organization_dict(
                    json_ld
                ),
                "sameAs",
            )
        )
        or _external_url(
            _json_string(
                _organization_dict(
                    json_ld
                ),
                "url",
            )
        )
    )

    published_at = _parse_source_datetime(
        _json_string(
            json_ld,
            "datePosted",
        )
    )
    expires_at = _parse_source_datetime(
        _json_string(
            json_ld,
            "validThrough",
        )
    )

    skills = tuple(
        _unique_strings(
            [
                *entry.tags,
                *_skills_from_json_ld(json_ld),
            ]
        )
    )

    raw_payload = {
        "external_id": entry.external_id,
        "canonical_url": entry.canonical_url,
        "company_slug": entry.company_slug,
        "job_slug": entry.job_slug,
        "index": {
            "source_index_url": (
                entry.source_index_url
            ),
            "title_hint": entry.title_hint,
            "company_hint": entry.company_hint,
            "employment_type_hint": (
                entry.employment_type_hint
            ),
            "salary_text": (
                entry.salary_text
            ),
            "tags": list(entry.tags),
            "status_text": (
                entry.status_text
            ),
        },
        "detail": {
            "structured_json_ld_present": bool(
                json_ld
            ),
            "closed_text": closed_text,
            "company_website_url": (
                company_website_url
            ),
        },
        "_chamba_source_enrichment": {
            "source": "DYNAMITEJOBS",
            "opened_relative": (
                opened_relative
            ),
            "closing_relative": (
                closing_relative
            ),
            "status_text": status_text,
        },
    }

    return DynamiteJobsPosting(
        external_id=entry.external_id,
        canonical_url=entry.canonical_url,
        company_slug=entry.company_slug,
        job_slug=entry.job_slug,
        title=title,
        company_name=company_name,
        description=description,
        location_text=location_text,
        employment_type=employment_type,
        skills=skills,
        salary_text=salary_text,
        apply_url=apply_url,
        company_website_url=company_website_url,
        published_at=published_at,
        expires_at=expires_at,
        opened_relative=opened_relative,
        closing_relative=closing_relative,
        status_text=status_text,
        is_closed=is_closed,
        raw_payload=raw_payload,
    )


def canonical_dynamite_job_url(
    url: str | None,
    *,
    base_url: str = DYNAMITEJOBS_BASE_URL,
) -> str | None:
    cleaned = _clean_text(url)

    if cleaned is None:
        return None

    absolute = urljoin(base_url, cleaned)
    parsed = urlparse(absolute)
    host = parsed.hostname.casefold() if parsed.hostname else ""

    if host not in {
        "dynamitejobs.com",
        "www.dynamitejobs.com",
    }:
        return None

    segments = [
        segment
        for segment in parsed.path.split("/")
        if segment
    ]

    if (
        len(segments) != 4
        or segments[0] != "company"
        or segments[2] != "remote-job"
    ):
        return None

    if not segments[1] or not segments[3]:
        return None

    return urlunparse(
        (
            "https",
            "dynamitejobs.com",
            "/".join(
                [
                    "",
                    "company",
                    segments[1],
                    "remote-job",
                    segments[3],
                ]
            ),
            "",
            "",
            "",
        )
    )


def dynamite_external_id(
    canonical_url: str,
) -> tuple[str, str, str]:
    parsed = urlparse(canonical_url)
    segments = [
        segment
        for segment in parsed.path.split("/")
        if segment
    ]

    if (
        len(segments) != 4
        or segments[0] != "company"
        or segments[2] != "remote-job"
    ):
        raise ValueError(
            "Not a canonical Dynamite job URL."
        )

    company_slug = segments[1]
    job_slug = segments[3]

    return (
        f"{company_slug}/{job_slug}",
        company_slug,
        job_slug,
    )


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

        parts.extend(current.text_parts)

        if current.tag in {
            "a",
            "p",
            "span",
            "div",
            "li",
            "h1",
            "h2",
            "h3",
            "br",
            "section",
            "article",
        }:
            parts.append("\n")

        for child in current.children:
            visit(child)

        if current.tag in {
            "a",
            "p",
            "span",
            "div",
            "li",
            "h1",
            "h2",
            "h3",
            "section",
            "article",
        }:
            parts.append("\n")

    visit(node)

    return unescape(" ".join(parts))


def _visible_lines(
    text: str,
) -> list[str]:
    return _unique_strings(
        _clean_text(line)
        for line in re.split(r"[\n\r]+", text)
        if _clean_text(line) is not None
    )


def _clean_text(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    cleaned = " ".join(
        unescape(value).split()
    )

    return cleaned if cleaned else None


def _unique_strings(
    values,
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


def _card_node(
    anchor: _Node,
) -> _Node:
    node = anchor

    while node.parent is not None:
        text = _node_text(node)
        lines = _visible_lines(text)
        tag_class = " ".join(
            [
                node.tag,
                node.attrs.get("class", ""),
                node.attrs.get("data-testid", ""),
            ]
        ).casefold()

        if (
            len(lines) >= 3
            and (
                node.tag in {
                    "article",
                    "li",
                    "section",
                }
                or any(
                    token in tag_class
                    for token in (
                        "job",
                        "card",
                        "listing",
                    )
                )
            )
        ):
            return node

        node = node.parent

    return anchor.parent or anchor


def _index_hints(
    *,
    lines: list[str],
    title_hint: str | None,
) -> dict[str, Any]:
    employment = _first_employment_type(lines)
    salary = _first_salary_text(lines)
    opened = _first_opened_relative(lines)
    closing = _first_closing_relative(lines)
    closed = _first_matching(
        lines,
        r"\bthis job is closed\b",
    )

    company = None

    if title_hint is not None:
        for index, line in enumerate(lines):
            if line != title_hint:
                continue

            for candidate in lines[index + 1 :]:
                if _is_hint_noise(candidate):
                    continue

                company = candidate
                break

            break

    tags = []

    for line in lines:
        if line in {
            title_hint,
            company,
            employment,
            salary,
            opened,
            closing,
            closed,
        }:
            continue

        if _is_tag_like(line):
            tags.append(line)

    return {
        "company_hint": company,
        "employment_type_hint": employment,
        "salary_text": salary,
        "tags": _unique_strings(tags),
        "opened_relative": opened,
        "closing_relative": closing,
        "status_text": closed or opened or closing,
    }


def _is_hint_noise(
    value: str,
) -> bool:
    return (
        _first_employment_type([value]) is not None
        or _first_salary_text([value]) is not None
        or _first_opened_relative([value]) is not None
        or _first_closing_relative([value]) is not None
        or re.search(
            r"\b(view|apply|remote|job|new)\b",
            value,
            re.I,
        )
        is not None
    )


def _is_tag_like(
    value: str,
) -> bool:
    if len(value) > 40:
        return False

    return (
        re.search(
            r"[A-Za-z#.+]",
            value,
        )
        is not None
    )


def _first_employment_type(
    lines: list[str],
) -> str | None:
    for line in lines:
        if re.fullmatch(
            r"(Full[- ]?Time|Part[- ]?Time|"
            r"Contract|Freelance|Temporary|"
            r"Internship)",
            line,
            re.I,
        ):
            return line

    return None


def _first_salary_text(
    lines: list[str],
) -> str | None:
    for line in lines:
        if re.search(
            r"(\$|USD|EUR|GBP|salary|/year|"
            r"/yr|per year)",
            line,
            re.I,
        ):
            return line

    return None


def _first_opened_relative(
    lines: list[str],
) -> str | None:
    for line in lines:
        if re.search(
            r"^(New Job!?|Opened\s+\d+\s+"
            r"(day|days|week|weeks|month|months)"
            r"\s+ago)$",
            line,
            re.I,
        ):
            return line

    return None


def _first_closing_relative(
    lines: list[str],
) -> str | None:
    for line in lines:
        if re.search(
            r"^Closes\s+(in\s+\d+\s+"
            r"(day|days|week|weeks|month|months)"
            r"|today)$",
            line,
            re.I,
        ):
            return line

    return None


def _first_matching(
    lines: list[str],
    pattern: str,
) -> str | None:
    for line in lines:
        if re.search(
            pattern,
            line,
            re.I,
        ):
            return line

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

        raw = "".join(
            node.text_parts
        ).strip()

        if not raw:
            continue

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue

        posting = _find_json_ld_jobposting(
            parsed
        )

        if posting is not None:
            return posting

    return {}


def _find_json_ld_jobposting(
    value: Any,
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
            == "jobposting"
            for item in types
        ):
            return value

        graph = value.get("@graph")

        if isinstance(graph, list):
            for item in graph:
                found = (
                    _find_json_ld_jobposting(
                        item
                    )
                )

                if found is not None:
                    return found

    elif isinstance(value, list):
        for item in value:
            found = _find_json_ld_jobposting(
                item
            )

            if found is not None:
                return found

    return None


def _json_string(
    value: Any,
    key: str,
) -> str | None:
    if not isinstance(value, dict):
        return None

    raw = value.get(key)

    if isinstance(raw, str):
        return raw

    return None


def _organization_dict(
    json_ld: dict[str, Any],
) -> dict[str, Any]:
    organization = json_ld.get(
        "hiringOrganization"
    )

    return (
        organization
        if isinstance(organization, dict)
        else {}
    )


def _organization_name(
    value: Any,
) -> str | None:
    if isinstance(value, dict):
        return _clean_text(
            value.get("name")
            if isinstance(
                value.get("name"),
                str,
            )
            else None
        )

    if isinstance(value, str):
        return _clean_text(value)

    return None


def _html_to_text(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    root = _parse_html(value)

    return _clean_text(
        _node_text(root)
    )


def _description_from_html(
    root: _Node,
) -> str | None:
    candidates: list[tuple[int, str]] = []

    for node in _iter_nodes(root):
        marker = " ".join(
            [
                node.attrs.get("class", ""),
                node.attrs.get("id", ""),
                node.attrs.get("data-testid", ""),
            ]
        ).casefold()

        if not any(
            token in marker
            for token in (
                "description",
                "job-content",
                "job_description",
                "content",
            )
        ):
            continue

        text = _clean_text(
            _node_text(node)
        )

        if text is not None:
            candidates.append(
                (
                    len(text),
                    text,
                )
            )

    if not candidates:
        return None

    candidates.sort(
        reverse=True
    )

    return candidates[0][1]


def _location_from_json_ld(
    json_ld: dict[str, Any],
) -> str | None:
    for key in (
        "applicantLocationRequirements",
        "jobLocation",
        "jobLocationType",
    ):
        value = json_ld.get(key)
        location = _location_value(value)

        if location is not None:
            return location

    return None


def _location_value(
    value: Any,
) -> str | None:
    if isinstance(value, str):
        return _clean_text(value)

    if isinstance(value, list):
        values = [
            _location_value(item)
            for item in value
        ]

        return "; ".join(
            item
            for item in values
            if item is not None
        ) or None

    if isinstance(value, dict):
        for key in (
            "name",
            "address",
        ):
            result = _location_value(
                value.get(key)
            )

            if result is not None:
                return result

        parts = [
            _clean_text(
                value.get(key)
                if isinstance(
                    value.get(key),
                    str,
                )
                else None
            )
            for key in (
                "addressLocality",
                "addressRegion",
                "addressCountry",
            )
        ]

        return "; ".join(
            part
            for part in parts
            if part is not None
        ) or None

    return None


def _employment_type_from_json_ld(
    json_ld: dict[str, Any],
) -> str | None:
    value = json_ld.get(
        "employmentType"
    )

    if isinstance(value, str):
        return _clean_text(value)

    if isinstance(value, list):
        return ", ".join(
            _unique_strings(
                item
                for item in value
                if isinstance(item, str)
            )
        ) or None

    return None


def _salary_from_json_ld(
    json_ld: dict[str, Any],
) -> str | None:
    value = json_ld.get(
        "baseSalary"
    )

    if isinstance(value, str):
        return _clean_text(value)

    if not isinstance(value, dict):
        return None

    amount = value.get("value")
    currency = _clean_text(
        value.get("currency")
        if isinstance(
            value.get("currency"),
            str,
        )
        else None
    )

    if isinstance(amount, dict):
        min_value = amount.get("minValue")
        max_value = amount.get("maxValue")
        unit = _clean_text(
            amount.get("unitText")
            if isinstance(
                amount.get("unitText"),
                str,
            )
            else None
        )

        parts = [
            str(part)
            for part in (
                min_value,
                max_value,
            )
            if part is not None
        ]

        if parts:
            return " ".join(
                part
                for part in (
                    currency,
                    "-".join(parts),
                    unit,
                )
                if part
            )

    return None


def _skills_from_json_ld(
    json_ld: dict[str, Any],
) -> list[str]:
    values: list[str] = []

    for key in (
        "skills",
        "occupationalCategory",
    ):
        raw = json_ld.get(key)

        if isinstance(raw, str):
            values.extend(
                item.strip()
                for item in re.split(
                    r"[,;]",
                    raw,
                )
            )

        elif isinstance(raw, list):
            values.extend(
                item
                for item in raw
                if isinstance(item, str)
            )

    return _unique_strings(values)


def _apply_url(
    root: _Node,
    *,
    canonical_url: str,
) -> str | None:
    candidates: list[str] = []

    for node in _iter_nodes(root):
        if node.tag != "a":
            continue

        href = node.attrs.get("href")
        absolute = _normalize_url(href)

        if absolute is None:
            continue

        text = _clean_text(
            _node_text(node)
        ) or ""

        if (
            _is_supported_external_apply_url(
                absolute
            )
            or (
                _is_external_url(absolute)
                and re.search(
                    r"\b(apply|application|job)\b",
                    text,
                    re.I,
                )
            )
        ):
            candidates.append(absolute)

    canonical_normalized = _normalize_url(
        canonical_url
    )

    for candidate in _unique_strings(
        candidates
    ):
        if candidate != canonical_normalized:
            return candidate

    return None


def _is_supported_external_apply_url(
    url: str,
) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname.casefold() if parsed.hostname else ""

    return (
        host.endswith("greenhouse.io")
        or host == "jobs.ashbyhq.com"
        or host == "jobs.lever.co"
        or host == "apply.workable.com"
        or host == "jobs.smartrecruiters.com"
        or host.endswith(".bamboohr.com")
    )


def _external_url(
    value: str | None,
) -> str | None:
    normalized = _normalize_url(value)

    if normalized is None:
        return None

    return (
        normalized
        if _is_external_url(normalized)
        else None
    )


def _is_external_url(
    url: str,
) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname.casefold() if parsed.hostname else ""

    return host not in {
        "",
        "dynamitejobs.com",
        "www.dynamitejobs.com",
    }


def _normalize_url(
    value: str | None,
) -> str | None:
    cleaned = _clean_text(value)

    if cleaned is None:
        return None

    absolute = urljoin(
        DYNAMITEJOBS_BASE_URL,
        cleaned,
    )
    parsed = urlparse(absolute)

    if parsed.scheme not in {
        "http",
        "https",
    }:
        return None

    if parsed.hostname is None:
        return None

    return urlunparse(
        (
            parsed.scheme.casefold(),
            parsed.netloc.casefold(),
            parsed.path.rstrip("/"),
            "",
            parsed.query,
            "",
        )
    )


def _parse_source_datetime(
    value: str | None,
) -> datetime | None:
    cleaned = _clean_text(value)

    if cleaned is None:
        return None

    normalized = (
        cleaned[:-1] + "+00:00"
        if cleaned.endswith("Z")
        else cleaned
    )

    try:
        parsed = datetime.fromisoformat(
            normalized
        )
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=UTC
        )

    return parsed.astimezone(UTC)


def _heading_text(
    root: _Node,
    tag: str,
) -> str | None:
    for node in _iter_nodes(root):
        if node.tag == tag:
            text = _clean_text(
                _node_text(node)
            )

            if text is not None:
                return text

    return None


def _company_from_lines(
    *,
    lines: list[str],
    title: str | None,
) -> str | None:
    if title is None:
        return None

    for index, line in enumerate(lines):
        if line != title:
            continue

        for candidate in lines[index + 1 :]:
            if _is_hint_noise(candidate):
                continue

            return candidate

    return None


def _labeled_line_value(
    lines: list[str],
    label: str,
) -> str | None:
    pattern = re.compile(
        rf"^{re.escape(label)}\s*:?\s+(.+)$",
        re.I,
    )

    for line in lines:
        match = pattern.match(line)

        if match:
            return _clean_text(
                match.group(1)
            )

    return None
