from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from html.parser import HTMLParser
import json
import re
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx


HIBOB_CAREERS_SUFFIX = ".careers.hibob.com"
_JOB_ID = r"([A-Za-z0-9_-]{1,128})"
JOB_PATH_PATTERNS = (
    re.compile(rf"^/jobs/{_JOB_ID}(?:/apply)?/?$", re.I),
    re.compile(rf"^/job/{_JOB_ID}(?:/apply)?/?$", re.I),
    re.compile(rf"^/positions/{_JOB_ID}(?:/apply)?/?$", re.I),
    re.compile(rf"^/careers/{_JOB_ID}(?:/apply)?/?$", re.I),
    re.compile(rf"^/careers/job/{_JOB_ID}(?:/apply)?/?$", re.I),
)
EMPTY_BOARD_MARKERS = (
    "no open positions",
    "no open roles",
    "no jobs available",
    "no vacancies",
    "there are currently no",
)


@dataclass(frozen=True, slots=True)
class HiBobJobLink:
    external_id: str
    title_hint: str | None
    job_url: str


@dataclass(frozen=True, slots=True)
class HiBobJobDetail:
    external_id: str
    title: str
    description: str | None
    location_text: str | None
    job_location_type: str | None
    employment_type: str | None
    published_at: datetime | None
    job_url: str
    apply_url: str
    raw_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class HiBobJobsFetch:
    http_status: int
    total: int
    jobs: list[HiBobJobDetail]


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []
        self._depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if self._href is not None:
            self._depth += 1
            return

        if tag.casefold() != "a":
            return

        attributes = {
            key.casefold(): value
            for key, value in attrs
        }
        href = attributes.get("href")

        if not href:
            return

        self._href = href
        self._text = []
        self._depth = 1

    def handle_endtag(self, tag: str) -> None:
        if self._href is None:
            return

        self._depth -= 1

        if self._depth > 0:
            return

        self.anchors.append(
            (
                self._href,
                " ".join(self._text).strip(),
            )
        )
        self._href = None
        self._text = []
        self._depth = 0

    def handle_data(self, data: str) -> None:
        if self._href is None:
            return

        text = " ".join(data.split())
        if text:
            self._text.append(text)


class _DetailParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.json_ld: list[str] = []
        self.h1: list[str] = []
        self.visible_text: list[str] = []
        self._json_ld = False
        self._json_text: list[str] = []
        self._h1_depth = 0
        self._skip_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        normalized = tag.casefold()
        attributes = {
            key.casefold(): value
            for key, value in attrs
        }

        if normalized == "script":
            if (
                attributes.get("type") or ""
            ).casefold() == "application/ld+json":
                self._json_ld = True
                self._json_text = []
            else:
                self._skip_depth += 1
            return

        if normalized in {"style", "noscript"}:
            self._skip_depth += 1
            return

        if normalized == "meta":
            key = (
                attributes.get("property")
                or attributes.get("name")
            )
            value = attributes.get("content")
            if key and value:
                self.meta[key.casefold()] = value

        if normalized == "h1":
            self._h1_depth = 1
        elif self._h1_depth > 0:
            self._h1_depth += 1

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.casefold()

        if normalized == "script" and self._json_ld:
            value = "".join(self._json_text).strip()
            if value:
                self.json_ld.append(value)
            self._json_ld = False
            self._json_text = []
            return

        if normalized in {"script", "style", "noscript"}:
            if self._skip_depth > 0:
                self._skip_depth -= 1
            return

        if self._h1_depth > 0:
            self._h1_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._json_ld:
            self._json_text.append(data)
            return

        if self._skip_depth > 0:
            return

        text = " ".join(data.split())
        if not text:
            return

        self.visible_text.append(text)
        if self._h1_depth > 0:
            self.h1.append(text)


