from collections import Counter
from dataclasses import dataclass, field
import re

from chamba_hunter.domain.common import (
    JsonObject,
    utc_now,
)
from chamba_hunter.domain.enums import RunStatus
from chamba_hunter.domain.tracing import Run, RunStep
from chamba_hunter.repositories.job_matching_repository import (
    JobMatchingRepository,
    MatchingCandidateRow,
    ProfessionalMatchWrite,
)
from chamba_hunter.repositories.tracing_repository import (
    TracingRepository,
)


RULE_VERSION = "MATCHING_V2"
PROFESSIONAL_RELEVANCE_FLOOR = 50.0
PROFILE_NAME = "BACKEND_SOFTWARE_V1"
PROFILE_DESCRIPTION = (
    "Backend Software Engineer search profile calibrated "
    "for the current Chamba Hunter search."
)


@dataclass(frozen=True, slots=True)
class SkillSignal:
    skill_key: str
    relation: str
    points: float


@dataclass(frozen=True, slots=True)
class SkillGroup:
    name: str
    max_points: float
    signals: tuple[SkillSignal, ...]


@dataclass(frozen=True, slots=True)
class MatchDecision:
    record_kind: str
    record_id: int

    source_type: str
    origin: str

    company_name: str
    title: str

    occupation_class: str
    backend_relevance: str
    seniority_class: str
    leadership_class: str

    score: float
    match_level: str

    role_score: float
    skills_score: float
    seniority_score: float
    leadership_score: float
    technology_penalty: float
    score_ceiling: float

    reasons: JsonObject


@dataclass(slots=True)
class MatchingSummary:
    apply: bool

    total: int = 0
    relevant: int = 0

    created: int = 0
    updated: int = 0
    deleted: int = 0

    run_id: int | None = None
    search_profile_id: int | None = None

    decisions: list[
        MatchDecision
    ] = field(default_factory=list)


