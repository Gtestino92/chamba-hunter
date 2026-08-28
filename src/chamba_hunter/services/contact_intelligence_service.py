from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
import re
from urllib.parse import urlsplit

import httpx

from chamba_hunter.domain.common import utc_now
from chamba_hunter.domain.enums import ContactType
from chamba_hunter.repositories.contact_intelligence_repository import (
    ContactIntelligenceRepository,
    ContactIntelligenceTarget,
    ContactIntelligenceWrite,
)
from chamba_hunter.services.public_contact_quality import (
    GENERIC_USEFUL_LOCAL_PARTS,
    compact_local_part,
    contact_quality_score_for,
    is_free_email,
    is_low_value_email,
    split_email,
)


RULE_VERSION = "CONTACT_INTELLIGENCE_V3_2"
DEFAULT_LIMIT = 500
DEFAULT_TIMEOUT_SECONDS = 12.0
MAX_RESPONSE_CHARS = 1_500_000
CONTEXT_RADIUS = 850
MAX_CONTEXT_CHARS = 700
ROLE_CONTEXT_RADIUS = 220

ABOUT_PATH_TERMS = (
    "about",
    "team",
    "people",
    "leadership",
    "company",
    "nosotros",
    "equipo",
    "quienes-somos",
)

CAREER_PATH_TERMS = (
    "career",
    "careers",
    "jobs",
    "job",
    "work-with-us",
    "join-us",
    "talent",
    "empleo",
    "empleos",
    "trabaja",
    "vacante",
)

RECRUITING_ROLE_TERMS = (
    "recruiter",
    "recruiting",
    "talent acquisition",
    "talent partner",
    "people operations",
    "people ops",
    "human resources",
    "recursos humanos",
    "rrhh",
    "hiring manager",
)

TECH_LEADERSHIP_TERMS = (
    "chief technology officer",
    "cto",
    "vp engineering",
    "vp of engineering",
    "head of engineering",
    "head of technology",
    "engineering director",
    "director of engineering",
    "technical director",
    "director tecnico",
    "director técnico",
    "engineering manager",
    "gerente de tecnologia",
    "gerente de tecnología",
    "tech lead",
)

ENGINEERING_ROLE_TERMS = (
    "software engineer",
    "software developer",
    "backend engineer",
    "backend developer",
    "developer",
    "engineer",
    "engineering",
    "desarrollador",
    "desarrolladora",
    "ingeniero",
    "ingeniera",
    "tecnologia",
    "tecnología",
    "technology",
)

STRONG_LEADERSHIP_ROLE_TERMS = (
    "co-founder",
    "cofounder",
    "founder",
    "fundador",
    "fundadora",
    "cofundador",
    "cofundadora",
    "chief executive officer",
    "ceo",
    "owner",
    "president",
    "partner",
    "socio",
    "socia",
)

MANAGEMENT_ROLE_TERMS = (
    "director",
    "gerente",
    "manager",
)

OPERATIONS_ROLE_TERMS = (
    "operations latam",
    "operations manager",
    "head of operations",
    "director of operations",
    "gerente de operaciones",
    "director de operaciones",
)

HIRING_CONTEXT_TERMS = (
    "we are hiring",
    "we're hiring",
    "hiring",
    "join our team",
    "join the team",
    "send your resume",
    "send your cv",
    "envia tu cv",
    "envía tu cv",
    "trabaja con nosotros",
    "vacantes",
)

NON_TARGET_ROLE_TERMS = (
    "vp sales",
    "vp of sales",
    "vice president sales",
    "vp comercial",
    "vicepresidente comercial",
    "head of sales",
    "sales manager",
    "sales director",
    "director of sales",
    "gerente de ventas",
    "director de ventas",
    "head of marketing",
    "marketing manager",
    "marketing director",
    "director of marketing",
    "gerente de marketing",
    "director de marketing",
    "key account manager",
    "account executive",
    "strategic partnerships",
    "partnerships manager",
    "business development manager",
    "business development",
    "legal counsel",
    "general counsel",
    "legal manager",
    "chief financial officer",
    "cfo",
    "finance manager",
    "accountant",
    "contador",
    "contadora",
    "customer success manager",
    "customer support",
    "support manager",
    "press contact",
    "media contact",
    "data protection officer",
    "dpo",
)

NON_HTML_SUFFIXES = (
    ".js",
    ".css",
    ".json",
    ".xml",
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".webp",
)


@dataclass(frozen=True, slots=True)
class ContactIntelligenceEvaluation:
    score: float
    label: str
    role_hint: str | None
    context: str | None
    source_kind: str


