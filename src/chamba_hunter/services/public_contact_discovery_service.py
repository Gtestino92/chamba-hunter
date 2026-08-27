from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser
import re
from time import sleep
from urllib.parse import (
    urljoin,
    urlsplit,
    urlunsplit,
)
from xml.etree import ElementTree

import httpx

from chamba_hunter.domain.enums import (
    ContactType,
    RunStatus,
)
from chamba_hunter.domain.models import (
    Company,
    PublicContact,
)
from chamba_hunter.repositories.company_outreach_repository import (
    CompanyOutreachRepository,
)
from chamba_hunter.repositories.company_repository import (
    CompanyRepository,
)
from chamba_hunter.repositories.public_contact_repository import (
    PublicContactRepository,
)
from chamba_hunter.services.public_contact_quality import (
    classify_email,
    email_domain_compatible,
    normalize_email,
)


MAX_HTML_CHARS = 2_000_000
MAX_SCRIPT_CHARS = 4_000_000
MAX_SCRIPT_RESOURCES = 5

DEFAULT_MAX_PAGES_PER_COMPANY = 6
DEFAULT_REQUEST_DELAY_SECONDS = 0.10

EMAIL_PATTERN = re.compile(
    r"\b[A-Z0-9._%+\-]+@"
    r"[A-Z0-9.\-]+\.[A-Z]{2,}\b",
    re.IGNORECASE,
)

RELEVANT_LINK_TERMS = (
    "career",
    "careers",
    "job",
    "jobs",
    "work with us",
    "work-at",
    "workat",
    "join us",
    "join-us",
    "join our team",
    "talent",
    "people",
    "team",
    "contact",
    "contact-us",
    "about",
    "about-us",
    "empleo",
    "empleos",
    "trabaja",
    "trabajo",
    "trabaja-con-nosotros",
    "unete",
    "contacto",
    "nosotros",
    "equipo",
)

GENERAL_APPLICATION_TERMS = (
    "general application",
    "open application",
    "spontaneous application",
    "submit resume",
    "submit your resume",
    "send resume",
    "send cv",
    "envia tu cv",
    "envianos tu cv",
    "enviar cv",
    "candidatura espontanea",
    "postulacion espontanea",
    "talent community",
    "join our talent",
    "base de talentos",
)

FALLBACK_PATHS = (
    "/careers",
    "/jobs",
    "/work-with-us",
    "/join-us",
    "/contact",
    "/contact-us",
    "/contacto",
    "/trabaja-con-nosotros",
)


@dataclass(frozen=True, slots=True)
class Anchor:
    href: str
    text: str


@dataclass(frozen=True, slots=True)
class PageDocument:
    final_url: str
    text: str
    anchors: tuple[
        Anchor,
        ...
    ]
    mailtos: tuple[
        str,
        ...
    ]
    script_urls: tuple[
        str,
        ...
    ]


@dataclass(frozen=True, slots=True)
class CompanyContactDiscoveryResult:
    company_id: int
    company_name: str
    status: RunStatus
    pages_fetched: int
    contacts_created: int
    contacts_existing: int
    error_type: str | None = None
    error_message: str | None = None


@dataclass(slots=True)
class PublicContactDiscoverySummary:
    processed: int = 0
    succeeded: int = 0
    failed: int = 0
    pages_fetched: int = 0
    contacts_created: int = 0
    contacts_existing: int = 0
    results: list[
        CompanyContactDiscoveryResult
    ] = field(
        default_factory=list
    )


