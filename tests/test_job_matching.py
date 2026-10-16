import pytest

from chamba_hunter.repositories.job_matching_repository import MatchingCandidateRow
from chamba_hunter.services import job_matching_service as service


STRONG_SKILLS = (
    "JAVA",
    "SPRING_BOOT",
    "REST",
    "DISTRIBUTED_SYSTEMS",
    "POSTGRESQL",
    "AWS",
    "KUBERNETES",
    "GITHUB_ACTIONS",
)
V4_STRONG_DESCRIPTION = (
    "Build Java Spring Boot REST APIs and distributed systems with PostgreSQL, "
    "AWS, Kubernetes and GitHub Actions."
)


def candidate(
    *,
    title: str = "Senior Java Backend Engineer",
    description: str = "",
    occupation: str = "SOFTWARE_ENGINEERING",
    backend: str = "BACKEND",
    seniority: str = "SENIOR",
    leadership: str = "NONE",
    skills: tuple[str, ...] = STRONG_SKILLS,
) -> MatchingCandidateRow:
    return MatchingCandidateRow(
        record_kind="ATS",
        record_id=1,
        source_type="ATS",
        origin="GREENHOUSE",
        company_name="Example",
        title=title,
        eligibility_status="ELIGIBLE",
        occupation_class=occupation,
        backend_relevance=backend,
        seniority_class=seniority,
        leadership_class=leadership,
        skills=skills,
        description=description,
    )


def v3(item: MatchingCandidateRow) -> service.MatchDecision:
    return service._match(item, profile=service.SENIOR_BACKEND_SOFTWARE_V1)


def v4(item: MatchingCandidateRow) -> service.MatchDecision:
    enriched = service.candidate_with_profile_evidence(
        item,
        service.SSR_SENIOR_BACKEND_SOFTWARE_V1,
    )
    return service._match(enriched, profile=service.SSR_SENIOR_BACKEND_SOFTWARE_V1)


def test_profile_versions_and_floor_are_explicit() -> None:
    assert service.BACKEND_SOFTWARE_V1.rule_version == "MATCHING_V2"
    assert service.SENIOR_BACKEND_SOFTWARE_V1.rule_version == "MATCHING_V3"
    assert service.SSR_SENIOR_BACKEND_SOFTWARE_V1.rule_version == "MATCHING_V4"
    assert service.PROFESSIONAL_RELEVANCE_FLOOR == 50.0


def test_ssr_and_senior_are_joint_primary_targets() -> None:
    mid = v4(candidate(seniority="MID", description=V4_STRONG_DESCRIPTION))
    senior = v4(candidate(seniority="SENIOR", description=V4_STRONG_DESCRIPTION))
    assert mid.match_level == "VERY_HIGH"
    assert senior.match_level == "VERY_HIGH"
    assert senior.score - mid.score == 1.0


def test_stronger_ssr_can_outrank_less_compatible_senior() -> None:
    strong_mid = v4(candidate(seniority="MID", description=V4_STRONG_DESCRIPTION))
    weaker_senior = v4(
        candidate(
            seniority="SENIOR",
            skills=("JAVA",),
            description="Maintain Java backend application code.",
        )
    )
    assert strong_mid.score > weaker_senior.score


def test_v4_unknown_staff_and_lead_remain_viable() -> None:
    for seniority in ("UNKNOWN", "STAFF", "LEAD"):
        assert v4(candidate(seniority=seniority, description=V4_STRONG_DESCRIPTION)).score >= 65


def test_v4_recomputes_full_skills_v3_instead_of_using_persisted_tuple() -> None:
    item = candidate(
        skills=(),
        description=(
            "Build Java Spring Boot REST APIs and distributed systems with "
            "idempotency, retries, cloud CI/CD and observability."
        ),
    )
    enriched = service.candidate_with_profile_evidence(
        item,
        service.SSR_SENIOR_BACKEND_SOFTWARE_V1,
    )
    assert {"JAVA", "SPRING_BOOT", "REST", "DISTRIBUTED_SYSTEMS", "IDEMPOTENCY"} <= set(enriched.skills)
    decision = service._match(enriched, profile=service.SSR_SENIOR_BACKEND_SOFTWARE_V1)
    assert decision.reasons["skill_evidence_version"] == "SKILLS_V3_IN_MEMORY"


def test_new_profile_apply_is_explicitly_disabled() -> None:
    matching = service.JobMatchingService(
        repository=None,  # type: ignore[arg-type]
        tracing_repository=None,  # type: ignore[arg-type]
        profile=service.SENIOR_BACKEND_SOFTWARE_V1,
    )
    with pytest.raises(ValueError, match="evaluation-only"):
        matching.run(apply=True)


def test_senior_backend_ranks_above_equivalent_mid() -> None:
    senior = v3(candidate(seniority="SENIOR"))
    mid = v3(candidate(seniority="MID"))
    assert senior.score > mid.score
    assert mid.score >= service.PROFESSIONAL_RELEVANCE_FLOOR


def test_unknown_seniority_remains_viable() -> None:
    assert v3(candidate(seniority="UNKNOWN")).score >= 65


@pytest.mark.parametrize("seniority", ["STAFF", "LEAD"])
def test_hands_on_staff_and_lead_can_reach_high(seniority: str) -> None:
    decision = v3(candidate(seniority=seniority, leadership="NONE"))
    assert decision.match_level in {"HIGH", "VERY_HIGH"}
    assert decision.score_ceiling == 100.0