@dataclass(frozen=True, slots=True)
class ContactIntelligenceSummary:
    inspected: int
    evaluated: int
    named_contacts: int
    direct_contacts: int
    page_fetches: int
    fetch_failures: int


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs,
    ) -> None:
        if tag.casefold() in {
            "script",
            "style",
            "noscript",
            "template",
        }:
            self._ignored_depth += 1

    def handle_endtag(
        self,
        tag: str,
    ) -> None:
        if (
            tag.casefold()
            in {
                "script",
                "style",
                "noscript",
                "template",
            }
            and self._ignored_depth
        ):
            self._ignored_depth -= 1

    def handle_data(
        self,
        data: str,
    ) -> None:
        if self._ignored_depth:
            return

        cleaned = " ".join(
            unescape(data).split()
        ).strip()

        if cleaned:
            self.parts.append(cleaned)


class ContactIntelligenceService:
    def __init__(
        self,
        repository: ContactIntelligenceRepository,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.repository = repository
        self.timeout_seconds = timeout_seconds

    def run(
        self,
        *,
        limit: int = DEFAULT_LIMIT,
        force: bool = False,
    ) -> ContactIntelligenceSummary:
        targets = self.repository.list_targets(
            rule_version=RULE_VERSION,
            limit=limit,
            force=force,
        )

        named_contacts = 0
        direct_contacts = 0
        page_fetches = 0
        fetch_failures = 0
        cache: dict[str, str | None] = {}

        with httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "chamba-hunter/0.3 "
                    "(public contact intelligence)"
                ),
                "Accept": (
                    "text/html,application/xhtml+xml,"
                    "application/xml;q=0.9,*/*;q=0.5"
                ),
            },
        ) as client:
            for target in targets:
                named = _is_named_email(
                    target.contact_type,
                    target.value,
                )

                if named:
                    named_contacts += 1

                context: str | None = None
                fetch_failed = False

                if (
                    named
                    and _can_fetch_source(
                        target.source_url
                    )
                ):
                    source_url = str(
                        target.source_url
                    )

                    if source_url not in cache:
                        page_fetches += 1

                        try:
                            response = client.get(
                                source_url
                            )
                            response.raise_for_status()
                            cache[source_url] = (
                                response.text[
                                    :MAX_RESPONSE_CHARS
                                ]
                            )
                        except httpx.HTTPError:
                            cache[source_url] = None
                            fetch_failures += 1

                    html = cache[source_url]

                    if html is None:
                        fetch_failed = True
                    else:
                        context = _extract_context(
                            html,
                            target.value,
                        )

                evaluation = evaluate_contact_intelligence(
                    target=target,
                    context=context,
                    fetch_failed=fetch_failed,
                )

                if evaluation.score > 20:
                    direct_contacts += 1

                self.repository.upsert(
                    ContactIntelligenceWrite(
                        public_contact_id=(
                            target.contact_id
                        ),
                        score=evaluation.score,
                        label=evaluation.label,
                        role_hint=(
                            evaluation.role_hint
                        ),
                        context=evaluation.context,
                        source_kind=(
                            evaluation.source_kind
                        ),
                        rule_version=RULE_VERSION,
                        evaluated_at=utc_now(),
                    )
                )

        return ContactIntelligenceSummary(
            inspected=len(targets),
            evaluated=len(targets),
            named_contacts=named_contacts,
            direct_contacts=direct_contacts,
            page_fetches=page_fetches,
            fetch_failures=fetch_failures,
        )