class _PageParser(HTMLParser):
    def __init__(
        self,
        *,
        base_url: str,
    ) -> None:
        super().__init__(
            convert_charrefs=True
        )

        self.base_url = base_url

        self.text_parts: list[
            str
        ] = []

        self.anchors: list[
            Anchor
        ] = []

        self.mailtos: list[
            str
        ] = []

        self.script_urls: list[
            str
        ] = []

        self._anchor_href: (
            str
            | None
        ) = None

        self._anchor_parts: list[
            str
        ] = []

        self._ignored_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[
            tuple[
                str,
                str | None,
            ]
        ],
    ) -> None:
        normalized_tag = (
            tag.casefold()
        )

        attributes = dict(
            attrs
        )

        if normalized_tag in {
            "script",
            "style",
            "noscript",
            "template",
        }:
            if normalized_tag == "script":
                src = attributes.get(
                    "src"
                )

                if src:
                    absolute = _normalize_url(
                        urljoin(
                            self.base_url,
                            src,
                        )
                    )

                    if (
                        absolute
                        and absolute
                        not in self.script_urls
                    ):
                        self.script_urls.append(
                            absolute
                        )

            self._ignored_depth += 1
            return

        if (
            normalized_tag != "a"
            or self._ignored_depth
        ):
            return

        href = attributes.get(
            "href"
        )

        self._anchor_href = href
        self._anchor_parts = []

        if (
            href is not None
            and href.casefold()
            .startswith("mailto:")
        ):
            email = (
                href.split(":", 1)[1]
                .split("?", 1)[0]
                .strip()
            )

            if email:
                self.mailtos.append(
                    email
                )

    def handle_endtag(
        self,
        tag: str,
    ) -> None:
        normalized_tag = (
            tag.casefold()
        )

        if normalized_tag in {
            "script",
            "style",
            "noscript",
            "template",
        }:
            if self._ignored_depth:
                self._ignored_depth -= 1
            return

        if (
            normalized_tag != "a"
            or self._anchor_href
            is None
        ):
            return

        self.anchors.append(
            Anchor(
                href=self._anchor_href,
                text=" ".join(
                    self._anchor_parts
                ).strip(),
            )
        )

        self._anchor_href = None
        self._anchor_parts = []

    def handle_data(
        self,
        data: str,
    ) -> None:
        if self._ignored_depth:
            return

        cleaned = " ".join(
            unescape(data).split()
        ).strip()

        if not cleaned:
            return

        self.text_parts.append(
            cleaned
        )

        if self._anchor_href is not None:
            self._anchor_parts.append(
                cleaned
            )


