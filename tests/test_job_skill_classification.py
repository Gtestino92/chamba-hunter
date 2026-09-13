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
        )
    )

    return {
        decision.skill_key
        for decision in decisions
    }


def test_rule_version_is_v2() -> None:
    assert service.RULE_VERSION == "SKILLS_V2"


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