SKILL_GROUPS: tuple[SkillGroup, ...] = (
    SkillGroup(
        name="CORE_JVM",
        max_points=7.0,
        signals=(
            SkillSignal("JAVA", "EXACT", 5.0),
            SkillSignal("KOTLIN", "EXACT", 4.0),
        ),
    ),
    SkillGroup(
        name="SPRING_JVM_FRAMEWORK",
        max_points=6.0,
        signals=(
            SkillSignal(
                "SPRING_BOOT",
                "EXACT",
                6.0,
            ),
            SkillSignal(
                "SPRING",
                "EXACT",
                3.0,
            ),
            SkillSignal(
                "JPA",
                "EXACT",
                1.5,
            ),
            SkillSignal(
                "HIBERNATE",
                "RELATED",
                1.0,
            ),
            SkillSignal(
                "SPRING_DATA",
                "RELATED",
                0.75,
            ),
            SkillSignal(
                "SPRING_SECURITY",
                "RELATED",
                0.75,
            ),
            SkillSignal(
                "SPRING_CLOUD",
                "RELATED",
                0.75,
            ),
            SkillSignal(
                "QUARKUS",
                "PEER",
                2.0,
            ),
            SkillSignal(
                "MICRONAUT",
                "PEER",
                2.0,
            ),
            SkillSignal(
                "KTOR",
                "PEER",
                2.0,
            ),
        ),
    ),
    SkillGroup(
        name="ARCHITECTURE_API",
        max_points=4.0,
        signals=(
            SkillSignal(
                "DISTRIBUTED_SYSTEMS",
                "EXACT",
                3.0,
            ),
            SkillSignal(
                "REST",
                "EXACT",
                2.0,
            ),
            SkillSignal(
                "MICROSERVICES",
                "RELATED",
                1.5,
            ),
            SkillSignal(
                "EVENT_DRIVEN",
                "RELATED",
                1.0,
            ),
            SkillSignal(
                "DDD",
                "RELATED",
                0.5,
            ),
            SkillSignal(
                "CQRS",
                "RELATED",
                0.5,
            ),
            SkillSignal(
                "EVENT_SOURCING",
                "RELATED",
                0.5,
            ),
            SkillSignal(
                "SAGA",
                "RELATED",
                0.5,
            ),
        ),
    ),
    SkillGroup(
        name="DATA",
        max_points=3.5,
        signals=(
            SkillSignal(
                "POSTGRESQL",
                "EXACT",
                3.5,
            ),
            SkillSignal(
                "MONGODB",
                "EXACT",
                2.0,
            ),
            SkillSignal(
                "ORACLE_DB",
                "EXACT",
                2.0,
            ),
            SkillSignal(
                "MYSQL",
                "PEER",
                1.25,
            ),
            SkillSignal(
                "SQL_SERVER",
                "PEER",
                1.25,
            ),
            SkillSignal(
                "MARIADB",
                "PEER",
                1.25,
            ),
            SkillSignal(
                "PERCONA",
                "PEER",
                1.25,
            ),
        ),
    ),
    SkillGroup(
        name="CLOUD",
        max_points=3.0,
        signals=(
            SkillSignal(
                "AWS",
                "EXACT",
                3.0,
            ),
            SkillSignal(
                "EC2",
                "EXACT",
                0.75,
            ),
            SkillSignal(
                "RDS",
                "EXACT",
                0.75,
            ),
            SkillSignal(
                "S3",
                "EXACT",
                0.75,
            ),
            SkillSignal(
                "AZURE",
                "PEER",
                2.0,
            ),
            SkillSignal(
                "GCP",
                "PEER",
                2.0,
            ),
        ),
    ),
    SkillGroup(
        name="CONTAINERS_PLATFORM",
        max_points=2.5,
        signals=(
            SkillSignal(
                "KUBERNETES",
                "EXACT",
                2.0,
            ),
            SkillSignal(
                "DOCKER",
                "EXACT",
                1.25,
            ),
            SkillSignal(
                "OPENSHIFT",
                "EXACT",
                1.0,
            ),
            SkillSignal(
                "HELM",
                "RELATED",
                0.4,
            ),
            SkillSignal(
                "TERRAFORM",
                "RELATED",
                0.4,
            ),
            SkillSignal(
                "CLOUDFORMATION",
                "RELATED",
                0.4,
            ),
            SkillSignal(
                "PULUMI",
                "RELATED",
                0.4,
            ),
        ),
    ),
    SkillGroup(
        name="DELIVERY",
        max_points=1.5,
        signals=(
            SkillSignal(
                "GITHUB_ACTIONS",
                "EXACT",
                1.0,
            ),
            SkillSignal(
                "GITLAB_CI",
                "EXACT",
                1.0,
            ),
            SkillSignal(
                "JENKINS",
                "PEER",
                0.75,
            ),
            SkillSignal(
                "AZURE_DEVOPS",
                "PEER",
                0.75,
            ),
            SkillSignal(
                "AZURE_PIPELINES",
                "PEER",
                0.75,
            ),
        ),
    ),
    SkillGroup(
        name="SECONDARY_STACK",
        max_points=2.5,
        signals=(
            SkillSignal(
                "TYPESCRIPT",
                "SECONDARY",
                0.75,
            ),
            SkillSignal(
                "NODEJS",
                "SECONDARY",
                1.0,
            ),
            SkillSignal(
                "NESTJS",
                "SECONDARY",
                1.25,
            ),
            SkillSignal(
                "ANDROID",
                "SECONDARY",
                0.25,
            ),
            SkillSignal(
                "JETPACK_COMPOSE",
                "SECONDARY",
                0.25,
            ),
        ),
    ),
)


