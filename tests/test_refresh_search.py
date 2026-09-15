from pathlib import Path

import pytest

from chamba_hunter.commands import (
    refresh_search,
)


EXPECTED_ATS_SYNC_MODULES = (
    "sync_greenhouse_jobs",
    "sync_lever_jobs",
    "sync_ashby_jobs",
    "sync_workable_jobs",
    "sync_smartrecruiters_jobs",
    "sync_bamboohr_jobs",
    "sync_hiringroom_jobs",
    "sync_teamtailor_jobs",
    "sync_hibob_jobs",
    "sync_successfactors_jobs",
)

DOWNSTREAM_MODULES = (
    "canonicalize_job_leads",
    "classify_argentina_eligibility",
    "classify_job_occupations",
    "classify_job_skills",
    "classify_job_seniority",
    "match_jobs",
    "prioritize_jobs",
)


def _build_plan(
    *,
    skip_ats: bool = False,
    skip_broad: bool = False,
    skip_himalayas: bool = False,
) -> list[refresh_search.RefreshStep]:
    return refresh_search.build_plan(
        skip_broad=skip_broad,
        skip_himalayas=skip_himalayas,
        skip_ats=skip_ats,
        skip_export=False,
        discover_known_ats_limit=25,
        discover_broad_ats_limit=10,
        himalayas_backfill_days=30,
        himalayas_overlap_hours=48,
        getonboard_max_pages=5,
        jobicy_max_jobs=100,
        wwr_max_jobs=300,
        jooble_max_pages_per_query=2,
        discover_broad_include_scanned=False,
        output=Path(
            "output/chamba-shortlist.xlsx"
        ),
    )


def _modules(
    plan: list[refresh_search.RefreshStep],
) -> list[str]:
    return [
        step.module
        for step in plan
    ]


def test_ats_sync_modules_include_successfactors_once() -> None:
    assert refresh_search.ATS_SYNC_MODULES == (
        EXPECTED_ATS_SYNC_MODULES
    )
    assert (
        refresh_search.ATS_SYNC_MODULES.count(
            "sync_successfactors_jobs"
        )
        == 1
    )


def test_successfactors_runs_before_downstream_steps() -> None:
    modules = _modules(
        _build_plan()
    )

    successfactors_index = modules.index(
        "sync_successfactors_jobs"
    )

    for module in DOWNSTREAM_MODULES:
        assert successfactors_index < modules.index(
            module
        )


def test_skip_ats_removes_all_ats_sync_modules() -> None:
    modules = _modules(
        _build_plan(
            skip_ats=True,
        )
    )

    for module in EXPECTED_ATS_SYNC_MODULES:
        assert module not in modules


