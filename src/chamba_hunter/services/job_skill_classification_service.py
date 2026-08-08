from collections import Counter
from dataclasses import dataclass, field
import html
import re

from chamba_hunter.domain.common import (
    JsonObject,
    utc_now,
)
from chamba_hunter.domain.enums import RunStatus
from chamba_hunter.domain.tracing import Run, RunStep
from chamba_hunter.repositories.job_skill_repository import (
    JobSkillRepository,
    SkillCandidateRow,
    SkillClassificationWrite,
)
from chamba_hunter.repositories.tracing_repository import (
    TracingRepository,
)


RULE_VERSION = "SKILLS_V1"

MAX_EVIDENCE_MATCHES_PER_SOURCE = 3
CONTEXT_RADIUS = 180


@dataclass(frozen=True, slots=True)
class SkillDefinition:
    key: str
    category: str
    patterns: tuple[re.Pattern[str], ...]


@dataclass(frozen=True, slots=True)
class SkillDecision:
    record_kind: str
    record_id: int
    source_type: str
    origin: str
    company_name: str
    eligibility_status: str

    occupation_class: str | None
    backend_relevance: str | None

    title: str

    skill_key: str
    skill_category: str

    title_match: bool
    description_match: bool

    evidence: JsonObject


@dataclass(slots=True)
class SkillClassificationSummary:
    apply: bool

    total_candidates: int = 0
    candidates_with_skills: int = 0
    candidates_without_skills: int = 0
    total_skill_rows: int = 0

    created: int = 0
    updated: int = 0
    deleted: int = 0

    run_id: int | None = None

    decisions: list[
        SkillDecision
    ] = field(default_factory=list)

    candidates: list[
        SkillCandidateRow
    ] = field(default_factory=list)


def _skill(
    key: str,
    category: str,
    *aliases: str,
) -> SkillDefinition:
    return SkillDefinition(
        key=key,
        category=category,
        patterns=tuple(
            re.compile(
                alias,
                re.I,
            )
            for alias in aliases
        ),
    )


