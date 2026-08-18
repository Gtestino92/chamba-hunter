from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
import re
from urllib.parse import urlsplit

import httpx

from chamba_hunter.sources.getonboard import (
    GETONBOARD_PROGRAMMING_URL,
    PER_PAGE,
    GetOnBoardJobResource,
    GetOnBoardJobsResponse,
)


MAX_DETAIL_FETCHES = 250
DEFAULT_DETAIL_WORKERS = 6


@dataclass(frozen=True, slots=True)
class GetOnBoardJobEnrichment:
    location_text: str | None
    published_date: str | None
    remote_policy_text: str | None
    source: str | None


@dataclass(frozen=True, slots=True)
class GetOnBoardJobsFetch:
    pages_fetched: int
    jobs: list[GetOnBoardJobResource]
    enrichments: dict[
        str,
        GetOnBoardJobEnrichment,
    ]


@dataclass(frozen=True, slots=True)
class _RemoteEnrichmentFetch:
    job_id: str
    enrichment: GetOnBoardJobEnrichment | None
    rate_limited: bool = False


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(
            convert_charrefs=True
        )
        self.parts: list[str] = []
        self.pre_title_parts: list[str] = []
        self.date_candidates: list[
            str
        ] = []
        self.seen_main_title = False

    def handle_starttag(
        self,
        tag: str,
        attrs: list[
            tuple[str, str | None]
        ],
    ) -> None:
        attributes = {
            key.casefold(): value
            for key, value
            in attrs
        }

        normalized_tag = (
            tag.casefold()
        )

        if normalized_tag == "h1":
            self.seen_main_title = True

        if (
            normalized_tag == "time"
            and not self.seen_main_title
        ):
            value = attributes.get(
                "datetime"
            )

            if value:
                self.date_candidates.append(
                    value
                )

        if normalized_tag == "meta":
            key = (
                attributes.get(
                    "property"
                )
                or attributes.get(
                    "name"
                )
                or ""
            ).casefold()

            if key in {
                "article:published_time",
                "datepublished",
            }:
                value = attributes.get(
                    "content"
                )

                if value:
                    self.date_candidates.append(
                        value
                    )

    def handle_data(
        self,
        data: str,
    ) -> None:
        cleaned = " ".join(
            data.split()
        )

        if cleaned:
            self.parts.append(
                cleaned
            )

            if not self.seen_main_title:
                self.pre_title_parts.append(
                    cleaned
                )

    def text(self) -> str:
        return " ".join(
            self.parts
        )

    def pre_title_text(self) -> str:
        return " ".join(
            self.pre_title_parts
        )


