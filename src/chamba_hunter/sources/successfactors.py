from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
import re
from typing import Any
from urllib.parse import (
    parse_qs,
    urlencode,
    urljoin,
    urlsplit,
    urlunsplit,
)

import httpx


MAX_PAGES = 20
DEFAULT_PAGE_SIZE = 25
EMPTY_BOARD_MARKERS = (
    "no hay puestos vacantes",
    "no open jobs",
    "no jobs found",
    "no jobs available",
    "no hay resultados",
    "0 puestos",
)


@dataclass(frozen=True, slots=True)
class SuccessFactorsDetection:
    external_identifier: str
    board_url: str
    evidence: str
    variant: str


@dataclass(frozen=True, slots=True)
class SuccessFactorsJobLink:
    external_id: str
    title_hint: str | None
    location_hint: str | None
    job_url: str


@dataclass(frozen=True, slots=True)
class SuccessFactorsJobDetail:
    external_id: str
    title: str
    description: str | None
    location_text: str | None
    employment_type: str | None
    published_at: datetime | None
    job_url: str
    apply_url: str | None
    raw_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class SuccessFactorsJobsFetch:
    http_status: int
    total: int
    jobs: list[SuccessFactorsJobDetail]
    snapshot_complete: bool
    variant: str
    error_type: str | None = None
    error_message: str | None = None


class _ReferenceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: list[tuple[str, str]] = []
        self.forms: list[str] = []
        self.resources: list[str] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = {
            key.casefold(): value
            for key, value in attrs
            if value is not None
        }
        normalized = tag.casefold()

        if normalized == "a":
            href = attributes.get("href")
            if href:
                self._href = href
                self._text = []
            return

        if normalized == "form":
            action = attributes.get("action")
            if action:
                self.forms.append(action)
            return

        if normalized in {"script", "iframe", "img", "link"}:
            value = (
                attributes.get("src")
                or attributes.get("href")
            )
            if value:
                self.resources.append(value)

    def handle_endtag(self, tag: str) -> None:
        if (
            self._href is None
            or tag.casefold() != "a"
        ):
            return

        self.anchors.append(
            (
                self._href,
                " ".join(self._text).strip(),
            )
        )
        self._href = None
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is None:
            return

        text = " ".join(data.split())
        if text:
            self._text.append(text)


