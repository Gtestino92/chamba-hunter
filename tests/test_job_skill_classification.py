import pytest

from chamba_hunter.repositories.job_skill_repository import (
    SkillCandidateRow,
)
from chamba_hunter.services import (
    job_skill_classification_service as service,
)


def classify(
    description: str,
    title: str = "Referente Técnico",
    rule_version: str = service.RULE_VERSION,
) -> set[str]:
    decisions = service._extract_candidate_skills(
        SkillCandidateRow(
            record_kind="ATS",
            record_id=1,
            source_type="ATS",
            origin="SUCCESSFACTORS",
            company_name="Example",
            eligibility_status="UNKNOWN",
            occupation_class="SOFTWARE_ENGINEERING",
            backend_relevance="FULL_STACK",
            title=title,
            description=description,
        ),
        rule_version=rule_version,
    )

    return {
        decision.skill_key
        for decision in decisions
    }


def test_rule_version_is_v2() -> None:
    assert service.RULE_VERSION == "SKILLS_V2"


def test_skills_v3_apply_is_explicitly_disabled() -> None:
    classifier = service.JobSkillClassificationService(
        repository=None,  # type: ignore[arg-type]
        tracing_repository=None,  # type: ignore[arg-type]
        rule_version=service.SKILLS_V3_RULE_VERSION,
    )
    with pytest.raises(ValueError, match="evaluation-only"):
        classifier.run(apply=True)


def test_microservices_spanish_alias() -> None:
    assert "MICROSERVICES" in classify(
        "Experiencia en arquitectura de microservicios."
    )


@pytest.mark.parametrize(
    "description",
    [
        "Diseño de APIs REST para canales digitales.",
        "Diseño de API REST para canales digitales.",
        "Integración mediante servicios REST.",
    ],
)
def test_rest_api_spanish_aliases(
    description: str,
) -> None:
    assert "REST" in classify(
        description
    )


def test_distributed_systems_spanish_alias() -> None:
    assert "DISTRIBUTED_SYSTEMS" in classify(
        "Experiencia construyendo sistemas distribuidos."
    )


def test_event_driven_spanish_alias() -> None:
    assert "EVENT_DRIVEN" in classify(
        "Diseño de arquitectura orientada a eventos."
    )


def test_java_spring_boot_punctuation_in_spanish_context() -> None:
    skills = classify(
        "Experiencia en desarrollo backend con Java 17 y Spring Boot."
    )

    assert {
        "JAVA",
        "SPRING_BOOT",
    } <= skills


def test_database_exact_technologies_continue_to_match() -> None:
    skills = classify(
        "Experiencia con Oracle / PL-SQL, PostgreSQL y MongoDB."
    )

    assert {
        "ORACLE_DB",
        "POSTGRESQL",
        "MONGODB",
    } <= skills


def test_generic_relational_database_does_not_invent_vendor() -> None:
    skills = classify(
        "Experiencia con bases de datos relacionales."
    )

    assert not (
        skills
        & {
            "POSTGRESQL",
            "ORACLE_DB",
            "MYSQL",
            "SQL_SERVER",
            "MARIADB",
        }
    )


def test_generic_cloud_does_not_invent_provider() -> None:
    skills = classify(
        "Experiencia en infraestructura cloud."
    )

    assert not (
        skills
        & {
            "AWS",
            "AZURE",
            "GCP",
        }
    )


def test_explicit_aws_spanish_context() -> None:
    assert "AWS" in classify(
        "Experiencia administrando servicios AWS."
    )


def test_commercial_catalog_does_not_infer_backend_stack() -> None:
    skills = classify(
        (
            "Venta consultiva de soluciones de Cloud, Datacenter, "
            "Desarrollo de Software, ERP, CRM, Ciberseguridad e IA."
        ),
        title="Ejecutivo de Soluciones Digitales",
    )

    assert not (
        skills
        & {
            "JAVA",
            "SPRING",
            "SPRING_BOOT",
            "NODEJS",
            "KAFKA",
            "POSTGRESQL",
        }
    )


def test_functional_salesforce_does_not_infer_backend_stack() -> None:
    skills = classify(
        (
            "Analista funcional CRM Salesforce. "
            "Integraciones y requerimientos funcionales."
        ),
        title="Analista Funcional CRM Salesforce B2B",
    )

    assert "SALESFORCE" in skills
    assert not (
        skills
        & {
            "JAVA",
            "SPRING",
            "SPRING_BOOT",
            "NODEJS",
            "KAFKA",
            "POSTGRESQL",
        }
    )


