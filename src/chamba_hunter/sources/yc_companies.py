from dataclasses import dataclass
from time import sleep
from urllib.parse import quote

import httpx


YC_PROFILE_BASE_URL = (
    "https://www.ycombinator.com"
    "/companies"
)

YC_OSS_API_BASE_URL = (
    "https://yc-oss.github.io/api"
)

DEFAULT_CATEGORIES = (
    "Developer Tools",
    "Infrastructure",
    "DevOps",
    "Cloud Computing",
    "API",
)

DEFAULT_MAX_COMPANIES = 150
DEFAULT_REQUEST_DELAY_SECONDS = 0.10

ACCEPTED_STATUSES = {
    "active",
    "public",
}

# The public snapshot mirrors YC's client-visible
# company directory data. "Infrastructure" is an
# YC industry; the other defaults are YC tags.
CATEGORY_FEEDS: dict[
    str,
    tuple[
        str,
        str,
    ],
] = {
    "Developer Tools": (
        "tag",
        "developer-tools",
    ),
    "Infrastructure": (
        "industry",
        "infrastructure",
    ),
    "DevOps": (
        "tag",
        "devops",
    ),
    "Cloud Computing": (
        "tag",
        "cloud-computing",
    ),
    "API": (
        "tag",
        "api",
    ),
}


@dataclass(frozen=True, slots=True)
class YcCompany:
    yc_id: int | None

    name: str
    slug: str
    profile_url: str

    website_url: str
    status: str

    matched_categories: tuple[
        str,
        ...
    ]

    batch: str | None
    team_size: int | None
    location: str | None

    industry: str | None
    subindustry: str | None

    industries: tuple[
        str,
        ...
    ]
    tags: tuple[
        str,
        ...
    ]
    regions: tuple[
        str,
        ...
    ]

    stage: str | None
    is_hiring: bool
    top_company: bool

    directory_rank: int

    @property
    def external_id(
        self,
    ) -> str:
        return self.slug

    @property
    def outreach_relevance_score(
        self,
    ) -> float:
        if (
            self.status.casefold()
            == "active"
        ):
            score = 20.0
        else:
            score = 15.0

        if self.is_hiring:
            score += 5.0

        return score


@dataclass(frozen=True, slots=True)
class YcDirectoryFetch:
    feeds_requested: int
    feeds_fetched: int
    feeds_failed: int

    raw_records: int
    unique_candidates: int

    skipped_status: int
    skipped_missing_website: int
    skipped_invalid: int

    companies: tuple[
        YcCompany,
        ...
    ]


@dataclass(slots=True)
class _MergedRecord:
    raw: dict
    matched_categories: set[str]
    directory_rank: int


class YcDirectoryClient:
    def __init__(
        self,
        *,
        timeout_seconds: float = 30.0,
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
        categories: tuple[str, ...] = (
            DEFAULT_CATEGORIES
        ),
        max_companies: int = (
            DEFAULT_MAX_COMPANIES
        ),
    ) -> YcDirectoryFetch:
        if max_companies < 1:
            raise ValueError(
                "max_companies must be "
                "at least 1."
            )

        cleaned_categories = tuple(
            _clean_category(
                category
            )
            for category in categories
            if _clean_category(
                category
            )
        )

        if not cleaned_categories:
            raise ValueError(
                "At least one YC category "
                "is required."
            )

        unknown_categories = [
            category
            for category in (
                cleaned_categories
            )
            if category
            not in CATEGORY_FEEDS
        ]

        if unknown_categories:
            supported = ", ".join(
                CATEGORY_FEEDS
            )

            raise ValueError(
                "Unsupported YC category: "
                + ", ".join(
                    unknown_categories
                )
                + ". Supported categories: "
                + supported
            )

        merged: dict[
            str,
            _MergedRecord,
        ] = {}

        feeds_fetched = 0
        feeds_failed = 0
        raw_records = 0
        global_rank = 0

        with httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "chamba-hunter/0.2 "
                    "(public YC directory "
                    "snapshot consumer)"
                ),
                "Accept": (
                    "application/json"
                ),
            },
        ) as client:
            for index, category in enumerate(
                cleaned_categories
            ):
                url = _feed_url(
                    category
                )

                try:
                    response = client.get(
                        url
                    )
                    response.raise_for_status()

                    payload = response.json()

                    if not isinstance(
                        payload,
                        list,
                    ):
                        raise ValueError(
                            "YC snapshot feed "
                            "must return a list."
                        )

                    feeds_fetched += 1
                    raw_records += len(
                        payload
                    )

                    for local_rank, raw in enumerate(
                        payload,
                        start=1,
                    ):
                        if not isinstance(
                            raw,
                            dict,
                        ):
                            continue

                        slug = _string(
                            raw.get(
                                "slug"
                            )
                        )

                        if slug is None:
                            continue

                        rank = (
                            global_rank
                            + local_rank
                        )

                        existing = (
                            merged.get(
                                slug
                            )
                        )

                        if existing is None:
                            merged[
                                slug
                            ] = _MergedRecord(
                                raw=raw,
                                matched_categories={
                                    category
                                },
                                directory_rank=(
                                    rank
                                ),
                            )
                        else:
                            existing.matched_categories.add(
                                category
                            )

                            if (
                                rank
                                < existing
                                .directory_rank
                            ):
                                existing.directory_rank = (
                                    rank
                                )
                                existing.raw = raw

                except (
                    httpx.HTTPError,
                    ValueError,
                    json.JSONDecodeError,
                ):
                    feeds_failed += 1

                global_rank += 10_000

                if (
                    index
                    < len(
                        cleaned_categories
                    ) - 1
                ):
                    self._delay()

        if not merged:
            raise RuntimeError(
                "YC snapshot acquisition "
                "returned no usable "
                "companies."
            )

        candidates: list[
            YcCompany
        ] = []

        skipped_status = 0
        skipped_missing_website = 0
        skipped_invalid = 0

        for item in merged.values():
            status = _string(
                item.raw.get(
                    "status"
                )
            )

            if (
                status is None
                or status.casefold()
                not in ACCEPTED_STATUSES
            ):
                skipped_status += 1
                continue

            website = _string(
                item.raw.get(
                    "website"
                )
            )

            if not website:
                skipped_missing_website += 1
                continue

            try:
                company = _normalize_record(
                    raw=item.raw,
                    matched_categories=tuple(
                        sorted(
                            item
                            .matched_categories,
                            key=str.casefold,
                        )
                    ),
                    directory_rank=(
                        item
                        .directory_rank
                    ),
                )

            except ValueError:
                skipped_invalid += 1
                continue

            candidates.append(
                company
            )

        candidates.sort(
            key=lambda item: (
                -int(
                    item.is_hiring
                ),
                -len(
                    item
                    .matched_categories
                ),
                0
                if (
                    item.status
                    .casefold()
                    == "active"
                )
                else 1,
                item.directory_rank,
                item.name.casefold(),
            )
        )

        return YcDirectoryFetch(
            feeds_requested=len(
                cleaned_categories
            ),
            feeds_fetched=(
                feeds_fetched
            ),
            feeds_failed=(
                feeds_failed
            ),
            raw_records=(
                raw_records
            ),
            unique_candidates=len(
                merged
            ),
            skipped_status=(
                skipped_status
            ),
            skipped_missing_website=(
                skipped_missing_website
            ),
            skipped_invalid=(
                skipped_invalid
            ),
            companies=tuple(
                candidates[
                    :max_companies
                ]
            ),
        )

    def _delay(
        self,
    ) -> None:
        if (
            self.request_delay_seconds
            > 0
        ):
            sleep(
                self.request_delay_seconds
            )