class PublicContactDiscoveryService:
    def __init__(
        self,
        *,
        company_repository: CompanyRepository,
        public_contact_repository: PublicContactRepository,
        outreach_repository: CompanyOutreachRepository,
        timeout_seconds: float = 15.0,
        request_delay_seconds: float = (
            DEFAULT_REQUEST_DELAY_SECONDS
        ),
    ) -> None:
        if request_delay_seconds < 0:
            raise ValueError(
                "request_delay_seconds cannot be negative."
            )

        self.company_repository = (
            company_repository
        )

        self.public_contact_repository = (
            public_contact_repository
        )

        self.outreach_repository = (
            outreach_repository
        )

        self.timeout_seconds = (
            timeout_seconds
        )

        self.request_delay_seconds = (
            request_delay_seconds
        )

    def run(
        self,
        *,
        company_ids: list[int],
        max_pages_per_company: int = (
            DEFAULT_MAX_PAGES_PER_COMPANY
        ),
    ) -> PublicContactDiscoverySummary:
        if max_pages_per_company < 1:
            raise ValueError(
                "max_pages_per_company must be at least 1."
            )

        summary = (
            PublicContactDiscoverySummary()
        )

        with httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "chamba-hunter/0.2 "
                    "(public contact discovery)"
                ),
                "Accept": (
                    "text/html,application/xhtml+xml,"
                    "application/xml;q=0.9,*/*;q=0.5"
                ),
            },
        ) as client:
            for index, company_id in enumerate(
                company_ids
            ):
                company = (
                    self.company_repository
                    .get_by_id(
                        company_id
                    )
                )

                if company is None:
                    continue

                result = self._scan_one(
                    client=client,
                    company=company,
                    max_pages=(
                        max_pages_per_company
                    ),
                )

                summary.processed += 1
                summary.pages_fetched += (
                    result.pages_fetched
                )
                summary.contacts_created += (
                    result.contacts_created
                )
                summary.contacts_existing += (
                    result.contacts_existing
                )

                if (
                    result.status
                    == RunStatus.SUCCESS
                ):
                    summary.succeeded += 1
                else:
                    summary.failed += 1

                summary.results.append(
                    result
                )

                if (
                    index
                    < len(company_ids) - 1
                    and self.request_delay_seconds
                    > 0
                ):
                    sleep(
                        self.request_delay_seconds
                    )

        return summary

    def _scan_one(
        self,
        *,
        client: httpx.Client,
        company: Company,
        max_pages: int,
    ) -> CompanyContactDiscoveryResult:
        if company.id is None:
            raise ValueError(
                "Company must have an id."
            )

        scan_id = (
            self.outreach_repository
            .start_contact_scan(
                company.id
            )
        )

        pages_fetched = 0
        created = 0
        existing = 0

        try:
            documents = (
                self._crawl_company(
                    client=client,
                    company=company,
                    max_pages=max_pages,
                )
            )

            pages_fetched = len(
                documents
            )

            discovered_emails: dict[
                str,
                tuple[
                    ContactType,
                    str,
                ],
            ] = {}

            for document in documents:
                for email in (
                    _visible_emails(
                        document
                    )
                ):
                    contact_type = (
                        classify_email(
                            email
                        )
                    )

                    if contact_type is None:
                        continue

                    if not _crawler_email_allowed(
                        email=email,
                        contact_type=(
                            contact_type
                        ),
                        company=company,
                    ):
                        continue

                    discovered_emails[
                        normalize_email(
                            email
                        )
                    ] = (
                        contact_type,
                        document.final_url,
                    )

            # React/Vue/etc. sites can return an app shell to
            # httpx while their public contact copy lives in a
            # same-origin JS bundle. Only high-signal recruiting /
            # careers addresses are accepted from bundles.
            if not any(
                contact_type
                in {
                    ContactType.RECRUITING_EMAIL,
                    ContactType.CAREERS_EMAIL,
                }
                for contact_type, _
                in discovered_emails.values()
            ):
                for email, source_url in (
                    _bundle_high_signal_emails(
                        client=client,
                        company=company,
                        documents=documents,
                    )
                ):
                    contact_type = (
                        classify_email(
                            email
                        )
                    )

                    if (
                        contact_type
                        not in {
                            ContactType.RECRUITING_EMAIL,
                            ContactType.CAREERS_EMAIL,
                        }
                    ):
                        continue

                    if not email_domain_compatible(
                        email,
                        company.website_url,
                    ):
                        continue

                    discovered_emails[
                        normalize_email(
                            email
                        )
                    ] = (
                        contact_type,
                        source_url,
                    )

            for (
                email,
                (
                    contact_type,
                    source_url,
                ),
            ) in discovered_emails.items():
                _, was_created = (
                    self.public_contact_repository
                    .add_or_touch(
                        PublicContact(
                            company_id=company.id,
                            contact_type=(
                                contact_type
                            ),
                            value=email,
                            source_url=source_url,
                            notes=(
                                "Discovered on "
                                "the company's "
                                "public website."
                            ),
                        )
                    )
                )

                if was_created:
                    created += 1
                else:
                    existing += 1

            for document in documents:
                for url in (
                    _general_application_urls(
                        document
                    )
                ):
                    _, was_created = (
                        self.public_contact_repository
                        .add_or_touch(
                            PublicContact(
                                company_id=company.id,
                                contact_type=(
                                    ContactType
                                    .GENERAL_APPLICATION_URL
                                ),
                                value=url,
                                source_url=(
                                    document.final_url
                                ),
                                notes=(
                                    "General/talent "
                                    "application link "
                                    "discovered on "
                                    "the company site."
                                ),
                            )
                        )
                    )

                    self.outreach_repository.fill_general_application_url(
                        company_id=company.id,
                        url=url,
                    )

                    if was_created:
                        created += 1
                    else:
                        existing += 1

            self.outreach_repository.finish_contact_scan(
                scan_id=scan_id,
                status=RunStatus.SUCCESS.value,
                pages_fetched=pages_fetched,
                contacts_found=(
                    created + existing
                ),
            )

            return (
                CompanyContactDiscoveryResult(
                    company_id=company.id,
                    company_name=company.name,
                    status=RunStatus.SUCCESS,
                    pages_fetched=pages_fetched,
                    contacts_created=created,
                    contacts_existing=existing,
                )
            )

        except (
            httpx.HTTPError,
            ValueError,
        ) as error:
            self.outreach_repository.finish_contact_scan(
                scan_id=scan_id,
                status=RunStatus.FAILED.value,
                pages_fetched=pages_fetched,
                contacts_found=(
                    created + existing
                ),
                error_type=(
                    type(error).__name__
                ),
                error_message=str(error),
            )

            return (
                CompanyContactDiscoveryResult(
                    company_id=company.id,
                    company_name=company.name,
                    status=RunStatus.FAILED,
                    pages_fetched=pages_fetched,
                    contacts_created=created,
                    contacts_existing=existing,
                    error_type=(
                        type(error).__name__
                    ),
                    error_message=str(
                        error
                    ),
                )
            )

    def _crawl_company(
        self,
        *,
        client: httpx.Client,
        company: Company,
        max_pages: int,
    ) -> list[
        PageDocument
    ]:
        if company.website_url is None:
            return []

        company_host = _hostname(
            company.website_url
        )

        if company_host is None:
            raise ValueError(
                "Company website has no hostname."
            )

        queue: list[str] = []

        for seed in (
            company.website_url,
            company.careers_url,
        ):
            if seed is None:
                continue

            normalized = (
                _normalize_url(
                    seed
                )
            )

            if (
                normalized is not None
                and normalized not in queue
            ):
                queue.append(
                    normalized
                )

        visited: set[
            str
        ] = set()

        documents: list[
            PageDocument
        ] = []

        homepage_loaded = False

        while (
            queue
            and len(documents)
            < max_pages
        ):
            url = queue.pop(
                0
            )

            if url in visited:
                continue

            visited.add(
                url
            )

            try:
                document = _fetch_page(
                    client=client,
                    url=url,
                )
            except httpx.HTTPStatusError:
                # The homepage is authoritative; if it is blocked/
                # broken, surface the failure. Optional discovered or
                # fallback paths are best-effort and may legitimately
                # 404.
                if not homepage_loaded:
                    raise
                continue
            except httpx.HTTPError:
                if not homepage_loaded:
                    raise
                continue

            homepage_loaded = True

            documents.append(
                document
            )

            for anchor in (
                document.anchors
            ):
                candidate = (
                    _normalize_url(
                        urljoin(
                            document.final_url,
                            anchor.href,
                        )
                    )
                )

                if candidate is None:
                    continue

                if candidate in visited:
                    continue

                if not _same_company_host(
                    candidate,
                    company_host,
                ):
                    continue

                if not _relevant_anchor(
                    anchor=anchor,
                    absolute_url=(
                        candidate
                    ),
                ):
                    continue

                if candidate not in queue:
                    queue.append(
                        candidate
                    )

        if (
            documents
            and len(documents) < max_pages
            and not queue
        ):
            for sitemap_url in (
                _sitemap_relevant_urls(
                    client=client,
                    website_url=(
                        company.website_url
                    ),
                    company_host=(
                        company_host
                    ),
                )
            ):
                if (
                    len(documents)
                    >= max_pages
                ):
                    break

                if sitemap_url in visited:
                    continue

                visited.add(
                    sitemap_url
                )

                try:
                    document = _fetch_page(
                        client=client,
                        url=sitemap_url,
                    )
                except httpx.HTTPError:
                    continue

                documents.append(
                    document
                )

        if (
            documents
            and len(documents) < max_pages
        ):
            root = (
                _site_root(
                    company.website_url
                )
            )

            for path in FALLBACK_PATHS:
                if (
                    len(documents)
                    >= max_pages
                ):
                    break

                candidate = _normalize_url(
                    urljoin(
                        root,
                        path,
                    )
                )

                if (
                    candidate is None
                    or candidate in visited
                ):
                    continue

                visited.add(
                    candidate
                )

                try:
                    document = _fetch_page(
                        client=client,
                        url=candidate,
                    )
                except httpx.HTTPError:
                    continue

                documents.append(
                    document
                )

        return documents


