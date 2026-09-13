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


def test_rule_version_is_v2() -> None:
    assert service.RULE_VERSION == "OCCUPATION_V2"


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