SKILL_CATALOG: tuple[
    SkillDefinition,
    ...,
] = (
    _skill("JAVA", "LANGUAGE", r"\bjava\b"),
    _skill("KOTLIN", "LANGUAGE", r"\bkotlin\b"),
    _skill("PYTHON", "LANGUAGE", r"\bpython\b"),
    _skill("GO", "LANGUAGE", r"\bgolang\b"),
    _skill("CSHARP", "LANGUAGE", r"(?<!\w)c#(?!\w)", r"\bc sharp\b"),
    _skill("CPP", "LANGUAGE", r"(?<!\w)c\+\+(?!\w)", r"\bcpp\b"),
    _skill("C", "LANGUAGE", r"\bc language\b"),
    _skill("JAVASCRIPT", "LANGUAGE", r"\bjavascript\b"),
    _skill("TYPESCRIPT", "LANGUAGE", r"\btypescript\b"),
    _skill("PHP", "LANGUAGE", r"\bphp\b"),
    _skill("RUBY", "LANGUAGE", r"\bruby\b"),
    _skill("RUST", "LANGUAGE", r"\brust\b"),
    _skill("SCALA", "LANGUAGE", r"\bscala\b"),
    _skill("CLOJURE", "LANGUAGE", r"\bclojure\b"),
    _skill("ELIXIR", "LANGUAGE", r"\belixir\b"),
    _skill("ERLANG", "LANGUAGE", r"\berlang\b"),
    _skill("SWIFT", "LANGUAGE", r"\bswift\b"),
    _skill("DART", "LANGUAGE", r"\bdart\b"),
    _skill("SQL", "LANGUAGE", r"\bsql\b(?!\s+server)"),
    _skill("BASH", "LANGUAGE", r"\bbash\b", r"\bshell scripting\b"),
    _skill("COBOL", "LANGUAGE", r"\bcobol\b"),
    _skill("ABAP", "LANGUAGE", r"\babap\b"),
    _skill("SPRING_BOOT", "FRAMEWORK", r"\bspring boot\b", r"\bspringboot\b"),
    _skill("SPRING", "FRAMEWORK", r"\bspring framework\b", r"\bspring mvc\b", r"\bspring\b(?!\s+(?:boot|cloud|data|security))"),
    _skill("SPRING_SECURITY", "FRAMEWORK", r"\bspring security\b"),
    _skill("SPRING_DATA", "FRAMEWORK", r"\bspring data\b"),
    _skill("SPRING_CLOUD", "FRAMEWORK", r"\bspring cloud\b"),
    _skill("MICRONAUT", "FRAMEWORK", r"\bmicronaut\b"),
    _skill("QUARKUS", "FRAMEWORK", r"\bquarkus\b"),
    _skill("GRAILS", "FRAMEWORK", r"\bgrails\b"),
    _skill("DOTNET", "FRAMEWORK", r"(?<!asp)\.net(?:\s+core)?(?!\w)", r"\bdotnet\b"),
    _skill("ASP_NET", "FRAMEWORK", r"\basp\.?\s*net(?:\s+core)?\b"),
    _skill("NODEJS", "FRAMEWORK", r"\bnode\.?\s*js\b", r"\bnodejs\b"),
    _skill("NESTJS", "FRAMEWORK", r"\bnest\.?\s*js\b", r"\bnestjs\b"),
    _skill("EXPRESS", "FRAMEWORK", r"\bexpress\.?\s*js\b", r"\bexpressjs\b"),
    _skill("DJANGO", "FRAMEWORK", r"\bdjango\b"),
    _skill("FLASK", "FRAMEWORK", r"\bflask\b"),
    _skill("FASTAPI", "FRAMEWORK", r"\bfastapi\b", r"\bfast api\b"),
    _skill("RAILS", "FRAMEWORK", r"\bruby on rails\b", r"\brails\b"),
    _skill("PHOENIX", "FRAMEWORK", r"\bphoenix framework\b", r"\belixir[/ ]phoenix\b"),
    _skill("LARAVEL", "FRAMEWORK", r"\blaravel\b"),
    _skill("JPA", "FRAMEWORK", r"\bjpa\b", r"\bjava persistence api\b"),
    _skill("HIBERNATE", "FRAMEWORK", r"\bhibernate\b"),
    _skill("KTOR", "FRAMEWORK", r"\bktor\b"),
    _skill("VERTX", "FRAMEWORK", r"\bvert\.?x\b"),
    _skill("PLAY_FRAMEWORK", "FRAMEWORK", r"\bplay framework\b"),
    _skill("REACT_NATIVE", "MOBILE", r"\breact native\b"),
    _skill("REACT", "FRONTEND", r"\breact\.?\s*js\b", r"\breactjs\b", r"\breact\b(?!\s+native)"),
    _skill("ANGULAR", "FRONTEND", r"\bangular\b"),
    _skill("VUE", "FRONTEND", r"\bvue\.?\s*js\b", r"\bvuejs\b"),
    _skill("NEXTJS", "FRONTEND", r"\bnext\.?\s*js\b", r"\bnextjs\b"),
    _skill("ANDROID", "MOBILE", r"\bandroid\b"),
    _skill("JETPACK_COMPOSE", "MOBILE", r"\bjetpack compose\b"),
    _skill("IOS", "MOBILE", r"\bios\b"),
    _skill("FLUTTER", "MOBILE", r"\bflutter\b"),
    _skill("POSTGRESQL", "DATABASE", r"\bpostgresql\b", r"\bpostgres\b"),
    _skill("MYSQL", "DATABASE", r"\bmysql\b"),
    _skill("MARIADB", "DATABASE", r"\bmariadb\b"),
    _skill("PERCONA", "DATABASE", r"\bpercona\b"),
    _skill("ORACLE_DB", "DATABASE", r"\boracle database\b", r"\boracle db\b"),
    _skill("SQL_SERVER", "DATABASE", r"\bsql server\b", r"\bmssql\b"),
    _skill("MONGODB", "DATABASE", r"\bmongodb\b", r"\bmongo db\b"),
    _skill("REDIS", "DATABASE", r"\bredis\b"),
    _skill("DYNAMODB", "DATABASE", r"\bdynamodb\b"),
    _skill("CASSANDRA", "DATABASE", r"\bcassandra\b"),
    _skill("ELASTICSEARCH", "DATABASE", r"\belasticsearch\b"),
    _skill("OPENSEARCH", "DATABASE", r"\bopensearch\b"),
    _skill("FLYWAY", "DATABASE_TOOLING", r"\bflyway\b"),
    _skill("LIQUIBASE", "DATABASE_TOOLING", r"\bliquibase\b"),
    _skill("SNOWFLAKE", "DATA_PLATFORM", r"\bsnowflake\b"),
    _skill("DATABRICKS", "DATA_PLATFORM", r"\bdatabricks\b"),
    _skill("BIGQUERY", "DATA_PLATFORM", r"\bbigquery\b", r"\bbig query\b"),
    _skill("SPARK", "DATA_PLATFORM", r"\bapache spark\b", r"\bspark\b"),
    _skill("KUBEFLOW", "DATA_PLATFORM", r"\bkubeflow\b"),
    _skill("DBT", "DATA_PLATFORM", r"\bdbt\b"),
    _skill("AIRFLOW", "DATA_PLATFORM", r"\bapache airflow\b", r"\bairflow\b"),
    _skill("HADOOP", "DATA_PLATFORM", r"\bhadoop\b"),
    _skill("FLINK", "DATA_PLATFORM", r"\bapache flink\b", r"\bflink\b"),
    _skill("MICROSOFT_FABRIC", "DATA_PLATFORM", r"\bmicrosoft fabric\b"),
    _skill("REDSHIFT", "DATA_PLATFORM", r"\bamazon redshift\b", r"\baws redshift\b", r"\bredshift\b"),
    _skill("POWER_BI", "ANALYTICS", r"\bpower bi\b"),
    _skill("TABLEAU", "ANALYTICS", r"\btableau\b"),
    _skill("LOOKER", "ANALYTICS", r"\blooker(?: studio)?\b"),
    _skill("AWS", "CLOUD", r"\baws\b", r"\bamazon web services\b"),
    _skill("AZURE", "CLOUD", r"\bazure\b(?!\s+(?:devops|pipelines|service bus))"),
    _skill("GCP", "CLOUD", r"\bgcp\b", r"\bgoogle cloud platform\b", r"\bgoogle cloud\b"),
    _skill("EC2", "CLOUD_SERVICE", r"\bec2\b"),
    _skill("RDS", "CLOUD_SERVICE", r"\brds\b"),
    _skill("S3", "CLOUD_SERVICE", r"\bs3\b"),
    _skill("LAMBDA", "CLOUD_SERVICE", r"\baws lambda\b", r"\blambda functions?\b"),
    _skill("ECS", "CLOUD_SERVICE", r"\baws ecs\b", r"\belastic container service\b"),
    _skill("EKS", "CLOUD_SERVICE", r"\baws eks\b", r"\belastic kubernetes service\b"),
    _skill("KINESIS", "CLOUD_SERVICE", r"\bamazon kinesis\b", r"\baws kinesis\b"),
    _skill("DOCKER", "INFRASTRUCTURE", r"\bdocker\b"),
    _skill("KUBERNETES", "INFRASTRUCTURE", r"\bkubernetes\b", r"\bk8s\b"),
    _skill("OPENSHIFT", "INFRASTRUCTURE", r"\bopenshift\b"),
    _skill("OPENSTACK", "INFRASTRUCTURE", r"\bopenstack\b"),
    _skill("CEPH", "INFRASTRUCTURE", r"\bceph\b"),
    _skill("TERRAFORM", "INFRASTRUCTURE", r"\bterraform\b"),
    _skill("PULUMI", "INFRASTRUCTURE", r"\bpulumi\b"),
    _skill("CLOUDFORMATION", "INFRASTRUCTURE", r"\bcloudformation\b", r"\bcloud formation\b"),
    _skill("CDK", "INFRASTRUCTURE", r"\baws cdk\b", r"\bcloud development kit\b"),
    _skill("ANSIBLE", "INFRASTRUCTURE", r"\bansible\b"),
    _skill("HELM", "INFRASTRUCTURE", r"\bhelm\b"),
    _skill("LINUX", "INFRASTRUCTURE", r"\blinux\b"),
    _skill("NGINX", "INFRASTRUCTURE", r"\bnginx\b"),
    _skill("VAULT", "INFRASTRUCTURE", r"\bhashicorp vault\b"),
    _skill("CONSUL", "INFRASTRUCTURE", r"\bhashicorp consul\b", r"\bconsul\b"),
    _skill("NOMAD", "INFRASTRUCTURE", r"\bhashicorp nomad\b"),
    _skill("KAFKA", "MESSAGING", r"\bapache kafka\b", r"\bkafka\b"),
    _skill("RABBITMQ", "MESSAGING", r"\brabbitmq\b", r"\brabbit mq\b"),
    _skill("SQS", "MESSAGING", r"\baws sqs\b", r"\bamazon sqs\b", r"\bsqs\b"),
    _skill("SNS", "MESSAGING", r"\baws sns\b", r"\bamazon sns\b", r"\bsns\b"),
    _skill("MQTT", "MESSAGING", r"\bmqtt\b"),
    _skill("ACTIVEMQ", "MESSAGING", r"\bactivemq\b", r"\bactive mq\b"),
    _skill("PULSAR", "MESSAGING", r"\bapache pulsar\b"),
    _skill("IBM_MQ", "MESSAGING", r"\bibm mq\b", r"\bwebsphere mq\b"),
    _skill("AZURE_SERVICE_BUS", "MESSAGING", r"\bazure service bus\b"),
    _skill("EVENTBRIDGE", "MESSAGING", r"\beventbridge\b", r"\baws eventbridge\b"),
    _skill("GITHUB_ACTIONS", "CI_CD", r"\bgithub actions\b"),
    _skill("GITLAB_CI", "CI_CD", r"\bgitlab ci(?:/cd)?\b", r"\bgitlab cicd\b"),
    _skill("JENKINS", "CI_CD", r"\bjenkins\b"),
    _skill("AZURE_PIPELINES", "CI_CD", r"\bazure pipelines\b"),
    _skill("AZURE_DEVOPS", "CI_CD", r"\bazure devops\b"),
    _skill("ARGOCD", "CI_CD", r"\bargocd\b", r"\bargo cd\b"),
    _skill("GITOPS", "CI_CD", r"\bgitops\b"),
    _skill("CIRCLECI", "CI_CD", r"\bcircleci\b", r"\bcircle ci\b"),
    _skill("TEAMCITY", "CI_CD", r"\bteamcity\b"),
    _skill("BITBUCKET_PIPELINES", "CI_CD", r"\bbitbucket pipelines\b"),
    _skill("REST", "ARCHITECTURE", r"\brestful\b", r"\brest api(?:s)?\b", r"\brest services?\b"),
    _skill("GRAPHQL", "ARCHITECTURE", r"\bgraphql\b"),
    _skill("GRPC", "ARCHITECTURE", r"\bgrpc\b"),
    _skill("OPENAPI", "ARCHITECTURE", r"\bopenapi\b", r"\bopen api specification\b"),
    _skill("SWAGGER", "ARCHITECTURE", r"\bswagger\b"),
    _skill("SOAP", "ARCHITECTURE", r"\bsoap\b"),
    _skill("WEBSOCKETS", "ARCHITECTURE", r"\bwebsockets?\b", r"\bweb sockets?\b"),
    _skill("MICROSERVICES", "ARCHITECTURE", r"\bmicroservices?\b", r"\bmicro services?\b"),
    _skill("DISTRIBUTED_SYSTEMS", "ARCHITECTURE", r"\bdistributed systems?\b"),
    _skill("EVENT_DRIVEN", "ARCHITECTURE", r"\bevent[- ]driven\b"),
    _skill("CQRS", "ARCHITECTURE", r"\bcqrs\b"),
    _skill("EVENT_SOURCING", "ARCHITECTURE", r"\bevent sourcing\b"),
    _skill("SAGA", "ARCHITECTURE", r"\bsagas?\b"),
    _skill("DDD", "ARCHITECTURE", r"\bdomain[- ]driven design\b", r"\bddd\b"),
    _skill("CLEAN_ARCHITECTURE", "ARCHITECTURE", r"\bclean architecture\b"),
    _skill("HEXAGONAL_ARCHITECTURE", "ARCHITECTURE", r"\bhexagonal architecture\b", r"\barquitectura hexagonal\b"),
    _skill("ONION_ARCHITECTURE", "ARCHITECTURE", r"\bonion architecture\b"),
    _skill("SOLID", "ENGINEERING_PRACTICE", r"\bsolid principles\b", r"\bprincipios solid\b"),
    _skill("CLEAN_CODE", "ENGINEERING_PRACTICE", r"\bclean code\b"),
    _skill("OAUTH", "SECURITY", r"\boauth(?:2| 2)?\b"),
    _skill("OIDC", "SECURITY", r"\boidc\b", r"\bopenid connect\b"),
    _skill("JWT", "SECURITY", r"\bjwt\b", r"\bjson web tokens?\b"),
    _skill("SAML", "SECURITY", r"\bsaml\b"),
    _skill("MTLS", "SECURITY", r"\bmtls\b", r"\bmutual tls\b"),
    _skill("RBAC", "SECURITY", r"\brbac\b"),
    _skill("ABAC", "SECURITY", r"\babac\b"),
    _skill("JUNIT", "TESTING", r"\bjunit\b"),
    _skill("MOCKITO", "TESTING", r"\bmockito\b"),
    _skill("PYTEST", "TESTING", r"\bpytest\b"),
    _skill("SELENIUM", "TESTING", r"\bselenium\b"),
    _skill("TESTCONTAINERS", "TESTING", r"\btestcontainers\b", r"\btest containers\b"),
    _skill("SONARQUBE", "TESTING", r"\bsonarqube\b", r"\bsonar qube\b"),
    _skill("PROMETHEUS", "OBSERVABILITY", r"\bprometheus\b"),
    _skill("GRAFANA", "OBSERVABILITY", r"\bgrafana\b"),
    _skill("DATADOG", "OBSERVABILITY", r"\bdatadog\b"),
    _skill("OPENTELEMETRY", "OBSERVABILITY", r"\bopentelemetry\b", r"\bopen telemetry\b"),
    _skill("NEW_RELIC", "OBSERVABILITY", r"\bnew relic\b", r"\bnewrelic\b"),
    _skill("SPLUNK", "OBSERVABILITY", r"\bsplunk\b"),
    _skill("SENTRY", "OBSERVABILITY", r"\bsentry\b"),
    _skill("ELK", "OBSERVABILITY", r"\belk stack\b", r"\belasticsearch logstash kibana\b"),
    _skill("LOKI", "OBSERVABILITY", r"\bgrafana loki\b", r"\bloki\b"),
    _skill("SAP", "BUSINESS_PLATFORM", r"\bsap\b(?!\s+(?:btp|integration suite|fiori|ui5|cpi))"),
    _skill("SAP_BTP", "BUSINESS_PLATFORM", r"\bsap btp\b"),
    _skill("SAP_INTEGRATION_SUITE", "BUSINESS_PLATFORM", r"\bsap integration suite\b", r"\bsap cpi\b"),
    _skill("SAP_FIORI", "BUSINESS_PLATFORM", r"\bsap fiori\b", r"\bfiori/ui5\b", r"\bsap ui5\b"),
    _skill("DYNAMICS_365", "BUSINESS_PLATFORM", r"\bdynamics 365\b"),
    _skill("SALESFORCE", "BUSINESS_PLATFORM", r"\bsalesforce\b"),
    _skill("VTEX", "BUSINESS_PLATFORM", r"\bvtex\b"),
    _skill("OUTSYSTEMS", "BUSINESS_PLATFORM", r"\boutsystems\b"),
    _skill("MUREX", "BUSINESS_PLATFORM", r"\bmurex\b"),
    _skill("IBM_OPENPAGES", "BUSINESS_PLATFORM", r"\bibm openpages\b", r"\bopenpages\b"),
    _skill("SERVICENOW", "BUSINESS_PLATFORM", r"\bservicenow\b", r"\bservice now\b"),
    _skill("WORDPRESS", "BUSINESS_PLATFORM", r"\bwordpress\b"),
    _skill("SHOPIFY", "BUSINESS_PLATFORM", r"\bshopify\b"),
    _skill("MAVEN", "BUILD_TOOL", r"\bmaven\b"),
    _skill("GRADLE", "BUILD_TOOL", r"\bgradle\b"),
    _skill("WEBRTC", "REALTIME", r"\bwebrtc\b"),
    _skill("LIVEKIT", "REALTIME", r"\blivekit\b"),
)


