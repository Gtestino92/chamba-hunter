from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
import re
from typing import Any
from urllib.parse import (
    parse_qs,
    urlsplit,
    urlunsplit,
)

import httpx

from chamba_hunter.domain.enums import WorkplaceType


HN_API_BASE_URL = "https://hacker-news.firebaseio.com/v0"
HN_ITEM_URL = "https://news.ycombinator.com/item?id={item_id}"
WHO_IS_HIRING_USER = "whoishiring"
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_MAX_SUBMISSIONS_TO_SCAN = 80

_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

_WHO_IS_HIRING_TITLE_RE = re.compile(
    r"^Ask HN: Who is hiring\? "
    r"\(("
    + "|".join(_MONTHS)
    + r") \d{4}\)$"
)
_URL_RE = re.compile(
    r"https?://[^\s<>()\"']+",
    re.IGNORECASE,
)
_COMPENSATION_RE = re.compile(
    r"(\$|€|£|¥|\b\d{2,4}\s?k\b|salary|equity|compensation)",
    re.IGNORECASE,
)
_EMPLOYMENT_PATTERNS: tuple[
    tuple[re.Pattern[str], str],
    ...
] = (
    (
        re.compile(
            r"\bfull[\s-]?time\b",
            re.IGNORECASE,
        ),
        "Full-time",
    ),
    (
        re.compile(
            r"\bpart[\s-]?time\b",
            re.IGNORECASE,
        ),
        "Part-time",
    ),
    (
        re.compile(
            r"\b(contract|contractor|freelance)\b",
            re.IGNORECASE,
        ),
        "Contract",
    ),
    (
        re.compile(
            r"\b(internship|intern)\b",
            re.IGNORECASE,
        ),
        "Internship",
    ),
)
_WORKPLACE_PATTERNS: tuple[
    tuple[re.Pattern[str], WorkplaceType],
    ...
] = (
    (
        re.compile(
            r"\bremote\b",
            re.IGNORECASE,
        ),
        WorkplaceType.REMOTE,
    ),
    (
        re.compile(
            r"\bhybrid\b",
            re.IGNORECASE,
        ),
        WorkplaceType.HYBRID,
    ),
    (
        re.compile(
            r"\b(on[\s-]?site|onsite)\b",
            re.IGNORECASE,
        ),
        WorkplaceType.ONSITE,
    ),
)
_LOCATION_HINT_RE = re.compile(
    r"("
    r"\b(remote|hybrid|onsite|on-site)\b|"
    r"\b(us|usa|u\.s\.|united states|canada|europe|emea|"
    r"latam|latin america|argentina|brazil|mexico|uk|"
    r"united kingdom|germany|france|spain)\b|"
    r","
    r")",
    re.IGNORECASE,
)
_ROLE_HINT_RE = re.compile(
    r"\b("
    r"engineer|developer|architect|designer|manager|"
    r"scientist|analyst|product|platform|backend|front[ -]?end|"
    r"full[ -]?stack|devops|sre|security|data|infra|"
    r"machine learning|ml|ai|founding|staff|principal|senior"
    r")\b",
    re.IGNORECASE,
)
_APPLY_URL_HINT_RE = re.compile(
    r"(apply|applicant|jobs?|careers?|greenhouse|lever|"
    r"ashby|workable|smartrecruiters|bamboohr|teamtailor)",
    re.IGNORECASE,
)
_COMPANY_WEBSITE_EXCLUDED_HOSTS = {
    "news.ycombinator.com",
    "hacker-news.firebaseio.com",
    "greenhouse.io",
    "boards.greenhouse.io",
    "job-boards.greenhouse.io",
    "lever.co",
    "jobs.lever.co",
    "ashbyhq.com",
    "jobs.ashbyhq.com",
    "workable.com",
    "apply.workable.com",
    "smartrecruiters.com",
    "jobs.smartrecruiters.com",
    "bamboohr.com",
    "teamtailor.com",
}


