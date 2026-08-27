from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from chamba_hunter.domain.enums import (
    SourceType,
)


OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)

DEFAULT_MAX_COMPANIES = 250
DEFAULT_TIMEOUT_SECONDS = 90.0

ARGENTINA_SOFTWARE_QUERY = r"""
[out:json][timeout:60];
area
  ["boundary"="administrative"]
  ["ISO3166-1"="AR"]
  ->.argentina;
(
  nwr["office"="it"](area.argentina);
  nwr["company"="it"](area.argentina);
  nwr["company"="software"](area.argentina);
  nwr["company"="software_development"](area.argentina);
  nwr["computer:software"="development"](area.argentina);
);
out tags center;
""".strip()


@dataclass(frozen=True, slots=True)
class ArgentinaDirectoryCompany:
    name: str
    website_url: str
    profile_url: str
    source_type: SourceType
    external_id: str

    email: str | None

    osm_type: str
    osm_id: int

    latitude: float | None
    longitude: float | None

    signal_tags: tuple[
        str,
        ...
    ]

    @property
    def discovery_score(
        self,
    ) -> float:
        # office=it / software-company tagging is direct
        # evidence of an IT/software company with Argentina
        # presence. Keep it strong enough to enter Explore
        # once a useful public contact is available, but far
        # below a professional/job match.
        return 15.0


@dataclass(frozen=True, slots=True)
class DirectoryFetch:
    endpoint: str

    elements_received: int
    candidates_with_name: int
    candidates_with_website: int
    candidates_with_email: int

    skipped_no_name: int
    skipped_no_website: int

    companies: tuple[
        ArgentinaDirectoryCompany,
        ...
    ]


class ArgentinaSoftwareDirectoryClient:
    source_type = (
        SourceType.OPENSTREETMAP
    )

    def __init__(
        self,
        *,
        timeout_seconds: float = (
            DEFAULT_TIMEOUT_SECONDS
        ),
        endpoints: tuple[str, ...] = (
            OVERPASS_ENDPOINTS
        ),
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError(
                "timeout_seconds must be positive."
            )

        if not endpoints:
            raise ValueError(
                "At least one Overpass endpoint is required."
            )

        self.timeout_seconds = (
            timeout_seconds
        )
        self.endpoints = endpoints

    def fetch(
        self,
        *,
        max_companies: int = (
            DEFAULT_MAX_COMPANIES
        ),
    ) -> DirectoryFetch:
        if max_companies < 1:
            raise ValueError(
                "max_companies must be at least 1."
            )

        errors: list[str] = []

        payload = None
        selected_endpoint = None

        headers = {
            "User-Agent": (
                "chamba-hunter/0.2 "
                "(Argentina public IT company discovery)"
            ),
            "Accept": "application/json",
        }

        with httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers=headers,
        ) as client:
            for endpoint in self.endpoints:
                try:
                    response = client.post(
                        endpoint,
                        data={
                            "data": ARGENTINA_SOFTWARE_QUERY
                        },
                    )
                    response.raise_for_status()

                    candidate = response.json()

                    if not isinstance(
                        candidate,
                        dict,
                    ):
                        raise ValueError(
                            "Overpass response is not an object."
                        )

                    elements = candidate.get(
                        "elements"
                    )

                    if not isinstance(
                        elements,
                        list,
                    ):
                        raise ValueError(
                            "Overpass response has no elements list."
                        )

                    payload = candidate
                    selected_endpoint = endpoint
                    break

                except (
                    httpx.HTTPError,
                    ValueError,
                ) as error:
                    errors.append(
                        f"{endpoint}: "
                        f"{type(error).__name__}: "
                        f"{error}"
                    )

        if (
            payload is None
            or selected_endpoint is None
        ):
            raise RuntimeError(
                "All Overpass endpoints failed. "
                + " | ".join(errors)
            )

        raw_elements = payload[
            "elements"
        ]

        companies: list[
            ArgentinaDirectoryCompany
        ] = []

        skipped_no_name = 0
        skipped_no_website = 0
        with_name = 0
        with_website = 0
        with_email = 0

        seen_identity: set[
            tuple[str, int]
        ] = set()

        for element in raw_elements:
            if not isinstance(
                element,
                dict,
            ):
                continue

            element_type = element.get(
                "type"
            )
            element_id = element.get(
                "id"
            )
            tags = element.get(
                "tags"
            )

            if (
                not isinstance(
                    element_type,
                    str,
                )
                or not isinstance(
                    element_id,
                    int,
                )
                or not isinstance(
                    tags,
                    dict,
                )
            ):
                continue

            identity = (
                element_type,
                element_id,
            )

            if identity in seen_identity:
                continue

            seen_identity.add(
                identity
            )

            name = _first_text(
                tags,
                (
                    "name",
                    "brand",
                    "operator",
                ),
            )

            if name is None:
                skipped_no_name += 1
                continue

            with_name += 1

            website = _first_text(
                tags,
                (
                    "website",
                    "contact:website",
                    "url",
                ),
            )

            website = _normalize_website(
                website
            )

            if website is None:
                skipped_no_website += 1
                continue

            with_website += 1

            email = _first_text(
                tags,
                (
                    "contact:email",
                    "email",
                ),
            )

            email = _normalize_email(
                email
            )

            if email is not None:
                with_email += 1

            latitude, longitude = (
                _coordinates(
                    element
                )
            )

            companies.append(
                ArgentinaDirectoryCompany(
                    name=name,
                    website_url=website,
                    profile_url=(
                        _osm_object_url(
                            element_type,
                            element_id,
                        )
                    ),
                    source_type=(
                        SourceType.OPENSTREETMAP
                    ),
                    external_id=(
                        f"{element_type}:"
                        f"{element_id}"
                    ),
                    email=email,
                    osm_type=element_type,
                    osm_id=element_id,
                    latitude=latitude,
                    longitude=longitude,
                    signal_tags=(
                        _signal_tags(
                            tags
                        )
                    ),
                )
            )

        # Prefer records with a published email and then
        # stronger/specific software tagging. Stable name ordering
        # makes refreshes deterministic.
        companies.sort(
            key=lambda item: (
                0
                if item.email is not None
                else 1,
                -len(
                    item.signal_tags
                ),
                item.name.casefold(),
                item.osm_type,
                item.osm_id,
            )
        )

        return DirectoryFetch(
            endpoint=selected_endpoint,
            elements_received=len(
                raw_elements
            ),
            candidates_with_name=(
                with_name
            ),
            candidates_with_website=(
                with_website
            ),
            candidates_with_email=(
                with_email
            ),
            skipped_no_name=(
                skipped_no_name
            ),
            skipped_no_website=(
                skipped_no_website
            ),
            companies=tuple(
                companies[
                    :max_companies
                ]
            ),
        )