def _fetch_page(
    *,
    client: httpx.Client,
    url: str,
) -> PageDocument:
    response = client.get(
        url
    )

    response.raise_for_status()

    content_type = (
        response.headers.get(
            "content-type",
            "",
        )
        .casefold()
    )

    if (
        content_type
        and "html" not in content_type
        and "xhtml" not in content_type
    ):
        raise ValueError(
            "Expected HTML but received "
            f"{content_type!r} from {url}"
        )

    html = response.text[
        :MAX_HTML_CHARS
    ]

    parser = _PageParser(
        base_url=str(
            response.url
        )
    )

    parser.feed(
        html
    )
    parser.close()

    return PageDocument(
        final_url=str(
            response.url
        ),
        text=" ".join(
            parser.text_parts
        ),
        anchors=tuple(
            parser.anchors
        ),
        mailtos=tuple(
            parser.mailtos
        ),
        script_urls=tuple(
            parser.script_urls
        ),
    )


def _visible_emails(
    document: PageDocument,
) -> list[
    str
]:
    unique: list[
        str
    ] = []

    for raw in (
        *document.mailtos,
        *EMAIL_PATTERN.findall(
            document.text
        ),
    ):
        email = normalize_email(
            raw
        )

        if (
            classify_email(
                email
            )
            is None
        ):
            continue

        if email not in unique:
            unique.append(
                email
            )

    return unique