class HnWhoIsHiringError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class HnHiringThread:
    id: int
    title: str
    author: str
    posted_at: datetime | None
    comment_ids: tuple[int, ...]
    raw_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class HnHiringPost:
    thread_id: int
    thread_title: str
    comment_id: int
    author: str | None
    posted_at: datetime | None
    company_name: str
    title: str
    description: str
    location_text: str | None
    workplace_type: WorkplaceType
    employment_type: str | None
    source_url: str
    apply_url: str | None
    website_url: str | None
    extracted_urls: tuple[str, ...]
    raw_html: str
    raw_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class HnThreadFetch:
    thread: HnHiringThread
    direct_comments_discovered: int
    comments_fetched: int
    deleted_dead_skipped: int
    invalid_skipped: int
    fetch_failures: int
    posts: tuple[HnHiringPost, ...]


class HnWhoIsHiringClient:
    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_submissions_to_scan: int = (
            DEFAULT_MAX_SUBMISSIONS_TO_SCAN
        ),
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError(
                "timeout_seconds must be positive."
            )

        if max_submissions_to_scan < 1:
            raise ValueError(
                "max_submissions_to_scan must be at least 1."
            )

        self.timeout_seconds = timeout_seconds
        self.max_submissions_to_scan = (
            max_submissions_to_scan
        )
        self.transport = transport

    def fetch_latest_thread(
        self,
        *,
        limit: int | None = None,
    ) -> HnThreadFetch:
        with self._http_client() as client:
            user = _get_json(
                client,
                "/user/whoishiring.json",
            )

            if not isinstance(user, dict):
                raise HnWhoIsHiringError(
                    "HN whoishiring user payload is invalid."
                )

            submitted = user.get("submitted")

            if not isinstance(submitted, list):
                raise HnWhoIsHiringError(
                    "HN whoishiring user payload is missing "
                    "submitted ids."
                )

            candidates: list[HnHiringThread] = []

            for raw_id in submitted[
                : self.max_submissions_to_scan
            ]:
                item_id = _coerce_item_id(
                    raw_id
                )

                if item_id is None:
                    continue

                item = _get_item(
                    client,
                    item_id,
                )
                thread = _parse_thread(
                    item
                )

                if thread is not None:
                    candidates.append(
                        thread
                    )

            if not candidates:
                raise HnWhoIsHiringError(
                    "No valid recent HN 'Who is hiring?' "
                    "thread found in whoishiring submissions."
                )

            thread = max(
                candidates,
                key=lambda candidate: (
                    candidate.posted_at
                    or datetime.min.replace(
                        tzinfo=UTC
                    ),
                    candidate.id,
                ),
            )

            return _fetch_thread_comments(
                client=client,
                thread=thread,
                limit=limit,
            )

    def fetch_thread(
        self,
        thread_id: int,
        *,
        limit: int | None = None,
    ) -> HnThreadFetch:
        with self._http_client() as client:
            item = _get_item(
                client,
                thread_id,
            )
            thread = _parse_thread(
                item
            )

            if thread is None:
                raise HnWhoIsHiringError(
                    "Explicit HN item is not a valid "
                    "'Ask HN: Who is hiring?' thread."
                )

            return _fetch_thread_comments(
                client=client,
                thread=thread,
                limit=limit,
            )

    def _http_client(
        self,
    ) -> httpx.Client:
        return httpx.Client(
            base_url=HN_API_BASE_URL,
            timeout=self.timeout_seconds,
            follow_redirects=True,
            transport=self.transport,
            headers={
                "User-Agent": (
                    "chamba-hunter/0.2 "
                    "(official Hacker News API consumer)"
                ),
                "Accept": "application/json",
            },
        )