def evaluate_contact_intelligence(
    *,
    target: ContactIntelligenceTarget,
    context: str | None,
    fetch_failed: bool = False,
) -> ContactIntelligenceEvaluation:
    contact_type = ContactType(
        target.contact_type
    )

    if (
        contact_type
        == ContactType.GENERAL_APPLICATION_URL
    ):
        return ContactIntelligenceEvaluation(
            score=8.0,
            label="GENERAL_APPLICATION",
            role_hint=None,
            context=None,
            source_kind="STATIC",
        )

    base_score = contact_quality_score_for(
        contact_type,
        target.value,
    )

    if base_score <= 0:
        return ContactIntelligenceEvaluation(
            score=0.0,
            label="LOW_VALUE",
            role_hint=None,
            context=context,
            source_kind="STATIC",
        )

    if (
        contact_type
        == ContactType.RECRUITING_EMAIL
    ):
        return ContactIntelligenceEvaluation(
            score=base_score,
            label="RECRUITING_INBOX",
            role_hint="RECRUITING",
            context=context,
            source_kind="STATIC",
        )

    if (
        contact_type
        == ContactType.CAREERS_EMAIL
    ):
        return ContactIntelligenceEvaluation(
            score=base_score,
            label="CAREERS_INBOX",
            role_hint="CAREERS",
            context=context,
            source_kind="STATIC",
        )

    if not _is_named_email(
        target.contact_type,
        target.value,
    ):
        return ContactIntelligenceEvaluation(
            score=base_score,
            label="GENERAL_INBOX",
            role_hint=None,
            context=context,
            source_kind="STATIC",
        )

    free_mail = is_free_email(
        target.value
    )

    score = (
        6.0
        if free_mail
        else 15.0
    )

    source_kind = "STATIC"
    path_signal = _source_path_signal(
        target.source_url
    )

    if path_signal == "ABOUT":
        score = max(
            score,
            12.0 if free_mail else 18.0,
        )
        source_kind = "SOURCE_PATH"

    elif path_signal == "CAREERS":
        score = max(
            score,
            13.0 if free_mail else 19.0,
        )
        source_kind = "SOURCE_PATH"

    normalized_context = (
        _normalize_context(context)
        if context
        else ""
    )

    directory_source = (
        _is_cessi_directory_source(
            target.source_url
        )
    )

    # CESSI directory cards describe the company activity, not the
    # role of the mailbox owner. Treat that text as provenance only.
    # Otherwise phrases such as "desarrollo de software" can make a
    # public contact look like an engineer/technical leader.
    role_hint = (
        None
        if directory_source
        else _role_hint(
            normalized_context,
            target.value,
        )
    )

    if role_hint == "RECRUITING":
        score = 18.0 if free_mail else 30.0
        label = "DIRECT_RECRUITING_PERSON"
    elif role_hint == "TECH_LEADERSHIP":
        score = 18.0 if free_mail else 30.0
        label = "DIRECT_TECH_LEADER"
    elif role_hint == "ENGINEERING":
        score = 17.0 if free_mail else 28.0
        label = "DIRECT_ENGINEERING"
    elif role_hint == "LEADERSHIP":
        score = 16.0 if free_mail else 27.0
        label = "DIRECT_LEADER"
    elif role_hint == "OPERATIONS":
        score = 12.0 if free_mail else 16.0
        label = "DIRECT_OPERATIONS"
    elif role_hint == "HIRING_CONTEXT":
        score = 16.0 if free_mail else 25.0
        label = "DIRECT_HIRING_CONTEXT"
    elif role_hint == "NON_TARGET":
        score = min(score, 5.0)
        label = "DIRECT_NON_TARGET"
    elif fetch_failed and score > 15.0:
        score = min(score, 19.0)
        label = "DIRECT_PERSON_PATH_ONLY"
    elif score > 15.0:
        label = "DIRECT_PERSON"
    else:
        label = "NAMED_PUBLIC"

    if normalized_context:
        source_kind = (
            "DIRECTORY_CONTEXT"
            if directory_source
            else "PAGE_CONTEXT"
        )
    elif fetch_failed:
        source_kind = (
            "FETCH_FAILED"
            if source_kind == "STATIC"
            else source_kind
        )

    return ContactIntelligenceEvaluation(
        score=round(score, 2),
        label=label,
        role_hint=(
            None
            if role_hint in {
                None,
                "NON_TARGET",
                "HIRING_CONTEXT",
            }
            else role_hint
        ),
        context=context,
        source_kind=source_kind,
    )


def _is_named_email(
    contact_type: str,
    value: str,
) -> bool:
    if contact_type != ContactType.GENERAL_EMAIL.value:
        return False

    if is_low_value_email(value):
        return False

    split = split_email(value)

    if split is None:
        return False

    local_part, _ = split
    compact = compact_local_part(
        local_part
    )

    generic_compact = {
        compact_local_part(item)
        for item in GENERIC_USEFUL_LOCAL_PARTS
    }

    return (
        local_part
        not in GENERIC_USEFUL_LOCAL_PARTS
        and compact not in generic_compact
    )


def _source_path_signal(
    source_url: str | None,
) -> str | None:
    if not source_url:
        return None

    path = urlsplit(
        source_url
    ).path.casefold()

    if any(
        term in path
        for term in CAREER_PATH_TERMS
    ):
        return "CAREERS"

    if any(
        term in path
        for term in ABOUT_PATH_TERMS
    ):
        return "ABOUT"

    return None


def _can_fetch_source(
    source_url: str | None,
) -> bool:
    if not source_url:
        return False

    parsed = urlsplit(source_url)

    if parsed.scheme.casefold() not in {
        "http",
        "https",
    }:
        return False

    path = parsed.path.casefold()

    return not path.endswith(
        NON_HTML_SUFFIXES
    )