def test_plan_only_mode_does_not_execute_subprocesses(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError(
            "plan-only mode must not execute subprocesses"
        )

    monkeypatch.setattr(
        refresh_search.subprocess,
        "run",
        fail_if_called,
    )
    monkeypatch.setattr(
        refresh_search.sys,
        "argv",
        [
            "refresh_search",
        ],
    )

    refresh_search.main()

    output = capsys.readouterr().out

    assert "Mode: PLAN ONLY" in output
    assert "No commands were executed." in output
    assert (
        "chamba_hunter.commands.sync_successfactors_jobs"
        in output
    )


def test_routine_settings_preserve_existing_defaults() -> None:
    settings = refresh_search.resolve_settings(
        deep=False,
        discover_known_ats_limit=None,
        discover_broad_ats_limit=None,
        himalayas_backfill_days=None,
        himalayas_overlap_hours=None,
        getonboard_max_pages=None,
        jobicy_max_jobs=None,
        wwr_max_jobs=None,
        jooble_max_pages_per_query=None,
    )

    assert settings.search_depth == "ROUTINE"
    assert settings.discover_known_ats_limit == 25
    assert settings.discover_broad_ats_limit == 10
    assert settings.himalayas_backfill_days == 30
    assert settings.himalayas_overlap_hours == 48
    assert settings.getonboard_max_pages == 5
    assert settings.jobicy_max_jobs == 100
    assert settings.wwr_max_jobs == 300
    assert settings.jooble_max_pages_per_query == 2
    assert not settings.discover_broad_include_scanned


def test_deep_settings_select_deep_defaults() -> None:
    settings = refresh_search.resolve_settings(
        deep=True,
        discover_known_ats_limit=None,
        discover_broad_ats_limit=None,
        himalayas_backfill_days=None,
        himalayas_overlap_hours=None,
        getonboard_max_pages=None,
        jobicy_max_jobs=None,
        wwr_max_jobs=None,
        jooble_max_pages_per_query=None,
    )

    assert settings.search_depth == "DEEP"
    assert settings.discover_known_ats_limit == 250
    assert settings.discover_broad_ats_limit == 100
    assert settings.himalayas_backfill_days == 30
    assert settings.himalayas_overlap_hours == 720
    assert settings.getonboard_max_pages == 25
    assert settings.jobicy_max_jobs == 100
    assert settings.wwr_max_jobs == 1000
    assert settings.jooble_max_pages_per_query == 10
    assert settings.discover_broad_include_scanned


def test_explicit_flags_override_deep_defaults() -> None:
    settings = refresh_search.resolve_settings(
        deep=True,
        discover_known_ats_limit=None,
        discover_broad_ats_limit=0,
        himalayas_backfill_days=None,
        himalayas_overlap_hours=None,
        getonboard_max_pages=None,
        jobicy_max_jobs=None,
        wwr_max_jobs=None,
        jooble_max_pages_per_query=20,
    )

    assert settings.discover_broad_ats_limit == 0
    assert settings.jooble_max_pages_per_query == 20


def test_deep_plan_uses_full_himalayas_actionable_overlap() -> None:
    settings = refresh_search.resolve_settings(
        deep=True,
        discover_known_ats_limit=None,
        discover_broad_ats_limit=None,
        himalayas_backfill_days=None,
        himalayas_overlap_hours=None,
        getonboard_max_pages=None,
        jobicy_max_jobs=None,
        wwr_max_jobs=None,
        jooble_max_pages_per_query=None,
    )

    plan = refresh_search.build_plan(
        skip_broad=False,
        skip_himalayas=False,
        skip_ats=False,
        skip_export=True,
        discover_known_ats_limit=(
            settings.discover_known_ats_limit
        ),
        discover_broad_ats_limit=(
            settings.discover_broad_ats_limit
        ),
        himalayas_backfill_days=(
            settings.himalayas_backfill_days
        ),
        himalayas_overlap_hours=(
            settings.himalayas_overlap_hours
        ),
        getonboard_max_pages=(
            settings.getonboard_max_pages
        ),
        jobicy_max_jobs=settings.jobicy_max_jobs,
        wwr_max_jobs=settings.wwr_max_jobs,
        jooble_max_pages_per_query=(
            settings.jooble_max_pages_per_query
        ),
        output=Path(
            "output/chamba-shortlist.xlsx"
        ),
        discover_broad_include_scanned=(
            settings.discover_broad_include_scanned
        ),
    )

    broad = plan[0]

    assert broad.module == "acquire_sources_v2"
    assert "--himalayas-overlap-hours" in broad.arguments
    assert "720" in broad.arguments


def test_deep_jobicy_remains_at_real_client_maximum() -> None:
    settings = refresh_search.resolve_settings(
        deep=True,
        discover_known_ats_limit=None,
        discover_broad_ats_limit=None,
        himalayas_backfill_days=None,
        himalayas_overlap_hours=None,
        getonboard_max_pages=None,
        jobicy_max_jobs=None,
        wwr_max_jobs=None,
        jooble_max_pages_per_query=None,
    )

    assert settings.jobicy_max_jobs == 100


def test_deep_plan_only_mode_does_not_execute_subprocesses(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError(
            "plan-only mode must not execute subprocesses"
        )

    monkeypatch.setattr(
        refresh_search.subprocess,
        "run",
        fail_if_called,
    )
    monkeypatch.setattr(
        refresh_search.sys,
        "argv",
        [
            "refresh_search",
            "--deep",
        ],
    )

    refresh_search.main()

    output = capsys.readouterr().out

    assert "Mode: PLAN ONLY" in output
    assert "Search depth: DEEP" in output
    assert "--getonboard-max-pages 25" in output
    assert "--jooble-max-pages-per-query 10" in output
    assert "--include-scanned" in output
    assert "No commands were executed." in output


def test_skip_flags_retain_current_plan_behavior() -> None:
    modules = _modules(
        _build_plan(
            skip_broad=True,
            skip_himalayas=True,
            skip_ats=True,
        )
    )

    assert "acquire_sources_v2" not in modules

    modules = _modules(
        _build_plan(
            skip_himalayas=True,
        )
    )
    broad = modules.index(
        "acquire_sources_v2"
    )
    assert (
        "--skip-himalayas"
        in _build_plan(
            skip_himalayas=True,
        )[broad].arguments
    )


def test_broad_ats_deep_discovery_is_bounded() -> None:
    plan = refresh_search.build_plan(
        skip_broad=False,
        skip_himalayas=False,
        skip_ats=True,
        skip_export=True,
        discover_known_ats_limit=0,
        discover_broad_ats_limit=100,
        himalayas_backfill_days=30,
        himalayas_overlap_hours=720,
        getonboard_max_pages=25,
        jobicy_max_jobs=100,
        wwr_max_jobs=1000,
        jooble_max_pages_per_query=10,
        output=Path(
            "output/chamba-shortlist.xlsx"
        ),
        discover_broad_include_scanned=True,
    )

    broad_discovery = [
        step
        for step in plan
        if step.module == "discover_broad_ats"
    ][0]

    assert broad_discovery.arguments == (
        "--limit",
        "100",
        "--include-scanned",
    )