def parse_hn_hiring_comment(
    *,
    thread: HnHiringThread,
    comment: dict[str, Any],
) -> HnHiringPost | None:
    if comment.get("type") != "comment":
        return None

    if comment.get("deleted") is True or comment.get("dead") is True:
        return None

    comment_id = _coerce_item_id(
        comment.get("id")
    )

    if comment_id is None:
        return None

    raw_html = comment.get("text")

    if not isinstance(raw_html, str):
        return None

    parsed_html = _parse_comment_html(
        raw_html
    )
    description = _clean_multiline_text(
        parsed_html.text
    )

    if description is None:
        return None

    first_line = _first_logical_line(
        description
    )

    if first_line is None:
        return None

    header_segments = [
        segment
        for segment in (
            _clean_segment(segment)
            for segment in first_line.split("|")
        )
        if segment is not None
    ]

    if not header_segments:
        return None

    company_name = _clean_company_name(
        header_segments[0]
    )

    if company_name is None:
        return None

    all_urls = _unique_urls(
        [
            *parsed_html.urls,
            *_urls_from_text(description),
        ]
    )
    apply_url = _select_apply_url(
        all_urls
    )
    website_url = _select_website_url(
        all_urls,
        apply_url=apply_url,
    )
    workplace_type = _workplace_type(
        header_segments,
        description,
    )
    employment_type = _employment_type(
        header_segments,
    )
    location_text = _location_text(
        header_segments,
    )
    title = _title(
        company_name=company_name,
        segments=header_segments[1:],
    )

    return HnHiringPost(
        thread_id=thread.id,
        thread_title=thread.title,
        comment_id=comment_id,
        author=_clean_text(
            comment.get("by")
        ),
        posted_at=_unix_datetime(
            comment.get("time")
        ),
        company_name=company_name,
        title=title,
        description=description,
        location_text=location_text,
        workplace_type=workplace_type,
        employment_type=employment_type,
        source_url=HN_ITEM_URL.format(
            item_id=comment_id
        ),
        apply_url=apply_url,
        website_url=website_url,
        extracted_urls=all_urls,
        raw_html=raw_html,
        raw_payload={
            "source": "hn_who_is_hiring",
            "thread": thread.raw_payload,
            "comment": comment,
            "normalized": {
                "company_name": company_name,
                "title": title,
                "location_text": location_text,
                "workplace_type": (
                    workplace_type.value
                ),
                "employment_type": employment_type,
                "extracted_urls": list(
                    all_urls
                ),
                "apply_url": apply_url,
                "website_url": website_url,
            },
        },
    )


def is_who_is_hiring_thread(
    item: dict[str, Any],
) -> bool:
    return (
        item.get("type") == "story"
        and item.get("by") == WHO_IS_HIRING_USER
        and isinstance(item.get("title"), str)
        and _WHO_IS_HIRING_TITLE_RE.match(
            str(item["title"])
        )
        is not None
    )


def _fetch_thread_comments(
    *,
    client: httpx.Client,
    thread: HnHiringThread,
    limit: int | None,
) -> HnThreadFetch:
    if limit is not None and limit < 1:
        raise ValueError(
            "limit must be at least 1."
        )

    comment_ids = (
        thread.comment_ids[:limit]
        if limit is not None
        else thread.comment_ids
    )
    comments_fetched = 0
    deleted_dead_skipped = 0
    invalid_skipped = 0
    fetch_failures = 0
    posts: list[HnHiringPost] = []

    for comment_id in comment_ids:
        try:
            comment = _get_item(
                client,
                comment_id,
            )
        except httpx.HTTPError:
            fetch_failures += 1
            continue

        comments_fetched += 1

        if (
            comment.get("deleted") is True
            or comment.get("dead") is True
        ):
            deleted_dead_skipped += 1
            continue

        post = parse_hn_hiring_comment(
            thread=thread,
            comment=comment,
        )

        if post is None:
            invalid_skipped += 1
            continue

        posts.append(post)

    return HnThreadFetch(
        thread=thread,
        direct_comments_discovered=len(
            thread.comment_ids
        ),
        comments_fetched=comments_fetched,
        deleted_dead_skipped=(
            deleted_dead_skipped
        ),
        invalid_skipped=invalid_skipped,
        fetch_failures=fetch_failures,
        posts=tuple(posts),
    )


def _get_json(
    client: httpx.Client,
    path: str,
) -> Any:
    response = client.get(path)
    response.raise_for_status()
    return response.json()


def _get_item(
    client: httpx.Client,
    item_id: int,
) -> dict[str, Any]:
    payload = _get_json(
        client,
        f"/item/{item_id}.json",
    )

    if not isinstance(payload, dict):
        raise HnWhoIsHiringError(
            f"HN item {item_id} payload is invalid."
        )

    return payload


def _parse_thread(
    item: dict[str, Any],
) -> HnHiringThread | None:
    if not is_who_is_hiring_thread(
        item
    ):
        return None

    item_id = _coerce_item_id(
        item.get("id")
    )
    title = _clean_text(
        item.get("title")
    )
    author = _clean_text(
        item.get("by")
    )

    if (
        item_id is None
        or title is None
        or author is None
    ):
        return None

    kids = item.get("kids")
    comment_ids: list[int] = []

    if isinstance(kids, list):
        for raw_id in kids:
            comment_id = _coerce_item_id(
                raw_id
            )

            if comment_id is not None:
                comment_ids.append(
                    comment_id
                )

    return HnHiringThread(
        id=item_id,
        title=title,
        author=author,
        posted_at=_unix_datetime(
            item.get("time")
        ),
        comment_ids=tuple(
            comment_ids
        ),
        raw_payload=item,
    )