def _extract_context(
    html: str,
    email: str,
) -> str | None:
    matches = list(
        re.finditer(
            re.escape(email),
            html,
            flags=re.IGNORECASE,
        )
    )[:5]

    best = ""

    for match in matches:
        start = max(
            0,
            match.start() - CONTEXT_RADIUS,
        )
        end = min(
            len(html),
            match.end() + CONTEXT_RADIUS,
        )

        fragment = html[
            start:end
        ]

        parser = _VisibleTextParser()

        try:
            parser.feed(fragment)
            parser.close()
        except Exception:
            continue

        text = " ".join(
            parser.parts
        ).strip()

        if len(text) > len(best):
            best = text

    if not best:
        return None

    return best[
        :MAX_CONTEXT_CHARS
    ]


def _normalize_context(
    context: str | None,
) -> str:
    if not context:
        return ""

    text = unescape(
        context
    ).casefold()

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def _contains_any(
    text: str,
    terms: tuple[str, ...],
) -> bool:
    return any(
        term in text
        for term in terms
    )


def _is_cessi_directory_source(
    source_url: str | None,
) -> bool:
    if not source_url:
        return False

    hostname = urlsplit(
        source_url
    ).hostname

    if hostname is None:
        return False

    hostname = (
        hostname.casefold()
        .removeprefix("www.")
    )

    return (
        hostname == "cessi.org.ar"
        or hostname.endswith(
            ".cessi.org.ar"
        )
    )


def _term_matches(
    text: str,
    term: str,
):
    # Role tokens must be lexical terms, not arbitrary substrings.
    # In particular, "cto" must not match Spanish "contacto".
    pattern = (
        r"(?<!\w)"
        + re.escape(term)
        + r"(?!\w)"
    )

    return re.finditer(
        pattern,
        text,
    )


def _role_hint(
    context: str,
    email: str,
) -> str | None:
    if not context:
        return None

    normalized_email = (
        email.strip().casefold()
    )
    email_index = context.find(
        normalized_email
    )

    if email_index >= 0:
        start = max(
            0,
            email_index - ROLE_CONTEXT_RADIUS,
        )
        end = min(
            len(context),
            email_index
            + len(normalized_email)
            + ROLE_CONTEXT_RADIUS,
        )
        local_context = context[start:end]
        local_email_start = (
            email_index - start
        )
        local_email_end = (
            local_email_start
            + len(normalized_email)
        )

        # Pick the role phrase physically closest to the mailbox rather
        # than the highest-precedence title anywhere in the surrounding
        # team section. Longer phrases win ties, so "sales director"
        # beats the generic substring "director".
        groups = (
            (
                "RECRUITING",
                RECRUITING_ROLE_TERMS,
                0,
            ),
            (
                "TECH_LEADERSHIP",
                TECH_LEADERSHIP_TERMS,
                1,
            ),
            (
                "NON_TARGET",
                NON_TARGET_ROLE_TERMS,
                2,
            ),
            (
                "OPERATIONS",
                OPERATIONS_ROLE_TERMS,
                3,
            ),
            (
                "ENGINEERING",
                ENGINEERING_ROLE_TERMS,
                4,
            ),
            (
                "LEADERSHIP",
                STRONG_LEADERSHIP_ROLE_TERMS,
                5,
            ),
            (
                "LEADERSHIP",
                MANAGEMENT_ROLE_TERMS,
                6,
            ),
        )

        matches: list[
            tuple[
                int,
                int,
                int,
                str,
            ]
        ] = []

        for (
            hint,
            terms,
            priority,
        ) in groups:
            for term in terms:
                for match in _term_matches(
                    local_context,
                    term,
                ):
                    if (
                        match.end()
                        <= local_email_start
                    ):
                        distance = (
                            local_email_start
                            - match.end()
                        )
                    elif (
                        match.start()
                        >= local_email_end
                    ):
                        distance = (
                            match.start()
                            - local_email_end
                        )
                    else:
                        distance = 0

                    matches.append(
                        (
                            distance,
                            -len(term),
                            priority,
                            hint,
                        )
                    )

        if matches:
            matches.sort()
            return matches[0][3]

    # Hiring copy is page/context evidence rather than a person's role.
    # It can raise a named mailbox modestly, but only after no local
    # person-role signal was found.
    if _contains_any(
        context,
        HIRING_CONTEXT_TERMS,
    ):
        return "HIRING_CONTEXT"

    return None
