from dataclasses import dataclass
from datetime import datetime
from html import unescape
from html.parser import HTMLParser
import json
import re
from typing import Any
import unicodedata
from urllib.parse import urljoin, urlsplit

import httpx


JOB_PATH_PATTERN = re.compile(
    r"^/jobs/(\d+)(?:-|$)"
)

TEAMTAILOR_EVIDENCE = (
    "teamtailor",
    "assets-aws.teamtailor-cdn.com",
    "assets.teamtailor-cdn.com",
)

REMOTE_LABELS = {
    "remote status",
    "estado remoto",
}

LOCATION_LABELS = {
    "location",
    "locations",
    "ubicacion",
    "ubicaciones",
}

DEPARTMENT_LABELS = {
    "department",
    "departments",
    "departament",
    "departamento",
}

INVALID_LABEL_VALUES = {
    "all jobs",
    "all locations",
    "career site",
    "inicio",
    "jobs",
    "pagina de empleo",
    "start",
    "team stories",
    "todas las ubicaciones",
    "vacantes",
}

DESCRIPTION_END_LABELS = {
    "department",
    "departments",
    "departament",
    "departamento",
    "location",
    "locations",
    "ubicacion",
    "ubicaciones",
    "remote status",
    "estado remoto",
    "about",
    "acerca de",
    "career site",
    "pagina de empleo",
    "loading application form",
    "cargando formulario de solicitud",
}

CTA_LABELS = {
    "apply for this job",
    "apply now",
    "send application",
    "submit application",
    "enviar solicitud",
    "postular",
    "postularme",
}


@dataclass(frozen=True, slots=True)
class TeamtailorJobLink:
    external_id: str
    job_url: str


@dataclass(frozen=True, slots=True)
class TeamtailorJobDetail:
    external_id: str
    title: str
    description: str | None
    location_text: str | None
    job_location_type: str | None
    remote_status: str | None
    employment_type: str | None
    published_at: datetime | None
    job_url: str
    apply_url: str
    raw_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class TeamtailorJobsFetch:
    http_status: int
    total: int
    jobs: list[TeamtailorJobDetail]


class _BoardParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.casefold() != "a":
            return

        attributes = {
            key.casefold(): value
            for key, value in attrs
        }

        href = attributes.get("href")

        if href:
            self.links.append(href)


class _DetailParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.json_ld: list[str] = []
        self.h1_blocks: list[list[str]] = []
        self.visible_text: list[str] = []

        self._capture_json_ld = False
        self._json_ld_text: list[str] = []

        self._capture_h1 = False
        self._h1_depth = 0
        self._h1_text: list[str] = []

        self._skip_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        normalized_tag = tag.casefold()
        attributes = {
            key.casefold(): value
            for key, value in attrs
        }

        if normalized_tag in {"script", "style", "noscript"}:
            if (
                normalized_tag == "script"
                and (
                    attributes.get("type")
                    or ""
                ).casefold()
                == "application/ld+json"
            ):
                self._capture_json_ld = True
                self._json_ld_text = []
            else:
                self._skip_depth += 1

        if normalized_tag == "meta":
            key = (
                attributes.get("property")
                or attributes.get("name")
            )
            value = attributes.get("content")

            if key and value:
                self.meta[
                    key.casefold()
                ] = value

        if normalized_tag == "h1":
            self._capture_h1 = True
            self._h1_depth = 1
            self._h1_text = []

        elif self._capture_h1:
            self._h1_depth += 1

    def handle_endtag(
        self,
        tag: str,
    ) -> None:
        normalized_tag = tag.casefold()

        if (
            normalized_tag == "script"
            and self._capture_json_ld
        ):
            raw = "".join(
                self._json_ld_text
            ).strip()

            if raw:
                self.json_ld.append(raw)

            self._capture_json_ld = False
            self._json_ld_text = []
            return

        if normalized_tag in {"script", "style", "noscript"}:
            if self._skip_depth > 0:
                self._skip_depth -= 1

        if self._capture_h1:
            self._h1_depth -= 1

            if self._h1_depth <= 0:
                if self._h1_text:
                    self.h1_blocks.append(
                        self._h1_text.copy()
                    )

                self._capture_h1 = False
                self._h1_depth = 0
                self._h1_text = []

    def handle_data(
        self,
        data: str,
    ) -> None:
        if self._capture_json_ld:
            self._json_ld_text.append(data)
            return

        if self._skip_depth > 0:
            return

        cleaned = _clean_visible_text(data)

        if not cleaned:
            return

        self.visible_text.append(cleaned)

        if self._capture_h1:
            self._h1_text.append(cleaned)