class SuccessFactorsClient:
    def __init__(
        self,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.timeout_seconds = timeout_seconds

    def fetch_jobs(
        self,
        board_url: str,
        *,
        client: httpx.Client | None = None,
    ) -> SuccessFactorsJobsFetch:
        if client is None:
            with httpx.Client(
                timeout=self.timeout_seconds,
                follow_redirects=True,
                headers={
                    "User-Agent": "chamba-hunter/0.1"
                },
            ) as owned_client:
                return self._fetch_with_client(
                    client=owned_client,
                    board_url=board_url,
                )

        return self._fetch_with_client(
            client=client,
            board_url=board_url,
        )

    def _fetch_with_client(
        self,
        *,
        client: httpx.Client,
        board_url: str,
    ) -> SuccessFactorsJobsFetch:
        normalized_board_url = normalize_board_url(
            board_url
        )
        response = client.get(normalized_board_url)
        response.raise_for_status()

        variant = (
            "DIRECT_LEGACY"
            if _is_direct_successfactors_host(
                normalized_board_url
            )
            else "CAREER_SITE_BUILDER"
        )
        search_url = _discover_search_url(
            base_url=str(response.url),
            html=response.text,
        )

        if search_url is None:
            links = _parse_job_links(
                page_url=str(response.url),
                html=response.text,
            )
            explicit_empty = _explicitly_empty(
                response.text
            )
            if not links:
                return SuccessFactorsJobsFetch(
                    http_status=response.status_code,
                    total=0,
                    jobs=[],
                    snapshot_complete=explicit_empty,
                    variant=variant,
                    error_type=(
                        None
                        if explicit_empty
                        else "PARSING_ERROR"
                    ),
                    error_message=(
                        None
                        if explicit_empty
                        else (
                            "No search URL or "
                            "recognizable job links found."
                        )
                    ),
                )
            total_hint = _parse_total_hint(
                response.text
            )
            page_size = _parse_page_size(
                response.text
            )
            record_count = _parse_record_count(
                response.text
            )
            pages = [
                _ListingPage(
                    url=str(response.url),
                    html=response.text,
                    links=links,
                    page_size=(
                        page_size
                        or record_count
                        or len(links)
                    ),
                    total_hint=total_hint,
                    record_count=(
                        record_count
                        or len(links)
                    ),
                    has_completeness_evidence=(
                        total_hint is not None
                        or page_size is not None
                        or record_count is not None
                    ),
                )
            ]
        else:
            pages = self._fetch_listing_pages(
                client=client,
                search_url=search_url,
            )

        links = _merge_links(pages)
        listing_complete = _listing_complete(
            pages=pages,
            link_count=len(links),
        )

        jobs: list[
            SuccessFactorsJobDetail
        ] = []
        detail_errors: list[str] = []

        for link in links:
            try:
                jobs.append(
                    self._fetch_detail(
                        client=client,
                        link=link,
                    )
                )
            except Exception as exc:
                detail_errors.append(
                    (
                        f"{link.external_id}: "
                        f"{type(exc).__name__}: {exc}"
                    )
                )

        snapshot_complete = (
            listing_complete
            and not detail_errors
        )
        error_type = None
        error_message = None
        if detail_errors:
            error_type = "DETAIL_FETCH_ERROR"
            error_message = "; ".join(
                detail_errors[:3]
            )
        elif not listing_complete:
            error_type = "PARTIAL_SNAPSHOT"
            error_message = (
                "Listing did not provide enough "
                "evidence for a complete board "
                "snapshot."
            )

        return SuccessFactorsJobsFetch(
            http_status=response.status_code,
            total=len(links),
            jobs=jobs,
            snapshot_complete=snapshot_complete,
            variant=variant,
            error_type=error_type,
            error_message=error_message,
        )

    def _fetch_listing_pages(
        self,
        *,
        client: httpx.Client,
        search_url: str,
    ) -> list[_ListingPage]:
        pages: list[_ListingPage] = []
        seen_page_urls: set[str] = set()
        seen_job_ids: set[str] = set()
        current_startrow = 0
        page_size = DEFAULT_PAGE_SIZE
        total_hint: int | None = None

        for _page_index in range(MAX_PAGES):
            page_url = _with_startrow(
                search_url,
                current_startrow,
            )
            if page_url in seen_page_urls:
                break
            seen_page_urls.add(page_url)

            response = client.get(page_url)
            response.raise_for_status()
            links = _parse_job_links(
                page_url=str(response.url),
                html=response.text,
            )
            parsed_page_size = _parse_page_size(
                response.text
            )
            parsed_total_hint = _parse_total_hint(
                response.text
            )
            parsed_record_count = _parse_record_count(
                response.text
            )
            page = _ListingPage(
                url=str(response.url),
                html=response.text,
                links=links,
                page_size=(
                    parsed_page_size
                    or page_size
                ),
                total_hint=parsed_total_hint,
                record_count=(
                    parsed_record_count
                    if parsed_record_count
                    is not None
                    else len(links)
                ),
                has_completeness_evidence=(
                    parsed_page_size is not None
                    or parsed_total_hint is not None
                    or parsed_record_count is not None
                ),
            )
            pages.append(page)

            if page.total_hint is not None:
                total_hint = page.total_hint
            page_size = page.page_size

            page_ids = {
                link.external_id
                for link in links
            }
            new_ids = page_ids - seen_job_ids
            seen_job_ids.update(page_ids)

            if not links:
                break
            if total_hint is not None and len(
                seen_job_ids
            ) >= total_hint:
                break
            if page.record_count < page.page_size:
                break
            if not new_ids:
                break

            current_startrow += page.page_size

        return pages

    def _fetch_detail(
        self,
        *,
        client: httpx.Client,
        link: SuccessFactorsJobLink,
    ) -> SuccessFactorsJobDetail:
        response = client.get(link.job_url)
        response.raise_for_status()

        return _parse_job_detail(
            html=response.text,
            job_url=str(response.url),
            fallback=link,
        )


@dataclass(frozen=True, slots=True)
class _ListingPage:
    url: str
    html: str
    links: list[SuccessFactorsJobLink]
    page_size: int
    total_hint: int | None
    record_count: int
    has_completeness_evidence: bool


def detect_successfactors_from_url(
    url: str,
) -> SuccessFactorsDetection | None:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None

    if parsed.scheme not in {"http", "https"}:
        return None

    host = (parsed.hostname or "").casefold()
    path = parsed.path.casefold()

    if not _is_successfactors_host_path(
        host=host,
        path=path,
    ):
        return None

    board_url = normalize_board_url(url)
    return SuccessFactorsDetection(
        external_identifier=(
            successfactors_external_identifier(
                board_url
            )
        ),
        board_url=board_url,
        evidence=(
            "SuccessFactors public host/path: "
            f"{host}{path}"
        ),
        variant=(
            "DIRECT_LEGACY"
            if _is_direct_successfactors_host(url)
            else "CAREER_SITE_BUILDER"
        ),
    )


def detect_successfactors_from_html(
    *,
    page_url: str,
    html: str,
) -> SuccessFactorsDetection | None:
    normalized = (
        unescape(html)
        .replace("\\/", "/")
    )
    lower_html = normalized.casefold()

    structural_markers = [
        "rmkcdn.successfactors.com",
        "careersitebuilder",
        "/platform/js/j2w/",
        "/platform/js/search/",
        "job-tile-list",
        "data-careersite-propertyid",
        "successfactors recruiting",
    ]

    urls = [
        match.group(0).rstrip(".,);]}\"'")
        for match in re.finditer(
            r"https?://[^\s\"'<>]+",
            normalized,
            re.IGNORECASE,
        )
    ]

    has_host_evidence = any(
        detect_successfactors_from_url(url)
        is not None
        for url in urls
    )
    has_marker_evidence = any(
        marker in lower_html
        for marker in structural_markers
    )

    if not (
        has_host_evidence
        or has_marker_evidence
    ):
        return None

    board_url = normalize_board_url(page_url)
    return SuccessFactorsDetection(
        external_identifier=(
            successfactors_external_identifier(
                board_url
            )
        ),
        board_url=board_url,
        evidence=(
            "SuccessFactors Career Site "
            "Builder structural evidence"
        ),
        variant="CAREER_SITE_BUILDER",
    )


def successfactors_external_identifier(
    board_url: str,
) -> str:
    parsed = urlsplit(board_url)
    host = (parsed.hostname or "").casefold()
    path = parsed.path.rstrip("/")
    query = parse_qs(parsed.query)

    if _is_direct_successfactors_host(
        board_url
    ):
        company = (
            query.get("company", [None])[0]
            or query.get("companyName", [None])[0]
        )
        if company:
            return (
                f"{host}{path or '/career'}"
                f"?company={company.strip()}"
            )

    if path and path != "/":
        return f"{host}{path}"

    return host


def normalize_board_url(
    board_url: str,
) -> str:
    parsed = urlsplit(board_url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(
            f"Invalid SuccessFactors URL: '{board_url}'."
        )

    path = parsed.path or "/"
    if not path.endswith("/") and not parsed.query:
        path = f"{path}/"

    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            path,
            parsed.query,
            "",
        )
    )