class GetOnBoardJobsClient:
    def __init__(
        self,
        timeout_seconds: float = 20.0,
        max_detail_workers: int = (
            DEFAULT_DETAIL_WORKERS
        ),
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

    def fetch_programming_jobs(
        self,
        max_pages: int,
    ) -> GetOnBoardJobsFetch:
        if max_pages < 1:
            raise ValueError(
                "max_pages must be at least 1."
            )

        jobs: list[
            GetOnBoardJobResource
        ] = []

        seen_ids: set[str] = set()
        pages_fetched = 0

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
                "Accept": "application/json",
            },
        ) as client:
            for page in range(
                1,
                max_pages + 1,
            ):
                response = client.get(
                    GETONBOARD_PROGRAMMING_URL,
                    params={
                        "per_page": PER_PAGE,
                        "expand[]": "company",
                        "page": page,
                    },
                )

                if response.status_code == 429:
                    raise RuntimeError(
                        "Get on Board rate "
                        "limit reached."
                    )

                response.raise_for_status()

                pages_fetched += 1

                payload = (
                    GetOnBoardJobsResponse
                    .model_validate(
                        response.json()
                    )
                )

                if not payload.data:
                    break

                for job in payload.data:
                    external_id = (
                        job.id.strip()
                    )

                    if not external_id:
                        raise ValueError(
                            "Get on Board "
                            "returned an empty "
                            "job id."
                        )

                    if external_id in seen_ids:
                        raise ValueError(
                            "Get on Board "
                            "returned a duplicate "
                            "job id while "
                            "paginating: "
                            f"{external_id}"
                        )

                    seen_ids.add(
                        external_id
                    )

                jobs.extend(
                    payload.data
                )

                if (
                    len(payload.data)
                    < PER_PAGE
                ):
                    break

            enrichments = (
                self._enrich_remote_jobs(
                    client=client,
                    jobs=jobs,
                )
            )

        return GetOnBoardJobsFetch(
            pages_fetched=pages_fetched,
            jobs=jobs,
            enrichments=enrichments,
        )

    def _enrich_remote_jobs(
        self,
        *,
        client: httpx.Client,
        jobs: list[
            GetOnBoardJobResource
        ],
    ) -> dict[
        str,
        GetOnBoardJobEnrichment,
    ]:
        enrichments: dict[
            str,
            GetOnBoardJobEnrichment,
        ] = {}

        for job in jobs:
            attributes = job.attributes

            if (
                attributes.remote
                and attributes.remote_modality
                == "fully_remote"
            ):
                enrichments[
                    job.id.strip()
                ] = (
                    GetOnBoardJobEnrichment(
                        location_text=(
                            "Worldwide"
                        ),
                        published_date=None,
                        remote_policy_text=(
                            "Fully remote"
                        ),
                        source=(
                            "REMOTE_MODALITY"
                        ),
                    )
                )

        detail_jobs: list[
            GetOnBoardJobResource
        ] = []

        for job in jobs:
            if not job.attributes.remote:
                continue

            if not job.links.public_url:
                continue

            detail_jobs.append(job)

            if (
                len(detail_jobs)
                >= MAX_DETAIL_FETCHES
            ):
                break

        with ThreadPoolExecutor(
            max_workers=self.max_detail_workers,
            thread_name_prefix=(
                "getonboard-detail"
            ),
        ) as executor:
            for start in range(
                0,
                len(detail_jobs),
                self.max_detail_workers,
            ):
                batch = detail_jobs[
                    start:
                    start + self.max_detail_workers
                ]

                futures = [
                    executor.submit(
                        self._fetch_remote_enrichment,
                        client=client,
                        job=job,
                    )
                    for job in batch
                ]

                rate_limited = False

                for future in futures:
                    result = future.result()

                    if result.rate_limited:
                        rate_limited = True
                        break

                    if result.enrichment is None:
                        continue

                    existing = (
                        enrichments.get(
                            result.job_id
                        )
                    )

                    enrichments[
                        result.job_id
                    ] = _merge_enrichment(
                        existing,
                        result.enrichment,
                    )

                if rate_limited:
                    for future in futures:
                        future.cancel()

                    break

        return enrichments

    @staticmethod
    def _fetch_remote_enrichment(
        *,
        client: httpx.Client,
        job: GetOnBoardJobResource,
    ) -> _RemoteEnrichmentFetch:
        job_id = job.id.strip()
        public_url = job.links.public_url

        if not public_url:
            return _RemoteEnrichmentFetch(
                job_id=job_id,
                enrichment=None,
            )

        try:
            response = client.get(
                public_url,
                headers={
                    "Accept": (
                        "text/html,"
                        "application/xhtml+xml,"
                        "*/*;q=0.8"
                    ),
                },
            )
        except httpx.RequestError:
            return _RemoteEnrichmentFetch(
                job_id=job_id,
                enrichment=None,
            )

        if response.status_code == 429:
            return _RemoteEnrichmentFetch(
                job_id=job_id,
                enrichment=None,
                rate_limited=True,
            )

        if response.status_code in {
            401,
            403,
        }:
            return _RemoteEnrichmentFetch(
                job_id=job_id,
                enrichment=None,
            )

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            return _RemoteEnrichmentFetch(
                job_id=job_id,
                enrichment=None,
            )

        if not _is_getonboard_url(
            str(
                response.url
            )
        ):
            return _RemoteEnrichmentFetch(
                job_id=job_id,
                enrichment=None,
            )

        return _RemoteEnrichmentFetch(
            job_id=job_id,
            enrichment=(
                _enrichment_from_html(
                    response.text,
                    remote_modality=(
                        job.attributes
                        .remote_modality
                    ),
                )
            ),
        )


def _merge_enrichment(
    first: GetOnBoardJobEnrichment | None,
    second: GetOnBoardJobEnrichment,
) -> GetOnBoardJobEnrichment:
    if first is None:
        return second

    return GetOnBoardJobEnrichment(
        location_text=(
            second.location_text
            or first.location_text
        ),
        published_date=(
            second.published_date
            or first.published_date
        ),
        remote_policy_text=(
            second.remote_policy_text
            or first.remote_policy_text
        ),
        source=(
            second.source
            or first.source
        ),
    )


def _enrichment_from_html(
    html: str,
    *,
    remote_modality: str | None,
) -> GetOnBoardJobEnrichment:
    parser = _VisibleTextParser()
    parser.feed(html)
    parser.close()

    text = parser.text()

    published_date = (
        _published_date(
            parser.date_candidates,
            parser.pre_title_text(),
        )
    )

    policy = (
        _remote_policy_text(
            text
        )
    )

    if remote_modality == "fully_remote":
        location_text = "Worldwide"
    else:
        location_text = (
            _residency_location(
                text
            )
        )

    source = (
        "PUBLIC_JOB_PAGE"
        if (
            published_date is not None
            or policy is not None
            or location_text is not None
        )
        else None
    )

    return GetOnBoardJobEnrichment(
        location_text=location_text,
        published_date=published_date,
        remote_policy_text=policy,
        source=source,
    )