def _normalize_record(
    *,
    raw: dict,
    matched_categories: tuple[
        str,
        ...
    ],
    directory_rank: int,
) -> YcCompany:
    name = _string(
        raw.get(
            "name"
        )
    )
    slug = _string(
        raw.get(
            "slug"
        )
    )
    website = _string(
        raw.get(
            "website"
        )
    )
    status = _string(
        raw.get(
            "status"
        )
    )

    if (
        name is None
        or slug is None
        or website is None
        or status is None
    ):
        raise ValueError(
            "YC record is missing "
            "required identity fields."
        )

    profile_url = _string(
        raw.get(
            "url"
        )
    ) or (
        f"{YC_PROFILE_BASE_URL}/"
        f"{quote(slug)}"
    )

    yc_id_raw = raw.get(
        "id"
    )

    yc_id = (
        int(yc_id_raw)
        if isinstance(
            yc_id_raw,
            int,
        )
        else None
    )

    return YcCompany(
        yc_id=yc_id,
        name=name,
        slug=slug,
        profile_url=profile_url,
        website_url=website,
        status=status,
        matched_categories=(
            matched_categories
        ),
        batch=_string(
            raw.get(
                "batch"
            )
        ),
        team_size=_integer(
            raw.get(
                "team_size"
            )
        ),
        location=_string(
            raw.get(
                "all_locations"
            )
        ),
        industry=_string(
            raw.get(
                "industry"
            )
        ),
        subindustry=_string(
            raw.get(
                "subindustry"
            )
        ),
        industries=_string_tuple(
            raw.get(
                "industries"
            )
        ),
        tags=_string_tuple(
            raw.get(
                "tags"
            )
        ),
        regions=_string_tuple(
            raw.get(
                "regions"
            )
        ),
        stage=_string(
            raw.get(
                "stage"
            )
        ),
        is_hiring=bool(
            raw.get(
                "isHiring",
                False,
            )
        ),
        top_company=bool(
            raw.get(
                "top_company",
                False,
            )
        ),
        directory_rank=(
            directory_rank
        ),
    )


def _feed_url(
    category: str,
) -> str:
    feed_type, slug = (
        CATEGORY_FEEDS[
            category
        ]
    )

    folder = (
        "tags"
        if feed_type == "tag"
        else "industries"
    )

    return (
        f"{YC_OSS_API_BASE_URL}/"
        f"{folder}/{slug}.json"
    )


def _string(
    value,
) -> str | None:
    if not isinstance(
        value,
        str,
    ):
        return None

    cleaned = " ".join(
        value.split()
    ).strip()

    return cleaned or None


def _string_tuple(
    value,
) -> tuple[
    str,
    ...
]:
    if not isinstance(
        value,
        list,
    ):
        return ()

    result = []

    for item in value:
        cleaned = _string(
            item
        )

        if (
            cleaned is not None
            and cleaned
            not in result
        ):
            result.append(
                cleaned
            )

    return tuple(
        result
    )


def _integer(
    value,
) -> int | None:
    if isinstance(
        value,
        bool,
    ):
        return None

    if isinstance(
        value,
        int,
    ):
        return value

    if isinstance(
        value,
        float,
    ) and value.is_integer():
        return int(
            value
        )

    return None


def _clean_category(
    value: str,
) -> str:
    return " ".join(
        value.split()
    ).strip()
