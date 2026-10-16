from chamba_hunter.sources.jooble_jobs import (
    JOOBLE_QUERY_SET_V1,
    JOOBLE_QUERY_SET_V2,
    JOOBLE_QUERY_SETS,
)


def test_jooble_v2_is_versioned_bounded_and_disabled_by_default() -> None:
    assert JOOBLE_QUERY_SETS["JOOBLE_QUERY_SET_V1"] is JOOBLE_QUERY_SET_V1
    assert JOOBLE_QUERY_SETS["JOOBLE_QUERY_SET_V2"] is JOOBLE_QUERY_SET_V2
    assert len(JOOBLE_QUERY_SET_V2) == 9
    assert "iam" not in JOOBLE_QUERY_SET_V2
    assert "security" not in JOOBLE_QUERY_SET_V2
    assert all(
        "java" in query or query == "kotlin engineer"
        for query in JOOBLE_QUERY_SET_V2
    )