def _residency_location(
    text: str,
) -> str | None:
    patterns = (
        re.compile(
            r"Position is 100% remote,\s*"
            r"but candidates must reside in\s+"
            r"(.+?)(?:[.!?](?:\s|$)|$)",
            re.IGNORECASE,
        ),
        re.compile(
            r"candidates must reside in\s+"
            r"(.+?)(?:[.!?](?:\s|$)|$)",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?:los|las)?\s*"
            r"(?:candidatos|candidatas)\s+"
            r"deben residir en\s+"
            r"(.+?)(?:[.!?](?:\s|$)|$)",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bRemote\s*\(([^)]+)\)",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bRemoto\s*\(([^)]+)\)",
            re.IGNORECASE,
        ),
    )

    for pattern in patterns:
        match = pattern.search(
            text
        )

        if match is None:
            continue

        value = _clean_location(
            match.group(1)
        )

        if value is not None:
            return value

    return None


def _remote_policy_text(
    text: str,
) -> str | None:
    patterns = (
        re.compile(
            r"(Position is 100% remote,\s*"
            r"but candidates must reside in\s+"
            r".+?[.!?])",
            re.IGNORECASE,
        ),
        re.compile(
            r"(Candidates can reside anywhere "
            r"in the world[.!?])",
            re.IGNORECASE,
        ),
        re.compile(
            r"(Fully remote\s+You can work "
            r"from anywhere in the world[.!?])",
            re.IGNORECASE,
        ),
    )

    for pattern in patterns:
        match = pattern.search(
            text
        )

        if match is not None:
            return " ".join(
                match.group(1).split()
            )

    return None


def _published_date(
    candidates: list[str],
    text: str,
) -> str | None:
    for candidate in candidates:
        value = candidate.strip()

        if len(value) >= 10:
            try:
                return (
                    date.fromisoformat(
                        value[:10]
                    )
                    .isoformat()
                )
            except ValueError:
                pass

    english_months = {
        "january": 1,
        "february": 2,
        "march": 3,
        "april": 4,
        "may": 5,
        "june": 6,
        "july": 7,
        "august": 8,
        "september": 9,
        "october": 10,
        "november": 11,
        "december": 12,
    }

    matches = list(
        re.finditer(
            r"\b("
            + "|".join(
                english_months
            )
            + r")\s+(\d{1,2}),\s+(\d{4})\b",
            text,
            re.IGNORECASE,
        )
    )

    if matches:
        match = matches[-1]

        return date(
            int(
                match.group(3)
            ),
            english_months[
                match.group(1)
                .casefold()
            ],
            int(
                match.group(2)
            ),
        ).isoformat()

    spanish_months = {
        "enero": 1,
        "febrero": 2,
        "marzo": 3,
        "abril": 4,
        "mayo": 5,
        "junio": 6,
        "julio": 7,
        "agosto": 8,
        "septiembre": 9,
        "octubre": 10,
        "noviembre": 11,
        "diciembre": 12,
    }

    matches = list(
        re.finditer(
            r"\b(\d{1,2})\s+de\s+("
            + "|".join(
                spanish_months
            )
            + r")\s+de\s+(\d{4})\b",
            text,
            re.IGNORECASE,
        )
    )

    if matches:
        match = matches[-1]

        return date(
            int(
                match.group(3)
            ),
            spanish_months[
                match.group(2)
                .casefold()
            ],
            int(
                match.group(1)
            ),
        ).isoformat()

    return None


def _clean_location(
    value: str,
) -> str | None:
    cleaned = " ".join(
        value.split()
    ).strip(
        " ,;:-"
    )

    if not cleaned:
        return None

    if cleaned.casefold() in {
        "remote",
        "remoto",
    }:
        return None

    if len(cleaned) > 200:
        return None

    return cleaned


def _is_getonboard_url(
    value: str,
) -> bool:
    try:
        host = (
            urlsplit(value)
            .hostname
            or ""
        ).casefold()
    except ValueError:
        return False

    allowed_suffixes = (
        "getonbrd.com",
        "getonbrd.cl",
        "getonbrd.com.ar",
        "getonbrd.com.co",
    )

    return any(
        host == suffix
        or host.endswith(
            "." + suffix
        )
        for suffix
        in allowed_suffixes
    )