def _is_successfactors_host_path(
    *,
    host: str,
    path: str,
) -> bool:
    if (
        host == "sapsf.com"
        or host.endswith(".sapsf.com")
    ):
        return True

    if (
        host == "successfactors.com"
        or host.endswith(
            ".successfactors.com"
        )
        or host.endswith(
            ".successfactors.eu"
        )
    ):
        return any(
            marker in path
            for marker in (
                "/career",
                "/sfcareer",
                "/careersection",
                "/platform/",
                "/doc/custom/",
            )
        ) or host.startswith(
            "career"
        ) or host.startswith(
            "performancemanager"
        )

    return False


def _is_direct_successfactors_host(
    url: str,
) -> bool:
    host = (
        urlsplit(url).hostname
        or ""
    ).casefold()
    return (
        host.startswith("career")
        and (
            host.endswith(
                ".successfactors.com"
            )
            or host.endswith(".sapsf.com")
        )
    )


def _discover_search_url(
    *,
    base_url: str,
    html: str,
) -> str | None:
    parsed_base = urlsplit(base_url)
    if "/search/" in parsed_base.path:
        return _with_empty_search_params(
            base_url
        )

    parser = _ReferenceParser()
    parser.feed(html)

    candidates = list(parser.forms) + [
        href
        for href, text in parser.anchors
        if (
            "search" in href.casefold()
            or "ver todas" in text.casefold()
            or "ofertas" in text.casefold()
        )
    ]

    for raw_url in candidates:
        resolved = urljoin(
            base_url,
            raw_url,
        )
        try:
            parsed = urlsplit(resolved)
        except ValueError:
            continue
        if parsed.scheme not in {
            "http",
            "https",
        }:
            continue
        if "/search/" in parsed.path:
            return _with_empty_search_params(
                resolved
            )

    return None