_BLOCK_TAG_PATTERN = re.compile(
    r"</?(?:"
    r"p|div|li|ul|ol|br|"
    r"h1|h2|h3|h4|h5|h6|"
    r"section|article"
    r")[^>]*>",
    re.I,
)

_OTHER_TAG_PATTERN = re.compile(
    r"<[^>]+>"
)

_WHITESPACE_PATTERN = re.compile(
    r"\s+"
)


class JobSkillClassificationService:
    def __init__(
        self,
        repository: JobSkillRepository,
        tracing_repository: TracingRepository,
    ) -> None:
        self.repository = repository
        self.tracing_repository = tracing_repository

    def run(
        self,
        apply: bool = False,
    ) -> SkillClassificationSummary:
        candidates = (
            self.repository.list_scoped_candidates()
        )

        summary = SkillClassificationSummary(
            apply=apply,
            total_candidates=len(candidates),
            candidates=candidates,
        )

        for candidate in candidates:
            summary.decisions.extend(
                _extract_candidate_skills(
                    candidate
                )
            )

        candidate_keys_with_skills = {
            (
                decision.record_kind,
                decision.record_id,
            )
            for decision in summary.decisions
        }

        summary.candidates_with_skills = len(
            candidate_keys_with_skills
        )

        summary.candidates_without_skills = (
            summary.total_candidates
            - summary.candidates_with_skills
        )

        summary.total_skill_rows = len(
            summary.decisions
        )

        if apply:
            self._apply(summary)

        return summary

    def _apply(
        self,
        summary: SkillClassificationSummary,
    ) -> None:
        run = self.tracing_repository.add_run(
            Run(
                command=(
                    "classify_job_skills"
                )
            )
        )

        if run.id is None:
            raise RuntimeError(
                "Skill classification run "
                "must have an id."
            )

        summary.run_id = run.id

        step = self.tracing_repository.add_run_step(
            RunStep(
                run_id=run.id,
                step_name=(
                    "job_skill_classification"
                ),
                items_total=(
                    summary.total_candidates
                ),
            )
        )

        if step.id is None:
            raise RuntimeError(
                "Skill classification run step "
                "must have an id."
            )

        try:
            writes = [
                SkillClassificationWrite(
                    record_kind=decision.record_kind,
                    record_id=decision.record_id,
                    skill_key=decision.skill_key,
                    skill_category=(
                        decision.skill_category
                    ),
                    title_match=decision.title_match,
                    description_match=(
                        decision.description_match
                    ),
                    evidence=decision.evidence,
                    rule_version=RULE_VERSION,
                )
                for decision in summary.decisions
            ]

            counts = (
                self.repository
                .upsert_classifications(
                    classifications=writes,
                    classified_at=utc_now(),
                )
            )

            summary.created = counts.created
            summary.updated = counts.updated
            summary.deleted = counts.deleted

            category_counts = Counter(
                decision.skill_category
                for decision in summary.decisions
            )

            skill_counts = Counter(
                decision.skill_key
                for decision in summary.decisions
            )

            source_counts = Counter(
                _source_method(decision)
                for decision in summary.decisions
            )

            metadata = {
                "rule_version": RULE_VERSION,
                "scope": (
                    "ARGENTINA_ELIGIBLE_OR_UNKNOWN"
                ),
                "candidates_total": (
                    summary.total_candidates
                ),
                "candidates_with_skills": (
                    summary.candidates_with_skills
                ),
                "candidates_without_skills": (
                    summary.candidates_without_skills
                ),
                "skill_rows": (
                    summary.total_skill_rows
                ),
                "categories": dict(
                    sorted(
                        category_counts.items()
                    )
                ),
                "skills": dict(
                    sorted(
                        skill_counts.items()
                    )
                ),
                "sources": dict(
                    sorted(
                        source_counts.items()
                    )
                ),
                "created": summary.created,
                "updated": summary.updated,
                "deleted": summary.deleted,
            }

            self.tracing_repository.finish_run_step(
                run_step_id=step.id,
                status=RunStatus.SUCCESS,
                items_success=(
                    summary.total_candidates
                ),
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
                items_skipped=(
                    summary.total_candidates
                ),
                metadata={
                    "rule_version": RULE_VERSION,
                },
                error_message=str(error),
            )

            self.tracing_repository.finish_run(
                run_id=run.id,
                status=RunStatus.FAILED,
            )

            raise


