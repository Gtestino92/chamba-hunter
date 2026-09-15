from dataclasses import dataclass

from chamba_hunter.commands.acquire_sources_v2 import (
    getonboard_coverage_warning,
    jooble_coverage_warnings,
)


@dataclass(frozen=True, slots=True)
class _JoobleCoverage:
    query: str
    pages_fetched: int
    jobs_fetched: int
    total_count: int | None


def test_getonboard_warns_only_when_final_configured_page_is_full() -> None:
    assert (
        getonboard_coverage_warning(
            pages_fetched=5,
            final_page_size=100,
            max_pages=5,
        )
        == (
            "GetOnBoard coverage warning: "
            "configured page limit reached"
        )
    )

    assert (
        getonboard_coverage_warning(
            pages_fetched=5,
            final_page_size=42,
            max_pages=5,
        )
        is None
    )

    assert (
        getonboard_coverage_warning(
            pages_fetched=4,
            final_page_size=100,
            max_pages=5,
        )
        is None
    )


def test_jooble_warns_only_for_queries_truncated_by_page_limit() -> None:
    warnings = jooble_coverage_warnings(
        query_coverages=(
            _JoobleCoverage(
                query="backend",
                pages_fetched=10,
                jobs_fetched=500,
                total_count=1324,
            ),
            _JoobleCoverage(
                query="spring boot",
                pages_fetched=3,
                jobs_fetched=120,
                total_count=120,
            ),
            _JoobleCoverage(
                query="java developer",
                pages_fetched=10,
                jobs_fetched=500,
                total_count=None,
            ),
        ),
        max_pages_per_query=10,
    )

    assert warnings == [
        "backend: fetched 500 of 1324 available",
    ]