def _parse_comment_html(
    raw_html: str,
) -> "_HnCommentHtml":
    parser = _HnHtmlParser()
    parser.feed(raw_html)

    return _HnCommentHtml(
        text=parser.text,
        urls=tuple(
            parser.urls
        ),
    )


def _title(
    *,
    company_name: str,
    segments: list[str],
) -> str:
    role_segments: list[str] = []

    for segment in segments:
        if _is_bare_url(
            segment
        ):
            continue

        if _employment_type_for_segment(
            segment
        ) is not None:
            continue

        if _is_compensation(
            segment
        ):
            continue

        if _is_location_segment(
            segment
        ):
            continue

        if not _looks_role_like(
            segment
        ):
            continue

        role_segments.append(
            segment
        )

    title = _clean_text(
        ", ".join(role_segments)
    )

    return (
        title
        if title is not None
        else f"Hiring at {company_name}"
    )


def _location_text(
    segments: list[str],
) -> str | None:
    locations: list[str] = []

    for segment in segments[1:]:
        if _is_location_segment(
            segment
        ):
            locations.append(
                segment
            )

    return _join_unique(
        locations
    )


def _workplace_type(
    segments: list[str],
    description: str,
) -> WorkplaceType:
    header = " | ".join(
        segments
    )

    for pattern, workplace_type in _WORKPLACE_PATTERNS:
        if pattern.search(header):
            return workplace_type

    return WorkplaceType.UNKNOWN


def _employment_type(
    segments: list[str],
) -> str | None:
    for segment in segments[1:]:
        employment_type = (
            _employment_type_for_segment(
                segment
            )
        )

        if employment_type is not None:
            return employment_type

    return None


def _employment_type_for_segment(
    segment: str,
) -> str | None:
    for pattern, label in _EMPLOYMENT_PATTERNS:
        if pattern.search(segment):
            return label

    return None


def _is_location_segment(
    segment: str,
) -> bool:
    if _ROLE_HINT_RE.search(segment):
        return False

    return _LOCATION_HINT_RE.search(segment) is not None


def _is_compensation(
    segment: str,
) -> bool:
    return _COMPENSATION_RE.search(segment) is not None


def _looks_role_like(
    segment: str,
) -> bool:
    if _ROLE_HINT_RE.search(segment):
        return True

    if "," in segment and len(segment) <= 80:
        return True

    return False


def _select_apply_url(
    urls: tuple[str, ...],
) -> str | None:
    for url in urls:
        parsed = urlsplit(url)
        searchable = " ".join(
            (
                parsed.netloc,
                parsed.path,
                parsed.query,
            )
        )

        if _APPLY_URL_HINT_RE.search(
            searchable
        ):
            return url

    return None


def _select_website_url(
    urls: tuple[str, ...],
    *,
    apply_url: str | None,
) -> str | None:
    for url in urls:
        if url == apply_url and _is_ats_url(url):
            continue

        if _is_hn_url(url):
            continue

        if _is_ats_url(url):
            continue

        return url

    return None


def _is_ats_url(
    url: str,
) -> bool:
    host = (
        urlsplit(url).hostname
        or ""
    ).casefold()

    return any(
        host == excluded
        or host.endswith(
            "." + excluded
        )
        for excluded in _COMPANY_WEBSITE_EXCLUDED_HOSTS
    )


def _is_hn_url(
    url: str,
) -> bool:
    host = (
        urlsplit(url).hostname
        or ""
    ).casefold()

    return host in {
        "news.ycombinator.com",
        "hacker-news.firebaseio.com",
    }


def _urls_from_text(
    text: str,
) -> tuple[str, ...]:
    return tuple(
        _normalize_url_match(match.group(0))
        for match in _URL_RE.finditer(text)
    )


def _unique_urls(
    urls: list[str],
) -> tuple[str, ...]:
    unique: list[str] = []
    seen: set[str] = set()

    for url in urls:
        cleaned = _clean_url(
            url
        )

        if cleaned is None:
            continue

        key = cleaned.casefold()

        if key in seen:
            continue

        seen.add(key)
        unique.append(cleaned)

    return tuple(unique)