def _extract_candidate_skills(
    candidate: SkillCandidateRow,
) -> list[SkillDecision]:
    title = _clean_text(
        candidate.title
    )

    description = _clean_text(
        candidate.description
    )

    decisions: list[
        SkillDecision
    ] = []

    for skill in SKILL_CATALOG:
        title_matches = _find_matches(
            text=title,
            patterns=skill.patterns,
        )

        description_matches = _find_matches(
            text=description,
            patterns=skill.patterns,
        )

        if (
            not title_matches
            and not description_matches
        ):
            continue

        evidence: JsonObject = {
            "title_matches": (
                _build_evidence_matches(
                    text=title,
                    matches=title_matches,
                )
            ),
            "description_matches": (
                _build_evidence_matches(
                    text=description,
                    matches=description_matches,
                )
            ),
        }

        decisions.append(
            SkillDecision(
                record_kind=candidate.record_kind,
                record_id=candidate.record_id,
                source_type=candidate.source_type,
                origin=candidate.origin,
                company_name=candidate.company_name,
                eligibility_status=(
                    candidate.eligibility_status
                ),
                occupation_class=(
                    candidate.occupation_class
                ),
                backend_relevance=(
                    candidate.backend_relevance
                ),
                title=candidate.title,
                skill_key=skill.key,
                skill_category=skill.category,
                title_match=bool(
                    title_matches
                ),
                description_match=bool(
                    description_matches
                ),
                evidence=evidence,
            )
        )

    return decisions