@pytest.mark.parametrize("seniority", ["STAFF", "LEAD"])
def test_staff_and_lead_title_alone_do_not_create_very_high(seniority: str) -> None:
    decision = v3(candidate(seniority=seniority, skills=()))
    assert decision.match_level in {"MEDIUM", "HIGH"}
    assert decision.match_level != "VERY_HIGH"


def test_lead_seniority_is_not_people_management() -> None:
    decision = v3(candidate(seniority="LEAD", leadership="NONE"))
    assert decision.leadership_score == 10.0
    assert not any(reason.startswith("leadership:") for reason in decision.reasons["ceiling_reasons"])


@pytest.mark.parametrize(
    ("title", "leadership", "maximum"),
    [
        ("Engineering Manager", "MANAGER", 60.0),
        ("Director of Engineering", "DIRECTOR", 55.0),
        ("Head of Engineering", "HEAD", 50.0),
    ],
)
def test_people_management_remains_capped(title: str, leadership: str, maximum: float) -> None:
    decision = v3(candidate(title=title, leadership=leadership))
    assert decision.score <= maximum
    assert decision.match_level != "HIGH"


def test_principal_backend_can_reach_high_but_not_very_high() -> None:
    decision = v3(candidate(seniority="PRINCIPAL"))
    assert decision.match_level == "HIGH"
    assert decision.score_ceiling == 79.0


HANDS_ON_ARCHITECT = (
    "Build backend services in Java and Spring Boot. "
    "Design distributed systems, microservices, and REST APIs. "
    "Own end-to-end software delivery and deploy services to production."
)


def test_hands_on_backend_architect_can_reach_high() -> None:
    decision = v3(candidate(title="Java Application Architect", description=HANDS_ON_ARCHITECT))
    responsibility = decision.reasons["components"]["role_responsibility"]
    assert responsibility["hands_on"] is True
    assert decision.match_level == "HIGH"
    assert decision.score_ceiling == 79.0


def test_hands_on_solutions_architect_can_be_rescored_from_tech_adjacent() -> None:
    decision = v3(
        candidate(
            title="Solutions Architect",
            description=HANDS_ON_ARCHITECT,
            occupation="TECH_ADJACENT",
            backend="NOT_APPLICABLE",
        )
    )
    assert decision.role_score == 35.0
    assert decision.match_level == "HIGH"


@pytest.mark.parametrize("domain_skill", ["IAM_DOMAIN", "PAYMENTS_DOMAIN"])
def test_domain_context_never_establishes_backend_fit(domain_skill: str) -> None:
    decision = v3(
        candidate(
            title="Consultant",
            occupation="TECH_ADJACENT",
            backend="NOT_APPLICABLE",
            skills=(domain_skill,),
            seniority="UNKNOWN",
        )
    )
    assert decision.skills_score == 0.0
    assert decision.match_level == "LOW"


@pytest.mark.parametrize(
    ("title", "description", "occupation"),
    [
        ("Enterprise Architect", "Define enterprise architecture governance, standards and roadmaps.", "TECH_ADJACENT"),
        ("Cloud Architect", "Own landing zones, Terraform modules, networking and cloud administration.", "IT_TECHNICAL"),
        ("Solutions Architect", "Lead presales RFPs, customer demos and commercial proposals.", "TECH_ADJACENT"),
        ("Security Architect", "Security compliance, audit controls and vulnerability management. Java awareness is useful.", "TECH_ADJACENT"),
    ],
)
def test_non_implementation_architects_do_not_reach_high(
    title: str, description: str, occupation: str
) -> None:
    decision = v3(candidate(title=title, description=description, occupation=occupation, backend="UNKNOWN", skills=("JAVA",)))
    assert decision.match_level != "HIGH"
    assert decision.reasons["components"]["role_responsibility"]["hands_on"] is False


def test_unrelated_it_operations_do_not_become_strong_match() -> None:
    decision = v3(
        candidate(
            title="Cloud Operations Engineer",
            description="Operate Kubernetes clusters, Terraform and production support rotations.",
            occupation="IT_TECHNICAL",
            backend="NOT_APPLICABLE",
            skills=("KUBERNETES", "TERRAFORM", "CLOUD_GENERIC", "OBSERVABILITY_GENERIC"),
            seniority="UNKNOWN",
        )
    )
    assert decision.match_level == "LOW"


def test_legacy_profile_keeps_known_v2_scores_ceilings_and_explanation_shape() -> None:
    item = candidate(skills=("JAVA", "SPRING_BOOT", "REST"))
    decision = service._match(item)
    assert decision.score == 78.0
    assert decision.match_level == "HIGH"
    assert decision.role_score == 45.0
    assert decision.skills_score == 13.0
    assert decision.seniority_score == 10.0
    assert decision.leadership_score == 10.0
    assert decision.score_ceiling == 100.0
    assert decision.reasons["profile_name"] == "BACKEND_SOFTWARE_V1"
    assert decision.reasons["rule_version"] == "MATCHING_V2"
    assert "role_responsibility" not in decision.reasons["components"]

    staff = service._match(candidate(seniority="STAFF"))
    architect = service._match(candidate(title="Backend Architect", description=HANDS_ON_ARCHITECT))
    assert staff.score_ceiling == 64.0
    assert architect.score_ceiling == 64.0