def _bundle_high_signal_emails(
    *,
    client: httpx.Client,
    company: Company,
    documents: list[
        PageDocument
    ],
) -> list[
    tuple[
        str,
        str,
    ]
]:
    if company.website_url is None:
        return []

    company_host = _hostname(
        company.website_url
    )

    if company_host is None:
        return []

    script_urls: list[
        str
    ] = []

    for document in documents:
        for url in (
            document.script_urls
        ):
            if (
                url not in script_urls
                and _same_company_host(
                    url,
                    company_host,
                )
            ):
                script_urls.append(
                    url
                )

            if (
                len(script_urls)
                >= MAX_SCRIPT_RESOURCES
            ):
                break

        if (
            len(script_urls)
            >= MAX_SCRIPT_RESOURCES
        ):
            break

    found: dict[
        str,
        str,
    ] = {}

    for url in script_urls:
        try:
            response = client.get(
                url
            )
            response.raise_for_status()
        except httpx.HTTPError:
            continue

        text = response.text[
            :MAX_SCRIPT_CHARS
        ]

        for raw in (
            EMAIL_PATTERN.findall(
                text
            )
        ):
            email = normalize_email(
                raw
            )

            contact_type = (
                classify_email(
                    email
                )
            )

            if (
                contact_type
                not in {
                    ContactType
                    .RECRUITING_EMAIL,
                    ContactType
                    .CAREERS_EMAIL,
                }
            ):
                continue

            if not email_domain_compatible(
                email,
                company.website_url,
            ):
                continue

            found[
                email
            ] = url

    return list(
        found.items()
    )