def _clean_url(
    url: str,
) -> str | None:
    cleaned = _normalize_url_match(
        url
    )
    parsed = urlsplit(cleaned)

    if parsed.scheme.casefold() not in {
        "http",
        "https",
    }:
        return None

    if parsed.hostname is None:
        return None

    if (
        parsed.hostname.casefold()
        == "news.ycombinator.com"
    ):
        query = parse_qs(
            parsed.query
        )

        if "id" not in query:
            return None

    return urlunsplit(
        (
            parsed.scheme.casefold(),
            parsed.netloc,
            parsed.path.rstrip("/"),
            parsed.query,
            "",
        )
    )


def _normalize_url_match(
    url: str,
) -> str:
    return url.rstrip(".,;:!?)\"]}'")


def _is_bare_url(
    value: str,
) -> bool:
    return _clean_url(value) == value.rstrip("/")


def _clean_company_name(
    value: str,
) -> str | None:
    cleaned = _clean_segment(
        value
    )

    if cleaned is None:
        return None

    cleaned = re.sub(
        r"^\s*(company|employer)\s*:\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()

    if not cleaned:
        return None

    if len(cleaned) > 100:
        return None

    if _is_bare_url(cleaned):
        return None

    if "@" in cleaned:
        return None

    if _employment_type_for_segment(
        cleaned
    ) is not None:
        return None

    if _is_location_segment(
        cleaned
    ):
        return None

    return cleaned


def _clean_segment(
    value: str,
) -> str | None:
    cleaned = _clean_text(
        value
    )

    if cleaned is None:
        return None

    cleaned = cleaned.strip(
        " -*•—–"
    ).strip()

    return cleaned or None


def _first_logical_line(
    text: str,
) -> str | None:
    for line in text.splitlines():
        cleaned = _clean_text(
            line
        )

        if cleaned is not None:
            return cleaned

    return None


def _clean_multiline_text(
    value: str,
) -> str | None:
    lines: list[str] = []

    for line in value.splitlines():
        cleaned = _clean_text(
            line
        )

        if cleaned is None:
            if lines and lines[-1] != "":
                lines.append("")

            continue

        lines.append(cleaned)

    while lines and lines[-1] == "":
        lines.pop()

    cleaned = "\n".join(
        lines
    ).strip()

    return cleaned or None


def _clean_text(
    value: Any,
) -> str | None:
    if not isinstance(value, str):
        return None

    cleaned = " ".join(
        value.split()
    ).strip()

    return cleaned or None


def _join_unique(
    values: list[str],
) -> str | None:
    parts: list[str] = []
    seen: set[str] = set()

    for value in values:
        cleaned = _clean_text(
            value
        )

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


def _unix_datetime(
    value: Any,
) -> datetime | None:
    if not isinstance(value, int):
        return None

    return datetime.fromtimestamp(
        value,
        tz=UTC,
    )


def _coerce_item_id(
    value: Any,
) -> int | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value

    if isinstance(value, str) and value.isdigit():
        return int(value)

    return None


@dataclass(frozen=True, slots=True)
class _HnCommentHtml:
    text: str
    urls: tuple[str, ...]


class _HnHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(
            convert_charrefs=True
        )
        self.parts: list[str] = []
        self.urls: list[str] = []
        self._anchor_href: str | None = None

    @property
    def text(self) -> str:
        return "".join(
            self.parts
        )

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        normalized = tag.casefold()

        if normalized in {
            "p",
            "br",
            "div",
            "li",
        }:
            self._newline()

        if normalized == "a":
            attributes = dict(attrs)
            self._anchor_href = (
                attributes.get("href")
            )

            if self._anchor_href is not None:
                self.urls.append(
                    self._anchor_href
                )

    def handle_endtag(
        self,
        tag: str,
    ) -> None:
        normalized = tag.casefold()

        if normalized in {
            "p",
            "div",
            "li",
        }:
            self._newline()

        if normalized == "a":
            self._anchor_href = None

    def handle_data(
        self,
        data: str,
    ) -> None:
        self.parts.append(data)

    def _newline(self) -> None:
        if not self.parts:
            return

        if not self.parts[-1].endswith(
            "\n"
        ):
            self.parts.append("\n")