class TeamtailorClient:
    def __init__(
        self,
        timeout_seconds: float = 20.0,
        max_pages: int = 100,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_pages = max_pages

    def fetch_jobs(
        self,
        board_url: str,
    ) -> TeamtailorJobsFetch:
        normalized_board_url = (
            _normalize_board_url(board_url)
        )

        with httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": "chamba-hunter/0.1"
            },
        ) as client:
            (
                http_status,
                job_links,
            ) = self._fetch_job_links(
                client=client,
                board_url=normalized_board_url,
            )

            jobs = [
                self._fetch_job_detail(
                    client=client,
                    source_job=job_link,
                )
                for job_link in job_links
            ]

        return TeamtailorJobsFetch(
            http_status=http_status,
            total=len(jobs),
            jobs=jobs,
        )

    def _fetch_job_links(
        self,
        client: httpx.Client,
        board_url: str,
    ) -> tuple[int, list[TeamtailorJobLink]]:
        current_url: str | None = board_url
        visited_urls: set[str] = set()
        jobs_by_id: dict[
            str,
            TeamtailorJobLink,
        ] = {}

        first_status: int | None = None
        page_count = 0

        while current_url is not None:
            if current_url in visited_urls:
                raise ValueError(
                    "Teamtailor pagination loop detected "
                    f"at '{current_url}'."
                )

            visited_urls.add(current_url)
            page_count += 1

            if page_count > self.max_pages:
                raise ValueError(
                    "Teamtailor pagination exceeded "
                    f"the {self.max_pages}-page safety limit."
                )

            response = client.get(current_url)
            response.raise_for_status()

            if first_status is None:
                first_status = response.status_code

                if not _has_teamtailor_evidence(
                    response.text
                ):
                    raise ValueError(
                        "Teamtailor board validation failed: "
                        "public page does not contain "
                        "Teamtailor evidence."
                    )

            parser = _BoardParser()
            parser.feed(response.text)

            page_url = str(response.url)

            for href in parser.links:
                resolved = urljoin(
                    page_url,
                    href,
                )

                try:
                    path = urlsplit(
                        resolved
                    ).path
                except ValueError:
                    continue

                match = JOB_PATH_PATTERN.match(path)

                if match is None:
                    continue

                external_id = match.group(1)

                jobs_by_id[external_id] = (
                    TeamtailorJobLink(
                        external_id=external_id,
                        job_url=(
                            resolved.split("#", 1)[0]
                        ),
                    )
                )

            current_url = _find_next_page(
                page_url=page_url,
                links=parser.links,
            )

        if first_status is None:
            raise RuntimeError(
                "Teamtailor board fetch produced "
                "no HTTP response."
            )

        jobs = list(jobs_by_id.values())
        jobs.sort(
            key=lambda item: int(
                item.external_id
            )
        )

        return first_status, jobs

    def _fetch_job_detail(
        self,
        client: httpx.Client,
        source_job: TeamtailorJobLink,
    ) -> TeamtailorJobDetail:
        response = client.get(
            source_job.job_url
        )
        response.raise_for_status()

        final_url = str(response.url)

        try:
            final_path = urlsplit(
                final_url
            ).path
        except ValueError as exc:
            raise ValueError(
                "Teamtailor returned an invalid "
                f"job URL: '{final_url}'."
            ) from exc

        final_match = JOB_PATH_PATTERN.match(
            final_path
        )

        if (
            final_match is None
            or final_match.group(1)
            != source_job.external_id
        ):
            raise ValueError(
                "Teamtailor job detail did not "
                "resolve to the expected job id "
                f"'{source_job.external_id}': "
                f"'{final_url}'."
            )

        parser = _DetailParser()
        parser.feed(response.text)

        job_posting = _job_posting(
            parser.json_ld
        )

        title = _job_title(
            parser=parser,
            job_posting=job_posting,
        )

        if not title:
            raise ValueError(
                "Teamtailor job detail is missing "
                f"a title: '{final_url}'."
            )

        description = _job_description(
            parser=parser,
            title=title,
            job_posting=job_posting,
        )

        location_text = (
            _job_location_text(
                parser=parser,
                title=title,
                job_posting=job_posting,
            )
        )

        job_location_type = _json_text(
            (
                job_posting or {}
            ).get("jobLocationType")
        )

        remote_status = _job_remote_status(
            parser=parser,
            title=title,
        )

        employment_type = (
            _employment_type(
                (
                    job_posting or {}
                ).get("employmentType")
            )
        )

        published_at = _published_at(
            _json_text(
                (
                    job_posting or {}
                ).get("datePosted")
            )
        )

        apply_url = (
            final_url.rstrip("/")
            + "/applications/new"
        )

        return TeamtailorJobDetail(
            external_id=source_job.external_id,
            title=title,
            description=description,
            location_text=location_text,
            job_location_type=job_location_type,
            remote_status=remote_status,
            employment_type=employment_type,
            published_at=published_at,
            job_url=final_url,
            apply_url=apply_url,
            raw_payload={
                "provider": "TEAMTAILOR",
                "job_url": final_url,
                "apply_url": apply_url,
                "job_posting": job_posting,
                "extracted": {
                    "title": title,
                    "description": description,
                    "location_text": location_text,
                    "job_location_type": (
                        job_location_type
                    ),
                    "remote_status": remote_status,
                    "employment_type": (
                        employment_type
                    ),
                    "date_posted": (
                        (
                            job_posting or {}
                        ).get("datePosted")
                    ),
                },
            },
        )


