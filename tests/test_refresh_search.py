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
) -> list[refresh_search.RefreshStep]:
    return refresh_search.build_plan(
        skip_broad=False,
        skip_himalayas=False,
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