# Compatibility alias so stale imports from an intermediate
# local V1 do not break after overlaying this patch.
GoodFirmsArgentinaClient = (
    ArgentinaSoftwareDirectoryClient
)
ClutchArgentinaClient = (
    ArgentinaSoftwareDirectoryClient
)


def _signal_tags(
    tags: dict,
) -> tuple[
    str,
    ...
]:
    result: list[
        str
    ] = []

    for key in (
        "office",
        "company",
        "computer:software",
        "consulting",
    ):
        raw = tags.get(
            key
        )

        if not isinstance(
            raw,
            str,
        ):
            continue

        cleaned = " ".join(
            raw.split()
        ).strip()

        if cleaned:
            result.append(
                f"{key}={cleaned}"
            )

    return tuple(
        result
    )


def _coordinates(
    element: dict,
) -> tuple[
    float | None,
    float | None,
]:
    lat = element.get(
        "lat"
    )
    lon = element.get(
        "lon"
    )

    if (
        isinstance(
            lat,
            (int, float),
        )
        and isinstance(
            lon,
            (int, float),
        )
    ):
        return (
            float(lat),
            float(lon),
        )

    center = element.get(
        "center"
    )

    if isinstance(
        center,
        dict,
    ):
        lat = center.get(
            "lat"
        )
        lon = center.get(
            "lon"
        )

        if (
            isinstance(
                lat,
                (int, float),
            )
            and isinstance(
                lon,
                (int, float),
            )
        ):
            return (
                float(lat),
                float(lon),
            )

    return (
        None,
        None,
    )


def _first_text(
    tags: dict,
    keys: tuple[
        str,
        ...
    ],
) -> str | None:
    for key in keys:
        raw = tags.get(
            key
        )

        if not isinstance(
            raw,
            str,
        ):
            continue

        cleaned = " ".join(
            raw.split()
        ).strip()

        if cleaned:
            return cleaned

    return None


def _normalize_email(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    cleaned = (
        value.strip()
        .casefold()
    )

    if (
        cleaned.count("@") != 1
        or " " in cleaned
    ):
        return None

    local_part, domain = (
        cleaned.split("@", 1)
    )

    if (
        not local_part
        or not domain
        or "." not in domain
    ):
        return None

    return cleaned


def _normalize_website(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    cleaned = value.strip()

    if not cleaned:
        return None

    if cleaned.startswith(
        "www."
    ):
        return (
            "https://"
            + cleaned.rstrip("/")
        )

    if not cleaned.startswith(
        (
            "http://",
            "https://",
        )
    ):
        return (
            "https://"
            + cleaned.rstrip("/")
        )

    return cleaned.rstrip("/")


def _osm_object_url(
    element_type: str,
    element_id: int,
) -> str:
    return (
        "https://www.openstreetmap.org/"
        f"{element_type}/{element_id}"
    )
