from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import httpx


WWR_FEED_URLS = (
    (
        "PROGRAMMING",
        "https://weworkremotely.com/"
        "categories/"
        "remote-programming-jobs.rss",
    ),
    (
        "DEVOPS",
        "https://weworkremotely.com/"
        "categories/"
        "remote-devops-sysadmin-jobs.rss",
    ),
)


@dataclass(frozen=True, slots=True)
class WeWorkRemotelyJobPosting:
    external_id: str
    title: str
    company_name: str

    link: str
    description_html: str | None
    region: str | None
    employment_type: str | None
    pub_date: str | None

    feed_name: str
    raw_fields: dict[
        str,
        str,
    ]


@dataclass(frozen=True, slots=True)
class WeWorkRemotelyJobsFetch:
    requests_made: int
    jobs: list[
        WeWorkRemotelyJobPosting
    ]


class WeWorkRemotelyJobsClient:
    def __init__(
        self,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.timeout_seconds = (
            timeout_seconds
        )

    def fetch_jobs(
        self,
        max_jobs: int,
    ) -> WeWorkRemotelyJobsFetch:
        if max_jobs < 1:
            raise ValueError(
                "max_jobs must be at least 1."
            )

        jobs: list[
            WeWorkRemotelyJobPosting
        ] = []
        seen_ids: set[str] = set()
        requests_made = 0

        with httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "chamba-hunter/0.1"
                ),
                "Accept": (
                    "application/rss+xml,"
                    "application/xml,"
                    "text/xml,"
                    "*/*;q=0.8"
                ),
            },
        ) as client:
            for feed_name, url in (
                WWR_FEED_URLS
            ):
                response = client.get(
                    url
                )

                requests_made += 1

                if (
                    response.status_code
                    == 429
                ):
                    raise RuntimeError(
                        "We Work Remotely "
                        "rate limit reached."
                    )

                response.raise_for_status()

                for job in _parse_feed(
                    response.text,
                    feed_name=feed_name,
                ):
                    if (
                        job.external_id
                        in seen_ids
                    ):
                        continue

                    seen_ids.add(
                        job.external_id
                    )
                    jobs.append(job)

        jobs.sort(
            key=_publication_sort_key,
            reverse=True,
        )

        return (
            WeWorkRemotelyJobsFetch(
                requests_made=(
                    requests_made
                ),
                jobs=jobs[:max_jobs],
            )
        )


def _parse_feed(
    raw_xml: str,
    *,
    feed_name: str,
) -> list[
    WeWorkRemotelyJobPosting
]:
    root = ElementTree.fromstring(
        raw_xml
    )

    jobs: list[
        WeWorkRemotelyJobPosting
    ] = []

    for item in root.iter():
        if (
            _local_name(item.tag)
            != "item"
        ):
            continue

        fields = (
            _item_fields(item)
        )

        link = _clean(
            _first(
                fields,
                "link",
            )
        )
        guid = _clean(
            _first(
                fields,
                "guid",
            )
        )

        external_id = (
            guid
            or link
        )

        if external_id is None:
            continue

        raw_title = _clean(
            _first(
                fields,
                "title",
            )
        )

        company = _clean(
            _first(
                fields,
                "company",
                "companyname",
            )
        )

        title = raw_title

        if (
            company is None
            and raw_title is not None
        ):
            (
                company_from_title,
                title_from_title,
            ) = _split_title(
                raw_title
            )

            if (
                company_from_title
                is not None
            ):
                company = (
                    company_from_title
                )
                title = title_from_title

        if (
            company is None
            or title is None
        ):
            continue

        description = _clean(
            _first(
                fields,
                "description",
                "encoded",
                "summary",
            )
        )

        region = _clean(
            _first(
                fields,
                "region",
                "location",
            )
        )

        employment_type = _clean(
            _first(
                fields,
                "employmenttype",
                "jobtype",
                "type",
            )
        )

        pub_date = _clean(
            _first(
                fields,
                "pubdate",
                "published",
                "date",
            )
        )

        jobs.append(
            WeWorkRemotelyJobPosting(
                external_id=external_id,
                title=title,
                company_name=company,
                link=(
                    link
                    or external_id
                ),
                description_html=(
                    description
                ),
                region=region,
                employment_type=(
                    employment_type
                ),
                pub_date=pub_date,
                feed_name=feed_name,
                raw_fields={
                    key: values[0]
                    for key, values
                    in fields.items()
                    if values
                },
            )
        )

    return jobs


def _item_fields(
    item,
) -> dict[
    str,
    list[str],
]:
    fields: dict[
        str,
        list[str],
    ] = {}

    for child in list(item):
        key = (
            _local_name(
                child.tag
            )
            .casefold()
        )

        value = "".join(
            child.itertext()
        ).strip()

        if not value:
            continue

        fields.setdefault(
            key,
            [],
        ).append(value)

    return fields


def _first(
    fields: dict[
        str,
        list[str],
    ],
    *names: str,
) -> str | None:
    for name in names:
        values = fields.get(
            name.casefold()
        )

        if values:
            return values[0]

    return None


def _local_name(
    tag: str,
) -> str:
    return (
        tag.rsplit(
            "}",
            1,
        )[-1]
    )


def _split_title(
    value: str,
) -> tuple[
    str | None,
    str,
]:
    if ":" not in value:
        return (
            None,
            value,
        )

    company, title = (
        value.split(
            ":",
            1,
        )
    )

    company = company.strip()
    title = title.strip()

    if (
        not company
        or not title
    ):
        return (
            None,
            value,
        )

    return (
        company,
        title,
    )


def _publication_sort_key(
    job: WeWorkRemotelyJobPosting,
) -> datetime:
    value = job.pub_date

    if not value:
        return datetime.min.replace(
            tzinfo=UTC
        )

    try:
        parsed = (
            parsedate_to_datetime(
                value
            )
        )
    except (
        TypeError,
        ValueError,
        OverflowError,
    ):
        return datetime.min.replace(
            tzinfo=UTC
        )

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=UTC
        )

    return parsed.astimezone(
        UTC
    )


def _clean(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    cleaned = " ".join(
        value.split()
    )

    return (
        cleaned
        if cleaned
        else None
    )
