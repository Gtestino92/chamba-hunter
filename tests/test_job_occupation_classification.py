import pytest

from chamba_hunter.repositories.job_occupation_repository import (
    OccupationCandidateRow,
)
from chamba_hunter.services import (
    job_occupation_classification_service as service,
)


def classify(
    title: str,
    description: str,
) -> tuple[str, str]:
    decision = service._classify(
        OccupationCandidateRow(
            record_kind="ATS",
            record_id=1,
            source_type="ATS",
            origin="SUCCESSFACTORS",
            company_name="Example",
            eligibility_status="UNKNOWN",
            title=title,
            description=description,
        )
    )

    return (
        decision.occupation_class,
        decision.backend_relevance,
    )


def test_rule_version_is_v3() -> None:
    assert service.RULE_VERSION == "OCCUPATION_V3"


REAL_WORLD_IDENTITY_BACKEND_DESCRIPTION = (
    "Write Java application code and build large-scale distributed "
    "systems. Build backend authentication and authorization "
    "services and REST APIs with Spring Boot and microservices. "
    "Design for scalability and reliability using AWS, Azure, "
    "Docker, Kubernetes, EKS, CI/CD, and observability. OAuth, "
    "OIDC, and SAML are domain-specific bonuses."
)


@pytest.mark.parametrize(
    "title",
    [
        "Cloud Java Software Engineer",
        "IAM Engineer",
        "Identity Management Consultant",
    ],
)
def test_real_world_identity_backend_title_variants_are_equivalent(
    title: str,
) -> None:
    assert classify(
        title,
        REAL_WORLD_IDENTITY_BACKEND_DESCRIPTION,
    ) == (
        "SOFTWARE_ENGINEERING",
        "BACKEND",
    )


@pytest.mark.parametrize(
    (
        "title",
        "description",
    ),
    [
        (
            "Platform Engineer",
            (
                "Develop Kotlin and Spring Boot backend services. "
                "Design REST APIs and microservices for the "
                "application platform."
            ),
        ),
        (
            "Cloud Engineer",
            (
                "Build Java application code for distributed "
                "systems and backend services running in AWS."
            ),
        ),
        (
            "Security Engineer",
            (
                "Develop Kotlin authorization services using an "
                "event-driven architecture and Spring Boot."
            ),
        ),
        (
            "Integration Engineer",
            (
                "Implement Java REST APIs and microservices for "
                "application-to-application integrations."
            ),
        ),
        (
            "Application Engineer",
            (
                "Write Java application code and build backend "
                "services exposed through REST APIs."
            ),
        ),
    ],
)
def test_ambiguous_titles_are_rescued_by_orthogonal_backend_evidence(
    title: str,
    description: str,
) -> None:
    assert classify(
        title,
        description,
    ) == (
        "SOFTWARE_ENGINEERING",
        "BACKEND",
    )


@pytest.mark.parametrize(
    (
        "title",
        "description",
    ),
    [
        (
            "IAM Engineer",
            (
                "Own IAM account provisioning, access reviews, "
                "identity lifecycle governance, and SailPoint "
                "administration. Review Java application access."
            ),
        ),
        (
            "IAM Engineer",
            (
                "Develop Java REST API integration services for "
                "SailPoint. Own provisioning policies, approval "
                "processes, and access reviews."
            ),
        ),
        (
            "Identity Management Consultant",
            (
                "Configure and administer Okta and Azure AD. "
                "Maintain SAML policies, IAM access reviews, and "
                "joiner mover leaver workflows."
            ),
        ),
        (
            "Platform Engineer",
            (
                "Operate Kubernetes clusters, provision Terraform "
                "infrastructure, and manage cloud landing zones."
            ),
        ),
        (
            "Cloud Engineer",
            (
                "Manage cloud infrastructure, networking, landing "
                "zones, and Kubernetes operations."
            ),
        ),
        (
            "Security Engineer",
            (
                "Work in the security operations center on SIEM, "
                "vulnerability management, and incident response."
            ),
        ),
        (
            "Application Engineer",
            (
                "Provide production support, resolve support "
                "tickets, and monitor application availability."
            ),
        ),
        (
            "Integration Engineer",
            (
                "Configure MuleSoft and SAP Integration Suite. "
                "Administer integration platform connections."
            ),
        ),
        (
            "Platform Engineer",
            (
                "Coordinate vendor documentation. Java appears in "
                "one unrelated product brochure."
            ),
        ),
        (
            "Senior Staff Machine Learning Platform Engineer",
            (
                "Build Kotlin distributed systems and event-driven "
                "services for model training infrastructure."
            ),
        ),
    ],
)
def test_operational_and_administration_roles_are_not_rescued(
    title: str,
    description: str,
) -> None:
    occupation_class, backend_relevance = classify(
        title,
        description,
    )

    assert occupation_class != "SOFTWARE_ENGINEERING"
    assert backend_relevance == "NOT_APPLICABLE"