ALTERNATE_BACKEND_FAMILIES = {
    "PYTHON": {
        "PYTHON",
        "DJANGO",
        "FLASK",
        "FASTAPI",
    },
    "GO": {
        "GO",
    },
    "DOTNET": {
        "CSHARP",
        "DOTNET",
        "ASP_NET",
    },
    "ELIXIR": {
        "ELIXIR",
        "ERLANG",
        "PHOENIX",
    },
    "RUBY": {
        "RUBY",
        "RAILS",
    },
    "PHP": {
        "PHP",
        "LARAVEL",
    },
    "RUST": {
        "RUST",
    },
    "SCALA": {
        "SCALA",
    },
}


COMPATIBLE_CORE_SKILLS = {
    "JAVA",
    "KOTLIN",
    "SPRING_BOOT",
    "SPRING",
    "QUARKUS",
    "MICRONAUT",
    "KTOR",
    "NODEJS",
    "NESTJS",
    "TYPESCRIPT",
}


STRONG_BACKEND_JVM_LANGUAGES = {
    "JAVA",
    "KOTLIN",
}


STRONG_BACKEND_JVM_FRAMEWORKS = {
    "SPRING_BOOT",
    "SPRING",
    "JPA",
    "HIBERNATE",
    "QUARKUS",
    "MICRONAUT",
    "KTOR",
}


STRONG_BACKEND_NODE_LANGUAGES = {
    "NODEJS",
    "TYPESCRIPT",
}


STRONG_BACKEND_NODE_FRAMEWORKS = {
    "NESTJS",
}


ROLE_SCORES = {
    (
        "SOFTWARE_ENGINEERING",
        "BACKEND",
    ): 45.0,
    (
        "SOFTWARE_ENGINEERING",
        "FULL_STACK",
    ): 38.0,
    (
        "SOFTWARE_ENGINEERING",
        "UNKNOWN",
    ): 25.0,
    (
        "SOFTWARE_ENGINEERING",
        "NON_BACKEND",
    ): 8.0,
}


SENIORITY_SCORES = {
    "MID": 15.0,
    "UNKNOWN": 12.0,
    "SENIOR": 10.0,
    "JUNIOR": 8.0,
    "ENTRY": 5.0,
    "LEAD": 5.0,
    "STAFF": 4.0,
    "PRINCIPAL": 2.0,
    "INTERN": 1.0,
}


LEADERSHIP_SCORES = {
    "NONE": 10.0,
    "UNKNOWN": 8.0,
    "MANAGER": 2.0,
    "DIRECTOR": 1.0,
    "HEAD": 0.0,
    "VP": 0.0,
    "C_LEVEL": 0.0,
}


OCCUPATION_SCORE_CEILINGS = {
    "NON_TECHNICAL": 40.0,
    "TECH_ADJACENT": 50.0,
    "IT_TECHNICAL": 60.0,
    "UNKNOWN": 70.0,
}


LEADERSHIP_SCORE_CEILINGS = {
    "MANAGER": 60.0,
    "DIRECTOR": 55.0,
    "HEAD": 50.0,
    "VP": 45.0,
    "C_LEVEL": 45.0,
}


SENIORITY_SCORE_CEILINGS = {
    "INTERN": 45.0,
    "ENTRY": 55.0,
    "JUNIOR": 64.0,
    "STAFF": 64.0,
    "PRINCIPAL": 60.0,
    "LEAD": 64.0,
}


ROLE_TITLE_MISMATCH_PATTERNS: tuple[
    tuple[str, re.Pattern[str]],
    ...,
] = (
    (
        "EDUCATION_ROLE",
        re.compile(
            r"\b(?:tutor(?:a)?|instructor(?:a)?|teacher|professor|docente|trainer)\b",
            re.I,
        ),
    ),
)


TITLE_SENIORITY_RISK_PATTERNS: tuple[
    tuple[str, re.Pattern[str], float],
    ...,
] = (
    (
        "ARCHITECT",
        re.compile(
            r"\b(?:architect|arquitecto|arquitecta)\b",
            re.I,
        ),
        64.0,
    ),
)


