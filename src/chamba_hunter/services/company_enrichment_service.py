from dataclasses import dataclass, field

from pydantic import AnyHttpUrl, TypeAdapter, ValidationError

from chamba_hunter.domain.enums import CompanyType, SourceType
from chamba_hunter.domain.models import CompanyClassification
from chamba_hunter.repositories.company_classification_repository import (
    CompanyClassificationRepository,
)
from chamba_hunter.repositories.company_repository import (
    CompanyRepository,
)
from chamba_hunter.repositories.company_source_repository import (
    CompanySourceRepository,
)
from chamba_hunter.services.company_classifier import (
    classify_company,
)
from chamba_hunter.services.company_import_service import (
    extract_domain,
    normalize_website_url,
)
from chamba_hunter.sources.himalayas import HimalayasClient


URL_ADAPTER = TypeAdapter(AnyHttpUrl)


@dataclass(slots=True)
class EnrichmentSummary:
    processed: int = 0
    websites_found: int = 0
    classified: int = 0
    unknown: int = 0
    domain_conflicts: int = 0
    failed: int = 0

    errors: list[str] = field(default_factory=list)


class CompanyEnrichmentService:
    def __init__(
        self,
        himalayas_client: HimalayasClient,
        company_repository: CompanyRepository,
        company_source_repository: CompanySourceRepository,
        classification_repository: CompanyClassificationRepository,
    ) -> None:
        self.himalayas_client = himalayas_client
        self.company_repository = company_repository
        self.company_source_repository = company_source_repository
        self.classification_repository = classification_repository

    def enrich_himalayas(
        self,
        limit: int | None = None,
    ) -> EnrichmentSummary:
        summary = EnrichmentSummary()

        sources = self.company_source_repository.list_by_source_type(
            SourceType.HIMALAYAS
        )

        if limit is not None:
            sources = sources[:limit]

        for source in sources:
            if source.external_id is None:
                continue

            try:
                self._enrich_one(
                    source.company_id,
                    source.external_id,
                    summary,
                )
            except Exception as exc:
                summary.failed += 1
                summary.errors.append(
                    f"{source.external_id}: {exc}"
                )

        return summary

    def _enrich_one(
        self,
        company_id: int,
        slug: str,
        summary: EnrichmentSummary,
    ) -> None:
        company = self.company_repository.get_by_id(
            company_id
        )

        if company is None:
            raise RuntimeError(
                f"Missing company {company_id}"
            )

        profile = self.himalayas_client.get_company_profile(
            slug
        )

        summary.processed += 1

        decision = classify_company(profile)

        website_url: str | None = None
        domain: str | None = None

        if (
            company.website_url is None
            and profile.official_website is not None
        ):
            try:
                validated_url = URL_ADAPTER.validate_python(
                    profile.official_website
                )

                candidate_url = normalize_website_url(
                    validated_url
                )
                candidate_domain = extract_domain(
                    validated_url
                )

                conflicting = (
                    self.company_repository.get_by_domain(
                        candidate_domain
                    )
                )

                if (
                    conflicting is not None
                    and conflicting.id != company.id
                ):
                    summary.domain_conflicts += 1
                else:
                    website_url = candidate_url
                    domain = candidate_domain
                    summary.websites_found += 1

            except ValidationError:
                pass

        company_type: CompanyType | None = None

        if (
            company.company_type == CompanyType.UNKNOWN
            and decision.company_type != CompanyType.UNKNOWN
        ):
            company_type = decision.company_type
            summary.classified += 1
        elif decision.company_type == CompanyType.UNKNOWN:
            summary.unknown += 1

        self.company_repository.update_enrichment(
            company_id=company.id,
            website_url=website_url,
            domain=domain,
            company_type=company_type,
        )

        self.classification_repository.add(
            CompanyClassification(
                company_id=company.id,
                company_type=decision.company_type,
                confidence=decision.confidence,
                method="HIMALAYAS_PROFILE_RULES",
                source_url=profile.source_url,
                evidence=decision.evidence,
            )
        )