from urllib.parse import urlparse

from chamba_hunter.domain.enums import AtsProvider
from chamba_hunter.domain.job_leads import JobAtsHint


def ats_hint_from_url(
    *,
    job_lead_id: int,
    company_id: int,
    url: str,
) -> JobAtsHint | None:
    cleaned = _clean_text(url)

    if cleaned is None:
        return None

    parsed = urlparse(cleaned)

    host = (
        parsed.hostname.casefold()
        if parsed.hostname
        else ""
    )

    segments = [
        segment
        for segment in parsed.path.split("/")
        if segment
    ]

    provider: AtsProvider | None = None
    identifier: str | None = None

    if host.endswith("greenhouse.io") and segments:
        provider = AtsProvider.GREENHOUSE
        identifier = segments[0]

    elif host == "jobs.ashbyhq.com" and segments:
        provider = AtsProvider.ASHBY
        identifier = segments[0]

    elif host == "jobs.lever.co" and segments:
        provider = AtsProvider.LEVER
        identifier = segments[0]

    elif (
        host == "apply.workable.com"
        and segments
        and segments[0].casefold()
        not in {"j", "jobs"}
    ):
        provider = AtsProvider.WORKABLE
        identifier = segments[0]

    elif (
        host == "jobs.smartrecruiters.com"
        and segments
    ):
        provider = AtsProvider.SMARTRECRUITERS
        identifier = segments[0]

    elif host.endswith(".bamboohr.com"):
        subdomain = host.removesuffix(
            ".bamboohr.com"
        )

        if subdomain:
            provider = AtsProvider.BAMBOOHR
            identifier = subdomain

    identifier = _clean_text(identifier)

    if provider is None or identifier is None:
        return None

    return JobAtsHint(
        job_lead_id=job_lead_id,
        company_id=company_id,
        provider=provider,
        external_identifier=identifier,
        source_url=cleaned,
    )


def _clean_text(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    cleaned = " ".join(value.split())

    return cleaned if cleaned else None