def _crawler_email_allowed(
    *,
    email: str,
    contact_type: ContactType,
    company: Company,
) -> bool:
    # The website crawler is deliberately stricter than
    # curated sources such as CESSI/manual imports.
    if not email_domain_compatible(
        email,
        company.website_url,
    ):
        return False

    return (
        contact_type
        in {
            ContactType.RECRUITING_EMAIL,
            ContactType.CAREERS_EMAIL,
            ContactType.GENERAL_EMAIL,
        }
    )


def _general_application_urls(
    document: PageDocument,
) -> list[
    str
]:
    result: list[
        str
    ] = []

    for anchor in document.anchors:
        absolute = _normalize_url(
            urljoin(
                document.final_url,
                anchor.href,
            )
        )

        if absolute is None:
            continue

        text = (
            f"{anchor.text} "
            f"{urlsplit(absolute).path}"
        ).casefold()

        if not any(
            term in text
            for term in (
                GENERAL_APPLICATION_TERMS
            )
        ):
            continue

        if absolute not in result:
            result.append(
                absolute
            )

    return result


def _sitemap_relevant_urls(
    *,
    client: httpx.Client,
    website_url: str,
    company_host: str,
) -> list[
    str
]:
    sitemap = urljoin(
        _site_root(
            website_url
        ),
        "/sitemap.xml",
    )

    try:
        response = client.get(
            sitemap
        )
        response.raise_for_status()
    except httpx.HTTPError:
        return []

    try:
        root = ElementTree.fromstring(
            response.text
        )
    except ElementTree.ParseError:
        return []

    result: list[
        str
    ] = []

    for element in root.iter():
        if not element.tag.casefold().endswith(
            "loc"
        ):
            continue

        if not element.text:
            continue

        candidate = _normalize_url(
            element.text
        )

        if candidate is None:
            continue

        if not _same_company_host(
            candidate,
            company_host,
        ):
            continue

        text = urlsplit(
            candidate
        ).path.casefold()

        if not any(
            term.replace(
                " ",
                "-"
            )
            in text
            or term
            in text
            for term in (
                RELEVANT_LINK_TERMS
            )
        ):
            continue

        if candidate not in result:
            result.append(
                candidate
            )

    return result


def _relevant_anchor(
    *,
    anchor: Anchor,
    absolute_url: str,
) -> bool:
    path = urlsplit(
        absolute_url
    ).path

    text = (
        f"{anchor.text} {path}"
    ).casefold()

    return any(
        term in text
        for term in (
            RELEVANT_LINK_TERMS
        )
    )


def _same_company_host(
    url: str,
    company_host: str,
) -> bool:
    host = _hostname(
        url
    )

    if host is None:
        return False

    company = (
        company_host
        .removeprefix(
            "www."
        )
    )

    current = (
        host.removeprefix(
            "www."
        )
    )

    return (
        current == company
        or current.endswith(
            "." + company
        )
    )


def _hostname(
    url: str,
) -> str | None:
    parsed = urlsplit(
        url
    )

    return (
        parsed.hostname.casefold()
        if parsed.hostname
        else None
    )


def _site_root(
    url: str,
) -> str:
    parsed = urlsplit(
        url
    )

    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            "/",
            "",
            "",
        )
    )


def _normalize_url(
    url: str,
) -> str | None:
    cleaned = url.strip()

    if not cleaned:
        return None

    parsed = urlsplit(
        cleaned
    )

    if (
        parsed.scheme.casefold()
        not in {
            "http",
            "https",
        }
    ):
        return None

    hostname = (
        parsed.hostname.casefold()
        if parsed.hostname
        else None
    )

    if hostname is None:
        return None

    netloc = hostname

    if parsed.port is not None:
        is_default = (
            parsed.scheme.casefold()
            == "http"
            and parsed.port == 80
        ) or (
            parsed.scheme.casefold()
            == "https"
            and parsed.port == 443
        )

        if not is_default:
            netloc = (
                f"{netloc}:{parsed.port}"
            )

    return urlunsplit(
        (
            parsed.scheme.casefold(),
            netloc,
            parsed.path.rstrip("/"),
            parsed.query,
            "",
        )
    )