def _normalize_board_url(
    value: str,
) -> str:
    cleaned = value.strip()

    if not cleaned:
        raise ValueError(
            "Teamtailor board URL is empty."
        )

    try:
        parsed = urlsplit(cleaned)
    except ValueError as exc:
        raise ValueError(
            "Teamtailor board URL is invalid: "
            f"'{value}'."
        ) from exc

    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
    ):
        raise ValueError(
            "Teamtailor board URL must be HTTP(S): "
            f"'{value}'."
        )

    root = (
        f"{parsed.scheme}://{parsed.netloc}"
    )

    return root + "/jobs"


def _has_teamtailor_evidence(
    html: str,
) -> bool:
    normalized = html.casefold()

    return any(
        marker in normalized
        for marker in TEAMTAILOR_EVIDENCE
    )


def _find_next_page(
    page_url: str,
    links: list[str],
) -> str | None:
    for href in links:
        resolved = urljoin(
            page_url,
            href,
        )

        try:
            parsed = urlsplit(resolved)
        except ValueError:
            continue

        if parsed.path.rstrip("/") != (
            "/jobs/show_more"
        ):
            continue

        if not parsed.query:
            continue

        return resolved

    return None


def _job_posting(
    raw_values: list[str],
) -> dict[str, Any] | None:
    for raw in raw_values:
        try:
            payload = json.loads(raw)
        except (
            TypeError,
            json.JSONDecodeError,
        ):
            continue

        candidates: list[Any]

        if isinstance(payload, list):
            candidates = payload
        else:
            candidates = [payload]

        for candidate in candidates:
            if not isinstance(
                candidate,
                dict,
            ):
                continue

            if candidate.get("@type") == (
                "JobPosting"
            ):
                return candidate

            graph = candidate.get("@graph")

            if not isinstance(graph, list):
                continue

            for item in graph:
                if (
                    isinstance(item, dict)
                    and item.get("@type")
                    == "JobPosting"
                ):
                    return item

    return None


def _job_title(
    parser: _DetailParser,
    job_posting: dict[str, Any] | None,
) -> str | None:
    structured = _json_text(
        (job_posting or {}).get("title")
    )

    if structured:
        return _clean_visible_text(
            unescape(structured)
        )

    og_title = parser.meta.get(
        "og:title"
    )

    if og_title:
        cleaned = _clean_visible_text(
            unescape(og_title)
        )

        if cleaned and " - " in cleaned:
            cleaned = cleaned.rsplit(
                " - ",
                1,
            )[0].strip()

        if cleaned:
            return cleaned

    for block in parser.h1_blocks:
        h1 = _clean_visible_text(
            " ".join(block)
        )

        if h1:
            return h1

    return None