TITLE_COMPATIBLE_CORE_PATTERN = re.compile(
    r"""
    (?:
        \bjava\b
        |\bkotlin\b
        |\bspring(?:\s+boot)?\b
        |\bnode\.?\s*js\b
        |\bnodejs\b
        |\bnest\.?\s*js\b
        |\bnestjs\b
        |\btypescript\b
    )
    """,
    re.I | re.X,
)


TITLE_ALTERNATE_STACK_PATTERNS: tuple[
    tuple[str, re.Pattern[str]],
    ...,
] = (
    (
        "PYTHON",
        re.compile(
            r"\bpython\b",
            re.I,
        ),
    ),
    (
        "GO",
        re.compile(
            r"\bgolang\b|\bgo\b(?![-\s]+to[-\s]+market)",
            re.I,
        ),
    ),
    (
        "DOTNET",
        re.compile(
            r"(?<!\w)c#(?!\w)|(?<!\w)\.net(?:\s+core)?(?!\w)|\bdotnet\b",
            re.I,
        ),
    ),
    (
        "ELIXIR",
        re.compile(
            r"\belixir\b|\bphoenix\b",
            re.I,
        ),
    ),
    (
        "RUBY",
        re.compile(
            r"\bruby\b|\brails\b",
            re.I,
        ),
    ),
    (
        "PHP",
        re.compile(
            r"\bphp\b|\blaravel\b",
            re.I,
        ),
    ),
    (
        "RUST",
        re.compile(
            r"\brust\b",
            re.I,
        ),
    ),
    (
        "SCALA",
        re.compile(
            r"\bscala\b",
            re.I,
        ),
    ),
)


def _has_strong_backend_core(
    skills: set[str],
) -> bool:
    strong_jvm = bool(
        skills
        & STRONG_BACKEND_JVM_LANGUAGES
    ) and bool(
        skills
        & STRONG_BACKEND_JVM_FRAMEWORKS
    )

    strong_node = bool(
        skills
        & STRONG_BACKEND_NODE_LANGUAGES
    ) and bool(
        skills
        & STRONG_BACKEND_NODE_FRAMEWORKS
    )

    return (
        strong_jvm
        or strong_node
    )


def _title_seniority_risks(
    title: str,
) -> list[
    tuple[str, float]
]:
    return [
        (
            key,
            ceiling,
        )
        for key, pattern, ceiling
        in TITLE_SENIORITY_RISK_PATTERNS
        if pattern.search(
            title
        )
    ]


def _title_role_mismatches(
    title: str,
) -> list[str]:
    return [
        key
        for key, pattern
        in ROLE_TITLE_MISMATCH_PATTERNS
        if pattern.search(title)
    ]


def _title_alternate_families(
    title: str,
) -> list[str]:
    return [
        family
        for family, pattern
        in TITLE_ALTERNATE_STACK_PATTERNS
        if pattern.search(title)
    ]


def _title_has_compatible_core(
    title: str,
) -> bool:
    return bool(
        TITLE_COMPATIBLE_CORE_PATTERN.search(
            title
        )
    )