def _with_empty_search_params(
    url: str,
) -> str:
    parsed = urlsplit(url)
    query = parse_qs(parsed.query)
    query.setdefault(
        "createNewAlert",
        ["false"],
    )
    query.setdefault("q", [""])
    query.setdefault(
        "locationsearch",
        [""],
    )
    query.pop("startrow", None)
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urlencode(
                query,
                doseq=True,
            ),
            "",
        )
    )


def _with_startrow(
    url: str,
    startrow: int,
) -> str:
    parsed = urlsplit(url)
    query = parse_qs(parsed.query)
    if startrow > 0:
        query["startrow"] = [str(startrow)]
    else:
        query.pop("startrow", None)
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urlencode(
                query,
                doseq=True,
            ),
            "",
        )
    )


def _parse_job_links(
    *,
    page_url: str,
    html: str,
) -> list[SuccessFactorsJobLink]:
    by_id: dict[
        str,
        SuccessFactorsJobLink,
    ] = {}

    for match in re.finditer(
        r"<li\b(?P<attrs>[^>]*)"
        r"(?P<body>[\s\S]*?)</li>",
        html,
        re.IGNORECASE,
    ):
        attrs = match.group("attrs")
        body = match.group("body")
        if "job-tile" not in attrs.casefold():
            continue

        data_url = _attribute(attrs, "data-url")
        href = (
            data_url
            or _first_href(body)
        )
        if href is None:
            continue
        resolved = urljoin(page_url, href)
        external_id = extract_job_id(resolved)
        if external_id is None:
            continue

        link = SuccessFactorsJobLink(
            external_id=external_id,
            title_hint=_title_from_html(body),
            location_hint=_location_from_html(body),
            job_url=_job_url(resolved),
        )
        by_id[external_id] = link

    if by_id:
        return sorted(
            by_id.values(),
            key=lambda item: item.external_id,
        )

    parser = _ReferenceParser()
    parser.feed(html)
    for href, text in parser.anchors:
        resolved = urljoin(page_url, href)
        external_id = extract_job_id(resolved)
        if external_id is None:
            continue
        by_id[external_id] = (
            SuccessFactorsJobLink(
                external_id=external_id,
                title_hint=text or None,
                location_hint=None,
                job_url=_job_url(resolved),
            )
        )

    return sorted(
        by_id.values(),
        key=lambda item: item.external_id,
    )


def extract_job_id(
    url: str,
) -> str | None:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None

    query = parse_qs(parsed.query)
    for key in (
        "career_job_req_id",
        "jobid",
        "jobId",
        "jobReqId",
    ):
        values = query.get(key)
        if values and values[0].strip():
            return values[0].strip()

    match = re.search(
        r"/job/[^?#]*/(\d+)/?$",
        parsed.path,
        re.IGNORECASE,
    )
    if match:
        return match.group(1)

    match = re.search(
        r"\bjob-id-(\d+)\b",
        url,
        re.IGNORECASE,
    )
    if match:
        return match.group(1)

    return None