def _job_description(
    parser: _DetailParser,
    title: str,
    job_posting: dict[str, Any] | None,
) -> str | None:
    structured = _json_text(
        (job_posting or {}).get("description")
    )

    if structured:
        return _html_to_text(
            unescape(structured)
        )

    extracted = _visible_description(
        parser.visible_text,
        title,
    )

    if extracted:
        return extracted

    fallback = parser.meta.get(
        "og:description"
    )

    if not fallback:
        fallback = parser.meta.get(
            "description"
        )

    if not fallback:
        return None

    return _clean_visible_text(
        unescape(fallback)
    ) or None


def _visible_description(
    tokens: list[str],
    title: str,
) -> str | None:
    normalized_title = _normalize_label(
        title
    )

    title_indexes = [
        index
        for index, token in enumerate(tokens)
        if _normalize_label(token)
        == normalized_title
    ]

    candidates: list[str] = []

    for title_index in title_indexes:
        selected: list[str] = []

        for token in tokens[
            title_index + 1 :
        ]:
            normalized = _normalize_label(token)

            if not normalized:
                continue

            if normalized in CTA_LABELS:
                continue

            if normalized in DESCRIPTION_END_LABELS:
                break

            if normalized == normalized_title:
                break

            if normalized in {
                "share page",
                "compartir pagina",
            }:
                continue

            selected.append(token)

        value = "\n".join(
            selected
        ).strip()

        if value:
            candidates.append(value)

    if not candidates:
        return None

    return max(
        candidates,
        key=len,
    )


def _job_location_text(
    parser: _DetailParser,
    title: str,
    job_posting: dict[str, Any] | None,
) -> str | None:
    structured = _structured_locations(
        job_posting or {}
    )

    if structured:
        return structured

    start, end = _content_window(
        parser.visible_text,
        title,
    )

    labeled = _label_value(
        parser.visible_text,
        LOCATION_LABELS,
        start_index=start,
        end_index=end,
    )

    if labeled:
        return labeled

    department = _label_value(
        parser.visible_text,
        DEPARTMENT_LABELS,
        start_index=start,
        end_index=end,
    )

    hero = _hero_token(
        parser.visible_text,
        title,
    )

    return _hero_location(
        hero,
        department,
    )


def _job_remote_status(
    parser: _DetailParser,
    title: str,
) -> str | None:
    start, end = _content_window(
        parser.visible_text,
        title,
    )

    labeled = _label_value(
        parser.visible_text,
        REMOTE_LABELS,
        start_index=start,
        end_index=end,
    )

    if labeled:
        return labeled

    hero = _hero_token(
        parser.visible_text,
        title,
    )

    if hero:
        for segment in _hero_segments(hero):
            if _modality(segment):
                return segment

    return _modality(title)


def _structured_locations(
    job_posting: dict[str, Any],
) -> str | None:
    values: list[str] = []

    for key in (
        "jobLocation",
        "applicantLocationRequirements",
    ):
        raw = job_posting.get(key)

        if raw is None:
            continue

        items = (
            raw
            if isinstance(raw, list)
            else [raw]
        )

        for item in items:
            value = _location_item(item)

            if (
                value
                and value not in values
            ):
                values.append(value)

    if not values:
        return None

    return " / ".join(values)


def _location_item(
    value: Any,
) -> str | None:
    if isinstance(value, str):
        return _clean_visible_text(value)

    if not isinstance(value, dict):
        return None

    name = _json_text(value.get("name"))

    if name:
        return _clean_visible_text(name)

    address = value.get("address")

    if not isinstance(address, dict):
        return None

    parts: list[str] = []

    for key in (
        "addressLocality",
        "addressRegion",
        "addressCountry",
    ):
        item = address.get(key)

        if isinstance(item, dict):
            item = item.get("name")

        text = _json_text(item)
        text = (
            _clean_visible_text(text)
            if text
            else None
        )

        if text and text not in parts:
            parts.append(text)

    if not parts:
        return None

    return ", ".join(parts)


def _label_value(
    tokens: list[str],
    labels: set[str],
    start_index: int = 0,
    end_index: int | None = None,
) -> str | None:
    stop = (
        len(tokens)
        if end_index is None
        else min(end_index, len(tokens))
    )

    for index in range(
        max(start_index, 0),
        stop,
    ):
        token = tokens[index]

        if _normalize_label(token) not in labels:
            continue

        for candidate in tokens[
            index + 1 : min(index + 4, stop)
        ]:
            normalized = _normalize_label(
                candidate
            )

            if (
                normalized
                and normalized not in labels
                and normalized
                not in DESCRIPTION_END_LABELS
                and normalized
                not in INVALID_LABEL_VALUES
            ):
                return candidate

    return None