def profile_rules() -> JsonObject:
    return {
        "profile_name": PROFILE_NAME,
        "rule_version": RULE_VERSION,
        "score_components": {
            "role_max": 45,
            "skills_max": 30,
            "seniority_max": 15,
            "leadership_max": 10,
            "technology_penalty_min": -5,
        },
        "match_levels": {
            "VERY_HIGH": 80,
            "HIGH": 65,
            "MEDIUM": 45,
            "LOW": 0,
        },
        "professional_relevance_floor": (
            PROFESSIONAL_RELEVANCE_FLOOR
        ),
        "seniority_target": (
            "semisenior / mid-level"
        ),
        "skill_relations": [
            "EXACT",
            "PEER",
            "RELATED",
            "SECONDARY",
        ],
        "principles": [
            "occupation/backend dominates",
            "missing skill evidence is not a rejection",
            "peer technology is partial transfer, not equality",
            "explicit alternate backend stack is a mild penalty and title-level ceiling",
            "clear non-engineering title-role mismatch cannot rank as a strong backend match",
            "junior remains viable but cannot rank HIGH for the mid-level target",
            "architect titles remain visible but cannot rank HIGH for the mid-level target",
            "software backend UNKNOWN may receive a role boost only from strong profile-specific backend evidence",
            "UNKNOWN remains viable",
            "professional score excludes freshness and application priority",
            "only scores at or above the professional relevance floor are persisted as current professional matches",
        ],
        "skill_groups": [
            {
                "name": group.name,
                "max_points": group.max_points,
                "signals": [
                    {
                        "skill_key": signal.skill_key,
                        "relation": signal.relation,
                        "points": signal.points,
                    }
                    for signal in group.signals
                ],
            }
            for group in SKILL_GROUPS
        ],
    }


class JobMatchingService:
    def __init__(
        self,
        repository: JobMatchingRepository,
        tracing_repository: TracingRepository,
    ) -> None:
        self.repository = repository
        self.tracing_repository = tracing_repository

    def run(
        self,
        apply: bool = False,
    ) -> MatchingSummary:
        candidates = (
            self.repository.list_scoped_candidates()
        )

        summary = MatchingSummary(
            apply=apply,
            total=len(candidates),
        )

        summary.decisions = [
            _match(candidate)
            for candidate in candidates
        ]

        summary.relevant = sum(
            1
            for decision in summary.decisions
            if (
                decision.score
                >= PROFESSIONAL_RELEVANCE_FLOOR
            )
        )

        if apply:
            self._apply(summary)

        return summary

    def _apply(
        self,
        summary: MatchingSummary,
    ) -> None:
        now = utc_now()

        search_profile_id = (
            self.repository.upsert_search_profile(
                name=PROFILE_NAME,
                description=PROFILE_DESCRIPTION,
                rules=profile_rules(),
                now=now,
            )
        )

        summary.search_profile_id = (
            search_profile_id
        )

        run = self.tracing_repository.add_run(
            Run(
                command="match_jobs"
            )
        )

        if run.id is None:
            raise RuntimeError(
                "Professional matching run must have an id."
            )

        summary.run_id = run.id

        step = self.tracing_repository.add_run_step(
            RunStep(
                run_id=run.id,
                step_name="professional_matching",
                items_total=summary.total,
            )
        )

        if step.id is None:
            raise RuntimeError(
                "Professional matching run step "
                "must have an id."
            )

        try:
            relevant_decisions = [
                decision
                for decision in summary.decisions
                if (
                    decision.score
                    >= PROFESSIONAL_RELEVANCE_FLOOR
                )
            ]

            writes = [
                ProfessionalMatchWrite(
                    record_kind=decision.record_kind,
                    record_id=decision.record_id,
                    score=decision.score,
                    match_level=decision.match_level,
                    role_score=decision.role_score,
                    skills_score=decision.skills_score,
                    seniority_score=(
                        decision.seniority_score
                    ),
                    leadership_score=(
                        decision.leadership_score
                    ),
                    technology_penalty=(
                        decision.technology_penalty
                    ),
                    score_ceiling=(
                        decision.score_ceiling
                    ),
                    reasons=decision.reasons,
                    rule_version=RULE_VERSION,
                )
                for decision in relevant_decisions
            ]

            counts = self.repository.upsert_matches(
                search_profile_id=search_profile_id,
                matches=writes,
                matched_at=now,
            )

            summary.created = counts.created
            summary.updated = counts.updated
            summary.deleted = counts.deleted

            level_counts = Counter(
                decision.match_level
                for decision in summary.decisions
            )

            occupation_counts = Counter(
                decision.occupation_class
                for decision in summary.decisions
            )

            metadata = {
                "rule_version": RULE_VERSION,
                "search_profile": PROFILE_NAME,
                "search_profile_id": (
                    search_profile_id
                ),
                "scope": (
                    "ARGENTINA_ELIGIBLE_OR_UNKNOWN"
                ),
                "professional_relevance_floor": (
                    PROFESSIONAL_RELEVANCE_FLOOR
                ),
                "evaluated": summary.total,
                "relevant": summary.relevant,
                "excluded_below_floor": (
                    summary.total
                    - summary.relevant
                ),
                "match_levels": dict(
                    sorted(
                        level_counts.items()
                    )
                ),
                "occupations": dict(
                    sorted(
                        occupation_counts.items()
                    )
                ),
                "created": summary.created,
                "updated": summary.updated,
                "deleted": summary.deleted,
            }

            self.tracing_repository.finish_run_step(
                run_step_id=step.id,
                status=RunStatus.SUCCESS,
                items_success=summary.total,
                items_failed=0,
                items_skipped=0,
                metadata=metadata,
            )

            self.tracing_repository.finish_run(
                run_id=run.id,
                status=RunStatus.SUCCESS,
            )

        except Exception as error:
            self.tracing_repository.finish_run_step(
                run_step_id=step.id,
                status=RunStatus.FAILED,
                items_success=0,
                items_failed=1,
                items_skipped=summary.total,
                metadata={
                    "rule_version": RULE_VERSION,
                    "search_profile": PROFILE_NAME,
                    "professional_relevance_floor": (
                        PROFESSIONAL_RELEVANCE_FLOOR
                    ),
                },
                error_message=str(error),
            )

            self.tracing_repository.finish_run(
                run_id=run.id,
                status=RunStatus.FAILED,
            )

            raise