def _parse_job_detail(
    *,
    html: str,
    job_url: str,
    fallback: SuccessFactorsJobLink,
) -> SuccessFactorsJobDetail:
    title = (
        _itemprop_content(
            html,
            "title",
        )
        or _h1_text(html)
        or fallback.title_hint
    )
    if title is None or not title.strip():
        raise ValueError(
            "SuccessFactors job title is empty."
        )

    description = (
        _description_from_html(html)
    )
    location_text = (
        _location_from_meta(html)
        or fallback.location_hint
    )
    employment_type = _itemprop_content(
        html,
        "employmentType",
    )
    published_at = _published_at(
        _itemprop_content(
            html,
            "datePosted",
        )
    )
    apply_url = _apply_url(
        base_url=job_url,
        html=html,
    )

    return SuccessFactorsJobDetail(
        external_id=fallback.external_id,
        title=" ".join(title.split()),
        description=description,
        location_text=location_text,
        employment_type=employment_type,
        published_at=published_at,
        job_url=job_url,
        apply_url=apply_url,
        raw_payload={
            "provider": "SUCCESSFACTORS",
            "job_url": job_url,
            "apply_url": apply_url,
            "listing": {
                "title_hint": fallback.title_hint,
                "location_hint": fallback.location_hint,
            },
            "extracted": {
                "title": title,
                "location_text": location_text,
                "employment_type": employment_type,
                "date_posted": _itemprop_content(
                    html,
                    "datePosted",
                ),
            },
        },
    )


def _merge_links(
    pages: list[_ListingPage],
) -> list[SuccessFactorsJobLink]:
    by_id: dict[
        str,
        SuccessFactorsJobLink,
    ] = {}
    for page in pages:
        for link in page.links:
            by_id.setdefault(
                link.external_id,
                link,
            )
    return sorted(
        by_id.values(),
        key=lambda item: item.external_id,
    )


def _listing_complete(
    *,
    pages: list[_ListingPage],
    link_count: int,
) -> bool:
    if not pages:
        return False

    if (
        link_count == 0
        and any(
            _explicitly_empty(page.html)
            for page in pages
        )
    ):
        return True

    total_hints = [
        page.total_hint
        for page in pages
        if page.total_hint is not None
    ]
    if total_hints:
        return link_count >= max(total_hints)

    last = pages[-1]
    return (
        last.has_completeness_evidence
        and
        link_count > 0
        and last.record_count < last.page_size
    )


def _parse_page_size(
    html: str,
) -> int | None:
    match = re.search(
        r'data-per-page=["\'](\d+)["\']',
        html,
        re.IGNORECASE,
    )
    if match:
        return int(match.group(1))
    return None


def _parse_record_count(
    html: str,
) -> int | None:
    match = re.search(
        r'data-record-returned=["\'](\d+)["\']',
        html,
        re.IGNORECASE,
    )
    if match:
        return int(match.group(1))
    return None


def _parse_total_hint(
    html: str,
) -> int | None:
    text = " ".join(
        unescape(
            re.sub(r"<[^>]+>", " ", html)
        ).split()
    )
    match = re.search(
        r"\bde\s+(\d+)\s+puestos\b",
        text,
        re.IGNORECASE,
    )
    if match:
        return int(match.group(1))
    match = re.search(
        r"\bof\s+(\d+)\s+jobs\b",
        text,
        re.IGNORECASE,
    )
    if match:
        return int(match.group(1))
    return None


def _attribute(
    attrs: str,
    name: str,
) -> str | None:
    match = re.search(
        rf'{name}=["\']([^"\']+)["\']',
        attrs,
        re.IGNORECASE,
    )
    if match:
        return unescape(match.group(1))
    return None