@pytest.mark.parametrize(
    (
        "title",
        "description",
        "expected",
    ),
    [
        (
            "Analista Técnico",
            (
                "Responsable por desarrollo de aplicaciones, "
                "programación en Java con Spring Boot, APIs REST "
                "y microservicios."
            ),
            (
                "SOFTWARE_ENGINEERING",
                "BACKEND",
            ),
        ),
        (
            "Desarrollador Java",
            "Participa en proyectos del equipo técnico.",
            (
                "SOFTWARE_ENGINEERING",
                "UNKNOWN",
            ),
        ),
        (
            "Administrador Cloud",
            (
                "Administrar plataforma Cloud, infraestructura "
                "cloud, gestión de incidentes y contenedores."
            ),
            (
                "IT_TECHNICAL",
                "NOT_APPLICABLE",
            ),
        ),
        (
            "Ingeniero de Red de Acceso",
            (
                "Coordina despliegue de red, infraestructura de "
                "red y proyectos de telecomunicaciones."
            ),
            (
                "IT_TECHNICAL",
                "NOT_APPLICABLE",
            ),
        ),
        (
            "Ingeniero/a Soporte Corporativo Infraestructura de Red",
            (
                "Gestiona mantenimiento de nodos, infraestructura "
                "de red y reportes de equipamiento crítico."
            ),
            (
                "IT_TECHNICAL",
                "NOT_APPLICABLE",
            ),
        ),
        (
            "Analista QA Automatización",
            (
                "Define pruebas automatizadas, testing de APIs "
                "y calidad de software."
            ),
            (
                "IT_TECHNICAL",
                "NOT_APPLICABLE",
            ),
        ),
        (
            "Analista de Datos",
            (
                "Realiza extracción y consolidación de datos, SQL, "
                "Power BI y modelos predictivos."
            ),
            (
                "IT_TECHNICAL",
                "NOT_APPLICABLE",
            ),
        ),
        (
            "Analista Funcional CRM Salesforce",
            (
                "Releva requerimientos funcionales, actúa como "
                "nexo entre áreas usuarias y equipos técnicos, "
                "prioriza backlog y define criterios de aceptación."
            ),
            (
                "TECH_ADJACENT",
                "NOT_APPLICABLE",
            ),
        ),
        (
            "Analista PO Proxy",
            (
                "Transforma necesidades de negocio en historias "
                "de usuario, define requerimientos no funcionales "
                "y articula con el Tech Lead."
            ),
            (
                "TECH_ADJACENT",
                "NOT_APPLICABLE",
            ),
        ),
        (
            "Ejecutivo de Soluciones Digitales",
            (
                "Impulsa venta consultiva de Cloud, Java, "
                "Desarrollo de Software, ERP y CRM; identifica "
                "oportunidades de negocio y objetivos comerciales."
            ),
            (
                "NON_TECHNICAL",
                "NOT_APPLICABLE",
            ),
        ),
        (
            "Asesor Comercial",
            "Asesoramiento comercial y oportunidades de venta.",
            (
                "NON_TECHNICAL",
                "NOT_APPLICABLE",
            ),
        ),
        (
            "Asesor de Ventas",
            "Atención integral a clientes y venta de servicios.",
            (
                "NON_TECHNICAL",
                "NOT_APPLICABLE",
            ),
        ),
        (
            "Referente Técnico",
            (
                "Coordina documentación interna y reuniones con "
                "proveedores sin evidencia suficiente del rol."
            ),
            (
                "UNKNOWN",
                "NOT_APPLICABLE",
            ),
        ),
        (
            "Referente Técnico",
            (
                "Experiencia mayor a 3 años como desarrollador. "
                "Responsable de desarrollo de aplicaciones, "
                "servicios backend, APIs REST y microservicios."
            ),
            (
                "SOFTWARE_ENGINEERING",
                "BACKEND",
            ),
        ),
    ],
)
def test_spanish_occupation_v2_cases(
    title: str,
    description: str,
    expected: tuple[str, str],
) -> None:
    assert classify(
        title,
        description,
    ) == expected


@pytest.mark.parametrize(
    (
        "title",
        "description",
        "expected",
    ),
    [
        (
            "Backend Software Engineer",
            "Build server side services.",
            (
                "SOFTWARE_ENGINEERING",
                "BACKEND",
            ),
        ),
        (
            "Frontend Engineer",
            "Build React components and web UI.",
            (
                "SOFTWARE_ENGINEERING",
                "NON_BACKEND",
            ),
        ),
        (
            "Mobile Developer",
            "Build Android and iOS applications.",
            (
                "SOFTWARE_ENGINEERING",
                "NON_BACKEND",
            ),
        ),
        (
            "Cloud Support Engineer",
            "Provide technical support for cloud infrastructure.",
            (
                "IT_TECHNICAL",
                "NOT_APPLICABLE",
            ),
        ),
        (
            "Technical Product Manager",
            "Own product roadmap and technical requirements.",
            (
                "TECH_ADJACENT",
                "NOT_APPLICABLE",
            ),
        ),
        (
            "Sales Executive",
            "Manage sales pipeline and business development.",
            (
                "NON_TECHNICAL",
                "NOT_APPLICABLE",
            ),
        ),
    ],
)
def test_existing_english_cases_stay_stable(
    title: str,
    description: str,
    expected: tuple[str, str],
) -> None:
    assert classify(
        title,
        description,
    ) == expected


def test_one_technology_word_does_not_make_software() -> None:
    assert classify(
        "Technical Analyst",
        (
            "Coordinates vendor documentation. Java appears in "
            "one unrelated product brochure."
        ),
    ) == (
        "UNKNOWN",
        "NOT_APPLICABLE",
    )


def test_commercial_technology_catalog_stays_non_technical() -> None:
    assert classify(
        "Analista de Soluciones Digitales",
        (
            "Impulsa venta consultiva de soluciones Cloud, Java, "
            "Desarrollo de Software, ERP, CRM e integraciones. "
            "Debe identificar oportunidades de negocio, gestionar "
            "el ciclo comercial y alcanzar objetivos comerciales."
        ),
    ) == (
        "NON_TECHNICAL",
        "NOT_APPLICABLE",
    )