def _match(
    candidate: MatchingCandidateRow,
) -> MatchDecision:
    skills = set(
        candidate.skills
    )

    role_score, role_reason = (
        _role_score(candidate)
    )

    (
        skills_score,
        skill_reasons,
    ) = _skills_score(
        skills
    )

    seniority_score = SENIORITY_SCORES.get(
        candidate.seniority_class,
        0.0,
    )

    leadership_score = (
        LEADERSHIP_SCORES.get(
            candidate.leadership_class,
            0.0,
        )
    )

    (
        technology_penalty,
        alternate_families,
    ) = _technology_penalty(
        candidate,
        skills,
    )

    raw_score = (
        role_score
        + skills_score
        + seniority_score
        + leadership_score
        + technology_penalty
    )

    score_ceiling, ceiling_reasons = (
        _score_ceiling(candidate)
    )

    score = round(
        max(
            0.0,
            min(
                raw_score,
                score_ceiling,
                100.0,
            ),
        ),
        2,
    )

    match_level = _match_level(
        score
    )

    exact = sorted(
        {
            item["skill_key"]
            for item in skill_reasons
            if item["relation"] == "EXACT"
        }
    )

    peer = sorted(
        {
            item["skill_key"]
            for item in skill_reasons
            if item["relation"] == "PEER"
        }
    )

    related = sorted(
        {
            item["skill_key"]
            for item in skill_reasons
            if item["relation"] == "RELATED"
        }
    )

    secondary = sorted(
        {
            item["skill_key"]
            for item in skill_reasons
            if item["relation"] == "SECONDARY"
        }
    )

    reasons: JsonObject = {
        "profile_name": PROFILE_NAME,
        "rule_version": RULE_VERSION,
        "candidate": {
            "source_type": candidate.source_type,
            "origin": candidate.origin,
            "company_name": candidate.company_name,
            "title": candidate.title,
            "eligibility_status": (
                candidate.eligibility_status
            ),
            "occupation_class": (
                candidate.occupation_class
            ),
            "backend_relevance": (
                candidate.backend_relevance
            ),
            "seniority_class": (
                candidate.seniority_class
            ),
            "leadership_class": (
                candidate.leadership_class
            ),
        },
        "components": {
            "role": {
                "score": role_score,
                "reason": role_reason,
            },
            "skills": {
                "score": skills_score,
                "groups": skill_reasons,
                "exact": exact,
                "peer": peer,
                "related": related,
                "secondary": secondary,
            },
            "seniority": {
                "score": seniority_score,
                "class": (
                    candidate.seniority_class
                ),
            },
            "leadership": {
                "score": leadership_score,
                "class": (
                    candidate.leadership_class
                ),
            },
            "technology_penalty": {
                "score": technology_penalty,
                "alternate_families": (
                    alternate_families
                ),
            },
        },
        "raw_score": round(
            raw_score,
            2,
        ),
        "score_ceiling": score_ceiling,
        "ceiling_reasons": ceiling_reasons,
        "final_score": score,
        "match_level": match_level,
    }

    return MatchDecision(
        record_kind=candidate.record_kind,
        record_id=candidate.record_id,
        source_type=candidate.source_type,
        origin=candidate.origin,
        company_name=candidate.company_name,
        title=candidate.title,
        occupation_class=(
            candidate.occupation_class
        ),
        backend_relevance=(
            candidate.backend_relevance
        ),
        seniority_class=(
            candidate.seniority_class
        ),
        leadership_class=(
            candidate.leadership_class
        ),
        score=score,
        match_level=match_level,
        role_score=role_score,
        skills_score=skills_score,
        seniority_score=seniority_score,
        leadership_score=leadership_score,
        technology_penalty=(
            technology_penalty
        ),
        score_ceiling=score_ceiling,
        reasons=reasons,
    )