def test_existing_english_global_cases_stay_stable() -> None:
    skills = classify(
        (
            "Build distributed systems, REST APIs, microservices, "
            "event-driven services with Java and Spring Boot on "
            "PostgreSQL."
        )
    )

    assert {
        "DISTRIBUTED_SYSTEMS",
        "REST",
        "MICROSERVICES",
        "EVENT_DRIVEN",
        "JAVA",
        "SPRING_BOOT",
        "POSTGRESQL",
    } <= skills


def classify_v3(description: str, title: str = "Senior Backend Engineer") -> set[str]:
    return classify(description, title, service.SKILLS_V3_RULE_VERSION)


def test_skills_v3_detects_authentication_authorization_service_development() -> None:
    skills = classify_v3(
        "Build backend authentication and authorization services with Java and Spring Boot."
    )
    assert {"AUTHENTICATION", "AUTHORIZATION", "JAVA", "SPRING_BOOT"} <= skills


def test_skills_v3_detects_resilience_implementation() -> None:
    skills = classify_v3(
        "Implement reliability and resilience using retries, idempotency, and circuit breakers."
    )
    assert {"RELIABILITY", "RESILIENCE", "RETRIES", "IDEMPOTENCY", "CIRCUIT_BREAKER"} <= skills


def test_skills_v3_detects_generic_platform_evidence_without_inventing_vendor() -> None:
    skills = classify_v3("Cloud services with CI/CD and observability practices.")
    assert {"CLOUD_GENERIC", "CI_CD_GENERIC", "OBSERVABILITY_GENERIC"} <= skills
    assert not skills & {"AWS", "AZURE", "GCP"}


def test_skills_v3_distinguishes_api_development_from_api_consumption() -> None:
    assert "API_DEVELOPMENT" in classify_v3(
        "Design and build application APIs for partner integrations."
    )
    assert "API_DEVELOPMENT" not in classify_v3(
        "Consume third-party APIs and review API documentation."
    )


def test_skills_v3_detects_explicit_integration_development() -> None:
    assert "INTEGRATION_DEVELOPMENT" in classify_v3(
        "Develop integrations between backend payment services and banking partners."
    )


def test_v3_domain_evidence_is_non_persisted_supporting_context() -> None:
    candidate = SkillCandidateRow(
        record_kind="ATS",
        record_id=2,
        source_type="ATS",
        origin="GREENHOUSE",
        company_name="Example",
        eligibility_status="ELIGIBLE",
        occupation_class="SOFTWARE_ENGINEERING",
        backend_relevance="BACKEND",
        title="Payments Backend Engineer",
        description="Build payment processing services and IAM authentication APIs.",
    )
    evidence = service.extract_v3_domain_evidence(candidate)
    assert evidence == ("IAM_DOMAIN", "PAYMENTS_DOMAIN")
    persisted_keys = {
        decision.skill_key
        for decision in service._extract_candidate_skills(
            candidate,
            rule_version=service.SKILLS_V3_RULE_VERSION,
        )
    }
    assert "IAM_DOMAIN" not in persisted_keys
    assert "PAYMENTS_DOMAIN" not in persisted_keys


def test_iam_governance_and_kubernetes_terraform_do_not_invent_development() -> None:
    skills = classify_v3(
        "IAM provisioning, access reviews and lifecycle governance. "
        "Administer Kubernetes and Terraform."
    )
    assert "API_DEVELOPMENT" not in skills
    assert "INTEGRATION_DEVELOPMENT" not in skills
    assert {"KUBERNETES", "TERRAFORM"} <= skills


def test_incidental_java_reference_adds_no_development_evidence() -> None:
    skills = classify_v3(
        "Review vendor systems; Java familiarity is a plus for production support."
    )
    assert "JAVA" in skills
    assert "API_DEVELOPMENT" not in skills
    assert "INTEGRATION_DEVELOPMENT" not in skills


def test_v2_catalog_remains_unchanged_by_v3_additions() -> None:
    description = "Build APIs with cloud, CI/CD, observability, retries and idempotency."
    v2 = classify(description)
    v3 = classify_v3(description)
    assert not v2 & {
        "API_DEVELOPMENT",
        "CLOUD_GENERIC",
        "CI_CD_GENERIC",
        "OBSERVABILITY_GENERIC",
        "RETRIES",
        "IDEMPOTENCY",
    }
    assert v3 > v2