def _clean_text(
    value: str | None,
) -> str:
    if not value:
        return ""

    value = html.unescape(
        value
    )

    value = _BLOCK_TAG_PATTERN.sub(
        " ",
        value,
    )

    value = _OTHER_TAG_PATTERN.sub(
        " ",
        value,
    )

    value = _WHITESPACE_PATTERN.sub(
        " ",
        value,
    )

    return value.strip()


def _find_matches(
    text: str,
    patterns: tuple[
        re.Pattern[str],
        ...,
    ],
) -> list[re.Match[str]]:
    if not text:
        return []

    matches: list[
        re.Match[str]
    ] = []

    seen_spans: set[
        tuple[int, int]
    ] = set()

    for pattern in patterns:
        for match in pattern.finditer(
            text
        ):
            span = (
                match.start(),
                match.end(),
            )

            if span in seen_spans:
                continue

            seen_spans.add(
                span
            )

            matches.append(
                match
            )

    matches.sort(
        key=lambda match: (
            match.start(),
            match.end(),
        )
    )

    return matches


def _build_evidence_matches(
    text: str,
    matches: list[
        re.Match[str]
    ],
) -> list[JsonObject]:
    result: list[
        JsonObject
    ] = []

    for match in matches[
        :MAX_EVIDENCE_MATCHES_PER_SOURCE
    ]:
        result.append(
            {
                "text": match.group(0),
                "context": _context(
                    text=text,
                    start=match.start(),
                    end=match.end(),
                ),
            }
        )

    return result


def _context(
    text: str,
    start: int,
    end: int,
) -> str:
    left = max(
        0,
        start - CONTEXT_RADIUS,
    )

    right = min(
        len(text),
        end + CONTEXT_RADIUS,
    )

    return text[
        left:right
    ].strip()


def _source_method(
    decision: SkillDecision,
) -> str:
    if (
        decision.title_match
        and decision.description_match
    ):
        return "TITLE_DESCRIPTION"

    if decision.title_match:
        return "TITLE"

    return "DESCRIPTION"