def _role_score(
    candidate: MatchingCandidateRow,
) -> tuple[float, str]:
    key = (
        candidate.occupation_class,
        candidate.backend_relevance,
    )

    if key in ROLE_SCORES:
        if (
            key
            == (
                "SOFTWARE_ENGINEERING",
                "UNKNOWN",
            )
            and _has_strong_backend_core(
                set(
                    candidate.skills
                )
            )
        ):
            return (
                35.0,
                (
                    "SOFTWARE_ENGINEERING:"
                    "UNKNOWN:"
                    "STRONG_BACKEND_CORE"
                ),
            )

        return (
            ROLE_SCORES[key],
            (
                candidate.occupation_class
                + ":"
                + candidate.backend_relevance
            ),
        )

    fallback = {
        "IT_TECHNICAL": 6.0,
        "TECH_ADJACENT": 4.0,
        "UNKNOWN": 3.0,
        "NON_TECHNICAL": 0.0,
    }

    score = fallback.get(
        candidate.occupation_class,
        0.0,
    )

    return (
        score,
        candidate.occupation_class,
    )


def _skills_score(
    skills: set[str],
) -> tuple[
    float,
    list[JsonObject],
]:
    total = 0.0
    reasons: list[JsonObject] = []

    for group in SKILL_GROUPS:
        matched_signals = [
            signal
            for signal in group.signals
            if signal.skill_key in skills
        ]

        raw_group_score = sum(
            signal.points
            for signal in matched_signals
        )

        group_score = min(
            raw_group_score,
            group.max_points,
        )

        total += group_score

        for signal in matched_signals:
            reasons.append(
                {
                    "group": group.name,
                    "group_max": (
                        group.max_points
                    ),
                    "skill_key": (
                        signal.skill_key
                    ),
                    "relation": (
                        signal.relation
                    ),
                    "points": (
                        signal.points
                    ),
                    "group_score": (
                        group_score
                    ),
                }
            )

    return (
        round(
            min(
                total,
                30.0,
            ),
            2,
        ),
        reasons,
    )