class HiBobClient:
    def __init__(
        self,
        timeout_seconds: float = 20.0,
        max_detail_workers: int = 6,
    ) -> None:
        if max_detail_workers < 1:
            raise ValueError(
                "max_detail_workers must be at least 1."
            )

        self.timeout_seconds = timeout_seconds
        self.max_detail_workers = max_detail_workers

    def fetch_jobs(
        self,
        board_url: str,
    ) -> HiBobJobsFetch:
        board_url = normalize_hibob_board_url(
            board_url
        )

        with httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            limits=httpx.Limits(
                max_connections=self.max_detail_workers,
                max_keepalive_connections=(
                    self.max_detail_workers
                ),
            ),
            headers={
                "User-Agent": "chamba-hunter/0.1"
            },
        ) as client:
            response = client.get(board_url)
            response.raise_for_status()
            _validate_hibob_url(str(response.url))

            links = _parse_job_links(
                board_url=str(response.url),
                html=response.text,
            )

            if not links and not _explicitly_empty(
                response.text
            ):
                raise ValueError(
                    "HiBob board returned no recognizable jobs; "
                    "refusing to treat it as an empty snapshot."
                )

            jobs = self._fetch_details(
                client=client,
                links=links,
            )

        return HiBobJobsFetch(
            http_status=response.status_code,
            total=len(jobs),
            jobs=jobs,
        )

    def _fetch_details(
        self,
        *,
        client: httpx.Client,
        links: list[HiBobJobLink],
    ) -> list[HiBobJobDetail]:
        if not links:
            return []

        results: list[HiBobJobDetail | None] = [
            None for _ in links
        ]

        with ThreadPoolExecutor(
            max_workers=min(
                self.max_detail_workers,
                len(links),
            ),
            thread_name_prefix="hibob-detail",
        ) as executor:
            futures = {
                executor.submit(
                    self._fetch_detail,
                    client,
                    link,
                ): index
                for index, link in enumerate(links)
            }

            try:
                for future in as_completed(futures):
                    results[futures[future]] = future.result()
            except Exception:
                for future in futures:
                    future.cancel()
                raise

        if any(item is None for item in results):
            raise RuntimeError(
                "HiBob detail fetch did not produce a full snapshot."
            )

        return [
            item
            for item in results
            if item is not None
        ]

    def _fetch_detail(
        self,
        client: httpx.Client,
        link: HiBobJobLink,
    ) -> HiBobJobDetail:
        response = client.get(link.job_url)
        response.raise_for_status()
        final_url = str(response.url)
        _validate_hibob_url(final_url)

        external_id = extract_hibob_job_id(
            final_url
        )
        if external_id != link.external_id:
            raise ValueError(
                "HiBob job detail resolved to an unexpected id: "
                f"'{final_url}'."
            )

        parser = _DetailParser()
        parser.feed(response.text)
        posting = _job_posting(parser.json_ld)

        title = _json_text(
            (posting or {}).get("title")
        )
        if not title:
            title = " ".join(parser.h1).strip()
        if not title:
            title = parser.meta.get("og:title")
        if not title:
            title = link.title_hint
        if not title:
            raise ValueError(
                f"HiBob job '{external_id}' has no title."
            )

        description = _description(
            posting=posting,
            parser=parser,
            title=title,
        )
        location_text = _location_text(
            posting
        )
        job_location_type = _json_text(
            (posting or {}).get("jobLocationType")
        )
        employment_type = _employment_type(
            (posting or {}).get("employmentType")
        )
        published_at = _published_at(
            _json_text(
                (posting or {}).get("datePosted")
            )
        )
        apply_url = (
            final_url.rstrip("/") + "/apply"
        )

        return HiBobJobDetail(
            external_id=external_id,
            title=title,
            description=description,
            location_text=location_text,
            job_location_type=job_location_type,
            employment_type=employment_type,
            published_at=published_at,
            job_url=final_url,
            apply_url=apply_url,
            raw_payload={
                "provider": "HIBOB",
                "job_url": final_url,
                "apply_url": apply_url,
                "job_posting": posting,
                "extracted": {
                    "title": title,
                    "location_text": location_text,
                    "job_location_type": job_location_type,
                    "employment_type": employment_type,
                    "date_posted": (
                        (posting or {}).get("datePosted")
                    ),
                },
            },
        )


def hibob_tenant_from_url(
    value: str,
) -> str | None:
    try:
        host = (urlsplit(value).hostname or "").casefold()
    except ValueError:
        return None

    if not host.endswith(HIBOB_CAREERS_SUFFIX):
        return None

    tenant = host[: -len(HIBOB_CAREERS_SUFFIX)]
    if not tenant or "." in tenant:
        return None

    return tenant


def canonical_hibob_board_url(
    tenant: str,
) -> str:
    cleaned = tenant.strip().casefold()
    if not cleaned or "." in cleaned or "/" in cleaned:
        raise ValueError(
            f"Invalid HiBob tenant identifier: '{tenant}'."
        )
    return f"https://{cleaned}{HIBOB_CAREERS_SUFFIX}/jobs"


def normalize_hibob_board_url(
    value: str,
) -> str:
    tenant = hibob_tenant_from_url(value)
    if tenant is None:
        raise ValueError(
            f"Not a HiBob public careers URL: '{value}'."
        )
    return canonical_hibob_board_url(tenant)