def _first_href(html: str) -> str | None:
    match = re.search(
        r'href=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    )
    if match:
        return unescape(match.group(1))
    return None


def _title_from_html(
    html: str,
) -> str | None:
    for pattern in (
        r'data-careersite-propertyid=["\']title["\'][^>]*>([\s\S]*?)</',
        r'itemprop=["\']title["\'][^>]*>([\s\S]*?)</',
        r'class=["\'][^"\']*jobTitle[^"\']*["\'][^>]*>([\s\S]*?)</',
        r"<a\b[^>]*>([\s\S]*?)</a>",
    ):
        match = re.search(
            pattern,
            html,
            re.IGNORECASE,
        )
        if match:
            text = _strip_html(match.group(1))
            if text and text.casefold() != "título":
                return text

    text = _strip_html(html)
    text = re.sub(
        r"^\s*título\s+",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return text or None


def _location_from_html(
    html: str,
) -> str | None:
    for pattern in (
        r'data-careersite-propertyid=["\']location["\'][^>]*>([\s\S]*?)</',
        r'class=["\'][^"\']*jobLocation[^"\']*["\'][^>]*>([\s\S]*?)</',
    ):
        match = re.search(
            pattern,
            html,
            re.IGNORECASE,
        )
        if match:
            return _strip_html(
                match.group(1)
            )
    return None


def _itemprop_content(
    html: str,
    itemprop: str,
) -> str | None:
    escaped = re.escape(itemprop)
    meta_match = re.search(
        rf'<meta[^>]+itemprop=["\']{escaped}["\'][^>]+content=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    )
    if meta_match:
        return " ".join(
            unescape(
                meta_match.group(1)
            ).split()
        )

    element_match = re.search(
        rf'itemprop=["\']{escaped}["\'][^>]*>([\s\S]*?)</',
        html,
        re.IGNORECASE,
    )
    if element_match:
        return _strip_html(
            element_match.group(1)
        )
    return None


def _h1_text(html: str) -> str | None:
    match = re.search(
        r"<h1\b[^>]*>([\s\S]*?)</h1>",
        html,
        re.IGNORECASE,
    )
    if match:
        return _strip_html(match.group(1))
    return None


def _description_from_html(
    html: str,
) -> str | None:
    for pattern in (
        r'<span[^>]+class=["\'][^"\']*jobdescription[^"\']*["\'][^>]*>([\s\S]*?)</span>',
        r'itemprop=["\']description["\'][^>]*>([\s\S]*?)</span>',
    ):
        match = re.search(
            pattern,
            html,
            re.IGNORECASE,
        )
        if match:
            value = _strip_html(
                match.group(1)
            )
            if value:
                return value
    return None


def _location_from_meta(
    html: str,
) -> str | None:
    values: list[str] = []
    for itemprop in (
        "addressLocality",
        "addressRegion",
        "addressCountry",
    ):
        value = _itemprop_content(
            html,
            itemprop,
        )
        if value and value not in values:
            values.append(value)
    return (
        ", ".join(values)
        if values
        else None
    )


def _apply_url(
    *,
    base_url: str,
    html: str,
) -> str | None:
    for pattern in (
        r'class=["\'][^"\']*apply[^"\']*["\'][^>]+href=["\']([^"\']+)["\']',
        r'href=["\']([^"\']*/apply/[^"\']*)["\']',
    ):
        match = re.search(
            pattern,
            html,
            re.IGNORECASE,
        )
        if match:
            return urljoin(
                base_url,
                unescape(match.group(1)),
            )
    return None


def _published_at(
    value: str | None,
) -> datetime | None:
    if not value:
        return None
    cleaned = value.strip().replace(
        "Z",
        "+00:00",
    )
    for parser in (
        datetime.fromisoformat,
        parsedate_to_datetime,
    ):
        try:
            parsed = parser(cleaned)
            if parsed.tzinfo is None:
                return parsed.replace(
                    tzinfo=timezone.utc
                )
            return parsed
        except (TypeError, ValueError):
            continue
    return None


def _job_url(
    url: str,
) -> str:
    parsed = urlsplit(url)
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.query,
            "",
        )
    )


def _explicitly_empty(html: str) -> bool:
    text = " ".join(
        unescape(html).casefold().split()
    )
    return any(
        marker in text
        for marker in EMPTY_BOARD_MARKERS
    )


def _strip_html(
    html: str,
) -> str:
    return " ".join(
        unescape(
            re.sub(r"<[^>]+>", " ", html)
        ).split()
    )