def _technology_penalty(
    candidate: MatchingCandidateRow,
    skills: set[str],
) -> tuple[
    float,
    list[str],
]:
    if (
        candidate.occupation_class
        != "SOFTWARE_ENGINEERING"
    ):
        return (
            0.0,
            [],
        )

    if candidate.backend_relevance not in {
        "BACKEND",
        "FULL_STACK",
        "UNKNOWN",
    }:
        return (
            0.0,
            [],
        )

    title_alternate = (
        _title_alternate_families(
            candidate.title
        )
    )

    if (
        title_alternate
        and not _title_has_compatible_core(
            candidate.title
        )
    ):
        return (
            -5.0,
            title_alternate,
        )

    if skills & COMPATIBLE_CORE_SKILLS:
        return (
            0.0,
            [],
        )

    alternate_families = sorted(
        family
        for family, family_skills
        in ALTERNATE_BACKEND_FAMILIES.items()
        if skills & family_skills
    )

    if not alternate_families:
        return (
            0.0,
            [],
        )

    return (
        -5.0,
        alternate_families,
    )


def _score_ceiling(
    candidate: MatchingCandidateRow,
) -> tuple[
    float,
    list[str],
]:
    ceilings = [
        100.0
    ]

    reasons = []

    occupation_ceiling = (
        OCCUPATION_SCORE_CEILINGS.get(
            candidate.occupation_class
        )
    )

    if (
        candidate.occupation_class
        == "SOFTWARE_ENGINEERING"
        and candidate.backend_relevance
        == "NON_BACKEND"
    ):
        occupation_ceiling = 60.0

    if occupation_ceiling is not None:
        ceilings.append(
            occupation_ceiling
        )
        reasons.append(
            (
                "occupation:"
                + candidate.occupation_class
                + ":"
                + str(occupation_ceiling)
            )
        )

    leadership_ceiling = (
        LEADERSHIP_SCORE_CEILINGS.get(
            candidate.leadership_class
        )
    )

    if leadership_ceiling is not None:
        ceilings.append(
            leadership_ceiling
        )
        reasons.append(
            (
                "leadership:"
                + candidate.leadership_class
                + ":"
                + str(leadership_ceiling)
            )
        )

    seniority_ceiling = (
        SENIORITY_SCORE_CEILINGS.get(
            candidate.seniority_class
        )
    )

    if seniority_ceiling is not None:
        ceilings.append(
            seniority_ceiling
        )
        reasons.append(
            (
                "seniority:"
                + candidate.seniority_class
                + ":"
                + str(seniority_ceiling)
            )
        )

    title_seniority_risks = (
        _title_seniority_risks(
            candidate.title
        )
    )

    for (
        risk_key,
        risk_ceiling,
    ) in title_seniority_risks:
        ceilings.append(
            risk_ceiling
        )
        reasons.append(
            (
                "title_seniority_risk:"
                + risk_key
                + ":"
                + str(
                    risk_ceiling
                )
            )
        )

    title_role_mismatches = (
        _title_role_mismatches(
            candidate.title
        )
    )

    if title_role_mismatches:
        ceilings.append(
            40.0
        )
        reasons.append(
            (
                "title_role_mismatch:"
                + ",".join(
                    title_role_mismatches
                )
                + ":40.0"
            )
        )

    title_alternate = (
        _title_alternate_families(
            candidate.title
        )
    )

    if (
        title_alternate
        and not _title_has_compatible_core(
            candidate.title
        )
    ):
        ceilings.append(
            64.0
        )
        reasons.append(
            (
                "title_alternate_stack:"
                + ",".join(
                    title_alternate
                )
                + ":64.0"
            )
        )

    ceiling = min(
        ceilings
    )

    applied_reasons = [
        reason
        for reason in reasons
        if reason.endswith(
            ":" + str(ceiling)
        )
    ]

    return (
        ceiling,
        applied_reasons,
    )


def _match_level(
    score: float,
) -> str:
    if score >= 80:
        return "VERY_HIGH"

    if score >= 65:
        return "HIGH"

    if score >= 45:
        return "MEDIUM"

    return "LOW"