def extract_hibob_job_id(
    value: str,
) -> str | None:
    try:
        path = urlsplit(value).path
    except ValueError:
        return None

    for pattern in JOB_PATH_PATTERNS:
        match = pattern.match(path)
        if match is not None:
            return match.group(1)
    return None


def _parse_job_links(
    *,
    board_url: str,
    html: str,
) -> list[HiBobJobLink]:
    parser = _AnchorParser()
    parser.feed(html)
    by_id: dict[str, HiBobJobLink] = {}

    for href, text in parser.anchors:
        resolved = urljoin(board_url, href)
        tenant = hibob_tenant_from_url(resolved)
        external_id = extract_hibob_job_id(resolved)
        if tenant is None or external_id is None:
            continue

        parsed = urlsplit(resolved)
        clean_path = re.sub(
            r"/apply/?$",
            "",
            parsed.path,
            flags=re.I,
        )
        job_url = (
            f"{parsed.scheme}://{parsed.netloc}"
            f"{clean_path}"
        )
        by_id.setdefault(
            external_id,
            HiBobJobLink(
                external_id=external_id,
                title_hint=(text or None),
                job_url=job_url,
            ),
        )

    return sorted(
        by_id.values(),
        key=lambda item: item.external_id,
    )


def _validate_hibob_url(value: str) -> None:
    if hibob_tenant_from_url(value) is None:
        raise ValueError(
            f"HiBob request resolved outside a public careers host: '{value}'."
        )


def _explicitly_empty(html: str) -> bool:
    normalized = " ".join(
        unescape(html).casefold().split()
    )
    return any(
        marker in normalized
        for marker in EMPTY_BOARD_MARKERS
    )


def _job_posting(
    values: list[str],
) -> dict[str, Any] | None:
    for raw in values:
        try:
            parsed = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue

        for item in _json_objects(parsed):
            kind = item.get("@type")
            kinds = (
                kind
                if isinstance(kind, list)
                else [kind]
            )
            if any(
                str(value).casefold() == "jobposting"
                for value in kinds
                if value is not None
            ):
                return item
    return None


def _json_objects(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        objects = [value]
        graph = value.get("@graph")
        if isinstance(graph, list):
            objects.extend(
                item
                for item in graph
                if isinstance(item, dict)
            )
        return objects
    if isinstance(value, list):
        return [
            item
            for item in value
            if isinstance(item, dict)
        ]
    return []


def _description(
    *,
    posting: dict[str, Any] | None,
    parser: _DetailParser,
    title: str,
) -> str | None:
    structured = _json_text(
        (posting or {}).get("description")
    )
    if structured:
        return _strip_html(structured)

    meta = (
        parser.meta.get("description")
        or parser.meta.get("og:description")
    )
    if meta and meta.strip() and meta.strip() != title:
        return " ".join(meta.split())

    visible = "\n".join(parser.visible_text).strip()
    if len(visible) >= 80:
        return visible
    return None


def _location_text(
    posting: dict[str, Any] | None,
) -> str | None:
    if not posting:
        return None

    values: list[str] = []
    raw_locations = posting.get("jobLocation")
    locations = (
        raw_locations
        if isinstance(raw_locations, list)
        else [raw_locations]
    )

    for location in locations:
        if not isinstance(location, dict):
            continue
        address = location.get("address")
        if isinstance(address, dict):
            for key in (
                "addressLocality",
                "addressRegion",
                "addressCountry",
            ):
                value = _json_text(address.get(key))
                if value and value not in values:
                    values.append(value)
        else:
            value = _json_text(address)
            if value and value not in values:
                values.append(value)

    if not values:
        applicant = posting.get(
            "applicantLocationRequirements"
        )
        items = applicant if isinstance(applicant, list) else [applicant]
        for item in items:
            if isinstance(item, dict):
                value = _json_text(item.get("name"))
            else:
                value = _json_text(item)
            if value and value not in values:
                values.append(value)

    return ", ".join(values) if values else None


def _employment_type(value: Any) -> str | None:
    if isinstance(value, list):
        parts = [
            str(item).strip()
            for item in value
            if str(item).strip()
        ]
        return ", ".join(parts) if parts else None
    return _json_text(value)


def _published_at(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        try:
            return datetime.fromisoformat(cleaned[:10])
        except ValueError:
            return None


def _json_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = " ".join(value.split())
        return cleaned or None
    return str(value)


def _strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    return " ".join(unescape(text).split())