def _content_window(
    tokens: list[str],
    title: str,
) -> tuple[int, int]:
    normalized_title = _normalize_label(title)

    indexes = [
        index
        for index, token in enumerate(tokens)
        if _normalize_label(token)
        == normalized_title
    ]

    if not indexes:
        return 0, len(tokens)

    start = indexes[0] + 1
    end = len(tokens)

    for index in range(start, end):
        if _normalize_label(tokens[index]) in {
            "loading application form",
            "cargando formulario de solicitud",
            "career site",
            "pagina de empleo",
        }:
            end = index
            break

    return start, end


def _hero_token(
    tokens: list[str],
    title: str,
) -> str | None:
    normalized_title = _normalize_label(title)

    for index, token in enumerate(tokens):
        if _normalize_label(token) != normalized_title:
            continue

        selected: list[str] = []

        for candidate in reversed(
            tokens[max(0, index - 6) : index]
        ):
            normalized = _normalize_label(candidate)

            if not normalized:
                continue

            if (
                normalized == normalized_title
                or normalized in INVALID_LABEL_VALUES
                or normalized in CTA_LABELS
                or normalized in {
                    "share page",
                    "compartir pagina",
                }
                or "facebook" in normalized
                or "linkedin" in normalized
            ):
                break

            selected.append(candidate)

        if not selected:
            return None

        return " · ".join(
            reversed(selected)
        )

    return None


def _hero_segments(
    value: str,
) -> list[str]:
    return [
        _clean_visible_text(segment)
        for segment in value.split("·")
        if _clean_visible_text(segment)
    ]


def _hero_location(
    hero: str | None,
    department: str | None,
) -> str | None:
    if not hero:
        return None

    department_normalized = _normalize_label(
        department or ""
    )

    candidates = []

    for segment in _hero_segments(hero):
        normalized = _normalize_label(segment)

        if (
            not normalized
            or normalized in INVALID_LABEL_VALUES
            or _modality(segment)
            or (
                department_normalized
                and normalized
                == department_normalized
            )
        ):
            continue

        candidates.append(segment)

    if not candidates:
        return None

    return candidates[-1]


def _modality(
    value: str,
) -> str | None:
    normalized = _normalize_label(value)

    remote = any(
        marker in normalized
        for marker in (
            "fully remote",
            "completamente remoto",
            "remote",
            "remoto",
        )
    )
    hybrid = any(
        marker in normalized
        for marker in (
            "hybrid",
            "hibrido",
        )
    )
    onsite = any(
        marker in normalized
        for marker in (
            "on site",
            "onsite",
            "presencial",
        )
    )

    modes = sum((remote, hybrid, onsite))

    if modes != 1:
        return None

    if remote:
        return "Remote"

    if hybrid:
        return "Hybrid"

    return "On-site"


def _employment_type(
    value: Any,
) -> str | None:
    if isinstance(value, str):
        cleaned = _clean_visible_text(value)
        return cleaned or None

    if isinstance(value, list):
        values = [
            _clean_visible_text(str(item))
            for item in value
            if item is not None
        ]
        values = [
            item
            for item in values
            if item
        ]

        if values:
            return ", ".join(values)

    return None


def _published_at(
    value: str | None,
) -> datetime | None:
    if not value:
        return None

    cleaned = value.strip()

    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"

    try:
        return datetime.fromisoformat(
            cleaned
        )
    except ValueError:
        return None


def _json_text(
    value: Any,
) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None

    return None


def _html_to_text(
    value: str,
) -> str | None:
    parser = _PlainTextParser()
    parser.feed(value)

    text = "\n".join(
        parser.tokens
    ).strip()

    return text or None


class _PlainTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tokens: list[str] = []

    def handle_data(
        self,
        data: str,
    ) -> None:
        cleaned = _clean_visible_text(data)

        if cleaned:
            self.tokens.append(cleaned)


def _clean_visible_text(
    value: str,
) -> str:
    return " ".join(
        value.replace("\xa0", " ").split()
    ).strip()


def _normalize_label(
    value: str,
) -> str:
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

    normalized = re.sub(
        r"[^a-z0-9]+",
        " ",
        without_accents.casefold(),
    )

    return " ".join(
        normalized.split()
    )
