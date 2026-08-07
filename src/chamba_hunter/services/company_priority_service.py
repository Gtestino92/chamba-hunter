from dataclasses import dataclass

from chamba_hunter.domain.enums import (
    CompanyType,
    TargetPriority,
)


@dataclass(frozen=True, slots=True)
class PriorityDecision:
    priority: TargetPriority

    remote_argentina: bool
    remote_latam: bool

    reasons: list[str]


def prioritize_company(
    company_type: CompanyType,
    metadata: dict,
) -> PriorityDecision:
    company_argentina = _flag(
        metadata,
        "company_argentina_signal",
    )

    company_buenos_aires = _flag(
        metadata,
        "company_buenos_aires_signal",
    )

    job_buenos_aires = _flag(
        metadata,
        "job_buenos_aires_signal",
    )

    remote_buenos_aires = _flag(
        metadata,
        "remote_buenos_aires_signal",
    )

    remote_global = _flag(
        metadata,
        "remote_global_signal",
    )

    remote_latam_signal = _flag(
        metadata,
        "remote_latam_signal",
    )

    remote_argentina_signal = _flag(
        metadata,
        "remote_argentina_signal",
    )

    remote_argentina_explicit = (
        remote_argentina_signal
        and not remote_global
        and not remote_latam_signal
    )

    remote_argentina = (
        remote_argentina_signal
    )

    remote_latam = (
        remote_latam_signal
        or remote_global
    )

    reasons: list[str] = []

    if company_argentina:
        reasons.append(
            "company based in Argentina"
        )

    if company_buenos_aires:
        reasons.append(
            "company based in Buenos Aires"
        )

    if job_buenos_aires:
        reasons.append(
            "job has Buenos Aires signal"
        )

    if remote_buenos_aires:
        reasons.append(
            "remote job has Buenos Aires signal"
        )

    if remote_argentina_explicit:
        reasons.append(
            "remote explicitly compatible "
            "with Argentina"
        )

    if remote_latam_signal:
        reasons.append(
            "remote compatible with LATAM/"
            "South America"
        )

    if remote_global:
        reasons.append(
            "fully remote/global"
        )

    if company_type == CompanyType.PRODUCT:
        reasons.append(
            "product company"
        )

    elif company_type == CompanyType.CONSULTANCY:
        reasons.append(
            "consultancy"
        )

    elif company_type == CompanyType.RECRUITER:
        reasons.append(
            "recruiter"
        )

    elif company_type == CompanyType.UNKNOWN:
        reasons.append(
            "company type unknown"
        )

    priority = _calculate_priority(
        company_type=company_type,
        company_argentina=company_argentina,
        company_buenos_aires=(
            company_buenos_aires
        ),
        job_buenos_aires=job_buenos_aires,
        remote_buenos_aires=(
            remote_buenos_aires
        ),
        remote_argentina=remote_argentina,
        remote_argentina_explicit=(
            remote_argentina_explicit
        ),
        remote_latam=remote_latam_signal,
        remote_global=remote_global,
    )

    return PriorityDecision(
        priority=priority,
        remote_argentina=remote_argentina,
        remote_latam=remote_latam,
        reasons=reasons,
    )


def _calculate_priority(
    company_type: CompanyType,
    company_argentina: bool,
    company_buenos_aires: bool,
    job_buenos_aires: bool,
    remote_buenos_aires: bool,
    remote_argentina: bool,
    remote_argentina_explicit: bool,
    remote_latam: bool,
    remote_global: bool,
) -> TargetPriority:
    if company_type == CompanyType.RECRUITER:
        return TargetPriority.LOW

    if (
        remote_buenos_aires
        or (
            company_buenos_aires
            and remote_argentina
        )
    ):
        return TargetPriority.VERY_HIGH

    if (
        company_buenos_aires
        or job_buenos_aires
    ):
        return TargetPriority.HIGH

    if (
        company_argentina
        and remote_argentina
    ):
        return TargetPriority.HIGH

    if remote_argentina_explicit:
        if company_type in {
            CompanyType.PRODUCT,
            CompanyType.UNKNOWN,
        }:
            return TargetPriority.HIGH

        return TargetPriority.MEDIUM

    if remote_latam:
        if company_type in {
            CompanyType.PRODUCT,
            CompanyType.UNKNOWN,
        }:
            return TargetPriority.HIGH

        return TargetPriority.MEDIUM

    if remote_global:
        if company_type == CompanyType.PRODUCT:
            return TargetPriority.HIGH

        return TargetPriority.MEDIUM

    if company_argentina:
        return TargetPriority.MEDIUM

    if company_type == CompanyType.PRODUCT:
        return TargetPriority.MEDIUM

    if company_type in {
        CompanyType.CONSULTANCY,
        CompanyType.OTHER,
    }:
        return TargetPriority.LOW

    return TargetPriority.UNKNOWN


def _flag(
    metadata: dict,
    key: str,
) -> bool:
    return metadata.get(key) is True